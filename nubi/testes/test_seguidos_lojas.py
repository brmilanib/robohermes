# -*- coding: utf-8 -*-
"""Card #126, etapa 1: cada vendedor seguido ligado (meli|seguidos) ganha a cidade/UF do perfil público da loja
(/users/{id}, dublê da API do ML, sem rede) e vira 1 linha em vend_lojas_ml; o painel #/vendedores-ml mostra a cidade.
Sem resposta do ML a cidade fica None (nunca inventada). Rodar: python3 testes/test_seguidos_lojas.py, na pasta nubi."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import meli  # noqa: E402
import nubi_web as w  # noqa: E402
from test_meli import Repo, _preparar  # noqa: E402


class R(Repo):
    def __init__(self, sem_tabela=False):
        super().__init__()
        self.lojas_ml, self.sem_tabela = {}, sem_tabela

    def _req(self, metodo, tabela, q=None, corpo=None, **k):
        if tabela == "vend_lojas_ml" and metodo == "POST":
            if self.sem_tabela:
                raise w.ErroNuvem("relation vend_lojas_ml does not exist", 404)
            assert q == {"on_conflict": "vendedor"} and "merge-duplicates" in k.get("prefer", "")
            for x in corpo:
                self.lojas_ml[x["vendedor"]] = x
            return []
        return super()._req(metodo, tabela, q, corpo, **k)


SEG = {"SIENO P13": {"id": "222222222", "nome": "SIENO.", "link": "https://perfil.mercadolivre.com.br/SIENO.",
                     "confianca": "manual", "prova": "confirmada pelo Bruno", "anuncios": []},
       "ICARBONXX P3": {"id": "2540338692", "nome": "KAIDOXSTOREE", "link": "", "confianca": "provável",
                        "prova": "preço exato em 2 produtos", "anuncios": []},
       "VANVIC P4": {"id": "999", "nome": "VANVICWEB", "link": "https://perfil.mercadolivre.com.br/VANVICWEB",
                     "confianca": "provável", "prova": "x", "anuncios": []},           # o ML não acha: sem cidade
       "PHTEC P7": {"id": "111111111", "nome": "PHTECHSP", "confianca": "dúvida"}}      # dúvida não entra


def test_cidade_e_uf_dos_seguidos_ligados_gravadas():
    d = _preparar()
    r = R()
    meli.gravar_hash_lojas(r, SEG, meli.SEGUIDOS)
    out = w.rota_meli(r, "POST", "meli_seguidos_lojas", {}, b"{}")["lojas"]
    assert {x["vendedor"] for x in out} == {"SIENO P13", "ICARBONXX P3", "VANVIC P4"}
    a, b, c = r.lojas_ml["SIENO P13"], r.lojas_ml["ICARBONXX P3"], r.lojas_ml["VANVIC P4"]
    assert (a["seller_id"], a["cidade"], a["uf"], a["nickname"], a["nome"]) == ("222222222", "Maringá", "PR", "ESSENCEPRIMEBR", "SIENO.")
    assert a["confianca"] == "manual" and a["prova"] == "confirmada pelo Bruno" and a["link"].startswith("https://perfil.")
    assert (b["cidade"], b["uf"], b["link"]) == ("São Paulo", "SP", "https://perfil.mercadolivre.com.br/KAIDOXSTOREE")
    assert (c["cidade"], c["uf"], c["nickname"], c["link"]) == (None, None, "VANVICWEB", "https://perfil.mercadolivre.com.br/VANVICWEB")
    assert "PHTEC P7" not in r.lojas_ml
    assert d.pedidos.count("/users/222222222") == 1
    w.rota_meli(r, "POST", "meli_seguidos_lojas", {}, b"{}")                        # de novo: 1 linha por vendedor (upsert)
    assert len(r.lojas_ml) == 3 and d.pedidos.count("/users/222222222") == 1         # perfil em cache (7 dias)


def test_sem_a_tabela_ou_sem_as_chaves_nao_quebra():
    _preparar()
    r = R(sem_tabela=True)                                     # o Chefe ainda não aplicou o SQL
    meli.gravar_hash_lojas(r, SEG, meli.SEGUIDOS)
    out = {x["vendedor"]: x for x in w.lojas_seguidos(r).values()}
    assert out["SIENO P13"]["cidade"] == "Maringá"
    _preparar(chaves=False)                                    # sem ML_CLIENT_ID/SECRET: loja fica, cidade None
    r = R()
    meli.gravar_hash_lojas(r, SEG, meli.SEGUIDOS)
    out = w.lojas_seguidos(r)
    assert out["SIENO P13"]["cidade"] is None and out["SIENO P13"]["nickname"] == "SIENO."


def test_painel_mostra_a_cidade_e_a_tela_desenha():
    _preparar()

    class P(R):
        def _todos(self, t, q=None):
            if t == "vend_relatorios":
                return [{"id": 9, "vendedor": "SIENO P13", "mes": "2026-09-01", "ate": None, "arquivo": "a", "importado_em": "x",
                         "seller_hash": "A" * 128, "nome_exibido": "SIENO P13"}]
            return []
    r = P()
    meli.gravar_hash_lojas(r, SEG, meli.SEGUIDOS)
    xs = w.rota_meli(r, "GET", "meli_seguidos_lista", {}, b"")["vendedores"]
    assert (xs[0]["ml"]["cidade"], xs[0]["ml"]["uf"]) == ("Maringá", "PR")
    assert "SIENO P13" in r.lojas_ml                         # abrir o painel já grava vend_lojas_ml
    html = (Path(__file__).resolve().parents[1] / "public" / "index.html").read_text(encoding="utf-8")
    assert "📍 ${esc(v.ml.cidade)}" in html and "cidade: l.cidade, uf: l.uf" in html
    sql = (Path(__file__).resolve().parents[1] / "supabase" / "vend_lojas_ml.sql").read_text(encoding="utf-8")
    for col in ("vendedor text primary key", "seller_id", "nickname", "nome", "cidade", "uf", "link", "confianca", "prova", "atualizado_em"):
        assert col in sql, col


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
