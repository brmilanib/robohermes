# -*- coding: utf-8 -*-
"""
Monitor de preços do Mercado Livre (30/09, pedido do Bruno: "quando eu clicar em monitorar preço, atualizar todo dia de
madrugada o preço que ele está vendendo; um menu de monitoramento com todos os anúncios que eu marcar, nome da loja, link e
o histórico de preço").

- Lista dos anúncios seguidos em `ia_resumos` `precos|monitor|lista` (até MAX_ANUNCIOS); histórico por anúncio em
  `precos|hist|<MLB>` (1 ponto por dia de Brasília; o mesmo dia é substituído), só leitura pública do ML.
- Quem lê o preço é o coletor (comando `ml-precos`, rotina `precos`, de madrugada): abre a página do anúncio no Chrome do
  coletor (produto.mercadolivre.com.br/MLB-<n>), como um humano, e manda preço, preço original, status e estoque para
  `ml_precos_gravar`. Sem API paga, sem software de concorrente.
"""
import json
import re
from datetime import datetime, timedelta, timezone

LISTA = "precos|monitor|lista"
HIST = "precos|hist|"
MAX_ANUNCIOS = 300
MAX_PONTOS = 400
BRASILIA = timezone(timedelta(hours=-3))


class ErroPrecos(Exception):
    pass


def _ler(repo, chave, padrao):
    r = (repo._req("GET", "ia_resumos", {"select": "texto", "chave": f"eq.{chave}"}) or [None])[0]
    try:
        return json.loads(r["texto"]) if r and r.get("texto") else padrao
    except (TypeError, ValueError):
        return padrao


def _gravar(repo, chave, valor):
    repo._req("POST", "ia_resumos", corpo=[{"chave": chave, "ia": "nubi", "criado_em": datetime.now(timezone.utc).isoformat(),
                                            "texto": json.dumps(valor, ensure_ascii=False)}],
              prefer="resolution=merge-duplicates,return=minimal")


def normalizar_mlb(txt):
    """'MLB-4577439527', 'mlb4577439527' ou o link -> 'MLB4577439527'; None se não for anúncio."""
    m = re.search(r"MLB-?(\d{6,14})", str(txt or ""), re.I)
    return f"MLB{m.group(1)}" if m else None


def link_de(mlb):
    return f"https://produto.mercadolivre.com.br/MLB-{mlb[3:]}"


def _num(v):
    try:
        v = float(v)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def lista(repo):
    xs = _ler(repo, LISTA, [])
    return xs if isinstance(xs, list) else []


def seguir(repo, item):
    """Põe um anúncio no monitor (ou atualiza o que já está). Devolve o item gravado."""
    mlb = normalizar_mlb(item.get("mlb") or item.get("link"))
    if not mlb:
        raise ErroPrecos("anúncio inválido: precisa do número MLB ou do link do Mercado Livre")
    xs = lista(repo)
    ja = next((x for x in xs if x.get("mlb") == mlb), None)
    if not ja and len(xs) >= MAX_ANUNCIOS:
        raise ErroPrecos(f"limite de {MAX_ANUNCIOS} anúncios monitorados (pare de seguir algum antes)")
    novo = {"mlb": mlb, "link": str(item.get("link") or link_de(mlb))[:500], "titulo": str(item.get("titulo") or "")[:200],
            "foto": str(item.get("foto") or "")[:500], "loja": str(item.get("loja") or "")[:120],
            "seller_id": re.sub(r"\D", "", str(item.get("seller_id") or ""))[:20],
            "vendedor": str(item.get("vendedor") or "")[:120],
            "preco_inicial": _num(item.get("preco")), "desde": datetime.now(timezone.utc).isoformat()}
    if ja:
        for k, v in novo.items():
            if k in ("desde", "preco_inicial"):
                continue
            if v:
                ja[k] = v
        novo = ja
    else:
        xs.append(novo)
    _gravar(repo, LISTA, xs)
    return novo


def parar(repo, mlb):
    """Tira do monitor (o histórico fica guardado). Devolve True se estava na lista."""
    mlb = normalizar_mlb(mlb)
    xs = lista(repo)
    resto = [x for x in xs if x.get("mlb") != mlb]
    if len(resto) != len(xs):
        _gravar(repo, LISTA, resto)
        return True
    return False


def historico(repo, mlb):
    mlb = normalizar_mlb(mlb)
    h = _ler(repo, HIST + mlb, []) if mlb else []
    return h if isinstance(h, list) else []


