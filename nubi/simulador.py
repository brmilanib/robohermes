# -*- coding: utf-8 -*-
"""
📊 Simulador de Estratégia de Reposição (card #151, 03/10; pedido do Bruno feito com o GPT, texto no card).

Só conta (sem IA), sem caixa (não existe controle de caixa nesta etapa: nada de caixa disponível, reserva ou capacidade de
pagamento; a recomendação é só OPERACIONAL: vendas, estoque, giro, cobertura, margem e ruptura).

REGRA DINÂMICA (estratégia "Regra saudável"): o limite semanal de compra (a custo) = PCT × faturamento das vendas
aprovadas dos 7 dias anteriores; dividido em segunda 40%, quarta 34% e sexta 26% (o que sobra de um dia passa para o
próximo dia de compra da mesma semana). Dentro do limite valem as regras de estoque de `reposicao.py` (nível = venda base
× (dias que tem que durar + prazo) + segurança; A dura `dura_a`, B e C `dura_bc`) e a fila: campeões que acabam antes da
entrega, depois B que acaba, depois campeões completando, depois o resto; dentro da faixa, quem dá mais lucro por dia.

ESTRATÉGIA "Arrumar o estoque" (Bruno, 02/10 à noite: "o foco é achar o cenário para queimar os produtos de baixo giro e
gerar caixa até deixar o estoque correto"): igual, mas só a curva A (campeões) compra; B, C e sem venda não compram.

COMO O BACKTEST É FEITO (o nubi não tem o estoque de cada dia antes de 24/09 — a exportação de movimentações do UpSeller
veio só com "Estoque Inicial"):
- "repetição da demanda": parte do estoque REAL de hoje (disponível + trânsito, custo médio) e reproduz, dia a dia, a
  sequência de vendas reais do período escolhido. Cada decisão de compra só usa o que já aconteceu NA SIMULAÇÃO até aquele
  dia (nunca dado futuro); o pedido entra no estoque só no dia da chegada (dia do pedido + prazo).
- demanda de cada dia = a venda real do dia (vendas por anúncio do UpSeller: só pedidos válidos, sem cancelados). Nos
  dias em que o produto estava, pelas vendas, em ruptura histórica (sequência de dias sem venda que seria muito improvável
  para o ritmo que ele tinha: P(zero) = e^(−λ·dias) < 5%) ou com estoque 0 nas fotos do nubi (desde 24/09), a demanda é
  a VENDA POTENCIAL ESTIMADA = média diária dos 28 dias anteriores com venda (média móvel, só passado). Ela nunca é
  mostrada como venda real.
- produto com menos de 14 dias de histórico antes do dia = "histórico insuficiente": compra conservadora (só `dura_bc`,
  sem segurança) e não entra na escolha do percentual.
- aprendizado × validação: os primeiros 2/3 do período escolhem os candidatos e o último 1/3 confirma (um percentual
  ótimo no aprendizado e ruim na validação não é recomendado).
"""
import math

DIAS_COMPRA = {0: 0.40, 2: 0.34, 4: 0.26}       # segunda, quarta, sexta (weekday do Python)
PCT_PADRAO = 37
PESOS_PADRAO = {"disponibilidade": 25, "ruptura_a": 25, "giro": 20, "excesso": 15, "regularidade": 10, "lucro": 5}
DESTAQUES = (30, 35, 37, 40, 45, 50)
EXCESSO_DIAS = 90            # cobertura acima disso no fim = excesso
HIST_MIN = 14                # dias de histórico para não ser "insuficiente"
P_RUPTURA = 0.05


