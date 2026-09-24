# -*- coding: utf-8 -*-
"""
Auditoria de dados e código (tarefa de rotina).

1) Conferências fixas nos dados (sem IA, não erram por "achismo"):
   - coleta: vendedor sem o arquivo de algum dos últimos dias;
   - tabela do grupo (Nubimetrics) x soma do export de 1 dia do vendedor: vendas que não batem;
   - soma dos dias do mês x acumulado do mês (foto diária do relatório do mês);
   - dia fora do padrão do vendedor (muito acima ou abaixo da mediana);
   - preço do mesmo produto que mudou demais de um dia para o outro;
   - produtos juntados pela IA com parecença baixa;
   - tarefas de rotina com erro.
2) O ChatGPT analisa as conferências e um trecho do código (um módulo por noite, em rodízio): causa provável,
   correção sugerida e prioridade.
3) Se houver a chave da Anthropic, o Claude revisa a análise do ChatGPT (concorda, discorda, riscos).
Nada é mudado sozinho: o relatório fica na aba Auditoria para o Claude (sessão de código) e o dono lerem.
"""

import os
import statistics
from datetime import date, timedelta

import agentes
import ia

MODULOS = ["nubi_web.py", "vend_bi.py", "vendedores.py", "produtos_iguais.py", "ia.py", "categorias.py", "ranking.py"]


def _f(v):
    v = float(v or 0)
    return f"R$ {v / 1e6:.2f} mi".replace(".", ",") if abs(v) >= 1e6 else f"R$ {v / 1e3:.1f} mil".replace(".", ",")


