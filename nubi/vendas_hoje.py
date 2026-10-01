# -*- coding: utf-8 -*-
"""
📊 Vendas de hoje (01/10, pedido do Bruno com o print de UpSeller → Análises → Visão geral: "a tela atualiza a cada 5 min
e não exporta; lê os números de 10 em 10 min e guarda a cada meia hora quanto vendeu no total, para eu comparar o 10/10
com o 09/09, hora a hora, e achar os picos para o marketing").

O coletor do Mac lê a tela (`coletor.py upseller-hoje`, chamado pelo vigia) e manda para `vendas_hoje_salvar`.
Guardado em `ia_resumos` (sem tabela nova):
  vendas_hoje|agora        a última leitura completa (KPIs, ranking de anúncio e de loja, erro se houver)
  vendas_hoje|AAAA-MM-DD   o dia: {"pontos": {"HH:MM": {valor, pedidos, lido_em}}, "lojas", "total_final"}
                           HH:MM = faixa de meia hora (00:00, 00:30…); vale a última leitura da faixa (acumulado).
O "ontem inteiro" que a tela mostra fecha o dia anterior em `total_final`.
"""
import json
import re
from datetime import datetime, timedelta, timezone

BRASILIA = timezone(timedelta(hours=-3))
AGORA = "vendas_hoje|agora"
BRUTO = "vendas_hoje|bruto"
INTERVALO_MIN = 9                      # o vigia passa a cada ~5 min; lê de novo depois de 9 min


class ErroVendasHoje(Exception):
    pass


def chave_dia(dia):
    return f"vendas_hoje|{dia}"


def _ler(repo, chave):
    r = (repo._req("GET", "ia_resumos", {"select": "texto,criado_em", "chave": f"eq.{chave}"}) or [None])[0]
    try:
        return json.loads(r["texto"]) if r and r.get("texto") else None
    except (TypeError, ValueError):
        return None


def _gravar(repo, chave, valor):
    repo._req("POST", "ia_resumos", corpo=[{"chave": chave, "ia": "coletor", "criado_em": datetime.now(timezone.utc).isoformat(),
                                            "texto": json.dumps(valor, ensure_ascii=False)}],
              prefer="resolution=merge-duplicates,return=minimal")


def num_br(t):
    """'14.995,73' -> 14995.73; '64' -> 64.0; lixo -> None."""
    t = str(t or "").strip()
    if not re.fullmatch(r"\d{1,3}(\.\d{3})*(,\d{1,2})?|\d+(,\d{1,2})?", t):
        return None
    return float(t.replace(".", "").replace(",", "."))


def faixa(agora):
    return f"{agora.hour:02d}:{0 if agora.minute < 30 else 30:02d}"


def _kpi(k):
    ns = [num_br(x) for x in (k or {}).get("nums") or []]
    ns = [x for x in ns if x is not None]
    return (ns + [None, None, None])[:3]          # hoje, ontem inteiro, ontem até o mesmo horário


def _foto_ok(u):
    """Só link https de imagem (a foto do anúncio que o UpSeller mostra); nada de data:, javascript: ou http."""
    u = str(u or "").strip()
    return u if re.fullmatch(r"https://[\w.-]+/[^\s\"'<>]{1,380}", u) else None


def _anuncios(linhas, fotos=None):
    out = []
    fotos = list(fotos or [])
    for i, c in enumerate(linhas or []):
        if len(c) < 4:
            continue
        partes = [x.strip() for x in str(c[1]).split("\n") if x.strip()]
        loja = partes[1] if len(partes) > 1 else ""
        m = re.match(r"(.*?)\s*\[(.*?)\]\s*$", loja)
        out.append({"titulo": partes[0][:200] if partes else "", "loja": (m.group(1) if m else loja)[:80],
                    "plataforma": (m.group(2) if m else "")[:40], "unidades": num_br(c[-2]), "valor": num_br(c[-1]),
                    "foto": _foto_ok(fotos[i]) if i < len(fotos) else None})
    return out[:20]


def _lojas(linhas):
    out = []
    for c in linhas or []:
        if len(c) < 4:
            continue
        partes = [x.strip() for x in str(c[1]).split("\n") if x.strip()]
        txt = " ".join(partes)
        m = re.match(r"(.*?)\s*\[(.*?)\]\s*$", txt)
        out.append({"loja": (m.group(1) if m else txt)[:80], "plataforma": (m.group(2) if m else "")[:40],
                    "pedidos": num_br(c[-2]), "valor": num_br(c[-1])})
    return out[:30]


