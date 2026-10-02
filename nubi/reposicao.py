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
   classe ABC (A 1,65 · B 1,0 · C 0,5: o dinheiro vai para a curva A; B e C saudáveis mas enxutas). A segurança NÃO usa a variação diária (os dias zerados a inflam).
3. Campeões (classe A) com cobertura 20% maior (Bruno: "vou usar mais o Full, a venda vai ser maior").
4. Quem teve estoque e mesmo assim vende em poucos dias: prateleira mínima (1 a 3 un.), não profundidade.
5. Compra = nível máximo − disponível − em trânsito (nunca negativa). Classe C só se estiver zerada.
6. Pedido em faixas para o caixa: 1 = campeões que acabam antes da próxima entrega; 2 = classe B que acaba antes;
   3 = campeões completando o nível; 4 = o resto. Dentro da faixa, quem fatura mais por dia primeiro.
7. Full: os 10 que mais faturam vão com 3 semanas da venda do Mercado Livre + 20%; no galpão fica a reserva das outras lojas
   (Amazon, Shopee, TikTok) E uma parte do próprio Mercado Livre (padrão 30%): o ML pede para despachar do galpão quando o
   frete daqui é mais rápido que o do Full.
8. (02/10, Bruno: "não quero ser campeão vendendo com margem baixa; prefiro vender menos com margem saudável, 18–20% já
   tirando o ADS") margem pós ADS do SKU (Curva ABC do Gestor Seller, `mpa_pct`): na meta ou acima = tratamento de campeão;
   entre 10% e a meta = repõe sem o +20%; abaixo de 10% (ou prejuízo) = só a semana, sem segurança, fim da fila e aviso
   "rever preço/custo". Dentro da faixa, a ordem é por LUCRO por dia (venda × preço × margem), não por faturamento.
10. (02/10, Bruno: "anúncio que volta de ruptura ou é novo precisa vender umas 30–50 unidades com preço mais baixo para
   ranquear; depois sobe o preço aos poucos; quando a venda cai, baixa um pouco; voltou a vender, sobe") RANQUEAMENTO:
   voltou de ruptura (≥ 2 dias zerado e o estoque voltou) ou novo (só vendeu nos últimos 14 dias), ou marcado na mão =
   ranqueando até vender `rank_un` (40) desde o início — automático só em curva A/B com 1+ venda/dia, e a compra para
   ranquear vai no máximo a 3 semanas de venda; enquanto ranqueia a margem baixa não pesa e a compra garante o
   que falta para completar. ALERTAS DE PREÇO todo dia: venda dos últimos 7 dias × as 2 semanas antes (só dias com
   estoque): caiu ≥ 30% → baixar um pouco; subiu ≥ 30% com margem abaixo da meta → subir; ranqueou → subir aos poucos.
9. O mercado do Explorador é só referência (fatia e preço do líder): a compra NUNCA sobe por causa do mercado (Bruno: "não
   vou pegar o mercado inteiro de uma vez na primeira semana; compro a média que venho vendendo quando tenho estoque").
"""
import math

SEMANA = 7
PRAZO = 5
CAMPEAO = 1.2
Z = {"A": 1.65, "B": 1.0, "C": 0.5}   # 02/10 (Bruno): B e C saudáveis, mas com menos dinheiro parado
META_FAT = 2_000_000                  # R$/mês em todas as lojas (Bruno: 2 a 2,5 milhões com 18–20% líquido depois do ADS)
DIAS_FULL = 21
TOP_FULL = 10
META_MARGEM = 18.0       # % de margem depois do ADS
MARGEM_RUIM = 10.0
ML_GALPAO = 0.3          # parte da venda do ML que sai do galpão (despacho próprio quando é mais rápido)
RANK_UN = 40             # unidades para ranquear um anúncio que voltou ou é novo (Bruno: 30 a 50)
QUEDA, ALTA = 0.7, 1.3   # venda dos últimos 7 dias ÷ as 2 semanas antes
RANK_MIN_DIA = 1.0       # ranqueamento automático só para curva A/B que vende 1+/dia (perfume caro e lento não ranqueia por volume)
RANK_MAX_DIAS = 21       # a compra para ranquear não passa de 3 semanas de venda


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


def _taxa(k, ds, vendas_dia, estoque_dia, dias_est):
    """Venda por dia de k nos dias `ds` em que tinha estoque (dia sem estoque conhecido conta como com estoque)."""
    un, n = 0.0, 0
    for d in ds:
        v = (vendas_dia.get(d, {}).get(k) or {}).get("un") or 0
        if d in estoque_dia:
            i = dias_est.index(d)
            ant = dias_est[i - 1] if i > 0 else d
            if not ((estoque_dia.get(ant, {}).get(k) or 0) > 0 or (estoque_dia[d].get(k) or 0) > 0 or v > 0):
                continue
        un += v
        n += 1
    return (un / n if n else None), n


def _ranqueando(k, dias, vendas_dia, estoque_dia, dias_est, inicio_manual=None):
    """(desde, vendidos desde então, motivo) se o anúncio está em fase de ranqueamento; senão None."""
    v = lambda d: (vendas_dia.get(d, {}).get(k) or {}).get("un") or 0
    if inicio_manual:
        return inicio_manual, sum(v(d) for d in dias if d >= inicio_manual), "marcado na mão"
    zerado, desde = 0, None
    for d in dias_est:                                   # voltou de ruptura: 2+ dias zerado e o estoque voltou
        if (estoque_dia[d].get(k) or 0) <= 0:
            zerado += 1
        else:
            if zerado >= 2:
                desde = d
            zerado = 0
    if desde:
        return desde, sum(v(d) for d in dias if d >= desde), "voltou de ruptura"
    if len(dias) >= 21:                                   # novo: nada antes dos últimos 14 dias, venda depois
        antes, depois = dias[:-14], dias[-14:]
        if sum(v(d) for d in antes) == 0 and sum(v(d) for d in depois) > 0:
            ini = next(d for d in depois if v(d) > 0)
            return ini, sum(v(d) for d in depois), "anúncio novo"
    return None


def calcular(itens, estoque_dia, vendas_dia, cfg=None, mercado=None, manuais=None, margens=None, ranque=None):
    """itens: [{sku, titulo, disponivel, transito, custo}] (estoque de hoje); estoque_dia: {dia: {chave: disponível}};
    vendas_dia: {dia: {chave: {un, valor, ml}}} (ml = unidades vendidas no Mercado Livre); cfg: prazo, semana, campeao,
    caixa, meta_margem, ml_galpao; mercado: {chave: {...}}; manuais: {chave: nota} (decide na mão, fora do pedido);
    margens: {chave: margem % depois do ADS}; ranque: {chave: AAAA-MM-DD} (início do ranqueamento marcado na mão)."""
    cfg = dict({"prazo": PRAZO, "semana": SEMANA, "campeao": CAMPEAO, "caixa": None, "meta_margem": META_MARGEM,
                "ml_galpao": ML_GALPAO, "rank_un": RANK_UN, "meta_fat": META_FAT}, **{k: v for k, v in (cfg or {}).items() if v is not None or k == "caixa"})
    mercado, manuais, margens, ranque = mercado or {}, manuais or {}, margens or {}, ranque or {}
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
        mg = margens.get(k)
        rk = (_ranqueando(k, dias, vendas_dia, estoque_dia, dias_est, ranque.get(k))
              if k in ranque or (t["un"] > 0 and classe in ("A", "B") and base >= RANK_MIN_DIA) else None)
        rank = None
        if rk and rk[1] < cfg["rank_un"]:
            rank = {"desde": rk[0], "vendidos": rk[1], "meta": cfg["rank_un"], "motivo": rk[2]}
        margem = ("ruim" if mg is not None and mg < MARGEM_RUIM else "abaixo" if mg is not None and mg < cfg["meta_margem"]
                  else "ok" if mg is not None else None)
        mx = 0
        if t["un"] > 0:
            if rank:                                 # 10. ranqueando: margem baixa de propósito; garante o que falta vender
                seg = Z.get(classe, Z["B"]) * 1.3 * math.sqrt(base * T)
                falta = min(cfg["rank_un"] - rank["vendidos"], base * RANK_MAX_DIAS)    # no máximo 3 semanas de venda
                mx = max(math.ceil(base * T + seg), math.ceil(falta))
            elif margem == "ruim":                   # 8. margem ruim: só a semana, sem segurança
                mx = math.ceil(base * cfg["semana"])
            elif intermit:
                mx = max(1, math.ceil(base * T)) + (1 if classe == "A" else 0)
            else:
                z = Z["B"] if classe == "A" and margem == "abaixo" else Z.get(classe, Z["C"])
                seg = z * 1.3 * math.sqrt(base * T)
                mx = base * T + seg
                if classe == "A" and margem != "abaixo":
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
        # 10. alertas de preço: últimos 7 dias × as 2 semanas antes (só dias com estoque)
        alerta = None
        if t["un"] > 0 and len(dias) >= 14 and classe in ("A", "B") and k not in manuais:
            r7, n7 = _taxa(k, dias[-7:], vendas_dia, estoque_dia, dias_est)
            ra, na = _taxa(k, dias[-21:-7], vendas_dia, estoque_dia, dias_est)
            if rk and rk[1] >= cfg["rank_un"] and margem in ("ruim", "abaixo"):
                alerta = {"tipo": "subir", "texto": f"ranqueou ({int(rk[1])} vendidos desde {rk[0][8:10]}/{rk[0][5:7]}): subir o preço aos poucos até a margem"}
            elif r7 is not None and ra and n7 >= 3 and ra >= 0.5 and r7 <= ra * QUEDA and not rank:
                alerta = {"tipo": "baixar", "texto": f"venda caiu de {ra:.1f} para {r7:.1f}/dia: baixar um pouco o preço"}
            elif r7 is not None and ra and n7 >= 3 and ra >= 0.5 and r7 >= ra * ALTA and margem in ("ruim", "abaixo") and not rank:
                alerta = {"tipo": "subir", "texto": f"venda subiu de {ra:.1f} para {r7:.1f}/dia com margem abaixo da meta: subir o preço"}
            if alerta:
                alerta.update({"r7": round(r7, 2) if r7 is not None else None, "antes": round(ra, 2) if ra else None})
        linhas.append({
            "sku": it.get("sku"), "chave": k, "titulo": it.get("titulo") or "", "classe": classe,
            "disponivel": disp, "transito": trans, "custo": custo, "preco": round(preco, 2) if preco else None,
            "vendas_un": t["un"], "vendas_valor": round(t["valor"], 2), "dias_venda": t["dias_venda"],
            "media_dia": round(md, 2), "dia_com_estoque": round(dc, 2) if dc is not None else None, "dias_com_estoque": dc_dias,
            "venda_base": round(base, 2), "ruptura_dias": ruptura, "intermitente": intermit,
            "fat_dia": round(base * preco, 2) if preco else 0.0, "ml_share": round(ml_share, 3),
            "margem_pct": mg, "margem": margem, "ranqueando": rank, "alerta": alerta,
            "lucro_dia": round(base * preco * (mg if mg is not None else cfg["meta_margem"]) / 100, 2) if preco else 0.0,
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
        l["faixa"] = (1 if l["ranqueando"] and l["classe"] in ("A", "B") and acaba else 4 if l["margem"] == "ruim" else 1 if l["classe"] == "A" and acaba else 2 if l["classe"] == "B" and acaba
                      else 3 if l["classe"] == "A" else 4)
    pedido = sorted([l for l in linhas if l["faixa"]], key=lambda l: (l["faixa"], l["margem"] == "ruim", -l["lucro_dia"]))
    ac = 0.0
    caixa = cfg.get("caixa")
    for l in pedido:
        ac += l["compra_valor"]
        l["acumulado"] = round(ac, 2)
        l["cabe_no_caixa"] = caixa is None or ac <= caixa
    faixas = []
    for f, nome in ((1, "Campeões que acabam antes da próxima entrega"), (2, "Classe B que acaba antes da próxima entrega"),
                    (3, "Campeões completando o nível"), (4, "O resto (e margem abaixo de 10%: só a semana)")):
        xs = [l for l in pedido if l["faixa"] == f]
        if xs:
            faixas.append({"faixa": f, "nome": nome, "skus": len(xs), "unidades": sum(l["compra"] for l in xs),
                           "valor": round(sum(l["compra_valor"] for l in xs), 2), "acumulado": xs[-1]["acumulado"]})
    # 7. Full: os 10 que mais faturam
    full = []
    for l in sorted([l for l in linhas if l["vendas_valor"] > 0], key=lambda l: -l["vendas_valor"])[:TOP_FULL]:
        ml_dia = l["venda_base"] * l["ml_share"]
        alvo = math.ceil(ml_dia * (1 - cfg["ml_galpao"]) * cfg["campeao"] * DIAS_FULL)
        reserva = math.ceil((l["venda_base"] * (1 - l["ml_share"]) + ml_dia * cfg["ml_galpao"]) * T)
        full.append({"sku": l["sku"], "titulo": l["titulo"], "ml_dia": round(ml_dia, 2), "full_alvo": alvo, "reserva": reserva,
                     "disponivel": l["disponivel"], "transito": l["transito"],
                     "mandar_agora": int(min(alvo, max(0, l["disponivel"] - reserva))), "manual": l["manual"],
                     "margem_pct": l["margem_pct"], "margem": l["margem"]})
    a = [l for l in linhas if l["classe"] == "A"]
    resumo = {
        "dias_vendas": n, "de": dias[0] if dias else None, "ate": dias[-1] if dias else None,
        "dias_estoque": len(dias_est), "pedido_valor": round(ac, 2), "pedido_skus": len(pedido),
        "campeoes": len(a), "campeoes_zerados": sum(1 for l in a if l["disponivel"] + l["transito"] <= 0),
        "campeoes_ruptura": sum(1 for l in a if l["ruptura_dias"] > 0),
        "sem_custo": sum(1 for l in pedido if l["sem_custo"]), "caixa": caixa,
        "margem_ruim": sum(1 for l in a if l["margem"] == "ruim"), "margem_abaixo": sum(1 for l in a if l["margem"] == "abaixo"),
        "meta_margem": cfg["meta_margem"],
        "ranqueando": sum(1 for l in linhas if l["ranqueando"]), "alertas": sum(1 for l in linhas if l["alerta"]),
        "cabe_no_caixa": round(sum(l["compra_valor"] for l in pedido if l["cabe_no_caixa"]), 2) if caixa else None,
    }
    # 11. dinheiro parado por curva (custo em estoque) e o que passa do nível máximo
    parado = []
    for cl, nome in (("A", "Curva A"), ("B", "Curva B"), ("C", "Curva C"), ("-", "Sem venda no período")):
        xs = [l for l in linhas if l["classe"] == cl and l["custo"]]
        custo = sum(l["disponivel"] * l["custo"] for l in xs)
        acima = sum(max(0.0, l["disponivel"] - l["nivel_max"]) * l["custo"] for l in xs)
        venda_custo_dia = sum(l["venda_base"] * l["custo"] for l in xs)
        parado.append({"classe": cl, "nome": nome, "skus": sum(1 for l in xs if l["disponivel"] > 0), "custo": round(custo, 2),
                       "acima_do_nivel": round(acima, 2), "dias": round(custo / venda_custo_dia, 1) if venda_custo_dia else None})
    for l in linhas:
        l["acima_valor"] = round(max(0.0, l["disponivel"] - l["nivel_max"]) * l["custo"], 2) if l["custo"] else 0.0
    sobras = sorted([l for l in linhas if l["acima_valor"] > 0 and not l["ranqueando"]], key=lambda l: -l["acima_valor"])
    # 12. meta: faturamento do mês no ritmo atual e margem média depois do ADS (ponderada pelo faturamento)
    fat_mes = sum(t["valor"] for t in tot.values()) / n * 30
    com_mg = [(l["vendas_valor"], l["margem_pct"]) for l in linhas if l["margem_pct"] is not None and l["vendas_valor"] > 0]
    mg_media = sum(v * m for v, m in com_mg) / sum(v for v, _ in com_mg) if com_mg else None
    resumo.update({"fat_mes": round(fat_mes, 2), "meta_fat": cfg["meta_fat"], "margem_media": round(mg_media, 2) if mg_media is not None else None,
                   "parado_total": round(sum(p["custo"] for p in parado), 2),
                   "parado_bc": round(sum(p["custo"] for p in parado if p["classe"] != "A"), 2),
                   "acima_do_nivel": round(sum(p["acima_do_nivel"] for p in parado), 2)})
    precos = sorted([l for l in linhas if l["alerta"] or l["ranqueando"]],
                    key=lambda l: (0 if l["alerta"] and l["alerta"]["tipo"] == "baixar" else 1 if l["alerta"] else 2, -l["fat_dia"]))
    return {"cfg": cfg, "resumo": resumo, "faixas": faixas, "pedido": pedido, "full": full, "precos": precos,
            "parado": parado, "sobras": sobras[:80],
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
    # 02/10 (Bruno: "o preço médio dos cinco primeiros colocados"): por vendedor, os 5 que mais venderam, preço = fat ÷ un
    pv = {}
    for a in com:
        v = pv.setdefault(a.get("vendedor") or "?", [0.0, 0.0])
        v[0] += float(a.get("un") or 0)
        v[1] += float(a.get("fat") or 0) or float(a.get("un") or 0) * float(a["preco"])
    top5 = sorted(pv.values(), key=lambda v: -v[0])[:5]
    u5 = sum(v[0] for v in top5)
    return {"preco_top5": round(sum(v[1] for v in top5) / u5, 2) if u5 else None, "top5_vendedores": len(top5),"un_dia": round(un / dias, 2), "anuncios": len(xs), "vendedores": len({a.get("vendedor") for a in xs}),
            "preco_min": round(min(float(a["preco"]) for a in com), 2) if com else None,
            "preco_lider": round(float(lider["preco"]), 2) if lider else None,
            "lider_un_dia": round(float(lider["un"]) / dias, 2) if lider else None,
            "preco_medio": round(sum(float(a.get("fat") or 0) for a in xs) / un, 2) if un else None}


FORMATOS_FORA = ("outra marca", "decant", "kit", "body splash", "splash", "deo", "miniatura", "amostra")
GENERICAS = {"arabe", "arabes", "original", "originais", "importado", "importada", "feminino", "feminina", "masculino",
             "masculina", "unissex", "unisex", "nicho", "lacrado", "edp", "edt", "parfum", "toilette", "extrait", "perfume",
             "fragrancia", "spray", "novo", "nova", "presente", "alta", "fixacao", "intenso"}


GENERO = {"man", "men", "homme", "him", "woman", "women", "femme", "her", "masculino", "feminino"}


def _genero(pal):
    m = bool(pal & {"man", "men", "homme", "him"})
    f = bool(pal & {"woman", "women", "femme", "her"})
    return "m" if m and not f else "f" if f and not m else None


def mercado_por_produto(titulo, anuncios, dias, tokens, tipo_tok, marca="", vocab_extra=frozenset()):
    """02/10 (casamento pelo PRODUTO consolidado do Explorador): agrupa os anúncios do card pelo nome do produto
    ("Armaf Club de Nuit Intense Man EDT 105 ml"), e o SKU casa com o produto cujas palavras estão no título do SKU (≥ 75%),
    mesmo volume e sem EDP × EDT. Decant/kit/splash/deo/outra marca só casam com SKU do mesmo formato. Anúncio com preço
    abaixo de metade do mediano do produto não entra no preço (decant mal classificado). `tokens(t)` -> (palavras, volume);
    `tipo_tok(t)` -> 'edp'|'edt'|''."""
    s_pal, s_vol = tokens(titulo)
    s_tipo = tipo_tok(titulo)
    m_pal, _ = tokens(marca) if marca else (set(), None)
    proprias = {p for p in s_pal if p not in GENERICAS and p not in m_pal}   # palavras que dizem QUAL produto é
    t_low = str(titulo or "").lower()
    if len(s_pal) < 2 or not dias:
        return None
    grupos = {}
    for a in anuncios:
        nome = str(a.get("produto") or "").strip()
        if not nome:
            continue
        fmt = str(a.get("tipo") or "").lower()
        if any(f in fmt or f in nome.lower() for f in FORMATOS_FORA) and not any(f in t_low for f in FORMATOS_FORA if f in fmt or f in nome.lower()):
            continue
        grupos.setdefault(nome, []).append(a)
    # só contam as palavras do SKU que o Explorador usa em algum nome de produto da marca ("elixir" conta; "amadeirado" não)
    vocab = set(vocab_extra)                 # palavras de produto de todos os cards lidos ("candy" está no card da Belara)
    for nome in grupos:
        vocab |= tokens(nome)[0]
    proprias = proprias & vocab
    melhor = None
    for nome, xs in grupos.items():
        p_pal, p_vol = tokens(nome)
        if len(p_pal) < 2:
            continue
        if s_vol and p_vol and s_vol != p_vol:
            continue
        p_tipo = tipo_tok(nome)
        if s_tipo and p_tipo and s_tipo != p_tipo:
            continue
        comum = len(p_pal & s_pal)
        nota = comum / len(p_pal)
        # todas as palavras do produto no título do SKU ("Delilah VIOLA" não é o Delilah Blanc); com 5+ palavras, falta 1,
        # mas nunca a de gênero (Intense MAN × Intense WOMAN)
        falta = p_pal - s_pal
        if len(falta) > (1 if len(p_pal) >= 5 else 0) or falta & GENERO:
            continue
        gp, gs = _genero(p_pal), _genero(s_pal)
        if gp and gs and gp != gs:
            continue
        # e o contrário: o que o título do SKU diz do produto ("Yara ELIXIR") tem que estar no nome do produto
        if proprias and len(proprias & p_pal) / len(proprias) < 0.75:
            continue
        un = sum(float(a.get("un") or 0) for a in xs)
        chave = (nota, comum, un)
        if not melhor or chave > melhor[0]:
            melhor = (chave, nome, xs)
    if not melhor:
        return None
    _, nome, xs = melhor
    return _agrega(xs, dias, nome)


def mercado_por_gtin(gtin, anuncios, dias):
    """Aceita um GTIN ou vários (o mesmo perfume tem mais de um: Ferrari Black 8002135111974 no cadastro, 7795666906867 no
    meu anúncio)."""
    gs = {str(g).strip() for g in (gtin if isinstance(gtin, (set, list, tuple, frozenset)) else [gtin]) if g}
    if not gs:
        return None
    if len(gs) > 1:
        xs = [a for a in anuncios if str(a.get("gtin") or "").strip() in gs]
        if not xs or not dias:
            return None
        nomes = {}
        for a in xs:
            n = str(a.get("produto") or "").strip()
            if n:
                nomes[n] = nomes.get(n, 0) + float(a.get("un") or 0)
        r = _agrega(xs, dias, max(nomes, key=nomes.get) if nomes else "")
        r["gtin"] = ",".join(sorted(gs))
        return r
    return _mercado_um_gtin(next(iter(gs)), anuncios, dias)


def _mercado_um_gtin(gtin, anuncios, dias):
    """02/10 (Bruno: "mas o GTIN é diferente, né"): o mercado é todo anúncio do card com o MESMO GTIN do meu SKU (o GTIN do
    meu SKU vem do meu próprio anúncio no Explorador, coluna Sku). O nome consolidado do Explorador junta Yara, Yara Elixir e
    Yara Moi num "Lattafa Yara EDP 100 ml"; o GTIN separa. Anúncio sem GTIN fica de fora (o número sai um pouco por baixo)."""
    g = str(gtin or "").strip()
    xs = [a for a in anuncios if str(a.get("gtin") or "").strip() == g] if g else []
    if not xs or not dias:
        return None
    nomes = {}
    for a in xs:
        n = str(a.get("produto") or "").strip()
        if n:
            nomes[n] = nomes.get(n, 0) + float(a.get("un") or 0)
    r = _agrega(xs, dias, max(nomes, key=nomes.get) if nomes else "")
    r["gtin"] = g
    return r


def _agrega(xs, dias, nome):
    un = sum(float(a.get("un") or 0) for a in xs)
    precos = sorted(float(a["preco"]) for a in xs if a.get("preco"))
    mediana = precos[len(precos) // 2] if precos else None
    com = [a for a in xs if float(a.get("un") or 0) > 0 and a.get("preco") and (not mediana or float(a["preco"]) >= mediana / 2)]
    lider = max(com, key=lambda a: float(a.get("un") or 0)) if com else None
    return {"produto": nome, "un_dia": round(un / dias, 2), "anuncios": len(xs), "vendedores": len({a.get("vendedor") for a in xs}),
            "preco_min": round(min(float(a["preco"]) for a in com), 2) if com else None,
            "preco_lider": round(float(lider["preco"]), 2) if lider else None,
            "lider_un_dia": round(float(lider["un"]) / dias, 2) if lider else None,
            "preco_medio": round(sum(float(a.get("fat") or 0) for a in xs) / un, 2) if un else None}


def escolher_mercado(por_gtin, por_nome, fatia_min=0.15):
    """O mesmo perfume pode ter mais de um GTIN (Ferrari Black: pelo meu GTIN só aparece o meu anúncio, 13/dia; pelo nome,
    36/dia), e o nome consolidado do Explorador pode juntar produtos diferentes (Yara Moi = 3% do "Lattafa Yara EDP 100 ml").
    Vale o NOME quando o meu GTIN é uma fatia relevante dele (≥ 15%); senão vale o GTIN; sem um dos dois, o que houver."""
    if por_nome and por_gtin:
        if por_gtin["un_dia"] >= fatia_min * por_nome["un_dia"]:
            return dict(por_nome, casado_por="nome+gtin", gtin=por_gtin.get("gtin"))
        return dict(por_gtin, casado_por="gtin")
    if por_gtin:
        return dict(por_gtin, casado_por="gtin")
    if por_nome:
        return dict(por_nome, casado_por="nome")
    return None
