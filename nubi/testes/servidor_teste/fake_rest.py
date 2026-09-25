"""Supabase/PostgREST de mentira, em memória, só para testar o nubi_web."""
import sys, json, copy, datetime
sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "..", ".."))
import nubi, nubi_web

DB = {"snapshots": [], "anuncios": [], "marcas_config": [], "gtin_info": [], "acesso": [{"email": "brmilani@gmail.com"}], "ranking_relatorios": [], "ranking_linhas": [], "agente_execucoes": [], "vend_relatorios": [], "vend_anuncios": [], "coletor_execucoes": [], "vend_decisoes": [], "vend_produto_dia": [], "ia_resumos": [], "marca_categorias": [], "vend_vendas_dia": [], "reuniao_mensagens": [], "reuniao_tarefas": [], "rotinas_execucoes": [], "coletor_pedidos": [], "auditorias": [], "vend_grupo_dia": [], "produto_grupos": [], "ia_lotes": [], "marca_sugestoes": [], "rotinas": [
  {"id": "auditoria", "ordem": 8, "nome": "Auditoria de dados e código (IA)", "descricao": "Audita.", "responsavel": "ChatGPT + Claude", "horario": "10:30", "dias_semana": ["seg","ter","qua","qui","sex","sab","dom"], "dia_mes": None, "ativo": True, "observacao": None, "ultima_execucao": None, "ultimo_resultado": None},
  {"id": "categorias_lote", "ordem": 7, "nome": "Classificar marcas em lote (IA)", "descricao": "Lote.", "responsavel": "ChatGPT", "horario": "04:00", "dias_semana": ["seg","ter","qua","qui","sex","sab","dom"], "dia_mes": None, "ativo": True, "observacao": None, "ultima_execucao": None, "ultimo_resultado": None},
  {"id": "produtos_ia", "ordem": 3, "nome": "Juntar produtos iguais (IA)", "descricao": "Junta.", "responsavel": "ChatGPT", "horario": "05:30", "dias_semana": ["seg","ter","qua","qui","sex","sab","dom"], "dia_mes": None, "ativo": True, "observacao": None, "ultima_execucao": None, "ultimo_resultado": None},
  {"id": "coleta", "ordem": 1, "nome": "Coleta diária do Nubimetrics", "descricao": "Baixa tudo.", "responsavel": "Coletor (Mac mini)", "horario": "07:00", "dias_semana": ["seg","ter","qua","qui","sex","sab","dom"], "dia_mes": None, "ativo": True, "observacao": None, "ultima_execucao": None, "ultimo_resultado": None},
  {"id": "agente", "ordem": 2, "nome": "Agente do Explorador", "descricao": "GTINs.", "responsavel": "Robô nubi (servidor)", "horario": "06:00", "dias_semana": ["seg","ter","qua","qui","sex","sab","dom"], "dia_mes": None, "ativo": True, "observacao": None, "ultima_execucao": None, "ultimo_resultado": None},
  {"id": "resumo_dia", "ordem": 3, "nome": "Resumo do dia dos vendedores", "descricao": "Resumo.", "responsavel": "ChatGPT", "horario": "08:00", "dias_semana": ["seg","ter","qua","qui","sex","sab","dom"], "dia_mes": None, "ativo": True, "observacao": "Destaque sempre os perfumes árabes.", "ultima_execucao": None, "ultimo_resultado": None},
  {"id": "resumo_semana", "ordem": 4, "nome": "Análise da semana", "descricao": "Semana.", "responsavel": "ChatGPT", "horario": "08:00", "dias_semana": ["seg"], "dia_mes": None, "ativo": True, "observacao": None, "ultima_execucao": None, "ultimo_resultado": None},
  {"id": "resumo_marcas", "ordem": 5, "nome": "Análise mensal das marcas", "descricao": "Mensal.", "responsavel": "ChatGPT", "horario": "08:00", "dias_semana": [], "dia_mes": 3, "ativo": True, "observacao": None, "ultima_execucao": None, "ultimo_resultado": None}], "marca_apelidos": [{"apelido": "YSL", "marca": "YVES SAINT LAURENT", "ignorar": False}]}
