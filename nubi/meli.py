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
    for i, m in _em_paralelo(um, faltando[:40]):
        if isinstance(m, dict) and m.get("anuncio"):
            out[i] = m
            _CACHE["item|" + i] = (time.time(), m)
        elif m == "bloqueado":
            out[i] = {"anuncio": i, "bloqueado": True, "link": link_do_item(i)}
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
        prods = [m for m in por_gtin(gtins, max_gtins=8) if str(m.get("vendedor_id")) == str(vendedor_id)]
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


def por_gtin(gtins, limite_produtos=2, max_gtins=4):
    """Quem vende o produto agora: catálogo do ML pelo GTIN. [{anúncio + loja}] do mais barato para o mais caro."""
    achados = []
    for g in [str(x).strip() for x in gtins if str(x or "").strip()][:max_gtins]:
        def buscar(g=g):
            r = _get("/products/search", {"status": "active", "site_id": SITE, "product_identifier": g}) or {}
            return [p.get("id") for p in r.get("results") or [] if p.get("id")][:limite_produtos]
        for pid in _mem("gtin|" + g, 30 * 60, buscar):
            def itens_do_produto(pid=pid):
                return (_get(f"/products/{pid}/items", {"limit": 50}) or {}).get("results") or []
            for x in _mem("prodit|" + pid, 20 * 60, itens_do_produto):
                if x.get("item_id"):
                    achados.append((pid, g, x))
    ids = list(dict.fromkeys(x["item_id"] for _, _, x in achados))
    its = itens(ids)
    lj = lojas([m.get("vendedor_id") for m in its.values() if m.get("vendedor_id")] + [x.get("seller_id") for _, _, x in achados])
    out = []
    for pid, g, x in achados:
        m = dict(its.get(str(x["item_id"]).upper()) or {"anuncio": x["item_id"]})
        if m.get("sumiu") or m.get("bloqueado") or not m.get("titulo"):
            # o ML não deu o anúncio para o app: título, foto e tipo vêm do catálogo e do próprio item do catálogo
            pc = _produto_catalogo(pid)
            m = {"anuncio": x["item_id"], "link": link_do_item(x["item_id"]), "titulo": pc.get("nome") or "",
                 "foto": pc.get("foto") or "", "tipo": TIPOS.get(x.get("listing_type_id"), x.get("listing_type_id") or ""),
                 "tipo_id": x.get("listing_type_id"), "catalogo": True, "condicao": x.get("condition") or "",
                 "vendedor_id": x.get("seller_id")}
        m.setdefault("preco", _num(x.get("price")))
        m.setdefault("vendedor_id", x.get("seller_id"))
        m["preco"] = _num(x.get("price")) or m.get("preco")          # o preço do catálogo é o de agora
        if x.get("original_price") and _num(x["original_price"]) and m["preco"] and _num(x["original_price"]) > m["preco"]:
            m["preco_cheio"] = _num(x["original_price"])
        sh = x.get("shipping") or {}
        if sh:
            m["full"] = sh.get("logistic_type") == "fulfillment" or m.get("full", False)
            m["frete_gratis"] = bool(sh.get("free_shipping")) or m.get("frete_gratis", False)
        m.update(produto_catalogo=pid, gtin_busca=g, loja=lj.get(str(m.get("vendedor_id"))) or {})
        out.append(m)
    uniq = {}
    for m in out:
        uniq.setdefault(m["anuncio"], m)
    return sorted(uniq.values(), key=lambda m: (m.get("preco") is None, m.get("preco") or 0))


# ---------------------------------------------------------------------------
# Vendedor embaralhado do Nubimetrics (hash) -> loja real
# ---------------------------------------------------------------------------
SEGUIDOS = "meli|seguidos"              # vendedor seguido no Nubimetrics (nome) -> loja real + anúncios dela


def ler_hash_lojas(repo, chave=HASH_LOJAS):
    r = (repo._req("GET", "ia_resumos", {"select": "texto", "chave": f"eq.{chave}"}) or [None])[0]
    try:
        return json.loads(r["texto"]) if r and r.get("texto") else {}
    except (TypeError, ValueError):
        return {}


def gravar_hash_lojas(repo, novos, chave=HASH_LOJAS):
    atual = ler_hash_lojas(repo, chave)
    for h, x in novos.items():
        velho = atual.get(h)
        if not velho or velho.get("confianca") != "manual":       # o que o Bruno confirmou à mão não é trocado
            atual[h] = x
    repo._req("POST", "ia_resumos", corpo=[{"chave": chave, "ia": "Mercado Livre (API)",
                                            "texto": json.dumps(atual, ensure_ascii=False)}],
              prefer="resolution=merge-duplicates,return=minimal")
    return atual