def _media(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else 0.0


def rupturas_historicas(dias, vendas, estoque_dia=None):
    """{sku: set(dias)} de dias em que o SKU provavelmente estava sem estoque. Pelas fotos do nubi (estoque 0) quando há;
    senão pela venda: sequência de k dias sem venda com taxa λ (28 dias antes, só dias com venda contados como "tinha")
    tal que e^(−λk) < 5%. Só usa o passado de cada dia para medir λ."""
    estoque_dia = estoque_dia or {}
    out = {}
    skus = {k for d in dias for k in (vendas.get(d) or {})}
    for k in skus:
        serie = [float(((vendas.get(d) or {}).get(k) or {}).get("un") or 0) for d in dias]
        marc = set()
        i = 0
        while i < len(dias):
            foto = (estoque_dia.get(dias[i]) or {})
            if k in foto:
                if foto[k] <= 0:
                    marc.add(dias[i])
                i += 1
                continue
            if serie[i] > 0:
                i += 1
                continue
            j = i
            while j < len(dias) and serie[j] == 0 and k not in (estoque_dia.get(dias[j]) or {}):
                j += 1
            ant = serie[max(0, i - 28):i]
            lam = sum(ant) / len(ant) if len(ant) >= 7 else 0.0
            if lam > 0 and math.exp(-lam * (j - i)) < P_RUPTURA:
                marc.update(dias[i:j])
            i = max(j, i + 1)
        if marc:
            out[k] = marc
    return out


def demanda(dias, vendas, rupt):
    """{sku: [(un_real, un_estimada, preço)]} por dia. Dia de ruptura histórica: demanda = média dos 28 dias anteriores
    com venda (venda potencial estimada); senão a venda real."""
    out = {}
    skus = {k for d in dias for k in (vendas.get(d) or {})}
    for k in skus:
        reais, lst, precos = [], [], []
        for d in dias:
            x = (vendas.get(d) or {}).get(k) or {}
            u, v = float(x.get("un") or 0), float(x.get("valor") or 0)
            if u > 0 and v > 0:
                precos.append(v / u)
            p = precos[-1] if precos else None
            if d in rupt.get(k, ()):
                base = [r for r in reais[-28:] if r > 0]
                est = (sum(base) / 28.0 * (28 / max(1, len(reais[-28:])))) if base else 0.0
                lst.append((u, max(0.0, est - u), p))
            else:
                lst.append((u, 0.0, p))
            reais.append(u)
        out[k] = lst
    return out


def _classes(fat):
    tot = sum(v for v in fat.values() if v > 0) or 1.0
    out, ac = {}, 0.0
    for k, v in sorted(fat.items(), key=lambda kv: -kv[1]):
        if v <= 0:
            out[k] = "C"
            continue
        out[k] = "A" if ac < 0.80 * tot else "B" if ac < 0.95 * tot else "C"
        ac += v
    return out


def simular(dias, dem, itens, pct, cfg=None, estrategia="saudavel", hist_antes=None):
    """Roda 1 cenário. dias = lista AAAA-MM-DD (em ordem); dem = demanda(); itens = {sku: {estoque, custo, preco, margem}}
    (estoque inicial = disponível + trânsito de hoje). hist_antes = {sku: [un dos dias antes do período]} para a venda
    base e a curva do 1º dia. -> indicadores do cenário."""
    cfg = cfg or {}
    prazo = int(cfg.get("prazo") or 5)
    dura_a, dura_bc = int(cfg.get("dura_a") or 30), int(cfg.get("dura_bc") or 15)
    z = {"A": 1.65, "B": 1.0, "C": 0.5}
    hist_antes = hist_antes or {}
    skus = sorted(set(itens) | set(dem))
    est = {k: float((itens.get(k) or {}).get("estoque") or 0) for k in skus}
    custo = {k: (itens.get(k) or {}).get("custo") for k in skus}
    margem = {k: (itens.get(k) or {}).get("margem") for k in skus}
    preco_fixo = {k: (itens.get(k) or {}).get("preco") for k in skus}
    hist = {k: list(hist_antes.get(k) or []) for k in skus}          # demanda conhecida até o dia (simulação)
    hist_fat = {k: [] for k in skus}
    chegadas = {}                                                     # dia índice -> {sku: un}
    em_transito = {k: 0.0 for k in skus}
    fat_dia = []
    sem_compra = {}
    tot = {"cmv": 0.0, "comprado": 0.0, "atendidas_un": 0.0, "atendidas": 0.0, "perdidas": 0.0, "perdidas_un": 0.0,
           "lucro": 0.0, "lucro_sem_dado": 0, "limite": 0.0, "usado": 0.0}
    semanas, semana_atual, estoque_medio = [], None, []
    rup_dias = {k: 0 for k in skus}
    rup_cls = {"A": 0, "B": 0, "C": 0}
    classes = _classes({k: sum(hist[k][-30:]) * float(preco_fixo.get(k) or custo.get(k) or 0) for k in skus})
    sobra = 0.0
    for i, d in enumerate(dias):
        wd = _weekday(d)
        for k, u in (chegadas.pop(i, None) or {}).items():
            est[k] += u
            em_transito[k] -= u
        # --- compra (antes das vendas do dia), só com o passado ---
        if wd == 0:
            classes = _classes({k: sum(hist_fat[k][-30:]) or sum(hist[k][-30:]) * float(preco_fixo.get(k) or 0) for k in skus})
            semana_atual = {"inicio": d, "comprado": 0.0, "limite": pct / 100.0 * sum(fat_dia[-7:]) if len(fat_dia) >= 7 else None}
            semanas.append(semana_atual)
            sobra = 0.0
        if wd in DIAS_COMPRA and semana_atual and semana_atual["limite"] is not None:
            limite = semana_atual["limite"] * DIAS_COMPRA[wd] + sobra
            tot["limite"] += semana_atual["limite"] * DIAS_COMPRA[wd]
            fila = []
            for k in skus:
                c = custo.get(k)
                if not c or c <= 0:
                    sem_compra[k] = "sem custo"
                    continue
                cl = classes.get(k, "C")
                if estrategia == "arrumar" and cl != "A":
                    continue
                h = hist[k]
                novo = len(h) < HIST_MIN
                com_venda = [x for x in h[-28:]]
                base = _media(com_venda[-7:]) if com_venda else 0.0
                if base <= 0:
                    continue
                dura = dura_bc if (novo or cl != "A") else dura_a
                seg = 0.0 if novo else z.get(cl, 0.5) * 1.3 * math.sqrt(base * (dura + prazo))
                nivel = base * (dura + prazo) + seg
                falta = nivel - est[k] - em_transito[k]
                if falta < 1:
                    continue
                acaba = (est[k] + em_transito[k]) / base
                p = preco_fixo.get(k) or c * 1.65
                lucro_dia = base * p * ((margem.get(k) if margem.get(k) is not None else 18.0) / 100.0)
                faixa = 1 if (cl == "A" and acaba < prazo + 2) else 2 if (cl == "B" and acaba < prazo + 2) else 3 if cl == "A" else 4
                fila.append((faixa, -lucro_dia, k, math.ceil(falta), c))
            fila.sort()
            gasto = 0.0
            pedido = {}
            for faixa, _, k, q, c in fila:
                q = min(q, int((limite - gasto) // c))       # o que cabe no limite do dia
                if q <= 0:
                    continue
                pedido[k] = q
                gasto += q * c
            sobra = max(0.0, limite - gasto)
            if pedido:
                cheg = chegadas.setdefault(i + prazo, {})
                for k, q in pedido.items():
                    cheg[k] = cheg.get(k, 0) + q
                    em_transito[k] += q
            tot["comprado"] += gasto
            tot["usado"] += gasto
            semana_atual["comprado"] += gasto
        # --- vendas do dia ---
        fat = 0.0
        for k in skus:
            lst = dem.get(k)
            u_real, u_est, p = lst[i] if lst else (0.0, 0.0, None)
            q = u_real + u_est
            p = p or preco_fixo.get(k) or ((custo.get(k) or 0) * 1.65)
            vendeu = min(est[k], q)
            perdeu = q - vendeu
            est[k] -= vendeu
            hist[k].append(q)
            hist_fat[k].append(vendeu * p)
            if q > 0 and perdeu > 0.0001:
                rup_dias[k] += 1
                rup_cls[classes.get(k, "C")] += 1
            fat += vendeu * p
            tot["cmv"] += vendeu * (custo.get(k) or p / 1.65)      # sem custo: pelo markup médio (1,65 em set/26)
            tot["atendidas_un"] += vendeu
            tot["atendidas"] += vendeu * p
            tot["perdidas"] += perdeu * p
            tot["perdidas_un"] += perdeu
            m = margem.get(k)
            if m is not None:
                tot["lucro"] += vendeu * p * m / 100.0
            elif custo.get(k):
                tot["lucro"] += vendeu * (p - custo[k])
            elif vendeu:
                tot["lucro_sem_dado"] += 1
        fat_dia.append(fat)
        estoque_medio.append(sum(est[k] * (custo.get(k) or 0) for k in skus))
    n = max(1, len(dias))
    cmv = tot["cmv"]                       # custo do que foi vendido (custo médio de hoje de cada SKU)
    est_final = sum(est[k] * (custo.get(k) or 0) for k in skus)
    est_med = _media(estoque_medio)
    cmv_dia = (cmv / n) if n else 0.0
    compras_sem = [s["comprado"] for s in semanas if s["limite"] is not None]
    reg = None
    if len(compras_sem) >= 2 and _media(compras_sem) > 0:
        m = _media(compras_sem)
        dp = math.sqrt(_media([(x - m) ** 2 for x in compras_sem]))
        reg = max(0.0, 1 - dp / m)
    cobertura_fim = {}
    for k in skus:
        h = [x for x in hist[k][-30:]]
        b = _media(h)
        cobertura_fim[k] = (est[k] / b) if b > 0 else (math.inf if est[k] > 0 else 0)
    excesso = sum(1 for k in skus if est[k] > 0 and cobertura_fim[k] > EXCESSO_DIAS and cobertura_fim[k] != math.inf)
    sem_venda = sum(1 for k in skus if est[k] > 0 and cobertura_fim[k] == math.inf)
    demanda_tot = tot["atendidas"] + tot["perdidas"]
    return {
        "pct": pct, "estrategia": estrategia, "dias": len(dias), "semanas": len(compras_sem),
        "comprado": round(tot["comprado"], 2),
        "compra_media_semana": round(_media(compras_sem), 2) if compras_sem else 0.0,
        "compra_max_semana": round(max(compras_sem), 2) if compras_sem else 0.0,
        "compra_min_semana": round(min(compras_sem), 2) if compras_sem else 0.0,
        "estoque_final": round(est_final, 2), "estoque_medio": round(est_med, 2),
        "cobertura_dias": round(est_med / cmv_dia, 1) if cmv_dia else None,
        "giro": round(cmv / est_med, 3) if est_med else None,
        "skus_ruptura": sum(1 for v in rup_dias.values() if v), "dias_ruptura": sum(rup_dias.values()),
        "ruptura_a": rup_cls["A"], "ruptura_b": rup_cls["B"], "excesso": excesso, "sem_venda": sem_venda,
        "vendas_atendidas": round(tot["atendidas"], 2), "vendas_perdidas_estimadas": round(tot["perdidas"], 2),
        "disponibilidade": round(tot["atendidas"] / demanda_tot, 4) if demanda_tot else None,
        "lucro_potencial": round(tot["lucro"], 2), "regularidade": round(reg, 3) if reg is not None else None,
        "limite_usado_pct": round(tot["usado"] / tot["limite"] * 100, 1) if tot["limite"] else None,
        "rupturas_por_sku": dict(list({k: v for k, v in sorted(rup_dias.items(), key=lambda kv: -kv[1]) if v}.items())[:30]),
        "sem_custo": len(sem_compra),
    }


def _weekday(d):
    from datetime import date
    return date.fromisoformat(d).weekday()


def pontuar(cenarios, pesos=None):
    """Pontuação de equilíbrio 0–100 (pesos editáveis). Cada critério vai de 0 a 1 entre o pior e o melhor cenário."""
    pesos = dict(PESOS_PADRAO, **(pesos or {}))
    soma = sum(pesos.values()) or 1

    def norm(chave, maior_melhor=True):
        vs = [c.get(chave) for c in cenarios if c.get(chave) is not None]
        lo, hi = (min(vs), max(vs)) if vs else (0, 0)
        out = {}
        for c in cenarios:
            v = c.get(chave)
            if v is None or hi == lo:
                out[c["pct"]] = 1.0 if v is not None else 0.5
            else:
                x = (v - lo) / (hi - lo)
                out[c["pct"]] = x if maior_melhor else 1 - x
        return out
    n = {"disponibilidade": norm("disponibilidade"), "ruptura_a": norm("ruptura_a", False), "giro": norm("giro"),
         "excesso": norm("estoque_medio", False), "regularidade": norm("regularidade"), "lucro": norm("lucro_potencial")}
    for c in cenarios:
        c["pontuacao"] = round(sum(pesos[k] * n[k][c["pct"]] for k in pesos) / soma * 100, 1)
    return cenarios


def recomendar(aprend, valid, faixa_pts=3.0):
    """Percentual de melhor equilíbrio: entre os que pontuam até `faixa_pts` do melhor no aprendizado E na validação, o
    MENOR percentual (subir mais só traria pouco ganho com mais estoque). Faixa segura = os que ficam a 5 pontos do melhor
    nos dois períodos."""
    pa = {c["pct"]: c["pontuacao"] for c in aprend}
    pv = {c["pct"]: c["pontuacao"] for c in valid}
    if not pa or not pv:
        return None, []
    ba, bv = max(pa.values()), max(pv.values())
    bons = sorted(p for p in pa if pa[p] >= ba - faixa_pts and pv.get(p, -1) >= bv - faixa_pts)
    seguros = sorted(p for p in pa if pa[p] >= ba - 5 and pv.get(p, -1) >= bv - 5)
    if not bons:                       # o melhor do aprendizado foi mal na validação: fica o melhor da validação
        bons = [max(pv, key=lambda p: (pv[p], -p))]
    return bons[0], seguros


def confianca(n_dias, frac_sem_custo, frac_insuf, tem_estoque_historico, tem_prazo=True):
    falta = []
    if n_dias < 30:
        falta.append(f"só {n_dias} dias de vendas (mínimo 30)")
    if not tem_estoque_historico:
        falta.append("estoque de cada dia antes de 24/09 (o export de movimentações do UpSeller veio incompleto): o "
                     "backtest parte do estoque de hoje e as rupturas antigas são estimadas pela venda")
    if frac_sem_custo > 0.2:
        falta.append(f"{frac_sem_custo:.0%} dos produtos sem custo")
    if frac_insuf > 0.3:
        falta.append(f"{frac_insuf:.0%} dos produtos com histórico insuficiente")
    if not tem_prazo:
        falta.append("prazo de entrega por fornecedor (usado o prazo único da reposição)")
    if n_dias < 30:
        nivel = "Dados insuficientes"
    elif frac_sem_custo > 0.4 or frac_insuf > 0.5:
        nivel = "Baixa"
    elif not tem_estoque_historico or n_dias < 60 or falta:
        nivel = "Média"
    else:
        nivel = "Alta"
    return nivel, falta


def rodar(dias, vendas, itens, cfg=None, pmin=25, pmax=60, passo=1, pesos=None, estoque_dia=None, estrategia="saudavel",
          hist_antes=None, pct_atual=PCT_PADRAO):
    """Simula todos os percentuais no período inteiro, no aprendizado (2/3) e na validação (1/3) e recomenda."""
    rupt = rupturas_historicas(dias, vendas, estoque_dia)
    dem = demanda(dias, vendas, rupt)
    pcts = list(range(int(pmin), int(pmax) + 1, max(1, int(passo))))
    if pct_atual not in pcts:
        pcts.append(int(pct_atual))
        pcts.sort()
    corte = max(1, (len(dias) * 2) // 3)
    d_a, d_v = dias[:corte], dias[corte:]
    dem_a = {k: v[:corte] for k, v in dem.items()}
    dem_v = {k: v[corte:] for k, v in dem.items()}
    hist_v = {k: [u + e for u, e, _ in v[:corte]] for k, v in dem.items()}
    for k, h in (hist_antes or {}).items():
        hist_v[k] = list(h) + hist_v.get(k, [])
    todos = pontuar([simular(dias, dem, itens, p, cfg, estrategia, hist_antes) for p in pcts], pesos)
    aprend = pontuar([simular(d_a, dem_a, itens, p, cfg, estrategia, hist_antes) for p in pcts], pesos)
    valid = pontuar([simular(d_v, dem_v, itens, p, cfg, estrategia, hist_v) for p in pcts], pesos) if d_v else []
    n_itens = len(set(itens) | set(dem))
    sem_custo = sum(1 for k in set(dem) if not (itens.get(k) or {}).get("custo")) / max(1, len(dem))
    insuf = sum(1 for k, v in dem.items() if sum(1 for u, e, _ in v if u + e > 0) + len((hist_antes or {}).get(k) or []) < HIST_MIN) / max(1, len(dem))
    nivel, falta = confianca(len(dias), sem_custo, insuf, bool(estoque_dia) and len(estoque_dia) >= len(dias) * 0.8)
    rec, seguros = (None, []) if nivel == "Dados insuficientes" else recomendar(aprend, valid)
    por = {c["pct"]: c for c in todos}
    return {"estrategia": estrategia, "inicio": dias[0] if dias else None, "fim": dias[-1] if dias else None,
            "dias": len(dias), "semanas": len(dias) // 7, "produtos": n_itens, "pcts": pcts, "pct_atual": pct_atual,
            "cenarios": todos, "aprendizado": {"inicio": d_a[0] if d_a else None, "fim": d_a[-1] if d_a else None,
                                               "pontos": {c["pct"]: c["pontuacao"] for c in aprend}},
            "validacao": {"inicio": d_v[0] if d_v else None, "fim": d_v[-1] if d_v else None,
                          "pontos": {c["pct"]: c["pontuacao"] for c in valid}},
            "recomendado": rec, "faixa_segura": [seguros[0], seguros[-1]] if seguros else None,
            "confianca": nivel, "falta": falta, "rupturas_historicas": sum(len(v) for v in rupt.values()),
            "skus_ruptura_historica": len(rupt), "pesos": dict(PESOS_PADRAO, **(pesos or {})),
            "resumo": resumo(por.get(pct_atual), por.get(rec) if rec else None, pct_atual, rec, nivel)}


def resumo(atual, rec, pa, pr, nivel):
    """Frase só com os números dos cenários (nada inventado)."""
    if not atual:
        return ""
    if rec is None or pr is None:
        return (f"Com {pa}%: compras de R$ {atual['comprado']:,.0f}, estoque médio de R$ {atual['estoque_medio']:,.0f} e "
                f"{atual['ruptura_a']} dias-produto de ruptura na curva A. Sem recomendação: confiança {nivel}.").replace(",", ".")
    if pr == pa:
        return (f"O percentual atual de {pa}% já é o de melhor equilíbrio na simulação (confiança {nivel}): compras de "
                f"R$ {atual['comprado']:,.0f}, estoque médio de R$ {atual['estoque_medio']:,.0f}, "
                f"{atual['ruptura_a']} dias-produto de ruptura na curva A.").replace(",", ".")
    def dif(c):
        return rec[c] - atual[c]
    lado = "mais" if pr > pa else "menos"
    return (f"Com {pa}% a simulação teve {atual['ruptura_a']} dias-produto de ruptura na curva A e estoque médio de "
            f"R$ {atual['estoque_medio']:,.0f}. O melhor equilíbrio ficou em {pr}% ({lado} compra): rupturas A "
            f"{dif('ruptura_a'):+d}, estoque médio {dif('estoque_medio'):+,.0f}, compras {dif('comprado'):+,.0f} e vendas "
            f"atendidas {dif('vendas_atendidas'):+,.0f} (venda potencial estimada incluída na demanda). Confiança {nivel}."
            ).replace(",", ".")
