# -*- coding: utf-8 -*-
"""👀 Vendedores observados (01/10, Bruno): todo vendedor dos exports do Explorador ganha cadastro (hash = chave), página com
os produtos e ⭐ interessante. Rodar: python3 testes/test_observados.py, na pasta nubi."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import observados  # noqa: E402
import nubi_web as w  # noqa: E402

H1, H2, H3 = "a" * 64, "b" * 64, "c" * 64


class Repo:
    def __init__(self):
        self.resumos = {}

    def _eq(self, v):
        return f"eq.{v}"

    def _req(self, metodo, tabela, q=None, corpo=None, **k):
        if tabela == "rpc/nubi_observados":
            return [{"vendedor_id": H1, "nomes": ["VACA.SALMAO.GANDULENTO", "VACA.SALMAO.X"], "marcas": 2, "anuncios": 5, "un": 3000, "fat": 1.1e6,
                     "gtins": 3, "pct_full": 0.8, "pct_catalogo": 0.6, "loja_oficial": 0, "primeiro": "2026-08-01", "ultimo": "2026-09-29"},
                    {"vendedor_id": H2, "nomes": ["MERCADO LIVRE"], "marcas": 33, "anuncios": 308, "un": 178488, "fat": 5e7, "gtins": 200,
                     "pct_full": 1, "pct_catalogo": 0.9, "loja_oficial": 1, "primeiro": "2026-08-01", "ultimo": "2026-09-29"},
                    {"vendedor_id": H3, "nomes": ["SIENO P13"], "marcas": 5, "anuncios": 50, "un": 900, "fat": 2e5, "gtins": 40,
                     "pct_full": 0.5, "pct_catalogo": 0.5, "loja_oficial": 0, "primeiro": "2026-08-01", "ultimo": "2026-09-29"}]
        if tabela == "rpc/nubi_observado_produtos":
            assert corpo == {"h": H1}
            return [{"produto": "Mq Chapinha Pro 480 · GTIN 1", "marca": "MQ", "categoria": "Chapinhas", "gtin": "1", "titulo": "Chapinha Profissional Mq Pro 480",
                     "anuncios": 2, "un": 3000, "fat": 1.1e6, "preco": 365.66, "pct_full": 1, "catalogo": 1, "dias_pub": 1097, "un_hist": 23800, "share": 0.4}]
        if tabela == "rpc/nubi_observado_periodos":
            return [{"marca": "MQ", "inicio": "2026-08-01", "fim": "2026-09-29", "dias": 60, "anuncios": 2, "un": 3000, "fat": 1.1e6}]
        if tabela == "anuncios":
            return [{"vendedor": "VACA.SALMAO.GANDULENTO"}, {"vendedor": "VACA.SALMAO.X"}]
        if tabela == "ia_resumos" and metodo == "GET":
            c = (q or {}).get("chave", "")[3:]
            return [{"texto": self.resumos[c]}] if c in self.resumos else []
        if tabela == "ia_resumos" and metodo == "POST":
            for r in corpo:
                self.resumos[r["chave"]] = r["texto"]
        return []


def test_lista_situacao_loja_e_estrela():
    r = Repo()
    lojas = {H3: {"id": "1142362911", "nome": "SIENO.", "link": "x", "confianca": "manual", "cidade": "São Paulo", "uf": "SP"}}
    L = observados.lista(r, {H3}, lojas)
    por = {x["vendedor_id"]: x for x in L["itens"]}
    assert por[H1]["situacao"] == "observado" and por[H1]["nome"] == "VACA.SALMAO.GANDULENTO" and por[H1]["nomes"] == ["VACA.SALMAO.GANDULENTO", "VACA.SALMAO.X"]
    assert por[H2]["situacao"] == "plataforma"                              # a loja do próprio ML: vendedor normal, marcado
    assert por[H3]["situacao"] == "seguido" and por[H3]["loja"]["nome"] == "SIENO." and por[H3]["loja"]["cidade"] == "São Paulo"
    assert L["total"] == {"vendedores": 3, "observados": 1, "seguidos": 1, "com_loja": 1, "interessantes": 0, "un": 182388}
    observados.marcar_interesse(r, H1, True, "chapinha MQ campeã")
    assert observados.lista(r, {H3}, lojas)["total"]["interessantes"] == 1
    assert json.loads(r.resumos[observados.INTERESSE])[H1]["nota"] == "chapinha MQ campeã"
    observados.marcar_interesse(r, H1, False)
    assert observados.interesses(r) == {}
    try:
        observados.marcar_interesse(r, "x", True)
        raise AssertionError("hash inválido devia falhar")
    except ValueError:
        pass


def test_detalhe_com_produtos_media_e_periodos():
    r = Repo()
    d = observados.detalhe(r, H1, set(), {})
    assert d["nome"] == "VACA.SALMAO.GANDULENTO" and d["situacao"] == "observado" and d["loja"] is None
    p = d["produtos"][0]
    assert p["share"] == 0.4 and p["media_dia_hist"] == round(23800 / 1097, 3) and p["categoria"] == "Chapinhas" and p["catalogo"] is True
    assert d["total"]["produtos"] == 1 and d["total"]["un"] == 3000 and d["total"]["media_dia_hist"] == round(23800 / 1097, 2)
    assert d["marcas"] == [{"marca": "MQ", "produtos": 1, "un": 3000, "fat": 1.1e6}]
    assert d["periodos"][0]["dias"] == 60
    # rota
    w._hashes_seguidos = lambda repo: set()
    w._lojas_ml_do = lambda repo, hs: {}
    assert w.rota_observados(r, "GET", "observado", {"vendedor_id": H1}, b"")["nome"] == "VACA.SALMAO.GANDULENTO"
    try:
        w.rota_observados(r, "GET", "observado", {"vendedor_id": "zz"}, b"")
        raise AssertionError("devia recusar")
    except w.ErroNuvem:
        pass


if __name__ == "__main__":
    test_lista_situacao_loja_e_estrela()
    test_detalhe_com_produtos_media_e_periodos()
    print("ok observados")
