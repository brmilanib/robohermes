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
    assert casar(ml("PERFUME ARABE ASAD LATTAFA 100 ML MASCULINO ORIGINAL"), ls) == (1, "titulo_forte", True)


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



def test_11_tres_anuncios_e_explorador():
    ls = [nubi(1, "Asad Lattafa 100ml", "6291108735411"), nubi(2, "Yara Lattafa EDP 100ml Feminino"),
          nubi(3, "Outro perfume")]
    foto = "https://http2.mlstatic.com/D_123-MLB123456_082025-I.jpg"
    exemplos = [dict(ml("Produto", "6291108735411")), ml("Yara Lattafa EDP 100ml Feminino"),
                dict(ml("Sem título conhecido"), foto=foto.replace('-I.jpg', '-O.webp'))]
    fs = [{"foto": foto, "title": "Outro perfume"}]
    for a, esperado in zip(exemplos, [(1, "gtin", False), (2, "titulo", True), (3, "foto", False)]):
        r = c.casar_anuncio_nubimetrics(a, ls, [dict(ls[0], id=101)], fs)
        assert (r["vend_anuncio_id"], r["confianca"], r["a_conferir"]) == esperado, r
        if esperado[0] == 1:
            assert r["anuncio_explorador_id"] == 101


def test_12_rotas_decisoes_persistem_e_isolam_vendedor():
    import json
    import copy
    import meli
    import nubi_web as w
    from test_meli import Repo

    class R(Repo):
        def __init__(self):
            super().__init__()
            self.regs = [{"vendedor": "SIENO", "seller_id": "123", "mlb": "MLB1", "dados": ml("X", "6291108735411")},
                         {"vendedor": "SIENO", "seller_id": "123", "mlb": "MLB2", "dados": ml("Yara Lattafa EDP 100ml")},
                         {"vendedor": "SIENO", "seller_id": "123", "mlb": "MLB3", "dados": ml("Desconhecido")}]
            self.linhas = [nubi(1, "Asad Lattafa 100ml", "6291108735411"), nubi(2, "Yara Lattafa EDP 100ml")]
        def _todos(self, t, q=None):
            if t == "vend_relatorios":
                return [{"id": 9, "mes": "2026-09-01", "vendedor": "SIENO"}]
            if t == "vend_anuncios":
                return copy.deepcopy(self.linhas)
            if t == "vend_anuncios_ml":
                return copy.deepcopy([r for r in self.regs if all(str(r.get(k)) == str(v)[3:] for k, v in (q or {}).items() if str(v).startswith("eq."))])
            return []
        def _req(self, metodo, tabela, q=None, corpo=None, **kw):
            if tabela == "vend_anuncios_ml":
                rs = self._todos(tabela, q)
                if metodo == "PATCH":
                    for a in self.regs:
                        if a in rs and not ("or" in (q or {}) and a.get("confianca_ligacao") in ("manual", "rejeitada")):
                            a.update(corpo)
                return rs
            return super()._req(metodo, tabela, q, corpo, **kw)
    r = R()
    meli.gravar_hash_lojas(r, {"SIENO": {"id": "123", "confianca": "manual"}}, meli.SEGUIDOS)
    get = lambda: w.rota_meli(r, "GET", "meli_seguido_anuncios", {"vendedor": "SIENO"}, b"")
    def post(mlb, alvo, decisao):
        return w.rota_meli(r, "POST", "meli_seguido_anuncio_ligar", {}, json.dumps(
            {"vendedor": "SIENO", "mlb": mlb, "vend_anuncio_id": alvo, "decisao": decisao}).encode())
    a = get()
    assert len(a["ligados"]) == 1 and len(a["a_conferir"]) == 2
    assert a["cobertura"] == 33.3 and a["anuncios"][0]["variacao_pct"] is None
    post("MLB2", 2, "confirmar")
    post("MLB1", None, "rejeitar")
    r.linhas[0]["gtin"] = "6291108730515"
    b = get()
    assert b["ligados"][0]["mlb"] == "MLB2" and b["ligados"][0]["confianca"] == "manual"
    assert next(x for x in b["a_conferir"] if x["mlb"] == "MLB1")["vend_anuncio_id"] is None
    for mlb, alvo, decisao in [("MLB2", 999, "confirmar"), ("MLB999", 2, "confirmar"), ("MLB2", 2, "qualquer")]:
        try:
            post(mlb, alvo, decisao)
            assert False, "decisão inválida aceita"
        except w.ErroNuvem:
            pass