SEQ = {"rotinas_execucoes": 0, "coletor_pedidos": 0, "reuniao_mensagens": 0, "reuniao_tarefas": 0, "snapshots": 0, "anuncios": 0, "ranking_relatorios": 0, "ranking_linhas": 0, "agente_execucoes": 0, "vend_relatorios": 0, "vend_anuncios": 0, "coletor_execucoes": 0, "vend_decisoes": 0}
cfg = json.load(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "..", "..", "marcas.json")))
DB["marcas_config"] = [{"marca": k, "linhas": v["linhas"]} for k, v in cfg.items()]
CHAMADAS = []

def _campo(k):
    """coluna simples ou caminho jsonb tipo 'meta->>tipo' (sintaxe do PostgREST)."""
    if "->>" in k:
        col, chave = k.split("->>", 1)
        return lambda r: (r.get(col) or {}).get(chave.strip("'\"")) if isinstance(r.get(col), dict) else None
    return lambda r: r.get(k)


def filtra(rows, params):
    out = rows
    for k, v in params.items():
        pega = _campo(k)
        if isinstance(v, str) and v.startswith("eq."):
            val = v[3:]
            out = [r for r in out if str(pega(r)) == val]
        elif isinstance(v, str) and v.startswith("neq."):
            out = [r for r in out if str(pega(r)) != v[4:]]
        elif isinstance(v, str) and v.startswith("gt."):
            out = [r for r in out if float(pega(r) or 0) > float(v[3:])]
        elif isinstance(v, str) and v == "is.null":
            out = [r for r in out if pega(r) is None]
        elif isinstance(v, str) and v.startswith("lte."):
            out = [r for r in out if float(pega(r) or 0) <= float(v[4:])]
        elif isinstance(v, str) and v.startswith("gte."):
            out = [r for r in out if str(pega(r)) >= v[4:]]
        elif isinstance(v, str) and v.startswith("like."):
            import fnmatch
            out = [r for r in out if fnmatch.fnmatchcase(str(pega(r)), v[5:])]
        elif isinstance(v, str) and v.startswith("in.("):
            vals = set(v[4:-1].split(","))
            out = [r for r in out if str(pega(r)) in vals]
    if "order" in params:
        for campo in reversed(params["order"].split(",")):
            desc = campo.endswith(".desc"); campo = campo.split(".")[0]
            out = sorted(out, key=lambda r: (r.get(campo) is None, r.get(campo) if r.get(campo) is not None else 0), reverse=desc)
    off, lim = int(params.get("offset", 0)), params.get("limit")
    out = out[off:]
    if lim is not None:
        out = out[:int(lim)]
    return out

