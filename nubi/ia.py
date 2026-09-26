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
import urllib.request


class SemIA(Exception):
    pass


def disponivel():
    """A IA padrão do nubi: ChatGPT quando há a chave da OpenAI (os resumos foram feitos para ele); senão Claude."""
    return "chatgpt" if os.environ.get("OPENAI_API_KEY") else "claude" if os.environ.get("ANTHROPIC_API_KEY") else None


CHAVES = {"claude": "ANTHROPIC_API_KEY", "chatgpt": "OPENAI_API_KEY", "deepseek": "DEEPSEEK_API_KEY", "ollama": "OLLAMA_API_KEY"}
OLLAMA_MODELOS = ["gpt-oss:120b", "gpt-oss:20b"]   # Ollama Cloud: modelos da cota grátis da conta
DEEPSEEK_MODELOS = ["deepseek-flash", "deepseek-v4-flash", "deepseek-chat"]   # nomes mudam; tenta na ordem


def tem(qual):
    qual = "chatgpt" if qual == "codex" else qual
    return qual in CHAVES and bool(os.environ.get(CHAVES[qual]))


DEEPSEEK_PRO = ["deepseek-v4-pro"] + DEEPSEEK_MODELOS                           # tarefas pesadas (revisão de código)
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
    return {"claude": "IA (Claude)", "chatgpt": "IA (ChatGPT)", "deepseek": "IA (DeepSeek)", "ollama": "IA (gpt-oss)"}.get(ia, "IA")


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


# Registro de uso (aba Agentes): nubi_web liga USO["gravar"]; cada chamada grava início, fim, tokens e modelo.
USO = {"gravar": None, "origem": "", "web": None}   # web: guarda cada pesquisa na internet na base de conhecimento (26/09)
PROVEDOR = (("api.anthropic.com", "claude"), ("api.openai.com", "chatgpt"), ("api.deepseek.com", "deepseek"),
            ("ollama.com", "gptoss"))


def _tokens(r):
    """(entrada, leitura de cache, criação de cache, saída) da resposta de qualquer provedor, cada um bruto como
    veio da API (a Anthropic já manda input_tokens SEM os tokens de cache: nunca somar aqui, senão cobra cache
    duas vezes no chamador). Sem uso relatado pelo provedor: os 4 ficam None (nunca 0)."""
    u = r.get("usage") or {}
    ent = u.get("input_tokens", u.get("prompt_tokens", r.get("prompt_eval_count")))
    sai = u.get("output_tokens", u.get("completion_tokens", r.get("eval_count")))
    if ent is None and sai is None:
        return None, None, None, None                   # provedor não mandou o uso: fica sem número (não zero)
    leitura = int(u.get("cache_read_input_tokens") or 0)
    criacao = int(u.get("cache_creation_input_tokens") or 0)
    return int(ent or 0), leitura, criacao, int(sai or 0)


def _http_json(url, corpo, cab, timeout=90):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **cab})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _post_json(url, corpo, cab, timeout=90):
    agente = next((a for h, a in PROVEDOR if h in url), None)
    if agente == "chatgpt" and "astra" in str(corpo.get("model") or ""):
        agente = "astra"                               # o designer (gpt-6-astra) tem cartão e custo próprios
    gravar = USO["gravar"] if agente else None
    rid = None
    if gravar:
        try:
            rid = gravar("inicio", {"agente": agente, "modelo": str(corpo.get("model") or ""), "origem": USO["origem"]})
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
            gravar("fim", {"id": rid, "ok": True, "modelo": str(r.get("model") or corpo.get("model") or ""),
                           "tokens_in": ent, "cache_read_tokens": leitura, "cache_creation_tokens": criacao,
                           "tokens_out": sai, "latencia_ms": int((time.monotonic() - t0) * 1000)})
        except Exception:  # noqa: BLE001
            pass
    return r


