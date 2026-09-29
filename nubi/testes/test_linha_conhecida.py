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
