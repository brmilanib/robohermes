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
            "gtin": re.sub(r"\D", "", str(item.get("gtin") or ""))[:14],   # 01/10: achado pelo GTIN (anúncio de catálogo)
            # 01/10 (Bruno: "se é catálogo, a tag de catálogo; se é full, a tag do Full"); None = não sabemos
            "catalogo": item.get("catalogo") if isinstance(item.get("catalogo"), bool) else None,
            "full": item.get("full") if isinstance(item.get("full"), bool) else None,
            "preco_inicial": _num(item.get("preco")), "desde": datetime.now(timezone.utc).isoformat()}
    if ja:
        for k, v in novo.items():
            if k in ("desde", "preco_inicial"):
                continue
            if v or (k in ("catalogo", "full") and v is not None):
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
                 "status": str(it.get("status") or "")[:40], "estoque": it.get("estoque") if isinstance(it.get("estoque"), int) else None,
                 "fonte": str(it.get("fonte") or "navegador")[:20]}
        if "mais_vendido" in it:                       # 01/10: tags e posição de cada leitura da página (histórico p/ o agente)
            ponto["mais_vendido"] = bool(it.get("mais_vendido"))
            ponto["posicao_mv"] = posicao_mais_vendido(it.get("mais_vendido"))[0]
        for k in ("full", "catalogo"):
            if isinstance(it.get(k), bool):
                ponto[k] = it[k]
        bp = it.get("busca_pos") if isinstance(it.get("busca_pos"), dict) else None
        if bp:                                         # posição na busca do ML (None = fora das páginas lidas)
            ponto["pos_busca"] = bp.get("posicao")
        # 01/10: leitura de hora em hora pela API: no mesmo dia, ponto igual ao último só atualiza a hora; se algo mudou
        # (preço, riscado, situação, estoque), entra um ponto novo com a hora (a mudança fica com a hora certa)
        h = historico(repo, mlb)
        antes = next((p for p in reversed(h) if p.get("preco")), None)
        mesmo_dia = [p for p in h if p.get("dia") == dia]
        chave = lambda p: (p.get("preco"), p.get("preco_original"), p.get("status"), p.get("estoque"),
                           p.get("mais_vendido"), p.get("posicao_mv"), p.get("full"), p.get("pos_busca"))
        if mesmo_dia and chave(mesmo_dia[-1]) == chave(ponto):
            mesmo_dia[-1]["em"] = agora
        else:
            h.append(ponto)
        h.sort(key=lambda p: (p.get("dia") or "", p.get("em") or ""))
        _gravar(repo, HIST + mlb, h[-MAX_PONTOS:])
        if mlb in por:
            x = por[mlb]
            _eventos(x, it, ponto, agora)                # antes de trocar o "ultimo": compara com a leitura anterior
            x["ultimo"] = {k: ponto[k] for k in ("dia", "preco", "preco_original", "status", "estoque")}
            # 01/10 (Bruno: "data e hora da última atualização, quantas atualizações já tivemos"): conta cada leitura
            x["leituras"] = int(x.get("leituras") or 0) + 1
            x["ultima_leitura"] = agora
            if ponto["fonte"] != "api":
                x["ultima_pagina"] = agora            # a página dá o que a API não dá: MAIS VENDIDO, +50, FULL, título
            # 01/10 (Bruno: "quando mudar o preço, que fique piscando no menu para eu clicar e ver"): aviso até ele ver
            if antes and ponto["preco"] and abs(ponto["preco"] - antes["preco"]) >= 0.01:
                x["alerta"] = {"de": antes["preco"], "para": ponto["preco"], "pct": round(ponto["preco"] / antes["preco"] - 1, 4),
                               "em": agora, "visto": False}
            for k in ("catalogo", "full", "estoque_mais"):
                if isinstance(it.get(k), bool):
                    x[k] = it[k]
            if "estoque" in it and not it.get("estoque_mais") and it.get("fonte") != "api":
                x.pop("estoque_mais", None)
            if bp:
                _evento_busca(x, bp, agora)
                x["busca_pos"] = dict({k: bp.get(k) for k in ("termo", "posicao", "pagina", "patrocinado", "lidos", "vencedor")}, em=agora)
            if re.fullmatch(r"MLB\d{6,14}", str(it.get("produto_catalogo") or "")):
                x["produto_catalogo"] = it["produto_catalogo"]
            for k in ("mais_vendido", "categoria", "tipo_id"):
                if it.get(k) is not None and (it[k] or k == "mais_vendido"):
                    x[k] = it[k]
            for k in ("titulo", "vendedor"):
                # 01/10: o cartão de foto mandava o tipo do anúncio ("Clássico") como título; a leitura corrige
                if it.get(k) and (not x.get(k) or (k == "titulo" and titulo_ruim(x.get(k)))):
                    x[k] = str(it[k])[:200]
        n += 1
    if n:
        _gravar(repo, LISTA, xs)
    return n


