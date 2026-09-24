# -*- coding: utf-8 -*-
"""
B.I. dos vendedores monitorados: o ano (todos os meses importados), o produto e os
alertas de estoque.

O export do Nubimetrics só traz anúncios COM venda no período e o estado ATUAL de cada
anúncio (active/paused). No Mercado Livre, anúncio sem estoque fica pausado; então:
  - produto que vendia e agora está com todos os anúncios pausados = sem estoque;
  - produto que vendia e sumiu do mês atual = parou de vender (sem estoque ou saiu);
  - vendas por dia: o coletor importa o mês atual todo dia (acumulado até ontem-1);
    a diferença entre dois dias é o que vendeu no dia (vend_produto_dia).
As unidades do Nubimetrics são estimativas e vêm arredondadas nos produtos grandes
(de 10 em 10), por isso as regras exigem volume antes de alertar.
"""

import calendar
from datetime import date, timedelta

import ranking

RITMO_MIN = 0.5          # un/dia no mês anterior para o produto entrar nos alertas (≈15 un/mês)
QUEDA = 0.35             # vendendo menos de 35% do ritmo anterior
DIAS_MIN_QUEDA = 7       # só compara ritmo com pelo menos 7 dias de mês
UN_SEM_VENDA = 25        # "parou de vender": unidades que ele deveria ter vendido nos dias parados (arredondamento de 10)


def chave(l):
    """Mesma chave do SQL (vend_prod_mes): GTIN; sem GTIN, o título em minúsculas."""
    return l.get("gtin") or ("T:" + (l.get("titulo") or "").lower())


def dias_do_mes(mes):
    a, m = map(int, str(mes)[:7].split("-"))
    return calendar.monthrange(a, m)[1]


def dias_periodo(rel):
    """Dias cobertos pelo relatório: até o dia 'ate' (parcial) ou o mês inteiro."""
    return int(rel["ate"][8:10]) if rel.get("ate") else dias_do_mes(rel["mes"])


def data_foto(mes, ate):
    """Dia a que o acumulado se refere: 'ate' (mês parcial) ou o último dia do mês."""
    return ate or f"{str(mes)[:7]}-{dias_do_mes(mes):02d}"


def fotos(linhas, vendedor, mes, ate):
    """Foto acumulada de cada produto para vend_produto_dia."""
    dia = data_foto(mes, ate)
    por = {}
    for l in linhas:
        k = chave(l)
        x = por.setdefault(k, {"u": 0, "v": 0.0, "a": 0, "n": 0})
        x["u"] += int(l.get("unidades") or 0)
        x["v"] += float(l.get("vendas") or 0)
        x["n"] += 1
        x["a"] += 1 if (l.get("estado") or "").lower() == "active" else 0
    return [{"vendedor": vendedor, "mes": str(mes)[:7] + "-01", "chave": k, "dias": {dia: v}} for k, v in por.items()]


def itens_dia(linhas):
    """Export de um dia -> um item por produto: {k, t (título), m (marca), u, v, a (anúncios ativos), n (anúncios)}."""
    por = {}
    for l in linhas:
        k = chave(l)
        x = por.setdefault(k, {"k": k, "t": "", "m": l.get("marca") or "", "u": 0, "v": 0.0, "a": 0, "n": 0, "_u": -1})
        u = int(l.get("unidades") or 0)
        if u > x["_u"]:                      # título/marca do anúncio que mais vendeu
            x["t"], x["_u"] = (l.get("titulo") or "")[:90], u
            x["m"] = l.get("marca") or x["m"]
        x["u"] += u
        x["v"] += float(l.get("vendas") or 0)
        x["n"] += 1
        x["a"] += 1 if (l.get("estado") or "").lower() == "active" else 0
    saida = [{k: (round(v, 2) if k == "v" else v) for k, v in x.items() if k != "_u"} for x in por.values()]
    return sorted([x for x in saida if x["u"] or x["v"]], key=lambda x: -x["v"])


