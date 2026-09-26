# -*- coding: utf-8 -*-
"""Card #30: zeladores locais (Hermes organiza, Qwen confere) na rotina 'memoria' do coletor. Ollama falso (urlopen
trocado), sem rede e sem banco: coleta ativa registra pausado_pela_coleta; um modelo por vez (keep_alive 0 na API
nativa); tokens = prompt_eval_count + eval_count e custo R$ 0 na linha de Execuções; sem revisão não vira aprovado.
Rodar: python3 testes/test_zeladores.py, na pasta nubi."""
import io
import json
import os
import sys
import tempfile
import urllib.error
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402


class OllamaFalso:
    """Guarda cada pedido e responde como a API nativa (/api/chat); anota que modelos ficaram carregados."""

    def __init__(self, respostas):
        self.respostas, self.pedidos, self.carregados, self.juntos = list(respostas), [], set(), False

    def __call__(self, req, timeout=None):
        corpo = json.loads(req.data.decode())
        self.pedidos.append((req.full_url, corpo))
        self.carregados.add(corpo["model"])
        self.juntos = self.juntos or len(self.carregados) > 1
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        if corpo.get("keep_alive") == 0:
            self.carregados.discard(corpo["model"])   # o Ollama descarrega logo depois de responder
        return io.BytesIO(json.dumps(r).encode())


def _preparar(ollama):
    chamadas = {"registrar": [], "salvar": []}
    c.token_nubi = lambda cfg: "T"
    c._outra_rodando = lambda: None
    c._fora_da_janela_coleta = lambda: True
    c.urllib.request.urlopen = ollama

    def api(token, rota, params=None, corpo=None, metodo=None, timeout=300):
        if rota == "coletor_registrar":
            chamadas["registrar"].append(dict(corpo))
            return {"id": 7}
        if rota == "conhecimento_pendente":
            return {"itens": [{"fonte": "reuniao_mensagens:2", "autor": "Bruno", "texto": "decidi X"}]}
        if rota == "conhecimento":
            return {"itens": []}
        if rota == "conhecimento_salvar":
            chamadas["salvar"].append(dict(corpo))
            return {"ok": True}
        raise AssertionError(rota)
    c.api = api
    return chamadas


REG = '[{"tipo": "decisao", "titulo": "Decisão X", "texto": "O Bruno decidiu X.", "fonte": "reuniao_mensagens:2"}]'


def test_coleta_ativa_nao_inicia_e_registra_pausado_pela_coleta():
    ollama = OllamaFalso([])
    chamadas = _preparar(ollama)
    c._outra_rodando = lambda: 4242
    assert c.cmd_hermes_memoria(None, {}) == 0
    assert ollama.pedidos == []                                    # nenhum modelo carregado durante a coleta
    assert len(chamadas["registrar"]) == 1
    r = chamadas["registrar"][0]
    assert r["mensagem"] == "pausado_pela_coleta" and r["tarefa"] == "memoria" and r["em_andamento"] is False
    assert "id" not in r      # linha nova: o servidor não marca a rotina como feita e ela roda depois da coleta


def test_um_modelo_por_vez_e_tokens_na_linha_de_execucoes():
    ollama = OllamaFalso([{"message": {"content": REG}, "prompt_eval_count": 120, "eval_count": 30},
                          {"message": {"content": '[{"nota": "Aprovado, sem contradição."}]'},
                           "prompt_eval_count": 20, "eval_count": 10}])
    chamadas = _preparar(ollama)
    assert c.cmd_hermes_memoria(None, {}) == 0
    assert [p[1]["model"] for p in ollama.pedidos] == ["hermes3:8b", "qwen3:8b"]
    assert all(u.endswith("/api/chat") and b["keep_alive"] == 0 for u, b in ollama.pedidos)
    assert not ollama.juntos, "Hermes e Qwen não podem ficar carregados juntos no Ollama"
    fim = chamadas["registrar"][-1]
    assert fim["ok"] is True and fim["id"] == 7
    assert "Hermes 150 tokens" in fim["mensagem"] and "Qwen 30 tokens" in fim["mensagem"], fim["mensagem"]
    assert "custo R$ 0" in fim["mensagem"]
    assert "Revisão (Qwen): Aprovado" in chamadas["salvar"][0]["texto"]


def test_tokens_ausentes_aparecem_como_nao_informados_nunca_zero():
    ollama = OllamaFalso([{"message": {"content": REG}},
                          {"message": {"content": '[{"nota": "Aprovado."}]'}, "prompt_eval_count": 5, "eval_count": 5}])
    chamadas = _preparar(ollama)
    assert c.cmd_hermes_memoria(None, {}) == 0
    msg = chamadas["registrar"][-1]["mensagem"]
    assert "Hermes Tokens não informados" in msg and "Hermes 0" not in msg and "Qwen 10 tokens" in msg, msg


def test_sem_revisao_do_qwen_nao_aparece_como_aprovado():
    ollama = OllamaFalso([{"message": {"content": REG}, "prompt_eval_count": 1, "eval_count": 1},
                          urllib.error.URLError("Qwen fora do ar")])
    chamadas = _preparar(ollama)
    assert c.cmd_hermes_memoria(None, {}) == 0
    texto = chamadas["salvar"][0]["texto"]
    assert "Sem revisão registrada." in texto and "Aprovado" not in texto


if __name__ == "__main__":
    falhou = 0
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            try:
                f()
                print("ok  ", nome)
            except Exception as e:  # noqa: BLE001
                falhou += 1
                print("FALHOU", nome, repr(e)[:400])
    sys.exit(1 if falhou else 0)
