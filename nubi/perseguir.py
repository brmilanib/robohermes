# -*- coding: utf-8 -*-
"""
Perseguir anúncios (28/09, pedido do Bruno): ele cadastra os anúncios do Mercado Livre (MLB…) e a palavra de busca; toda
semana (rotina 'perseguir') e quando ele pede ("🔎 Consultar agora"), o Apify confere a posição orgânica na busca e o nubi
guarda o histórico. Robô do Apify: maximedupre/mercado-libre-product-rank-checker (US$ 0,0025 por página de busca).

Chave: APIFY_TOKEN nas variáveis da Vercel (colocada pelo Bruno; nunca no código, no banco ou no chat).
A execução é assíncrona: `iniciar` dispara e guarda o id; `conferir` (na tela e no cron) busca o resultado quando acabou.
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ATOR = "maximedupre~mercado-libre-product-rank-checker"
API = "https://api.apify.com/v2"
LISTA = "perseguir|lista"
HIST = "perseguir|historico"
EXEC = "perseguir|execucao"
MAX_ANUNCIOS = 40
PAGINAS = int(os.environ.get("NUBI_PERSEGUIR_PAGINAS", "5"))      # até 5 páginas por anúncio (~240 resultados)
PRECO_PAGINA = 0.0025
A_CADA_DIAS = 7


class ErroPerseguir(Exception):
    pass


def tem_chave():
    return bool(os.environ.get("APIFY_TOKEN"))


def _http(metodo, caminho, corpo=None, timeout=60):
    if not tem_chave():
        raise ErroPerseguir("falta a chave do Apify (APIFY_TOKEN) nas variáveis da Vercel")
    url = f"{API}{caminho}{'&' if '?' in caminho else '?'}token={urllib.parse.quote(os.environ['APIFY_TOKEN'])}"
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        raise ErroPerseguir(f"Apify respondeu {e.code}: {e.read().decode(errors='replace')[:200]}")


def _ler(repo, chave, padrao):
    r = (repo._req("GET", "ia_resumos", {"select": "texto", "chave": f"eq.{chave}"}) or [None])[0]
    try:
        return json.loads(r["texto"]) if r and r.get("texto") else padrao
    except (TypeError, ValueError):
        return padrao


def _gravar(repo, chave, valor):
    repo._req("POST", "ia_resumos", corpo=[{"chave": chave, "ia": "apify", "criado_em": datetime.now(timezone.utc).isoformat(),
                                            "texto": json.dumps(valor, ensure_ascii=False)}],
              prefer="resolution=merge-duplicates,return=minimal")


def normalizar_anuncio(txt):
    """'MLB-4577439527', 'mlb4577439527' ou o link do anúncio -> 'MLB4577439527'."""
    m = re.search(r"\b(MLB)-?(\d{6,})", str(txt or "").upper())
    if not m:
        raise ErroPerseguir("informe o código do anúncio (ex.: MLB4577439527) ou o link dele")
    return m.group(1) + m.group(2)


def salvar(repo, d):
    """{acao: 'adicionar', anuncio, termo, cep?, apelido?} ou {acao: 'remover', id}."""
    lista = _ler(repo, LISTA, [])
    if d.get("acao") == "remover":
        lista = [x for x in lista if x["id"] != str(d.get("id"))]
    else:
        anuncio = normalizar_anuncio(d.get("anuncio"))
        termo = re.sub(r"\s+", " ", str(d.get("termo") or "")).strip()[:120]
        if len(termo) < 2:
            raise ErroPerseguir("informe a palavra de busca (como o cliente procura)")
        cep = re.sub(r"[^\d-]", "", str(d.get("cep") or ""))[:9] or None
        chave = f"{anuncio}|{termo.lower()}"
        if any(x["id"] == chave for x in lista):
            raise ErroPerseguir("esse anúncio já está sendo perseguido com essa palavra")
        if len(lista) >= MAX_ANUNCIOS:
            raise ErroPerseguir(f"limite de {MAX_ANUNCIOS} anúncios perseguidos (remova um antes)")
        lista.append({"id": chave, "anuncio": anuncio, "termo": termo, "cep": cep,
                      "apelido": str(d.get("apelido") or "")[:80] or None, "criado_em": datetime.now(timezone.utc).isoformat()})
    _gravar(repo, LISTA, lista)
    return {"ok": True, "lista": lista}


def iniciar(repo, ids=None, motivo="semanal"):
    """Dispara o Apify para os anúncios (todos ou só `ids`). Uma execução por vez."""
    ex = _ler(repo, EXEC, {})
    if ex.get("status") == "rodando":
        raise ErroPerseguir("já tem uma conferência rodando no Apify; o resultado chega em alguns minutos")
    lista = [x for x in _ler(repo, LISTA, []) if not ids or x["id"] in ids]
    if not lista:
        raise ErroPerseguir("nenhum anúncio para perseguir")
    checks = [{"keyword": x["termo"], "productId": x["anuncio"], "country": "br", **({"postalCode": x["cep"]} if x.get("cep") else {})}
              for x in lista]
    r = (_http("POST", f"/acts/{ATOR}/runs", {"rankChecks": checks, "pagesToCheck": PAGINAS}) or {}).get("data") or {}
    ex = {"status": "rodando", "run_id": r.get("id"), "dataset_id": r.get("defaultDatasetId"), "ids": [x["id"] for x in lista],
          "motivo": motivo, "em": datetime.now(timezone.utc).isoformat(), "custo_max": round(len(lista) * PAGINAS * PRECO_PAGINA, 4)}
    _gravar(repo, EXEC, ex)
    return ex


def conferir(repo):
    """Se a execução do Apify acabou, guarda as posições no histórico. Devolve o estado da execução."""
    ex = _ler(repo, EXEC, {})
    if ex.get("status") != "rodando" or not tem_chave():
        return ex
    run = (_http("GET", f"/actor-runs/{ex['run_id']}") or {}).get("data") or {}
    st = run.get("status")
    if st in ("READY", "RUNNING"):
        return ex
    if st != "SUCCEEDED":
        ex.update(status="erro", erro=f"o Apify terminou com {st}", fim=datetime.now(timezone.utc).isoformat())
        _gravar(repo, EXEC, ex)
        return ex
    itens = _http("GET", f"/datasets/{ex['dataset_id']}/items?clean=true&format=json") or []
    hist = _ler(repo, HIST, {})
    agora = datetime.now(timezone.utc).isoformat()
    for it in itens:
        chave = f"{normalizar_anuncio(it.get('productId'))}|{str(it.get('keyword') or '').strip().lower()}"
        pos = it.get("organicPosition")
        hist.setdefault(chave, []).append({
            "em": agora, "posicao": int(pos) if isinstance(pos, (int, float)) and pos else None,
            "pagina": it.get("page") or it.get("organicPage"), "paginas": it.get("pagesChecked"),
            "cep": it.get("appliedPostalCode"), "achou": bool(pos)})
        hist[chave] = hist[chave][-60:]
    _gravar(repo, HIST, hist)
    ex.update(status="ok", fim=agora, resultados=len(itens), custo_usd=run.get("usageTotalUsd"))
    _gravar(repo, EXEC, ex)
    return ex


def semanal(repo):
    """Rotina 'perseguir': confere o que ficou pendente e, se a última foi há 7 dias ou mais, dispara todos."""
    try:
        ex = conferir(repo)
    except ErroPerseguir as e:
        return f"erro: {e}"
    if ex.get("status") == "rodando":
        return "conferência ainda rodando no Apify"
    ult = _ler(repo, "perseguir|ultima_semanal", {}).get("em")
    if ult and datetime.now(timezone.utc) - datetime.fromisoformat(ult) < timedelta(days=A_CADA_DIAS - 1):
        return "já conferido nesta semana"
    try:
        novo = iniciar(repo, motivo="semanal")
    except ErroPerseguir as e:
        return f"não disparou: {e}"
    _gravar(repo, "perseguir|ultima_semanal", {"em": novo["em"]})
    return f"conferência semanal disparada ({len(novo['ids'])} anúncios, até US$ {novo['custo_max']:.2f})"


def painel(repo):
    try:
        ex = conferir(repo)
        erro = None
    except ErroPerseguir as e:
        ex, erro = _ler(repo, EXEC, {}), str(e)
    hist = _ler(repo, HIST, {})
    lista = _ler(repo, LISTA, [])
    for x in lista:
        h = hist.get(x["id"]) or []
        x["historico"] = h[-12:]
        x["atual"] = h[-1] if h else None
        ant = next((p for p in reversed(h[:-1]) if p.get("posicao")), None)
        x["variacao"] = (ant["posicao"] - h[-1]["posicao"]) if h and h[-1].get("posicao") and ant else None   # >0 = subiu
    return {"lista": lista, "execucao": ex, "chave": tem_chave(), "erro": erro, "paginas": PAGINAS,
            "preco_pagina": PRECO_PAGINA, "max": MAX_ANUNCIOS}
