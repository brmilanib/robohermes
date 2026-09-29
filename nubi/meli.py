# -*- coding: utf-8 -*-
"""
API oficial do Mercado Livre (29/09, pedido do Bruno — o mesmo que o HunterHub mostra, sem scraping):
- anúncio: foto, título, preço com o cheio riscado, tipo, Full/Flex/frete grátis, idade, vendidos (faixa do ML),
  visitas em 30 dias, a loja VERDADEIRA (o Nubimetrics embaralha) com reputação, medalha e cidade;
- loja: perfil, os anúncios dela (busca por seller_id), insights e o produto destaque;
- catálogo pelo GTIN (/products/search -> /products/{id}/items): quem vende o mesmo produto agora e a que preço —
  é assim que o vendedor embaralhado do Nubimetrics (hash) vira a loja real (casa por preço, Full e dias publicados).

Chaves: ML_CLIENT_ID e ML_CLIENT_SECRET nas variáveis da Vercel (o Bruno coloca; nunca no código, no banco, no log ou no
chat). O token do app (client_credentials, ~6 h) fica só na memória do servidor. Tudo aqui é leitura.
Nota e insights são regras (sem IA): o ML dá os números, o nubi interpreta.
"""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

API = os.environ.get("NUBI_ML_API", "https://api.mercadolibre.com")
SITE = "MLB"
FALTA_CHAVE = ("Faltam as chaves do Mercado Livre (ML_CLIENT_ID e ML_CLIENT_SECRET nas variáveis da Vercel): crie o app em "
               "developers.mercadolivre.com.br/devcenter e cole as duas lá.")
HASH_LOJAS = "meli|hash_lojas"          # vendedor embaralhado do Nubimetrics (hash) -> loja real
LOJA_CACHE = "meli|loja|"               # página da loja pronta (6 h)
LOJA_VALIDADE = 6 * 3600
MAX_PRODUTOS_LOJA = 200
TIPOS = {"gold_special": "Clássico", "gold_pro": "Premium", "gold_premium": "Premium", "gold": "Ouro", "silver": "Prata",
         "bronze": "Bronze", "free": "Grátis"}
MEDALHAS = {"platinum": "Platinum", "gold": "Gold", "silver": "Silver"}
ITEM_CAMPOS = ("id,title,price,original_price,available_quantity,sold_quantity,listing_type_id,condition,permalink,thumbnail,"
               "pictures,seller_id,category_id,catalog_product_id,catalog_listing,shipping,seller_address,date_created,"
               "start_time,status,attributes")


class ErroMeli(Exception):
    pass


class NaoAchou(ErroMeli):
    pass


class ErroLogin(ErroMeli):
    """Sem as chaves ou o ML recusou o login do app: aparece sempre (nunca vira 'bloqueado' em silêncio)."""
    pass


class Bloqueado(ErroMeli):
    """O ML recusou este recurso para o token do app (403): não é erro do nubi."""
    pass


# ---------------------------------------------------------------------------
# Conexão: token do app só na memória; nada de token em mensagem de erro
# ---------------------------------------------------------------------------
_TOKEN = {"valor": None, "ate": 0.0}
_CACHE = {}                               # memória do servidor: {chave: (quando, dado)}


def tem_chave():
    return bool(os.environ.get("ML_CLIENT_ID") and os.environ.get("ML_CLIENT_SECRET"))


def _abrir(req, timeout):                 # ponto único de rede (os testes trocam por um dublê)
    return urllib.request.urlopen(req, timeout=timeout)


