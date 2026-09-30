# -*- coding: utf-8 -*-
"""Card #128 (desafio #126): casar_anuncio_nubimetrics liga o anúncio real do ML à linha de vend_anuncios só por regras:
manual intocável, GTIN antes do título, título forte/fraco com as travas de volume, kit, concentração, gênero e marca.
Rodar: python3 testes/test_seguidos_casamento.py, na pasta nubi."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import categorias as c  # noqa: E402

CONHECIDAS = {"LATTAFA": "LATTAFA", "ARMAF": "ARMAF", "AFNAN": "AFNAN"}


def ml(titulo, gtin="", full=False, tipo="Clássico"):
    return {"titulo": titulo, "gtin": gtin, "full": full, "tipo": tipo}


def nubi(id, titulo, gtin="", marca="LATTAFA", full=False, tipo="Clássico", unidades=0):
    return {"id": id, "titulo": titulo, "gtin": gtin, "marca_chave": marca, "fulfillment": full, "tipo_pub": tipo,
            "unidades": unidades}


def casar(anuncio, linhas, ligacao=None):
    r = c.casar_anuncio_nubimetrics(anuncio, linhas, CONHECIDAS, ligacao)
    return (r["linha"] or {}).get("id"), r["metodo"], r["a_conferir"]


def test_01_gtin_igual_liga_mesmo_com_titulo_diferente():
    ls = [nubi(1, "Perfume Asad Lattafa 100ml", "6291108735411"), nubi(2, "Yara Lattafa Edp 100ml", "6291108730515")]
    assert casar(ml("Asad Masculino Eau De Parfum 100 Ml", "6291108735411"), ls) == (1, "gtin", False)


def test_02_gtin_com_zero_na_frente_e_colado_do_nubimetrics():
    ls = [nubi(1, "Asad Lattafa 100ml", "62911087354116291108730515")]      # 2 GTINs colados (13+13)
    assert casar(ml("Asad Lattafa 100ml", "06291108735411"), ls) == (1, "gtin", False)


def test_03_mesmo_gtin_full_e_nao_full_fica_o_do_mesmo_full():
    ls = [nubi(1, "Asad Lattafa 100ml", "6291108735411", full=False, unidades=90),
          nubi(2, "Asad Lattafa 100ml", "6291108735411", full=True, unidades=10)]
    assert casar(ml("Asad Lattafa 100ml", "6291108735411", full=True), ls) == (2, "gtin", False)


def test_04_mesmo_gtin_full_e_tipo_iguais_nas_duas_e_empate_a_conferir():
    ls = [nubi(1, "Asad Lattafa 100ml", "6291108735411", unidades=5),
          nubi(2, "Asad Lattafa Edp 100ml", "6291108735411", unidades=40)]
    assert casar(ml("Asad Lattafa 100ml", "6291108735411"), ls) == (2, "gtin", True)


def test_05_gtins_diferentes_o_titulo_nao_passa_por_cima():
    ls = [nubi(1, "Perfume Asad Lattafa 100ml", "6291108730515")]
    assert casar(ml("Perfume Asad Lattafa 100ml", "6291108735411"), ls) == (None, None, False)


def test_06_sem_gtin_titulo_forte_com_acento_maiusculas_e_original():
    ls = [nubi(1, "Perfume Árabe Asad Lattafa 100ml Masculino"), nubi(2, "Yara Lattafa 100ml Feminino")]
    assert casar(ml("PERFUME ARABE ASAD LATTAFA 100 ML MASCULINO ORIGINAL"), ls) == (1, "titulo_forte", False)


def test_07_volume_concentracao_genero_e_kit_diferentes_nao_ligam():
    ls = [nubi(1, "Asad Lattafa 200ml"), nubi(2, "Asad Lattafa Edt 100ml"), nubi(3, "Asad Lattafa 100ml Feminino"),
          nubi(4, "Kit 3 Asad Lattafa 100ml")]
    assert casar(ml("Asad Lattafa Edp 100ml Masculino"), ls) == (None, None, False)


def test_08_marca_do_titulo_diferente_da_marca_chave_nao_liga():
    ls = [nubi(1, "Club De Nuit Intense 105ml", marca="ARMAF")]
    assert casar(ml("Club De Nuit Intense 105ml Afnan"), ls) == (None, None, False)


def test_09_volume_so_de_um_lado_e_titulo_fraco_a_conferir():
    ls = [nubi(1, "Perfume Asad Lattafa Masculino"), nubi(2, "Yara Lattafa Feminino")]
    assert casar(ml("Perfume Asad Lattafa 100ml Masculino"), ls) == (1, "titulo_fraco", True)


def test_10_ligacao_manual_nunca_e_desfeita():
    manual = {"metodo": "manual", "linha": {"id": 7}}
    ls = [nubi(1, "Asad Lattafa 100ml", "6291108735411")]
    assert casar(ml("Asad Lattafa 100ml", "6291108735411"), ls, manual) == (7, "manual", False)
    # ligação automática antiga não trava: o GTIN refaz
    assert casar(ml("Asad Lattafa 100ml", "6291108735411"), ls, {"metodo": "titulo_fraco", "linha": {"id": 7}}) == (1, "gtin", False)


if __name__ == "__main__":
    for nome, f in sorted(globals().items()):
        if nome.startswith("test_") and callable(f):
            f()
            print("ok", nome)