def salvar(repo, x, agora=None):
    """Leitura do coletor -> última leitura + ponto da meia hora no dia. Devolve um resumo para o log do Mac."""
    agora = (agora or datetime.now(timezone.utc)).astimezone(BRASILIA)
    if x.get("erro"):
        ult = _ler(repo, AGORA) or {}
        ult.update(erro=str(x["erro"])[:500], erro_em=agora.isoformat(), login=bool(x.get("login")))
        _gravar(repo, AGORA, ult)
        return {"ok": False, "resumo": "erro guardado"}
    valor, valor_ontem, valor_mesmo = _kpi(x.get("valor"))
    pedidos, ped_ontem, ped_mesmo = _kpi(x.get("pedidos"))
    if valor is None or pedidos is None:
        raise ErroVendasHoje("não achei 'Valor de Vendas Válidas' e 'Pedidos Válidos' na leitura")
    dia = agora.date().isoformat()
    leitura = {"lido_em": agora.isoformat(), "dia": dia, "valor": valor, "pedidos": int(pedidos),
               "valor_ontem": valor_ontem, "pedidos_ontem": int(ped_ontem) if ped_ontem is not None else None,
               "valor_ontem_mesmo": valor_mesmo, "pedidos_ontem_mesmo": int(ped_mesmo) if ped_mesmo is not None else None,
               "anuncios": _anuncios(x.get("anuncios"), x.get("fotos_anuncios")), "lojas": _lojas(x.get("lojas")),
               "series": (x.get("series") or [])[:4], "hora_upseller": str(x.get("hora_upseller") or "")[:20]}
    _gravar(repo, AGORA, leitura)
    if x.get("respostas"):                             # respostas JSON da página (para ler a curva por hora no futuro)
        _gravar(repo, BRUTO, {"em": agora.isoformat(), "respostas": x["respostas"][:10]})
    d = _ler(repo, chave_dia(dia)) or {"dia": dia, "pontos": {}}
    d["pontos"][faixa(agora)] = {"valor": valor, "pedidos": int(pedidos), "lido_em": agora.isoformat()}
    d["lojas"] = leitura["lojas"]
    d["anuncios"] = leitura["anuncios"][:10]
    # 01/10 (modo TV): ranking de cada meia hora, para dizer quem sobe e quem cai contra ontem no mesmo horário
    if leitura["anuncios"] or leitura["lojas"]:        # leitura sem a tabela não apaga o ranking da faixa
        d.setdefault("ranking", {})[faixa(agora)] = {
            "anuncios": [{k: a.get(k) for k in ("titulo", "loja", "plataforma", "unidades", "valor", "foto")} for a in leitura["anuncios"][:10]],
            "lojas": [{k: l[k] for k in ("loja", "plataforma", "pedidos", "valor")} for l in leitura["lojas"]]}
    if leitura["series"]:
        d["series"] = leitura["series"]
    _gravar(repo, chave_dia(dia), d)
    try:
        gravar_picos(repo, d)
    except Exception:  # noqa: BLE001 — o histórico de picos nunca derruba a leitura
        pass
    if valor_ontem is not None:                        # fecha o dia anterior com o total que o UpSeller mostra
        ontem = (agora.date() - timedelta(days=1)).isoformat()
        o = _ler(repo, chave_dia(ontem))
        if o is not None and (o.get("total_final") or {}).get("valor") != valor_ontem:
            o["total_final"] = {"valor": valor_ontem, "pedidos": leitura["pedidos_ontem"]}
            _gravar(repo, chave_dia(ontem), o)
    return {"ok": True, "resumo": f"{dia} {faixa(agora)}: R$ {valor:,.2f} em {int(pedidos)} pedidos"}


def pendente(repo, agora=None, ativo=True):
    """O vigia do Mac pergunta: está na hora de ler de novo (última leitura há 9 min ou mais)?"""
    if not ativo:
        return {"rodar": False}
    agora = agora or datetime.now(timezone.utc)
    ult = _ler(repo, AGORA) or {}
    quando = max([t for t in (ult.get("lido_em"), ult.get("erro_em")) if t] or [""])
    if not quando:
        return {"rodar": True}
    try:
        passou = (agora - datetime.fromisoformat(quando)).total_seconds() / 60
    except ValueError:
        return {"rodar": True}
    return {"rodar": passou >= INTERVALO_MIN, "minutos": round(passou, 1)}