def _token(forcar=False):
    if not tem_chave():
        raise ErroLogin(FALTA_CHAVE)
    if not forcar and _TOKEN["valor"] and time.time() < _TOKEN["ate"]:
        return _TOKEN["valor"]
    corpo = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": os.environ["ML_CLIENT_ID"],
                                    "client_secret": os.environ["ML_CLIENT_SECRET"]}).encode()
    req = urllib.request.Request(f"{API}/oauth/token", data=corpo, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        with _abrir(req, 20) as r:
            d = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            motivo = json.loads(e.read() or b"{}").get("error") or ""
        except Exception:  # noqa: BLE001
            motivo = ""
        raise ErroLogin(f"o Mercado Livre recusou o login do app ({e.code}{': ' + str(motivo)[:60] if motivo else ''}); "
                       "confira ML_CLIENT_ID e ML_CLIENT_SECRET na Vercel")
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ErroLogin("sem resposta do Mercado Livre (login do app)")
    if not d.get("access_token"):
        raise ErroLogin("o Mercado Livre não devolveu o token do app")
    _TOKEN.update(valor=d["access_token"], ate=time.time() + max(300, int(d.get("expires_in") or 21600) - 300))
    return _TOKEN["valor"]


def _get(caminho, params=None, timeout=20):
    url = f"{API}{caminho}" + (("&" if "?" in caminho else "?") + urllib.parse.urlencode(params) if params else "")
    forcar = False
    for tentativa in range(3):
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {_token(forcar)}", "Accept": "application/json"})
        try:
            with _abrir(req, timeout) as r:
                return json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            if e.code == 401 and not forcar:
                forcar = True                    # token vencido/revogado: pede outro uma vez
                continue
            if e.code == 404:
                raise NaoAchou(f"o Mercado Livre não achou {caminho.split('?')[0]}")
            if (e.code == 429 or e.code >= 500) and tentativa < 2:
                time.sleep(1.2 * (tentativa + 1))
                continue
            try:                                 # a mensagem do ML ajuda a entender (nunca tem token nem segredo)
                corpo = json.loads(e.read() or b"{}")
                motivo = str(corpo.get("message") or corpo.get("error") or corpo.get("code") or "")[:90]
            except Exception:  # noqa: BLE001
                motivo = ""
            txt = f"o Mercado Livre respondeu {e.code} em {caminho.split('?')[0]}" + (f" ({motivo})" if motivo else "")
            raise (Bloqueado if e.code == 403 else ErroMeli)(txt)
        except (urllib.error.URLError, TimeoutError, OSError):
            if tentativa < 2:
                time.sleep(1.0)
                continue
            raise ErroMeli(f"sem resposta do Mercado Livre em {caminho.split('?')[0]}")
    raise ErroMeli(f"o Mercado Livre não respondeu em {caminho.split('?')[0]}")


def _mem(chave, validade, fazer):
    x = _CACHE.get(chave)
    if x and time.time() - x[0] < validade:
        return x[1]
    v = fazer()
    _CACHE[chave] = (time.time(), v)
    if len(_CACHE) > 3000:                   # memória do servidor não cresce sem limite
        for k in sorted(_CACHE, key=lambda k: _CACHE[k][0])[:1000]:
            _CACHE.pop(k, None)
    return v


def _em_paralelo(f, itens, n=6):
    itens = list(itens)
    if len(itens) <= 1:
        return [f(x) for x in itens]
    with ThreadPoolExecutor(max_workers=min(n, len(itens))) as ex:
        return list(ex.map(f, itens))


# ---------------------------------------------------------------------------
# Links e códigos
# ---------------------------------------------------------------------------
def codigo_do_texto(txt):
    """Link ou código colado -> ("item", "MLB123…") | ("produto", "MLB1234…") (página de catálogo /p/) |
    ("loja", "123456") | ("apelido", "NICKNAME") | None."""
    s = str(txt or "").strip()
    m = re.search(r"(?:wid=|item_id[:=])\s*(MLB)-?(\d{6,})", s, re.I)            # catálogo com o anúncio escolhido
    if m:
        return "item", "MLB" + m.group(2)
    m = re.search(r"/p/(MLB\d{5,})", s, re.I)
    if m:
        return "produto", m.group(1).upper()
    m = re.search(r"\bMLB-?(\d{6,})", s, re.I)
    if m:
        return "item", "MLB" + m.group(1)
    m = re.search(r"_CustId_(\d+)", s) or re.search(r"seller_id=(\d+)", s)
    if m:
        return "loja", m.group(1)
    m = re.search(r"perfil\.mercadolivre\.com\.br/([^/?#\s]+)", s, re.I)
    if m:
        return "apelido", urllib.parse.unquote(m.group(1))
    if re.fullmatch(r"\d{5,12}", s):
        return "loja", s
    return None


def link_do_item(mlb):
    m = re.fullmatch(r"MLB(\d+)", str(mlb or ""))
    return f"https://produto.mercadolivre.com.br/MLB-{m.group(1)}" if m else ""


def _uf(v):
    v = str(v or "")
    return v.split("-", 1)[1] if v.startswith("BR-") else v[:2].upper() if len(v) == 2 else v


def _nivel(level_id):
    m = re.match(r"(\d)", str(level_id or ""))
    return int(m.group(1)) if m else None


def _dias_desde(txt, agora=None):
    try:
        dt = datetime.fromisoformat(str(txt).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    agora = agora or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, (agora - dt).days)


def _num(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Anúncios, lojas, visitas
# ---------------------------------------------------------------------------
def normalizar_item(b, agora=None):
    """Corpo de /items -> o anúncio no formato das telas (contrato da rota meli_anuncios)."""
    fotos = b.get("pictures") or []
    foto = (fotos[0].get("secure_url") or fotos[0].get("url")) if fotos else (b.get("thumbnail") or "")
    sh = b.get("shipping") or {}
    end = b.get("seller_address") or {}
    preco, cheio = _num(b.get("price")), _num(b.get("original_price"))
    gtin = next((str(a.get("value_name") or "").strip() for a in (b.get("attributes") or [])
                 if a.get("id") == "GTIN" and a.get("value_name")), "")
    criado = b.get("start_time") or b.get("date_created")
    return {"anuncio": b.get("id"), "titulo": b.get("title") or "", "preco": preco,
            "preco_cheio": cheio if cheio and preco and cheio > preco else None,
            "link": b.get("permalink") or link_do_item(b.get("id")), "foto": str(foto).replace("http://", "https://"),
            "tipo": TIPOS.get(b.get("listing_type_id"), b.get("listing_type_id") or ""), "tipo_id": b.get("listing_type_id"),
            "full": sh.get("logistic_type") == "fulfillment", "flex": "self_service_in" in (sh.get("tags") or []),
            "frete_gratis": bool(sh.get("free_shipping")), "status": b.get("status") or "",
            "disponivel": b.get("available_quantity"), "vendidos": b.get("sold_quantity"),
            "criado_em": criado, "dias_pub": _dias_desde(criado, agora) if criado else None,
            "cidade": ((end.get("city") or {}).get("name") or ""), "uf": _uf((end.get("state") or {}).get("id") or (end.get("state") or {}).get("name")),
            "categoria": b.get("category_id") or "", "catalogo": bool(b.get("catalog_listing")),
            "produto_catalogo": b.get("catalog_product_id") or "", "vendedor_id": b.get("seller_id"), "gtin": gtin,
            "condicao": b.get("condition") or ""}


def normalizar_loja(u):
    rep = u.get("seller_reputation") or {}
    tr = rep.get("transactions") or {}
    end = u.get("address") or {}
    desde = u.get("registration_date")
    dias = _dias_desde(desde) if desde else None
    return {"id": u.get("id"), "nome": u.get("nickname") or "", "link": u.get("permalink") or "",
            "cidade": end.get("city") or "", "uf": _uf(end.get("state")), "nivel": _nivel(rep.get("level_id")),
            "cor": rep.get("level_id") or "", "medalha": MEDALHAS.get(rep.get("power_seller_status") or "", ""),
            "vendas": tr.get("total"), "concluidas": tr.get("completed"), "desde": desde,
            "anos": round(dias / 365, 1) if dias is not None else None,
            "loja_oficial": bool((u.get("tags") or []) and "brand" in (u.get("tags") or []))}


def _itens_bloqueados():
    x = _CACHE.get("items|bloqueado")
    return bool(x and time.time() - x[0] < 30 * 60)


def itens(ids):
    """{MLB: anúncio}; o que o ML não acha vem {"anuncio": MLB, "sumiu": True}. 20 por chamada, em paralelo."""
    ids = [i for i in dict.fromkeys(str(x).upper() for x in ids if x)]
    out, faltam = {}, []
    for i in ids:
        x = _CACHE.get("item|" + i)
        if x and time.time() - x[0] < 50 * 60:
            out[i] = x[1]
        else:
            faltam.append(i)
    if faltam and _itens_bloqueados():
        # 29/09 (produção): o ML não dá /items de outras lojas para o token do app; não repete 40 pedidos a cada tela
        for i in faltam:
            out[i] = {"anuncio": i, "bloqueado": True, "link": link_do_item(i)}
        faltam = []

    def lote(grupo):
        try:
            r = _get("/items", {"ids": ",".join(grupo), "attributes": ITEM_CAMPOS}) or []
        except NaoAchou:
            return []
        except ErroLogin:
            raise
        except ErroMeli:                      # o ML recusou o pedido de vários: vai um por um abaixo
            return []
        return r if isinstance(r, list) else []

    for resp in _em_paralelo(lote, [faltam[k:k + 20] for k in range(0, len(faltam), 20)]):
        for x in resp:
            b = x.get("body") or {}
            mlb = str(b.get("id") or "").upper()
            if x.get("code") == 200 and mlb:
                out[mlb] = normalizar_item(b)
                _CACHE["item|" + mlb] = (time.time(), out[mlb])
    # 29/09 (produção): o pedido de vários pode não devolver o anúncio para o token do app; tenta um por um (até 40)
    faltando = [i for i in faltam if i not in out]

    def um(i):
        try:
            return i, normalizar_item(_get(f"/items/{i}"))
        except NaoAchou:
            return i, None
        except ErroLogin:
            raise
        except ErroMeli:
            return i, "bloqueado"
    res = _em_paralelo(um, faltando[:40])
    for i, m in res:
        if isinstance(m, dict) and m.get("anuncio"):
            out[i] = m
            _CACHE["item|" + i] = (time.time(), m)
        elif m == "bloqueado":
            out[i] = {"anuncio": i, "bloqueado": True, "link": link_do_item(i)}
    if len(res) >= 3 and len(faltando) == len(faltam) and not any(isinstance(m, dict) for _, m in res):
        _CACHE["items|bloqueado"] = (time.time(), True)      # nenhum veio, nem de vários nem um por um
    for i in ids:
        out.setdefault(i, {"anuncio": i, "sumiu": True})
    return out


def lojas(ids):
    """{seller_id: loja} (cache de 7 dias na memória do servidor)."""
    ids = [str(i) for i in dict.fromkeys(ids) if i]

    def uma(i):
        try:
            return i, _mem("user|" + i, 7 * 86400, lambda: normalizar_loja(_get(f"/users/{i}")))
        except NaoAchou:
            return i, None
    return {i: l for i, l in _em_paralelo(uma, ids) if l}


def visitas(ids, dias=30):
    """{MLB: visitas nos últimos `dias`}. Um pedido para vários anúncios; se o ML recusar, um por anúncio (até 60)."""
    ids = [str(i).upper() for i in dict.fromkeys(ids) if i]
    if not ids:
        return {}
    ate = datetime.now(timezone.utc).date()
    de = ate - timedelta(days=dias)
    out = {}
    try:
        for k in range(0, len(ids), 50):
            r = _get("/items/visits", {"ids": ",".join(ids[k:k + 50]), "date_from": f"{de.isoformat()}T00:00:00.000-00:00",
                                        "date_to": f"{ate.isoformat()}T00:00:00.000-00:00"})
            for x in (r if isinstance(r, list) else [r] if isinstance(r, dict) and r.get("item_id") else []):
                if x.get("item_id") is not None:
                    out[str(x["item_id"]).upper()] = int(x.get("total_visits") or 0)
            if isinstance(r, dict) and not r.get("item_id"):
                out.update({str(k2).upper(): int(v or 0) for k2, v in r.items() if str(k2).upper().startswith("MLB")})
        if out:
            return out
    except ErroLogin:
        raise
    except ErroMeli:
        pass

    def um(i):
        try:
            r = _get(f"/items/{i}/visits/time_window", {"last": dias, "unit": "day"}) or {}
            return i, int(r.get("total_visits") or 0)
        except ErroLogin:
            raise
        except ErroMeli:
            return i, None
    return {i: v for i, v in _em_paralelo(um, ids[:60]) if v is not None}


def anuncios(ids, com_visitas=False):
    """Contrato da rota meli_anuncios: {MLB: anúncio + loja (+ visitas)}."""
    ids = [str(i).upper() for i in ids][:120]
    its = itens(ids)
    lj = lojas([m.get("vendedor_id") for m in its.values() if m.get("vendedor_id")])
    vis = visitas([i for i, m in its.items() if not m.get("sumiu")]) if com_visitas else {}
    for i, m in its.items():
        if m.get("sumiu") or m.get("bloqueado"):
            continue
        m["loja"] = lj.get(str(m.get("vendedor_id"))) or {}
        if com_visitas and i in vis:
            m["visitas"] = {"total": vis[i], "por_dia": round(vis[i] / 30, 1)}
    return its


# ---------------------------------------------------------------------------
# Nota do anúncio e insights da loja (regras, sem IA)
# ---------------------------------------------------------------------------
def _dias_txt(d):
    return "menos de 1 dia" if d < 1 else f"{int(round(d))} dia{'s' if round(d) >= 2 else ''}"


def analisar_anuncio(m):
    """Nota de 0 a 100 e os pontos que explicam a nota (o que o HunterHub chama de 'Anúncio forte')."""
    vend = m.get("vendidos") or 0
    dias = max(1, m.get("dias_pub") or 1)
    por_dia = vend / dias
    vis = (m.get("visitas") or {}).get("total")
    conv = min(1.0, por_dia * 30 / vis) if vis else None
    disp = m.get("disponivel")
    pts, nota = [], 0
    # conversão (até 30)
    if conv is None:
        nota += 12
        pts.append({"tipo": "neutro", "texto": "Sem as visitas deste anúncio, a conversão não foi calculada."})
    else:
        c = conv * 100
        nota += 30 if c >= 3 else 22 if c >= 2 else 15 if c >= 1 else 8 if c >= 0.5 else 3
        ok = c >= 2
        pts.append({"tipo": "ok" if ok else "alerta",
                    "texto": f"O anúncio converte {c:.1f}% das visitas em venda".replace(".", ",")
                             + (", acima do usual no Mercado Livre." if ok else ", abaixo do usual (2% a 3%)."),
                    "dica": "" if ok else "Revise fotos, título e preço: tem gente vendo e não comprando."})
    # visitas (até 20)
    if vis is not None:
        nota += 20 if vis >= 2000 else 15 if vis >= 800 else 10 if vis >= 300 else 5 if vis >= 100 else 2
        forte = vis >= 800
        pts.append({"tipo": "ok" if forte else "neutro",
                    "texto": f"{_mil(vis)} visitas em 30 dias." + (" O anúncio tem audiência pra sustentar volume." if forte else ""),
                    "dica": "" if forte else "Pouca audiência: posição na busca e anúncios patrocinados ajudam."})
    # vendas por dia (até 20)
    nota += 20 if por_dia >= 5 else 15 if por_dia >= 2 else 10 if por_dia >= 0.5 else 5 if por_dia >= 0.1 else 0
    if vend:
        pts.append({"tipo": "ok" if por_dia >= 1 else "neutro",
                    "texto": f"São pelo menos {_fmt_dec(por_dia)} vendas por dia desde que entrou no ar, algo como "
                             f"{int(round(por_dia * 30))} por mês."})
    # estoque (até 10)
    if disp is not None and por_dia > 0:
        cobre = disp / por_dia
        nota += 10 if cobre >= 15 else 6 if cobre >= 5 else 2
        if cobre < 5:
            pts.insert(0, {"tipo": "alerta", "texto": f"São {disp} unidade{'s' if disp != 1 else ''} anunciada{'s' if disp != 1 else ''}, "
                                                         f"o que dá {_dias_txt(cobre)} no ritmo atual.",
                           "dica": "Reponha antes de zerar. Anúncio sem estoque perde posição e leva tempo pra recuperar."})
    elif disp is not None:
        nota += 5
    # logística (até 20)
    if m.get("full"):
        nota += 15 + (5 if m.get("frete_gratis") else 0)
        pts.append({"tipo": "ok", "texto": "O anúncio está no Full" + (" com frete grátis." if m.get("frete_gratis") else ".")})
    elif m.get("frete_gratis"):
        nota += 8
        pts.append({"tipo": "neutro", "texto": "O anúncio usa frete grátis, mas fica fora do filtro de Full.",
                    "dica": "Simule o impacto no preço antes de ativar: as duas alavancas custam margem."})
    else:
        pts.append({"tipo": "alerta", "texto": "Sem Full e sem frete grátis: perde nos filtros da busca."})
    if m.get("status") and m["status"] != "active":
        nota = max(0, nota - 30)
        pts.insert(0, {"tipo": "alerta", "texto": f"O anúncio está {'pausado' if m['status'] == 'paused' else m['status']}."})
    nota = max(0, min(100, int(round(nota))))
    rotulo = "Anúncio forte" if nota >= 70 else "Anúncio mediano" if nota >= 45 else "Anúncio fraco"
    kpis = {"vendas_totais": vend, "vendas_dia": round(por_dia, 1), "visitas_30d": vis,
            "visitas_dia": round(vis / 30) if vis else None, "conversao": round(conv * 100, 2) if conv is not None else None,
            "faturamento": round((m.get("preco") or 0) * vend, 2),
            "faturamento_mes": round((m.get("preco") or 0) * por_dia * 30, 2)}
    return {"nota": nota, "rotulo": rotulo, "pontos": pts, "kpis": kpis}


def _mil(n):
    return f"{n / 1000:.1f}k".replace(".", ",") if n >= 1000 else str(int(n))


def _fmt_dec(x):
    return f"{x:.1f}".replace(".", ",") if x < 10 else str(int(round(x)))


PALAVRAS_FRACAS = set("""de da do das dos e para com sem em o a os as um uma kit perfume perfumes ml eau parfum toilette edp edt
original masculino feminino unissex lacrado novo nova importado""".split())


def analisar_loja(loja, prods):
    """Insights e números da loja a partir dos anúncios dela (regras)."""
    n = len(prods)
    vend = [p.get("vendidos") or 0 for p in prods]
    total_v = sum(vend)
    fat = sum((p.get("preco") or 0) * (p.get("vendidos") or 0) for p in prods)
    vis = sum((p.get("visitas") or {}).get("total") or 0 for p in prods)
    parados = sum(1 for v in vend if not v)
    full = sum(1 for p in prods if p.get("full"))
    cats = {}
    for p in prods:
        cats[p.get("categoria") or "?"] = cats.get(p.get("categoria") or "?", 0) + 1
    cat_top = max(cats.values()) if cats else 0
    termos = {}
    for p in prods:
        for w in re.findall(r"[a-zà-ú0-9]+", (p.get("titulo") or "").lower()):
            if len(w) >= 3 and w not in PALAVRAS_FRACAS and not w.isdigit():
                termos[w] = termos.get(w, 0) + (p.get("vendidos") or 0) + 1
    top_termos = [w for w, _ in sorted(termos.items(), key=lambda kv: -kv[1])[:5]]
    maior = max(prods, key=lambda p: ((p.get("vendidos") or 0) * (p.get("preco") or 0), (p.get("visitas") or {}).get("total") or 0)) if prods else None
    share_top = ((maior.get("vendidos") or 0) * (maior.get("preco") or 0) / fat) if maior and fat else 0
    destaque = max(prods, key=lambda p: ((p.get("visitas") or {}).get("total") or 0, p.get("vendidos") or 0)) if prods else None
    ins = []
    if n:
        ins.append({"titulo": "Faturamento acumulado estimado",
                    "texto": f"Nos {n} anúncios analisados, os produtos dele acumulam cerca de R$ {f'{fat:,.0f}'.replace(',', '.')}"
                             f" em vendas desde que foram publicados ({_mil(total_v)} vendas no total)."})
    tr = loja.get("vendas") or 0
    veterano = tr >= 10000 or (loja.get("anos") or 0) >= 5
    ins.append({"titulo": "Perfil: " + ("Veterano" if veterano else "Em crescimento" if tr >= 500 else "Iniciante"),
                "texto": f"{loja.get('nome') or 'A loja'} tem {_mil(tr)} transações históricas"
                         + (f", reputação {loja['nivel']}/5" if loja.get("nivel") else "")
                         + (f", em {loja['cidade']}-{loja['uf']}" if loja.get("cidade") else "") + "."})
    if n:
        pct_parado = parados / n
        ins.append({"titulo": "Cauda morta no catálogo" if pct_parado >= 0.15 else "Catálogo enxuto",
                    "texto": f"{round(pct_parado * 100)}% dos {n} anúncios analisados não venderam"
                             + (", muita gordura no catálogo." if pct_parado >= 0.15 else ".")})
        pct_full = full / n
        ins.append({"titulo": "Logística: " + ("Full" if pct_full >= 0.5 else "Logística tradicional"),
                    "texto": f"{round(pct_full * 100)}% usam Full." + (" Você pode ganhar dele na entrega adotando Full." if pct_full < 0.3 else ""),
                    "dica": "Adotar Full pode te dar vantagem de entrega sobre ele." if pct_full < 0.3 else ""})
        pct_cat = cat_top / n
        ins.append({"titulo": "Especialista" if pct_cat >= 0.6 else "Generalista",
                    "texto": f"{round(pct_cat * 100)}% do catálogo está na principal categoria"
                             + (". Ele conhece bem esse nicho." if pct_cat >= 0.6 else ", vende de tudo um pouco.")})
        if top_termos:
            ins.append({"titulo": "Termos que ele domina", "texto": "Os anúncios dele aparecem forte em: " + ", ".join(top_termos) + ".",
                        "dica": "Reforce esses termos nos seus títulos pra disputar as mesmas buscas."})
        if maior and fat:
            conc = share_top >= 0.4
            ins.append({"titulo": "Vendas concentradas" if conc else "Vendas diversificadas", "ok": not conc,
                        "texto": f"O produto mais forte responde por {round(share_top * 100)}% do total"
                                 + (": ataque esse produto e ele sente." if conc else "; as vendas estão bem distribuídas.")})
    kpis = {"vendas_totais": total_v, "mercado": round(fat, 2), "visitas_30d": vis, "anuncios": n,
            "destaque": ({k: destaque.get(k) for k in ("anuncio", "titulo", "foto", "link", "preco")}
                         | {"visitas": (destaque.get("visitas") or {}).get("total"),
                            "pct_visitas": round(100 * ((destaque.get("visitas") or {}).get("total") or 0) / vis, 1) if vis else None})
            if destaque else None}
    return {"insights": ins, "kpis": kpis}


# ---------------------------------------------------------------------------
# Páginas: anúncio, loja, catálogo por GTIN
# ---------------------------------------------------------------------------
def _item_do_produto(pid):
    """Página de catálogo (/p/MLB…) -> o anúncio que está ganhando (buy box) ou o primeiro que vende."""
    p = _get(f"/products/{pid}") or {}
    bw = (p.get("buy_box_winner") or {}).get("item_id")
    if bw:
        return bw
    r = (_get(f"/products/{pid}/items", {"limit": 1}) or {}).get("results") or []
    if r:
        return r[0].get("item_id")
    raise NaoAchou("o produto de catálogo não tem anúncio ativo agora")


def tarifa(preco, categoria, tipo_id):
    """Tarifa de venda do ML para o preço/categoria/tipo: {pct, fixa, total}."""
    try:
        r = _get(f"/sites/{SITE}/listing_prices", {"price": round(float(preco), 2), "category_id": categoria,
                                                    "listing_type_id": tipo_id or "gold_special"})
    except ErroLogin:
        raise
    except ErroMeli:
        return None
    x = r[0] if isinstance(r, list) and r else r if isinstance(r, dict) else {}
    det = x.get("sale_fee_details") or {}
    total = _num(x.get("sale_fee_amount"))
    return {"pct": _num(det.get("percentage_fee")), "fixa": _num(det.get("fixed_fee")) or 0.0, "total": total}


def frete_do_vendedor(vendedor_id, mlb):
    """O que o vendedor paga de frete grátis neste anúncio (custo cheio de lista)."""
    try:
        r = _get(f"/users/{vendedor_id}/shipping_options/free", {"item_id": mlb}) or {}
    except ErroLogin:
        raise
    except ErroMeli:
        return None
    return _num((((r.get("coverage") or {}).get("all_country") or {}).get("list_cost")))


def pagina_anuncio(texto):
    """Link/código -> anúncio completo para a tela (cabeçalho, nota, KPIs, calculadora)."""
    alvo = codigo_do_texto(texto)
    if not alvo or alvo[0] not in ("item", "produto"):
        raise ErroMeli("cole o link de um anúncio do Mercado Livre (ou o código MLB…)")
    mlb = alvo[1] if alvo[0] == "item" else _item_do_produto(alvo[1])
    m = anuncios([mlb], com_visitas=True)[str(mlb).upper()]
    if m.get("bloqueado"):
        raise ErroMeli(f"o Mercado Livre não libera os detalhes do anúncio {mlb} para o app")
    if m.get("sumiu"):
        raise NaoAchou(f"o Mercado Livre não achou o anúncio {mlb} (removido?)")
    m["analise"] = analisar_anuncio(m)
    if m.get("preco") and m.get("categoria"):
        m["tarifa"] = tarifa(m["preco"], m["categoria"], m.get("tipo_id"))
    if m.get("frete_gratis") and m.get("vendedor_id"):
        m["frete_custo"] = frete_do_vendedor(m["vendedor_id"], mlb)
    return m


def _com_visitas(prods):
    vis = visitas([m["anuncio"] for m in prods if m.get("anuncio")])
    return [dict(m, visitas={"total": vis[str(m["anuncio"]).upper()], "por_dia": round(vis[str(m["anuncio"]).upper()] / 30, 1)})
            if str(m.get("anuncio") or "").upper() in vis else m for m in prods]


def produtos_da_loja(vendedor_id, limite=MAX_PRODUTOS_LOJA, gtins_fn=None):
    """Os anúncios da loja. 1º pela busca do ML (50 por página); a busca por loja é bloqueada para o token do app (403 em
    produção, 29/09) — aí vêm os anúncios dela no catálogo dos produtos que o Nubimetrics mostra que ela vende (gtins_fn).
    Devolve (produtos, total da loja ou None, fonte)."""
    try:
        primeiro = _get(f"/sites/{SITE}/search", {"seller_id": vendedor_id, "offset": 0, "limit": 50}) or {}
    except ErroLogin:
        raise
    except ErroMeli:
        gtins = list(gtins_fn(vendedor_id) or []) if gtins_fn else []
        if not gtins:
            return [], None, "bloqueada"
        prods = por_gtin(gtins, max_gtins=8, maximo=MAX_OFERTAS, vendedor=vendedor_id)    # todas as páginas do catálogo
        return _com_visitas(prods), None, "catálogo"
    total = int((primeiro.get("paging") or {}).get("total") or 0)
    ids = [r.get("id") for r in primeiro.get("results") or []]
    offs = list(range(50, min(total, limite), 50))
    for r in _em_paralelo(lambda o: _get(f"/sites/{SITE}/search", {"seller_id": vendedor_id, "offset": o, "limit": 50}) or {}, offs, 4):
        ids += [x.get("id") for x in r.get("results") or []]
    ids = [i for i in dict.fromkeys(ids) if i][:limite]
    its = itens(ids)
    prods = [its[str(i).upper()] for i in ids if its.get(str(i).upper()) and not its[str(i).upper()].get("sumiu")
             and not its[str(i).upper()].get("bloqueado")]
    return _com_visitas(prods), total, "busca"


def pagina_loja(repo, texto, forcar=False, gtins_fn=None):
    """Link de anúncio/loja ou seller_id -> perfil, insights, KPIs e produtos (cache de 6 h em ia_resumos).
    gtins_fn(seller_id) -> GTINs que a loja vende segundo o Nubimetrics (para quando a busca por loja é bloqueada)."""
    alvo = codigo_do_texto(texto)
    if not alvo:
        raise ErroMeli("cole o link de um anúncio ou da loja no Mercado Livre")
    if alvo[0] == "loja":
        vid = alvo[1]
    elif alvo[0] == "apelido":
        try:
            r = _get(f"/sites/{SITE}/search", {"nickname": alvo[1], "limit": 1}) or {}
        except ErroLogin:
            raise
        except ErroMeli:
            raise ErroMeli("o Mercado Livre não deixa o app achar a loja pelo nome: cole o link de um anúncio dela")
        vid = str((r.get("seller") or {}).get("id") or ((r.get("results") or [{}])[0].get("seller") or {}).get("id") or "")
        if not vid:
            raise NaoAchou(f"não achei a loja {alvo[1]}")
    else:
        mlb = alvo[1] if alvo[0] == "item" else _item_do_produto(alvo[1])
        m = itens([mlb])[str(mlb).upper()]
        if m.get("bloqueado"):
            raise ErroMeli(f"o Mercado Livre não libera os detalhes do anúncio {mlb} para o app")
        if m.get("sumiu"):
            raise NaoAchou(f"o Mercado Livre não achou o anúncio {mlb}")
        vid = str(m["vendedor_id"])
    chave = LOJA_CACHE + str(vid)
    if not forcar:
        r = (repo._req("GET", "ia_resumos", {"select": "texto,criado_em", "chave": f"eq.{chave}"}) or [None])[0]
        if r:
            try:
                d = json.loads(r["texto"])
                if time.time() - float(d.get("_ts") or 0) < LOJA_VALIDADE:
                    return d
            except (TypeError, ValueError):
                pass
    loja = lojas([vid]).get(str(vid))
    if not loja:
        raise NaoAchou(f"o Mercado Livre não achou a loja {vid}")
    prods, total, fonte = produtos_da_loja(vid, gtins_fn=gtins_fn)
    loja["anuncios"] = total
    d = {"loja": loja, "produtos": prods, "total_anuncios": total, "fonte_produtos": fonte, **analisar_loja(loja, prods),
         "_ts": time.time(), "atualizado_em": datetime.now(timezone.utc).isoformat()}
    d["hash_nubimetrics"] = [h for h, x in (ler_hash_lojas(repo) or {}).items() if str(x.get("id")) == str(vid)]
    try:
        repo._req("POST", "ia_resumos", corpo=[{"chave": chave, "ia": "Mercado Livre (API)", "texto": json.dumps(d, ensure_ascii=False)}],
                  prefer="resolution=merge-duplicates,return=minimal")
    except Exception:  # noqa: BLE001  (sem o cache a tela sai do mesmo jeito)
        pass
    return d


def _produto_catalogo(pid):
    """Nome, foto e link da página do produto de catálogo (6 h de cache)."""
    def ler():
        try:
            p = _get(f"/products/{pid}") or {}
        except ErroLogin:
            raise
        except ErroMeli:
            return {}
        fotos = p.get("pictures") or []
        return {"nome": p.get("name") or "", "foto": str((fotos[0].get("url") if fotos else "") or "").replace("http://", "https://"),
                "link": p.get("permalink") or ""}
    return _mem("prod|" + pid, 6 * 3600, ler)


MAX_OFERTAS = 1000                      # ofertas lidas por produto de catálogo (o ML devolve 50 por página)


def loja_oficial_do_texto(txt):
    """Explorador do Nubimetrics, coluna "Loja oficial": "LOJA.OFICIAL.23829" -> 23829, o official_store_id do ML (o
    Nubimetrics embaralha o vendedor e o anúncio, mas não o número da loja oficial)."""
    m = re.search(r"OFICIAL\D*(\d+)\s*$", str(txt or ""), re.I)
    return int(m.group(1)) if m else None


def _produtos_do_gtin(g, limite_produtos=2):
    def buscar():
        r = _get("/products/search", {"status": "active", "site_id": SITE, "product_identifier": g}) or {}
        return [p.get("id") for p in r.get("results") or [] if p.get("id")]
    return _mem("gtin|" + g, 30 * 60, buscar)[:limite_produtos]


TOTAL_OFERTAS = {}                        # produto -> quantas ofertas o ML diz que tem (para o diagnóstico)


def ofertas_do_produto(pid, maximo=MAX_OFERTAS):
    """As ofertas (anúncios de catálogo) de um produto do ML, 50 por página, até `maximo`. 29/09: a 1ª versão lia só a
    1ª página, e a loja certa (ICARBONXX) podia estar depois das 50 primeiras. Com o total da 1ª página, as outras vêm em
    paralelo (produção: o Asad Elixir passa de 300)."""
    def pagina(off):
        return _get(f"/products/{pid}/items", {"limit": 50, "offset": off}) or {}

    def seguinte(off):
        try:
            return pagina(off).get("results") or []
        except ErroLogin:
            raise
        except ErroMeli:
            return None                        # o ML recusou esta página: fica com o que veio

    def ler():
        try:
            r = pagina(0)
        except NaoAchou:
            return []                          # produto sem oferta ativa agora
        out, vistos = [], set()

        def juntar(xs):
            novos = [x for x in xs or [] if x.get("item_id") and x["item_id"] not in vistos]
            vistos.update(x["item_id"] for x in novos)
            out.extend(novos)
            return novos
        juntar(r.get("results") or [])
        total = (r.get("paging") or {}).get("total")
        if total is not None:
            TOTAL_OFERTAS[pid] = int(total)
            for xs in _em_paralelo(seguinte, range(50, min(int(total), maximo), 50), 4):
                juntar(xs)
        elif len(r.get("results") or []) >= 50:                    # sem o total: uma página depois da outra
            for off in range(50, maximo, 50):
                xs = seguinte(off)
                if not juntar(xs) or len(xs) < 50:
                    break
        return out
    return _mem(f"prodit|{pid}|{maximo}", 20 * 60, ler)


def _oferta(pid, g, x):
    """Oferta do catálogo no formato das telas, sem pedir o anúncio (o ML não libera /items de outra loja para o app)."""
    sh = x.get("shipping") or {}
    preco, cheio = _num(x.get("price")), _num(x.get("original_price"))
    return {"anuncio": x["item_id"], "link": link_do_item(x["item_id"]), "vendedor_id": x.get("seller_id"), "preco": preco,
            "preco_cheio": cheio if cheio and preco and cheio > preco else None,
            "full": sh.get("logistic_type") == "fulfillment", "frete_gratis": bool(sh.get("free_shipping")),
            "tipo_id": x.get("listing_type_id"), "tipo": TIPOS.get(x.get("listing_type_id"), x.get("listing_type_id") or ""),
            "condicao": x.get("condition") or "", "catalogo": True, "produto_catalogo": pid, "gtin_busca": g,
            "loja_oficial": x.get("official_store_id"), "_tem_oficial": "official_store_id" in x}


def ofertas_por_gtin(gtins, limite_produtos=2, max_gtins=8, maximo=MAX_OFERTAS):
    """Todas as ofertas dos produtos de catálogo desses GTINs agora (leve: sem pedir anúncio nem loja)."""
    gs = list(dict.fromkeys(str(x).strip() for x in gtins if str(x or "").strip()))[:max_gtins]
    pares = [(pid, g) for ps in _em_paralelo(lambda g: [(pid, g) for pid in _produtos_do_gtin(g, limite_produtos)], gs, 4)
             for pid, g in ps]
    out = []
    for (pid, g), xs in zip(pares, _em_paralelo(lambda pg: ofertas_do_produto(pg[0], maximo), pares, 4)):
        out += [_oferta(pid, g, x) for x in xs]
    return out


def _enriquecer(ofs):
    """Título, foto e a loja real de cada oferta: o anúncio quando o ML libera; senão o produto de catálogo."""
    its = itens([o["anuncio"] for o in ofs]) if ofs else {}
    lj = lojas([o.get("vendedor_id") for o in ofs if o.get("vendedor_id")])
    out = {}
    for o in ofs:
        it = its.get(str(o["anuncio"]).upper()) or {}
        if it.get("titulo") and not it.get("sumiu") and not it.get("bloqueado"):
            m = dict(it, preco=o["preco"] or it.get("preco"), produto_catalogo=o["produto_catalogo"], gtin_busca=o["gtin_busca"],
                     loja_oficial=o["loja_oficial"], _tem_oficial=o["_tem_oficial"])
            m["preco_cheio"] = o["preco_cheio"] or it.get("preco_cheio")
            m["full"] = o["full"] or bool(it.get("full"))
            m["frete_gratis"] = o["frete_gratis"] or bool(it.get("frete_gratis"))
        else:
            pc = _produto_catalogo(o["produto_catalogo"])
            m = dict(o, titulo=pc.get("nome") or "", foto=pc.get("foto") or "")
        m["loja"] = lj.get(str(m.get("vendedor_id"))) or {}
        out.setdefault(m["anuncio"], m)
    return sorted(out.values(), key=lambda m: (m.get("preco") is None, m.get("preco") or 0))


def por_gtin(gtins, limite_produtos=2, max_gtins=4, maximo=50, vendedor=None):
    """Quem vende o produto agora: catálogo do ML pelo GTIN. [{anúncio + loja}] do mais barato para o mais caro.
    `vendedor`: só as ofertas dessa loja (com maximo=MAX_OFERTAS lê todas as páginas)."""
    ofs = ofertas_por_gtin(gtins, limite_produtos, max_gtins, maximo)
    if vendedor is not None:
        ofs = [o for o in ofs if str(o.get("vendedor_id")) == str(vendedor)]
    return _enriquecer(ofs)


# ---------------------------------------------------------------------------
# Vendedor do Nubimetrics (hash do Explorador ou vendedor seguido) -> loja real
# ---------------------------------------------------------------------------
# 29/09 (ICARBONXX casou com uma loja nada a ver): o hash do Nubimetrics é feito com chave secreta (testado com 200
# anúncios da PUREHOME: nenhum formato bate), então a loja sai do catálogo do ML, com provas:
# - o nº da loja oficial ("LOJA.OFICIAL.23829" no Explorador) = official_store_id da oferta: prova forte;
# - Full e tipo (Clássico/Premium) iguais são obrigatórios; preço do dia do export (±1%) ou médio do mês (perto);
# - a mesma loja em vários produtos dele; o nome que o Bruno deu ao seguido só desempata.
# Sem prova suficiente não grava nada: devolve as candidatas para o Bruno escolher.
SEGUIDOS = "meli|seguidos"              # vendedor seguido no Nubimetrics (nome) -> loja real + anúncios dela


def ler_hash_lojas(repo, chave=HASH_LOJAS):
    r = (repo._req("GET", "ia_resumos", {"select": "texto", "chave": f"eq.{chave}"}) or [None])[0]
    try:
        return json.loads(r["texto"]) if r and r.get("texto") else {}
    except (TypeError, ValueError):
        return {}


def gravar_hash_lojas(repo, novos, chave=HASH_LOJAS, tirar=()):
    """Grava o de-para; `tirar`: chaves cujo de-para automático não se confirmou (o manual do Bruno nunca sai)."""
    atual = ler_hash_lojas(repo, chave)
    for h, x in novos.items():
        velho = atual.get(h)
        if not velho or velho.get("confianca") != "manual":       # o que o Bruno confirmou à mão não é trocado
            atual[h] = x
    for h in tirar:
        if h in atual and atual[h].get("confianca") != "manual":
            atual.pop(h)
    repo._req("POST", "ia_resumos", corpo=[{"chave": chave, "ia": "Mercado Livre (API)",
                                            "texto": json.dumps(atual, ensure_ascii=False)}],
              prefer="resolution=merge-duplicates,return=minimal")
    return atual


def _tipo_ml(txt):
    """'Clássico'/'Clássica'/gold_special -> gold_special; 'Premium'/gold_pro/gold_premium -> gold_pro."""
    t = str(txt or "").strip().lower()
    if t.startswith("cl") or t == "gold_special":
        return "gold_special"
    if t.startswith("pr") or t in ("gold_pro", "gold_premium"):
        return "gold_pro"
    return None


def _pontos_preco(po, pr, exato):
    """Preço de agora (ML) x o do Nubimetrics. exato: o 'Último preço' do dia do export do Explorador (±1% ou R$ 1 é
    'exato'); senão o preço médio do mês do vendedor seguido (no máximo 'perto')."""
    if not po or not pr:
        return 0.0, ""
    if exato and abs(po - pr) <= max(1.0, 0.01 * pr):
        return 3.0, "exato"
    d = abs(po - pr) / pr
    teto, lim, perto = (1.5, 0.15, 0.05) if exato else (2.0, 0.20, 0.10)
    if d > lim:
        return 0.0, ""
    return round(teto * (1 - d / lim), 3), ("perto" if d <= perto else "")      # quanto mais perto, mais ponto


def _data(v):
    if not v:
        return None
    if hasattr(v, "year") and not isinstance(v, datetime):
        return v
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def ref_explorador(l, hoje=None, data_ref=None):
    """Linha do Explorador -> o que ela diz do anúncio (ver casar)."""
    hoje = hoje or datetime.now(timezone.utc).date()
    d = _data(l.get("data_ref")) or _data(data_ref)
    dl = l.get("dias_pub")
    try:
        dl = int(dl) if dl is not None and dl == dl else None           # NaN do pandas vira None
    except (TypeError, ValueError):
        dl = None
    cat, un = l.get("catalogo"), _num(l.get("un"))
    return {"gtins": [str(l.get("gtin") or "")], "preco": _num(l.get("preco")), "full": bool(l.get("full")),
            "exato": bool(d and 0 <= (hoje - d).days <= 5), "loja_oficial": l.get("loja_oficial_id"),
            "tipo": l.get("exposicao") or None, "catalogo": None if cat is None or cat != cat else bool(cat),
            "dias_pub": dl, "data_ref": d, "peso": un if un and un == un else 0.0}


def casar(refs, ofertas):
    """
    refs: o que o Nubimetrics diz dos anúncios de UM vendedor [{gtins, preco, full, exato, loja_oficial (nº; 0 = sabido
    que não é; None = não se sabe), tipo, catalogo, dias_pub, data_ref}]; ofertas: ofertas_por_gtin (catálogo agora).
    Obrigatórios: Full igual, tipo igual e, quando o Explorador traz, o nº da loja oficial igual. Anúncio fora do
    catálogo não entra (não aparece nas ofertas do produto). Cada produto conta uma vez por loja.
    Devolve (candidatas da mais forte para a mais fraca, nº de produtos sondados).
    """
    por_g = {}
    for o in ofertas:
        por_g.setdefault(str(o.get("gtin_busca") or ""), []).append(o)
    grupos = {}
    for r in refs:
        if r.get("catalogo") is False or not _num(r.get("preco")):
            continue
        gs = [str(g) for g in r.get("gtins") or [] if str(g) in por_g]
        if gs:
            grupos.setdefault(gs[0], []).append((r, gs))
    cand = {}
    for rs in grupos.values():
        melhor = {}
        for r, gs in rs:
            pr, lo_r, tipo_r = _num(r.get("preco")), r.get("loja_oficial"), _tipo_ml(r.get("tipo"))
            dl, dref = r.get("dias_pub"), _data(r.get("data_ref"))
            for g in gs:
                for o in por_g[g]:
                    sid = str(o.get("vendedor_id") or "")
                    if not sid or bool(o.get("full")) != bool(r.get("full")):
                        continue
                    tipo_o = _tipo_ml(o.get("tipo_id"))
                    if tipo_r and tipo_o and tipo_r != tipo_o:
                        continue
                    oficial = None
                    if o.get("_tem_oficial") and lo_r is not None:
                        if int(o.get("loja_oficial") or 0) != int(lo_r or 0):
                            continue
                        oficial = int(lo_r) or None
                    idade_ok = False
                    criado = _data(o.get("criado_em"))
                    if dl is not None and dref and criado:            # só quando o ML dá o anúncio (hoje não dá ao app)
                        idade = (dref - criado).days
                        if abs(idade - int(dl)) > 3:
                            continue
                        idade_ok = abs(idade - int(dl)) <= 1
                    pp, como = _pontos_preco(_num(o.get("preco")), pr, r.get("exato"))
                    pts = 1.0 + pp + (4.0 if oficial else 0.0) + (3.0 if idade_ok else 0.0)
                    if pts > melhor.get(sid, (0.0,))[0]:
                        melhor[sid] = (pts, como, oficial, idade_ok)
        for sid, (pts, como, oficial, idade_ok) in melhor.items():
            c = cand.setdefault(sid, {"id": sid, "pontos": 0.0, "produtos": 0, "exato": 0, "perto": 0, "idade": 0, "oficial": []})
            c["pontos"] += pts
            c["produtos"] += 1
            c["exato"] += como == "exato"
            c["perto"] += como == "perto"
            c["idade"] += idade_ok
            if oficial and oficial not in c["oficial"]:
                c["oficial"].append(oficial)
    return sorted(cand.values(), key=lambda c: (-c["pontos"], -c["produtos"])), len(grupos)


def decidir(cands, sondados):
    """'certa' | 'provável' | None (sem prova suficiente: não grava, mostra as candidatas)."""
    if not cands:
        return None
    c1, outros = cands[0], cands[1:]
    c2 = outros[0] if outros else None
    rivais = set().union(*[set(c["oficial"]) for c in outros]) if outros else set()
    if set(c1["oficial"]) - rivais and (c1["produtos"] >= 2 or c1["exato"] or c1["idade"]):
        return "certa"                          # o nº da loja oficial do Explorador é o desta loja, e só dela
    if c1["exato"] >= 3 and not (c2 and c2["exato"] >= 2):
        return "certa"                          # o preço do dia do export bate exato em 3+ produtos
    if c1["exato"] and c1["idade"] and not any(c["exato"] and c["idade"] for c in outros):
        return "provável"                       # preço do dia e idade do anúncio batem (vale para 1 produto só)
    minimo = max(2, -(-sondados // 2))          # em pelo menos metade dos produtos sondados (e 2), mais que qualquer rival
    if (c1["produtos"] >= minimo and c1["produtos"] > (c2["produtos"] if c2 else 0) and c1["exato"] + c1["perto"] >= 2
            and c1["pontos"] - (c2["pontos"] if c2 else 0.0) >= 2):
        return "provável"
    return None


def _prova(c, sondados):
    p = [f"em {c['produtos']} de {sondados} produto(s) dele no catálogo"]
    if c.get("oficial"):
        p.append("loja oficial nº " + ", ".join(str(x) for x in c["oficial"]))
    if c.get("exato"):
        p.append(f"preço do dia exato em {c['exato']}")
    if c.get("perto"):
        p.append(f"preço perto em {c['perto']}")
    if c.get("idade"):
        p.append(f"idade do anúncio igual em {c['idade']}")
    if c.get("nome_bate"):
        p.append("nome parecido")
    return "; ".join(p) + "; Full e tipo iguais"


def casar_vendedores(linhas, ml, data_ref=None):
    """
    Quadro do produto: os vendedores embaralhados do Explorador x ofertas do catálogo agora -> {hash: loja}, só com
    prova (loja oficial, ou preço do dia + idade do anúncio). linhas: [{vendedor_id (hash), gtin, preco, full,
    loja_oficial_id, exposicao, catalogo, dias_pub, data_ref}] do período que termina em `data_ref`.
    """
    hoje = datetime.now(timezone.utc).date()
    lj = {str(m.get("vendedor_id")): m.get("loja") or {} for m in ml if m.get("vendedor_id")}
    por_h = {}
    for l in linhas:
        if l.get("vendedor_id") and l.get("gtin") and _num(l.get("preco")):
            por_h.setdefault(l["vendedor_id"], []).append(ref_explorador(l, hoje, data_ref))
    out = {}
    for h, refs in por_h.items():
        cands, sondados = casar(refs, ml)
        conf = decidir(cands, sondados)
        if conf:
            c, loja = cands[0], lj.get(cands[0]["id"]) or {}
            out[h] = {"id": c["id"], "nome": loja.get("nome") or "", "link": loja.get("link") or "", "votos": c["produtos"],
                      "oficial": c["oficial"], "confianca": conf, "prova": _prova(c, sondados),
                      "em": datetime.now(timezone.utc).isoformat()}
    return out


def gtins_do_texto(txt):
    """O Nubimetrics às vezes cola 2 GTINs no mesmo campo ("78994631129785055810099459" = 7899463112978 + 5055810099459)."""
    t = re.sub(r"\D", "", str(txt or ""))
    if len(t) in (8, 12, 13, 14):
        return [t]
    if len(t) > 14 and len(t) % 13 == 0:
        return [t[i:i + 13] for i in range(0, len(t), 13)]
    return []


def _base_nome(nome):
    """"ICARBONXX P3" -> "ICARBONXX"; "MAMS ECOMMERCE TOP14" -> "MAMSECOMMERCE" (o P3/TOP14 é rótulo do Bruno)."""
    import unicodedata
    n = re.sub(r"\s+(P|TOP)\s*\d+$", "", str(nome or "").strip(), flags=re.I)
    return re.sub(r"[^A-Z0-9]", "", unicodedata.normalize("NFKD", n).encode("ascii", "ignore").decode().upper())


def achar_loja(nome, refs, ofertas, un_mes=None):
    """
    Vendedor do Nubimetrics (refs do Explorador + do relatório do seguido) x ofertas do catálogo -> (loja escolhida ou
    None, candidatas). nome: o que o Bruno deu ao seguido ("ICARBONXX P3"); é rótulo dele, então só desempata.
    un_mes: unidades dele no mês no Nubimetrics. Trava (ideia do Cowork, 29/09): loja com menos vendas NA VIDA do que
    metade disso não pode ser ele (a LUH… que entrou errado no ICARBONXX tinha 230 vendas; ele vende 25 mil/mês).
    A escolhida traz os anúncios dela achados no catálogo (ID, link, preço de agora).
    """
    cands, sondados = casar(refs, ofertas)
    top = cands[:6]
    lj = lojas([c["id"] for c in top]) if top else {}
    base = _base_nome(nome)
    for c in top:
        loja = lj.get(c["id"]) or {}
        c.update(nome=loja.get("nome") or "", link=loja.get("link") or "", vendas_vida=loja.get("vendas"))
        nick = _base_nome(c["nome"])
        c["nome_bate"] = bool(base and nick and len(min(base, nick, key=len)) >= 4 and (base in nick or nick in base))
        c["pontos"] += 1.0 if c["nome_bate"] else 0.0
    if un_mes:
        top = [c for c in top if c.get("vendas_vida") is None or c["vendas_vida"] >= un_mes / 2]
        if not top:                            # todas pequenas demais: nenhuma é ele
            return None, []
    cands = sorted(top, key=lambda c: (-c["pontos"], -c["produtos"])) + cands[6:]
    conf = decidir(cands, sondados)
    mostrar = [{"id": c["id"], "nome": c.get("nome") or "", "link": c.get("link") or "", "produtos": c["produtos"],
                "sondados": sondados, "exato": c["exato"], "perto": c["perto"], "oficial": c["oficial"],
                "prova": _prova(c, sondados)} for c in cands[:3]]
    if not conf:
        return None, mostrar
    c = cands[0]
    anuncios, nomes = {}, {}
    for o in ofertas:
        if str(o.get("vendedor_id")) == c["id"] and o["anuncio"] not in anuncios:
            pid = o.get("produto_catalogo")
            if pid and pid not in nomes:
                nomes[pid] = _produto_catalogo(pid).get("nome") or ""
            anuncios[o["anuncio"]] = {"anuncio": o["anuncio"], "link": o.get("link") or link_do_item(o["anuncio"]),
                                      "titulo": nomes.get(pid, ""), "preco": o.get("preco"), "full": bool(o.get("full")),
                                      "produto_catalogo": pid or ""}
    x = {"id": c["id"], "nome": c["nome"], "link": c["link"], "votos": c["produtos"], "sondados": sondados,
         "preco_bate": c["exato"] + c["perto"], "exato": c["exato"], "oficial": c["oficial"], "nome_bate": c["nome_bate"],
         "confianca": conf, "prova": _prova(c, sondados), "em": datetime.now(timezone.utc).isoformat(),
         "anuncios": sorted(anuncios.values(), key=lambda a: a.get("titulo") or "")[:60]}
    return x, mostrar


# ---------------------------------------------------------------------------
# Diagnóstico (botão "testar conexão"): o que funciona com o token do app
# ---------------------------------------------------------------------------
def _diag_varios(mlb):
    r = _get("/items", {"ids": mlb, "attributes": ITEM_CAMPOS}) or []
    x = (r if isinstance(r, list) else [{}])[0] or {}
    b = x.get("body") or {}
    return f"código {x.get('code')}: " + (b.get("title") or str(b.get("message") or b.get("error") or "")[:90])


def testar(mlb="MLB4577439527", gtin="6290362346548"):
    """Botão 🔌 da tela: cada recurso da API com o código e a mensagem do ML (nunca token nem segredo)."""
    passos = []

    def passo(nome, f):
        t = time.time()
        try:
            r = f()
            passos.append({"passo": nome, "ok": True, "ms": int((time.time() - t) * 1000), "detalhe": r})
        except ErroMeli as e:
            passos.append({"passo": nome, "ok": False, "ms": int((time.time() - t) * 1000), "detalhe": str(e)})
    if not tem_chave():
        return {"chaves": False, "passos": [{"passo": "chaves", "ok": False, "detalhe": FALTA_CHAVE}]}
    passo("token do app", lambda: "ok" if _token(True) else "")
    passo("vários anúncios (/items?ids=)", lambda: _diag_varios(mlb))
    passo("um anúncio (/items/ID)", lambda: (_get(f"/items/{mlb}") or {}).get("title") or "sem título")
    cat = {}

    def catalogo():
        xs = por_gtin([gtin])
        cat["xs"] = xs
        oficial = (f"{sum(1 for x in xs if x.get('loja_oficial'))} de loja oficial (com o nº)" if any(x.get("_tem_oficial") for x in xs)
                   else "o ML não mandou o nº da loja oficial")
        return (f"{len(xs)} anúncio(s); {sum(1 for x in xs if x.get('titulo'))} com título; "
                f"{sum(1 for x in xs if (x.get('loja') or {}).get('nome'))} com a loja; {oficial}")
    passo("catálogo pelo GTIN (/products)", catalogo)
    def paginas():
        n = len(ofertas_por_gtin([gtin], max_gtins=1))
        tot = sum(TOTAL_OFERTAS.get(pid, 0) for pid in _produtos_do_gtin(gtin))
        return f"{n} ofertas lidas" + (f" de {tot} no catálogo" if tot else "") + " (50 por página, em paralelo)"
    passo("todas as páginas do catálogo", paginas)
    sid = next((x.get("vendedor_id") for x in cat.get("xs") or [] if x.get("vendedor_id")), None)
    passo("loja (/users/ID)", lambda: (_get(f"/users/{sid}") or {}).get("nickname") if sid else "sem vendedor para testar")
    passo("visitas (/items/visits)", lambda: visitas([mlb]).get(mlb))
    passo("tarifa (/sites/MLB/listing_prices)", lambda: (tarifa(100, "MLB6284", "gold_special") or {}).get("pct"))
    passo("busca por loja (/sites/MLB/search)",
          lambda: (_get(f"/sites/{SITE}/search", {"seller_id": sid or 1, "limit": 1}) or {}).get("paging", {}).get("total"))
    return {"chaves": True, "passos": passos}