# 01/10 (Bruno: "a posição na busca, com as principais palavras do título do perfume; esse monitoramento é o rastreamento"):
# o termo nasce do título (sem palavras genéricas, volume e gênero) e o Bruno pode trocar na tela.
PALAVRAS_FORA = set("""perfume perfumes original originais importado importada lacrado lacrada novo nova masculino masculina
feminino feminina unissex homem mulher para de da do das dos e com sem o a os as em edt edp eau toilette parfum parfume
colonia colônia extrait ml 100ml 200ml 50ml 30ml 80ml 90ml 60ml 75ml 125ml 150ml spray vaporizador frete gratis grátis kit
masc fem promoção promocao oferta""".split())


def termo_busca(titulo, n=5):
    t = re.sub(r"[^\wÀ-ÿ ]+", " ", str(titulo or "").lower())
    ws = [w for w in t.split() if w not in PALAVRAS_FORA and not re.fullmatch(r"\d+(ml|g)?", w) and len(w) > 1]
    return " ".join(ws[:n])


# 01/10 (Bruno: "monitora a tag de MAIS VENDIDO: quando aparece e quando some; o Full, quando entrou e saiu; quando zerar o
# estoque; e a posição — para o agente entender como o ML dá essas tags"). Cada mudança vira um evento no anúncio (fica no
# histórico; `visto: False` = alerta piscando até o Bruno marcar "vi"). Só a leitura da PÁGINA sabe MAIS VENDIDO/FULL/catálogo.
MAX_EVENTOS = 200


def posicao_mais_vendido(txt):
    """"MAIS VENDIDO · 2º em Perfumes Jacques Bogart" -> (2, "Perfumes Jacques Bogart")."""
    m = re.search(r"(\d{1,3})\s*[º°o]?\s+em\s+(.+)$", str(txt or ""))
    return (int(m.group(1)), m.group(2).strip()) if m else (None, "")


def _evento_busca(x, bp, agora):
    """Posição na busca: entrar/sair das páginas lidas ou trocar de página = alerta; mudar de posição na mesma página fica
    só no histórico (visto)."""
    antes = x.get("busca_pos") or {}
    if not antes or antes.get("termo") != bp.get("termo"):
        return
    pa, pn = antes.get("posicao"), bp.get("posicao")
    if pa == pn:
        return
    termo = bp.get("termo")
    evs = x.setdefault("eventos", [])
    if pa and not pn:
        evs.append({"tipo": "busca_saiu", "texto": f"🔎 Sumiu das {bp.get('paginas') or 3} primeiras páginas da busca '{termo}' (estava {pa}º)", "em": agora, "visto": False})
    elif pn and not pa:
        evs.append({"tipo": "busca_entrou", "texto": f"🔎 Apareceu na busca '{termo}': {pn}º (pág. {bp.get('pagina')})", "em": agora, "visto": False})
    else:
        pg_a, pg_n = antes.get("pagina"), bp.get("pagina")
        mudou_pag = pg_a != pg_n
        evs.append({"tipo": "busca_posicao", "texto": f"🔎 Busca '{termo}': {pa}º → {pn}º" + (f" (pág. {pg_a} → {pg_n})" if mudou_pag else ""),
                    "em": agora, "visto": not mudou_pag, "de": pa, "para": pn})