# ---------- curva do dia, comparação e picos ----------
FAIXAS = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)]


def curva(d):
    """Acumulado em cada meia hora (fim da faixa), preenchendo faixas sem leitura com o último valor conhecido; faixas
    depois da última leitura ficam None (o dia ainda não chegou lá)."""
    pts = (d or {}).get("pontos") or {}
    if not pts:
        return []
    ultima = max(pts)
    out, atual = [], {"valor": 0.0, "pedidos": 0}
    for f in FAIXAS:
        if f > ultima:
            out.append({"hora": f, "valor": None, "pedidos": None})
            continue
        if f in pts:
            atual = {"valor": pts[f]["valor"], "pedidos": pts[f]["pedidos"]}
        out.append({"hora": f, "valor": atual["valor"], "pedidos": atual["pedidos"]})
    fim = (d or {}).get("total_final")
    if fim and fim.get("valor") is not None:           # dia fechado: a última faixa vale o total que o UpSeller mostrou
        for x in out:
            if x["valor"] is None:
                x["valor"], x["pedidos"] = fim["valor"], fim.get("pedidos")
    return out


def por_hora(c, lidas=None):
    """Vendido em cada hora (diferença do acumulado), a partir da curva de meia hora. `lidas` = faixas com leitura de
    verdade (sem ela, não confere buracos)."""
    fim_hora = {x["hora"][:2]: x for x in c if x["hora"].endswith(":30") and x["valor"] is not None}
    for x in c:                                        # hora em andamento (só a faixa :00 lida): parcial
        if x["hora"].endswith(":00") and x["valor"] is not None and x["hora"][:2] not in fim_hora:
            fim_hora[x["hora"][:2]] = x
    out, antes = [], {"valor": 0.0, "pedidos": 0}
    for h in range(24):
        x = fim_hora.get(f"{h:02d}")
        if not x or x["valor"] is None:
            out.append({"hora": h, "valor": None, "pedidos": None})
            continue
        # 01/10 (print do Bruno: "18h R$ 15.100" no 1º dia, o coletor começou às 18h): sem leitura na hora anterior, a
        # diferença junta horas que não foram lidas — não é venda dessa hora (fica None, marcada como "acumulado")
        if lidas is not None and h and not lidas & {f"{h - 1:02d}:00", f"{h - 1:02d}:30"}:
            out.append({"hora": h, "valor": None, "pedidos": None, "acumulado": round(max(0.0, x["valor"] - antes["valor"]), 2)})
            antes = x
            continue
        out.append({"hora": h, "valor": round(max(0.0, x["valor"] - antes["valor"]), 2),
                    "pedidos": max(0, (x["pedidos"] or 0) - (antes["pedidos"] or 0))})
        antes = x
    return out


def lidas_do(d):
    """Faixas de meia hora com leitura de verdade no dia (dia fechado pelo total_final conta a última)."""
    return set(((d or {}).get("pontos") or {}).keys()) if d else None


def por_hora_lojas(d):
    """01/10 (Bruno: "gravar todos os picos, para identificar os melhores picos de venda de cada loja"): vendido por hora em
    cada loja, pelo ranking de loja guardado a cada meia hora (acumulado do dia). Hora sem leitura na anterior = None."""
    rk = (d or {}).get("ranking") or {}
    if not rk:
        return {}
    lidas = set(rk)
    lojas = {}
    for f in sorted(rk):
        for l in rk[f].get("lojas") or []:
            lojas.setdefault(f"{l.get('loja')} · {l.get('plataforma')}", {})[f] = l
    out = {}
    for k, pts in lojas.items():
        fim = {}
        for f in sorted(pts):                                # última leitura de cada hora
            fim[f[:2]] = pts[f]
        horas, antes = [], {"valor": 0.0, "pedidos": 0}
        for h in range(24):
            x = fim.get(f"{h:02d}")
            if not x or x.get("valor") is None:
                # a loja não apareceu nessa hora: se houve leitura (outras lojas), ela não vendeu o bastante para o ranking
                horas.append(None)
                continue
            if h and not lidas & {f"{h - 1:02d}:00", f"{h - 1:02d}:30"}:
                horas.append(None)
            else:
                horas.append(round(max(0.0, (x["valor"] or 0) - (antes["valor"] or 0)), 2))
            antes = x
        out[k] = horas
    return out


PICOS = "vendas_hoje|picos"
PICOS_DIAS = 400


