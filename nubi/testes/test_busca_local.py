# -*- coding: utf-8 -*-
"""Card #29: busca semântica local. O despachante do Mac gera o vetor (nomic-embed-text no Ollama do Mac) de cada item
novo da caixa de conhecimento e a busca devolve os 5 mais parecidos; sem Ollama, cai para a busca por palavras.
Ollama falso numa porta local e nubi em memória (sem rede, sem banco). Rodar: python3 testes/test_busca_local.py, na pasta nubi."""
import hashlib
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import nubi_web as w  # noqa: E402

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402

# ---------- Ollama falso: "significado" = palavras com sinônimos juntados no mesmo lugar do vetor ----------
SINONIMOS = {"fuso": "horario", "brasilia": "horario", "relogio": "horario", "dono": "bruno"}
PEDIDOS = []


def _vetor(texto):
    v = [0.0] * 64
    for p in c._palavras(texto.split(": ", 1)[-1]):
        v[int(hashlib.md5(SINONIMOS.get(p, p).encode()).hexdigest(), 16) % 64] += 1.0
    return v


class Ollama(BaseHTTPRequestHandler):
    def do_POST(self):
        d = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        PEDIDOS.append(d)
        corpo = json.dumps({"model": d["model"], "embeddings": [_vetor(d["input"])]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *a):
        pass


srv = HTTPServer(("127.0.0.1", 0), Ollama)
threading.Thread(target=srv.serve_forever, daemon=True).start()
LIGADO = f"http://127.0.0.1:{srv.server_port}/api/embed"
DESLIGADO = "http://127.0.0.1:9/api/embed"          # porta sem ninguém: Mac/Ollama fora do ar


# ---------- nubi em memória ----------

class Repo:
    def __init__(self, itens, com_coluna=True):
        self.itens, self.com_coluna = itens, com_coluna

    @staticmethod
    def _eq(v):
        return f"eq.{v}"

    def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
        params = params or {}
        if tab != "conhecimento":
            return []
        if not self.com_coluna and ("vetor_local" in str(params.get("select")) or "vetor_local" in params
                                    or "vetor_local" in (corpo or {})):
            raise w.ErroNuvem("column conhecimento.vetor_local does not exist")
        if metodo == "PATCH":
            it = next(i for i in self.itens if f"eq.{i['id']}" == params["id"])
            it.update(corpo)
            return None
        linhas = self.itens
        if params.get("vetor_local") == "is.null":
            linhas = [i for i in linhas if not i.get("vetor_local")]
        if str(params.get("criado_em", "")).startswith("gte."):
            linhas = [i for i in linhas if i["criado_em"] >= params["criado_em"][4:]]
        cols = params.get("select", "").split(",")
        return [{k: v for k, v in i.items() if k in cols} for i in linhas][:int(params.get("limit") or 999)]


def _item(i, titulo, texto, criado="2026-09-28T10:00:00+00:00"):
    return {"id": i, "tipo": "aprendizado", "titulo": titulo, "texto": texto, "autor": "x", "fonte": None, "fixo": False,
            "atualizado_em": criado, "criado_em": criado}


# ---------- valores originais (antes de qualquer patch), para restaurar depois de cada teste ----------
_ORIG_W = {"RepoSupabase": w.RepoSupabase, "ligar_registro_uso": w.ligar_registro_uso,
           "indexar_aos_poucos": w.indexar_aos_poucos, "ferreiro_proximo": w.ferreiro_proximo}
_ORIG_ATENDIMENTO = {f: getattr(w.atendimento, f) for f in
                     ("atendente_proximo", "sac_proximo", "retomar_esquecidas", "aprender_aos_poucos", "fichar_aos_poucos")}
_ORIG_C = {"api": c.api, "token_nubi": c.token_nubi, "EMBED": c.EMBED, "_info_mac": c._info_mac}


def _restaurar():
    """Desfaz os monkeypatches de _ligar(): sem isso, o estado vaza para os testes de outros arquivos que rodarem
    depois no mesmo processo (a suíte inteira roda tudo junto)."""
    w.RepoSupabase = _ORIG_W["RepoSupabase"]
    w.ligar_registro_uso = _ORIG_W["ligar_registro_uso"]
    w.indexar_aos_poucos = _ORIG_W["indexar_aos_poucos"]
    w.ferreiro_proximo = _ORIG_W["ferreiro_proximo"]
    for f, fn in _ORIG_ATENDIMENTO.items():
        setattr(w.atendimento, f, fn)
    c.api = _ORIG_C["api"]
    c.token_nubi = _ORIG_C["token_nubi"]
    c.EMBED = _ORIG_C["EMBED"]
    c._info_mac = _ORIG_C["_info_mac"]


def _ligar(repo, ollama):
    """c.api fala com o nubi em memória (rota atender de verdade); o mac_tick não mexe no resto do nubi."""
    w.RepoSupabase = lambda token: repo
    w.ligar_registro_uso = lambda *a, **k: None
    w.indexar_aos_poucos = lambda *a, **k: None
    w.ferreiro_proximo = lambda *a, **k: ""
    for f in ("atendente_proximo", "sac_proximo", "retomar_esquecidas", "aprender_aos_poucos", "fichar_aos_poucos"):
        setattr(w.atendimento, f, lambda *a, **k: None)

    def api(token, rota, params=None, corpo=None, metodo=None, timeout=300, _de_novo=True):
        m = metodo or ("POST" if corpo is not None else "GET")
        st, _, dados, _ = w.atender(m, rota, {k: str(v) for k, v in (params or {}).items()},
                                    json.dumps(corpo).encode() if corpo is not None else b"", "tok")
        assert st == 200, dados
        return json.loads(dados)
    c.api = api
    c.token_nubi = lambda cfg: "tok"
    c.EMBED = ollama
    c._info_mac = lambda: {"ollama": ollama == LIGADO, "modelos": ["nomic-embed-text:latest"]}
    try:
        os.remove(c.PASTA / "despachante.json")
    except OSError:
        pass


def _caixa():
    return [_item(1, "Horário", "Sempre usar o de Brasília ao falar com o Bruno.", "2026-09-20T00:00:00+00:00"),   # antigo
            _item(2, "Branch de trabalho", "Nunca publicar versão velha da branch claude."),
            _item(3, "Coletor", "O coletor do Mac baixa os arquivos do Nubimetrics às 7h."),
            _item(4, "Custo", "Teto de US$ 10 por dia para o Ferreiro."),
            _item(5, "Horário do relatório", "Relatório sai com hora de Brasília (UTC-3)."),
            _item(6, "Estoque", "O estoque vem do UpSeller."),
            _item(7, "Card", "Card aprovado vai para a fila do programador.")]


def test_despachante_grava_o_vetor_dos_itens_novos_e_nao_dos_antigos():
    repo = Repo(_caixa())
    try:
        _ligar(repo, LIGADO)
        c.despachar({})                     # 1º sinal: o nubi pede os itens novos; o Mac gera os vetores
        c.despachar({})                     # 2º sinal: os vetores vão para o nubi
        assert all(i.get("vetor_local") for i in repo.itens if i["id"] != 1), repo.itens
        assert not repo.itens[0].get("vetor_local")                 # item de antes do card: não reprocessa
        assert all(p["model"] == "nomic-embed-text" for p in PEDIDOS)
    finally:
        _restaurar()


def test_busca_com_ollama_traz_o_parecido_entre_os_5_e_no_maximo_5():
    repo = Repo(_caixa())
    try:
        _ligar(repo, LIGADO)
        c.despachar({})
        c.despachar({})
        repo.itens.append(_item(8, "Fuso", "Qual relógio o dono usa? UTC-3."))        # item de teste
        c.despachar({})
        c.despachar({})
        assert repo.itens[-1].get("vetor_local")
        achou = c.buscar_conhecimento("tok", "em que fuso horário falo com o dono?")
        assert len(achou) == 5, achou
        assert achou[0]["id"] in (5, 8) and 8 in [a["id"] for a in achou], achou
        assert all("vetor_local" not in a for a in achou)
        assert PEDIDOS[-1]["input"].startswith("search_query: ")
    finally:
        _restaurar()


def test_sem_ollama_cai_para_palavras_e_continua_respondendo():
    repo = Repo(_caixa())
    try:
        _ligar(repo, LIGADO)
        c.despachar({})
        c.despachar({})
        _ligar(repo, DESLIGADO)                 # Mac/Ollama parado: nada de erro
        assert c.despachar({}) == 0
        achou = c.buscar_conhecimento("tok", "o coletor baixa os arquivos do Nubimetrics?")
        assert achou and achou[0]["id"] == 3, achou
        assert c.buscar_conhecimento("tok", "zzzz qqqq") == []        # nada parecido: lista vazia, nada inventado
    finally:
        _restaurar()


def test_sem_a_coluna_nova_o_nubi_segue_e_a_busca_usa_palavras():
    repo = Repo(_caixa(), com_coluna=False)                # migração ainda não aplicada
    try:
        _ligar(repo, LIGADO)
        assert c.despachar({}) == 0
        assert c.despachar({}) == 0
        achou = c.buscar_conhecimento("tok", "teto de custo do Ferreiro")
        assert achou and achou[0]["id"] == 4, achou
    finally:
        _restaurar()


if __name__ == "__main__":
    falhas = 0
    for nome, f in list(globals().items()):
        if nome.startswith("test_") and callable(f):
            try:
                f()
                print(f"ok   {nome}")
            except Exception as e:  # noqa: BLE001
                falhas += 1
                print(f"FALHOU {nome}: {type(e).__name__}: {e}")
    print("tudo certo" if not falhas else f"{falhas} falha(s)")
    sys.exit(1 if falhas else 0)
