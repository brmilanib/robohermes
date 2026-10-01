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


# Card #127: rotas meli_seguido_anuncios / meli_seguido_anuncio_ligar (anúncio real do ML x linha do Nubimetrics)
import json  # noqa: E402

import nubi_web as w  # noqa: E402


class RepoRota:
    def __init__(self):
        self.ml = {}
        self.linhas = [
            {"id": 1, "titulo": "Asad Lattafa 100ml Masculino", "gtin": "6291108735411", "marca_chave": "LATTAFA", "marca": "Lattafa",
             "fulfillment": 0, "tipo_pub": "Clássico", "unidades": 30, "vendas": 3000, "preco": 100, "relatorio_id": 9},
            {"id": 2, "titulo": "Yara Lattafa Feminino 100ml", "gtin": "", "marca_chave": "LATTAFA", "marca": "Lattafa",
             "fulfillment": 0, "tipo_pub": "Clássico", "unidades": 9, "vendas": 900, "preco": 100, "relatorio_id": 9},
            {"id": 3, "titulo": "Perfume Khamrah Lattafa Masculino", "gtin": "", "marca_chave": "LATTAFA", "marca": "Lattafa",
             "fulfillment": 0, "tipo_pub": "Clássico", "unidades": 5, "vendas": 500, "preco": 100, "relatorio_id": 9}]
        self.resumos = {"meli|seguidos": json.dumps({"SIENO": {"id": 222, "nome": "SIENO", "confianca": "manual"}})}
        self.upserts = 0

    def _eq(self, v):
        return f"eq.{v}"

    def _todos(self, t, q=None):
        q = q or {}
        if t == "vend_anuncios_ml":
            return [dict(x) for x in self.ml.values() if x["vendedor"] == q["vendedor"][3:]
                    and ("mlb" not in q or x["mlb"] == q["mlb"][3:])]
        if t == "vend_relatorios":
            return [{"id": 9, "vendedor": "SIENO", "mes": "2026-09-01"}]
        if t == "vend_anuncios":
            return [dict(l, estado="active", catalogo=0, frete_gratis=0, desconto=0, sku="", marca_chave=l["marca_chave"]) for l in self.linhas]
        if t == "ia_resumos":
            return []
        return []

    def _req(self, metodo, tabela, q=None, corpo=None, **k):
        if tabela == "ia_resumos" and metodo == "GET":
            c = (q or {}).get("chave", "")[3:]
            return [{"texto": self.resumos[c], "criado_em": "x"}] if c in self.resumos else []
        if tabela == "vend_anuncios_ml" and metodo == "POST":
            self.upserts += 1
            for x in corpo:
                assert x.get("vendedor") and x.get("seller_id"), "NOT NULL do Postgres"
                self.ml[x["mlb"]] = {**self.ml[x["mlb"]], **x}
            return []
        if tabela == "marca_apelidos" or metodo == "GET":
            return []
        return []


def _anuncio(mlb, titulo, gtin=None, vendidos=1):
    return {"mlb": mlb, "vendedor": "SIENO", "seller_id": "222", "link": "x", "titulo": titulo, "foto": "f", "preco": 99,
            "vendidos": vendidos, "full": False, "tipo_pub": "Clássico", "gtin": gtin, "vend_anuncio_id": None, "ligacao": None}


def test_11_rota_separa_ligados_a_conferir_e_sem_ligacao():
    r = RepoRota()
    for a in (_anuncio("MLB1", "Asad Lattafa 100ml Masculino Original", "6291108735411", 50),
              _anuncio("MLB2", "Perfume Yara Lattafa Feminino", None, 20),          # título sem volume: fraco, a conferir
              _anuncio("MLB3", "Fragrância Qualquer Outra Coisa", None, 5)):
        r.ml[a["mlb"]] = a
    out = w.rota_meli(r, "GET", "meli_seguido_anuncios", {"vendedor": "SIENO"}, b"")
    assert [x["mlb"] for x in out["ligados"]] == ["MLB1"] and out["ligados"][0]["metodo"] == "gtin"
    assert [x["mlb"] for x in out["a_conferir"]] == ["MLB2"] and out["a_conferir"][0]["nubimetrics"]["id"] == 2
    assert [x["mlb"] for x in out["sem_ligacao"]] == ["MLB3"] and out["total"] == 3
    assert r.ml["MLB1"]["vend_anuncio_id"] == 1 and r.ml["MLB1"]["ligacao"] == "gtin"      # gravado
    assert out["pct_ligados"] == 33.3


def test_12_ligacao_manual_e_recusa_nao_sao_desfeitas_por_rodada_nova():
    r = RepoRota()
    for a in (_anuncio("MLB1", "Asad Lattafa 100ml Masculino Original", "6291108735411", 50),
              _anuncio("MLB2", "Perfume Yara Lattafa Feminino", None, 20)):
        r.ml[a["mlb"]] = a
    w.rota_meli(r, "GET", "meli_seguido_anuncios", {"vendedor": "SIENO"}, b"")
    pedido = lambda **d: w.rota_meli(r, "POST", "meli_seguido_anuncio_ligar", {}, json.dumps(dict(vendedor="SIENO", **d)).encode())
    pedido(mlb="MLB2", decisao="sim")                                   # ✔ É este (a sugerida, linha 2)
    pedido(mlb="MLB1", decisao="nao")                                   # ✖ Não é (mesmo com GTIN igual)
    for _ in range(2):                                                  # rodada nova: nada muda
        out = w.rota_meli(r, "GET", "meli_seguido_anuncios", {"vendedor": "SIENO"}, b"")
    assert [x["mlb"] for x in out["ligados"]] == ["MLB2"] and out["ligados"][0]["metodo"] == "manual"
    assert out["sem_ligacao"][0]["mlb"] == "MLB1" and out["sem_ligacao"][0]["recusado"]
    pedido(mlb="MLB1", decisao="limpar")                                # volta ao automático
    out = w.rota_meli(r, "GET", "meli_seguido_anuncios", {"vendedor": "SIENO"}, b"")
    assert {x["mlb"] for x in out["ligados"]} == {"MLB1", "MLB2"}
    for ruim in (dict(mlb="MLB2", decisao="sim", vend_anuncio_id=999), dict(mlb="MLBX", decisao="sim"), dict(mlb="MLB2", decisao="oi")):
        try:
            pedido(**ruim)
            raise AssertionError("devia recusar")
        except w.ErroNuvem:
            pass
    assert w.rota_meli(r, "GET", "meli_seguido_anuncios", {"vendedor": "OUTRO"}, b"")["anuncios"] == []


def test_13_manual_de_relatorio_antigo_nao_e_sobrescrita():
    r = RepoRota()
    a = _anuncio("MLB1", "Asad Lattafa 100ml Masculino Original", "6291108735411")
    a.update(vend_anuncio_id=777, ligacao="manual")                 # linha 777 era de um relatório que já não é o último
    r.ml["MLB1"] = a
    out = w.rota_meli(r, "GET", "meli_seguido_anuncios", {"vendedor": "SIENO"}, b"")
    assert r.ml["MLB1"]["ligacao"] == "manual" and r.ml["MLB1"]["vend_anuncio_id"] == 777 and r.upserts == 0
    assert out["ligados"][0]["metodo"] == "gtin"                    # na tela mostra o casamento de agora


if __name__ == "__main__":
    for nome, f in sorted(globals().items()):
        if nome.startswith("test_") and callable(f):
            f()
            print("ok", nome)
