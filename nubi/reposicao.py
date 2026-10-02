# -*- coding: utf-8 -*-
"""
🔁 Reposição (02/10, Bruno: "uma inteligência comigo nesse estoque: focar nos campeões, não deixar dar ruptura, usar os
dados do mercado do Explorador; compro toda semana e o caixa é limitado").

Só conta (sem IA), a partir de:
- a venda por SKU de cada dia (UpSeller, `vendas_anuncio_dia|AAAA-MM-DD`);
- o estoque de cada dia (a última atualização do dia, `estoque_itens`);
- o estoque de hoje (disponível, em trânsito, custo médio);
- o mercado do produto no Explorador (quanto o mercado inteiro vende por dia e a que preço), quando casado.

REGRAS (combinadas com o Bruno em 02/10, no doc "Estudo de estoque"):
1. Venda base = a venda nos dias em que TINHA estoque. A média simples conta como zero os dias zerados e esconde quem mais
   falta (Bruno: "Torino 21 ontem vendeu 3; se eu tenho estoque, vende"). Peso da venda com estoque = dias com estoque
   conhecidos ÷ 8 (até 1); o resto, a média do período.
2. Nível máximo = venda base × (semana + prazo) + segurança; segurança = z × 1,3 × √(venda base × (semana + prazo)), z por
   classe ABC (A 1,65 · B 1,28 · C 0,84). A segurança NÃO usa a variação diária (os dias zerados a inflam).
3. Campeões (classe A) com cobertura 20% maior (Bruno: "vou usar mais o Full, a venda vai ser maior").
4. Quem teve estoque e mesmo assim vende em poucos dias: prateleira mínima (1 a 3 un.), não profundidade.
5. Compra = nível máximo − disponível − em trânsito (nunca negativa). Classe C só se estiver zerada.
6. Pedido em faixas para o caixa: 1 = campeões que acabam antes da próxima entrega; 2 = classe B que acaba antes;
   3 = campeões completando o nível; 4 = o resto. Dentro da faixa, quem fatura mais por dia primeiro.
7. Full: os 10 que mais faturam vão com 3 semanas da venda do Mercado Livre + 20%; no galpão fica a reserva das outras lojas.
"""
import math

SEMANA = 7
PRAZO = 5
CAMPEAO = 1.2
Z = {"A": 1.65, "B": 1.28, "C": 0.84}
DIAS_FULL = 21
TOP_FULL = 10


def _chave(sku):
    import estoque
    return estoque._chave(sku or "")


def classes_abc(fat):
    """{sku: faturamento} -> {sku: 'A'|'B'|'C'} (A até 80% do faturamento, B até 95%)."""
    tot = sum(v for v in fat.values() if v > 0) or 1.0
    out, ac = {}, 0.0
    for k, v in sorted(fat.items(), key=lambda kv: -kv[1]):
        if v <= 0:
            continue
        out[k] = "A" if ac < 0.8 * tot else "B" if ac < 0.95 * tot else "C"
        ac += v
    return out


