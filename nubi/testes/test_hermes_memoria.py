# -*- coding: utf-8 -*-
"""Card #39: rotina 'memoria' — o Hermes (Mac mini) lê a Sala e os cards concluídos e grava na caixa de
conhecimento; o Qwen revisa. Testa o lado do servidor (rota conhecimento_pendente) e o do coletor (comando
hermes-memoria), sem rede, sem Ollama e sem banco de verdade. Rodar: python3 testes/test_hermes_memoria.py, na pasta nubi."""
import os
import sys
import tempfile
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import nubi_web as w  # noqa: E402

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402


# ---------- servidor: _conhecimento_pendente ----------

class RepoServidor:
    def __init__(self, rotina=None, msgs=None, cards=None):
        self.rotina, self.msgs, self.cards = rotina, msgs or [], cards or []

    def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
        if tab == "rotinas":
            return [self.rotina] if self.rotina else []
        if tab == "reuniao_mensagens":
            desde = params["criado_em"][3:]
            return [m for m in self.msgs if m["criado_em"] > desde]
        if tab == "reuniao_tarefas":
            desde = params["atualizado_em"][3:]
            return [t for t in self.cards if t["atualizado_em"] > desde]
        return []


def test_pendente_usa_a_ultima_execucao_da_rotina_memoria():
    corte = "2026-09-25T12:00:00+00:00"
    r = RepoServidor(rotina={"ultima_execucao": corte},
                      msgs=[{"id": 1, "autor": "Bruno", "texto": "antes do corte", "criado_em": "2026-09-25T11:00:00+00:00"},
                            {"id": 2, "autor": "Bruno", "texto": "aprovei o card #39", "criado_em": "2026-09-25T13:00:00+00:00"}],
                      cards=[{"id": 39, "titulo": "Card novo", "notas": "", "relatorio": "## O que foi feito\nx",
                              "atualizado_em": "2026-09-25T14:00:00+00:00"}])
    itens, desde = w._conhecimento_pendente(r)
    assert desde == corte
    assert len(itens) == 2, itens
    assert itens[0] == {"fonte": "reuniao_mensagens:2", "autor": "Bruno", "texto": "aprovei o card #39"}
    assert itens[1]["fonte"] == "reuniao_tarefas:39" and "Card novo" in itens[1]["texto"]


def test_pendente_sem_rotina_ainda_cai_para_24h():
    r = RepoServidor(rotina=None, msgs=[], cards=[])
    itens, desde = w._conhecimento_pendente(r)
    assert itens == []
    ago = datetime.now(timezone.utc) - timedelta(hours=24)
    assert abs((datetime.fromisoformat(desde) - ago).total_seconds()) < 60


def test_pendente_sem_nada_novo_fica_vazio():
    r = RepoServidor(rotina={"ultima_execucao": "2026-09-25T12:00:00+00:00"},
                      msgs=[{"id": 1, "autor": "x", "texto": "y", "criado_em": "2026-09-25T11:00:00+00:00"}], cards=[])
    itens, _ = w._conhecimento_pendente(r)
    assert itens == []


# ---------- coletor: _json_lista ----------

def test_json_lista_aceita_texto_em_volta_e_recusa_o_que_nao_for_lista():
    assert c._json_lista('aqui está:\n[{"titulo": "a"}]\nprontinho') == [{"titulo": "a"}]
    assert c._json_lista('{"titulo": "a"}') == []          # objeto, não lista
    assert c._json_lista("não é json") == []
    assert c._json_lista("") == []


# ---------- coletor: cmd_hermes_memoria ----------

def _preparar(fora_da_coleta=True):
    chamadas = {"registrar": [], "salvar": [], "ollama": []}
    c.token_nubi = lambda cfg: "T"
    c._outra_rodando = lambda: None
    c._fora_da_janela_coleta = lambda: fora_da_coleta

    def api(token, rota, params=None, corpo=None, metodo=None, timeout=300):
        if rota == "coletor_registrar":
            chamadas["registrar"].append(dict(corpo))
            return {"id": 1}
        if rota == "conhecimento_pendente":
            return {"itens": chamadas.get("pendente", [])}
        if rota == "conhecimento":
            termo = (params or {}).get("q", "").lower()
            return {"itens": [x for x in chamadas.get("existentes", []) if termo in x["titulo"].lower()]}
        if rota == "conhecimento_salvar":
            chamadas["salvar"].append(dict(corpo))
            return {"ok": True}
        raise AssertionError(rota)
    c.api = api
    return chamadas