def casar_vendedores(linhas, ml, data_ref=None):
    """
    linhas: anúncios do Nubimetrics [{vendedor_id (hash), gtin, preco, full, dias_pub}] de um período que termina em
    `data_ref`; ml: anúncios do ML do mesmo GTIN (por_gtin). O anúncio do ML casa quando o preço bate (±1% ou R$ 1),
    o Full é o mesmo e a idade bate (dias publicados na data do export, ±3). Cada hash vota na loja; ganha a loja com
    mais votos, e 2 votos (ou 1 com a idade exata) viram 'provável'. Devolve {hash: {id, nome, link, votos, confianca}}.
    """
    data_ref = data_ref or datetime.now(timezone.utc).date()
    votos = {}
    for l in linhas:
        pl, dl = _num(l.get("preco")), l.get("dias_pub")
        ref = l.get("data_ref") or data_ref
        if not pl:
            continue
        for m in ml:
            if str(m.get("gtin_busca") or m.get("gtin") or "") and str(l.get("gtin") or "") not in (str(m.get("gtin_busca") or ""), str(m.get("gtin") or "")):
                continue
            pm = _num(m.get("preco"))
            if not pm or abs(pm - pl) > max(1.0, 0.01 * pl) or bool(m.get("full")) != bool(l.get("full")):
                continue
            exato = False
            if dl is not None and m.get("criado_em"):
                try:
                    criado = datetime.fromisoformat(str(m["criado_em"]).replace("Z", "+00:00")).date()
                except ValueError:
                    criado = None
                if criado:
                    idade = (ref - criado).days
                    if abs(idade - int(dl)) > 3:
                        continue
                    exato = abs(idade - int(dl)) <= 1
            sid = str(m.get("vendedor_id") or "")
            if not sid:
                continue
            v = votos.setdefault(l["vendedor_id"], {}).setdefault(sid, {"votos": 0, "exato": 0, "loja": m.get("loja") or {}})
            v["votos"] += 1
            v["exato"] += 1 if exato else 0
    out = {}
    for h, cands in votos.items():
        sid, v = max(cands.items(), key=lambda kv: (kv[1]["exato"], kv[1]["votos"]))
        outros = sum(x["votos"] for s, x in cands.items() if s != sid)
        if v["votos"] >= 2 or v["exato"] >= 1:
            lj = v["loja"]
            out[h] = {"id": sid, "nome": lj.get("nome") or "", "link": lj.get("link") or "", "votos": v["votos"],
                      "confianca": "provável" if outros == 0 else "dúvida", "em": datetime.now(timezone.utc).isoformat()}
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


def casar_seguido(nome, linhas, ml):
    """
    Vendedor SEGUIDO no Nubimetrics (o export dele não tem ID de anúncio; preço é o MÉDIO do mês) -> loja real.
    linhas: [{gtins, preco (médio), full, catalogo}]; ml: por_gtin dos GTINs dele. Cada loja do ML ganha ponto por produto
    dele em que aparece, por preço perto do médio (±8%), por Full igual e, forte, pelo nome parecido ("ICARBONXX P3" x
    ICARBONXX). Devolve a loja + os anúncios dela achados ({anuncio, link, titulo, preco}) ou None.
    """
    base = _base_nome(nome)
    por_g = {}
    for m in ml:
        por_g.setdefault(str(m.get("gtin_busca") or ""), []).append(m)
    cand = {}
    for l in linhas:
        for g in l.get("gtins") or []:
            for m in por_g.get(g, []):
                sid = str(m.get("vendedor_id") or "")
                if not sid:
                    continue
                c = cand.setdefault(sid, {"presenca": set(), "preco": 0, "full": 0, "loja": m.get("loja") or {}, "anuncios": {}})
                if g in c["presenca"]:
                    continue
                c["presenca"].add(g)
                pm, pl = _num(m.get("preco")), _num(l.get("preco"))
                if pm and pl and abs(pm - pl) <= 0.08 * pl:
                    c["preco"] += 1
                if bool(m.get("full")) == bool(l.get("full")):
                    c["full"] += 1
                c["anuncios"][m["anuncio"]] = {"anuncio": m["anuncio"], "link": m.get("link") or link_do_item(m["anuncio"]),
                                               "titulo": m.get("titulo") or "", "preco": m.get("preco"), "full": bool(m.get("full"))}
    if not cand:
        return None
    for c in cand.values():
        nick = _base_nome((c["loja"] or {}).get("nome"))
        c["nome_bate"] = bool(base and nick and len(min(base, nick, key=len)) >= 4 and (base == nick or base in nick or nick in base))
        c["pontos"] = len(c["presenca"]) + c["preco"] + 0.5 * c["full"] + (6 if c["nome_bate"] else 0)
    ordem = sorted(cand.items(), key=lambda kv: -kv[1]["pontos"])
    sid, c = ordem[0]
    seg = ordem[1][1]["pontos"] if len(ordem) > 1 else 0
    if c["nome_bate"] or (len(c["presenca"]) >= 3 and c["preco"] >= 2 and c["pontos"] - seg >= 2):
        conf = "provável"
    elif c["pontos"] >= 3 and c["pontos"] > seg:
        conf = "dúvida"
    else:
        return None
    lj = c["loja"] or {}
    return {"id": sid, "nome": lj.get("nome") or "", "link": lj.get("link") or "", "votos": len(c["presenca"]),
            "preco_bate": c["preco"], "nome_bate": c["nome_bate"], "confianca": conf, "em": datetime.now(timezone.utc).isoformat(),
            "anuncios": sorted(c["anuncios"].values(), key=lambda a: a.get("titulo") or "")[:40]}


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
        return f"{len(xs)} anúncio(s); {sum(1 for x in xs if x.get('titulo'))} com título; {sum(1 for x in xs if (x.get('loja') or {}).get('nome'))} com a loja"
    passo("catálogo pelo GTIN (/products)", catalogo)
    sid = next((x.get("vendedor_id") for x in cat.get("xs") or [] if x.get("vendedor_id")), None)
    passo("loja (/users/ID)", lambda: (_get(f"/users/{sid}") or {}).get("nickname") if sid else "sem vendedor para testar")
    passo("visitas (/items/visits)", lambda: visitas([mlb]).get(mlb))
    passo("tarifa (/sites/MLB/listing_prices)", lambda: (tarifa(100, "MLB6284", "gold_special") or {}).get("pct"))
    passo("busca por loja (/sites/MLB/search)",
          lambda: (_get(f"/sites/{SITE}/search", {"seller_id": sid or 1, "limit": 1}) or {}).get("paging", {}).get("total"))
    return {"chaves": True, "passos": passos}
