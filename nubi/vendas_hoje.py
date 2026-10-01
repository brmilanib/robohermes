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


def _anuncios(linhas):
    out = []
    for c in linhas or []:
        if len(c) < 4:
            continue
        partes = [x.strip() for x in str(c[1]).split("\n") if x.strip()]
        loja = partes[1] if len(partes) > 1 else ""
        m = re.match(r"(.*?)\s*\[(.*?)\]\s*$", loja)
        out.append({"titulo": partes[0][:200] if partes else "", "loja": (m.group(1) if m else loja)[:80],
                    "plataforma": (m.group(2) if m else "")[:40], "unidades": num_br(c[-2]), "valor": num_br(c[-1])})
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
               "anuncios": _anuncios(x.get("anuncios")), "lojas": _lojas(x.get("lojas")),
               "series": (x.get("series") or [])[:4], "hora_upseller": str(x.get("hora_upseller") or "")[:20]}
    _gravar(repo, AGORA, leitura)
    if x.get("respostas"):                             # respostas JSON da página (para ler a curva por hora no futuro)
        _gravar(repo, BRUTO, {"em": agora.isoformat(), "respostas": x["respostas"][:10]})
    d = _ler(repo, chave_dia(dia)) or {"dia": dia, "pontos": {}}
    d["pontos"][faixa(agora)] = {"valor": valor, "pedidos": int(pedidos), "lido_em": agora.isoformat()}
    d["lojas"] = leitura["lojas"]
    d["anuncios"] = leitura["anuncios"][:10]
    if leitura["series"]:
        d["series"] = leitura["series"]
    _gravar(repo, chave_dia(dia), d)
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


def por_hora(c):
    """Vendido em cada hora (diferença do acumulado), a partir da curva de meia hora."""
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
        out.append({"hora": h, "valor": round(max(0.0, x["valor"] - antes["valor"]), 2),
                    "pedidos": max(0, (x["pedidos"] or 0) - (antes["pedidos"] or 0))})
        antes = x
    return out


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
    hora = faixa(agora) if dia == hoje else "23:30"
    atual, antes = no_horario(cd, hora), no_horario(ck, hora)
    ult = _ler(repo, AGORA) or {}
    return {"hoje": hoje, "dia": dia, "comparar": comparar, "hora": hora, "agora": ult if dia == hoje else None,
            "curva": cd, "curva_comparar": ck, "por_hora": por_hora(cd), "por_hora_comparar": por_hora(ck),
            "picos": picos(por_hora(cd)), "picos_comparar": picos(por_hora(ck)),
            "ate_agora": atual, "ate_agora_comparar": antes,
            "total": (d or {}).get("total_final") or (cd[-1] if cd and cd[-1]["valor"] is not None else None),
            "total_comparar": (k or {}).get("total_final") or (ck[-1] if ck and ck[-1]["valor"] is not None else None),
            "lojas": (d or {}).get("lojas") or [], "anuncios": (d or {}).get("anuncios") or [],
            "dias": dias_guardados(repo)}