def conferencias(repo, hoje=None):
    """Lista de achados: {nivel: erro|alerta|info, area, titulo, detalhe}."""
    hoje = hoje or date.today()
    ach = []
    ult = repo._req("GET", "vend_vendas_dia", {"select": "data", "order": "data.desc", "limit": 1}) or []
    if not ult:
        return [{"nivel": "info", "area": "coleta", "titulo": "Ainda sem vendas diárias", "detalhe": ""}]
    fim = date.fromisoformat(str(ult[0]["data"])[:10])
    ini = fim - timedelta(days=20)
    rows = [r for r in repo._todos("rpc/vend_dia_serie", {}, "POST", {"desde": ini.isoformat(), "ate": fim.isoformat()})]
    por_v = {}
    for r in rows:
        por_v.setdefault(r["vendedor"], {})[str(r["data"])[:10]] = float(r["v"] or 0)
    dias7 = [(fim - timedelta(days=i)).isoformat() for i in range(7)]
    ddmm = lambda d: d[8:10] + "/" + d[5:7]
    # coleta em andamento: pedido ainda não atendido ou coleta rodando no Mac -> dia faltando vira alerta, não erro
    andamento = coleta_em_andamento(repo)
    try:
        grupo = repo._todos("vend_grupo_dia", {"select": "data,vendedor,v", "data": f"gte.{ini.isoformat()}"})
    except Exception:  # noqa: BLE001
        grupo = []
    g_v = {(g["vendedor"], str(g["data"])[:10]): g.get("v") for g in grupo}
    g_dias = {str(g["data"])[:10] for g in grupo}
    # 1) coleta: dias faltando nos últimos 7 (e se a tabela do grupo mostra venda nesses dias = falha de download)
    for v, dd in sorted(por_v.items()):
        falt = [d for d in dias7 if d not in dd]
        if falt:
            com_venda = [d for d in falt if float(g_v.get((v, d)) or 0) > 0]
            nivel = "alerta" if andamento else ("erro" if fim.isoformat() in falt or com_venda else "alerta")
            ach.append({"nivel": nivel, "area": "coleta",
                        "titulo": f"{v}: {len(falt)} dia(s) sem o arquivo nos últimos 7" + (" (coleta em andamento)" if andamento else ""),
                        "detalhe": "Dias: " + ", ".join(ddmm(d) for d in sorted(falt))
                        + (f". No grupo com vendas mas sem export (falha de download): {', '.join(ddmm(d) for d in sorted(com_venda))}"
                           if com_venda else "") + (f". {andamento}" if andamento else "")})
    # 1b) vendedor que aparece no grupo com vendas e não tem nenhum export no período
    for gv_nome in sorted({g["vendedor"] for g in grupo} - set(por_v)):
        dias_v = sorted(d for (n, d), x in g_v.items() if n == gv_nome and d in dias7 and float(x or 0) > 0)
        if dias_v:
            ach.append({"nivel": "alerta" if andamento else "erro", "area": "coleta",
                        "titulo": f"{gv_nome}: no grupo com vendas mas sem export (falha de download)",
                        "detalhe": "Dias com venda no grupo e sem o arquivo do dia: " + ", ".join(ddmm(d) for d in dias_v)})
    # 1c) vendedor com export do dia mas ausente da tabela do grupo nesse dia (saiu do grupo ou mudou de nome)
    for v, dd in sorted(por_v.items()):
        aus = sorted(d for d in dias7 if d in dd and d in g_dias and (v, d) not in g_v)
        if aus:
            ach.append({"nivel": "alerta", "area": "cadastro", "titulo": f"{v}: ausente da tabela do grupo",
                        "detalhe": "Tem o export do dia mas não aparece no grupo em: " + ", ".join(ddmm(d) for d in aus)
                        + ". Conferir se saiu do grupo ou mudou de nome no Nubimetrics."})
    difs = []
    for g in grupo:
        d = str(g["data"])[:10]
        dia = por_v.get(g["vendedor"], {}).get(d)
        if g.get("v") is None or dia is None:
            continue
        gv = float(g["v"])
        if abs(gv - dia) > max(500, 0.03 * max(gv, dia)):
            difs.append((g["vendedor"], d, gv, dia))
    for v, d, gv, dia in sorted(difs, key=lambda t: -abs(t[2] - t[3]))[:15]:
        ach.append({"nivel": "erro", "area": "dados", "titulo": f"{v} em {d[8:10]}/{d[5:7]}: tabela do grupo x export do dia",
                    "detalhe": f"Nubimetrics (grupo) {_f(gv)} x soma dos anúncios do dia {_f(dia)} ({(dia / gv - 1) * 100:+.1f}%)".replace(".", ",")
                    if gv else f"grupo 0 x dia {_f(dia)}"})
    if grupo and not difs:
        ach.append({"nivel": "info", "area": "dados", "titulo": "Tabela do grupo bate com os exports do dia",
                    "detalhe": f"{len(grupo)} vendedor-dia conferidos (tolerância 3%)"})
    # 3) soma dos dias do mês x acumulado do mês
    mes = fim.strftime("%Y-%m")
    fotos = repo._todos("vend_produto_dia", {"select": "vendedor,dias", "mes": f"eq.{mes}-01"})
    acum = {}
    for f in fotos:
        dd = f["dias"] or {}
        if dd:
            ud = max(dd)
            acum.setdefault(f["vendedor"], {}).setdefault(ud, 0.0)
            acum[f["vendedor"]][ud] += float(dd[ud].get("v") or 0)
    for v, porD in acum.items():
        ud = max(porD)
        dias_mes = [(date.fromisoformat(mes + "-01") + timedelta(days=i)).isoformat() for i in range(int(ud[8:10]))]
        if v not in por_v:
            continue
        todos = repo._todos("vend_vendas_dia", {"select": "data,v", "vendedor": f"eq.{v}", "data": f"gte.{mes}-01"})
        soma = {str(r["data"])[:10]: float(r["v"] or 0) for r in todos}
        if not all(d in soma for d in dias_mes):
            continue
        s = sum(soma[d] for d in dias_mes)
        a = porD[ud]
        if a and abs(s / a - 1) > 0.05:
            ach.append({"nivel": "alerta", "area": "dados", "titulo": f"{v}: soma dos dias x acumulado do mês até {ud[8:10]}/{ud[5:7]}",
                        "detalhe": f"soma dos {len(dias_mes)} dias {_f(s)} x relatório do mês {_f(a)} ({(s / a - 1) * 100:+.1f}%)"})
    # 4) dia fora do padrão
    for v, dd in por_v.items():
        vals = [x for d, x in sorted(dd.items())[:-1]]
        if len(vals) < 6:
            continue
        med = statistics.median(vals)
        x = dd.get(fim.isoformat())
        if med >= 5000 and x is not None and (x > 4 * med or x < 0.2 * med):
            ach.append({"nivel": "alerta", "area": "dados", "titulo": f"{v}: {fim.strftime('%d/%m')} fora do padrão",
                        "detalhe": f"{_f(x)} no dia x mediana {_f(med)} dos dias anteriores — conferir se o arquivo veio completo"})
    # 5) preço que mudou demais (produto do mesmo vendedor, dia anterior x último dia)
    ult_dia = repo._todos("vend_vendas_dia", {"select": "vendedor,itens", "data": f"eq.{fim.isoformat()}"})
    ant_dia = repo._todos("vend_vendas_dia", {"select": "vendedor,itens", "data": f"eq.{(fim - timedelta(days=1)).isoformat()}"})
    ant = {(r["vendedor"], it["k"]): it for r in ant_dia for it in (r["itens"] or [])}
    saltos = []
    for r in ult_dia:
        for it in r["itens"] or []:
            a = ant.get((r["vendedor"], it["k"]))
            pa, pb = (a or {}).get("p"), it.get("p")
            if pa and pb and it.get("u", 0) >= 2 and abs(pb / pa - 1) > 0.4:
                saltos.append((r["vendedor"], it.get("t"), pa, pb))
    for v, t, pa, pb in saltos[:10]:
        ach.append({"nivel": "info", "area": "preço", "titulo": f"{v}: preço mudou {(pb / pa - 1) * 100:+.0f}% de um dia para o outro",
                    "detalhe": f"{(t or '')[:60]}: R$ {pa:,.2f} -> R$ {pb:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")})
    # 6) produtos juntados com parecença baixa
    try:
        fracos = [g for g in repo._todos("produto_grupos", {"select": "titulo,grupo_titulo,similaridade", "metodo": "eq.ia"})
                  if (g.get("similaridade") or 1) < 0.86]
    except Exception:  # noqa: BLE001
        fracos = []
    for g in fracos[:10]:
        ach.append({"nivel": "info", "area": "produtos iguais", "titulo": "Junção com parecença baixa: conferir",
                    "detalhe": f"“{g['titulo']}” junto de “{g['grupo_titulo']}” (parecença {g['similaridade']:.2f}). "
                               f"Regras: {regras_juncao(g['titulo'], g['grupo_titulo'])}"})
    # 7) rotinas com erro
    for r in repo._todos("rotinas", {"select": "id,nome,ultimo_resultado"}):
        if str(r.get("ultimo_resultado") or "").startswith("erro"):
            ach.append({"nivel": "erro", "area": "rotinas", "titulo": f"Tarefa '{r['nome']}' com erro",
                        "detalhe": str(r["ultimo_resultado"])[:300]})
    ordem = {"erro": 0, "alerta": 1, "info": 2}
    return sorted(ach, key=lambda a: ordem.get(a["nivel"], 3))