def perguntar(pergunta, web=True, max_tokens=1500, qual=None, modelo=None, sistema=None):
    """
    qual: 'chatgpt', 'claude', 'deepseek' ou 'codex' (ChatGPT com o modelo de código) — padrão: disponivel();
    modelo: troca o modelo só nesta pergunta ('pro' no DeepSeek = o modelo maior); sistema: instruções fixas do agente.
    """
    ia = qual or disponivel()
    if ia == "codex":
        if not tem("chatgpt"):
            raise SemIA("falta a chave da OpenAI")
        mc = modelo_codex()
        try:
            t, l, _ = perguntar(pergunta, web=False, max_tokens=max(max_tokens, 4000), qual="chatgpt", modelo=mc, sistema=sistema)
            if t:
                return t, l, "chatgpt"
        except Exception:  # noqa: BLE001 — Codex fora do ar ou sem acesso: o modelo padrão responde
            pass
        return perguntar(pergunta, web=False, max_tokens=max_tokens, qual="chatgpt", sistema=sistema)
    if not ia or not tem(ia):
        raise SemIA("nenhuma chave de IA configurada" if not ia else f"falta a chave da IA {nome(ia)}")
    if ia == "ollama":
        return _ollama(pergunta, max_tokens, modelo, sistema), [], ia
    if ia == "deepseek":
        return _deepseek(pergunta, max_tokens, None if modelo == "pro" else modelo, sistema,
                         DEEPSEEK_PRO if modelo == "pro" else None).strip(), [], ia
    if ia == "claude":
        # o Claude sempre raciocina antes e isso conta no max_tokens: folga de 16 mil para sobrar a resposta
        corpo = {"model": modelo or os.environ.get("NUBI_IA_MODELO_CLAUDE", "claude-opus-5-5"),
                 "max_tokens": max(max_tokens, 16000), "messages": [{"role": "user", "content": pergunta}]}
        if sistema:
            corpo["system"] = sistema
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
        corpo = {"model": modelo or os.environ.get("NUBI_IA_MODELO", "gpt-4.1"), "input": pergunta, "max_output_tokens": max_tokens}
        if sistema:
            corpo["instructions"] = sistema
        if web:
            corpo["tools"] = [{"type": "web_search_preview"}]
        r = _post_json("https://api.openai.com/v1/responses", corpo,
                       {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
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


def perguntar_json(pergunta, web=True, max_tokens=1500, qual=None, sistema=None):
    texto, links, ia = perguntar(pergunta, web, max_tokens, qual=qual, sistema=sistema)
    return _primeiro_json(texto), links, ia


def perguntar_estruturado(pergunta, schema, nome="resposta", max_tokens=2500):
    """
    Resposta em JSON que segue `schema` (JSON Schema) -> (dict, nome_da_ia).
    ChatGPT: structured outputs (o modelo é obrigado a seguir o formato). Claude: pede o JSON e confere.
    """
    ia = disponivel()
    if not ia:
        raise SemIA("nenhuma chave de IA configurada")
    if ia == "chatgpt":
        corpo = {"model": os.environ.get("NUBI_IA_MODELO", "gpt-4.1"), "input": pergunta, "max_output_tokens": max_tokens,
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
    qual = "claude" if tem("claude") else ("chatgpt" if tem("chatgpt") else None)
    if not qual:
        raise SemIA("nenhuma IA disponível para a resposta estruturada")
    pedido = (pergunta + "\n\nResponda SOMENTE com um JSON válido que siga exatamente este JSON Schema, sem texto antes "
              "ou depois:\n" + json.dumps(schema, ensure_ascii=False))
    ultimo = "resposta vazia"
    for _ in range(2):
        j, _, q = perguntar_json(pedido, web=False, max_tokens=max_tokens, qual=qual)
        falhas = erros_schema(j, schema) if j else ["não veio JSON"]
        if not falhas:
            return j, q
        ultimo = "; ".join(falhas[:3])
    raise SemIA(f"a IA não devolveu o JSON no formato pedido ({ultimo})")


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


def embeddings(textos, modelo=None):
    """Vetores de significado dos textos (OpenAI), na mesma ordem; lotes de 500."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise SemIA("embeddings precisam da OPENAI_API_KEY")
    saida = []
    for i in range(0, len(textos), 500):
        r = _post_json("https://api.openai.com/v1/embeddings",
                       {"model": modelo or os.environ.get("NUBI_IA_EMBED", "text-embedding-3-small"), "input": textos[i:i + 500]},
                       {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}, timeout=120)
        saida.extend(d["embedding"] for d in sorted(r["data"], key=lambda d: d["index"]))
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
