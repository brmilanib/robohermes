# -*- coding: utf-8 -*-
"""
📟 Monitor do nubi (01/10, pedido do Bruno: "um monitor de bancos de dados nosso, memória e base de conhecimento com dados e
evolução deles em um dashboard; também os dados das máquinas: processamento, temperatura, memória, GPU").

- Banco: 1 vez por dia (rotina `monitor`, 03:20) a função SQL `nubi_tamanhos()` (linhas e bytes de cada tabela) é gravada
  em `monitor_banco` (data, tabela): a tela mostra o tamanho de hoje e a evolução (7 e 30 dias).
- Memória e base de conhecimento: as tabelas `saber`, `saber_trechos`, `conhecimento`, `ia_resumos`, `reuniao_mensagens`,
  `tarefa_eventos` (grupo MEMORIA) e a base por tipo (`nubi_saber_tipos()`).
- Máquinas: `servidor_metricas` (Mac, Dell e gamdias mandam CPU, memória, disco, temperatura e GPU a cada 5 min no
  mac_tick; `origem` = nome da máquina). A tela mostra a última leitura e as últimas 24 h.
"""
import json
from datetime import datetime, timedelta, timezone

MEMORIA = ("saber", "saber_trechos", "conhecimento", "ia_resumos", "reuniao_mensagens", "tarefa_eventos", "atendimento_kb")
DADOS = ("anuncios", "snapshots", "vend_anuncios", "vend_vendas_dia", "vend_produto_dia", "vend_anuncios_ml", "estoque_itens",
         "ranking_linhas", "produto_grupos", "marcas_config")
MAQUINAS_NOME = {"mac_mini": "Mac mini", "gamdias": "gamdias (PC de casa)", "dell": "Dell (escritório)"}


def _hoje(agora=None):
    return ((agora or datetime.now(timezone.utc)) - timedelta(hours=3)).date()


def coletar(repo, agora=None, forcar=False):
    """Guarda a foto do banco de hoje em monitor_banco (1 vez por dia; `forcar` regrava). -> texto para a rotina."""
    hoje = _hoje(agora).isoformat()
    if not forcar and repo._req("GET", "monitor_banco", {"select": "tabela", "data": f"eq.{hoje}", "limit": 1}):
        return "foto do banco de hoje já guardada"
    linhas = repo._req("POST", "rpc/nubi_tamanhos", corpo={}) or []
    regs = [{"data": hoje, "tabela": str(x.get("tabela"))[:80], "linhas": int(x.get("linhas") or 0), "bytes": int(x.get("bytes") or 0)}
            for x in linhas if x.get("tabela")]
    if not regs:
        return "sem leitura do banco (função nubi_tamanhos)"
    repo._req("POST", "monitor_banco", {"on_conflict": "data,tabela"}, corpo=regs, prefer="resolution=merge-duplicates,return=minimal")
    total = sum(r["bytes"] for r in regs)
    return f"{len(regs)} tabela(s), {total / 1e6:.1f} MB"


def _serie_banco(repo, dias=30, agora=None):
    """{tabela: {data: (linhas, bytes)}} dos últimos `dias`."""
    desde = (_hoje(agora) - timedelta(days=dias)).isoformat()
    out = {}
    for r in repo._todos("monitor_banco", {"select": "data,tabela,linhas,bytes", "data": f"gte.{desde}", "order": "data"}):
        out.setdefault(r["tabela"], {})[str(r["data"])[:10]] = (int(r.get("linhas") or 0), int(r.get("bytes") or 0))
    return out


def _grupo(tabela):
    if tabela in MEMORIA:
        return "memoria"
    if tabela in DADOS or tabela.startswith("vend_") or tabela.startswith("ranking"):
        return "dados"
    if tabela in ("servidor_metricas", "monitor_banco", "agentes_uso", "agente_execucoes", "rotinas_execucoes", "coletor_execucoes",
                  "coletor_fotos", "mac_comandos", "ia_lotes"):
        return "operacao"
    return "outros"


def _var(atual, antigo):
    if antigo is None:
        return None
    return atual - antigo


def painel(repo, agora=None):
    agora = agora or datetime.now(timezone.utc)
    hoje = _hoje(agora)
    serie = _serie_banco(repo, 30, agora)
    if not serie:                                     # primeira vez: lê agora e guarda
        try:
            coletar(repo, agora)
            serie = _serie_banco(repo, 30, agora)
        except Exception:  # noqa: BLE001
            serie = {}
    d7, d30 = (hoje - timedelta(days=7)).isoformat(), (hoje - timedelta(days=30)).isoformat()
    tabelas = []
    for t, pontos in serie.items():
        datas = sorted(pontos)
        ult = pontos[datas[-1]]
        a7 = next((pontos[d] for d in datas if d <= d7), None)
        a30 = next((pontos[d] for d in datas if d <= d30), None)
        if a7 is None and len(datas) > 1 and datas[0] < datas[-1]:
            a7 = pontos[datas[0]]                     # menos de 7 dias de histórico: compara com o 1º ponto
        tabelas.append({"tabela": t, "grupo": _grupo(t), "linhas": ult[0], "bytes": ult[1], "data": datas[-1],
                        "linhas_7d": _var(ult[0], a7[0] if a7 else None), "bytes_7d": _var(ult[1], a7[1] if a7 else None),
                        "linhas_30d": _var(ult[0], a30[0] if a30 else None), "bytes_30d": _var(ult[1], a30[1] if a30 else None),
                        "serie_bytes": [pontos[d][1] for d in datas[-30:]], "serie_linhas": [pontos[d][0] for d in datas[-30:]]})
    tabelas.sort(key=lambda x: -x["bytes"])
    total = {"bytes": sum(x["bytes"] for x in tabelas), "linhas": sum(x["linhas"] for x in tabelas), "tabelas": len(tabelas),
             "bytes_7d": sum(x["bytes_7d"] or 0 for x in tabelas), "linhas_7d": sum(x["linhas_7d"] or 0 for x in tabelas)}
    grupos = {}
    for x in tabelas:
        g = grupos.setdefault(x["grupo"], {"grupo": x["grupo"], "bytes": 0, "linhas": 0, "tabelas": 0, "bytes_7d": 0, "linhas_7d": 0})
        g["bytes"] += x["bytes"]; g["linhas"] += x["linhas"]; g["tabelas"] += 1
        g["bytes_7d"] += x["bytes_7d"] or 0; g["linhas_7d"] += x["linhas_7d"] or 0
    # datas com foto (para o gráfico do total)
    datas = sorted({d for p in serie.values() for d in p})
    total["serie"] = [{"data": d, "bytes": sum(p[d][1] for p in serie.values() if d in p), "linhas": sum(p[d][0] for p in serie.values() if d in p)}
                      for d in datas[-30:]]
    try:
        saber_tipos = repo._req("POST", "rpc/nubi_saber_tipos", corpo={}) or []
    except Exception:  # noqa: BLE001
        saber_tipos = []
    return {"hoje": hoje.isoformat(), "total": total, "grupos": sorted(grupos.values(), key=lambda g: -g["bytes"]), "tabelas": tabelas,
            "saber_tipos": [{"tipo": x.get("tipo"), "n": int(x.get("n") or 0), "ultimo": x.get("ultimo")} for x in saber_tipos],
            "maquinas": maquinas(repo, agora)}


