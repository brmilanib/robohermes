# -*- coding: utf-8 -*-
"""Ficha fixa da linha (01/10, Bruno: "Sabah Al Ward só existe EDP 100 ml; confirme pela API do ML antes de juntar").
Rodar: python3 testes/test_ficha_linha.py, na pasta nubi."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import meli  # noqa: E402
import nubi  # noqa: E402
import test_titulo_cortado as tc  # noqa: E402


def test_atributos_do_ml():
    attrs = [{"id": "BRAND", "name": "Marca", "value_name": "Al wataniah"}, {"id": "UNIT_VOLUME", "name": "Volume da unidade", "value_name": "100 mL"},
             {"id": "FRAGRANCE_TYPE", "name": "Tipo", "value_name": "Eau de parfum"}]
    assert meli.ficha_dos_atributos(attrs) == {"tipo": "EDP", "volume": "100 ml"}
    assert meli.ficha_dos_atributos([{"name": "Volume", "value_name": "0,2 L"}, {"name": "Tipo", "value_name": "Eau de toilette"}]) == {"tipo": "EDT", "volume": "200 ml"}
    assert meli.ficha_dos_atributos([]) == {"tipo": None, "volume": None}


def test_ficha_corrige_erro_de_digitacao_sem_tocar_body_splash_e_decant():
    nubi.definir_gtin_global({}); nubi.INFO_GTIN.clear()
    df = tc.df()
    extra = nubi.preparar(__import__("pandas").DataFrame([
        {**tc.df().iloc[0].to_dict(), "rid": 90, "titulo": "Body Splash Al Wataniah Sabah Al Ward 250ml", "gtin": "", "un": 50},
        {**tc.df().iloc[0].to_dict(), "rid": 91, "titulo": "Decant Sabah Al Ward Al Wataniah 10ml", "gtin": "", "un": 10}]))
    df = __import__("pandas").concat([df, extra], ignore_index=True)
    nubi.definir_fichas({"AL WATANIAH": {"Sabah Al Ward": {"tipo": "EDP", "volume": "100 ml"}, "Sabah Al Ward Sugar": {"tipo": "EDP", "volume": "100 ml"}}})
    try:
        r = nubi.consolidar(df, tc.M, {tc.M: {"linhas": tc.LINHAS}})
    finally:
        nubi.definir_fichas({})
    prod = dict(zip(r["titulo"], r["produto"]))
    assert prod["Perfume Árabe Sabah Al Ward Al Wataniah Edt 200ml Aerosol"] == "Al Wataniah Sabah Al Ward EDP 100 ml", prod   # erro de digitação
    assert prod["Body Splash Al Wataniah Sabah Al Ward 250ml"].endswith("Body Splash 250 ml")
    assert "Decant" in prod["Decant Sabah Al Ward Al Wataniah 10ml"]
    assert set(p for t, p in prod.items() if "Sugar" in t) == {"Al Wataniah Sabah Al Ward Sugar EDP 100 ml"}


if __name__ == "__main__":
    test_atributos_do_ml()
    test_ficha_corrige_erro_de_digitacao_sem_tocar_body_splash_e_decant()
    print("ok ficha da linha")