def test_13_ofertas_somente_do_seller_confirmado():
    import meli
    from test_meli import Repo
    r = Repo()
    loja = {"id": "123", "confianca": "manual", "anuncios": [dict(ml("Prova"), anuncio="MLB1")]}
    velhos = meli.ofertas_por_gtin, meli._enriquecer
    meli.ofertas_por_gtin = lambda gs: [{"anuncio": "MLB2", "vendedor_id": "123", "gtin_busca": "6291108735411"},
                                       {"anuncio": "MLB3", "vendedor_id": "999"}]
    meli._enriquecer = lambda xs: xs
    try:
        xs, _ = meli.anuncios_do_seguido(r, "SIENO", ["6291108735411"], loja)
        assert {a["mlb"] for a in xs} == {"MLB1", "MLB2"}
    finally:
        meli.ofertas_por_gtin, meli._enriquecer = velhos


def test_14_foto_nao_sobrepoe_gtin_e_ambiguidade_pede_conferencia():
    foto = "https://http2.mlstatic.com/D_123-MLB123456_082025-I.jpg"
    ls = [dict(nubi(1, "Primeiro", "6291108735411"), foto=foto), dict(nubi(2, "Segundo"), foto=foto)]
    r = c.casar_anuncio_nubimetrics(dict(ml("X"), foto=foto), ls, [], [])
    assert r["confianca"] == "foto" and r["a_conferir"]
    r = c.casar_anuncio_nubimetrics(dict(ml("X", "6291108730515"), foto=foto), ls[:1], [], [])
    assert r["vend_anuncio_id"] is None
    r = c.casar_anuncio_nubimetrics(dict(ml("X"), foto=foto.replace("http2.mlstatic.com", "outro.com")), ls, [], [])
    assert r["vend_anuncio_id"] is None


def test_15_full_desconhecido_nao_resolve_empate():
    ls = [nubi(1, "Asad", "6291108735411", full=True), nubi(2, "Asad", "6291108735411", full=False)]
    r = c.casar_anuncio_nubimetrics({"titulo": "Asad", "gtin": "6291108735411"}, ls, [], [])
    assert r["a_conferir"]


def test_16_sem_tabela_e_sem_catalogo_preserva_previa():
    import meli
    import nubi_web as w
    from test_meli import Repo
    class R(Repo):
        def _todos(self, tabela, q=None):
            if tabela == "vend_relatorios":
                return [{"id": 1, "mes": "2026-09-01", "vendedor": "SIENO"}]
            if tabela == "vend_anuncios":
                return [nubi(1, "Asad Lattafa", "6291108735411")]
            if tabela == "vend_anuncios_ml":
                raise w.ErroNuvem("Tabela ausente", 404)
            return []
    r = R()
    meli.gravar_hash_lojas(r, {"SIENO": {"id": "123", "confianca": "manual", "anuncios": [
        {"anuncio": "MLB1", "titulo": "Asad Lattafa", "preco": 0}]}}, meli.SEGUIDOS)
    velho = meli.ofertas_por_gtin
    def indisponivel(*a, **k):
        raise meli.ErroMeli("Sem catálogo")
    meli.ofertas_por_gtin = indisponivel
    try:
        out = w.rota_meli(r, "GET", "meli_seguido_anuncios", {"vendedor": "SIENO"}, b"")
        assert len(out["anuncios"]) == 1 and not out["pode_ligar"]
        assert out["anuncios"][0]["preco"] == 0 and "indisponível" in out["aviso"]
    finally:
        meli.ofertas_por_gtin = velho


if __name__ == "__main__":
    for nome, f in sorted(globals().items()):
        if nome.startswith("test_") and callable(f):
            f()
            print("ok", nome)