def test_nao_roda_durante_a_janela_da_coleta():
    chamadas = _preparar(fora_da_coleta=False)   # dentro de 00:30-06:40 em Brasília
    assert c.cmd_hermes_memoria(None, {}) == 0
    assert chamadas["registrar"] == []


def test_nao_roda_com_outra_coleta_em_andamento():
    chamadas = _preparar()
    c._outra_rodando = lambda: 999
    assert c.cmd_hermes_memoria(None, {}) == 0
    assert chamadas["registrar"] == []


def test_nada_pendente_marca_ok_sem_gravar_nada():
    chamadas = _preparar()
    chamadas["pendente"] = []
    assert c.cmd_hermes_memoria(None, {}) == 0
    assert len(chamadas["registrar"]) == 2
    assert chamadas["registrar"][1]["ok"] is True and "nada novo" in chamadas["registrar"][1]["mensagem"]
    assert chamadas["salvar"] == []


def test_grava_registro_novo_com_revisao_do_qwen():
    chamadas = _preparar()
    chamadas["pendente"] = [{"fonte": "reuniao_mensagens:2", "autor": "Bruno", "texto": "aprovei o card #39"}]
    chamadas["existentes"] = []
    respostas = ['[{"tipo": "decisao", "titulo": "Card 39 aprovado", "texto": "O Bruno aprovou o card #39.", '
                 '"fonte": "reuniao_mensagens:2"}]',
                 '[{"nota": "Aprovado, sem contradição."}]']
    c._chamar_ollama = lambda modelo, sistema, pedido, timeout=300: respostas.pop(0)
    assert c.cmd_hermes_memoria(None, {}) == 0
    assert len(chamadas["salvar"]) == 1
    s = chamadas["salvar"][0]
    assert s["autor"] == "Hermes" and s["tipo"] == "decisao" and "id" not in s
    assert "O Bruno aprovou o card #39." in s["texto"] and "Revisão (Qwen): Aprovado, sem contradição." in s["texto"]
    assert chamadas["registrar"][1]["ok"] is True and "1 de 1" in chamadas["registrar"][1]["mensagem"]


def test_atualiza_registro_existente_em_vez_de_duplicar():
    chamadas = _preparar()
    chamadas["pendente"] = [{"fonte": "reuniao_mensagens:9", "autor": "Bruno", "texto": "novo detalhe sobre o mesmo assunto"}]
    chamadas["existentes"] = [{"id": 501, "tipo": "decisao", "titulo": "Card 39 aprovado"}]
    respostas = ['[{"tipo": "decisao", "titulo": "Card 39 aprovado", "texto": "Detalhe extra.", "fonte": "reuniao_mensagens:9"}]',
                 '[{"nota": "Atualiza o registro já existente."}]']
    c._chamar_ollama = lambda modelo, sistema, pedido, timeout=300: respostas.pop(0)
    assert c.cmd_hermes_memoria(None, {}) == 0
    assert len(chamadas["salvar"]) == 1 and chamadas["salvar"][0]["id"] == 501   # atualiza, não duplica


def test_hermes_sem_nada_relevante_nao_grava():
    chamadas = _preparar()
    chamadas["pendente"] = [{"fonte": "reuniao_mensagens:3", "autor": "Bruno", "texto": "bom dia"}]
    c._chamar_ollama = lambda modelo, sistema, pedido, timeout=300: "[]"
    assert c.cmd_hermes_memoria(None, {}) == 0
    assert chamadas["salvar"] == []
    assert "não achou nada relevante" in chamadas["registrar"][1]["mensagem"]


def test_ollama_fora_do_ar_registra_erro():
    chamadas = _preparar()
    chamadas["pendente"] = [{"fonte": "reuniao_mensagens:4", "autor": "Bruno", "texto": "algo"}]

    def falha(*a, **k):
        raise urllib.error.URLError("recusou a conexão")
    c._chamar_ollama = falha
    assert c.cmd_hermes_memoria(None, {}) == 1
    assert chamadas["registrar"][1]["ok"] is False and "Ollama" in chamadas["registrar"][1]["mensagem"]


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
