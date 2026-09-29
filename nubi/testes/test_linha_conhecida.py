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
    assert out.at[3, "tipo"] == nubi.TIPO_OUTRA                              # contratipo continua outra marca
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
