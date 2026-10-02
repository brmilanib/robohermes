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
    # Full = venda do ML × 70% (30% do ML sai do galpão) × 1,2 × 21 dias; galpão = outras lojas + 30% do ML, por 12 dias
    assert f["CAMPEAO"]["full_alvo"] == 177 and f["CAMPEAO"]["reserva"] == 36 and f["CAMPEAO"]["mandar_agora"] == 0, f["CAMPEAO"]
    assert f["MEIO"]["full_alvo"] == 18 and f["MEIO"]["reserva"] == 16 and f["MEIO"]["mandar_agora"] == 0, f["MEIO"]
    itens[0]["disponivel"] = 100
    f2 = {x["sku"]: x for x in reposicao.calcular(itens, est, vendas)["full"]}
    assert f2["CAMPEAO"]["mandar_agora"] == 64                        # 100 − 36 que ficam no galpão


def test_margem_pos_ads():
    """02/10 (Bruno: "prefiro vender menos com margem saudável, 18–20% já tirando o ADS")."""
    itens, est, vendas = _dados()
    base = {l["sku"]: l for l in reposicao.calcular(itens, est, vendas)["pedido"]}
    r = reposicao.calcular(itens, est, vendas, margens={"CAMPEAO": 3.8, "ZERADO": 20.7, "MEIO": 14.0})
    por = {l["sku"]: l for l in r["pedido"]}
    c = por["CAMPEAO"]
    assert c["margem"] == "ruim" and c["faixa"] == 4 and c["nivel_max"] == 70 and c["compra"] == 40, c   # só a semana: 10 × 7
    assert por["ZERADO"]["margem"] == "ok" and por["ZERADO"]["nivel_max"] == base["ZERADO"]["nivel_max"]
    assert r["pedido"][0]["sku"] == "ZERADO" and r["pedido"][-1]["sku"] == "CAMPEAO"              # lucro primeiro, margem ruim no fim
    assert r["resumo"]["margem_ruim"] == 1 and r["resumo"]["meta_margem"] == 18.0
    # entre 10% e a meta: campeão sem o +20% e com a segurança da classe B
    r3 = reposicao.calcular(itens, est, vendas, margens={"CAMPEAO": 15.0})
    c3 = next(l for l in r3["pedido"] if l["sku"] == "CAMPEAO")
    assert c3["margem"] == "abaixo" and c3["nivel_max"] == 135, c3                               # 120 + 1,0 × 1,3 × √120 = 134,2 → 135


def test_mercado_do_produto():
    ans = [{"titulo": "Torino 21 Xerjoff 100ml", "un": 30, "fat": 45000, "preco": 1500, "vendedor": "A"},
           {"titulo": "Torino 21 Xerjoff 100ml", "un": 10, "fat": 14000, "preco": 1400, "vendedor": "B"},
           {"titulo": "Torino 21 Xerjoff 100ml", "un": 0, "fat": 0, "preco": 1300, "vendedor": "C"}]
    m = reposicao.mercado_do_produto("Torino 21", ans, 20, lambda t, xs: xs)
    assert m == {"un_dia": 2.0, "anuncios": 3, "vendedores": 3, "preco_min": 1400.0, "preco_lider": 1500.0,
                 "lider_un_dia": 1.5, "preco_medio": 1475.0}, m
    assert reposicao.mercado_do_produto("x", ans, 20, lambda t, xs: []) is None


def test_ranqueamento_e_alertas_de_preco():
    """02/10 (Bruno: "voltou de ruptura ou é novo: vende 30–50 unidades com margem baixa para ranquear; caiu a venda, baixa um
    pouco o preço; voltou a vender, sobe")."""
    itens, est, vendas = _dados()
    r = reposicao.calcular(itens, est, vendas, margens={"ZERADO": 5.0})
    z = next(l for l in r["pedido"] if l["sku"] == "ZERADO")
    # ficou 5 dias zerado e voltou em 29/09: ranqueando com 9 vendidos de 40; margem baixa não manda para o fim da fila
    assert z["ranqueando"] == {"desde": "2026-09-29", "vendidos": 9, "meta": 40, "motivo": "voltou de ruptura"}, z["ranqueando"]
    assert z["faixa"] == 1 and z["nivel_max"] == 29, z               # faltam 31, limitado a 3 semanas: 1,35 × 21 = 28,4 → 29
    assert any(l["sku"] == "ZERADO" for l in r["precos"])
    # marcado na mão
    r = reposicao.calcular(itens, est, vendas, ranque={"MEIO": "2026-09-25"})
    m = next(l for l in r["pedido"] + r["precos"] if l["sku"] == "MEIO")
    assert m["ranqueando"]["motivo"] == "marcado na mão" and m["ranqueando"]["vendidos"] == 14, m["ranqueando"]
    # venda caindo: CAMPEAO vendia 10/dia e na última semana 4/dia (com estoque) → baixar um pouco o preço
    for d in list(vendas)[-7:]:
        vendas[d]["CAMPEAO"] = {"un": 4, "valor": 400.0, "ml": 4}
    r = reposicao.calcular(itens, est, vendas)
    c = next(l for l in r["precos"] if l["sku"] == "CAMPEAO")
    assert c["alerta"]["tipo"] == "baixar" and c["alerta"]["r7"] == 4 and c["alerta"]["antes"] == 10, c["alerta"]
    assert r["precos"][0]["sku"] == "CAMPEAO"                          # baixar o preço vem primeiro
    # venda subindo com margem abaixo da meta → subir o preço
    for d in list(vendas)[-7:]:
        vendas[d]["CAMPEAO"] = {"un": 15, "valor": 1500.0, "ml": 15}
    r = reposicao.calcular(itens, est, vendas, margens={"CAMPEAO": 12.0})
    c = next(l for l in r["precos"] if l["sku"] == "CAMPEAO")
    assert c["alerta"]["tipo"] == "subir", c["alerta"]
    # com margem na meta, subir a venda não gera alerta
    r = reposicao.calcular(itens, est, vendas, margens={"CAMPEAO": 22.0})
    assert not any(l["sku"] == "CAMPEAO" for l in r["precos"])