def diario(dias, mes):
    """
    dias: {"AAAA-MM-DD": {"u": acumulado, ...}} de um produto num mês.
    Devolve [{"dia", "u", "estimado"}] do dia 1 até a última foto. Entre duas fotos com
    intervalo de mais de um dia, o que vendeu é dividido igualmente (estimado).
    """
    if not dias:
        return []
    ini = date.fromisoformat(str(mes)[:7] + "-01")
    saida, ant_dia, ant_u = [], ini - timedelta(days=1), 0
    for d in sorted(dias):
        dd = date.fromisoformat(d)
        n = (dd - ant_dia).days
        if n <= 0:
            continue
        delta = max(0, int(dias[d].get("u") or 0) - ant_u)
        for i in range(n):
            dia = ant_dia + timedelta(days=i + 1)
            saida.append({"dia": dia.isoformat(), "u": delta / n, "estimado": n > 1})
        ant_dia, ant_u = dd, max(ant_u, int(dias[d].get("u") or 0))
    return saida


def dias_parado(dias):
    """Dias seguidos no fim do mês em que o acumulado não mudou (só com fotos diárias)."""
    ds = sorted(dias)
    if len(ds) < 2:
        return 0
    ult = dias[ds[-1]].get("u") or 0
    parado = 0
    for i in range(len(ds) - 2, -1, -1):
        if (dias[ds[i]].get("u") or 0) != ult:
            break
        parado = (date.fromisoformat(ds[-1]) - date.fromisoformat(ds[i])).days
    return parado


# ---------------------------------------------------------------------------
# Ano do vendedor
# ---------------------------------------------------------------------------

def _tendencia(ritmos):
    """ritmos: un/dia por mês (None = sem venda). Compara os 2 últimos meses com os 2 anteriores."""
    vals = [r or 0 for r in ritmos]
    if len(vals) < 3 or not any(vals):
        return ""
    rec = sum(vals[-2:]) / 2
    ant = sum(vals[-4:-2]) / max(1, len(vals[-4:-2]))
    if ant == 0:
        return "Novo" if rec > 0 else ""
    if rec == 0:
        return "Parou"
    r = rec / ant - 1
    return "Subindo forte" if r >= 0.5 else "Subindo" if r >= 0.15 else "Caindo forte" if r <= -0.5 else \
        "Caindo" if r <= -0.15 else "Estável"