def vincular(repo, mlb, sku, nenhum=False):
    """01/10: o Bruno liga o anúncio monitorado a um SKU do estoque dele (custo, disponível); `nenhum` = não tenho esse
    produto (para de sugerir pelo título); sem sku e sem `nenhum` = volta ao automático."""
    mlb = normalizar_mlb(mlb)
    xs = lista(repo)
    x = next((x for x in xs if x.get("mlb") == mlb), None)
    if not x:
        raise ErroPrecos("anúncio fora do monitor")
    sku = str(sku or "").strip()[:60]
    x.pop("sku_meu", None)
    x.pop("sem_vinculo", None)
    if sku:
        x["sku_meu"] = sku
    elif nenhum:
        x["sem_vinculo"] = True
    _gravar(repo, LISTA, xs)
    return x


def salvar_busca(repo, mlb, termo):
    mlb = normalizar_mlb(mlb)
    termo = re.sub(r"\s+", " ", str(termo or "")).strip()[:80]
    xs = lista(repo)
    x = next((x for x in xs if x.get("mlb") == mlb), None)
    if not x:
        raise ErroPrecos("anúncio fora do monitor")
    if termo:
        x["busca"] = termo
    else:
        x.pop("busca", None)
    _gravar(repo, LISTA, xs)
    return x.get("busca") or termo_busca(x.get("titulo"))


def pn_ok(it):
    return "mais_vendido" in it


def _eventos(x, it, ponto, agora):
    evs = x.setdefault("eventos", [])

    def ev(tipo, texto, **extra):
        evs.append(dict({"tipo": tipo, "texto": texto, "em": agora, "visto": False}, **extra))

    pagina = ponto["fonte"] != "api"
    if pagina and "mais_vendido" in it:
        antes, agora_mv = x.get("mais_vendido") or "", it.get("mais_vendido") or ""
        pa, ca = posicao_mais_vendido(antes)
        pn, cn = posicao_mais_vendido(agora_mv)
        if agora_mv and not antes and x.get("ultima_pagina_antes"):
            ev("mais_vendido_on", f"🟠 Ganhou a tag MAIS VENDIDO{f' ({pn}º em {cn})' if pn else ''}", posicao=pn)
        elif agora_mv and not x.get("ultima_pagina_antes"):              # 1ª leitura da página: só marca o ponto de partida
            evs.append({"tipo": "mais_vendido_on", "texto": f"🟠 Já estava com MAIS VENDIDO na 1ª leitura{f' ({pn}º em {cn})' if pn else ''}",
                        "em": agora, "visto": True, "posicao": pn})
        elif antes and not agora_mv:
            ev("mais_vendido_off", "⚪ Perdeu a tag MAIS VENDIDO" + (f" (estava {pa}º em {ca})" if pa else ""), posicao=pa)
        elif pa and pn and pa != pn:
            ev("posicao", f"{'⬆️' if pn < pa else '⬇️'} MAIS VENDIDO: {pa}º → {pn}º em {cn or ca}", de=pa, para=pn)
    if pagina and pn_ok(it):
        x["posicao_mv"] = posicao_mais_vendido(it.get("mais_vendido"))[0]
    if pagina and isinstance(it.get("full"), bool) and isinstance(x.get("full"), bool) and it["full"] != x["full"]:
        ev("full_on" if it["full"] else "full_off", "⚡ Entrou no FULL" if it["full"] else "📦 Saiu do FULL")
    if pagina and isinstance(it.get("catalogo"), bool) and isinstance(x.get("catalogo"), bool) and it["catalogo"] != x["catalogo"]:
        ev("catalogo_on" if it["catalogo"] else "catalogo_off", "🏷️ Entrou no catálogo" if it["catalogo"] else "🏷️ Saiu do catálogo")
    ult = x.get("ultimo") or {}
    sem = lambda e, st: e == 0 or st in ("esgotado", "pausado", "finalizado", "indisponível")
    if ult and (ult.get("estoque") is not None or ult.get("status")):
        if sem(ponto["estoque"], ponto["status"]) and not sem(ult.get("estoque"), ult.get("status")):
            ev("estoque_zerou", f"🚫 Ficou sem estoque ({ponto['status'] or 'zerado'})")
        elif not sem(ponto["estoque"], ponto["status"]) and sem(ult.get("estoque"), ult.get("status")) and ponto["preco"]:
            ev("estoque_voltou", "✅ Voltou a ter estoque" + (f" ({ponto['estoque']} disponíveis)" if ponto["estoque"] else ""))
    if pagina:
        x["ultima_pagina_antes"] = True
    del evs[:-MAX_EVENTOS]


