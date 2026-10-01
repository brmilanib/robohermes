# -*- coding: utf-8 -*-
"""01/10 (card #126): busca por foto. A foto de um card DE CATÁLOGO é a do produto (igual para todos os vendedores) e não
vale como prova; e uma loja já ligada com outro seller_id nunca é trocada pelo robô (vira candidata no card).
Rodar: python3 testes/test_busca_foto.py, na pasta nubi."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import meli  # noqa: E402
import nubi_web as w  # noqa: E402
from test_meli import Repo  # noqa: E402


class R(Repo):
    def __init__(self):
        super().__init__()
        self.eventos = []

    def _todos(self, t, q=None):
        return []

    def _req(self, metodo, tabela, q=None, corpo=None, **k):
        if tabela == "tarefa_eventos" and metodo == "POST":
            self.eventos += corpo
            return []
        return super()._req(metodo, tabela, q, corpo, **k)


def _achou(r, **d):
    corpo = {"vendedor": "VANVIC P4", "seller_id": "", "nome": "X", "mlb": "MLB1234567", "fid": "1-MLB1234567", "titulo": "t"} | d
    return w.rota_posicoes(r, "POST", "ml_busca_foto_achou", {}, json.dumps(corpo).encode())


def test_card_de_catalogo_nao_e_prova():
    import coletor as c
    assert c._foto_de_catalogo("849828-MLA93387691711") and not c._foto_de_catalogo("863486-MLB114945658162")
    assert c._card_de_catalogo({"link": "https://www.mercadolivre.com.br/perfume-x/p/MLB12345"})
    assert not c._card_de_catalogo({"link": "https://produto.mercadolivre.com.br/MLB-123456-perfume"})
    assert not c._card_de_catalogo({})


def test_loja_ja_ligada_com_outro_id_nao_e_trocada():
    meli.lojas = lambda ids: {}
    w._hashes_do_nome = lambda repo, nome: []
    r = R()
    meli.gravar_hash_lojas(r, {"VANVIC P4": {"id": "273342367", "nome": "VANVICWEB", "confianca": "provável", "prova": "190 fotos",
                                             "anuncios": [], "votos": 1}}, meli.SEGUIDOS)
    x = _achou(r, seller_id="2281807340", nome="BEAUTYFLOWER")
    assert x["aviso"].startswith("candidata") and x["loja"]["nome"] == "VANVICWEB"
    assert meli.ler_hash_lojas(r, meli.SEGUIDOS)["VANVIC P4"]["id"] == "273342367"
    assert "candidata" in r.eventos[-1]["texto"] and "BEAUTYFLOWER" in r.eventos[-1]["texto"]
    # sem seller_id na página: também não troca
    x = _achou(r, seller_id="", nome="KID'S LIFE")
    assert x["aviso"].startswith("sem seller_id") and meli.ler_hash_lojas(r, meli.SEGUIDOS)["VANVIC P4"]["nome"] == "VANVICWEB"
    # mesmo seller_id: a foto confirma (certa) e soma o anúncio à prova
    x = _achou(r, seller_id="273342367", nome="VANVICWEB", mlb="MLB7777777", fid="9-MLB9", loja_oficial="")
    lj = meli.ler_hash_lojas(r, meli.SEGUIDOS)["VANVIC P4"]
    assert not x["aviso"] and lj["confianca"] == "certa" and lj["votos"] == 2 and lj["prova"].startswith("190 fotos; foto do anúncio MLB7777777")
    assert [a["anuncio"] for a in lj["anuncios"]] == ["MLB7777777"]
    # vendedor sem loja: entra como nova, com a loja oficial anotada na prova
    x = _achou(r, vendedor="MAMS ECOMMERCE TOP14", seller_id="55", nome="MAMS ECOMMERCE", loja_oficial="KID'S LIFE")
    lj = meli.ler_hash_lojas(r, meli.SEGUIDOS)["MAMS ECOMMERCE TOP14"]
    assert lj["id"] == "55" and lj["confianca"] == "certa" and "loja oficial KID'S LIFE" in lj["prova"]
    # foto do catálogo (MLA) reaproveitada: no máximo "provável" e nunca troca uma loja já ligada
    x = _achou(r, vendedor="AUMA PERFUMARIA P2", seller_id="316", nome="EAMCOSMETICOS", fid="849828-MLA93387691711", mlb="MLB7338224356")
    lj = meli.ler_hash_lojas(r, meli.SEGUIDOS)["AUMA PERFUMARIA P2"]
    assert lj["confianca"] == "provável" and "não é prova" in lj["prova"] and not x["aviso"]
    x = _achou(r, seller_id="999", nome="OUTRA", fid="111111-MLA22222222222", mlb="MLB7338224357")        # VANVIC já ligado
    assert x["aviso"].startswith("foto de catálogo") and meli.ler_hash_lojas(r, meli.SEGUIDOS)["VANVIC P4"]["id"] == "273342367"


if __name__ == "__main__":
    for f in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        f()
        print("ok", f.__name__)
