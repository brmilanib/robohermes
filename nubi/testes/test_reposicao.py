# -*- coding: utf-8 -*-
"""02/10 (Bruno): Estoque → 🔁 Reposição. A venda base é a venda nos dias com estoque (Torino 21: "se eu tenho estoque, vende"),
campeões com +20%, prateleira mínima para quem tem estoque e vende pouco, pedido em faixas cortado pelo caixa, Full dos top."""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import reposicao  # noqa: E402

DIAS = [(date(2026, 9, 7) + timedelta(i)).isoformat() for i in range(25)]


def _dados():
    vendas = {d: {} for d in DIAS}
    est = {}
    for i, d in enumerate(DIAS):
        vendas[d]["CAMPEAO"] = {"un": 10, "valor": 1000.0, "ml": 10}                     # vende todo dia, nunca zera
        vendas[d]["ZERADO"] = {"un": 3 if i >= 22 else 0, "valor": 4200.0 if i >= 22 else 0, "ml": 3 if i >= 22 else 0}
        vendas[d]["LENTO"] = {"un": 1 if i % 6 == 0 else 0, "valor": 50.0 if i % 6 == 0 else 0, "ml": 0}
        vendas[d]["MEIO"] = {"un": 2, "valor": 200.0, "ml": 1}
        if i >= 17:                                                    # o nubi só sabe o estoque dos últimos 8 dias
            est[d] = {"CAMPEAO": 100, "ZERADO": 0 if i < 22 else 5, "LENTO": 30, "MEIO": 10}
    itens = [{"sku": "CAMPEAO", "titulo": "Perfume Campeão 100ml", "disponivel": 30, "transito": 0, "custo": 50},
             {"sku": "ZERADO", "titulo": "Perfume Que Vive Zerado 100ml", "disponivel": 1, "transito": 0, "custo": 800},
             {"sku": "LENTO", "titulo": "Perfume Lento 100ml", "disponivel": 30, "transito": 0, "custo": 20},
             {"sku": "MEIO", "titulo": "Perfume Meio 100ml", "disponivel": 0, "transito": 5, "custo": 60}]
    return itens, est, vendas


def test_venda_nos_dias_com_estoque():
    itens, est, vendas = _dados()
    r = reposicao.calcular(itens, est, vendas)
    por = {l["sku"]: l for l in r["campeoes"] + r["pedido"]}
    z = por["ZERADO"]
    # média de 25 dias = 9/25 = 0,36; com estoque só nos 3 últimos dias = 3/dia, peso 3/8 → 0,36 × 5/8 + 3 × 3/8 = 1,35
    assert z["media_dia"] == 0.36 and z["dia_com_estoque"] == 3.0 and z["venda_base"] == 1.35, z
    assert z["ruptura_dias"] == 5 and z["classe"] == "A", z
    c = por["CAMPEAO"]
    assert c["venda_base"] == 10 and c["ruptura_dias"] == 0
    # nível = (10 × 12 + 1,65 × 1,3 × √120) × 1,2 = 172,2 → 173 (sempre para cima) → compra 143
    assert c["nivel_max"] == 173 and c["compra"] == 143, c


def test_prateleira_minima_e_classe_c():
    itens, est, vendas = _dados()
    r = reposicao.calcular(itens, est, vendas)
    lento = [l for l in r["campeoes"] + r["pedido"] if l["sku"] == "LENTO"]
    assert not lento                                                    # classe C com estoque: não entra no pedido
    itens[2]["disponivel"] = 0
    r = reposicao.calcular(itens, est, vendas)
    l = next(l for l in r["pedido"] if l["sku"] == "LENTO")
    assert l["intermitente"] and l["nivel_max"] == 3 and l["compra"] == 3, l   # teve estoque e vende pouco: 0,25/dia × 12 dias, sem segurança


def test_faixas_caixa_manual_e_full():
    itens, est, vendas = _dados()
    r = reposicao.calcular(itens, est, vendas, {"caixa": 8000})
    assert [f["faixa"] for f in r["faixas"]][0] == 1
    assert r["pedido"][0]["sku"] in ("CAMPEAO", "ZERADO") and r["pedido"][0]["faixa"] == 1
    cabe = [l["sku"] for l in r["pedido"] if l["cabe_no_caixa"]]
    assert r["resumo"]["cabe_no_caixa"] <= 8000 and len(cabe) < len(r["pedido"]), r["resumo"]
    acum = [l["acumulado"] for l in r["pedido"]]
    assert acum == sorted(acum)
    r2 = reposicao.calcular(itens, est, vendas, {}, manuais={"ZERADO": "anúncio voltando"})
    assert all(l["sku"] != "ZERADO" for l in r2["pedido"]) and r2["manuais"][0]["manual"] == "anúncio voltando"
    f = {x["sku"]: x for x in r["full"]}
    # MEIO vende metade no ML: Full = 1/dia × 1,0 (classe B não muda o Full: campeao vale para o Full dos top) × 1,2 × 21
    assert f["CAMPEAO"]["full_alvo"] == 252 and f["CAMPEAO"]["mandar_agora"] == 30, f["CAMPEAO"]
    assert f["MEIO"]["reserva"] == 12 and f["MEIO"]["mandar_agora"] == 0, f["MEIO"]


def test_mercado_do_produto():
    ans = [{"titulo": "Torino 21 Xerjoff 100ml", "un": 30, "fat": 45000, "preco": 1500, "vendedor": "A"},
           {"titulo": "Torino 21 Xerjoff 100ml", "un": 10, "fat": 14000, "preco": 1400, "vendedor": "B"},
           {"titulo": "Torino 21 Xerjoff 100ml", "un": 0, "fat": 0, "preco": 1300, "vendedor": "C"}]
    m = reposicao.mercado_do_produto("Torino 21", ans, 20, lambda t, xs: xs)
    assert m == {"un_dia": 2.0, "anuncios": 3, "vendedores": 3, "preco_min": 1400.0, "preco_lider": 1500.0,
                 "lider_un_dia": 1.5, "preco_medio": 1475.0}, m
    assert reposicao.mercado_do_produto("x", ans, 20, lambda t, xs: []) is None


if __name__ == "__main__":
    test_venda_nos_dias_com_estoque()
    test_prateleira_minima_e_classe_c()
    test_faixas_caixa_manual_e_full()
    test_mercado_do_produto()
    print("ok reposição")
