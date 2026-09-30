"""30/09 (6+ casos do Bruno na semana): o anúncio diz a marca (coluna Marca, título e SKU), mas a pesquisa do GTIN numa
base pública devolveu outro produto ("Boho Gray Leaves Floral Switch Cover", marca JXUMSYJN) e o Maktub La Vie da Bidaya
virou "Outra marca: Jxumsyjn". O que o anúncio diz manda; a base que não parece perfume é ignorada e a IA pesquisa."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import pandas as pd  # noqa: E402
import nubi  # noqa: E402

LIXO = {"634240397363": {"nome": "Boho Gray Leaves Floral Switch Cover 2 Gang Double Rocker Wall Plate", "marca": "JXUMSYJN",
                         "fonte": "UPCitemdb"}}


def _df(linhas, marca_col=None):
    return pd.DataFrame([{"titulo": t, "gtin": g, "un": u, "fat": u * 200.0, "categoria": "", "marca_anuncio": m,
                          "sku": s, "vendedor": "v", "vendedor_id": "v", "preco": 200.0} for t, g, u, m, s in linhas])


def test_pesquisa_do_gtin_nao_vence_o_anuncio():
    df = _df([
        ("Perfume Árabe Maktub La Vie Bidaya Eau De Parfum 100ml Unisex", "634240397363", 1100, "BIDAYA", "BIDAYAMAKTUBLAVIE"),
        ("Perfume Árabe Maktub La Vie Bidaya 100ml", "634240397363", 60, "BIDAYA", "BIDAYAMAKTUBLAVIE"),
        ("Maktub La Vie Bidaya Eau De Parfum 100ml", "634240397363", 5, "BIDAYA", "MAKTBULAVIE"),
        ("Bidaya Gris Perfume Árabe Unissex Eau De Parfum 100ml", "6294015153057", 300, "BIDAYA", "GRIS"),
    ])
    out = nubi.consolidar(df, "BIDAYA", {}, info=dict(LIXO))
    assert not (out["tipo"] == nubi.TIPO_OUTRA).any(), list(out["produto"])
    assert out.at[0, "produto"].startswith("Bidaya Maktub") and out.at[0, "produto"].endswith("EDP 100 ml"), out.at[0, "produto"]
    assert out.at[0, "produto"] == out.at[1, "produto"] == out.at[2, "produto"]
    assert "Boho" not in " ".join(out["produto"]) and "Gray" not in " ".join(out["linha"])
    print("ok test_pesquisa_do_gtin_nao_vence_o_anuncio")


def test_titulo_ou_sku_com_a_marca_vale_mesmo_com_coluna_marca_errada():
    df = _df([
        ("Perfume Lattafa Asad Zanzibar Limited 100ml", "6290360591254", 520, "PERFUMES ÁRABES", ""),
        ("Perfume Árabe Fakhar Rose Lattafa Feminino 100ml", "6291108735640", 90, "FINKÈ", ""),
        ("Perfume Árabe Yara 100ml Edp", "6291108738870", 30, "LOJA DO ZÉ", "LATTAFA-YARA-100"),
        ("Lattafa Asad Eau De Parfum 100ml", "6290360591230", 800, "LATTAFA", "ASAD"),
        # contratipo: cita a Lattafa, mas cita também a marca declarada -> continua outra marca
        ("Perfume New Brand Prestige Delightful ( Lattafa Yara ) 100ml", "7898999000001", 40, "NEW BRAND", ""),
        # outra marca de verdade, sem citar a Lattafa
        ("Perfume Armaf Club De Nuit Intense 105ml", "6085010041544", 200, "ARMAF", ""),
    ])
    out = nubi.consolidar(df, "LATTAFA", {}, info={})
    outra = out[out["tipo"] == nubi.TIPO_OUTRA]
    assert sorted(outra["linha"]) == ["Armaf"], list(zip(out["titulo"], out["produto"]))
    assert out.at[4, "tipo"] == nubi.TIPO_CONTRATIPO, out.at[4, "produto"]     # 30/09: contratipo = Low price
    assert out.at[0, "produto"].startswith("Lattafa Asad Zanzibar"), out.at[0, "produto"]
    assert out.at[1, "produto"].startswith("Lattafa Fakhar Rose"), out.at[1, "produto"]
    assert out.at[2, "produto"].startswith("Lattafa Yara"), out.at[2, "produto"]
    print("ok test_titulo_ou_sku_com_a_marca_vale_mesmo_com_coluna_marca_errada")


def test_pesquisa_certa_continua_valendo():
    # GTIN pesquisado diz outra marca e NENHUM anúncio cita a marca do export: continua outra marca (regra antiga)
    df = _df([("Perfume Importado Masculino 100ml Original", "3386460114424", 50, "", "")])
    info = {"3386460114424": {"nome": "Azzaro Wanted Eau de Toilette 100 ml", "marca": "Azzaro", "fonte": "teste"}}
    out = nubi.consolidar(df, "MONTBLANC", {}, info=info)
    assert out.at[0, "produto"] == "Outra marca: Azzaro", out.at[0, "produto"]
    print("ok test_pesquisa_certa_continua_valendo")


def test_base_que_nao_parece_perfume_e_ignorada_e_a_ia_pesquisa():
    assert not nubi.parece_perfume("Boho Gray Leaves Floral Switch Cover 2 Gang Double Rocker Wall Plate")
    assert nubi.parece_perfume("Bidaya Maktub La Vie Eau de Parfum 100 ml")
    assert nubi.parece_perfume("Batiste Original 120 g dry shampoo hair")
    chamadas = []
    orig = (nubi.fonte_open_beauty, nubi.fonte_upcitemdb, nubi.fonte_ia)
    nubi.fonte_open_beauty = lambda g: None
    nubi.fonte_upcitemdb = lambda g: {"nome": "Boho Gray Leaves Floral Switch Cover", "marca": "JXUMSYJN"}
    nubi.fonte_ia = lambda g: chamadas.append(g) or {"nome": "Bidaya Maktub La Vie Eau de Parfum 100 ml", "marca": "Bidaya"}
    import ia
    disp = ia.disponivel
    ia.disponivel = lambda: True
    try:
        r, falhas, n = nubi.consultar_gtin("634240397363")
    finally:
        nubi.fonte_open_beauty, nubi.fonte_upcitemdb, nubi.fonte_ia = orig
        ia.disponivel = disp
    assert chamadas == ["634240397363"] and r["marca"] == "Bidaya" and r["fonte"] == ia.nome(), (r, falhas)
    print("ok test_base_que_nao_parece_perfume_e_ignorada_e_a_ia_pesquisa")


if __name__ == "__main__":
    test_pesquisa_do_gtin_nao_vence_o_anuncio()
    test_titulo_ou_sku_com_a_marca_vale_mesmo_com_coluna_marca_errada()
    test_pesquisa_certa_continua_valendo()
    test_base_que_nao_parece_perfume_e_ignorada_e_a_ia_pesquisa()
