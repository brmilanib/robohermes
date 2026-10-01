# -*- coding: utf-8 -*-
"""
👀 Vendedores observados (01/10, pedido do Bruno): todo vendedor que aparece nos exports do Explorador de anúncios do
Nubimetrics (nome fictício + hash) e que NÃO está no grupo de seguidos (limite de 20 no Nubimetrics). O nubi já guarda os
anúncios deles em `anuncios` (por marca/período); aqui eles ganham cadastro, lista e página própria:

- lista (`nubi_observados()`): 1 linha por hash no último export de cada marca — nomes vistos, marcas, anúncios, unidades,
  faturamento, GTINs, FULL/catálogo, loja oficial, primeira/última vez visto; mais a loja real (meli|hash_lojas) e ⭐.
- página (`nubi_observado_produtos`, `nubi_observado_periodos`): os produtos (agrupados pelo nubi, com GTIN, share em cada
  produto, preço, média/dia desde a criação) e a evolução por período/marca.
- ⭐ interessante (`observados|interesse`, ia_resumos): a fila do revezamento no Nubimetrics (parar de seguir X, seguir Y,
  baixar o histórico, voltar) e da busca da loja real no ML (foto na busca → vitrine → catálogo confirma).
O hash é a chave (o Nubimetrics troca o nome fictício entre exports; os nomes vistos ficam guardados). "MERCADO LIVRE" é a
loja do próprio ML e é tratado como vendedor normal.
"""
import json
import re
from datetime import datetime, timezone

INTERESSE = "observados|interesse"
RE_HASH = re.compile(r"^[0-9a-f]{16,64}$")


def _ler(repo, chave, padrao):
    r = (repo._req("GET", "ia_resumos", {"select": "texto", "chave": f"eq.{chave}"}) or [None])[0]
    try:
        return json.loads(r["texto"]) if r and r.get("texto") else padrao
    except (TypeError, ValueError):
        return padrao


def interesses(repo):
    x = _ler(repo, INTERESSE, {})
    return x if isinstance(x, dict) else {}


def marcar_interesse(repo, vid, ligado, nota=""):
    vid = str(vid or "")
    if not RE_HASH.match(vid):
        raise ValueError("vendedor inválido")
    atual = interesses(repo)
    if ligado:
        atual[vid] = {"em": datetime.now(timezone.utc).isoformat(), "nota": str(nota or "")[:200]}
    else:
        atual.pop(vid, None)
    repo._req("POST", "ia_resumos", corpo=[{"chave": INTERESSE, "ia": "bruno", "criado_em": datetime.now(timezone.utc).isoformat(),
                                            "texto": json.dumps(atual, ensure_ascii=False)}],
              prefer="resolution=merge-duplicates,return=minimal")
    return atual


def lista(repo, seguidos_hashes=None, lojas=None):
    """Todos os vendedores do Explorador (último export de cada marca), com situação seguido/observado, loja e ⭐."""
    linhas = repo._req("POST", "rpc/nubi_observados", corpo={}) or []
    seg = set(seguidos_hashes or [])
    lojas = lojas or {}
    inter = interesses(repo)
    out = []
    for l in linhas:
        vid = str(l.get("vendedor_id") or "")
        nomes = [n for n in (l.get("nomes") or []) if n]
        lj = lojas.get(vid)
        out.append({"vendedor_id": vid, "nome": nomes[0] if nomes else vid[:12], "nomes": nomes,
                    "situacao": "seguido" if vid in seg else "plataforma" if any(n.upper() == "MERCADO LIVRE" for n in nomes) else "observado",
                    "marcas": int(l.get("marcas") or 0), "anuncios": int(l.get("anuncios") or 0), "un": int(l.get("un") or 0),
                    "fat": float(l.get("fat") or 0), "gtins": int(l.get("gtins") or 0),
                    "pct_full": float(l.get("pct_full") or 0), "pct_catalogo": float(l.get("pct_catalogo") or 0),
                    "loja_oficial": bool(l.get("loja_oficial")), "primeiro": l.get("primeiro"), "ultimo": l.get("ultimo"),
                    "loja": {k: lj.get(k) for k in ("id", "nome", "link", "confianca", "cidade", "uf")} if lj else None,
                    "interesse": inter.get(vid)})
    total = {"vendedores": len(out), "observados": sum(1 for x in out if x["situacao"] == "observado"),
             "seguidos": sum(1 for x in out if x["situacao"] == "seguido"), "com_loja": sum(1 for x in out if x["loja"]),
             "interessantes": sum(1 for x in out if x["interesse"]), "un": sum(x["un"] for x in out)}
    return {"itens": out, "total": total}


def detalhe(repo, vid, seguidos_hashes=None, lojas=None):
    vid = str(vid or "")
    if not RE_HASH.match(vid):
        raise ValueError("vendedor inválido")
    prods = repo._req("POST", "rpc/nubi_observado_produtos", corpo={"h": vid}) or []
    pers = repo._req("POST", "rpc/nubi_observado_periodos", corpo={"h": vid}) or []
    produtos = []
    for p in prods:
        dp, uh = int(p.get("dias_pub") or 0), int(p.get("un_hist") or 0)
        produtos.append({"produto": p.get("produto"), "marca": p.get("marca"), "categoria": p.get("categoria") or "", "gtin": p.get("gtin") or "",
                         "titulo": p.get("titulo") or "", "anuncios": int(p.get("anuncios") or 0), "un": int(p.get("un") or 0),
                         "fat": float(p.get("fat") or 0), "preco": float(p["preco"]) if p.get("preco") is not None else None,
                         "pct_full": float(p.get("pct_full") or 0), "catalogo": bool(p.get("catalogo")),
                         "share": float(p.get("share") or 0), "un_hist": uh, "dias_pub": dp,
                         "media_dia_hist": round(uh / dp, 3) if dp > 0 else None})
    periodos = [{"marca": x.get("marca"), "inicio": x.get("inicio"), "fim": x.get("fim"), "dias": int(x.get("dias") or 0),
                 "anuncios": int(x.get("anuncios") or 0), "un": int(x.get("un") or 0), "fat": float(x.get("fat") or 0)} for x in pers]
    nomes = sorted({n for n in (repo._req("GET", "anuncios", {"select": "vendedor", "vendedor_id": f"eq.{vid}", "limit": 200}) or [])
                    for n in [n.get("vendedor")] if n})
    marcas = {}
    for p in produtos:
        m = marcas.setdefault(p["marca"] or "-", {"marca": p["marca"] or "-", "produtos": 0, "un": 0, "fat": 0.0})
        m["produtos"] += 1; m["un"] += p["un"]; m["fat"] += p["fat"]
    lj = (lojas or {}).get(vid)
    tot = {"produtos": len(produtos), "anuncios": sum(p["anuncios"] for p in produtos), "un": sum(p["un"] for p in produtos),
           "fat": sum(p["fat"] for p in produtos), "gtins": sum(1 for p in produtos if p["gtin"]),
           "media_dia_hist": round(sum(p["media_dia_hist"] or 0 for p in produtos), 2)}
    return {"vendedor_id": vid, "nome": nomes[0] if nomes else vid[:12], "nomes": nomes,
            "situacao": "seguido" if vid in set(seguidos_hashes or []) else "observado",
            "total": tot, "produtos": produtos, "marcas": sorted(marcas.values(), key=lambda m: -m["un"]),
            "periodos": periodos, "loja": lj, "interesse": interesses(repo).get(vid)}
