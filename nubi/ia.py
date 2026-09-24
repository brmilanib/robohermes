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


def _post_json(url, corpo, cab, timeout=90):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **cab})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


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
    return texto.strip(), list(dict.fromkeys(l for l in links if l)), ia


def perguntar_json(pergunta, web=True, max_tokens=1500, qual=None, sistema=None):
    texto, links, ia = perguntar(pergunta, web, max_tokens, qual=qual, sistema=sistema)
    m = re.search(r"\{.*\}", texto, re.S)
    try:
        j = json.loads(m.group(0)) if m else {}
    except ValueError:
        j = {}
    return j, links, ia


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
        r = _post_json("https://api.openai.com/v1/responses", corpo,
                       {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}, timeout=150)
        texto = " ".join(c.get("text", "") for o in r.get("output", []) if o.get("type") == "message"
                         for c in o.get("content", []))
        return json.loads(texto), ia
    pedido = (pergunta + "\n\nResponda SOMENTE com um JSON válido que siga exatamente este JSON Schema, sem texto antes "
              "ou depois:\n" + json.dumps(schema, ensure_ascii=False))
    for _ in range(2):
        j, _, qual = perguntar_json(pedido, web=False, max_tokens=max_tokens)
        if j:
            return j, qual
    raise SemIA("a IA não devolveu o JSON pedido")


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


def lote_resultados(output_file_id):
    """{custom_id: texto da resposta} de um lote concluído."""
    saida = {}
    for linha in _openai("GET", f"files/{output_file_id}/content", bruto=True).decode().splitlines():
        if not linha.strip():
            continue
        j = json.loads(linha)
        corpo = ((j.get("response") or {}).get("body") or {})
        saida[j.get("custom_id")] = " ".join(c.get("text", "") for o in corpo.get("output", []) if o.get("type") == "message"
                                            for c in o.get("content", []))
    return saida