def maquinas(repo, agora=None, horas=24):
    """Última leitura e a série das últimas `horas` de cada máquina (servidor_metricas por origem)."""
    agora = agora or datetime.now(timezone.utc)
    desde = (agora - timedelta(hours=horas)).isoformat()
    por = {}
    for r in repo._todos("servidor_metricas", {"select": "coletado_em,origem,cpu_pct,mem_pct,disco_pct,temp_c,gpu_pct,gpu_mem_pct,gpu_temp_c,alertas,status,agentes",
                                               "coletado_em": f"gte.{desde}", "order": "coletado_em"}):
        por.setdefault(r.get("origem") or "mac_mini", []).append(r)
    out = []
    for origem, xs in por.items():
        ult = xs[-1]
        try:
            visto = datetime.fromisoformat(str(ult["coletado_em"]).replace("Z", "+00:00"))
            atraso = (agora - visto).total_seconds() / 60
        except ValueError:
            atraso = None
        passo = max(1, len(xs) // 96)                 # até ~96 pontos (24 h de 15 em 15 min)
        amostra = xs[::passo] if passo > 1 else xs
        if amostra and amostra[-1] is not ult:
            amostra = amostra + [ult]
        serie = {k: [x.get(k) for x in amostra] for k in ("cpu_pct", "mem_pct", "disco_pct", "temp_c", "gpu_pct", "gpu_mem_pct", "gpu_temp_c")}
        serie["t"] = [x.get("coletado_em") for x in amostra]
        maximos = {k: max((float(v) for v in serie[k] if v is not None), default=None) for k in ("cpu_pct", "mem_pct", "temp_c", "gpu_pct")}
        out.append({"origem": origem, "nome": MAQUINAS_NOME.get(origem, origem), "ultimo": ult, "atraso_min": round(atraso, 1) if atraso is not None else None,
                    "fora_do_ar": atraso is None or atraso > 15, "serie": serie, "maximos_24h": maximos, "leituras_24h": len(xs),
                    "ip": ip_da_maquina(repo, origem, agora)})
    out.sort(key=lambda m: (m["fora_do_ar"], m["origem"]))
    return out


IP_TROCAR_DIAS = 30


def ip_da_maquina(repo, origem, agora=None):
    """01/10 (Bruno: "colocar os IPs no monitor, controlar há quanto tempo e trocar 1 vez por mês"): IP público atual da
    máquina (extras.ip da última leitura), desde quando está com ele e se já passou do prazo de trocar (reiniciar o roteador)."""
    agora = agora or datetime.now(timezone.utc)
    try:
        ult = (repo._req("GET", "servidor_metricas", {"select": "coletado_em,extras", "origem": f"eq.{origem}", "extras->>ip": "not.is.null",
                                                      "order": "coletado_em.desc", "limit": 1}) or [None])[0]
    except Exception:  # noqa: BLE001
        ult = None
    ip = ((ult or {}).get("extras") or {}).get("ip") if ult else None
    if not ip:
        return None
    try:   # a última leitura com OUTRO ip = quando o atual começou (sem outra: a 1ª leitura com este ip)
        troca = (repo._req("GET", "servidor_metricas", {"select": "coletado_em", "origem": f"eq.{origem}", "extras->>ip": f"neq.{ip}",
                                                        "order": "coletado_em.desc", "limit": 1}) or [None])[0]
        if troca:
            desde = troca["coletado_em"]
        else:
            prim = (repo._req("GET", "servidor_metricas", {"select": "coletado_em", "origem": f"eq.{origem}", "extras->>ip": f"eq.{ip}",
                                                           "order": "coletado_em", "limit": 1}) or [None])[0]
            desde = (prim or ult)["coletado_em"]
        dias = (agora - datetime.fromisoformat(str(desde).replace("Z", "+00:00"))).total_seconds() / 86400
    except Exception:  # noqa: BLE001
        desde, dias = None, None
    return {"ip": ip, "desde": desde, "dias": round(dias, 1) if dias is not None else None,
            "trocar": bool(dias is not None and dias >= IP_TROCAR_DIAS)}


def _json(x):
    return json.dumps(x, ensure_ascii=False)