def coleta_em_andamento(repo):
    """Texto explicando a coleta em andamento (pedido não atendido ou coleta rodando no Mac), ou "" se não houver."""
    try:
        ped = repo._req("GET", "coletor_pedidos", {"select": "id,pedido_em,motivo", "atendido_em": "is.null",
                                                  "order": "id.desc", "limit": 5}) or []
    except Exception:  # noqa: BLE001
        ped = []
    if ped:
        return f"Há {len(ped)} pedido(s) de coleta ainda não atendido(s) (o mais recente: {ped[0].get('motivo') or 'coleta'})"
    try:
        run = repo._req("GET", "coletor_execucoes", {"select": "id,tarefa,atualizado_em,iniciado_em", "em_andamento": "eq.true",
                                                    "order": "id.desc", "limit": 1}) or []
    except Exception:  # noqa: BLE001
        run = []
    if run:
        from datetime import datetime, timezone
        ts = str(run[0].get("atualizado_em") or run[0].get("iniciado_em") or "")
        try:
            recente = (datetime.now(timezone.utc) - datetime.fromisoformat(ts.replace("Z", "+00:00"))).total_seconds() < 1800
        except ValueError:
            recente = False
        if recente:
            return f"Coleta rodando agora no Mac ({run[0].get('tarefa') or 'diario'})"
    return ""


