# -*- coding: utf-8 -*-
"""01/10 (print do Bruno, Revlon: 29 GTINs de escovas viraram "Revlon Escova Secadora EDT"): fora de perfumaria o produto é
o GTIN (nome do título + modelo), e perfumaria é pela categoria FINAL (escova em "Beleza e Cuidado Pessoal" não é perfume;
"Mais Categorias > Perfumes" é). Rodar: python3 testes/test_fora_perfume.py, na pasta nubi."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import pandas as pd  # noqa: E402
import nubi  # noqa: E402


def _df(linhas):
    out = []
    for t, g, u, cat, modelo in linhas:
        out.append({"titulo": t, "gtin": g, "un": u, "fat": u * 300.0, "categoria": cat, "marca_anuncio": "REVLON", "sku": "",
                    "vendedor": "v", "vendedor_id": "v", "preco": 300.0,
                    "bruto": {"Categoria final": cat or "Perfumes", "Categoria L1": "Beleza e Cuidado Pessoal", "Modelo": modelo}})
    return pd.DataFrame(out)


def test_perfumaria_e_pela_categoria_final():
    assert not nubi.eh_perfumaria("Beleza e Cuidado Pessoal", "Escovas Elétricas")
    assert nubi.eh_perfumaria("Beleza e Cuidado Pessoal", "Perfumes")
    assert nubi.eh_perfumaria("Mais Categorias", "Perfumes") and nubi.eh_perfumaria("Mais Categorias", "Fragrâncias")
    assert nubi.eh_perfumaria("Beleza e Cuidado Pessoal", "Cuidado do Corpo")       # body splash
    assert nubi.eh_perfumaria("Beleza e Cuidado Pessoal", "")                       # arquivo velho, só L1
    assert not nubi.eh_perfumaria("Eletrodomésticos", "Secadores de Cabelo")


def test_fora_de_perfume_o_produto_e_o_gtin():
    df = _df([
        ("Escova Secadora Modeladora Revlon Root Booster Rvdr5292 Original", "0761318552925", 730, "Escovas Elétricas", "RVDR5292"),
        ("Escova Secadora Revlon Root Booster Rvdr5292 110v", "0761318552925", 50, "Escovas Elétricas", "RVDR5292"),   # mesmo GTIN
        ("Escova Secadora Alisadora Revlon Root Booster Preto", "0761318452928", 370, "Escovas Elétricas", "RVDR5292"),  # outro GTIN
        ("Escova Secadora Modeladora Revlon Titanium Max Edition", "761318528241", 320, "Escovas Elétricas", "ONESTEP"),
        ("Secador De Cabelo Revlon Turbo 2000w", "", 40, "Secadores de Cabelo", ""),                                     # sem GTIN
        ("Perfume Revlon Charlie Blue Eau De Toilette 100ml", "0309970021010", 60, "", ""),                               # perfume
    ])
    out = nubi.consolidar(df, "REVLON", {}, info={})
    out = nubi.campos_do_arquivo(out, "REVLON")
    prods = list(out["produto"])
    assert out.at[0, "tipo"] == nubi.TIPO_FORA and "EDT" not in prods[0] and "(não perfume)" not in prods[0], prods
    assert prods[0] == prods[1], prods                                   # mesmo GTIN = mesmo produto (nome do que mais vende)
    assert prods[2] != prods[0] and prods[3] != prods[0] and prods[3] != prods[2], prods   # GTINs diferentes = produtos diferentes
    assert "Rvdr5292" in prods[0] and "Titanium Max" in prods[3], prods
    assert prods[4].startswith("Revlon Secador") and out.at[4, "cat"] == "Secadores de Cabelo", (prods[4], out.at[4, "cat"])
    assert out.at[0, "cat"] == "Escovas Elétricas"
    assert out.at[5, "tipo"] == "EDT" and out.at[5, "produto"] == "Revlon Charlie Blue EDT 100 ml", out.at[5, "produto"]
    # mesmo nome em 2 GTINs (cores): o GTIN entra no nome
    df2 = _df([("Escova Revlon One-step Rosa", "0761318552925", 10, "Escovas Elétricas", ""),
               ("Escova Revlon One-step Preta", "0761318452928", 8, "Escovas Elétricas", "")])
    o2 = nubi.consolidar(df2, "REVLON", {}, info={})
    p2 = list(o2["produto"])
    assert p2[0] != p2[1] and (("GTIN" in p2[0] and "GTIN" in p2[1]) or "Rosa" in p2[0]), p2


if __name__ == "__main__":
    test_perfumaria_e_pela_categoria_final()
    test_fora_de_perfume_o_produto_e_o_gtin()
    print("ok fora de perfume")
