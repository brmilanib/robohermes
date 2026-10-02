# -*- coding: utf-8 -*-
"""
💰 Financeiro (02/10, Bruno: "abre uma aba em Minhas Lojas → Financeiro; vou exportar todo mês fechado o DRE Simplificado do
Gestor Seller; depois ensino o coletor; calcule meu markup médio para o potencial de vendas do estoque").

O DRE Simplificado (Financeiro → DRE Simplificado, 1 mês fechado) vem como PDF; a tela lê o texto do PDF no navegador
(pdf.js) e manda o TEXTO para cá (`ler_dre`). O coletor, quando aprender, manda o texto da página (mesmas linhas).
Guardado em ia_resumos `financeiro|dre|AAAA-MM`. Markup médio = faturamento ÷ custo dos produtos vendidos (set/26:
820.464 ÷ 497.530 = 1,65×); é ele que vale no potencial de vendas do estoque (Bruno: "às vezes estou rankeando um produto
e vendo mais barato mesmo" — o preço de venda do SKU agora não serve de base).
"""
import json
import re

CANAIS = ("Amazon", "Mercado Livre", "Shopee", "TikTok Shop")
MESES_MARKUP = 12       # 02/10 (Bruno): média do ano, não de um mês — mês rankeando produto novo baixa a margem, outro sobe


def _num(txt):
    """'R$ 820.464,00' / '- R$ 58.589,50' / '+ R$ 955,33' / '-R$ 32,51' -> float."""
    t = str(txt or "").replace("R$", "").replace(" ", "")
    neg = t.startswith("-")
    t = t.lstrip("+-").replace(".", "").replace(",", ".")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def _canal(nome):
    n = re.sub(r"\s+", " ", str(nome or "")).strip().lower()
    for c in CANAIS:
        if c.lower() == n:
            return c
    return None