def regras_juncao(a, b):
    """Resultado de cada regra fixa de produtos iguais para dois títulos (✅ bate, ❌ não bate, — sem informação)."""
    import produtos_iguais as pi
    va, vb = pi.volumes(a), pi.volumes(b)
    ca, cb = pi.concentracoes(a), pi.concentracoes(b)
    ga, gb = pi.genero(a), pi.genero(b)
    na, nb = pi.palavras_nome(a), pi.palavras_nome(b)
    r = lambda ok, info=True: "—" if not info else ("✅" if ok else "❌")
    return (f"volume {r(bool(va & vb), bool(va and vb))} · kit {r(pi.quantidade(a) == pi.quantidade(b))} · "
            f"concentração {r(ca == cb, bool(ca and cb))} · gênero {r(ga == gb, bool(ga and gb))} · "
            f"números {r(pi._numeros_batem(a, b))} · nome {r(na == nb, bool(na and nb))}"
            + (f" (nomes: {', '.join(sorted(na)) or '—'} x {', '.join(sorted(nb)) or '—'})" if na != nb else ""))


def trecho_codigo(noite, limite=45000):
    """O módulo da noite (rodízio) e o trecho que cabe no pedido (os módulos grandes vão por partes)."""
    base = os.path.dirname(os.path.abspath(__file__))
    nome = MODULOS[noite % len(MODULOS)]
    try:
        txt = open(os.path.join(base, nome), encoding="utf-8").read()
    except OSError:
        return nome, "", 0, 0
    partes = max(1, -(-len(txt) // limite))
    parte = (noite // len(MODULOS)) % partes
    return nome, txt[parte * limite:(parte + 1) * limite], parte + 1, partes


def rodar(repo, obs=""):
    """Faz a auditoria completa e devolve o registro para gravar em 'auditorias'."""
    hoje = date.today()
    ach = conferencias(repo, hoje)
    noite = hoje.toordinal()
    modulo, codigo, parte, partes = trecho_codigo(noite)
    lista = "\n".join(f"[{a['nivel'].upper()}] ({a['area']}) {a['titulo']} — {a['detalhe']}" for a in ach) or "nenhum achado"
    conversa = []
    pedido = (
        "Você é o auditor de dados e engenheiro de software do nubi, um sistema que coleta do Nubimetrics as vendas diárias "
        "de vendedores de perfume do Mercado Livre e mostra análises (Python na Vercel + Supabase + coletor Playwright no Mac).\n"
        "O dono exige ZERO erro nos números. Tarefas:\n"
        "1) Para cada achado das conferências abaixo, diga a causa mais provável e como corrigir (dado ou código). "
        "Separe o que é problema real do que é esperado (ex.: arredondamento do Nubimetrics de 100 em 100).\n"
        f"2) Revise o trecho do código ({modulo}, parte {parte} de {partes}) procurando bugs que distorçam números, "
        "casos não tratados e otimizações simples. Cite a função e mostre a correção em poucas linhas.\n"
        "3) Termine com as 3 ações mais importantes, em ordem.\n"
        "Não invente: se não der para saber pelo que foi mostrado, diga o que precisa ser verificado. Português, direto.\n"
        + (f"\nOBSERVAÇÃO DO DONO: {obs}\n" if obs else "")
        + f"\nCONFERÊNCIAS DE HOJE:\n{lista}\n\nCÓDIGO ({modulo}, parte {parte}/{partes}):\n```python\n{codigo}\n```")
    sis = agentes.SISTEMA
    if ia.tem("codex"):
        try:
            mc = ia.modelo_codex()
            t, _, _ = ia.perguntar(pedido, web=False, max_tokens=5000, qual="codex", sistema=sis)
            conversa.append({"autor": f"ChatGPT ({mc})", "texto": t})
        except Exception as e:  # noqa: BLE001
            conversa.append({"autor": "sistema", "texto": f"O ChatGPT não respondeu: {str(e)[:200]}"})
    if ia.tem("deepseek"):
        try:
            t = agentes.perguntar(
                "deepseek",
                "Revise o trecho de código abaixo e as conferências: confira as contas e a consistência entre totais, "
                "procure bugs que distorçam números, casos de borda, desempenho e custo. Liste no máximo 5 pontos, cada um "
                "com a função, o problema e a correção em poucas linhas. Se o ChatGPT já apontou algo, diga se concorda.\n\n"
                f"CONFERÊNCIAS:\n{lista}\n\nANÁLISE DO CHATGPT:\n{conversa[-1]['texto'][:6000] if conversa else '—'}\n\n"
                f"CÓDIGO ({modulo}, parte {parte}/{partes}):\n```python\n{codigo}\n```", max_tokens=3000)
            if not t.strip():
                raise ia.SemIA("resposta vazia")
            conversa.append({"autor": "DeepSeek", "texto": t})
        except Exception as e:  # noqa: BLE001
            conversa.append({"autor": "sistema", "texto": f"O DeepSeek não respondeu: {str(e)[:200]}"})
    gpt = next((m["texto"] for m in conversa if m["autor"].startswith("ChatGPT")), None)
    ds = next((m["texto"] for m in conversa if m["autor"] == "DeepSeek"), None)
    if ia.tem("claude") and (gpt or ds):
        try:
            t, _, _ = ia.perguntar(
                "Você é o revisor técnico e coordenador do nubi. O ChatGPT e o DeepSeek analisaram as conferências de dados e "
                "um trecho de código. Revise as análises: diga com o que concorda, o que está errado ou arriscado, o que "
                "deixaram passar e qual correção você faria. Seja concreto e curto. Português.\n\n"
                f"CONFERÊNCIAS:\n{lista}\n\nANÁLISE DO CHATGPT:\n{gpt or '—'}\n\nANÁLISE DO DEEPSEEK:\n{ds or '—'}\n\n"
                f"CÓDIGO ({modulo}, parte {parte}/{partes}):\n```python\n{codigo}\n```",
                web=False, max_tokens=3000, qual="claude", sistema=sis)
            conversa.append({"autor": "Claude", "texto": t})
        except Exception as e:  # noqa: BLE001
            conversa.append({"autor": "sistema", "texto": f"O Claude não respondeu: {str(e)[:200]}"})
    elif not ia.tem("claude"):
        conversa.append({"autor": "sistema", "texto": "Revisão do Claude desligada: coloque ANTHROPIC_API_KEY na Vercel para ele "
                                                         "revisar a análise do ChatGPT toda noite."})
    n = {k: sum(1 for a in ach if a["nivel"] == k) for k in ("erro", "alerta", "info")}
    return {"data": hoje.isoformat(), "conferencias": ach, "conversa": conversa, "modulo": f"{modulo} ({parte}/{partes})",
            "resumo": f"{n['erro']} erro(s), {n['alerta']} alerta(s), {n['info']} informação(ões); código revisado: {modulo} parte {parte}/{partes}"}