def test_dinheiro_parado_e_meta():
    """02/10 (Bruno: "muito dinheiro parado em B e C; quero B e C saudáveis mas com menos; meta 2 a 2,5 milhões com 18–20%")."""
    itens, est, vendas = _dados()
    itens[2]["disponivel"] = 300                                       # LENTO (curva C): 300 un. × R$ 20 = R$ 6.000 parados
    r = reposicao.calcular(itens, est, vendas, margens={"CAMPEAO": 20.0, "MEIO": 10.0})
    p = {x["classe"]: x for x in r["parado"]}
    assert p["C"]["custo"] == 6000 and p["C"]["acima_do_nivel"] == 5940, p["C"]                # nível da prateleira: 3 un.
    assert r["sobras"][0]["sku"] == "LENTO" and r["sobras"][0]["acima_valor"] == 5940
    rs = r["resumo"]
    assert rs["parado_bc"] >= 6000 and rs["meta_fat"] == 2_000_000
    # faturamento de 25 dias levado a 30; margem média ponderada pelo faturamento dos que têm margem
    tot = sum(sum(v["valor"] for v in d.values()) for d in vendas.values())
    assert rs["fat_mes"] == round(tot / 25 * 30, 2)
    assert rs["margem_media"] == round((25000 * 20 + 5000 * 10) / 30000, 2), rs["margem_media"]


def test_mercado_pelo_nome_do_produto():
    """02/10 (conferência do cron): o título longo do SKU casa com o PRODUTO consolidado do Explorador, nos dois sentidos."""
    import nubi_web as w
    ans = [{"produto": "Lattafa Yara EDP 100 ml", "tipo": "EDP", "un": 8000, "fat": 1_400_000, "preco": 180, "vendedor": "A"},
           {"produto": "Lattafa Asad Elixir EDP 100 ml", "tipo": "EDP", "un": 2800, "fat": 640_000, "preco": 230, "vendedor": "B"},
           {"produto": "Lattafa Asad Elixir Decant 5 ml", "tipo": "Decant", "un": 50, "fat": 2_000, "preco": 40, "vendedor": "C"},
           {"produto": "Maison Alhambra Delilah Viola EDP 100 ml", "tipo": "EDP", "un": 40, "fat": 11_000, "preco": 290, "vendedor": "D"},
           {"produto": "Armaf Club de Nuit Intense Woman EDP 105 ml", "tipo": "EDP", "un": 1450, "fat": 350_000, "preco": 246, "vendedor": "E"},
           {"produto": "Armaf Club de Nuit Intense Man EDT 105 ml", "tipo": "EDT", "un": 25000, "fat": 5_000_000, "preco": 221, "vendedor": "F"}]
    m = lambda t, marca="LATTAFA", vocab=frozenset(): reposicao.mercado_por_produto(t, ans, 30, w._tokens_produto, w._tipo_tok, marca, vocab)
    a = m("Perfume Asad Elixir Lattafa 100 Ml Perfume Árabe Masculino Original")
    assert a["produto"] == "Lattafa Asad Elixir EDP 100 ml" and a["un_dia"] == round(2800 / 30, 2), a      # o decant não entra
    assert m("Perfume Feminino Yara Elixir Lattafa Eau De Parfum 100 Ml") is None, "Yara Elixir não é o Yara"
    assert m("Perfume Feminino Delilah Blanc Maison Alhambra Eau De Parfum 100ml", "MAISON ALHAMBRA") is None
    w2 = m("Perfume Club De Nuit Woman Armaf Eau De Parfum 105ml", "ARMAF")
    assert w2["produto"] == "Armaf Club de Nuit Intense Woman EDP 105 ml", w2                                   # 5 palavras: falta 1
    assert m("Perfume Club De Nuit Intense Man Armaf Eau De Parfum 105ml", "ARMAF") is None                     # EDP × EDT
    assert m("Perfume Lattafa Yara Candy Eau De Parfum 100 Ml", vocab=frozenset({"candy"})) is None             # candy é outro produto