def ler_dre(texto):
    """Texto do DRE Simplificado (todas as páginas) -> dicionário por mês. Lê por blocos: Faturamento (por canal), Líquido
    Marketplace (Valor Final por canal), Lucro Bruto (custo dos produtos, reembolsados, imposto por canal), ADS (por canal),
    Despesas operacionais, Lucro líquido. Linha que não casa é ignorada; o que faltar fica None (nunca zero inventado)."""
    linhas = [re.sub(r"\s+", " ", l).strip() for l in str(texto or "").splitlines()]
    linhas = [l for l in linhas if l and not l.startswith("https://") and "DRE Simplificado" not in l]
    m = re.search(r"Per[ií]odo:\s*(\d{2})/(\d{4})", " ".join(linhas))
    if not m:
        raise ValueError("não achei 'Período: MM/AAAA' no texto do DRE")
    mes = f"{m.group(2)}-{m.group(1)}"
    d = {"mes": mes, "faturamento": None, "faturamento_canal": {}, "liquido": None, "liquido_canal": {},
         "custo_produtos": 0.0, "custo_canal": {}, "custo_reembolsados": 0.0, "imposto": 0.0, "lucro_bruto": None,
         "lucro_bruto_pct": None, "lucro_bruto_canal": {}, "ads": None, "ads_canal": {}, "lucro_pos_ads": None,
         "lucro_pos_ads_pct": None, "despesas": None, "despesas_itens": {}, "lucro_liquido": None, "lucro_liquido_pct": None,
         "armazenamento": None}
    bloco, canal = None, None
    cab = re.compile(r"^(Faturamento|L[ií]quido Marketplace|Lucro Bruto|Custo de armazenamento FULL/FBA|ADS|Lucro bruto depois de ads|"
                     r"Receita extra|Despesas operacionais|Lucro L[ií]quido Operacional)\s*(-?\s*R\$\s*[\d.,]+)?\s*(?:\((-?[\d,]+)%\))?$", re.I)
    for l in linhas:
        c = cab.match(l)
        if c:
            nome = c.group(1).lower()
            val = _num(c.group(2)) if c.group(2) else None
            pct = float(c.group(3).replace(",", ".")) / 100 if c.group(3) else None
            bloco, canal = nome, None
            if nome == "faturamento":
                d["faturamento"] = val
            elif nome.startswith("l") and "marketplace" in nome:
                d["liquido"] = val
            elif nome == "lucro bruto":
                d["lucro_bruto"], d["lucro_bruto_pct"] = val, pct
            elif nome == "ads":
                d["ads"] = -val if val is not None and val < 0 else val
            elif nome.startswith("lucro bruto depois"):
                d["lucro_pos_ads"], d["lucro_pos_ads_pct"] = val, pct
            elif nome == "despesas operacionais":
                d["despesas"] = -val if val is not None and val < 0 else val
            elif nome.startswith("lucro l"):
                d["lucro_liquido"], d["lucro_liquido_pct"] = val, pct
            elif nome.startswith("custo de armazenamento"):
                d["armazenamento"] = -val if val is not None and val < 0 else val
            continue
        solo = re.match(r"^(-?\s*R\$\s*[\d.,]+)$", l)
        if solo:                                  # total do bloco numa linha só ("-R$ 25.343,33" do ADS, das despesas)
            v = abs(_num(solo.group(1)) or 0)
            if bloco == "ads" and d["ads"] is None:
                d["ads"] = v
            elif bloco == "despesas operacionais" and d["despesas"] is None:
                d["despesas"] = v
            elif bloco and bloco.startswith("custo de armazenamento") and d["armazenamento"] is None:
                d["armazenamento"] = v
            continue
        kv = re.match(r"^(.+?):\s*((?:[+-]\s*)?R\$\s*[\d.,]+)$", l)
        if not kv:
            continue
        chave, val = kv.group(1).strip(), _num(kv.group(2))
        canal_l = _canal(chave)
        if canal_l:
            canal = canal_l
            if bloco == "faturamento":
                d["faturamento_canal"][canal] = val
            elif bloco == "ads":
                d["ads_canal"][canal] = val
            continue
        k = chave.lower()
        if bloco == "lucro bruto":
            if k == "custo dos produtos":
                d["custo_produtos"] += -val if val < 0 else val
                d["custo_canal"][canal or "?"] = d["custo_canal"].get(canal or "?", 0.0) + (-val if val < 0 else val)
            elif k == "custo dos produtos reembolsados":
                d["custo_reembolsados"] += -val if val < 0 else val
            elif k == "imposto":
                d["imposto"] += -val if val < 0 else val
            elif k == "valor final" and canal:
                d["lucro_bruto_canal"][canal] = val
        elif bloco and "marketplace" in bloco and k == "valor final" and canal:
            d["liquido_canal"][canal] = val
        elif bloco == "despesas operacionais":
            d["despesas_itens"][chave] = val
    if d["faturamento"] is None and d["faturamento_canal"]:
        d["faturamento"] = round(sum(d["faturamento_canal"].values()), 2)
    if d["ads"] is None and d["ads_canal"]:
        d["ads"] = round(sum(d["ads_canal"].values()), 2)
    for k in ("custo_produtos", "custo_reembolsados", "imposto"):
        d[k] = round(d[k], 2)
    d["markup"] = round(d["faturamento"] / d["custo_produtos"], 4) if d["faturamento"] and d["custo_produtos"] else None
    d["markup_liquido"] = round(d["liquido"] / d["custo_produtos"], 4) if d["liquido"] and d["custo_produtos"] else None
    d["margem_bruta_pct"] = d["lucro_bruto_pct"]
    return d


def gravar_dre(repo, d, origem="manual"):
    reg = dict(d, origem=origem)
    repo._req("POST", "ia_resumos", corpo=[{"chave": f"financeiro|dre|{d['mes']}", "ia": "Gestor Seller (DRE)",
                                            "texto": json.dumps(reg, ensure_ascii=False)}],
              prefer="resolution=merge-duplicates,return=minimal")
    return reg


def meses(repo):
    out = []
    for r in repo._req("GET", "ia_resumos", {"select": "chave,texto", "chave": "like.financeiro|dre|%", "order": "chave.desc", "limit": 60}) or []:
        try:
            d = json.loads(r["texto"])
            if d.get("mes"):
                out.append(d)
        except (ValueError, TypeError):
            continue
    out.sort(key=lambda d: d["mes"], reverse=True)
    return out