def ano(rels, prods, dias_mes_atual=None):
    """
    rels: relatórios do vendedor [{id, mes, ate}] (qualquer ordem).
    prods: linhas de vend_prod_mes desses relatórios.
    dias_mes_atual: {chave: dias} do último mês (vend_produto_dia), para o "parado há".
    """
    rels = sorted(rels, key=lambda r: r["mes"])
    idx = {r["id"]: i for i, r in enumerate(rels)}
    n = len(rels)
    meses = []
    for r in rels:
        d = dias_periodo(r)
        meses.append({"mes": r["mes"][:7], "nome": ranking.nome_mes(r["mes"]), "ate": r.get("ate"), "dias": d,
                      "dias_mes": dias_do_mes(r["mes"]), "vendas": 0.0, "unidades": 0, "produtos": 0,
                      "anuncios": 0, "ativos": 0, "marcas": set()})
    P, marcas_mes = {}, [dict() for _ in rels]
    for p in prods:
        i = idx.get(p["relatorio_id"])
        if i is None:
            continue
        m = meses[i]
        v, u = float(p["vendas"] or 0), int(p["unidades"] or 0)
        m["vendas"] += v
        m["unidades"] += u
        m["produtos"] += 1
        m["anuncios"] += p["anuncios"] or 0
        m["ativos"] += p["ativos"] or 0
        marca = (p["marca"] or "").strip().upper() or "(SEM MARCA)"
        m["marcas"].add(marca)
        marcas_mes[i][marca] = marcas_mes[i].get(marca, 0.0) + v
        x = P.setdefault(p["chave"], {"chave": p["chave"], "gtin": p["gtin"], "marca": p["marca"],
                                      "u": [0] * n, "v": [0.0] * n, "ativos": [None] * n, "anuncios": [None] * n,
                                      "titulo": p["titulo"], "full": False, "catalogo": False, "ult_i": -1})
        x["u"][i], x["v"][i], x["ativos"][i], x["anuncios"][i] = u, v, p["ativos"], p["anuncios"]
        if i >= x["ult_i"]:
            x["titulo"], x["ult_i"] = p["titulo"] or x["titulo"], i
            x["full"], x["catalogo"] = bool(p["fulfillment"]), bool(p["catalogo"])
    for m in meses:
        m["marcas"] = len(m["marcas"])
        m["ticket"] = m["vendas"] / m["unidades"] if m["unidades"] else 0
        m["vendas_dia"] = m["vendas"] / m["dias"] if m["dias"] else 0
        m["unidades_dia"] = m["unidades"] / m["dias"] if m["dias"] else 0
        m["projecao"] = m["vendas_dia"] * m["dias_mes"] if m["ate"] else None

    ritmo = lambda x, i: x["u"][i] / meses[i]["dias"] if meses[i]["dias"] else 0
    produtos = []
    for x in P.values():
        rit = [ritmo(x, i) if x["u"][i] else None for i in range(n)]
        ult = n - 1
        tot_v, tot_u = sum(x["v"]), sum(x["u"])
        produtos.append({
            "chave": x["chave"], "produto": x["titulo"], "marca": x["marca"], "gtin": x["gtin"] or "",
            "vendas": tot_v, "unidades": tot_u, "preco": tot_v / tot_u if tot_u else 0,
            "serie_u": x["u"], "serie_v": x["v"], "ritmo": rit,
            "ritmo_atual": rit[ult] or 0, "ritmo_ant": (rit[ult - 1] or 0) if n > 1 else None,
            "meses_com_venda": sum(1 for u in x["u"] if u), "tendencia": _tendencia(rit),
            "ativos": x["ativos"][ult], "anuncios": x["anuncios"][ult],
            "full": "Sim" if x["full"] else "Não", "catalogo": "Sim" if x["catalogo"] else "Não",
        })
    produtos.sort(key=lambda p: -p["vendas"])

    # marcas: as 8 maiores do ano, com a fatia em cada mês
    tot_marca = {}
    for mm in marcas_mes:
        for k, v in mm.items():
            tot_marca[k] = tot_marca.get(k, 0.0) + v
    top = [k for k, _ in sorted(tot_marca.items(), key=lambda kv: -kv[1])[:8]]
    marcas = [{"marca": k, "vendas": tot_marca[k],
               "serie": [marcas_mes[i].get(k, 0.0) for i in range(n)],
               "share": [marcas_mes[i].get(k, 0.0) / meses[i]["vendas"] if meses[i]["vendas"] else 0 for i in range(n)]}
              for k in top]

    grupo = lambda t: [p for p in produtos if p["tendencia"] == t]
    return {"meses": meses, "produtos": produtos, "marcas": marcas,
            "subindo": sorted(grupo("Subindo forte") + grupo("Subindo"), key=lambda p: -p["ritmo_atual"] * p["preco"])[:15],
            "caindo": sorted(grupo("Caindo forte") + grupo("Parou"), key=lambda p: -(p["ritmo_ant"] or 0) * p["preco"])[:15],
            "novos": sorted(grupo("Novo"), key=lambda p: -p["vendas"])[:15]}


# ---------------------------------------------------------------------------
# Alertas de estoque
# ---------------------------------------------------------------------------