TITULOS_RUINS = {"classico", "clássico", "premium", "gratis", "grátis", "gratuito", "full", "catalogo", "catálogo"}


def titulo_ruim(t):
    """Título que não é título: tipo de anúncio ("Clássico", "Premium") ou curto demais."""
    t = str(t or "").strip()
    return not t or t.lower() in TITULOS_RUINS or len(t) < 12


CAMPOS_MUDANCA = (("preco", "Preço"), ("preco_original", "Preço riscado"), ("status", "Situação"), ("estoque", "Estoque"),
                  ("mais_vendido", "Tag MAIS VENDIDO"), ("posicao_mv", "Posição no MAIS VENDIDO"), ("full", "FULL"), ("catalogo", "Catálogo"),
                  ("pos_busca", "Posição na busca"))


def mudancas(h):
    """01/10 (Bruno: "que dia mudou o preço, quanto mudou"): entre leituras seguidas, o que mudou -> lista do mais novo
    para o mais antigo: {dia, dia_antes, campo, nome, de, para, diff, pct}. Leitura sem o campo (None) não conta como mudança."""
    out = []
    pts = sorted([p for p in h or [] if p.get("dia")], key=lambda p: (p["dia"], p.get("em") or ""))
    ult = {}
    for p in pts:
        for c, nome in CAMPOS_MUDANCA:
            v = p.get(c)
            if v in (None, ""):
                continue
            if c in ult and ult[c][1] != v:
                de, dia_antes = ult[c][1], ult[c][0]
                x = {"dia": p["dia"], "em": p.get("em"), "dia_antes": dia_antes, "campo": c, "nome": nome, "de": de, "para": v}
                if isinstance(de, (int, float)) and isinstance(v, (int, float)):
                    x["diff"] = round(v - de, 2)
                    x["pct"] = round(v / de - 1, 4) if de else None
                out.append(x)
            ult[c] = (p["dia"], v)
    return list(reversed(out))


def detalhe(repo, mlb):
    """Um anúncio do monitor com o histórico inteiro, as mudanças e o resumo (para a tela de histórico)."""
    mlb = normalizar_mlb(mlb)
    item = next((x for x in lista(repo) if x.get("mlb") == mlb), None) or {"mlb": mlb, "link": link_de(mlb), "fora_do_monitor": True}
    h = sorted(historico(repo, mlb), key=lambda p: (p.get("dia") or "", p.get("em") or ""))
    precos = [p["preco"] for p in h if p.get("preco")]
    ini = item.get("preco_inicial") or (precos[0] if precos else None)
    atual = precos[-1] if precos else None
    return {"item": item, "historico": h, "mudancas": mudancas(h), "atual": atual, "inicial": ini,
            "var_inicio": round(atual / ini - 1, 4) if atual and ini else None,
            "minimo": min(precos) if precos else None, "maximo": max(precos) if precos else None,
            "medio": round(sum(precos) / len(precos), 2) if precos else None, "dias": len(h),
            "primeiro_dia": h[0]["dia"] if h else None, "ultimo_dia": h[-1]["dia"] if h else None}


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
        com_p = [p for p in h if p.get("preco")]
        menor = min(com_p, key=lambda p: p["preco"]) if com_p else None
        maior = max(com_p, key=lambda p: p["preco"]) if com_p else None
        out.append(dict(x, busca_auto="" if titulo_ruim(x.get("titulo")) or str(x.get("titulo") or "").startswith("Anúncio ") else termo_busca(x.get("titulo")), historico=h[-240:], atual=(ult or {}).get("preco"), anterior=(ant or {}).get("preco"), var=var,
                        ultima_em=x.get("ultima_leitura") or (ult or {}).get("em"), leituras=int(x.get("leituras") or 0) or len(h),
                        menor_em=(menor or {}).get("em") or (menor or {}).get("dia"), maior_em=(maior or {}).get("em") or (maior or {}).get("dia"),
                        titulo_ok=not titulo_ruim(x.get("titulo")),
                        mudancas_preco=sum(1 for m in mudancas(h) if m["campo"] == "preco"),
                        minimo=min(precos) if precos else None, maximo=max(precos) if precos else None,
                        status=(ult or {}).get("status") or "", estoque=(ult or {}).get("estoque"),
                        ultimo_dia=(ult or {}).get("dia"), pontos=len(h)))
    out.sort(key=lambda x: (x.get("loja") or "", x.get("titulo") or ""))
    return out