def markup_medio(ms, n=MESES_MARKUP):
    """Média ponderada pelo custo dos últimos `n` meses: Σ faturamento ÷ Σ custo dos produtos. Sem DRE = None."""
    ult = [d for d in ms if d.get("faturamento") and d.get("custo_produtos")][:n]
    if not ult:
        return None
    fat, custo = sum(d["faturamento"] for d in ult), sum(d["custo_produtos"] for d in ult)
    return {"markup": round(fat / custo, 4), "meses": [d["mes"] for d in ult], "faturamento": round(fat, 2), "custo": round(custo, 2),
            "markup_liquido": round(sum(d["liquido"] or 0 for d in ult) / custo, 4) if all(d.get("liquido") for d in ult) else None}


MESES_PT = {"JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "MARÇO": 3, "ABRIL": 4, "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8,
            "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12}
LINHAS_RESUMO = {"faturamento": "faturamento", "liq. do marketplace": "liquido", "líq. do marketplace": "liquido",
                 "liquido do marketplace": "liquido", "líquido do marketplace": "liquido", "lucro bruto": "lucro_bruto",
                 "margem": "margem", "custo de ads": "ads", "lucro bruto pós ads": "lucro_pos_ads", "lucro bruto pos ads": "lucro_pos_ads",
                 "mpa": "mpa"}
IMPOSTO_PCT = 0.024      # set/26: R$ 19.616 de imposto em R$ 820.464 (2,4%) — só para o markup APROXIMADO pelo Resumo
RESUMO = "financeiro|resumo"


def _canal_img(tok):
    t = tok.lower()
    if "mercado" in t or "meli" in t or t.startswith("ml"):
        return "Mercado Livre"
    if "shopee" in t:
        return "Shopee"
    if "tiktok" in t or "tik" in t:
        return "TikTok Shop"
    if "amazon" in t or "amz" in t:
        return "Amazon"
    return None


def ler_resumo(texto, hoje=None):
    """Texto da tela Gestor Seller → Analítico → Resumo (/analytics/invoices), com as imagens trocadas por "[IMG:nome]" pelo
    coletor: por canal (Mercado Livre, Shopee, TikTok Shop, Amazon) × mês, 7 linhas (faturamento, líquido do marketplace,
    lucro bruto, margem, custo de ads, lucro bruto pós ads, MPA). Linha com menos valores que meses (a Amazon começou em
    abril) alinha pela direita. Meses sem ano: o ano de hoje; mês maior que o de hoje = ano passado."""
    from datetime import date
    hoje = hoje or date.today()
    toks = [t.strip() for t in re.split(r"[\n\t]+", str(texto or "")) if t.strip()]
    meses_h = []
    for t in toks:
        if t.upper() in MESES_PT:
            m = MESES_PT[t.upper()]
            ano = hoje.year if m <= hoje.month else hoje.year - 1
            meses_h.append(f"{ano}-{m:02d}")
        elif meses_h and t.upper() not in MESES_PT and len(meses_h) >= 2:
            break
    if not meses_h:
        raise ValueError("não achei os meses (MARÇO, ABRIL…) no texto do Resumo")
    canais = {}
    ordem_padrao = ["Mercado Livre", "Shopee", "TikTok Shop", "Amazon"]      # ordem da tela quando a imagem não diz o canal
    canal, linha, vals, n_blocos = None, None, [], 0
    val_rx = re.compile(r"^-?\s*R\$\s*-?[\d.]+,\d{2}$|^-?[\d.]+,?\d*\s*%$")

    def fechar():
        nonlocal linha, vals
        if canal and linha and vals:
            v = vals[-len(meses_h):]
            ms = meses_h[-len(v):]
            for mes, x in zip(ms, v):
                canais.setdefault(canal, {}).setdefault(mes, {})[linha] = x
        linha, vals = None, []
    for t in toks:
        img = re.match(r"^\[IMG:(.*)\]$", t)
        if img:
            fechar()
            c = _canal_img(img.group(1))
            if c is None and n_blocos < len(ordem_padrao):
                c = ordem_padrao[n_blocos]
            n_blocos += 1
            canal = c
            continue
        k = LINHAS_RESUMO.get(t.lower().rstrip(":").strip())
        if k:
            fechar()
            linha = k
            continue
        if linha and val_rx.match(t):
            if t.endswith("%"):
                vals.append(round(float(t.rstrip("%").replace(".", "").replace(",", ".").replace(" ", "")) / 100, 4))
            else:
                vals.append(_num(t))
        elif linha and t.upper() in MESES_PT:
            continue
    fechar()
    if not canais:
        raise ValueError("não achei as linhas por canal (Faturamento, Líq. do Marketplace…) no texto do Resumo")
    por_mes = {}
    for c, mm in canais.items():
        for mes, d in mm.items():
            p = por_mes.setdefault(mes, {"faturamento": 0.0, "liquido": 0.0, "lucro_bruto": 0.0, "ads": 0.0, "lucro_pos_ads": 0.0})
            for k in p:
                p[k] += float(d.get(k) or 0)
    for mes, p in por_mes.items():
        p["margem"] = round(p["lucro_bruto"] / p["faturamento"], 4) if p["faturamento"] else None
        p["mpa"] = round(p["lucro_pos_ads"] / p["faturamento"], 4) if p["faturamento"] else None
        # custo ≈ líquido − lucro bruto − imposto (2,4% do faturamento): o Resumo não traz o custo dos produtos
        custo = p["liquido"] - p["lucro_bruto"] - p["faturamento"] * IMPOSTO_PCT
        p["custo_aprox"] = round(custo, 2)
        p["markup_aprox"] = round(p["faturamento"] / custo, 4) if custo > 0 and p["faturamento"] else None
        for k in ("faturamento", "liquido", "lucro_bruto", "ads", "lucro_pos_ads"):
            p[k] = round(p[k], 2)
    return {"meses": meses_h, "canais": canais, "por_mes": por_mes}


def gravar_resumo(repo, r, origem="coletor"):
    from datetime import datetime, timezone
    reg = dict(r, origem=origem, em=datetime.now(timezone.utc).isoformat())
    repo._req("POST", "ia_resumos", corpo=[{"chave": RESUMO, "ia": "Gestor Seller (Resumo analítico)",
                                            "texto": json.dumps(reg, ensure_ascii=False)}],
              prefer="resolution=merge-duplicates,return=minimal")
    return reg


def ler_resumo_gravado(repo):
    r = (repo._req("GET", "ia_resumos", {"select": "texto", "chave": f"eq.{RESUMO}"}) or [None])[0]
    try:
        return json.loads(r["texto"]) if r and r.get("texto") else None
    except (ValueError, TypeError):
        return None


def markup_ano(ms, resumo, ano):
    """Markup do ano: exato nos meses com DRE (faturamento ÷ custo dos produtos); nos outros, o aproximado do Resumo.
    Devolve {markup, meses: [{mes, markup, exato}], faturamento, custo, so_exatos}."""
    dre = {d["mes"]: d for d in ms if d.get("markup")}
    aprox = (resumo or {}).get("por_mes") or {}
    linhas, fat, custo, fat_e, custo_e = [], 0.0, 0.0, 0.0, 0.0
    for mes in sorted(set(dre) | set(aprox)):
        if not mes.startswith(str(ano)):
            continue
        if mes in dre:
            d = dre[mes]
            linhas.append({"mes": mes, "markup": d["markup"], "exato": True, "faturamento": d["faturamento"], "custo": d["custo_produtos"]})
            fat += d["faturamento"]; custo += d["custo_produtos"]; fat_e += d["faturamento"]; custo_e += d["custo_produtos"]
        elif aprox[mes].get("markup_aprox"):
            a = aprox[mes]
            linhas.append({"mes": mes, "markup": a["markup_aprox"], "exato": False, "faturamento": a["faturamento"], "custo": a["custo_aprox"]})
            fat += a["faturamento"]; custo += a["custo_aprox"]
    return {"ano": ano, "markup": round(fat / custo, 4) if custo else None, "meses": linhas, "faturamento": round(fat, 2),
            "custo": round(custo, 2), "so_exatos": round(fat_e / custo_e, 4) if custo_e else None,
            "meses_exatos": sum(1 for l in linhas if l["exato"])}


def painel(repo, hoje=None):
    from datetime import date
    hoje = hoje or date.today()
    ms = meses(repo)
    resumo = ler_resumo_gravado(repo)
    return {"meses": ms, "markup_medio": markup_medio(ms), "canais": list(CANAIS), "resumo": resumo,
            "markup_ano": markup_ano(ms, resumo, hoje.year), "markup_12m": markup_12m(ms, resumo, hoje),
            "estoque": markup_para_estoque(repo, hoje)}


def _meses_fechados(hoje, n=12):
    """Os `n` últimos meses FECHADOS (o mês de hoje fica de fora), do mais velho para o mais novo."""
    a, m, out = hoje.year, hoje.month, []
    for _ in range(n):
        m -= 1
        if m == 0:
            a, m = a - 1, 12
        out.append(f"{a}-{m:02d}")
    return out[::-1]


def markup_12m(ms, resumo, hoje):
    """Markup dos últimos 12 meses fechados (Σ faturamento ÷ Σ custo): exato nos meses com DRE, aproximado do Resumo nos
    outros. Ponderado pelo custo, então mês grande pesa mais que mês pequeno."""
    dre = {d["mes"]: d for d in ms if d.get("markup")}
    aprox = (resumo or {}).get("por_mes") or {}
    linhas, fat, custo = [], 0.0, 0.0
    for mes in _meses_fechados(hoje):
        if mes in dre:
            d = dre[mes]
            linhas.append({"mes": mes, "markup": d["markup"], "exato": True})
            fat += d["faturamento"]; custo += d["custo_produtos"]
        elif (aprox.get(mes) or {}).get("markup_aprox"):
            a = aprox[mes]
            linhas.append({"mes": mes, "markup": a["markup_aprox"], "exato": False})
            fat += a["faturamento"]; custo += a["custo_aprox"]
    if not custo:
        return None
    return {"markup": round(fat / custo, 4), "meses": linhas, "meses_exatos": sum(1 for l in linhas if l["exato"]),
            "faturamento": round(fat, 2), "custo": round(custo, 2)}


def pendente(repo, hoje=None, dias=6):
    """Para o coletor (toda semana): rodar se o Resumo tem mais de `dias` dias (ou nunca veio); `meses` = os 12 meses
    FECHADOS sem DRE + o último mês fechado (para refrescar)."""
    from datetime import date, datetime
    hoje = hoje or date.today()
    r = ler_resumo_gravado(repo) or {}
    velho = True
    if r.get("em"):
        try:
            velho = (hoje - datetime.fromisoformat(r["em"].replace("Z", "+00:00")).date()).days >= dias
        except ValueError:
            velho = True
    tem = {d["mes"] for d in meses(repo)}
    fechados = _meses_fechados(hoje)
    faltam = [m for m in fechados if m not in tem]
    if fechados[-1] not in faltam and velho:
        faltam.append(fechados[-1])
    return {"rodar": bool(velho or faltam), "resumo": velho, "meses": faltam, "ultimo_resumo": r.get("em")}


def markup_para_estoque(repo, hoje=None):
    """O markup que o estoque usa no potencial de vendas: média ponderada dos últimos 12 meses fechados (exato onde tem DRE,
    aproximado do Resumo nos outros). Bruno: "tem que pegar um médio", não um mês só."""
    from datetime import date
    hoje = hoje or date.today()
    m = markup_12m(meses(repo), ler_resumo_gravado(repo), hoje)
    if not m:
        return None
    n, e = len(m["meses"]), m["meses_exatos"]
    fonte = f"média de {n} {'mês' if n == 1 else 'meses'} ({m['meses'][0]['mes']} a {m['meses'][-1]['mes']})"
    fonte += ", todos pelo DRE" if e == n else f", {e} pelo DRE e {n - e} aproximados pelo Resumo"
    return {"markup": m["markup"], "fonte": fonte, "exato": e == n, "meses": n, "meses_exatos": e}
