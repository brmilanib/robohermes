"""Xerjoff "Outros" (29/09): anúncio sem GTIN entra no produto certo pelas linhas que a marca já tem nos GTINs."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import pandas as pd  # noqa: E402
import nubi  # noqa: E402


def _df(linhas):
    return pd.DataFrame([{"titulo": t, "gtin": g, "un": u, "fat": u * 1000.0, "categoria": "", "marca_anuncio": "Xerjoff",
                          "vendedor": "v", "preco": 1000.0} for t, g, u in linhas])


def test_sem_gtin_sai_de_outros():
    df = _df([
        ("Xerjoff Naxos 1861 Eau De Parfum 100ml", "8033488155025", 80),
        ("Perfume Xerjoff 1861 Naxos Edp 100ml", "8033488155999", 21),
        ("Xerjoff Erba Pura Eau De Parfum 100ml", "8033488156077", 102),
        ("Decant Xerjoff 5ml", "8033488150000", 3),
        ("Perfume Xerjoff 1861 Naxos Eau De Parfum 100ml", "", 40),
        ("Decant Xerjoff Erba Pura 10ml Eau De Parfum", "", 10),
        ("Xerjoff Perfume Importado Original 100ml Edp", "", 5),
    ])
    out = nubi.consolidar(df, "XERJOFF", {}, info={})
    linhas = list(out["linha"])
    assert linhas[0] == linhas[1] == linhas[4] == "Naxos 1861", linhas   # mesma linha, uma grafia só
    assert linhas[5] == "Erba Pura", linhas                                # "Decant" não vira linha
    assert linhas[6] == "Outros", linhas                                   # sem pista nenhuma, continua Outros
    assert out.at[4, "confianca"] == nubi.CONF_LINHA_CONHECIDA
    assert "Naxos 1861" in out.at[4, "produto"], out.at[4, "produto"]
    print("ok test_sem_gtin_sai_de_outros")


if __name__ == "__main__":
    test_sem_gtin_sai_de_outros()


class _Repo:
    """Só o que produto_meu lê: último estoque, vendas por anúncio (30 dias), meus anúncios e minhas lojas."""
    def __init__(self, itens, vendas, anuncios=(), lojas=()):
        self.itens, self.vendas, self.anuncios, self.lojas = itens, vendas, list(anuncios), list(lojas)

    def _eq(self, v):
        return f"eq.{v}"

    def _req(self, metodo, tabela, q=None, **k):
        import json
        if tabela == "estoque_atualizacoes":
            return [{"id": 7, "criado_em": "2026-09-29T12:00:00+00:00"}]
        if tabela == "ia_resumos":
            return [{"texto": json.dumps(self.vendas)}]
        return []

    def _todos(self, tabela, q=None):
        return {"estoque_itens": [dict(x) for x in self.itens], "meus_anuncios": [dict(x) for x in self.anuncios],
                "ml_lojas": [{"nome": n} for n in self.lojas]}.get(tabela, [])


def test_quadro_do_produto_traz_o_meu_lado():
    os.environ.setdefault("ANTHROPIC_API_KEY", "x")
    import nubi_web as w
    itens = [{"sku": "XJ-NAX100", "titulo": "Perfume Xerjoff Naxos 1861 Edp 100ml", "disponivel": 4, "atual": 4,
              "transito_compra": 6, "estoque_min": 5, "custo_medio": 900},
             {"sku": "XJ-ERBA100", "titulo": "Xerjoff Erba Pura Edp 100ml", "disponivel": 2, "atual": 2, "transito_compra": 0,
              "estoque_min": 0, "custo_medio": 800},
             {"sku": "8033488155025", "titulo": "Outro nome qualquer", "disponivel": 1, "atual": 1, "transito_compra": 0,
              "estoque_min": 0, "custo_medio": 950}]
    vendas = {"dias": 30, "inicio": "2026-08-30", "fim": "2026-09-28", "linhas": [
        {"sku": "XJ-NAX100", "produto": "Naxos", "loja": "PUREHOME[Mercado Libre BR]", "unidades": 10, "valor": 15000},
        {"sku": "XJ-NAX100", "produto": "Naxos", "loja": "Purehome[Shopee]", "unidades": 2, "valor": 2800},
        {"sku": "XJ-ERBA100", "produto": "Erba", "loja": "PUREHOME[Mercado Libre BR]", "unidades": 5, "valor": 6000}]}
    r = _Repo(itens, vendas, [{"id": "MLB1", "loja": "PUREHOME", "titulo": "Xerjoff Naxos 1861 Eau De Parfum 100ml", "preco": 1499}],
              ["PUREHOME"])
    # pelo título (sem GTIN que case)
    m = w.produto_meu(r, "Xerjoff Naxos 1861 EDP 100 ml")
    assert m["casado_por"] == "titulo" and [x["sku"] for x in m["estoque"]] == ["XJ-NAX100"], m
    assert m["vendas"]["unidades"] == 12 and m["vendas"]["preco_medio"] == round(17800 / 12, 2)
    assert [l["loja"] for l in m["vendas"]["lojas"]] == ["PUREHOME[Mercado Libre BR]", "Purehome[Shopee]"]
    assert m["anuncios_ml"][0]["id"] == "MLB1" and m["minhas_lojas"] == ["PUREHOME"]
    # pelo GTIN (SKU = GTIN) vence o título
    m = w.produto_meu(r, "Xerjoff Naxos 1861 EDP 100 ml", gtins=["8033488155025"])
    assert m["casado_por"] == "gtin" and [x["sku"] for x in m["estoque"]] == ["8033488155025"]
    # "Outros" não casa por palavra solta; produto que não tenho
    assert w.produto_meu(r, "Xerjoff Outros EDP 100 ml", titulos=["Xerjoff Naxos 1861 100ml"])["estoque"] == []
    m = w.produto_meu(r, "Xerjoff Torino 21 EDP 100 ml")
    assert m["estoque"] == [] and m["vendas"]["unidades"] == 0 and m["casado_por"] is None
    # 01/10 (Bruno, Light Blue): "Dolce & Gabbana Light Blue EDP 100 ml" não pode puxar o meu SKU Light Blue EDT 50 ml,
    # nem pelo título de reserva sem volume ("Perfume Dolce & Gabbana Light Blue Feminino")
    itens3 = [{"sku": "DOLCE-LIGHTBLUE-50", "titulo": "Light Blue Pour Homme Dolce&Gabbana Eau de Toilette Masculino 50ml", "disponivel": 0, "atual": 0,
               "transito_compra": 0, "estoque_min": 2, "custo_medio": 179},
              {"sku": "DG-LB-100", "titulo": "Dolce Gabbana Light Blue Eau De Parfum Intense 100ml", "disponivel": 3, "atual": 3, "transito_compra": 0, "estoque_min": 0, "custo_medio": 400}]
    m = w.produto_meu(_Repo(itens3, {"dias": 30, "linhas": []}), "Dolce & Gabbana Light Blue EDP 100 ml",
                      titulos=["Perfume Dolce & Gabbana Light Blue Feminino", "Dolce&gabbana Light Blue For Men Eau De Parfum 100ml"])
    assert [x["sku"] for x in m["estoque"]] == ["DG-LB-100"], m["estoque"]
    m = w.produto_meu(_Repo(itens3, {"dias": 30, "linhas": []}), "Dolce & Gabbana Light Blue EDT 50 ml", titulos=["Light Blue Pour Homme 50ml"])
    assert [x["sku"] for x in m["estoque"]] == ["DOLCE-LIGHTBLUE-50"], m["estoque"]
    # 30/09 (Bruno: "meu Vibrato tem 26", o quadro dizia 63): decant de 3/5/10 ml não soma no produto de 100 ml
    itens2 = [{"sku": "SOS-VIB-100", "titulo": "Perfume Vibrato Sospiro Edp 100ml Importado Original", "disponivel": 25, "atual": 26,
               "transito_compra": 1, "estoque_min": 21, "custo_medio": 988},
              {"sku": "SV-DEC-03", "titulo": "Vibrato Sospiro Extrait de Parfum Decant(3ml)", "disponivel": 19, "atual": 20, "transito_compra": 0, "estoque_min": 0, "custo_medio": 30},
              {"sku": "SV-DEC-10", "titulo": "Vibrato Sospiro Extrait de Parfum Decant(10ml)", "disponivel": 20, "atual": 20, "transito_compra": 0, "estoque_min": 0, "custo_medio": 90}]
    m = w.produto_meu(_Repo(itens2, {"dias": 30, "linhas": []}), "Sospiro Vibrato EDP 100 ml")
    assert [x["sku"] for x in m["estoque"]] == ["SOS-VIB-100"], m["estoque"]
    m = w.produto_meu(_Repo(itens2, {"dias": 30, "linhas": []}), "Sospiro Vibrato Decant 10 ml")
    assert [x["sku"] for x in m["estoque"]] == ["SV-DEC-10"], m["estoque"]
    print("ok test_quadro_do_produto_traz_o_meu_lado")


if __name__ == "__main__":
    test_quadro_do_produto_traz_o_meu_lado()


def test_numero_do_nome_separa_produtos():
    import nubi_web as w
    itens = [{"sku": "T25", "titulo": "Xerjoff Torino 25 Edp 100ml", "disponivel": 3}]
    for it in itens:
        it["_tok"] = w._tokens_produto(it["titulo"])
    assert w._casar_varios("Xerjoff Torino 21 EDP 100 ml", itens) == []
    assert w._casar_varios("Perfume Xerjoff Torino 25 Eau de Parfum 100ml", itens)[0]["sku"] == "T25"
    assert w.casar_estoque("Xerjoff Torino 21 100ml", itens) is None
    print("ok test_numero_do_nome_separa_produtos")


if __name__ == "__main__":
    test_numero_do_nome_separa_produtos()


def test_marca_escrita_errado_e_da_marca():
    # 29/09 (print do Bruno): "Outra marca: Lataffa" com 28 mil un. dentro da Lattafa
    nubi.definir_apelidos({})
    assert nubi.marca_bate("LATAFFA", "LATTAFA") and nubi.marca_bate("Lataffa Vurv", "LATTAFA")
    assert nubi.marca_bate("BELARA - LATAFFA YARA", "LATTAFA")
    assert not nubi.marca_bate("CAROLINA HERRERA", "AROEIRA") and not nubi.marca_bate("MONTBLANC", "MONTANA")
    assert not nubi.marca_bate("ARMANI", "ARMAF") and not nubi.marca_bate("DIOT", "DIOR") and not nubi.marca_bate("CHANTAL", "CHANEL")
    nubi.definir_apelidos({"AZARRO": "AZZARO"})                  # Nomes de marcas
    assert nubi.marca_bate("Azarro", "AZZARO")
    df = pd.DataFrame([{"titulo": t, "gtin": g, "un": u, "fat": u * 300.0, "categoria": "", "marca_anuncio": m,
                        "vendedor": "v", "preco": 300.0} for t, g, u, m in [
        ("Perfume Lattafa Asad 100ml Eau De Parfum", "6291108735411", 500, "Lataffa"),
        ("Perfume Asad Lataffa 100ml Eau De Parfum", "", 300, "Lataffa"),
        ("Lattafa Asad Eau de Parfum 100ml", "6291108735411", 50, "Lattafa"),
        ("Perfume J. Serrano inspirado", "", 20, "J. Serrano")]])
    out = nubi.consolidar(df, "LATTAFA", {}, info={})
    assert list(out["tipo"])[:3] != [nubi.TIPO_OUTRA] * 3 and out.at[0, "linha"] == "Asad", out[["linha", "tipo"]]
    assert out.at[1, "linha"] == "Asad", out.at[1, "linha"]                 # "Lataffa" não vira nome de linha
    assert out.at[3, "tipo"] == nubi.TIPO_CONTRATIPO                         # 30/09: contratipo = Low price
    a = nubi.auditar_marca(out, "LATTAFA")
    assert not any(x["tipo"] == "marca_errada" for x in a["achados"]) and a["pct_outra_marca"] < 3, a
    # conferência acha a marca escrita errado no que foi gravado com a regra antiga
    velho = out.copy()
    velho.loc[[0, 1], "tipo"], velho.loc[[0, 1], "linha"] = nubi.TIPO_OUTRA, "Lataffa"
    a = nubi.auditar_marca(velho, "LATTAFA")
    assert a["achados"][0]["tipo"] == "marca_errada" and a["achados"][0]["un"] == 800, a["achados"]
    print("ok test_marca_escrita_errado_e_da_marca")


if __name__ == "__main__":
    test_marca_escrita_errado_e_da_marca()


def test_variacao_da_linha_fakhar_gold():
    # 29/09 (print do Bruno): "Lattafa Fakhar EDP 100 ml" era o Fakhar Gold Extrait (GTIN pesquisado) + Platin sem GTIN
    nubi.definir_apelidos({})
    df = pd.DataFrame([{"titulo": t, "gtin": g, "un": u, "fat": u * 300.0, "categoria": "", "marca_anuncio": "Lattafa",
                        "vendedor": "v", "preco": 300.0} for t, g, u in [
        ("Perfume Árabe Lattafa Fakhar Gold Extrai", "6290360593166", 900),
        ("Perfume Lattafa Fakhar Rose Gold Feminin", "6290360593166", 300),
        ("Perfume Lattafa Fakhar Black Eau De Parfum 100ml", "6290360591111", 400),
        ("Perfume Fakhar Lattafa Rose Feminino 100ml Original", "6290360592222", 200),
        ("Perfume Lattafa Fakhar Platin 100ml Eau De Parfum", "6290362345817", 100),
        ("Perfume Árabe  - Fakhar Platinum Edp - 5", "", 2),
        ("Perfume Lattafa Asad 100ml Eau De Parfum", "6291108735411", 500),
        ("Perfume Árabe Masculino Asad Bourbon Lat", "6291108739999", 80)]])
    info = {"6290360593166": {"nome": "593166 3.4 oz  Fakhar Extrait Gold Eau De Parfum Spray for Unisex one size", "marca": "Lattafa"}}
    cfg = {"LATTAFA": {"linhas": [["fakhar", "Fakhar"], ["fakhar black", "Fakhar Black"], ["fakhar rose", "Fakhar Rose"],
                                  ["asad", "Asad"], ["asad bourbon", "Asad Bourbon"]]}}
    out = nubi.consolidar(df, "LATTAFA", cfg, info=info)
    l = list(out["linha"])
    assert l[0] == l[1] == "Fakhar Gold", l                      # o GTIN é um só produto: vale o nome pesquisado
    assert l[2] == "Fakhar Black" and l[3] == "Fakhar Rose", l
    assert l[4] == "Fakhar Platin" and l[5] == "Fakhar Platin", l   # "Platinum" cortado junta com "Platin"
    assert l[6] == "Asad" and l[7] == "Asad Bourbon", l          # Asad sozinho continua Asad
    assert "Fakhar Gold" in out.at[0, "produto"], out.at[0, "produto"]
    print("ok test_variacao_da_linha_fakhar_gold")


if __name__ == "__main__":
    test_variacao_da_linha_fakhar_gold()


def test_conferencia_diaria_de_todas_as_marcas():
    # 29/09 (Bruno): rotina sem IA; marca escrita errado -> reprocessa sozinho; o resto vira lista
    import json
    os.environ.setdefault("ANTHROPIC_API_KEY", "x")
    import nubi_web as w

    class R:
        def __init__(self):
            self.resumos, self.reproc = {}, []
        def _eq(self, v): return f"eq.{v}"
        def snapshots(self):
            return pd.DataFrame([{"id": 1, "marca": "LATTAFA", "inicio": "2026-08-01", "fim": "2026-09-27"},
                                 {"id": 2, "marca": "XERJOFF", "inicio": "2026-08-01", "fim": "2026-09-27"}])
        def _todos(self, t, q=None):
            if q["snapshot_id"].startswith("in."):              # mapa de GTIN entre marcas: nenhum GTIN repetido aqui
                return []
            if q["snapshot_id"] == "eq.1":
                return [{"titulo": "Perfume Lattafa Asad", "marca_anuncio": "Lataffa", "gtin": "", "un": 800, "linha": "Lataffa",
                         "tipo": nubi.TIPO_OUTRA, "confianca": "-"},
                        {"titulo": "Lattafa Yara 100ml", "marca_anuncio": "Lattafa", "gtin": "1", "un": 500, "linha": "Yara",
                         "tipo": "EDP", "confianca": nubi.CONF_GTIN}]
            return [{"titulo": "Xerjoff Naxos", "marca_anuncio": "Xerjoff", "gtin": "2", "un": 90, "linha": "Naxos",
                     "tipo": "EDP", "confianca": nubi.CONF_GTIN},
                    {"titulo": "Perfume Xerjoff Importado", "marca_anuncio": "Xerjoff", "gtin": "", "un": 10, "linha": "Outros",
                     "tipo": "EDP", "confianca": nubi.CONF_TITULO}]
        def _req(self, metodo, tabela, q=None, corpo=None, **k):
            if tabela == "ia_resumos" and metodo == "GET":
                chave = (q or {}).get("chave", "")
                return [{"chave": c, "texto": v, "criado_em": "x"} for c, v in self.resumos.items()
                        if chave == f"eq.{c}" or chave.startswith("like.") and c.startswith(chave[5:-1])]
            if tabela == "ia_resumos" and metodo == "POST":
                for r in corpo:
                    self.resumos[r["chave"]] = r["texto"]
            return []
        def carregar_config(self): return {}

    r = R()
    antes = nubi.reconsolidar
    nubi.reconsolidar = lambda repo, cfg, marcas=None: r.reproc.append(list(marcas or []))
    try:
        txt = w.auditar_explorador(r)
        assert "2 marca(s) conferida(s)" in txt and "1 reprocessada(s)" in txt, txt
        assert r.reproc == [["LATTAFA"]]
        assert w.auditar_explorador(r) is None                     # 1 vez por dia
        a = w.auditoria_explorador_ultima(r)
        lat = next(m for m in a["marcas"] if m["marca"] == "LATTAFA")
        assert lat["achados"][0]["tipo"] == "marca_errada" and lat["achados"][0]["corrigido"] is True
        xj = next(m for m in a["marcas"] if m["marca"] == "XERJOFF")
        assert xj["nota"] == 90.0 and xj["outros_top"][0]["titulo"] == "Perfume Xerjoff Importado", xj
    finally:
        nubi.reconsolidar = antes
    print("ok test_conferencia_diaria_de_todas_as_marcas")


if __name__ == "__main__":
    test_conferencia_diaria_de_todas_as_marcas()


def test_mesmo_gtin_em_outra_marca_e_o_mesmo_produto():
    # 29/09 (print do Bruno): ICARBONXX cadastra o Asad Elixir da Lattafa com a marca LIPX (mesmo GTIN 6290362346548)
    nubi.definir_apelidos({})
    L = lambda **k: dict({"confianca": nubi.CONF_GTIN, "genero": "Masculino", "volume": "100 ml", "tipo": "EDP"}, **k)
    linhas = [
        L(gtin="6290362346548", un=2800, marca_snap="LATTAFA", titulo="Perfume Asad Elixir Lattafa Árabe Origin",
          linha="Asad Elixir", produto="Lattafa Asad Elixir EDP 100 ml"),
        L(gtin="6290362346548", un=1300, marca_snap="LIPX", titulo="Perfume Asad Elixir 100ml Eau De Parfum Original Edp",
          linha="Lattafa", produto="Lipx Lattafa EDP 100 ml"),
        # a LIPX vende mais, mas o título não diz LIPX e o da Lattafa diz: a dona é a Lattafa
        L(gtin="6291107455365", un=1900, marca_snap="LIPX", titulo="Perfume Arabe Qaed Al Fursan 90ml", linha="Qaed",
          produto="Lipx Qaed EDP 90 ml", volume="90 ml"),
        L(gtin="6291107455365", un=504, marca_snap="LATTAFA", titulo="Lattafa Qaed Al Fursan Edp 90ml", linha="Qaed AL Fursan",
          produto="Lattafa Qaed AL Fursan EDP 90 ml", volume="90 ml"),
        # ninguém cita a marca no título e ninguém pesquisou: vale quem mais vende
        L(gtin="6290360378053", un=2010, marca_snap="LIPX", titulo="Perfume French Avenue Vulcan Feu Edp 100ml",
          linha="Vulcan Feu", produto="Lipx Vulcan Feu EDP 100 ml"),
        L(gtin="6290360378053", un=11, marca_snap="LATTAFA", titulo="Perfume Fakhar Men Black Árabe", linha="Fakhar Black",
          produto="Lattafa Fakhar Black EDP 100 ml"),
        L(gtin="111", un=5, marca_snap="LATTAFA", titulo="x", linha="Yara", produto="Lattafa Yara EDP 100 ml")]   # só 1 marca
    m = nubi.mapa_gtin_global(linhas)
    assert set(m) == {"6290362346548", "6291107455365", "6290360378053"}, m
    # 30/09 (Ameerati da Al Wataniah preso na LIPX): os anúncios da Al Wataniah já tinham sido gravados como "outra marca";
    # o mapa refeito tem que devolver o GTIN a quem o título cita, com o nome dela no produto
    am = [L(gtin="5055810014902", un=1677, marca_snap="AL WATANIAH", titulo="Perfume Feminino Ameerati Al Wataniah Eau De Parfum",
            linha="Ameerati", produto="Lipx Ameerati EDP 100 ml", tipo=nubi.TIPO_OUTRA, confianca=nubi.CONF_GTIN_OUTRA, genero="Feminino"),
          L(gtin="5055810014902", un=1502, marca_snap="LIPX", titulo="Perfume Ameerati 100ml Edp", linha="Ameerati",
            produto="Lipx Ameerati EDP 100 ml", genero="Feminino")]
    a = nubi.mapa_gtin_global(am)["5055810014902"]
    assert a["marca"] == "AL WATANIAH" and a["produto"] == "Al Wataniah Ameerati EDP 100 ml", a
    assert m["6290362346548"]["marca"] == "LATTAFA" and m["6290362346548"]["produto"] == "Lattafa Asad Elixir EDP 100 ml"
    assert m["6291107455365"]["marca"] == "LATTAFA"
    assert m["6290360378053"]["marca"] == "LIPX"
    # 01/10 (Bruno, "Lipx Sabah EDP 100 ml" com 4 vendedores e o Sabah Al Ward da Al Wataniah com 277): LIPX é revenda —
    # GTIN próprio da ICARBONXX (789…) com 8.710 un. na LIPX e 2.620 na Al Wataniah: a dona é a Al Wataniah mesmo assim
    sb = [L(gtin="7899463112978", un=8710, marca_snap="LIPX", titulo="Perfume Árabe Sabah Al Ward Sugar Feminino 100ml - Original Com Nf",
            linha="Sabah", produto="Lipx Sabah EDP 100 ml", genero="Feminino"),
          L(gtin="7899463112978", un=2620, marca_snap="AL WATANIAH", titulo="Perfume Árabe Sabah Al Ward Sugar Eau De Parfum 100ml",
            linha="Sabah", produto="Lipx Sabah EDP 100 ml", tipo=nubi.TIPO_OUTRA, confianca=nubi.CONF_GTIN_OUTRA, genero="Feminino")]
    assert nubi.mapa_gtin_global(sb)["7899463112978"]["marca"] == "LIPX"            # sem a marcação: quem mais vende
    nubi.definir_revenda(["LIPX"])
    try:
        x = nubi.mapa_gtin_global(sb)["7899463112978"]
        assert x["marca"] == "AL WATANIAH" and x["produto"] == "Al Wataniah Sabah EDP 100 ml", x
        assert nubi.mapa_gtin_global(m_linhas := linhas)["6290360378053"]["marca"] == "LATTAFA"   # Vulcan Feu: a Lattafa tem o GTIN, ganha da LIPX
        so_lipx = [L(gtin="7891559867861", un=590, marca_snap="LIPX", titulo="Musamam White Lipx", linha="Musamam White", produto="Lipx Musamam White EDP 100 ml"),
                   L(gtin="7891559867861", un=1, marca_snap="LIPX", titulo="Musamam", linha="Musamam White", produto="Lipx Musamam White EDP 100 ml")]
        assert "7891559867861" not in nubi.mapa_gtin_global(so_lipx)                  # só a LIPX tem: continua dela (1 marca)
    finally:
        nubi.definir_revenda([])
    nubi.definir_gtin_global(m)
    try:
        df = pd.DataFrame([{"titulo": "Perfume Asad Elixir 100ml Eau De Parfum Original Edp", "gtin": "6290362346548", "un": 1300,
                            "fat": 363000.0, "categoria": "", "marca_anuncio": "LIPX", "vendedor": "ICARBONXX P3", "preco": 369.9},
                           {"titulo": "Perfume Lipx Arabe Shaghaf 100ml", "gtin": "999", "un": 10, "fat": 1000.0, "categoria": "",
                            "marca_anuncio": "LIPX", "vendedor": "X", "preco": 100.0}])
        out = nubi.consolidar(df, "LIPX", {}, info={})
        assert out.at[0, "produto"] == "Lattafa Asad Elixir EDP 100 ml" and out.at[0, "tipo"] == nubi.TIPO_OUTRA, out.iloc[0].to_dict()
        assert out.at[0, "confianca"] == nubi.CONF_GTIN_OUTRA
        assert out.at[1, "linha"] == "Shaghaf", out.at[1, "linha"]            # "Arabe" não é nome de linha
        assert nubi._titulo_canonico(["a b", "a b c", "a b"]) == "a b" and nubi._titulo_canonico(["a b", "a b c"]) == "a b c"
    finally:
        nubi.definir_gtin_global({})
    print("ok test_mesmo_gtin_em_outra_marca_e_o_mesmo_produto")


if __name__ == "__main__":
    test_mesmo_gtin_em_outra_marca_e_o_mesmo_produto()


def test_relatorio_da_dona_traz_o_anuncio_com_a_marca_trocada():
    # 29/09: no relatório da Lattafa, o anúncio da LIPX do mesmo GTIN (mesmo período) entra no Asad Elixir
    import nubi_web as w
    g = {"6290362346548": {"marca": "LATTAFA", "linha": "Asad Elixir", "volume": "100 ml", "tipo": "EDP", "genero": "Masculino",
                           "produto": "Lattafa Asad Elixir EDP 100 ml", "titulo": "Perfume Asad Elixir Lattafa"}}
    nubi.definir_gtin_global(g)
    base = {c: None for c in nubi.CAMPOS_ANUNCIO}

    class R:
        def _eq(self, v): return f"eq.{v}"
        def snapshots(self, marca=None):
            return pd.DataFrame([{"id": 1, "marca": "LATTAFA", "inicio": "2026-08-01", "fim": "2026-09-27"},
                                 {"id": 2, "marca": "LIPX", "inicio": "2026-08-01", "fim": "2026-09-27"},
                                 {"id": 3, "marca": "LIPX", "inicio": "2026-07-01", "fim": "2026-07-31"}])
        def _todos(self, t, q=None):
            assert q["snapshot_id"] == "in.(2)" and q["confianca"] == f"eq.{nubi.CONF_GTIN_OUTRA}", q
            return [dict(base, id=9, snapshot_id=2, titulo="Perfume Asad Elixir 100ml", vendedor="ICARBONXX P3", vendedor_id="77",
                         marca_anuncio="LIPX", gtin="6290362346548", un=1300, fat=363000, preco=369.9, linha="Asad Elixir",
                         tipo=nubi.TIPO_OUTRA, confianca=nubi.CONF_GTIN_OUTRA, produto="Lattafa Asad Elixir EDP 100 ml",
                         volume="100 ml", genero="Masculino", catalogo=True, full=True)]
    try:
        df = pd.DataFrame([dict(base, rid=1, snapshot_id=1, titulo="Perfume Asad Elixir Lattafa", vendedor="HIMALAIA", vendedor_id="5",
                                marca_anuncio="LATTAFA", gtin="6290362346548", un=2800, fat=758000, preco=279.0, linha="Asad Elixir",
                                tipo="EDP", confianca=nubi.CONF_GTIN, produto="Lattafa Asad Elixir EDP 100 ml", volume="100 ml",
                                genero="Masculino")])
        df = nubi.campos_do_arquivo(nubi.preparar(df), "LATTAFA")
        novo, un = w._com_marca_trocada(R(), df, {"inicio": "2026-08-01", "fim": "2026-09-27"}, "LATTAFA")
        assert un == 1300 and len(novo) == 2 and set(novo["produto"]) == {"Lattafa Asad Elixir EDP 100 ml"}
        assert list(novo["tipo"]) == ["EDP", "EDP"] and list(novo["marca_prod"]) == ["Lattafa", "Lattafa"], novo[["tipo", "marca_prod"]]
        # 02/10: o MESMO anúncio (mesmo ID do anúncio) no export da LIPX e no da Lattafa não soma duas vezes
        R._todos_velho = R._todos
        def _com_id(self, t, q=None):
            return [dict(r, bruto={"ID do anúncio": "abc123"}) for r in R._todos_velho(self, t, q)]
        R._todos = _com_id
        df2 = pd.concat([df, df.assign(bruto=[{"ID do anúncio": "abc123"}], vendedor="ICARBONXX P3", un=1300)], ignore_index=True)
        novo2, un2 = w._com_marca_trocada(R(), df2, {"inicio": "2026-08-01", "fim": "2026-09-27"}, "LATTAFA")
        assert un2 == 0 and len(novo2) == 2, (un2, len(novo2))
        R._todos = R._todos_velho
        # na LIPX, a coluna Marca mostra a dona do GTIN
        lipx = nubi.campos_do_arquivo(nubi.preparar(pd.DataFrame(R()._todos("a", {"snapshot_id": "in.(2)", "confianca": f"eq.{nubi.CONF_GTIN_OUTRA}"}))), "LIPX")
        assert lipx.at[0, "marca_prod"] == "Lattafa"
    finally:
        nubi.definir_gtin_global({})
    print("ok test_relatorio_da_dona_traz_o_anuncio_com_a_marca_trocada")


if __name__ == "__main__":
    test_relatorio_da_dona_traz_o_anuncio_com_a_marca_trocada()


def test_anuncio_sem_gtin_herda_pelo_sku_do_vendedor():
    # 29/09 (print do Bruno): ICARBONXX, mesmo título e SKU ASADELIXIR, um anúncio sem GTIN
    nubi.definir_apelidos({})
    nubi.definir_gtin_global({})
    R = lambda t, g, u, v, sku: {"titulo": t, "gtin": g, "un": u, "fat": u * 300.0, "categoria": "", "marca_anuncio": "Lattafa",
                                 "vendedor": v, "vendedor_id": v, "sku": sku, "preco": 300.0}
    df = pd.DataFrame([
        R("Perfume Asad Elixir Lattafa Eau De Parfum 100ml", "6290362346548", 1300, "ICARBONXX", "ASADELIXIR"),
        R("Perfume Asad Elixir Lattafa Eau De Parfum 100ml", "", 740, "ICARBONXX", "asadelixir "),
        R("Perfume Lattafa Khamrah Edp 100ml", "", 50, "OUTRO", "ASADELIXIR"),        # outro vendedor: não herda
        R("Perfume Lattafa Yara Edp 100ml", "", 30, "V3", "6290360593159"),            # SKU que é código de barras
        R("Perfume Lattafa Yara Edp 100ml", "", 5, "V4", "82688")])
    ef = nubi.gtin_efetivo(df)
    assert list(ef) == ["6290362346548", "6290362346548", "", "6290360593159", ""], list(ef)
    out = nubi.consolidar(df, "LATTAFA", {"LATTAFA": {"linhas": [["asad elixir", "Asad Elixir"], ["khamrah", "Khamrah"], ["yara", "Yara"]]}}, info={})
    assert out.at[0, "produto"] == out.at[1, "produto"] == "Lattafa Asad Elixir EDP 100 ml", list(out["produto"])
    assert out.at[1, "confianca"] == nubi.CONF_SKU and out.at[0, "confianca"] == nubi.CONF_GTIN
    assert list(out["gtin"]) == ["6290362346548", "", "", "", ""]            # o GTIN gravado não muda
    assert out.at[2, "produto"].startswith("Lattafa Khamrah")
    print("ok test_anuncio_sem_gtin_herda_pelo_sku_do_vendedor")


if __name__ == "__main__":
    test_anuncio_sem_gtin_herda_pelo_sku_do_vendedor()


def test_foto_do_produto_respeita_o_genero():
    """01/10 (Bruno): "a foto que trouxe é a de mulher, mas o The Kingdom é o de homem"."""
    import meli
    import nubi_web as w
    cat = {"P1": {"nome": "Lattafa The Kingdom Woman Eau de Parfum 100 ml", "foto": "https://x/woman.jpg", "link": "l1"},
           "P2": {"nome": "Lattafa The Kingdom Eau de Parfum Masculino 100 ml", "foto": "https://x/men.jpg", "link": "l2"},
           "P3": {"nome": "Sem foto", "foto": "", "link": ""}}
    meli._produtos_do_gtin = lambda g, n=2: {"6290360598352": ["P1"], "6290360598345": ["P3"], "7891805378189": ["P2"]}.get(g, [])
    meli._produto_catalogo = lambda pid: cat[pid]
    gs = ["6290360598352", "6290360598345", "7891805378189"]
    f = w.foto_do_produto(gs, "Masculino")
    assert f["foto"] == "https://x/men.jpg" and f["genero_confere"] and f["gtin"] == "7891805378189", f
    f = w.foto_do_produto(gs, "Feminino")
    assert f["foto"] == "https://x/woman.jpg" and f["genero_confere"]
    f = w.foto_do_produto(gs, "")                                       # sem gênero: a 1ª com foto
    assert f["foto"] == "https://x/woman.jpg"
    f = w.foto_do_produto(["6290360598352"], "Masculino")               # só tem a de mulher: vem com aviso
    assert f["foto"] == "https://x/woman.jpg" and f["genero_confere"] is False
    assert w.foto_do_produto(["6290360598345"], "Masculino") == {"foto": None}
    print("ok foto genero")


if __name__ == "__main__":
    test_foto_do_produto_respeita_o_genero()