def gravar_leitura(repo, itens, dia=None):
    """Leituras do coletor: [{mlb, preco, preco_original, status, estoque, titulo, vendedor}] -> 1 ponto por dia no
    histórico de cada anúncio (o mesmo dia é substituído). Devolve quantos anúncios foram gravados."""
    dia = dia or datetime.now(BRASILIA).date().isoformat()
    agora = datetime.now(timezone.utc).isoformat()
    n = 0
    xs = lista(repo)
    por = {x.get("mlb"): x for x in xs}
    for it in itens or []:
        mlb = normalizar_mlb(it.get("mlb"))
        if not mlb:
            continue
        ponto = {"dia": dia, "em": agora, "preco": _num(it.get("preco")), "preco_original": _num(it.get("preco_original")),
                 "status": str(it.get("status") or "")[:40], "estoque": it.get("estoque") if isinstance(it.get("estoque"), int) else None}
        h = [p for p in historico(repo, mlb) if p.get("dia") != dia]
        h.append(ponto)
        h.sort(key=lambda p: p.get("dia") or "")
        _gravar(repo, HIST + mlb, h[-MAX_PONTOS:])
        if mlb in por:
            x = por[mlb]
            x["ultimo"] = {k: ponto[k] for k in ("dia", "preco", "preco_original", "status", "estoque")}
            for k in ("titulo", "vendedor"):
                if it.get(k) and not x.get(k):
                    x[k] = str(it[k])[:200]
        n += 1
    if n:
        _gravar(repo, LISTA, xs)
    return n


def painel(repo, dias=60):
    """A lista com o resumo do histórico de cada anúncio, para a tela."""
    out = []
    desde = (datetime.now(BRASILIA).date() - timedelta(days=dias)).isoformat()
    for x in lista(repo):
        h = [p for p in historico(repo, x.get("mlb")) if (p.get("dia") or "") >= desde]
        precos = [p["preco"] for p in h if p.get("preco")]
        ult = h[-1] if h else None
        ant = next((p for p in reversed(h[:-1]) if p.get("preco")), None) if ult else None
        var = None
        if ult and ult.get("preco") and ant and ant.get("preco"):
            var = ult["preco"] / ant["preco"] - 1
        out.append(dict(x, historico=h[-45:], atual=(ult or {}).get("preco"), anterior=(ant or {}).get("preco"), var=var,
                        minimo=min(precos) if precos else None, maximo=max(precos) if precos else None,
                        status=(ult or {}).get("status") or "", estoque=(ult or {}).get("estoque"),
                        ultimo_dia=(ult or {}).get("dia"), pontos=len(h)))
    out.sort(key=lambda x: (x.get("loja") or "", x.get("titulo") or ""))
    return out


def pendente(repo, rotina, agora=None):
    """Para o vigia do Mac: está na hora da rotina `precos`, há anúncios e nenhum foi lido hoje? Devolve os itens."""
    agora = agora or datetime.now(BRASILIA)
    xs = lista(repo)
    hoje = agora.date().isoformat()
    faltam = [{"mlb": x["mlb"], "link": x.get("link") or link_de(x["mlb"])} for x in xs
              if (x.get("ultimo") or {}).get("dia") != hoje]
    na_hora = bool(rotina and rotina.get("ativo", True) and agora.strftime("%H:%M") >= (rotina.get("horario") or "04:00"))
    return {"rodar": na_hora and bool(faltam), "itens": faltam, "total": len(xs), "horario": (rotina or {}).get("horario")}


STATUS_PAGINA = (("pausad", "pausado"), ("finalizad", "finalizado"), ("esgotad", "esgotado"), ("nao esta disponivel", "indisponível"),
                 ("não está disponível", "indisponível"))


def ler_pagina(x):
    """Normaliza o que o JS da página do anúncio devolveu: preço em reais (fraction+cents), preço original, status pelo texto
    da página ("Publicação pausada", "finalizado", "esgotado"), estoque ("(96 disponíveis)", "Último disponível")."""
    x = x or {}
    fr, ct = x.get("fracao"), x.get("centavos")
    preco = None
    if fr not in (None, ""):
        try:
            preco = float(re.sub(r"\D", "", str(fr)) or 0) + float(re.sub(r"\D", "", str(ct or "0")) or 0) / 100
        except ValueError:
            preco = None
    orig = None
    if x.get("original"):
        m = re.search(r"(\d[\d.]*),?(\d{2})?", str(x["original"]).replace("R$", ""))
        if m:
            orig = float(m.group(1).replace(".", "")) + (float(m.group(2)) / 100 if m.group(2) else 0)
    texto = str(x.get("texto") or "").lower()
    status = "ativo"
    for pista, nome in STATUS_PAGINA:
        if pista in texto:
            status = nome
            break
    if preco is None and status == "ativo":
        status = "sem preço"
    estoque = None
    m = re.search(r"\(?\s*(\d{1,6})\s+dispon[ií]ve", texto) or re.search(r"(\d{1,6})\s+unidades?\s+dispon", texto)
    if m:
        estoque = int(m.group(1))
    elif "ultimo disponivel" in texto or "último disponível" in texto:
        estoque = 1
    return {"preco": preco if preco and preco > 0 else None, "preco_original": orig if orig and orig > (preco or 0) else None,
            "status": status, "estoque": estoque, "titulo": str(x.get("titulo") or "")[:200], "vendedor": str(x.get("vendedor") or "")[:120]}