def fake_req(self, metodo, caminho, params=None, corpo=None, prefer=None):
    params = params or {}
    CHAMADAS.append((metodo, caminho))
    assert self.token
    if caminho.startswith("rpc/"):
        nome = caminho[4:]
        chv = lambda a: a.get("gtin") or "T:" + (a.get("titulo") or "").lower()
        def agrupa(anuncios, com_chave=True):
            g = {}
            for a in anuncios:
                k = (a["relatorio_id"], chv(a)) if com_chave else a["relatorio_id"]
                g.setdefault(k, []).append(a)
            out = []
            for k, ls in g.items():
                top = max(ls, key=lambda a: a.get("unidades") or 0)
                d = {"relatorio_id": k[0] if com_chave else k, "gtin": max((a.get("gtin") or "" for a in ls)) or None,
                     "marca": max(a.get("marca") or "" for a in ls), "titulo": top["titulo"],
                     "unidades": sum(a.get("unidades") or 0 for a in ls), "vendas": sum(a.get("vendas") or 0 for a in ls),
                     "anuncios": len(ls), "ativos": sum(1 for a in ls if (a.get("estado") or "").lower() == "active"),
                     "fulfillment": any(a.get("fulfillment") for a in ls), "catalogo": any(a.get("catalogo") for a in ls)}
                if com_chave: d["chave"] = k[1]
                out.append(d)
            return out
        if nome == "marcas_resumo":
            return [{"marca": "JEAN PAUL GAULTIER", "fonte": "ranking", "mes": "2026-08-01", "fim": None, "vendas": 4600000, "vendedores": None, "posicao": 8},
                    {"marca": "JEAN PAUL GAULTIER", "fonte": "vendedores", "mes": "2026-08-01", "fim": None, "vendas": 2895310, "vendedores": 4, "posicao": None},
                    {"marca": "JPG", "fonte": "vendedores", "mes": "2026-05-01", "fim": None, "vendas": 3900, "vendedores": 1, "posicao": None},
                    {"marca": "TED LAPIDOS", "fonte": "vendedores", "mes": "2026-08-01", "fim": None, "vendas": 6860, "vendedores": 1, "posicao": None},
                    {"marca": "TED LAPIDUS", "fonte": "explorador", "mes": "2026-08-01", "fim": "2026-09-22", "vendas": 20120, "vendedores": 12, "posicao": None}]
        if nome == "vend_prod_mes":
            ids = set(corpo["ids"])
            out = sorted(agrupa([a for a in DB["vend_anuncios"] if a["relatorio_id"] in ids]), key=lambda d: (d["relatorio_id"], d["chave"]))
            off, lim = int(params.get("offset", 0)), params.get("limit")
            return out[off:off + int(lim)] if lim else out
        if nome == "vend_prod_serie":
            return agrupa([a for a in DB["vend_anuncios"] if chv(a) == corpo["p_chave"]], False)
        if nome == "vend_dia_serie":
            rows = [r for r in DB["vend_vendas_dia"] if corpo["desde"] <= r["data"] <= corpo["ate"]]
            out = [{"data": r["data"], "vendedor": r["vendedor"], "v": r["v"], "u": r["u"], "produtos": len(r["itens"])} for r in sorted(rows, key=lambda r: (r["data"], r["vendedor"]))]
            off, lim = int(params.get("offset", 0)), params.get("limit")
            return out[off:off + int(lim)] if lim else out
        if nome == "vend_dia_semana":
            ag = {}
            for r in DB["vend_vendas_dia"]:
                if corpo["desde"] <= r["data"] <= corpo["ate"] and (not corpo.get("so_vendedor") or r["vendedor"] == corpo["so_vendedor"]):
                    dw = datetime.date.fromisoformat(r["data"]).isoweekday()
                    a = ag.setdefault(dw, [set(), 0.0]); a[0].add(r["data"]); a[1] += r["v"]
            return [{"dow": k, "dias": len(v[0]), "v": v[1]} for k, v in sorted(ag.items())]
        if nome == "vend_dia_produtos":
            ag = {}
            for r in sorted(DB["vend_vendas_dia"], key=lambda r: r["data"]):
                if corpo["desde"] <= r["data"] <= corpo["ate"] and (not corpo.get("so_vendedor") or r["vendedor"] == corpo["so_vendedor"]):
                    for i in r["itens"]:
                        a = ag.setdefault(i["k"], {"chave": i["k"], "produto": i["t"], "marca": i["m"], "v": 0, "u": 0, "vs": set(), "ds": set(), "ativos_ult": 0, "por_dia": {}})
                        a["v"] += i["v"]; a["u"] += i["u"]; a["vs"].add(r["vendedor"]); a["ds"].add(r["data"]); a["ativos_ult"] = i["a"]
                        a["por_dia"][r["data"]] = a["por_dia"].get(r["data"], 0) + i["v"]
            out = sorted(ag.values(), key=lambda a: -a["v"])[:corpo.get("lim", 40)]
            return [dict({k: v for k, v in a.items() if k not in ("vs", "ds")}, vendedores=len(a["vs"]), dias=len(a["ds"])) for a in out]
        if nome == "vend_dia_gravar":
            for d in corpo["dados"]:
                ex = next((r for r in DB["vend_produto_dia"] if (r["vendedor"], r["mes"], r["chave"]) == (d["vendedor"], d["mes"], d["chave"])), None)
                if ex: ex["dias"].update(d["dias"])
                else: DB["vend_produto_dia"].append({"vendedor": d["vendedor"], "mes": d["mes"], "chave": d["chave"], "dias": dict(d["dias"])})
            return None
        if nome == "atualizar_consolidacao":
            idx = {r["id"]: r for r in DB["anuncios"]}
            for d in corpo["dados"]:
                idx[d["id"]].update({k: v for k, v in d.items() if k != "id"})
            return len(corpo["dados"])
        if nome == "un_por_produto":
            agg = {}
            for r in DB["anuncios"]:
                if r["snapshot_id"] in corpo["ids"]:
                    agg[(r["snapshot_id"], r["produto"])] = agg.get((r["snapshot_id"], r["produto"]), 0) + r["un"]
            rows = [{"snapshot_id": a, "produto": b, "un": u} for (a, b), u in agg.items()]
            return filtra(rows, params)
        if nome == "marcas_vistas":
            agg = {}
            for t, f in (("ranking_linhas", "ranking"), ("vend_anuncios", "vendedores")):
                for r in DB[t]:
                    if r.get("marca"):
                        agg[(r["marca"], f)] = agg.get((r["marca"], f), 0) + (r.get("vendas") or 0)
            return [{"marca": m, "fonte": f, "vendas": v} for (m, f), v in agg.items()]
        if nome == "painel":
            out = []
            for m in sorted({s["marca"] for s in DB["snapshots"]}):
                s = sorted([x for x in DB["snapshots"] if x["marca"] == m], key=lambda x: (x["fim"], x["inicio"], x["id"]))[-1]
                a = [r for r in DB["anuncios"] if r["snapshot_id"] == s["id"]]
                out.append({"marca": m, "snapshot_id": s["id"], "inicio": s["inicio"], "fim": s["fim"], "dias": s["dias"],
                    "periodos": sum(1 for x in DB["snapshots"] if x["marca"] == m), "anuncios": len(a),
                    "vendedores": len({r["vendedor_id"] for r in a}), "referencias": len({r["produto"] for r in a}),
                    "un": sum(r["un"] for r in a), "fat": sum(r["fat"] for r in a), "catalogo": sum(r["catalogo"] for r in a),
                    "duvidas": len({r["gtin"] for r in a if (r["confianca"] or "").startswith("Dúvida") and r["gtin"]})})
            return sorted(out, key=lambda x: -x["un"])
    tab = DB[caminho]
    if metodo == "PATCH":
        for r in filtra(tab, params):
            r.update(corpo)
        return None
    if metodo == "GET":
        return copy.deepcopy(filtra(tab, params))
    if metodo == "DELETE":
        alvo = filtra(tab, {k: v for k, v in params.items()})
        ids = {id(r) for r in alvo}
        DB[caminho] = [r for r in tab if id(r) not in ids]
        if caminho == "snapshots":
            sids = {r["id"] for r in alvo}
            DB["anuncios"] = [a for a in DB["anuncios"] if a["snapshot_id"] not in sids]
        if caminho == "vend_relatorios":
            rids = {r["id"] for r in alvo}
            DB["vend_anuncios"] = [a for a in DB["vend_anuncios"] if a["relatorio_id"] not in rids]
        if caminho == "estoque_atualizacoes":
            rids = {r["id"] for r in alvo}
            DB["estoque_itens"] = [a for a in DB["estoque_itens"] if a["atualizacao_id"] not in rids]
        if caminho == "ranking_relatorios":
            rids = {r["id"] for r in alvo}
            DB["ranking_linhas"] = [a for a in DB["ranking_linhas"] if a["relatorio_id"] not in rids]
        return copy.deepcopy(alvo) if prefer and "representation" in prefer else None
    if metodo == "POST":
        linhas = copy.deepcopy(corpo)
        json.dumps(linhas)  # tem que ser JSON puro
        chave = {"marcas_config": "marca", "gtin_info": "gtin", "marca_apelidos": "apelido", "marca_categorias": "marca_chave", "ia_resumos": "chave", "rotinas": "id", "auditorias": "data", "ia_precos": "modelo", "mac_estado": "id", "produto_grupos": "chave", "ia_lotes": "id", "marca_sugestoes": "marca_chave"}.get(caminho)
        for l in linhas:
            if caminho in SEQ:
                SEQ[caminho] += 1
                l["id"] = SEQ[caminho]
                if caminho in ("snapshots", "ranking_relatorios", "vend_relatorios"):
                    if any(s.get("hash") == l.get("hash") for s in tab):
                        raise nubi_web.ErroNuvem("duplicado", 409)
                    l["importado_em"] = datetime.datetime.now().isoformat()
                if caminho == "estoque_atualizacoes":
                    l.setdefault("criado_em", datetime.datetime.now(datetime.timezone.utc).isoformat())
                    l.setdefault("analise", None); l.setdefault("analise_por", None); l.setdefault("loja", "UpSeller · My Warehouse")
            if chave:
                tab[:] = [r for r in tab if r[chave] != l[chave]]
            if caminho == "vend_grupo_dia":
                tab[:] = [r for r in tab if (r["vendedor"], r["data"]) != (l["vendedor"], l["data"])]
            if caminho == "vend_vendas_dia":
                tab[:] = [r for r in tab if (r["vendedor"], r["data"]) != (l["vendedor"], l["data"])]
            tab.append(l)
        return linhas if prefer and "representation" in prefer else None

