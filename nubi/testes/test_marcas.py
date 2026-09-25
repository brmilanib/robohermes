"""Nomes de marcas: grafia parecida (erro de digitação do próprio ranking, card de 25/09)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import nubi_web as w  # noqa: E402


def test_grafia_parecida():
    assert w.grafia_parecida("LATAFFA", "LATTAFA")          # 2 letras trocadas: antes passava batido (86%)
    assert not w.grafia_parecida("ARMAF", "ARMANI")         # marcas diferentes
    assert not w.grafia_parecida("DIOR", "DIORE")           # curto demais para arriscar
    assert w._distancia("LATAFFA", "LATTAFA") == 2


def test_ranking_com_erro_de_digitacao_vira_sugestao():
    rows = [{"marca": "LATTAFA", "fonte": "ranking", "vendas": 19000000, "mes": "2026-08-01", "fim": None, "vendedores": None, "posicao": 2},
            {"marca": "LATAFFA", "fonte": "ranking", "vendas": 292300, "mes": "2026-05-01", "fim": None, "vendedores": None, "posicao": 81},
            {"marca": "ARMAF", "fonte": "ranking", "vendas": 500000, "mes": "2026-08-01", "fim": None, "vendedores": None, "posicao": 20},
            {"marca": "ARMANI", "fonte": "ranking", "vendas": 400000, "mes": "2026-08-01", "fim": None, "vendedores": None, "posicao": 25}]

    class Repo:
        def _eq(self, v):
            return f"eq.{v}"
        def _todos(self, t, q=None):
            return []
        def _req(self, m, t, q=None, corpo=None, prefer=None):
            return rows if t == "rpc/marcas_resumo" else []
    w.apelidos = lambda repo: {}
    sug, _ = w.sugestoes_apelidos(Repo())
    assert [(x["apelido"], x["marca"]) for x in sug] == [("LATAFFA", "LATTAFA")]


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
