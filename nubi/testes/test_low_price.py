"""30/09 (Bruno): "contratipo tem que entrar na categoria low price, e decant também, tudo que é decant, 10ml, poucos ml"."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import pandas as pd  # noqa: E402
import nubi  # noqa: E402


def _df(linhas):
    return pd.DataFrame([{"titulo": t, "gtin": g, "un": u, "fat": u * 100.0, "categoria": "", "marca_anuncio": m,
                          "sku": "", "vendedor": "v", "vendedor_id": "v", "preco": 100.0, "bruto": {"Categoria final": "Perfumes"}}
                         for t, g, u, m in linhas])


def test_decant_e_contratipo_viram_low_price():
    df = _df([
        ("Lattafa Asad Eau De Parfum 100ml", "6290360591230", 800, "LATTAFA"),
        ("Decant Lattafa Asad 10ml Eau De Parfum", "", 120, "LATTAFA"),
        ("Lattafa Asad 5ml Amostra", "6290360591230", 30, "LATTAFA"),           # mesmo GTIN do 100 ml: não vota nele
        ("Perfume Lattafa Yara 8 Ml", "", 15, "LATTAFA"),                          # poucos ml, sem a palavra decant
        ("Perfume Contratipo Lattafa Asad 100ml", "", 60, "LATTAFA"),
        ("Perfume New Brand Prestige ( Lattafa Yara ) 100ml", "7898999000001", 40, "NEW BRAND"),   # contratipo de outra marca
        ("Perfume J. Serrano inspirado 100ml", "", 20, "J. SERRANO"),
        ("Perfume Armaf Club De Nuit 105ml", "6085010041544", 200, "ARMAF"),      # outra marca de verdade
        ("Lattafa Yara Eau De Parfum 100ml", "6291108738870", 500, "LATTAFA"),
    ])
    out = nubi.consolidar(df, "LATTAFA", {}, info={})
    out = nubi.campos_do_arquivo(out, "LATTAFA")
    tipos = list(out["tipo"])
    assert tipos[0] == "EDP" and out.at[0, "volume"] == "100 ml" and out.at[0, "produto"] == "Lattafa Asad EDP 100 ml", out.iloc[0].to_dict()
    assert tipos[1] == tipos[2] == tipos[3] == nubi.TIPO_DECANT, tipos
    assert tipos[4] == tipos[5] == tipos[6] == nubi.TIPO_CONTRATIPO, tipos
    assert tipos[7] == nubi.TIPO_OUTRA and out.at[7, "produto"] == "Outra marca: Armaf", out.at[7, "produto"]
    assert out.at[1, "produto"] == "Lattafa Asad Decant 10 ml", out.at[1, "produto"]
    assert out.at[2, "produto"] == "Lattafa Asad Decant 5 ml", out.at[2, "produto"]
    assert out.at[3, "produto"] == "Lattafa Yara Decant 8 ml", out.at[3, "produto"]
    assert out.at[4, "produto"] == "Lattafa Asad Contratipo 100 ml", out.at[4, "produto"]
    assert out.at[5, "produto"] == "Lattafa Yara Contratipo 100 ml", out.at[5, "produto"]
    assert out.at[6, "produto"].startswith("Lattafa J. Serrano Contratipo") or out.at[6, "produto"].startswith("Lattafa J. serrano Contratipo"), out.at[6, "produto"]
    assert all(out.loc[out["tipo"].isin(nubi.TIPOS_LOW), "cat"] == nubi.CAT_LOW), list(out["cat"])
    assert all(out.loc[out["tipo"].isin(nubi.TIPOS_LOW), "confianca"] == nubi.CONF_LOW)
    assert out.at[0, "cat"] == "Perfumes" and out.at[8, "cat"] == "Perfumes"
    print("ok test_decant_e_contratipo_viram_low_price")


def test_volume_pequeno_e_lido():
    assert nubi.achar_volume("lattafa asad 5ml") == "5 ml" and nubi.achar_volume("asad 100 ml") == "100 ml"
    assert nubi.tipo_low_price("perfume x 30ml", "30 ml") == "" and nubi.tipo_low_price("perfume x", "15 ml") == nubi.TIPO_DECANT
    assert nubi.tipo_low_price("perfume x mini 100ml", "100 ml") == nubi.TIPO_DECANT
    assert nubi.tipo_low_price("perfume x", "100 ml", True, True) == nubi.TIPO_CONTRATIPO
    assert nubi.tipo_low_price("perfume x", "100 ml", True, False) == ""
    print("ok test_volume_pequeno_e_lido")


if __name__ == "__main__":
    test_decant_e_contratipo_viram_low_price()
    test_volume_pequeno_e_lido()