def gravar_picos(repo, d):
    """Guarda no banco o vendido por hora do dia (geral e por loja) em `vendas_hoje|picos` {dia: {...}} — base para os
    melhores horários de cada loja (comparação entre dias)."""
    ph = por_hora(curva(d), lidas_do(d))
    hist = _ler(repo, PICOS) or {}
    hist[d["dia"]] = {"geral": [x["valor"] for x in ph], "pedidos": [x["pedidos"] for x in ph],
                      "lojas": por_hora_lojas(d), "picos": picos(ph, 5)}
    for k in sorted(hist)[:-PICOS_DIAS]:
        hist.pop(k, None)
    _gravar(repo, PICOS, hist)


def melhores_horarios(repo, dias=30, hoje=None):
    """Média do vendido em cada hora nos últimos `dias` dias guardados (só horas com leitura), geral e por loja; os 3
    melhores horários de cada loja e o dia da semana mais forte."""
    hist = _ler(repo, PICOS) or {}
    ks = sorted(k for k in hist if not hoje or k < hoje)[-dias:]
    def media(listas):
        out = []
        for h in range(24):
            vs = [l[h] for l in listas if l and h < len(l) and l[h] is not None]
            out.append(round(sum(vs) / len(vs), 2) if vs else None)
        return out
    geral = media([hist[k].get("geral") for k in ks])
    por_loja = {}
    for k in ks:
        for loja, v in (hist[k].get("lojas") or {}).items():
            por_loja.setdefault(loja, []).append(v)
    lojas = []
    for loja, ls in por_loja.items():
        m = media(ls)
        top = sorted([(h, v) for h, v in enumerate(m) if v], key=lambda x: -x[1])[:3]
        nome, _, plat = loja.partition(" · ")
        lojas.append({"loja": nome, "plataforma": plat, "dias": len(ls), "media": m,
                      "melhores": [{"hora": f"{h:02d}h", "valor": v} for h, v in top]})
    lojas.sort(key=lambda x: -sum(v or 0 for v in x["media"]))
    sem = {}
    for k in ks:
        tot = sum(v for v in (hist[k].get("geral") or []) if v)
        if tot:
            sem.setdefault(datetime.fromisoformat(k).weekday(), []).append(tot)
    nomes = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    semana = [{"dia": nomes[w], "media": round(sum(v) / len(v), 2), "dias": len(v)} for w, v in sorted(sem.items())]
    top_g = sorted([(h, v) for h, v in enumerate(geral) if v], key=lambda x: -x[1])[:3]
    return {"dias": len(ks), "geral": geral, "melhores": [{"hora": f"{h:02d}h", "valor": v} for h, v in top_g],
            "lojas": lojas[:12], "semana": semana}


def picos(ph, n=3):
    xs = sorted([x for x in ph if x["valor"]], key=lambda x: -x["valor"])[:n]
    return [{"hora": f"{x['hora']:02d}h", "valor": x["valor"], "pedidos": x["pedidos"]} for x in xs]


def no_horario(c, hora):
    """Acumulado do dia até a faixa `hora` (HH:MM)."""
    x = next((p for p in c if p["hora"] == hora), None)
    return x if x and x["valor"] is not None else None


def dias_guardados(repo, limite=120):
    rs = repo._req("GET", "ia_resumos", {"select": "chave", "chave": "like.vendas_hoje|2*", "order": "chave.desc",
                                         "limit": limite}) or []
    return [r["chave"].split("|", 1)[1] for r in rs]


