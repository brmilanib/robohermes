# -*- coding: utf-8 -*-
"""
🧪 Decants (01/10, pedido do Bruno: "um menu só dos decants: puxar todo o estoque de perfumes e montar uma planilha com os
decants de 15, 10 e 5 ml, custo por ml, + R$ 5 do frasco, R$ 1 do adesivo e R$ 1 da caixa (padrão, mas editável), markup
2,3 e o preço de venda; foto e botão para o Bazar gerar a arte").

Conta (sempre em código):
  custo por ml   = custo médio do UpSeller ÷ ml do frasco (lido no título, ou digitado na tela)
  custo do decant = tamanho × custo por ml + frasco + adesivo + caixa
  preço de venda  = custo do decant × markup (o do produto, senão o padrão)

Guardado em `ia_resumos`: `decants|config` (tamanhos e custos padrão) e `decants|itens` ({sku: foto, volume, markup,
oculto}). A arte e o post saem pelo Bazar (aba 🧪 Decants).
"""
import json
import re
from datetime import datetime, timezone

import nubi

CONFIG = "decants|config"
ITENS = "decants|itens"
PADRAO = {"tamanhos": [15, 10, 5], "frasco": 5.0, "adesivo": 1.0, "caixa": 1.0, "markup": 2.3}
VOLUME_MIN = 20                     # frasco com menos de 20 ml já é decant/miniatura: não se fraciona
TIPOS = ("Perfume",)


class ErroDecant(Exception):
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


def _num(v, nome, minimo=0.0, maximo=None):
    if v in (None, ""):
        return None
    try:
        v = float(str(v).replace(",", ".")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        raise ErroDecant(f"{nome}: número inválido")
    if v < minimo or (maximo is not None and v > maximo):
        raise ErroDecant(f"{nome}: fora do permitido ({minimo:g} a {maximo:g})" if maximo else f"{nome}: tem que ser {minimo:g} ou mais")
    return v


def config(repo):
    c = dict(PADRAO)
    c.update({k: v for k, v in (_ler(repo, CONFIG, {}) or {}).items() if k in PADRAO})
    return c


def salvar_config(repo, d):
    c = config(repo)
    for k in ("frasco", "adesivo", "caixa"):
        if k in d:
            c[k] = _num(d[k], k, 0, 500) or 0.0
    if "markup" in d:
        c["markup"] = _num(d["markup"], "markup", 1, 20) or PADRAO["markup"]
    if "tamanhos" in d:
        ts = sorted({int(_num(t, "tamanho", 1, 100)) for t in d["tamanhos"] if t not in (None, "")}, reverse=True)
        if not ts or len(ts) > 6:
            raise ErroDecant("informe de 1 a 6 tamanhos de decant")
        c["tamanhos"] = ts
    _gravar(repo, CONFIG, c)
    return c


def itens_extra(repo):
    x = _ler(repo, ITENS, {})
    return x if isinstance(x, dict) else {}


def salvar_item(repo, d):
    sku = str(d.get("sku") or "").strip()
    if not sku:
        raise ErroDecant("SKU obrigatório")
    xs = itens_extra(repo)
    it = xs.get(sku, {})
    if "volume_ml" in d:
        it["volume_ml"] = _num(d["volume_ml"], "ml do frasco", 1, 1000)
    if "markup" in d:
        it["markup"] = _num(d["markup"], "markup", 1, 20)
    if "oculto" in d:
        it["oculto"] = bool(d["oculto"])
    if "tamanhos_bazar" in d:                         # 01/10: quais tamanhos vão para o Bazar (árabe barato só 15 ml…)
        ts = sorted({int(_num(t, "tamanho", 1, 100)) for t in d["tamanhos_bazar"] or []}, reverse=True)
        it["tamanhos_bazar"] = ts or None
    if "foto" in d:
        f = str(d.get("foto") or "")
        if f and (not re.fullmatch(r"bazar/[A-Za-z0-9_./-]{3,250}", f) or ".." in f):
            raise ErroDecant("foto inválida")
        it["foto"] = f
    xs[sku] = {k: v for k, v in it.items() if v not in (None, "", False)}
    _gravar(repo, ITENS, xs)
    return xs[sku]


def volume_do_titulo(titulo):
    """Maior "N ml" do título (o frasco), se for de VOLUME_MIN ml para cima; senão None."""
    vs = [int(m.group(1)) for m in nubi.RE_VOLUME.finditer(nubi.normalizar(titulo or ""))]
    vs = [v for v in vs if v >= VOLUME_MIN]
    return max(vs) if vs else None


def precos(custo_ml, cfg, markup):
    fixos = round((cfg["frasco"] or 0) + (cfg["adesivo"] or 0) + (cfg["caixa"] or 0), 2)
    out = []
    for t in cfg["tamanhos"]:
        custo = round(t * custo_ml + fixos, 2)
        preco = round(custo * markup, 2)
        out.append({"ml": t, "custo": custo, "preco": preco, "lucro": round(preco - custo, 2)})
    return out


def planilha(itens_cat, cfg, extras):
    """itens_cat: `categorias.estoque_por_categoria(...)["itens"]` (sku, titulo, marca, tipo, disponivel, custo)."""
    linhas, sem_volume, sem_custo = [], [], []
    for it in itens_cat:
        if it.get("tipo") not in TIPOS:
            continue
        sku = it.get("sku") or ""
        ex = extras.get(sku, {})
        kit = re.search(r"\bkit\b", nubi.normalizar(it.get("titulo") or ""))   # custo do kit não é de 1 frasco
        vol = ex.get("volume_ml") or (None if kit else volume_do_titulo(it.get("titulo")))
        base = {"sku": sku, "titulo": it.get("titulo") or "", "marca": it.get("marca") or "", "disponivel": it.get("disponivel") or 0,
                "custo": it.get("custo"), "volume_ml": vol, "volume_manual": bool(ex.get("volume_ml")), "foto": ex.get("foto") or "",
                "oculto": bool(ex.get("oculto")), "markup": ex.get("markup"), "tamanhos_bazar": ex.get("tamanhos_bazar"), "categoria": it.get("categoria")}
        if not it.get("custo"):
            sem_custo.append(base)
            continue
        if not vol:
            sem_volume.append(base)
            continue
        mk = ex.get("markup") or cfg["markup"]
        cml = round(float(it["custo"]) / float(vol), 4)
        base.update({"custo_ml": cml, "markup_usado": mk, "decants": precos(cml, cfg, mk),
                     "ml_disponivel": round((it.get("disponivel") or 0) * vol, 0)})
        linhas.append(base)
    linhas.sort(key=lambda x: (x["oculto"], -(x["disponivel"] > 0), x["marca"] or "~", x["titulo"]))
    return {"itens": linhas, "sem_volume": sem_volume, "sem_custo": sem_custo, "config": cfg}