DB["agentes"] = [
  {"id": "claude", "nome": "Claude", "icone": "✴️", "cor": "#d97757", "papel": "Coordena", "onde": "API Anthropic", "ordem": 1, "apelido": None, "ultimo_teste": None},
  {"id": "chatgpt", "nome": "ChatGPT", "icone": "🧠", "cor": "#10a37f", "papel": "Código", "onde": "API OpenAI", "ordem": 2, "apelido": None, "ultimo_teste": None},
  {"id": "deepseek", "nome": "DeepSeek", "icone": "🐋", "cor": "#4d6bfe", "papel": "Matemática", "onde": "API DeepSeek", "ordem": 3, "apelido": None, "ultimo_teste": None},
  {"id": "gptoss", "nome": "gpt-oss", "icone": "🦙", "cor": "#6b4fb3", "papel": "Segunda opinião", "onde": "Ollama Cloud", "ordem": 4, "apelido": None, "ultimo_teste": None},
  {"id": "hermes", "nome": "Hermes", "icone": "🪽", "cor": "#a2741a", "papel": "Vigia", "onde": "Mac mini", "ordem": 5, "apelido": None, "ultimo_teste": None},
  {"id": "claude_code", "nome": "Claude (código)", "icone": "💻", "cor": "#b3541e", "papel": "Programa", "onde": "Sessão", "ordem": 6, "apelido": None, "ultimo_teste": None}]