# 01/10 (Bruno: "atualizar os preços dos monitorados 1 vez ao meio-dia e 1 vez às 19 h"): duas rodadas por dia. A API
# oficial lê todos (servidor, no cron da hora); o que a API não devolver o coletor do Mac lê pela página na mesma rodada.
HORARIOS = ("12:00", "19:00")
RODADA = "precos|rodada"


def rodada_atual(agora=None):
    """Início (Brasília) da última rodada que já passou: hoje 12:00/19:00, senão ontem 19:00."""
    agora = (agora or datetime.now(BRASILIA)).astimezone(BRASILIA)
    for h in reversed(HORARIOS):
        ini = agora.replace(hour=int(h[:2]), minute=int(h[3:]), second=0, microsecond=0)
        if agora >= ini:
            return ini
    h = HORARIOS[-1]
    return (agora - timedelta(days=1)).replace(hour=int(h[:2]), minute=int(h[3:]), second=0, microsecond=0)


def _lido_desde(x, ini):
    try:
        return bool(x.get("ultima_leitura")) and datetime.fromisoformat(x["ultima_leitura"]) >= ini
    except ValueError:
        return False


def api_devida(repo, agora=None):
    """O cron da hora pergunta: a rodada atual (12h/19h) já foi feita pela API? Devolve o início da rodada se falta."""
    ini = rodada_atual(agora)
    r = (repo._req("GET", "ia_resumos", {"select": "texto", "chave": f"eq.{RODADA}"}) or [None])[0]
    return None if r and r.get("texto") == ini.isoformat() else ini


def marcar_rodada(repo, ini):
    repo._req("POST", "ia_resumos", corpo=[{"chave": RODADA, "ia": "nubi", "criado_em": datetime.now(timezone.utc).isoformat(),
                                            "texto": ini.isoformat()}], prefer="resolution=merge-duplicates,return=minimal")