def calcular(itens, estoque_dia, vendas_dia, cfg=None, mercado=None, manuais=None):
    """itens: [{sku, titulo, disponivel, transito, custo}] (estoque de hoje); estoque_dia: {dia: {chave: disponível}};
    vendas_dia: {dia: {chave: {un, valor, ml}}} (ml = unidades vendidas no Mercado Livre); cfg: prazo, semana, campeao,
    caixa; mercado: {chave: {...}}; manuais: {chave: nota} (decide na mão, fora do pedido)."""
    cfg = dict({"prazo": PRAZO, "semana": SEMANA, "campeao": CAMPEAO, "caixa": None}, **(cfg or {}))
    mercado, manuais = mercado or {}, manuais or {}
    dias = sorted(vendas_dia)
    n = len(dias) or 1
    T = cfg["semana"] + cfg["prazo"]
    tot = {}
    for d in dias:
        for k, v in vendas_dia[d].items():
            t = tot.setdefault(k, {"un": 0.0, "valor": 0.0, "ml": 0.0, "dias_venda": 0})
            t["un"] += v.get("un") or 0
            t["valor"] += v.get("valor") or 0
            t["ml"] += v.get("ml") or 0
            t["dias_venda"] += 1 if (v.get("un") or 0) > 0 else 0
    abc = classes_abc({k: t["valor"] for k, t in tot.items()})
    dias_est = sorted(estoque_dia)
    linhas = []
    for it in itens:
        k = _chave(it.get("sku"))
        t = tot.get(k, {"un": 0.0, "valor": 0.0, "ml": 0.0, "dias_venda": 0})
        disp = max(0.0, float(it.get("disponivel") or 0))
        trans = max(0.0, float(it.get("transito") or 0))
        custo = it.get("custo")
        custo = float(custo) if custo not in (None, "") and float(custo) > 0 else None
        md = t["un"] / n
        # 1. venda nos dias com estoque (só onde o estoque do dia é conhecido)
        dc_un, dc_dias, ruptura = 0.0, 0, 0
        for i, d in enumerate(dias):
            if d not in estoque_dia:
                continue
            ant = dias_est[dias_est.index(d) - 1] if d in dias_est and dias_est.index(d) > 0 else d
            vend = (vendas_dia.get(d, {}).get(k) or {}).get("un") or 0
            tinha = (estoque_dia.get(ant, {}).get(k) or 0) > 0 or (estoque_dia[d].get(k) or 0) > 0 or vend > 0
            if tinha:
                dc_dias += 1
                dc_un += vend
            elif t["un"] > 0:
                ruptura += 1
        dc = dc_un / dc_dias if dc_dias else None
        peso = min(1.0, dc_dias / 8)
        base = max(md, (dc * peso + md * (1 - peso)) if dc is not None else md)
        classe = abc.get(k, "-")
        preco = t["valor"] / t["un"] if t["un"] else None
        ml_share = t["ml"] / t["un"] if t["un"] else 1.0
        intermit = t["un"] > 0 and t["dias_venda"] / n < 0.3 and dc_dias >= 5 and (dc or 0) < 0.5
        mx = 0
        if t["un"] > 0:
            if intermit:
                mx = max(1, math.ceil(base * T)) + (1 if classe == "A" else 0)
            else:
                seg = Z.get(classe, Z["C"]) * 1.3 * math.sqrt(base * T)
                mx = base * T + seg
                if classe == "A":
                    mx *= cfg["campeao"]
                mx = math.ceil(mx)
        compra = max(0, math.ceil(mx - disp - trans)) if t["un"] > 0 else 0
        if classe == "C" and disp + trans > 0:
            compra = 0
        motivo_fora = None
        if k in manuais:
            motivo_fora, compra = manuais[k] or "decido na mão", 0
        cobertura = (disp + trans) / base if base else None
        m = mercado.get(k)
        linhas.append({
            "sku": it.get("sku"), "chave": k, "titulo": it.get("titulo") or "", "classe": classe,
            "disponivel": disp, "transito": trans, "custo": custo, "preco": round(preco, 2) if preco else None,
            "vendas_un": t["un"], "vendas_valor": round(t["valor"], 2), "dias_venda": t["dias_venda"],
            "media_dia": round(md, 2), "dia_com_estoque": round(dc, 2) if dc is not None else None, "dias_com_estoque": dc_dias,
            "venda_base": round(base, 2), "ruptura_dias": ruptura, "intermitente": intermit,
            "fat_dia": round(base * preco, 2) if preco else 0.0, "ml_share": round(ml_share, 3),
            "nivel_max": mx, "compra": compra, "compra_valor": round(compra * custo, 2) if custo and compra else 0.0,
            "sem_custo": compra > 0 and not custo, "cobertura_dias": round(cobertura, 1) if cobertura is not None else None,
            "manual": motivo_fora, "mercado": m,
            "share_mercado": round(base / m["un_dia"], 3) if m and m.get("un_dia") else None,
        })
    # 6. faixas
    for l in linhas:
        if not l["compra"]:
            l["faixa"] = None
            continue
        acaba = l["cobertura_dias"] is None or l["cobertura_dias"] < T
        l["faixa"] = (1 if l["classe"] == "A" and acaba else 2 if l["classe"] == "B" and acaba
                      else 3 if l["classe"] == "A" else 4)
    pedido = sorted([l for l in linhas if l["faixa"]], key=lambda l: (l["faixa"], -l["fat_dia"]))
    ac = 0.0
    caixa = cfg.get("caixa")
    for l in pedido:
        ac += l["compra_valor"]
        l["acumulado"] = round(ac, 2)
        l["cabe_no_caixa"] = caixa is None or ac <= caixa
    faixas = []
    for f, nome in ((1, "Campeões que acabam antes da próxima entrega"), (2, "Classe B que acaba antes da próxima entrega"),
                    (3, "Campeões completando o nível"), (4, "O resto")):
        xs = [l for l in pedido if l["faixa"] == f]
        if xs:
            faixas.append({"faixa": f, "nome": nome, "skus": len(xs), "unidades": sum(l["compra"] for l in xs),
                           "valor": round(sum(l["compra_valor"] for l in xs), 2), "acumulado": xs[-1]["acumulado"]})
    # 7. Full: os 10 que mais faturam
    full = []
    for l in sorted([l for l in linhas if l["vendas_valor"] > 0], key=lambda l: -l["vendas_valor"])[:TOP_FULL]:
        ml_dia = l["venda_base"] * l["ml_share"]
        alvo = math.ceil(ml_dia * cfg["campeao"] * DIAS_FULL)
        reserva = math.ceil(l["venda_base"] * (1 - l["ml_share"]) * T)
        full.append({"sku": l["sku"], "titulo": l["titulo"], "ml_dia": round(ml_dia, 2), "full_alvo": alvo, "reserva": reserva,
                     "disponivel": l["disponivel"], "transito": l["transito"],
                     "mandar_agora": int(min(alvo, max(0, l["disponivel"] - reserva))), "manual": l["manual"]})
    a = [l for l in linhas if l["classe"] == "A"]
    resumo = {
        "dias_vendas": n, "de": dias[0] if dias else None, "ate": dias[-1] if dias else None,
        "dias_estoque": len(dias_est), "pedido_valor": round(ac, 2), "pedido_skus": len(pedido),
        "campeoes": len(a), "campeoes_zerados": sum(1 for l in a if l["disponivel"] + l["transito"] <= 0),
        "campeoes_ruptura": sum(1 for l in a if l["ruptura_dias"] > 0),
        "sem_custo": sum(1 for l in pedido if l["sem_custo"]), "caixa": caixa,
        "cabe_no_caixa": round(sum(l["compra_valor"] for l in pedido if l["cabe_no_caixa"]), 2) if caixa else None,
    }
    return {"cfg": cfg, "resumo": resumo, "faixas": faixas, "pedido": pedido, "full": full,
            "campeoes": sorted(a, key=lambda l: -l["vendas_valor"]),
            "manuais": [l for l in linhas if l["manual"]]}


def mercado_do_produto(titulo, anuncios, dias, casar):
    """O mercado de um SKU meu no card da marca no Explorador: anúncios do mesmo produto (casados pelo título, mesmo volume e
    tipo), quanto vendem por dia somados e a que preço. `casar(titulo, anuncios)` devolve os anúncios do mesmo produto."""
    xs = casar(titulo, anuncios)
    if not xs or not dias:
        return None
    un = sum(float(a.get("un") or 0) for a in xs)
    com = [a for a in xs if float(a.get("un") or 0) > 0 and a.get("preco")]
    lider = max(com, key=lambda a: float(a.get("un") or 0)) if com else None
    return {"un_dia": round(un / dias, 2), "anuncios": len(xs), "vendedores": len({a.get("vendedor") for a in xs}),
            "preco_min": round(min(float(a["preco"]) for a in com), 2) if com else None,
            "preco_lider": round(float(lider["preco"]), 2) if lider else None,
            "lider_un_dia": round(float(lider["un"]) / dias, 2) if lider else None,
            "preco_medio": round(sum(float(a.get("fat") or 0) for a in xs) / un, 2) if un else None}
