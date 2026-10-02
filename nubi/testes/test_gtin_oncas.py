# -*- coding: utf-8 -*-
"""02/10 (Bruno, Armaf setembro): o anúncio da MNZIMPORTS (título cortado, GTIN 6085010094144, 9,1 mil un.) virava
"Club de Nuit Intense Man EDT 100 ml" porque o nome pesquisado na UPCitemdb diz "3.4 oz./100ml" (conversão de onças).
Tem que ficar no "EDT 105 ml" com o resto do mercado. Rodar: python3 testes/test_gtin_oncas.py, na pasta nubi."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import pandas as pd  # noqa: E402
import nubi  # noqa: E402

M = "ARMAF"
LINHAS = [["club de nuit intense", "Club de Nuit Intense Man"], ["club de nuit", "Club de Nuit"]]
ANUNCIOS = [  # (título, gtin, un)
    ("Perfume Club De Nuit Intense Da Armaf Ed", "6085010044712", 9300),            # MAMS, cortado
    ("Perfume Club De Nuit Intense Da Armaf Ed", "6085010094144", 9100),            # MNZ, cortado, GTIN pesquisado "100ml"
    ("Perfume Club De Nuit Intense Edt 105ml", "6085010044712", 550),
    ("Perfume Club De Nuit Intense Armaf Edt 105ml Masculino", "", 1000),
    ("Perfume Armaf Club De Nuit Intense Man Edt 105ml", "6085010044712", 500),
]


def df():
    return nubi.preparar(pd.DataFrame([{"rid": i, "snapshot_id": 1, "titulo": t, "vendedor": f"V{i}", "vendedor_id": f"{i}" * 64,
                                        "marca_anuncio": M, "categoria": "", "gtin": g, "sku": "", "un": u, "fat": u * 240.0, "preco": 240.0,
                                        "un_hist": u, "fat_hist": 0, "dias_pub": 100, "exposicao": "", "catalogo": 1, "full": 1, "flex": 0,
                                        "internacional": 0, "loja_oficial": 0, "frete_gratis": 1, "bruto": {}}
                                       for i, (t, g, u) in enumerate(ANUNCIOS)]))


def test_volume_em_oncas_do_gtin_pesquisado_nao_parte_o_produto():
    nubi.definir_gtin_global({})
    nubi.INFO_GTIN.clear()
    nubi.INFO_GTIN["6085010094144"] = {"nome": "Club De Nuit by Armaf, 3.6 oz EDT Spray for Men 3.4 oz./100ml",
                                       "marca": "Armaf", "fonte": "UPCitemdb"}
    nubi.INFO_GTIN["6085010044712"] = {"nome": "Armaf | Club De Nuit Intense Man EDT | 105 ml", "marca": "Armaf",
                                       "fonte": "Open Beauty Facts"}
    r = nubi.consolidar(df(), M, {M: {"linhas": LINHAS}})
    nubi.INFO_GTIN.clear()
    prods = set(r["produto"])
    assert len(prods) == 1, prods
    assert "105 ml" in prods.pop()


def test_volume_bem_diferente_continua_separado():
    nubi.definir_gtin_global({})
    nubi.INFO_GTIN.clear()
    nubi.INFO_GTIN["6085010094144"] = {"nome": "Armaf Club De Nuit Intense Man EDT 200ml", "marca": "Armaf", "fonte": "x"}
    r = nubi.consolidar(df(), M, {M: {"linhas": LINHAS}})
    nubi.INFO_GTIN.clear()
    assert any("200 ml" in p for p in r["produto"]), set(r["produto"])



def test_familia_club_de_nuit_perde_para_o_modelo():
    # 02/10 (Bruno): Overdose, Lionheart e Private Key são outros perfumes, não o Club de Nuit Intense Man
    linhas = [["club de nuit intense man", "Club de Nuit Intense Man"], ["club de nuit intense woman", "Club de Nuit Intense Woman"],
              ["club de nuit sillage", "Club de Nuit Sillage"], ["club de nuit intense", "Club de Nuit Intense Man"],
              ["club de nuit", "Club de Nuit Intense Man"], ["private key to my dreams", "Private Key To My Dreams"],
              ["lionheart", "Club de Nuit Lionheart"]]
    pm = nubi.palavras_da_marca("ARMAF")
    ach = lambda t: nubi.achar_linha(nubi.normalizar(t), linhas, pm)
    assert ach("Extrato De Perfume Em Spray Armaf Club De Nuit Private Key To My Dreams 100ml") == "Private Key To My Dreams"
    assert ach("Club De Nuit Lionheart Armaf Man 100 Ml") == "Club de Nuit Lionheart"
    assert ach("Perfume Club De Nuit Intense Da Armaf Ed") == "Club de Nuit Intense Man"
    assert ach("Perfume Armaf Club De Nuit Sillage 105ml") == "Club de Nuit Sillage"


if __name__ == "__main__":
    test_volume_em_oncas_do_gtin_pesquisado_nao_parte_o_produto()
    test_volume_bem_diferente_continua_separado()
    test_familia_club_de_nuit_perde_para_o_modelo()
    print("ok volume em onças")