def pendente(repo, rotina, agora=None):
    """Para o vigia do Mac: na rodada atual (12h/19h), os anúncios que ainda não foram lidos (a API não trouxe)."""
    agora = agora or datetime.now(BRASILIA)
    ini = rodada_atual(agora)
    xs = lista(repo)
    # 01/10 (Bruno: "o título certinho do produto que está no ML"): a API não dá o título de anúncio de outra loja; o
    # coletor abre a página e lê o <h1> — também dos já lidos que ainda estão sem título de verdade
    # 01/10 (print do Bruno): em cada rodada o coletor abre a página de todos (tags MAIS VENDIDO, "+50 disponíveis", FULL)
    faltam = [{"mlb": x["mlb"], "link": x.get("link") or link_de(x["mlb"]), "produto": x.get("produto_catalogo") or "",
               "busca": x.get("busca") or ("" if titulo_ruim(x.get("titulo")) else termo_busca(x.get("titulo")))} for x in xs
              if not _lido_desde(dict(x, ultima_leitura=x.get("ultima_pagina")), ini)]
    # 02/10 (Bruno: "toda vez que adicionar no monitorar, o robô vai lá buscar os dados na mesma hora"): o anúncio recém
    # posto no monitor (`ler_ja`) e ainda sem leitura de página entra já, fora do horário da rodada
    def urgente(x):
        if not x.get("ler_ja"):
            return False
        try:
            return not _lido_desde(dict(x, ultima_leitura=x.get("ultima_pagina")), datetime.fromisoformat(x["ler_ja"]))
        except ValueError:
            return False
    novos = [x["mlb"] for x in xs if urgente(x)]
    ja_tem = {f["mlb"] for f in faltam}
    for x in xs:
        if x["mlb"] in novos and x["mlb"] not in ja_tem:
            faltam.append({"mlb": x["mlb"], "link": x.get("link") or link_de(x["mlb"]), "produto": x.get("produto_catalogo") or "",
                           "busca": x.get("busca") or ("" if titulo_ruim(x.get("titulo")) else termo_busca(x.get("titulo")))})
    # dá 20 min para a API (cron da hora) ler primeiro; o coletor pega só o que sobrar
    na_hora = bool(rotina is None or rotina.get("ativo", True)) and agora >= ini + timedelta(minutes=20)
    if novos and not na_hora:                          # fora da rodada: só os novos (não relê os outros)
        faltam = [f for f in faltam if f["mlb"] in novos]
    return {"rodar": (na_hora or bool(novos)) and bool(faltam), "itens": faltam, "novos": novos, "total": len(xs), "horario": " e ".join(HORARIOS),
            "rodada": ini.isoformat()}


def pedir_leitura(repo, mlb, agora=None):
    """Marca o anúncio para o coletor ler a página já (ver `pendente`)."""
    alvo, xs = normalizar_mlb(mlb), lista(repo)
    for x in xs:
        if x.get("mlb") == alvo:
            x["ler_ja"] = (agora or datetime.now(timezone.utc)).isoformat()
            _gravar(repo, LISTA, xs)
            return True
    return False


def alertas(repo):
    """Anúncios com mudança que o Bruno ainda não viu: preço (de/para/pct) e/ou tags (`eventos` não vistos)."""
    out = []
    for x in lista(repo):
        al = x.get("alerta") if (x.get("alerta") or {}).get("visto") is False else None
        evs = [e for e in x.get("eventos") or [] if e.get("visto") is False]
        if not al and not evs:
            continue
        out.append({"mlb": x["mlb"], "titulo": x.get("titulo") or x["mlb"], "loja": x.get("loja") or "", "foto": x.get("foto") or "",
                    **({k: al[k] for k in ("de", "para", "pct", "em")} if al else {"em": evs[-1]["em"]}),
                    "eventos": [{k: e.get(k) for k in ("tipo", "texto", "em")} for e in evs]})
    return out


def marcar_visto(repo, mlb=None):
    xs, n = lista(repo), 0
    alvo = normalizar_mlb(mlb) if mlb else None
    for x in xs:
        if alvo is not None and x.get("mlb") != alvo:
            continue
        if (x.get("alerta") or {}).get("visto") is False:
            x["alerta"]["visto"] = True
            n += 1
        for e in x.get("eventos") or []:
            if e.get("visto") is False:
                e["visto"] = True
                n += 1
    if n:
        _gravar(repo, LISTA, xs)
    return n


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
    extra = {k: x[k] for k in ("catalogo", "full") if isinstance(x.get(k), bool)}
    if re.search(r"\+\s*\d{1,6}\s+dispon", texto):       # "(+50 disponíveis)": o ML mostra "mais de"
        extra["estoque_mais"] = True
    if x.get("mais_vendido") is not None:
        extra["mais_vendido"] = re.sub(r"\s+", " ", str(x.get("mais_vendido") or "")).strip()[:120]
    bp = x.get("busca_pos")
    if isinstance(bp, dict) and bp.get("termo"):
        pos = bp.get("posicao")
        extra["busca_pos"] = {"termo": str(bp["termo"])[:80], "posicao": int(pos) if isinstance(pos, int) and 0 < pos < 1000 else None,
                              "pagina": int(bp["pagina"]) if isinstance(bp.get("pagina"), int) else None,
                              "patrocinado": bool(bp.get("patrocinado")), "vencedor": bp.get("vencedor") if isinstance(bp.get("vencedor"), bool) else None,
                              "lidos": int(bp.get("lidos") or 0), "paginas": int(bp.get("paginas") or 3)}
    if re.fullmatch(r"MLB\d{6,14}", str(x.get("produto_catalogo") or "")):
        extra["produto_catalogo"] = x["produto_catalogo"]
    for k, rx in (("categoria", r"MLB\d{2,8}"), ("tipo_id", r"gold_pro|gold_special|gold|free|silver|bronze")):
        if re.fullmatch(rx, str(x.get(k) or "")):
            extra[k] = x[k]
    return {"preco": preco if preco and preco > 0 else None, "preco_original": orig if orig and orig > (preco or 0) else None,
            "status": status, "estoque": estoque, "titulo": str(x.get("titulo") or "")[:200], "vendedor": str(x.get("vendedor") or "")[:120],
            **extra}