def alertas(vendedor, rel_ant, rel_ult, prods_ant, prods_ult, dias_ult=None):
    """
    Produtos que vendiam bem no mês anterior (rel_ant) e agora, no último relatório (rel_ult):
      - "Sem estoque": todos os anúncios que venderam estão pausados;
      - "Parou de vender": com fotos diárias, o acumulado não muda há vários dias;
      - "Sumiu": não aparece no último relatório (nenhuma venda no período);
      - "Vendendo bem menos": ritmo abaixo de 35% do mês anterior.
    """
    dias_ult = dias_ult or {}
    d_ant, d_ult = dias_periodo(rel_ant), dias_periodo(rel_ult)
    ult = {p["chave"]: p for p in prods_ult}
    foto = data_foto(rel_ult["mes"], rel_ult.get("ate"))
    saida = []
    for p in prods_ant:
        u_ant = int(p["unidades"] or 0)
        r_ant = u_ant / d_ant if d_ant else 0
        if r_ant < RITMO_MIN:
            continue
        preco = float(p["vendas"] or 0) / u_ant if u_ant else 0
        q = ult.get(p["chave"])
        r_ult = (int(q["unidades"] or 0) / d_ult) if q and d_ult else 0
        parado = dias_parado(dias_ult.get(p["chave"]) or {})
        tipo = nivel = None
        if q and (q["anuncios"] or 0) > 0 and (q["ativos"] or 0) == 0:
            tipo, nivel = "Sem estoque", 3
            detalhe = f"todos os {q['anuncios']} anúncio(s) com venda estão pausados"
        elif q and parado >= 3 and r_ant * parado >= UN_SEM_VENDA:
            tipo, nivel = "Parou de vender", 3
            detalhe = f"nenhuma venda nos últimos {parado} dias"
        elif not q and d_ult >= 5:
            tipo, nivel = "Sumiu", 2
            detalhe = f"nenhuma venda em {ranking.nome_mes(rel_ult['mes'])}"
        elif q and d_ult >= DIAS_MIN_QUEDA and r_ult < QUEDA * r_ant:
            tipo, nivel = "Vendendo bem menos", 1
            detalhe = f"{r_ult:.1f} un/dia contra {r_ant:.1f} no mês anterior".replace(".", ",")
        if not tipo:
            continue
        saida.append({
            "vendedor": vendedor, "chave": p["chave"], "produto": (q or p)["titulo"], "marca": p["marca"],
            "gtin": p["gtin"] or "", "tipo": tipo, "nivel": nivel, "detalhe": detalhe,
            "ritmo_ant": r_ant, "ritmo_atual": r_ult, "preco": preco,
            # sem estoque / parado / sumiu: deixa de vender o ritmo inteiro; em queda: só a diferença
            "perda_dia": r_ant * preco if nivel >= 2 else max(0.0, (r_ant - r_ult) * preco),
            "anuncios": (q or {}).get("anuncios"), "ativos": (q or {}).get("ativos"),
            "mes_ant": rel_ant["mes"][:7], "foto": foto,
        })
    saida.sort(key=lambda a: (-a["nivel"], -a["perda_dia"]))
    return saida


def cruzar_alertas(todos, quem_vende):
    """
    todos: alertas de todos os vendedores. quem_vende: {chave: [{vendedor, ritmo, ativos}]} no último mês.
    Junta por produto: quantos concorrentes estão sem estoque e quem ainda vende.
    """
    por = {}
    for a in todos:
        x = por.setdefault(a["chave"], {"chave": a["chave"], "produto": a["produto"], "marca": a["marca"],
                                        "gtin": a["gtin"], "alertas": [], "perda_dia": 0.0, "nivel": 0})
        x["alertas"].append(a)
        x["perda_dia"] += a["perda_dia"]
        x["nivel"] = max(x["nivel"], a["nivel"])
    for k, x in por.items():
        fora = {a["vendedor"] for a in x["alertas"]}
        x["ainda_vendem"] = [v for v in quem_vende.get(k, []) if v["vendedor"] not in fora and (v["ativos"] or 0) > 0]
        x["sem_estoque"] = sum(1 for a in x["alertas"] if a["nivel"] >= 2)
    return sorted(por.values(), key=lambda x: (-x["sem_estoque"], -x["nivel"], -x["perda_dia"]))