DB["agentes_uso"] = []
DB["tarefa_eventos"] = []
DB["mac_comandos"] = []
SEQ["mac_comandos"] = 0
DB["mac_estado"] = []
SEQ["tarefa_eventos"] = 0
SEQ["agentes_uso"] = 0
DB["ia_precos"] = [{"modelo": "claude-opus-5-5", "entrada": 4, "saida": 20, "obs": "Anthropic"}, {"modelo": "gpt-oss", "entrada": 0, "saida": 0, "obs": "grátis"},
                   {"modelo": "deepseek", "entrada": None, "saida": None, "obs": "preencher"}]
DB["conhecimento"] = [{"id": 1, "tipo": "briefing", "titulo": "Programador automático", "texto": "Leia nubi/PROGRAMADOR.md.", "autor": "Claude (código)", "fonte": "PROGRAMADOR.md", "fixo": True, "atualizado_em": "2026-09-25T00:00:00+00:00"}]
SEQ["conhecimento"] = 1
DB["estoque_atualizacoes"] = []
DB["estoque_itens"] = []
SEQ["estoque_atualizacoes"] = 0
DB["rotinas"].append({"id": "estoque", "ordem": 5, "nome": "Estoque do UpSeller", "descricao": "Exporta o estoque.", "responsavel": "Mac mini (coletor)", "horario": "03:00", "dias_semana": ["seg","ter","qua","qui","sex","sab","dom"], "dia_mes": None, "ativo": True, "observacao": None, "ultima_execucao": None, "ultimo_resultado": None})
DB["rotinas"].append({"id": "gestor", "ordem": 6, "nome": "Planilha no Gestor Seller", "descricao": "Importa.", "responsavel": "Mac mini (coletor)", "horario": "03:00", "dias_semana": ["seg","ter","qua","qui","sex","sab","dom"], "dia_mes": None, "ativo": False, "observacao": None, "ultima_execucao": None, "ultimo_resultado": None})
DB["agentes"].append({"id": "estoquista", "nome": "Estoquista", "icone": "📦", "cor": "#2f7d5b", "papel": "Analisa o estoque", "onde": "gpt-oss grátis", "ordem": 7, "apelido": None, "ultimo_teste": None})
nubi_web.RepoSupabase._req = fake_req
nubi_web.PAGINA = 300   # força paginação nos testes
