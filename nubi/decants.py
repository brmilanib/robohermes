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
# 01/10 (2º pedido): frasco (split) R$ 5, embalagem ("caixa") R$ 1, adesivo R$ 0,50 — padrão para todos e editável por perfume
PADRAO = {"tamanhos": [15, 10, 5], "frasco": 5.0, "adesivo": 0.5, "caixa": 1.0, "markup": 2.3}
INSUMOS = ("frasco", "caixa", "adesivo")
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


MAX_MIDIAS = 3


def _caminho(c):
    c = str(c or "")
    if c and (not re.fullmatch(r"bazar/[A-Za-z0-9_./-]{3,250}", c) or ".." in c):
        raise ErroDecant("arquivo inválido")
    return c


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
    for k in INSUMOS:                                  # custo próprio deste perfume (vazio = o padrão)
        if k in d:
            it[k] = _num(d[k], k, 0, 500)
    if "oculto" in d:
        it["oculto"] = bool(d["oculto"])
    if "tamanhos_bazar" in d:                         # 01/10: quais tamanhos vão para o Bazar (árabe barato só 15 ml…)
        ts = sorted({int(_num(t, "tamanho", 1, 100)) for t in d["tamanhos_bazar"] or []}, reverse=True)
        it["tamanhos_bazar"] = ts or None
    if "foto" in d:
        it["foto"] = _caminho(d.get("foto"))
    # 01/10 (Bruno: "espaço para subir três fotos e vídeos de cada decant")
    for k in ("fotos", "videos"):
        if k in d:
            cs = [_caminho(c) for c in (d.get(k) or []) if c][:MAX_MIDIAS]
            it[k] = cs or None
            if k == "fotos":
                it["foto"] = cs[0] if cs else ""
    if "legenda" in d:
        it["legenda"] = str(d.get("legenda") or "").strip()[:2000]
    xs[sku] = {k: v for k, v in it.items() if v is not None and v != "" and v is not False}   # 0 (sem adesivo) vale
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
                "preco_venda": it.get("preco_venda"),     # preço médio do frasco nas vendas (para "sinta antes de investir")
                "custo": it.get("custo"), "volume_ml": vol, "volume_manual": bool(ex.get("volume_ml")), "foto": ex.get("foto") or "",
                "oculto": bool(ex.get("oculto")), "markup": ex.get("markup"), "tamanhos_bazar": ex.get("tamanhos_bazar"),
                "fotos": ex.get("fotos") or ([ex["foto"]] if ex.get("foto") else []), "videos": ex.get("videos") or [],
                "legenda": ex.get("legenda") or "", "categoria": it.get("categoria")}
        if not it.get("custo"):
            sem_custo.append(base)
            continue
        if not vol:
            sem_volume.append(base)
            continue
        mk = ex.get("markup") or cfg["markup"]
        cml = round(float(it["custo"]) / float(vol), 4)
        cfg_it = dict(cfg, **{k: ex[k] for k in INSUMOS if ex.get(k) is not None})
        base.update({k: ex.get(k) for k in INSUMOS})
        base["insumos"] = {k: cfg_it[k] for k in INSUMOS}
        base["insumos_total"] = round(sum(cfg_it[k] or 0 for k in INSUMOS), 2)
        base.update({"custo_ml": cml, "markup_usado": mk, "decants": precos(cml, cfg_it, mk),
                     "ml_disponivel": round((it.get("disponivel") or 0) * vol, 0)})
        linhas.append(base)
    linhas.sort(key=lambda x: (x["oculto"], -(x["disponivel"] > 0), x["marca"] or "~", x["titulo"]))
    return {"itens": linhas, "sem_volume": sem_volume, "sem_custo": sem_custo, "config": cfg}


# ---------- notas (Fragrantica pela busca do Google no Gemini) e legenda ----------
PEDIDO_NOTAS = """Procure o perfume "{nome}" no site Fragrantica (fragrantica.com ou fragrantica.com.br) usando a busca. Use SÓ o
que a página do Fragrantica (ou, se não houver, outra fonte confiável de perfumaria) diz. Responda SÓ JSON numa linha:
{{"perfume": "nome e marca", "familia": "família olfativa", "notas_topo": "notas separadas por vírgula", "notas_coracao": "...",
"notas_fundo": "...", "inspirado_em": "perfume famoso que ele lembra, só se a fonte disser", "ocasiao": "dia/noite, estações",
"curiosidades": "1 frase", "link": "endereço da página do Fragrantica"}}. Não invente notas: campo sem dado fica "".""".strip()

PEDIDO_LEGENDA = """Escreva a legenda de um post de WhatsApp/Instagram da PURE PERFUMARIA vendendo o DECANT (perfume original
fracionado em frasquinho) do perfume abaixo. Objetivo: convencer a pessoa a comprar o decant ANTES de comprar o frasco inteiro
(experimentar na pele, sentir a fixação, levar na bolsa, conhecer sem gastar muito). Use as notas olfativas para descrever o
cheiro de um jeito sensorial e fácil de entender. Tom: animado, elegante, brasileiro, com alguns emojis (sem exagero).
Até 7 linhas curtas. NÃO escreva preço, valor, desconto, ml, quantidade nem nenhum número: os tamanhos e preços são colocados
depois pelo sistema. Não prometa o que não está nas notas.

PERFUME: {nome}
FAMÍLIA: {familia}
NOTAS DE TOPO: {topo}
NOTAS DE CORAÇÃO: {coracao}
NOTAS DE FUNDO: {fundo}
LEMBRA: {inspirado}
OCASIÃO: {ocasiao}"""


def notas_do_texto(texto):
    m = re.search(r"\{.*\}", str(texto or ""), re.S)
    if not m:
        return {}
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return {}
    campos = ("perfume", "familia", "notas_topo", "notas_coracao", "notas_fundo", "inspirado_em", "ocasiao", "curiosidades", "link")
    out = {k: re.sub(r"\s+", " ", str(d.get(k) or "")).strip()[:600] for k in campos}
    if out["link"] and not re.match(r"https://(www\.)?fragrantica\.com(\.br)?/", out["link"]):
        out["link"] = ""
    return out if any(out[k] for k in ("notas_topo", "notas_coracao", "notas_fundo")) else {}


def legenda_limpa(texto):
    """Tira números (preço/ml) que a IA tenha escrito: preço é sempre do sistema."""
    linhas = []
    for l in str(texto or "").strip().splitlines():
        l = re.sub(r"(R\$\s*)?\d+([.,]\d+)?\s*(ml|reais|%)?", "", l, flags=re.I).strip()
        l = re.sub(r"\s{2,}", " ", l)
        if l or (linhas and linhas[-1]):
            linhas.append(l)
    return "\n".join(linhas).strip()[:1500]
