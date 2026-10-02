# -*- coding: utf-8 -*-
"""02/10: teste da API do ML para uma marca (meli.testar_marca) com um dublê da API. Rodar na pasta nubi."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("ML_CLIENT_ID", "x")
os.environ.setdefault("ML_CLIENT_SECRET", "y")
import meli  # noqa: E402


def falso(caminho, params=None, timeout=20):
    if caminho.startswith("/sites/MLB/search"):
        raise meli.Bloqueado("o Mercado Livre respondeu 403 em /sites/MLB/search (forbidden)")
    if caminho == "/products/search":
        return {"paging": {"total": 2}, "results": [
            {"id": "MLB1", "name": "Armaf Club De Nuit Intense Man EDT 105 ml", "attributes": [{"id": "BRAND", "value_name": "Armaf"}]},
            {"id": "MLB2", "name": "Outro", "attributes": [{"id": "BRAND", "value_name": "Lattafa"}]}]}
    if caminho.startswith("/products/MLB1/items"):
        return {"paging": {"total": 2}, "results": [{"item_id": "MLB10", "seller_id": 5, "price": 240},
                                                    {"item_id": "MLB11", "seller_id": 6, "price": 250}]}
    if caminho.startswith("/items"):
        raise meli.Bloqueado("o Mercado Livre respondeu 403 em /items")
    if caminho.startswith("/users/"):
        return {"nickname": "LOJA", "seller_reputation": {"transactions": {"total": 100}}}
    if caminho.startswith("/highlights"):
        return {"content": [{"id": "MLB1", "type": "PRODUCT"}]}
    if caminho == "/products/MLB1":
        return {"id": "MLB1", "name": "x", "buy_box_winner": {"item_id": "MLB10"}}
    return {}


def test_testar_marca():
    meli._get = falso
    meli._token = lambda forcar=False: "t"
    meli.visitas = lambda ids, dias=30: {i: 7 for i in ids}
    r = meli.testar_marca("armaf")
    a = r["achado"]
    assert a["produtos_da_marca"] == 1 and a["ofertas"] == 2 and a["vendedores"] == 2 and a["ofertas_com_vendidos"] == 0, a
    nomes = {p["passo"]: p["ok"] for p in r["passos"]}
    assert nomes["busca de anúncios por palavra (/sites/MLB/search?q=)"] is False
    assert nomes["anúncios de cada produto (/products/ID/items)"] is True
    assert "token" not in str(r).lower().replace("token em uso", "")


if __name__ == "__main__":
    test_testar_marca()
    print("ok teste da marca")