def painel(repo, dia=None, comparar=None, agora=None):
    agora = (agora or datetime.now(timezone.utc)).astimezone(BRASILIA)
    hoje = agora.date().isoformat()
    dia = dia or hoje
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dia) or (comparar and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", comparar)):
        raise ErroVendasHoje("data inválida (AAAA-MM-DD)")
    comparar = comparar or (datetime.fromisoformat(dia) - timedelta(days=1)).date().isoformat()
    d, k = _ler(repo, chave_dia(dia)), _ler(repo, chave_dia(comparar))
    cd, ck = curva(d), curva(k)
    ph, pk = por_hora(cd, lidas_do(d)), por_hora(ck, lidas_do(k))
    hora = faixa(agora) if dia == hoje else "23:30"
    atual, antes = no_horario(cd, hora), no_horario(ck, hora)
    ult = _ler(repo, AGORA) or {}
    return {"hoje": hoje, "dia": dia, "comparar": comparar, "hora": hora, "agora": ult if dia == hoje else None,
            "curva": cd, "curva_comparar": ck, "por_hora": ph, "por_hora_comparar": pk,
            "picos": picos(ph), "picos_comparar": picos(pk),
            "ate_agora": atual, "ate_agora_comparar": antes,
            "total": (d or {}).get("total_final") or (cd[-1] if cd and cd[-1]["valor"] is not None else None),
            "total_comparar": (k or {}).get("total_final") or (ck[-1] if ck and ck[-1]["valor"] is not None else None),
            "lojas": (d or {}).get("lojas") or [], "anuncios": (d or {}).get("anuncios") or [],
            "dias": dias_guardados(repo), "horarios": melhores_horarios(repo, 30, hoje)}


# ---------- 📺 Modo TV (01/10, Bruno: "um modo TV para eu ficar olhando ao vivo: vendas, chats, ranking dos campeões, se
# estamos crescendo ou caindo") ----------
def _ranking_ate(d, hora):
    """Ranking guardado na faixa `hora` ou na última antes dela (o de ontem no mesmo horário)."""
    rk = (d or {}).get("ranking") or {}
    fx = [f for f in sorted(rk) if f <= hora]
    return rk[fx[-1]] if fx else None


def _chave(titulo, loja):
    return re.sub(r"\W+", " ", f"{titulo} {loja}".lower()).strip()


def tv(repo, agora=None):
    agora = (agora or datetime.now(timezone.utc)).astimezone(BRASILIA)
    hoje = agora.date().isoformat()
    ontem = (agora.date() - timedelta(days=1)).isoformat()
    semana = (agora.date() - timedelta(days=7)).isoformat()
    p = painel(repo, hoje, ontem, agora=agora)
    ds = _ler(repo, chave_dia(semana))
    cs = curva(ds)
    hora = p["hora"]
    a, b, c = p["ate_agora"], p["ate_agora_comparar"], no_horario(cs, hora)
    # projeção do dia: o ritmo de ontem (total ÷ até este horário) aplicado ao de hoje; senão o da semana passada
    proj = None
    for ate, tot in ((b, p["total_comparar"]), (c, (ds or {}).get("total_final"))):
        if a and ate and tot and ate.get("valor") and tot.get("valor"):
            proj = {"valor": round(a["valor"] * tot["valor"] / ate["valor"], 2), "base": "ontem" if ate is b else "semana passada"}
            break
    # última hora completa x a mesma hora ontem
    h = agora.hour - 1 if agora.hour else 0
    ultima = {"hora": h, "hoje": (p["por_hora"][h] or {}).get("valor"), "ontem": (p["por_hora_comparar"][h] or {}).get("valor")}
    # campeões e lojas: agora x ontem no mesmo horário
    d_ontem = _ler(repo, chave_dia(ontem))
    rk_o = _ranking_ate(d_ontem, hora) or {}
    pos_o = {_chave(x.get("titulo"), x.get("loja")): (i + 1, x) for i, x in enumerate(rk_o.get("anuncios") or [])}
    campeoes = []
    for i, x in enumerate((p["agora"] or {}).get("anuncios") or p["anuncios"] or []):
        o = pos_o.get(_chave(x.get("titulo"), x.get("loja")))
        campeoes.append(dict(x, pos=i + 1, pos_ontem=o[0] if o else None, valor_ontem=(o[1].get("valor") if o else None)))
    lojas_o = {(l.get("loja"), l.get("plataforma")): l for l in rk_o.get("lojas") or []}
    lojas = [dict(l, valor_ontem=(lojas_o.get((l.get("loja"), l.get("plataforma"))) or {}).get("valor"))
             for l in (p["agora"] or {}).get("lojas") or p["lojas"] or []]
    return {"hoje": hoje, "hora": hora, "agora": p["agora"], "ate_agora": a, "ate_ontem": b, "ate_semana": c,
            "total_ontem": p["total_comparar"], "total_semana": (ds or {}).get("total_final"), "projecao": proj,
            "ultima_hora": ultima, "curva": p["curva"], "curva_ontem": p["curva_comparar"], "curva_semana": cs,
            "por_hora": p["por_hora"], "por_hora_ontem": p["por_hora_comparar"], "picos": p["picos"],
            "campeoes": campeoes[:10], "lojas": lojas, "ontem": ontem, "semana": semana,
            "lojas_hora": por_hora_lojas(_ler(repo, chave_dia(hoje))), "horarios": melhores_horarios(repo, 30, hoje)}
