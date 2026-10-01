# -*- coding: utf-8 -*-
"""01/10 (Bruno, Al Wataniah): título cortado em 40 letras não pode virar "Sabah EDT 200 ml"; Sabah Al Ward Sugar é outro
produto. Rodar: python3 testes/test_titulo_cortado.py, na pasta nubi."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import pandas as pd  # noqa: E402
import nubi  # noqa: E402

M = "AL WATANIAH"
LINHAS = [["sabah al ward sugar", "Sabah Al Ward Sugar"], ["ward sugar", "Sabah Al Ward Sugar"], ["sabah al ward", "Sabah Al Ward"],
          ["sabah", "Sabah Al Ward"], ["durrat", "Durrat"]]
ANUNCIOS = [  # (título, gtin, un)
    ("Al Wataniah - Sabah Al Ward Edp 100 Ml - Feminino", "5055810013110", 25000),
    ("Perfume Arabe Feminino Al Wataniah Sabah", "7902287196731", 11300),            # cortado: sem tipo e sem volume
    ("Perfume Arabe Feminino Al Wataniah Sabah", "", 370),
    ("Perfume Árabe Sabah Al Ward Al Wataniah Edt 200ml Aerosol", "", 60),        # o único EDT 200 ml de verdade
    ("Perfume Árabe Sabah Al Ward Sugar Eau De", "7899463112978", 2600),          # Sugar cortado
    ("Al Wataniah Sabah Al Ward Sugar Original Feminino Eau De Parfum 100ml", "5055810099459", 539),
    ("Perfume Sabah Al Ward Sugar Feminino 100", "", 1700),
    ("Al Wataniah Al Wataniah Sabah Al Ward Original Feminino Eau De Parfum 100ml", "", 300),
]


def df():
    return nubi.preparar(pd.DataFrame([{"rid": i, "snapshot_id": 1, "titulo": t, "vendedor": f"V{i}", "vendedor_id": f"{i}" * 64,
                                        "marca_anuncio": M, "categoria": "", "gtin": g, "sku": "", "un": u, "fat": u * 130.0, "preco": 130.0,
                                        "un_hist": u, "fat_hist": 0, "dias_pub": 100, "exposicao": "", "catalogo": 1, "full": 1, "flex": 0,
                                        "internacional": 0, "loja_oficial": 0, "frete_gratis": 1, "bruto": {}}
                                       for i, (t, g, u) in enumerate(ANUNCIOS)]))


def test_cortado_vai_para_o_par_que_mais_vende_e_sugar_separado():
    nubi.definir_gtin_global({})
    nubi.INFO_GTIN.clear()
    # nome da base pública do GTIN principal (UPCitemdb): "For Him / Her" não é variação (virava "Sabah Al Ward Him Her")
    nubi.INFO_GTIN["5055810013110"] = {"nome": "Al Wataniah Sabah Al Ward For Him / Her Edp 100 Ml / 3.4 Fl. Oz 3.4 Fl Oz",
                                       "marca": "Al Wataniah", "fonte": "UPCitemdb"}
    r = nubi.consolidar(df(), M, {M: {"linhas": LINHAS}})
    nubi.INFO_GTIN.clear()
    prod = dict(zip(r["titulo"] + "|" + r["gtin"], r["produto"]))
    assert prod["Perfume Arabe Feminino Al Wataniah Sabah|7902287196731"] == "Al Wataniah Sabah Al Ward EDP 100 ml", prod
    assert prod["Perfume Arabe Feminino Al Wataniah Sabah|"] == "Al Wataniah Sabah Al Ward EDP 100 ml", prod
    assert "200 ml" in prod["Perfume Árabe Sabah Al Ward Al Wataniah Edt 200ml Aerosol|"]
    for k in ("Perfume Árabe Sabah Al Ward Sugar Eau De|7899463112978", "Perfume Sabah Al Ward Sugar Feminino 100|",
              "Al Wataniah Sabah Al Ward Sugar Original Feminino Eau De Parfum 100ml|5055810099459"):
        assert "Sabah Al Ward Sugar" in prod[k], (k, prod[k])
    assert prod["Al Wataniah - Sabah Al Ward Edp 100 Ml - Feminino|5055810013110"] == "Al Wataniah Sabah Al Ward EDP 100 ml"
    assert prod["Al Wataniah Al Wataniah Sabah Al Ward Original Feminino Eau De Parfum 100ml|"] == "Al Wataniah Sabah Al Ward EDP 100 ml"


if __name__ == "__main__":
    test_cortado_vai_para_o_par_que_mais_vende_e_sugar_separado()
    print("ok título cortado")
