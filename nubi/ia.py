# -*- coding: utf-8 -*-
"""
IA do nubi: ChatGPT (OPENAI_API_KEY) ou Claude (ANTHROPIC_API_KEY), a que tiver chave na Vercel.

perguntar(pergunta, web=True) -> (texto, links, nome_da_ia)
perguntar_json(pergunta, web=True) -> (dict, links, nome_da_ia)   # a pergunta pede um JSON na resposta
Com web=True a IA pesquisa na internet antes de responder (web search das duas APIs).
Modelo: NUBI_IA_MODELO (ChatGPT, padrão gpt-4.1), NUBI_IA_MODELO_CLAUDE (padrão claude-opus-5-5),
NUBI_IA_CODIGO (Codex; padrão: o Codex mais novo da conta) e NUBI_IA_MODELO_DEEPSEEK.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request


class SemIA(Exception):
    pass


def disponivel():
    """A IA padrão do nubi: ChatGPT quando há a chave da OpenAI (os resumos foram feitos para ele); senão Claude."""
    return "chatgpt" if os.environ.get("OPENAI_API_KEY") else "claude" if os.environ.get("ANTHROPIC_API_KEY") else None


CHAVES = {"claude": "ANTHROPIC_API_KEY", "chatgpt": "OPENAI_API_KEY", "deepseek": "DEEPSEEK_API_KEY", "ollama": "OLLAMA_API_KEY",
          "gemini": "GEMINI_API_KEY"}
OLLAMA_MODELOS = ["gpt-oss:120b", "gpt-oss:20b"]   # Ollama Cloud: modelos da cota grátis da conta
# 28/09 (Bruno): as análises com o DeepSeek usam o v4-pro (o melhor dele); os flash ficam só de reserva se o pro falhar
DEEPSEEK_FLASH = ["deepseek-flash", "deepseek-v4-flash", "deepseek-chat"]   # nomes mudam; tenta na ordem
DEEPSEEK_MODELOS = ["deepseek-v4-pro"] + DEEPSEEK_FLASH


def tem(qual):
    qual = "chatgpt" if qual == "codex" else qual
    if qual == "deepseek" and not USO.get("deepseek_ok"):
        return False            # 28/09 (Bruno): o DeepSeek só existe nas 2 análises do dia (deepseek_liberado)
    return qual in CHAVES and bool(os.environ.get(CHAVES[qual]))


class deepseek_liberado:
    """28/09 (Bruno: "isso não existe essas IAs terem esse tanto de chamada"): o DeepSeek faz SÓ 2 análises por dia, a dos
    dados coletados (Explorador, Concorrentes e Produtos: rotina analise_foco) e a do estoque (analise_estoque). Fora deste
    bloco, ia.tem("deepseek") é False: Sala, cards, reservas e o que mais houver simplesmente não o usam."""
    def __enter__(self):
        USO["deepseek_ok"] = True
        return self

    def __exit__(self, *a):
        USO["deepseek_ok"] = False


DEEPSEEK_PRO = DEEPSEEK_MODELOS                                                  # tarefas pesadas (revisão de código)
_CODEX = {}


def modelo_codex():
    """
    O Codex (modelo de código da OpenAI) mais novo que a conta tem: lê /v1/models e escolhe o id com 'codex' mais
    recente (o completo antes do mini). NUBI_IA_CODIGO manda, se existir. Sem Codex na conta: o modelo padrão.
    """
    if os.environ.get("NUBI_IA_CODIGO"):
        return os.environ["NUBI_IA_CODIGO"]
    if "id" in _CODEX:
        return _CODEX["id"]
    escolhido = None
    try:
        req = urllib.request.Request("https://api.openai.com/v1/models",
                                     headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
        with urllib.request.urlopen(req, timeout=20) as r:
            ms = json.loads(r.read().decode()).get("data", [])
        cod = [m for m in ms if "codex" in m.get("id", "")]
        cod.sort(key=lambda m: ("mini" in m["id"], -int(m.get("created") or 0)))
        escolhido = cod[0]["id"] if cod else None
    except Exception:  # noqa: BLE001
        escolhido = None
    _CODEX["id"] = escolhido or os.environ.get("NUBI_IA_MODELO", "gpt-4.1")
    return _CODEX["id"]


def _deepseek(pergunta, max_tokens, modelo=None, sistema=None, modelos=None):
    """DeepSeek (API no formato da OpenAI). Se o nome do modelo for recusado, tenta o próximo da lista."""
    import urllib.error
    fixo = modelo or os.environ.get("NUBI_IA_MODELO_DEEPSEEK")
    modelos = [fixo] if fixo else (modelos or DEEPSEEK_MODELOS)
    msgs = ([{"role": "system", "content": sistema}] if sistema else []) + [{"role": "user", "content": pergunta}]
    ultimo = None
    for m in modelos:
        try:
            # modelos que raciocinam antes (pro/reasoner) gastam tokens pensando: dá folga para sobrar resposta
            mt = max(max_tokens, 6000) if re.search(r"pro|reason", m) else max_tokens
            r = _post_json("https://api.deepseek.com/chat/completions",
                           {"model": m, "messages": msgs, "max_tokens": mt, "stream": False},
                           {"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"}, timeout=150)
            c = (r.get("choices") or [{}])[0]
            texto = (c.get("message") or {}).get("content") or ""
            if texto.strip():
                return texto
            ultimo = f"{m} devolveu resposta vazia (fim: {c.get('finish_reason')})"
            continue                                       # vazio: tenta o próximo modelo da lista
        except urllib.error.HTTPError as e:
            corpo = e.read().decode(errors="replace")[:300]
            ultimo = f"{e.code}: {corpo}"
            if e.code in (400, 404) and "model" in corpo.lower():
                continue
            raise SemIA(f"DeepSeek respondeu {ultimo}")
    raise SemIA(f"DeepSeek recusou os modelos {modelos}: {ultimo}")


def nome(ia=None):
    ia = ia or disponivel()
    return {"claude": "IA (Claude)", "chatgpt": "IA (ChatGPT)", "deepseek": "IA (DeepSeek)", "ollama": "IA (gpt-oss)",
            "gemini": "IA (Gemini)"}.get(ia, "IA")


def _ollama(pergunta, max_tokens, modelo=None, sistema=None):
    """Ollama Cloud (ollama.com/api/chat) com a cota grátis; cota acabou (429/402) = SemIA, ninguém paga nada."""
    import urllib.error
    msgs = ([{"role": "system", "content": sistema}] if sistema else []) + [{"role": "user", "content": pergunta}]
    ultimo = None
    for m in ([modelo] if modelo else OLLAMA_MODELOS):
        try:
            r = _post_json("https://ollama.com/api/chat",
                           {"model": m, "messages": msgs, "stream": False, "options": {"num_predict": max(max_tokens, 3000)}},
                           {"Authorization": f"Bearer {os.environ['OLLAMA_API_KEY']}"}, timeout=150)
            texto = ((r.get("message") or {}).get("content") or "").strip()
            if texto:
                return texto
            ultimo = f"{m} devolveu resposta vazia"
        except urllib.error.HTTPError as e:
            corpo = e.read().decode(errors="replace")[:300]
            if e.code in (402, 429):
                raise SemIA(f"cota grátis do Ollama esgotada por agora ({e.code})")
            ultimo = f"{m}: {e.code} {corpo}"
            if e.code in (400, 404):
                continue
            raise SemIA(f"Ollama respondeu {ultimo}")
    raise SemIA(f"Ollama sem resposta: {ultimo}")


def ollama_ferramentas(mensagens, sistema, ferramentas, modelo=None):
    """gpt-oss grátis usando ferramentas, no formato de mensagens da Anthropic (o atendente do PC/Mac manda assim):
    converte para o /api/chat do Ollama e devolve {"content": [blocos text/tool_use], "usage": {...}, "modelo": ...}.
    Resultados de ferramenta antigos são encurtados (só os 2 últimos vão inteiros) para caber e ficar rápido."""
    import urllib.error
    import uuid
    if not tem("ollama"):
        raise SemIA("sem chave do Ollama")
    tools = [{"type": "function", "function": {"name": f["name"], "description": f.get("description", ""),
                                               "parameters": f.get("input_schema") or {"type": "object", "properties": {}}}}
             for f in ferramentas]
    msgs = [{"role": "system", "content": sistema}] if sistema else []
    n_res = sum(1 for m in mensagens if m.get("role") == "user" and isinstance(m.get("content"), list))
    visto = 0
    for m in mensagens:
        c = m.get("content")
        if isinstance(c, str):
            msgs.append({"role": m["role"], "content": c})
            continue
        if m["role"] == "assistant":
            texto = " ".join(b.get("text", "") for b in c if b.get("type") == "text").strip()
            calls = [{"function": {"name": b["name"], "arguments": b.get("input") or {}}} for b in c if b.get("type") == "tool_use"]
            msgs.append({"role": "assistant", "content": texto, **({"tool_calls": calls} if calls else {})})
        else:
            visto += 1
            for b in c:
                if b.get("type") == "tool_result":
                    conteudo = str(b.get("content") or "")
                    msgs.append({"role": "tool", "content": conteudo if visto > n_res - 2 else conteudo[:600]})
    ultimo = None
    for mod in ([modelo] if modelo else OLLAMA_MODELOS):
        try:
            r = _post_json("https://ollama.com/api/chat", {"model": mod, "messages": msgs, "tools": tools, "stream": False,
                                                          "options": {"num_predict": 2000}},
                           {"Authorization": f"Bearer {os.environ['OLLAMA_API_KEY']}"}, timeout=150)
        except urllib.error.HTTPError as e:
            if e.code in (402, 429):
                raise SemIA(f"cota grátis do Ollama esgotada por agora ({e.code})")
            ultimo = f"{mod}: {e.code}"
            continue
        msg = r.get("message") or {}
        blocos = [{"type": "text", "text": msg["content"]}] if (msg.get("content") or "").strip() else []
        for tc in msg.get("tool_calls") or []:
            f = tc.get("function") or {}
            args = f.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            blocos.append({"type": "tool_use", "id": "g" + uuid.uuid4().hex[:12], "name": f.get("name"), "input": args})
        if blocos:
            return {"content": blocos, "modelo": mod, "usage": {"input_tokens": int(r.get("prompt_eval_count") or 0),
                                                                "output_tokens": int(r.get("eval_count") or 0)}}
        ultimo = f"{mod} devolveu resposta vazia"
    raise SemIA(f"gpt-oss sem resposta: {ultimo}")


def ollama_web(pergunta, max_resultados=5):
    """Busca grátis na internet pela conta do Ollama (cota grátis, mesma chave do gpt-oss): se a pergunta tiver links,
    lê as páginas (web_fetch); senão busca (web_search). -> lista de {titulo, url, texto}. Falhou: levanta SemIA."""
    import urllib.error
    if not tem("ollama"):
        raise SemIA("sem chave do Ollama")
    cab = {"Authorization": f"Bearer {os.environ['OLLAMA_API_KEY']}"}
    urls = re.findall(r"https?://[^\s)\]>\"']+", pergunta or "")[:2]
    try:
        if urls:
            out = []
            for u in urls:
                r = _http_json("https://ollama.com/api/web_fetch", {"url": u.rstrip(".,;")}, cab, timeout=60)
                out.append({"titulo": r.get("title") or "", "url": u, "texto": r.get("content") or ""})
            return out
        r = _http_json("https://ollama.com/api/web_search", {"query": str(pergunta)[:300], "max_results": max_resultados},
                       cab, timeout=60)
        return [{"titulo": x.get("title") or "", "url": x.get("url") or "", "texto": x.get("content") or ""}
                for x in r.get("results") or []]
    except urllib.error.HTTPError as e:
        raise SemIA(f"busca do Ollama respondeu {e.code}")
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise SemIA(f"busca do Ollama falhou: {str(e)[:80]}")


# Registro de uso (aba Agentes): nubi_web liga USO["gravar"]; cada chamada grava início, fim, tokens e modelo.
USO = {"gravar": None, "origem": "", "web": None, "quem": None,   # web: guarda cada pesquisa na internet na base de conhecimento (26/09)
       "nivel": None, "gasto": None, "espera": None, "local": False}   # teto por provedor (card #10)
PROVEDOR = (("api.anthropic.com", "claude"), ("api.openai.com", "chatgpt"), ("api.deepseek.com", "deepseek"),
            ("ollama.com", "gptoss"), ("generativelanguage.googleapis.com", "gemini"))

# Teto de custo por provedor (card #10): NUBI_TETO_<PROVEDOR> = "dia/mês" em US$ (ex.: NUBI_TETO_DEEPSEEK="2/30"; um lado
# vazio = sem teto nesse período), somado em agentes_uso com o dia e o mês de Brasília (USO["gasto"]). Estourou: tarefa de
# texto/triagem (USO["nivel"]) cai para o modelo local (gpt-oss grátis, gravado como agente 'local', custo 0); conferência
# de número, nível 3 e o que não disser o nível ficam em espera (EmEspera, sem chamar o provedor) e o dono é avisado.
TETO_PROVEDORES = {"deepseek": "DeepSeek", "codex": "Codex", "sonnet": "Claude Sonnet", "claude_code": "Claude Code",
                    "gemini": "Gemini"}
NIVEL_DEGRADA = ("texto", "triagem")


class EmEspera(SemIA):
    pass


def provedor(agente, modelo):
    """Provedor do teto a partir da linha de agentes_uso (não há coluna própria): Codex e Sonnet pelo nome do modelo."""
    m = str(modelo or "").lower()
    if agente == "deepseek":
        return "deepseek"
    if agente == "chatgpt" and "codex" in m:
        return "codex"
    if agente == "claude" and "sonnet" in m:
        return "sonnet"
    if agente == "claude_mac":                         # Ferreiro (Claude Code no Mac); o teto dele na hora é NUBI_FERREIRO_TETO
        return "claude_code"
    if agente == "gemini":                             # conector de criativos (card #14); teto próprio NUBI_TETO_GEMINI
        return "gemini"
    return None


def teto(prov):
    """(teto do dia, teto do mês) em US$ do provedor; None = sem teto nesse período."""
    partes = (os.environ.get(f"NUBI_TETO_{prov.upper()}") or "").split("/")
    out = []
    for p in (partes + [""])[:2]:
        try:
            out.append(float(p.replace(",", ".")) if p.strip() else None)
        except ValueError:
            out.append(None)
    return tuple(out)


def _conferir_teto(agente, modelo):
    prov = provedor(agente, modelo)
    if not prov or not USO.get("gasto"):
        return
    t_dia, t_mes = teto(prov)
    if t_dia is None and t_mes is None:
        return
    try:
        g_dia, g_mes = USO["gasto"](prov)
    except Exception:  # noqa: BLE001 — sem conseguir somar não trava nada (o custo continua registrado)
        return
    if t_dia is not None and g_dia >= t_dia:
        raise EmEspera(f"teto diário do {TETO_PROVEDORES[prov]} atingido (US$ {g_dia:.2f} de US$ {t_dia:.2f})")
    if t_mes is not None and g_mes >= t_mes:
        raise EmEspera(f"teto mensal do {TETO_PROVEDORES[prov]} atingido (US$ {g_mes:.2f} de US$ {t_mes:.2f})")


def _tokens(r):
    """(entrada, leitura de cache, criação de cache, saída) da resposta de qualquer provedor, cada um bruto como
    veio da API (a Anthropic já manda input_tokens SEM os tokens de cache: nunca somar aqui, senão cobra cache
    duas vezes no chamador). Sem uso relatado pelo provedor: os 4 ficam None (nunca 0)."""
    u = r.get("usage") or {}
    ent = u.get("input_tokens", u.get("prompt_tokens", r.get("prompt_eval_count")))
    sai = u.get("output_tokens", u.get("completion_tokens", r.get("eval_count")))
    if ent is None and sai is None:
        um = r.get("usageMetadata") or {}               # Gemini (card #14): promptTokenCount/candidatesTokenCount
        ent, sai = um.get("promptTokenCount"), um.get("candidatesTokenCount")
    if ent is None and sai is None:
        return None, None, None, None                   # provedor não mandou o uso: fica sem número (não zero)
    leitura = int(u.get("cache_read_input_tokens") or 0)
    criacao = int(u.get("cache_creation_input_tokens") or 0)
    return int(ent or 0), leitura, criacao, int(sai or 0)


CACHE_MIN_CHARS = 2000    # ~570 tokens: acima do mínimo do cache dos modelos Opus 5 (512 tokens)


def _http_json(url, corpo, cab, timeout=90):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **cab})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _post_json(url, corpo, cab, timeout=90):
    agente = next((a for h, a in PROVEDOR if h in url), None)
    if agente == "chatgpt" and "astra" in str(corpo.get("model") or ""):
        agente = "astra"                               # o designer (gpt-6-astra) tem cartão e custo próprios
    if agente and USO.get("local"):
        agente = "local"                               # tarefa degradada pelo teto: nunca fica no provedor original
    if agente:
        _conferir_teto(agente, corpo.get("model"))     # antes de chamar: estourou, nem chega no provedor
    gravar = USO["gravar"] if agente else None
    rid = None
    if gravar:
        try:
            # 27/09: agente com nome próprio (ex.: Banguela, o atendimento no Sonnet) aparece com cartão e custo dele
            rid = gravar("inicio", {"agente": USO.get("apelido_agente") or agente, "modelo": str(corpo.get("model") or ""),
                                    "origem": USO["origem"]})
        except Exception:  # noqa: BLE001 — o registro nunca derruba a chamada
            rid = None
    t0 = time.monotonic()
    try:
        r = _http_json(url, corpo, cab, timeout)
    except Exception as e:
        if gravar:
            try:
                gravar("fim", {"id": rid, "ok": False, "erro": str(e)[:300], "latencia_ms": int((time.monotonic() - t0) * 1000)})
            except Exception:  # noqa: BLE001
                pass
        raise
    if gravar:
        try:
            ent, leitura, criacao, sai = _tokens(r)
            gravar("fim", dict({"id": rid, "ok": True, "modelo": str(r.get("model") or corpo.get("model") or ""),
                                "tokens_in": ent, "cache_read_tokens": leitura, "cache_creation_tokens": criacao,
                                "tokens_out": sai, "latencia_ms": int((time.monotonic() - t0) * 1000)},
                               **({"custo_usd": 0.0} if agente == "local" else {})))
        except Exception:  # noqa: BLE001
            pass
    return r


def perguntar(pergunta, web=True, max_tokens=1500, qual=None, modelo=None, sistema=None, imagens=None, timeout=None):
    """
    qual: 'chatgpt', 'claude', 'deepseek' ou 'codex' (ChatGPT com o modelo de código) — padrão: disponivel();
    modelo: troca o modelo só nesta pergunta ('pro' no DeepSeek = o modelo maior); sistema: instruções fixas do agente.
    timeout: segundos de espera na OpenAI (padrão 90; a pesquisa na web do Astra usa mais).
    Teto do provedor estourado (card #10): texto/triagem responde no modelo local ('local'); o resto fica em espera.
    """
    try:
        return _perguntar(pergunta, web, max_tokens, qual, modelo, sistema, imagens, timeout)
    except EmEspera as e:
        if USO.get("nivel") not in NIVEL_DEGRADA or not tem("ollama"):
            if USO.get("espera"):
                try:
                    USO["espera"](str(e))
                except Exception:  # noqa: BLE001 — o aviso nunca troca o erro
                    pass
            raise
        USO["local"] = True
        try:
            return _ollama(pergunta, max_tokens, None, sistema), [], "local"
        finally:
            USO["local"] = False


def _perguntar(pergunta, web=True, max_tokens=1500, qual=None, modelo=None, sistema=None, imagens=None, timeout=None):
    ia = qual or disponivel()
    if ia == "codex":
        if not tem("chatgpt"):
            raise SemIA("falta a chave da OpenAI")
        mc = modelo_codex()
        try:
            t, l, _ = _perguntar(pergunta, web=False, max_tokens=max(max_tokens, 4000), qual="chatgpt", modelo=mc, sistema=sistema)
            if t:
                return t, l, "chatgpt"
        except EmEspera:
            raise                                      # teto do Codex: não troca por outro modelo pago
        except Exception:  # noqa: BLE001 — Codex fora do ar ou sem acesso: o modelo padrão responde
            pass
        return _perguntar(pergunta, web=False, max_tokens=max_tokens, qual="chatgpt", sistema=sistema)
    if ia == "deepseek" and not USO.get("deepseek_ok"):
        raise SemIA("o DeepSeek só faz as 2 análises do dia (dados coletados e estoque)")
    if not ia or not tem(ia):
        raise SemIA("nenhuma chave de IA configurada" if not ia else f"falta a chave da IA {nome(ia)}")
    if ia == "ollama":
        return _ollama(pergunta, max_tokens, modelo, sistema), [], ia
    if ia == "deepseek":
        # modelo="flash": reserva barata da IA grátis (textos do atendimento, resumo de pesquisa); o resto usa o v4-pro
        lista = DEEPSEEK_FLASH if modelo == "flash" else DEEPSEEK_PRO if modelo == "pro" else None
        return _deepseek(pergunta, max_tokens, None if modelo in ("pro", "flash") else modelo, sistema, lista).strip(), [], ia
    if ia == "claude":
        # o Claude sempre raciocina antes e isso conta no max_tokens: folga de 16 mil para sobrar a resposta
        conteudo = pergunta
        if imagens:                                     # fotos e quadros de vídeo da Sala (26/09)
            conteudo = [{"type": "image", "source": {"type": "base64", "media_type": _tipo_img(u), "data": u.split(",", 1)[1]}}
                        for u in imagens] + [{"type": "text", "text": pergunta}]
        corpo = {"model": modelo or os.environ.get("NUBI_IA_MODELO_CLAUDE", "claude-opus-5-5"),
                 "max_tokens": max(max_tokens, 16000), "messages": [{"role": "user", "content": conteudo}]}
        if sistema:
            # cache do briefing (26/09, aprovado pelo Bruno): o SISTEMA é igual em todas as chamadas; guardado no cache, as
            # seguintes (5 min) pagam ~1/10 da entrada. Texto curto (abaixo do mínimo do cache) vai sem marcação.
            corpo["system"] = ([{"type": "text", "text": sistema, "cache_control": {"type": "ephemeral"}}]
                               if len(sistema) >= CACHE_MIN_CHARS else sistema)
        if web:
            corpo["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}]
        cab = {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"}
        r = _post_json("https://api.anthropic.com/v1/messages", corpo, cab, timeout=200)
        texto = " ".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text")
        if not texto.strip() and r.get("stop_reason") == "max_tokens":
            # pensou demais e não sobrou resposta: repete pensando menos
            r = _post_json("https://api.anthropic.com/v1/messages", dict(corpo, output_config={"effort": "low"}), cab, timeout=200)
            texto = " ".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text")
        if not texto.strip():
            raise SemIA(f"Claude sem resposta (fim: {r.get('stop_reason')})")
        links = [c.get("url") for b in r.get("content", []) for c in (b.get("citations") or []) if c.get("url")]
    else:
        entrada = pergunta
        if imagens:                                     # fotos e quadros de vídeo da Sala (26/09)
            entrada = [{"role": "user", "content": [{"type": "input_text", "text": pergunta}]
                        + [{"type": "input_image", "image_url": u} for u in imagens]}]
        corpo = {"model": modelo or os.environ.get("NUBI_IA_MODELO", "gpt-4.1"), "input": entrada, "max_output_tokens": max_tokens}
        if sistema:
            corpo["instructions"] = sistema
        if web:
            corpo["tools"] = [{"type": "web_search_preview"}]
        r = _post_json("https://api.openai.com/v1/responses", corpo,
                       {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}, timeout=timeout or 90)
        partes = [c for o in r.get("output", []) if o.get("type") == "message" for c in o.get("content", [])]
        texto = " ".join(c.get("text", "") for c in partes)
        links = [a.get("url") for c in partes for a in (c.get("annotations") or []) if a.get("url")]
    links = list(dict.fromkeys(l for l in links if l))
    if web and USO.get("web"):
        try:                                           # pedido do Bruno: toda pesquisa na internet fica guardada na base
            USO["web"](pergunta, texto.strip(), links, ia)
        except Exception:  # noqa: BLE001 — guardar nunca derruba a resposta
            pass
    return texto.strip(), links, ia


def _tipo_img(url_dados):
    m = re.match(r"data:(image/[a-z+]+);base64,", url_dados or "")
    return m.group(1) if m else "image/jpeg"


def transcrever(audio, nome="audio.wav"):
    """Fala -> texto (OpenAI; português). audio: bytes de um arquivo de até 25 MB (wav, mp3, m4a, mp4, webm)."""
    import uuid
    if not os.environ.get("OPENAI_API_KEY"):
        raise SemIA("transcrição precisa da OPENAI_API_KEY")
    ultimo = None
    for modelo in (os.environ.get("NUBI_IA_TRANSCRICAO", "gpt-4o-transcribe"), "whisper-1"):
        b = uuid.uuid4().hex
        partes = [f"--{b}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{modelo}\r\n".encode(),
                  f"--{b}\r\nContent-Disposition: form-data; name=\"language\"\r\n\r\npt\r\n".encode(),
                  f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{nome}\"\r\n"
                  f"Content-Type: application/octet-stream\r\n\r\n".encode() + audio + b"\r\n",
                  f"--{b}--\r\n".encode()]
        req = urllib.request.Request("https://api.openai.com/v1/audio/transcriptions", data=b"".join(partes), method="POST",
                                     headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                                              "Content-Type": f"multipart/form-data; boundary={b}"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return (json.loads(r.read().decode()).get("text") or "").strip()
        except urllib.error.HTTPError as e:
            ultimo = f"{modelo}: {e.code} {e.read().decode(errors='replace')[:200]}"
    raise SemIA(f"transcrição falhou ({ultimo})")


def _primeiro_json(texto):
    """Primeiro objeto JSON (dict) dentro de texto: tenta json.JSONDecoder().raw_decode a partir de cada '{',
    ignorando chaves soltas ou inválidas (a regex antiga \\{.*\\} gulosa pegava do primeiro '{' ao último '}',
    quebrando com texto depois do JSON ou dois objetos seguidos). Lista/string na resposta não têm '{': devolve {}."""
    dec = json.JSONDecoder()
    i = texto.find("{")
    while i != -1:
        try:
            obj, _ = dec.raw_decode(texto, i)
        except ValueError:
            obj = None
        if isinstance(obj, dict):
            return obj
        i = texto.find("{", i + 1)
    return {}


def perguntar_json(pergunta, web=True, max_tokens=1500, qual=None, sistema=None, modelo=None):
    texto, links, ia = perguntar(pergunta, web, max_tokens, qual=qual, modelo=modelo, sistema=sistema)
    return _primeiro_json(texto), links, ia


def perguntar_estruturado(pergunta, schema, nome="resposta", max_tokens=2500, qual=None, modelo=None):
    """
    Resposta em JSON que segue `schema` (JSON Schema) -> (dict, nome_da_ia).
    ChatGPT: structured outputs (o modelo é obrigado a seguir o formato). Claude: pede o JSON e confere.
    qual/modelo fixos (mini-benchmark #15): só esse modelo responde, sem trocar de provedor.
    """
    ia = qual or disponivel()
    if not ia:
        raise SemIA("nenhuma chave de IA configurada")
    if ia == "chatgpt":
        corpo = {"model": modelo or os.environ.get("NUBI_IA_MODELO", "gpt-4.1"), "input": pergunta, "max_output_tokens": max_tokens,
                 "text": {"format": {"type": "json_schema", "name": nome, "schema": schema, "strict": True}}}
        try:
            r = _post_json("https://api.openai.com/v1/responses", corpo,
                           {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}, timeout=150)
            texto = " ".join(c.get("text", "") for o in r.get("output", []) if o.get("type") == "message"
                             for c in o.get("content", []))
            j = json.loads(texto)
            if not erros_schema(j, schema):
                return j, ia
        except Exception:  # noqa: BLE001 — ChatGPT fora do ar, JSON quebrado ou fora do formato: tenta o Claude
            pass
    # sem ChatGPT (ou ele falhou): o Claude responde e o JSON é conferido contra o schema
    qual = qual or ("claude" if tem("claude") else ("chatgpt" if tem("chatgpt") else None))
    if not qual:
        raise SemIA("nenhuma IA disponível para a resposta estruturada")
    pedido = (pergunta + "\n\nResponda SOMENTE com um JSON válido que siga exatamente este JSON Schema, sem texto antes "
              "ou depois:\n" + json.dumps(schema, ensure_ascii=False))
    ultimo = "resposta vazia"
    for _ in range(2):
        j, _, q = perguntar_json(pedido, web=False, max_tokens=max_tokens, qual=qual, modelo=modelo)
        falhas = erros_schema(j, schema) if j else ["não veio JSON"]
        if not falhas:
            return j, q
        ultimo = "; ".join(falhas[:3])
    raise SemIA(f"a IA não devolveu o JSON no formato pedido ({ultimo})")


def gemini_gerar_imagem(prompt, modelo=None):
    """Conector Gemini para as rotinas de criativo (imagem/post do Instagram, card #14): gera 1 imagem a partir de
    `prompt`. Teto mensal próprio (NUBI_TETO_GEMINI, regra do card #10) e custo por ia_precos, iguais aos outros
    provedores (_post_json cuida dos dois). Sem GEMINI_API_KEY: SemIA. Devolve (imagem_b64, texto, modelo).
    A chave vai no cabeçalho (x-goog-api-key), nunca na URL, para não vazar em log de erro."""
    if not tem("gemini"):
        raise SemIA(f"falta a chave {CHAVES['gemini']}")
    modelo = modelo or os.environ.get("NUBI_IA_MODELO_GEMINI", "gemini-2.5-flash-image")
    corpo = {"model": modelo, "contents": [{"parts": [{"text": prompt}]}]}
    cab = {"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"}
    try:
        r = _post_json(f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent", corpo, cab,
                       timeout=120)
    except EmEspera as e:
        # sem fallback local (card #10 só degrada texto/triagem): registra o aviso ao dono e sobe o erro
        if USO.get("espera"):
            try:
                USO["espera"](str(e))
            except Exception:  # noqa: BLE001 — o aviso nunca troca o erro
                pass
        raise
    partes = [p for c in (r.get("candidates") or []) for p in (c.get("content", {}).get("parts") or [])]
    imagem_b64 = next((p["inlineData"]["data"] for p in partes if (p.get("inlineData") or {}).get("data")), None)
    texto = " ".join(p.get("text", "") for p in partes if p.get("text"))
    if not imagem_b64:
        motivo = ((r.get("candidates") or [{}])[0]).get("finishReason", "sem candidatos")
        raise SemIA(f"Gemini não devolveu imagem (motivo: {motivo})")
    return imagem_b64, texto.strip(), modelo


def gemini_texto(pergunta, web=True, max_tokens=4000, modelo=None, sistema=None, timeout=150):
    """30/09 (Bruno: "talvez o Gemini do Google"): texto com a busca do Google (grounding) — o 4º pesquisador. Devolve
    (texto, links). Sem GEMINI_API_KEY: SemIA. Chave só no cabeçalho, nunca na URL."""
    if not tem("gemini"):
        raise SemIA(f"falta a chave {CHAVES['gemini']}")
    modelo = modelo or os.environ.get("NUBI_IA_MODELO_GEMINI_TEXTO", "gemini-2.5-flash")
    corpo = {"contents": [{"role": "user", "parts": [{"text": pergunta}]}],
             "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3}}
    if sistema:
        corpo["systemInstruction"] = {"parts": [{"text": sistema}]}
    if web:
        corpo["tools"] = [{"google_search": {}}]
    cab = {"x-goog-api-key": os.environ["GEMINI_API_KEY"], "Content-Type": "application/json"}
    r = _post_json(f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent", corpo, cab, timeout=timeout)
    cands = r.get("candidates") or []
    partes = [p for c in cands for p in (c.get("content", {}).get("parts") or [])]
    texto = "\n".join(p.get("text", "") for p in partes if p.get("text")).strip()
    links = []
    for ch in (cands[0].get("groundingMetadata", {}).get("groundingChunks") or []) if cands else []:
        u = (ch.get("web") or {}).get("uri")
        if u and u not in links:
            links.append(u)
    if not texto:
        raise SemIA(f"Gemini não devolveu texto ({(cands[0].get('finishReason') if cands else 'sem candidatos')})")
    return texto, links[:30]


_TIPOS_SCHEMA = {"object": dict, "array": list, "string": str, "boolean": bool, "integer": int, "number": (int, float)}


def _ok(v, x):
    """v bate com o tipo simples x do JSON Schema (bool nunca conta como integer/number)."""
    if x == "null":
        return v is None
    if x in ("integer", "number") and isinstance(v, bool):
        return False
    return isinstance(v, _TIPOS_SCHEMA.get(x, object))


def erros_schema(v, sc, caminho="$"):
    """Conferência simples de JSON Schema (type, required, properties, additionalProperties, enum, items)."""
    t = sc.get("type")
    if isinstance(t, list):
        if not any(_ok(v, x) for x in t):
            return [f"{caminho}: tipo {type(v).__name__} fora de {t}"]
    elif t and t != "null" and not _ok(v, t):
        return [f"{caminho}: esperado {t}"]
    if "enum" in sc and v not in sc["enum"]:
        return [f"{caminho}: valor fora da lista"]
    out = []
    if isinstance(v, dict):
        props = sc.get("properties") or {}
        out += [f"{caminho}.{k}: faltando" for k in sc.get("required") or [] if k not in v]
        if sc.get("additionalProperties") is False:
            out += [f"{caminho}.{k}: campo a mais" for k in v if k not in props]
        for k, sub in props.items():
            if k in v:
                out += erros_schema(v[k], sub, f"{caminho}.{k}")
    if isinstance(v, list) and isinstance(sc.get("items"), dict):
        for i, x in enumerate(v):
            out += erros_schema(x, sc["items"], f"{caminho}[{i}]")
    return out


class LimiteProvedor(SemIA):
    """HTTP 429 do provedor esgotou as 3 tentativas (card #110): quem chama trata como pendente, não como erro."""
    pass


def _espera_429(erro, tentativa):
    """Segundos para esperar antes de tentar de novo: Retry-After do provedor, senão 30s/60s/120s (card #110)."""
    try:
        return float(erro.headers.get("Retry-After"))
    except (TypeError, ValueError, AttributeError):
        return (30, 60, 120)[tentativa]


def embeddings(textos, modelo=None, progresso=None, limite_seg=None):
    """
    Vetores de significado dos textos (OpenAI), na mesma ordem; lotes de 500.
    HTTP 429: espera (Retry-After do provedor, senão 30s/60s/120s) e tenta de novo, até 3 vezes por lote; esgotou,
    levanta LimiteProvedor em vez de deixar subir como erro genérico (card #110).
    progresso(inicio, vetores_do_lote), se dado, roda a cada lote pronto — quem chama pode gravar na hora e retomar
    do lote que parou se as tentativas se esgotarem, sem recalcular o que já foi feito.
    limite_seg, se dado, é o orçamento total de tempo desta chamada: um provedor com rate limit sustentado pode
    somar bem mais que 30+60+120s em textos com muitos lotes, e isso estouraria o tempo da função da Vercel (a
    plataforma mata o processo sem levantar exceção — nem a rotina fica "pendente" nem as rotinas seguintes da
    mesma passada rodam). Em vez de deixar isso acontecer, levanta LimiteProvedor assim que o tempo já gasto (mais
    a próxima espera) ultrapassaria o limite, sem dormir além da conta.
    """
    if not os.environ.get("OPENAI_API_KEY"):
        raise SemIA("embeddings precisam da OPENAI_API_KEY")
    t0 = time.monotonic()
    saida = []
    for i in range(0, len(textos), 500):
        lote = textos[i:i + 500]
        r = None
        for tentativa in range(3):
            if limite_seg is not None and time.monotonic() - t0 >= limite_seg:
                raise LimiteProvedor("tempo esgotado (limite_seg) antes de terminar todos os lotes")
            try:
                r = _post_json("https://api.openai.com/v1/embeddings",
                               {"model": modelo or os.environ.get("NUBI_IA_EMBED", "text-embedding-3-small"), "input": lote},
                               {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}, timeout=120)
                break
            except urllib.error.HTTPError as e:
                if e.code != 429:
                    raise
                if tentativa == 2:
                    raise LimiteProvedor("HTTP 429 (limite do provedor) mesmo após 3 tentativas") from e
                espera = _espera_429(e, tentativa)
                if limite_seg is not None and time.monotonic() - t0 + espera >= limite_seg:
                    raise LimiteProvedor("tempo esgotado (limite_seg) esperando o provedor responder") from e
                time.sleep(espera)
        vet = [d["embedding"] for d in sorted(r["data"], key=lambda d: d["index"])]
        saida.extend(vet)
        if progresso:
            progresso(i, vet)
    return saida


# ---------------------------------------------------------------------------
# Batch da OpenAI: muitos pedidos de uma vez pela metade do preço; o resultado sai em até 24 h.
# ---------------------------------------------------------------------------
def _openai(metodo, caminho, corpo=None, cab=None, timeout=120, bruto=False):
    req = urllib.request.Request("https://api.openai.com/v1/" + caminho, data=corpo, method=metodo,
                                 headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", **(cab or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        dados = r.read()
    return dados if bruto else json.loads(dados.decode())


def lote_criar(pedidos, nome="nubi"):
    """
    pedidos: [(custom_id, corpo do /v1/responses)]. Sobe o arquivo JSONL e cria o lote. Devolve o id do lote.
    """
    if not os.environ.get("OPENAI_API_KEY"):
        raise SemIA("o lote precisa da OPENAI_API_KEY")
    jsonl = "\n".join(json.dumps({"custom_id": cid, "method": "POST", "url": "/v1/responses", "body": corpo},
                                 ensure_ascii=False) for cid, corpo in pedidos).encode()
    fronteira = "nubi" + os.urandom(8).hex()
    partes = (f"--{fronteira}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\nbatch\r\n"
              f"--{fronteira}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{nome}.jsonl\"\r\n"
              "Content-Type: application/jsonl\r\n\r\n").encode() + jsonl + f"\r\n--{fronteira}--\r\n".encode()
    arq = _openai("POST", "files", partes, {"Content-Type": f"multipart/form-data; boundary={fronteira}"})
    lote = _openai("POST", "batches", json.dumps({"input_file_id": arq["id"], "endpoint": "/v1/responses",
                                                  "completion_window": "24h", "metadata": {"nubi": nome}}).encode(),
                   {"Content-Type": "application/json"})
    return lote["id"]


def lote_status(lote_id):
    """{status, output_file_id, request_counts, ...} do lote (status: validating, in_progress, completed, failed…)."""
    return _openai("GET", f"batches/{lote_id}")


def lote_resultados(output_file_id, falhas=None, error_file_id=None):
    """
    {custom_id: texto da resposta} de um lote concluído. Os pedidos que falharam (erro, status diferente de 200 ou
    resposta vazia) não somem: vão para a lista `falhas` como {"id", "erro"} para a rotina tratar como pendentes.
    """
    saida = {}
    falhas = falhas if falhas is not None else []
    for linha in _openai("GET", f"files/{output_file_id}/content", bruto=True).decode().splitlines():
        if not linha.strip():
            continue
        j = json.loads(linha)
        resp = j.get("response") or {}
        corpo = resp.get("body") or {}
        texto = " ".join(c.get("text", "") for o in corpo.get("output", []) if o.get("type") == "message"
                         for c in o.get("content", []))
        if j.get("error") or (resp.get("status_code") not in (None, 200)) or not texto.strip():
            falhas.append({"id": j.get("custom_id"), "erro": str(j.get("error") or resp.get("status_code") or "resposta vazia")[:200]})
            continue
        saida[j.get("custom_id")] = texto
    if error_file_id:
        for linha in _openai("GET", f"files/{error_file_id}/content", bruto=True).decode().splitlines():
            if linha.strip():
                j = json.loads(linha)
                falhas.append({"id": j.get("custom_id"), "erro": str(j.get("error") or (j.get("response") or {}).get("status_code"))[:200]})
    return saida