def test_mercado_pelo_gtin():
    """02/10 (Bruno: "mas o GTIN é diferente, né"): o Explorador junta Yara, Yara Elixir e Yara Moi no mesmo nome de produto;
    o GTIN separa."""
    ans = [{"produto": "Lattafa Yara EDP 100 ml", "gtin": "6290360591247", "un": 8000, "fat": 1_400_000, "preco": 180, "vendedor": "A"},
           {"produto": "Lattafa Yara EDP 100 ml", "gtin": "6290362346531", "un": 600, "fat": 132_000, "preco": 220, "vendedor": "B"},
           {"produto": "Lattafa Yara EDP 100 ml", "gtin": "6290362346531", "un": 300, "fat": 69_000, "preco": 230, "vendedor": "C"},
           {"produto": "Lattafa Yara EDP 100 ml", "gtin": "6290360591421", "un": 90, "fat": 17_000, "preco": 190, "vendedor": "D"}]
    m = reposicao.mercado_por_gtin("6290362346531", ans, 30)          # Yara Elixir
    assert m["un_dia"] == 30.0 and m["anuncios"] == 2 and m["preco_lider"] == 220 and m["gtin"] == "6290362346531", m
    assert reposicao.mercado_por_gtin("6290360591421", ans, 30)["un_dia"] == 3.0                 # Yara Moi
    assert reposicao.mercado_por_gtin("", ans, 30) is None and reposicao.mercado_por_gtin("123", ans, 30) is None
    # o mesmo perfume com mais de um GTIN (Ferrari: 13/dia pelo meu GTIN, 36/dia pelo nome) → vale o nome
    g, n = {"un_dia": 13.2, "gtin": "7795666906867"}, {"un_dia": 35.7, "produto": "Ferrari Black EDT 125 ml"}
    assert reposicao.escolher_mercado(g, n) == {"un_dia": 35.7, "produto": "Ferrari Black EDT 125 ml", "casado_por": "nome+gtin", "gtin": "7795666906867"}
    # o nome junta outro produto (Yara Moi = 3% do "Yara") → vale o GTIN
    assert reposicao.escolher_mercado({"un_dia": 8.9, "gtin": "x"}, {"un_dia": 273.0})["un_dia"] == 8.9
    assert reposicao.escolher_mercado(None, n)["casado_por"] == "nome" and reposicao.escolher_mercado(None, None) is None
    # vários GTINs do mesmo SKU (cadastro do UpSeller + meu anúncio no Explorador): soma os dois
    m = reposicao.mercado_por_gtin({"6290362346531", "6290360591421"}, ans, 30)
    assert m["un_dia"] == 33.0 and m["anuncios"] == 3 and m["gtin"] == "6290360591421,6290362346531", m
    assert reposicao.mercado_por_gtin({"6290362346531"}, ans, 30)["un_dia"] == 30.0


def test_perfume_arabe_nao_e_marca():
    """02/10 (Bruno: "não tem nada a ver essa marca Perfume Árabe"): palavra de anúncio nunca vira marca."""
    from categorias import marca_do_titulo
    conh = {"PERFUMEARABE": "Perfume Arabe", "LATTAFA": "Lattafa", "ALWATANIAH": "Al Wataniah"}
    assert marca_do_titulo("Perfume Árabe Original Alta Fixação 100ml", conh) is None
    assert marca_do_titulo("Perfume Árabe Bareeq Al Wataniah EDP 100ml", conh) == "Al Wataniah"
    assert marca_do_titulo("Perfume Arabe Yara Lattafa", conh) == "Lattafa"


def test_cadastro_upseller():
    """02/10: Produtos → Exportar do UpSeller -> GTIN e custo de compra por SKU."""
    import io, openpyxl
    from estoque import ler_cadastro_produtos
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["SKU", "Título", "Código de Barras", "Custo de Compra", "Categorias", "Marca"])
    ws.append(["FERRARI-BLACK-125", "Ferrari Black EDT 125ml", "8002135111974", 89.9, "Perfumes", "Ferrari"])
    ws.append(["SEM-GTIN", "Kit", "", "", "", ""])
    b = io.BytesIO(); wb.save(b)
    c = ler_cadastro_produtos(b.getvalue())
    f = [v for v in c.values() if v["sku"] == "FERRARI-BLACK-125"][0]
    assert f["gtin"] == "8002135111974" and f["custo_compra"] == 89.9, c
    assert [v for v in c.values() if v["sku"] == "SEM-GTIN"][0]["gtin"] is None, c


if __name__ == "__main__":
    test_venda_nos_dias_com_estoque()
    test_prateleira_minima_e_classe_c()
    test_faixas_caixa_manual_e_full()
    test_mercado_do_produto()
    test_margem_pos_ads()
    test_ranqueamento_e_alertas_de_preco()
    test_dinheiro_parado_e_meta()
    test_mercado_pelo_nome_do_produto()
    test_mercado_pelo_gtin()
    test_cadastro_upseller()
    test_perfume_arabe_nao_e_marca()
    print("ok reposição")