def ler_pela_api(repo, itens_fn):
    """01/10 (Bruno: "melhor monitorar por API, sem abrir navegador"): preço, preço riscado, situação e estoque de todos os
    monitorados pela API oficial do ML (itens_fn = meli.itens), sem navegador. O que a API não devolver fica para o coletor.
    -> (lidos, faltaram)."""
    xs = lista(repo)
    if not xs:
        return 0, 0
    r = itens_fn([x["mlb"] for x in xs]) or {}
    ok = []
    for x in xs:
        it = r.get(x["mlb"]) or {}
        if it.get("bloqueado") or it.get("sumiu") or it.get("preco") is None:
            continue
        st = {"active": "ativo", "paused": "pausado", "closed": "finalizado"}.get(str(it.get("status") or ""), str(it.get("status") or ""))
        ok.append({"mlb": x["mlb"], "preco": it.get("preco"), "preco_original": it.get("preco_cheio"), "status": st,
                   "estoque": it.get("disponivel") if isinstance(it.get("disponivel"), int) else None, "titulo": it.get("titulo"), "fonte": "api",
                   **{k: it[k] for k in ("catalogo", "full") if isinstance(it.get(k), bool)},
                   **{k: v for k, v in (("categoria", it.get("categoria")), ("tipo_id", it.get("tipo_id"))) if v}})
    if ok:
        gravar_leitura(repo, ok)
    return len(ok), len(xs) - len(ok)


# ---------- calculadora (01/10, Bruno: "puxa o custo do meu estoque e coloca lucro líquido, margem e ROI vendendo no mesmo
# preço que ele"): mesma conta da calculadora da extensão (painel.js `contas`) ----------
CALC = "precos|calc"


def calc_config(repo):
    c = _ler(repo, CALC, {}) or {}
    return {"imposto_pct": float(c.get("imposto_pct") or 0)}


def salvar_calc(repo, d):
    try:
        v = float(str(d.get("imposto_pct") or 0).replace(",", "."))
    except ValueError:
        raise ErroPrecos("imposto inválido")
    if not 0 <= v <= 40:
        raise ErroPrecos("imposto entre 0 e 40%")
    _gravar(repo, CALC, {"imposto_pct": v})
    return {"imposto_pct": v}


def contas(preco, custo, tarifa_total, frete, imposto_pct):
    """Vendendo a `preco`: recebido = preço − tarifa do ML − frete; lucro = recebido − imposto − custo."""
    if not preco:
        return None
    imposto = round(preco * (imposto_pct or 0) / 100, 2)
    recebido = round(preco - (tarifa_total or 0) - (frete or 0), 2)
    lucro = round(recebido - imposto - (custo or 0), 2) if custo else None
    return {"preco": preco, "tarifa": tarifa_total, "frete": frete or 0, "imposto": imposto, "recebido": recebido, "custo": custo,
            "lucro": lucro, "margem": round(lucro / preco, 4) if lucro is not None else None,
            "roi": round(lucro / custo, 4) if lucro is not None and custo else None}
