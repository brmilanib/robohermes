# -*- coding: utf-8 -*-
"""28/09 (pedido do Bruno): vendas por anúncio do UpSeller × estoque = zerados, mais vendidos e preciso comprar;
e o DeepSeek só nas 2 análises do dia."""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import estoque  # noqa: E402
import ia  # noqa: E402


def _xlsx(linhas):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Produtos", "Loja", "SKU Principal", "ID do Anúncios", "Pedidos Válidos", "Unidades Vendidas", "Valor de Vendas", "Preço Médio"])
    for x in linhas:
        ws.append(x)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


VENDAS = [("Perfume A", "PUREHOME[Mercado Libre BR]", "A-100", "MLB1", 60, 60, 12000, 200),
          ("Perfume A", "AURA SCENT[Mercado Libre BR]", "A-100", "MLB2", 30, 30, 6000, 200),
          ("Perfume B", "Purehome[Shopee]", "B-100", "S1", 30, 30, 3000, 100),
          ("Perfume C", "PUREHOME[Mercado Libre BR]", "C-100", "MLB3", 3, 3, 300, 100),
          ("Perfume D", "PUREHOME[Mercado Libre BR]", "D-100", "MLB4", 15, 15, 1500, 100)]
ESTOQUE = [{"sku": "A-100", "titulo": "A", "disponivel": 10, "atual": 10, "transito_compra": 20, "estoque_min": 0},   # 3/dia, dura 10 d
           {"sku": "B-100", "titulo": "B", "disponivel": 100, "atual": 100, "transito_compra": 0, "estoque_min": 0},  # 1/dia, dura 100 d
           {"sku": "C-100", "titulo": "C", "disponivel": 0, "atual": 0, "transito_compra": 0, "estoque_min": 0},     # zerado com venda
           {"sku": "E-100", "titulo": "E", "disponivel": 0, "atual": 0, "transito_compra": 0, "estoque_min": 0}]     # zerado sem venda


def test_le_o_relatorio_e_o_periodo():
    v = estoque.ler_vendas(_xlsx(VENDAS))
    assert len(v) == 5 and v[0]["sku"] == "A-100" and v[0]["unidades"] == 60.0 and v[1]["loja"].startswith("AURA")
    assert estoque.periodo_vendas("Vendas_por_Produtos_20260829-20260927_20260928205649.xlsx") == ("2026-08-29", "2026-09-27", 30)
    try:
        estoque.ler_vendas(_xlsx([]))
        raise AssertionError("aceitou planilha sem vendas")
    except estoque.ErroEstoque:
        pass


def test_listas():
    ls = estoque.listas(ESTOQUE, estoque.ler_vendas(_xlsx(VENDAS)), dias=30)
    assert [r["sku"] for r in ls["mais_vendidos"]][:2] == ["A-100", "B-100"]
    a = next(r for r in ls["mais_vendidos"] if r["sku"] == "A-100")
    assert a["vendidos"] == 90 and a["venda_dia"] == 3 and a["cobertura_dias"] == 10 and a["lojas"] == ["AURA SCENT", "PUREHOME"]
    comprar = {r["sku"]: r for r in ls["comprar"]}
    assert set(comprar) == {"A-100", "C-100", "D-100"}                      # B dura 100 dias
    assert comprar["A-100"]["sugerido"] == 60                               # 3/dia × 30 − 10 − 20
    assert comprar["D-100"]["no_estoque"] is False and ls["vendas_sem_estoque"] == 1
    assert [r["sku"] for r in ls["zerados"]] == ["C-100", "E-100"] and ls["zerados_com_venda"] == 1
    assert ls["comprar"][0]["cobertura_dias"] == 0                          # o que já acabou vem primeiro
    assert "NÃO invente" in estoque.pedido_analise(ls) and "A-100" in estoque.pedido_analise(ls)


def test_deepseek_so_nas_analises_do_dia():
    import os
    os.environ.setdefault("DEEPSEEK_API_KEY", "x")
    assert ia.tem("deepseek") is False
    with ia.deepseek_liberado():
        assert ia.tem("deepseek") is True
    assert ia.tem("deepseek") is False
    try:
        ia.perguntar("oi", web=False, qual="deepseek")
        raise AssertionError("DeepSeek respondeu fora das análises do dia")
    except ia.SemIA:
        pass
    assert estoque.ORDEM_IA == (("ollama", None, "Estoquista (gpt-oss)"),)   # importação do estoque: só a grátis


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
