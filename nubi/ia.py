# -*- coding: utf-8 -*-
"""
IA do nubi: ChatGPT (OPENAI_API_KEY) ou Claude (ANTHROPIC_API_KEY), a que tiver chave na Vercel.

perguntar(pergunta, web=True) -> (texto, links, nome_da_ia)
perguntar_json(pergunta, web=True) -> (dict, links, nome_da_ia)   # a pergunta pede um JSON na resposta
Com web=True a IA pesquisa na internet antes de responder (web search das duas APIs).
Modelo: NUBI_IA_MODELO (padrão gpt-4.1 / claude-sonnet-5).
"""

import json
import os
import re
import urllib.request


class SemIA(Exception):
    pass


def disponivel():
    return "claude" if os.environ.get("ANTHROPIC_API_KEY") else "chatgpt" if os.environ.get("OPENAI_API_KEY") else None


def nome(ia=None):
    ia = ia or disponivel()
    return {"claude": "IA (Claude)", "chatgpt": "IA (ChatGPT)"}.get(ia, "IA")


def _post_json(url, corpo, cab, timeout=90):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **cab})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def perguntar(pergunta, web=True, max_tokens=1500):
    ia = disponivel()
    if not ia:
        raise SemIA("nenhuma chave de IA configurada")
    if ia == "claude":
        corpo = {"model": os.environ.get("NUBI_IA_MODELO", "claude-sonnet-5"), "max_tokens": max_tokens,
                 "messages": [{"role": "user", "content": pergunta}]}
        if web:
            corpo["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}]
        r = _post_json("https://api.anthropic.com/v1/messages", corpo,
                       {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
        texto = " ".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text")
        links = [c.get("url") for b in r.get("content", []) for c in (b.get("citations") or []) if c.get("url")]
    else:
        corpo = {"model": os.environ.get("NUBI_IA_MODELO", "gpt-4.1"), "input": pergunta}
        if web:
            corpo["tools"] = [{"type": "web_search_preview"}]
        r = _post_json("https://api.openai.com/v1/responses", corpo,
                       {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
        partes = [c for o in r.get("output", []) if o.get("type") == "message" for c in o.get("content", [])]
        texto = " ".join(c.get("text", "") for c in partes)
        links = [a.get("url") for c in partes for a in (c.get("annotations") or []) if a.get("url")]
    return texto.strip(), list(dict.fromkeys(l for l in links if l)), ia


def perguntar_json(pergunta, web=True, max_tokens=1500):
    texto, links, ia = perguntar(pergunta, web, max_tokens)
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
