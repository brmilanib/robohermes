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
import contextvars
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


# ---------------------------------------------------------------------------
# Conta do ML conectada (29/09, autorizado pelo Bruno: "vamos logar uma conta minha que não uso, a mesma que criou a API").
# O token do APP (client_credentials) leva 403 em /items e /sites/MLB/search; com o token de um USUÁRIO o ML libera.
# O login é na página do próprio ML (a senha nunca passa pelo nubi). O refresh_token fica CIFRADO em ia_resumos
# (meli|conta), com chave derivada do ML_CLIENT_SECRET (que só existe na Vercel); o access_token só na memória.
# Nada de token em log, erro ou tela. Qualquer falha volta para o token do app.
# ---------------------------------------------------------------------------
CONTA = "meli|conta"
AUTH = os.environ.get("NUBI_ML_AUTH", "https://auth.mercadolivre.com.br")
_USUARIO = {"valor": None, "ate": 0.0, "erro": None, "nick": None, "falhou_em": 0.0}
USUARIO_REPO = None                       # nubi_web liga aqui uma função que devolve o repositório (login do agente)


def _chave_cifra():
    import hashlib, hmac
    return hmac.new((os.environ.get("ML_CLIENT_SECRET") or "").encode(), b"nubi|meli|conta|v1", hashlib.sha256).digest()


def cifrar(texto):
    """Cifra autenticada só com a biblioteca padrão: fluxo HMAC-SHA256 em contador + etiqueta HMAC (encrypt-then-MAC)."""
    import base64, hashlib, hmac, secrets
    k = _chave_cifra()
    dado, nonce = texto.encode(), secrets.token_bytes(16)
    fluxo = b"".join(hmac.new(k, nonce + i.to_bytes(4, "big"), hashlib.sha256).digest() for i in range(len(dado) // 32 + 1))
    ct = bytes(a ^ b for a, b in zip(dado, fluxo))
    tag = hmac.new(k, b"tag" + nonce + ct, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + tag + ct).decode()


def decifrar(tok):
    import base64, hashlib, hmac
    k = _chave_cifra()
    raw = base64.urlsafe_b64decode(tok.encode())
    nonce, tag, ct = raw[:16], raw[16:48], raw[48:]
    if not hmac.compare_digest(tag, hmac.new(k, b"tag" + nonce + ct, hashlib.sha256).digest()):
        raise ValueError("conta do ML: dado cifrado não confere (chave trocada?)")
    fluxo = b"".join(hmac.new(k, nonce + i.to_bytes(4, "big"), hashlib.sha256).digest() for i in range(len(ct) // 32 + 1))
    return bytes(a ^ b for a, b in zip(ct, fluxo)).decode()


def url_conectar(redirect, estado):
    return f"{AUTH}/authorization?" + urllib.parse.urlencode({"response_type": "code", "client_id": os.environ.get("ML_CLIENT_ID", ""),
                                                              "redirect_uri": redirect, "state": estado})


def _oauth(dados):
    corpo = urllib.parse.urlencode({"client_id": os.environ["ML_CLIENT_ID"], "client_secret": os.environ["ML_CLIENT_SECRET"], **dados}).encode()
    req = urllib.request.Request(f"{API}/oauth/token", data=corpo, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        with _abrir(req, 20) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            motivo = str(json.loads(e.read() or b"{}").get("error") or "")[:60]
        except Exception:  # noqa: BLE001
            motivo = ""
        raise ErroLogin(f"o Mercado Livre recusou a conta ({e.code}{': ' + motivo if motivo else ''})")
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ErroLogin("sem resposta do Mercado Livre (login da conta)")


def ler_conta(repo):
    r = (repo._req("GET", "ia_resumos", {"select": "texto", "chave": repo._eq(CONTA)}) or [None])[0]
    try:
        d = json.loads(r["texto"]) if r else {}
    except (TypeError, ValueError):
        d = {}
    return d if d.get("refresh") else {}


def _gravar_conta(repo, d):
    repo._req("POST", "ia_resumos", corpo=[{"chave": CONTA, "ia": "Mercado Livre (conta)", "texto": json.dumps(d, ensure_ascii=False)}],
              prefer="resolution=merge-duplicates,return=minimal")


def conectar_conta(repo, codigo, redirect):
    """Troca o código da volta do login pelo token do usuário; guarda o refresh cifrado. Devolve {id, nick}."""
    d = _oauth({"grant_type": "authorization_code", "code": codigo, "redirect_uri": redirect})
    if not d.get("access_token") or not d.get("refresh_token"):
        raise ErroLogin("o Mercado Livre não devolveu o acesso da conta (confira se o app pede 'offline_access')")
    req = urllib.request.Request(f"{API}/users/me", headers={"Authorization": f"Bearer {d['access_token']}", "Accept": "application/json"})
    try:
        with _abrir(req, 20) as r:
            eu = json.loads(r.read() or b"{}")
    except Exception:  # noqa: BLE001
        eu = {}
    conta = {"id": eu.get("id") or d.get("user_id"), "nick": eu.get("nickname") or "", "refresh": cifrar(d["refresh_token"]),
             "em": datetime.now(timezone.utc).isoformat(), "escopo": d.get("scope") or ""}
    _gravar_conta(repo, conta)
    _USUARIO.update(valor=d["access_token"], ate=time.time() + max(300, int(d.get("expires_in") or 21600) - 300),
                    erro=None, nick=conta["nick"], falhou_em=0.0)
    _CACHE.pop("items|bloqueado", None)           # com a conta, /items pode voltar a funcionar na hora
    return {"id": conta["id"], "nick": conta["nick"]}


def desconectar_conta(repo):
    _gravar_conta(repo, {"desconectada_em": datetime.now(timezone.utc).isoformat()})
    _USUARIO.update(valor=None, ate=0.0, nick=None, erro=None)


def _token_usuario(forcar=False):
    """Token da conta conectada (renova sozinho pelo refresh; o ML troca o refresh a cada uso e o novo é gravado).
    Sem conta, sem repositório ou com erro: None (usa o do app). Depois de uma falha, espera 10 min para tentar de novo."""
    if not forcar and _USUARIO["valor"] and time.time() < _USUARIO["ate"]:
        return _USUARIO["valor"]
    if USUARIO_REPO is None or not tem_chave() or time.time() - _USUARIO["falhou_em"] < 600:
        return None
    try:
        repo = USUARIO_REPO()
        conta = ler_conta(repo)
        if not conta:
            _USUARIO.update(valor=None, erro=None, nick=None)
            return None
        d = _oauth({"grant_type": "refresh_token", "refresh_token": decifrar(conta["refresh"])})
        if not d.get("access_token"):
            raise ErroLogin("o Mercado Livre não renovou o acesso da conta")
        if d.get("refresh_token"):
            _gravar_conta(repo, dict(conta, refresh=cifrar(d["refresh_token"]), renovado_em=datetime.now(timezone.utc).isoformat()))
        _USUARIO.update(valor=d["access_token"], ate=time.time() + max(300, int(d.get("expires_in") or 21600) - 300),
                        erro=None, nick=conta.get("nick"), falhou_em=0.0)
        return _USUARIO["valor"]
    except Exception as e:  # noqa: BLE001  (a conta é um extra: sem ela segue o token do app)
        _USUARIO.update(valor=None, erro=str(e)[:160], falhou_em=time.time())
        return None


def token_em_uso():
    """Para o diagnóstico: qual token está valendo (sem mostrar o token)."""
    return {"conta": _USUARIO.get("nick") if _token_usuario() else None, "erro_conta": _USUARIO.get("erro")}


# 03/10 (Bruno: "uma página para cada loja, sem misturar"): o token de UMA loja conectada em 🔌 Conexões vale só dentro
# daquela consulta (contextvar); fora dela segue o token da conta principal / do app, como sempre.
TOKEN_DA_VEZ = contextvars.ContextVar("token_da_vez", default=None)


def _get(caminho, params=None, timeout=20, headers=None):
    url = f"{API}{caminho}" + (("&" if "?" in caminho else "?") + urllib.parse.urlencode(params) if params else "")
    forcar = False
    for tentativa in range(3):
        tok = TOKEN_DA_VEZ.get() or _token_usuario(forcar) or _token(forcar)
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}", "Accept": "application/json", **(headers or {})})
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
                # 29/09 (403 mesmo com a conta conectada): o código e quem bloqueou dizem se é política do app ou do IP
                extra = [str(corpo.get(k)) for k in ("code", "blocked_by") if corpo.get(k) and str(corpo.get(k)) not in motivo]
                causa = corpo.get("cause")
                if isinstance(causa, list) and causa:
                    causa = causa[0].get("code") if isinstance(causa[0], dict) else causa[0]
                if causa and not isinstance(causa, (dict, list)):
                    extra.append(str(causa)[:60])
                if extra:
                    motivo = (motivo + " · " + " · ".join(extra))[:180]
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
TIPOS_FICHA = (("body splash", "Body Splash"), ("extrait", "Parfum"), ("eau de parfum", "EDP"), ("eau de toilette", "EDT"),
               ("eau de cologne", "EDC"), ("colonia", "EDC"), ("colônia", "EDC"), ("parfum", "Parfum"))


def ficha_dos_atributos(attrs):
    """01/10 (Bruno: "confirme o anúncio pela API do ML antes de juntar"): as características do anúncio/produto no ML
    ("Tipo: Eau de parfum", "Volume da unidade: 100 mL") -> {"tipo": "EDP", "volume": "100 ml"} (o que não vier fica None)."""
    tipo = volume = None
    for a in attrs or []:
        nome = str(a.get("name") or "").lower()
        aid = str(a.get("id") or "").upper()
        val = str(a.get("value_name") or "").strip()
        if not val:
            continue
        if volume is None and ("VOLUME" in aid or nome.startswith("volume")):
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*(ml|l)\b", val.lower())
            if m:
                n = float(m.group(1).replace(",", "."))
                volume = f"{int(round(n * 1000 if m.group(2) == 'l' else n))} ml"
        if tipo is None and (nome in ("tipo", "tipo de perfume", "concentração", "concentracao") or aid in ("FRAGRANCE_TYPE", "PERFUME_TYPE", "FRAGRANCE_CONCENTRATION")):
            v = val.lower()
            tipo = next((t for k, t in TIPOS_FICHA if k in v), None)
    return {"tipo": tipo, "volume": volume}


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
            "condicao": b.get("condition") or "", "ficha": ficha_dos_atributos(b.get("attributes"))}


def normalizar_loja(u):
    rep = u.get("seller_reputation") or {}
    tr = rep.get("transactions") or {}
    end = u.get("address") or {}
    desde = u.get("registration_date")
    dias = _dias_desde(desde) if desde else None
    return {"id": u.get("id"), "nome": u.get("nickname") or "", "link": re.sub(r"^http://", "https://", u.get("permalink") or ""),
            "cidade": end.get("city") or "", "uf": _uf(end.get("state")), "nivel": _nivel(rep.get("level_id")),
            "cor": rep.get("level_id") or "", "medalha": MEDALHAS.get(rep.get("power_seller_status") or "", ""),
            "vendas": tr.get("total"), "concluidas": tr.get("completed"), "canceladas": tr.get("canceled"), "desde": desde,
            # 29/09 (print: Hunter 25.957 x nubi 26.173 na ESSENCEPRIMEBR): vendas sem as canceladas, como o Hunter mostra
            "vendas_ok": tr.get("completed") if tr.get("completed") is not None else
            (tr.get("total") - tr.get("canceled") if tr.get("total") is not None and tr.get("canceled") is not None else None),
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


def categoria_pelo_titulo(titulo):
    """01/10: categoria que o ML sugere para o título (preditor público /domain_discovery), para a tarifa antes de
    a página do anúncio ser lida. None quando o ML não responde."""
    try:
        r = _get(f"/sites/{SITE}/domain_discovery/search", {"q": str(titulo)[:120], "limit": 1})
    except ErroLogin:
        raise
    except ErroMeli:
        return None
    x = r[0] if isinstance(r, list) and r else {}
    return x.get("category_id") or None


def _minha_conta_dados():
    u = _mem("conta|me", 3600, lambda: _get("/users/me") or {})
    return u if isinstance(u, dict) else {}


def _minha_conta():
    """Nº da conta do ML conectada (a do Bruno); None sem a conta."""
    return _minha_conta_dados().get("id")


def preco_de_venda(mlb):
    """01/10 (Bruno: "meu anúncio está a 259 e mostrou 275,99"): o preço que o comprador paga agora (com a promoção), por
    /items/{id}/sale_price; o `price` do item às vezes é o cheio. None se o ML não responder."""
    try:
        r = _get(f"/items/{mlb}/sale_price", {"context": "channel_marketplace"}) or {}
    except ErroMeli:
        return None
    return _num(r.get("amount"))


def _medida(v, unidade):
    """'12 cm' / '0,5 kg' / '500 g' -> número na unidade pedida (cm ou g)."""
    m = re.match(r"\s*([\d.,]+)\s*([a-zA-Z]*)", str(v or ""))
    if not m:
        return None
    n = float(m.group(1).replace(",", ".")) if m.group(1).count(",") <= 1 else None
    if n is None:
        return None
    u = m.group(2).lower()
    if unidade == "g":
        return round(n * 1000) if u == "kg" else round(n)
    return round(n * (100 if u == "m" else 0.1 if u == "mm" else 1), 1)


def dimensoes_do_item(b):
    """'AxLxC,peso' (cm e g) do anúncio: shipping.dimensions ou os atributos SELLER_PACKAGE_* / PACKAGE_*."""
    d = ((b.get("shipping") or {}).get("dimensions") or "").strip()
    if re.fullmatch(r"\d+(\.\d+)?x\d+(\.\d+)?x\d+(\.\d+)?,\d+", d):
        return d
    at = {a.get("id"): a.get("value_name") for a in b.get("attributes") or []}
    def pega(nome, un):
        return _medida(at.get(f"SELLER_PACKAGE_{nome}") or at.get(f"PACKAGE_{nome}"), un)
    a, l, c, p = pega("HEIGHT", "cm"), pega("WIDTH", "cm"), pega("LENGTH", "cm"), pega("WEIGHT", "g")
    if all(v for v in (a, l, c, p)):
        cm = lambda v: str(int(v)) if float(v).is_integer() else f"{v:.1f}"
        return f"{cm(a)}x{cm(l)}x{cm(c)},{int(p)}"
    return None


def meu_anuncio_por_sku(sku):
    """01/10 (Bruno: "pegar a minha categoria, o peso do produto, para calcular certo a tarifa e o frete"): o MEU anúncio
    do SKU na conta conectada (só leitura): categoria, tipo (Clássico/Premium), Full e as medidas do pacote."""
    uid = _minha_conta()
    if not uid or not sku:
        return None
    r = _get(f"/users/{uid}/items/search", {"seller_sku": str(sku), "limit": 10}) or {}
    for mlb in (r.get("results") or [])[:5]:
        try:
            b = _get(f"/items/{mlb}", {"include_attributes": "all"}) or {}
        except ErroMeli:
            continue
        if not b.get("category_id"):
            continue
        venda = preco_de_venda(b.get("id") or mlb)
        return {"mlb": b.get("id") or mlb, "titulo": b.get("title"), "categoria": b.get("category_id"),
                "tipo_id": b.get("listing_type_id"), "preco": venda or _num(b.get("price")),
                "preco_cheio": _num(b.get("original_price")) or (_num(b.get("price")) if venda and venda != _num(b.get("price")) else None),
                "status": b.get("status"), "link": b.get("permalink") or link_do_item(b.get("id") or mlb),
                "loja": _minha_conta_dados().get("nickname"),
                "full": (b.get("shipping") or {}).get("logistic_type") == "fulfillment", "dimensoes": dimensoes_do_item(b),
                "gtin": next((m.group(0) for a in b.get("attributes") or [] if a.get("id") == "GTIN"
                              for m in [re.search(r"\d{8,14}", str(a.get("value_name") or ""))] if m), None)}
    return None


def frete_por_medidas(dimensoes, preco, tipo_id="gold_special", full=False):
    """Frete grátis que o ML cobra da MINHA conta para um pacote 'AxLxC,peso' (cm, g) vendido a `preco`."""
    uid = _minha_conta()
    if not uid or not dimensoes:
        return None
    r = _get(f"/users/{uid}/shipping_options/free", {"dimensions": dimensoes, "item_price": round(float(preco), 2),
                                                      "listing_type_id": tipo_id or "gold_special", "mode": "me2",
                                                      "condition": "new", "logistic_type": "fulfillment" if full else "drop_off",
                                                      "verbose": "true"}) or {}
    return _num((((r.get("coverage") or {}).get("all_country") or {}).get("list_cost")))


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


def ficha_do_catalogo(pid):
    """Tipo e volume do produto de catálogo do ML (características) + nome."""
    def ler():
        try:
            p = _get(f"/products/{pid}") or {}
        except ErroLogin:
            raise
        except ErroMeli:
            return {}
        return dict(ficha_dos_atributos(p.get("attributes")), nome=p.get("name") or "")
    return _mem("ficha|" + pid, 6 * 3600, ler)


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
                "link": p.get("permalink") or "", "criado": str(p.get("date_created") or "")[:10] or None}
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


def data_pelo_mlb(mlb, calib):
    """
    29/09: o ML não dá a data de criação do anúncio de outra loja ao app (/items 403), mas o nº do MLB cresce com o
    tempo, em SEQUÊNCIAS separadas (nos anúncios do Bruno: 45xx–50xx de mar a ago/2026 e 61xx–73xx de jan a jul/2026).
    calib: [(nº, data)] dos anúncios do Bruno (MLB do UpSeller x "Data de criação" do Explorador). Estima só entre dois
    pontos vizinhos da mesma sequência (data subindo, até 90 dias) ou até 60 dias depois do maior nº de todos.
    Devolve (data estimada, folga em dias) ou (None, None).
    """
    try:
        n = int(re.sub(r"\D", "", str(mlb or "")))
    except ValueError:
        return None, None
    pts = sorted(calib or [])
    if len(pts) < 2 or not n:
        return None, None
    import bisect
    i = bisect.bisect_left([p[0] for p in pts], n)
    if i < len(pts) and pts[i][0] == n:
        return pts[i][1], 1.0
    if 0 < i < len(pts):
        (n0, d0), (n1, d1) = pts[i - 1], pts[i]
        gap = (d1 - d0).days
        if gap < 0 or gap > 90 or n1 == n0:
            return None, None                   # troca de sequência ou buraco grande: não dá para saber
        return d0 + timedelta(days=round(gap * (n - n0) / (n1 - n0))), 2.0 + 0.04 * gap
    if i == len(pts):                           # depois do maior nº: segue o ritmo do último trecho (≥ 20 dias)
        (n1, d1) = pts[-1]
        ant = next(((m, d) for m, d in reversed(pts[:-1]) if 20 <= (d1 - d).days <= 120), None)
        if ant and n1 > ant[0]:
            por_dia = (n1 - ant[0]) / (d1 - ant[1]).days
            dias = (n - n1) / por_dia
            if dias <= 60:
                return d1 + timedelta(days=round(dias)), 3.0 + 0.15 * dias
    return None, None


def _data_br(txt):
    """'16-07-2026' (Explorador) -> date."""
    m = re.fullmatch(r"(\d{2})[-/](\d{2})[-/](\d{4})", str(txt or "").strip())
    if not m:
        return None
    try:
        return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date()
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
            "dias_pub": dl, "data_ref": d, "peso": un if un and un == un else 0.0,
            "criado": _data(l.get("criado")) or _data_br(l.get("criado"))}


def casar(refs, ofertas, calib=None, oficiais=None):
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
                        # 29/09 (🔌 em produção): o nº "LOJA.OFICIAL" do Nubimetrics NÃO é o official_store_id do ML
                        # (WATHIQ 25357 x 361164). Vale: ser ou não loja oficial; e o nº traduzido pelo que o Bruno confirmou
                        lo_o = int(o.get("loja_oficial") or 0)
                        if bool(lo_o) != bool(lo_r):
                            continue
                        alvo = (oficiais or {}).get(int(lo_r)) if lo_r else None
                        if alvo:
                            if lo_o != int(alvo):
                                continue
                            oficial = int(lo_r)
                    idade_ok = False
                    criado = _data(o.get("criado_em"))
                    if dl is not None and dref and criado:            # só quando o ML dá o anúncio (hoje não dá ao app)
                        idade = (dref - criado).days
                        if abs(idade - int(dl)) > 3:
                            continue
                        idade_ok = abs(idade - int(dl)) <= 1
                    elif r.get("criado") and calib:                   # data estimada pelo nº do MLB (calibrada)
                        est, folga = data_pelo_mlb(o.get("anuncio"), calib)
                        idade_ok = bool(est and abs((est - r["criado"]).days) <= folga)
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
    if c1["idade"] >= 2 and not any(c["idade"] >= 2 for c in outros):
        return "certa"                          # a data de criação bate em 2+ anúncios dele (pelo nº do MLB)
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
        p.append(f"data de criação batendo em {c['idade']}")
    if c.get("nome_bate"):
        p.append("nome parecido")
    return "; ".join(p) + "; Full e tipo iguais"


def casar_vendedores(linhas, ml, data_ref=None, calib=None, oficiais=None):
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
        cands, sondados = casar(refs, ml, calib, oficiais)
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


def achar_loja(nome, refs, ofertas, un_mes=None, calib=None, oficiais=None):
    """
    Vendedor do Nubimetrics (refs do Explorador + do relatório do seguido) x ofertas do catálogo -> (loja escolhida ou
    None, candidatas). nome: o que o Bruno deu ao seguido ("ICARBONXX P3"); é rótulo dele, então só desempata.
    un_mes: unidades dele no mês no Nubimetrics. Trava (ideia do Cowork, 29/09): loja com menos vendas NA VIDA do que
    metade disso não pode ser ele (a LUH… que entrou errado no ICARBONXX tinha 230 vendas; ele vende 25 mil/mês).
    A escolhida traz os anúncios dela achados no catálogo (ID, link, preço de agora).
    """
    cands, sondados = casar(refs, ofertas, calib, oficiais)
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
    # 29/09 (ROCHA IMPORTADOS -> OUD_ESSENCE, errado): no Explorador todos os anúncios dele são da loja oficial 14017 e a
    # OUD_ESSENCE casou só pelo relatório do mês (4 de 8 produtos, preço perto). Vendedor de loja oficial só vira
    # "provável" sem a loja oficial batendo se o nome ou a data de criação baterem; senão, candidatas para o Bruno.
    if (conf == "provável" and any(r.get("loja_oficial") for r in refs) and cands and not cands[0]["oficial"]
            and not cands[0].get("nome_bate") and not cands[0]["idade"]):
        conf = None
    mostrar = [{"id": c["id"], "nome": c.get("nome") or "", "link": c.get("link") or "", "produtos": c["produtos"],
                "sondados": sondados, "exato": c["exato"], "perto": c["perto"], "idade": c["idade"], "oficial": c["oficial"],
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
         "preco_bate": c["exato"] + c["perto"], "exato": c["exato"], "idade": c["idade"], "oficial": c["oficial"], "nome_bate": c["nome_bate"],
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
    if x.get("code") != 200:                             # 30/09: 403 aparecia com ✅
        raise ErroMeli(f"código {x.get('code')}: " + str(b.get("message") or b.get("error") or "sem o anúncio")[:90])
    return b.get("title") or "sem título"


def _diag_meus():
    # o ML não aceita "me" nesse caminho (400 Invalid user_id): vai o nº da conta
    uid = (_get("/users/me") or {}).get("id")
    r = _get(f"/users/{uid}/items/search", {"limit": 1}) or {}
    return f"{(r.get('paging') or {}).get('total', 0)} anúncio(s)"


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
    # 29/09: com a conta conectada o /items continuou 403: estes mostram o que a conta enxerga e onde o ML bloqueia
    if _token_usuario():
        passo("conta: quem sou (/users/me)", lambda: (lambda u: f"{u.get('nickname')} ({u.get('id')}), {u.get('site_id')}")(_get("/users/me") or {}))
        # o ML não aceita "me" nesse caminho (400 Invalid user_id): vai o nº da conta
        passo("conta: anúncios da própria conta (/users/ID/items/search)", _diag_meus)
        passo("busca por palavra (/sites/MLB/search?q=)", lambda: f"{((_get(f'/sites/{SITE}/search', {'q': 'perfume', 'limit': 1}) or {}).get('paging') or {}).get('total')} resultados")
        passo("descrição do anúncio (/items/ID/description)", lambda: f"{len(str((_get(f'/items/{mlb}/description') or {}).get('plain_text') or ''))} letras")
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


def testar_marca(marca="armaf", max_produtos=1000, sondar=40):
    """02/10 (Bruno: "pela API do ML dá para trazer todos os itens da marca, vendidos por dia e todos os vendedores? Aí a
    gente exporta do ML em vez do Nubimetrics"). Só LEITURA: tenta cada caminho e conta o que vem (nunca token)."""
    passos, achado = [], {"marca": marca}

    def passo(nome, f):
        t = time.time()
        try:
            r = f()
            passos.append({"passo": nome, "ok": True, "ms": int((time.time() - t) * 1000), "detalhe": r})
            return r
        except ErroMeli as e:
            passos.append({"passo": nome, "ok": False, "ms": int((time.time() - t) * 1000), "detalhe": str(e)})
            return None
    if not tem_chave():
        return {"chaves": False, "passos": [{"passo": "chaves", "ok": False, "detalhe": FALTA_CHAVE}]}
    passo("token em uso", lambda: token_em_uso())
    # 1. busca de anúncios (o que o Nubimetrics usa): todos os anúncios da marca, com vendedor e vendidos
    passo("busca de anúncios por palavra (/sites/MLB/search?q=)",
          lambda: f"{((_get(f'/sites/{SITE}/search', {'q': marca, 'limit': 1}) or {}).get('paging') or {}).get('total')} anúncios")
    passo("busca de anúncios na categoria Perfumes (/sites/MLB/search?category=MLB6284&q=)",
          lambda: f"{((_get(f'/sites/{SITE}/search', {'q': marca, 'category': 'MLB6284', 'limit': 1}) or {}).get('paging') or {}).get('total')} anúncios")
    # 2. produtos de catálogo da marca
    prods = []

    def catalogo():
        off, total = 0, None
        while off < max_produtos:
            r = _get("/products/search", {"status": "active", "site_id": SITE, "q": marca, "limit": 50, "offset": off}) or {}
            xs = r.get("results") or []
            total = (r.get("paging") or {}).get("total", total)
            prods.extend({"id": p.get("id"), "nome": p.get("name"),
                          "marca": next((a.get("value_name") for a in p.get("attributes") or [] if a.get("id") == "BRAND"), "")}
                         for p in xs if p.get("id"))
            if len(xs) < 50:
                break
            off += 50
        da_marca = [p for p in prods if marca.lower() in f"{p['marca']} {p['nome']}".lower()]
        achado["produtos"] = len(prods)
        achado["produtos_da_marca"] = len(da_marca)
        achado["exemplos_produtos"] = [p["nome"] for p in da_marca[:8]]
        return f"{total} no total; li {len(prods)}; {len(da_marca)} com a marca no nome/atributo"
    passo("produtos de catálogo da marca (/products/search?q=)", catalogo)
    # 3. ofertas (anúncios) de cada produto: vendedor, preço, Full… e vendidos?
    ofertas, campos = [], set()

    def ofs():
        alvo = [p for p in prods if marca.lower() in f"{p['marca']} {p['nome']}".lower()][:sondar]
        for p, xs in zip(alvo, _em_paralelo(lambda p: ofertas_do_produto(p["id"], 300), alvo, 4)):
            for x in xs or []:
                campos.update(x.keys())
                ofertas.append({"pid": p["id"], "item": x.get("item_id"), "vendedor": x.get("seller_id"),
                                "sold": x.get("sold_quantity"), "preco": x.get("price")})
        vend = {o["vendedor"] for o in ofertas if o["vendedor"]}
        com_sold = sum(1 for o in ofertas if o["sold"] is not None)
        achado.update(ofertas=len(ofertas), vendedores=len(vend), ofertas_com_vendidos=com_sold, campos_da_oferta=sorted(campos))
        return (f"{len(alvo)} produtos sondados: {len(ofertas)} anúncios de catálogo, {len(vend)} vendedores; "
                f"{com_sold} com 'vendidos'; campos: {', '.join(sorted(campos))[:300]}")
    passo("anúncios de cada produto (/products/ID/items)", ofs)
    # 4. dados do anúncio de outra loja (vendidos, data de criação)
    mlb = next((o["item"] for o in ofertas if o["item"]), None)
    if mlb:
        passo("anúncio de outra loja (/items/ID)", lambda: (lambda b: f"vendidos={b.get('sold_quantity')} criado={b.get('date_created')}")(_get(f"/items/{mlb}") or {}))
        passo("vários anúncios (/items?ids=)", lambda: _diag_varios(mlb))
        passo("visitas do anúncio (/items/visits)", lambda: visitas([mlb]).get(mlb))
        sid = next((o["vendedor"] for o in ofertas if o["item"] == mlb), None)
        if sid:
            passo("vitrine da loja pela API (/sites/MLB/search?seller_id=)",
                  lambda: (_get(f"/sites/{SITE}/search", {"seller_id": sid, "limit": 1}) or {}).get("paging", {}).get("total"))
            passo("perfil da loja (/users/ID)", lambda: (lambda u: f"{u.get('nickname')} · vendas na vida {((u.get('seller_reputation') or {}).get('transactions') or {}).get('total')}")(_get(f"/users/{sid}") or {}))
    # 5. ranking de mais vendidos da categoria (posição, sem número de vendas)
    def destaques():
        r = _get(f"/highlights/{SITE}/category/MLB6284") or {}
        cont = r.get("content") or []
        return f"{len(cont)} itens no ranking de mais vendidos (tipos: {sorted({c.get('type') for c in cont})})"
    passo("mais vendidos da categoria Perfumes (/highlights)", destaques)
    pid = next((p["id"] for p in prods if marca.lower() in f"{p['marca']} {p['nome']}".lower()), None)
    if pid:
        passo("ficha do produto (/products/ID): tem vendidos?",
              lambda: (lambda b: f"campos: {', '.join(sorted(b.keys()))[:250]}; buy_box={sorted((b.get('buy_box_winner') or {}).keys())[:20]}")(_get(f"/products/{pid}") or {}))
    return {"chaves": True, "passos": passos, "achado": achado}


# ---------------------------------------------------------------------------
# Extensão do Chrome (29/09, pedido do Bruno: "as mesmas funções do painel do Hunter"). A extensão lê a página do anúncio
# (vendedor, categoria, tipo, preço, produto de catálogo) e pede aqui só o que é dado PÚBLICO do ML com o token do app:
# comissão, frete, visitas, concorrentes do catálogo com a loja real, tendências. Nada do nubi, nada do Bruno.

EXT_TIPOS = ("gold_special", "gold_pro")
EXT_POR_MINUTO = 90                      # pedidos novos (sem cache) por minuto nesta instância: rota sem login
_EXT_CONTA = {"min": 0, "n": 0}
EXT_COLETA_POR_MINUTO = 30               # coletas da extensão gravadas por minuto (rota sem login que grava no banco)
_EXT_COLETA = {"min": 0, "n": 0}


def _ext_limite(conta=_EXT_CONTA, teto=None):
    m = int(time.time() // 60)
    if conta["min"] != m:
        conta.update(min=m, n=0)
    conta["n"] += 1
    if conta["n"] > (EXT_POR_MINUTO if teto is None else teto):
        raise ErroMeli("muitos pedidos agora; tente em 1 minuto")


def ext_parametros(q):
    """Confere tudo que vem da extensão (rota sem login): só códigos do ML e números."""
    def cod(k, pad):
        v = str(q.get(k) or "").strip().upper().replace("-", "")
        return v if re.fullmatch(pad, v) else None
    try:
        preco = float(str(q.get("preco") or "").replace(",", "."))
        preco = preco if 0 < preco < 1e6 else None
    except ValueError:
        preco = None
    tipo = str(q.get("tipo") or "")
    return {"mlb": cod("mlb", r"MLB\d{6,14}"), "pid": cod("pid", r"MLB\d{5,14}"), "vendedor": cod("vendedor", r"\d{3,14}"),
            "categoria": cod("categoria", r"MLB\d{1,9}"), "tipo": tipo if tipo in TIPOS else None, "preco": preco}


def ext_coleta(q):
    """Card #121: o que a extensão leu da página do anúncio que o Bruno abriu -> o registro do anúncio. Só código do ML,
    números e fotos do mlstatic; o que a página não trouxe fica None ("sem dados"), nunca zero nem chute."""
    p = ext_parametros(q)
    if not (p["mlb"] and p["vendedor"]):
        raise ErroMeli("informe o anúncio e o vendedor")
    nome = re.sub(r"[<>\x00-\x1f]", "", str(q.get("loja") or "")).strip()[:80] or None
    try:
        vend = int(str(q.get("vendidos") or ""))
        vend = vend if 0 <= vend < 10 ** 9 else None
    except ValueError:
        vend = None
    full = {"1": True, "true": True, "0": False, "false": False}.get(str(q.get("full") or "").lower())
    fotos = [f for f in dict.fromkeys(str(q.get("fotos") or "").split(","))
             if re.fullmatch(r"https://http2\.mlstatic\.com/[\w\-.]{5,200}", f)][:12]
    reg = {"mlb": p["mlb"], "vendedor": p["vendedor"], "loja": nome, "preco": p["preco"], "fotos": fotos or None,
           "vendidos": vend, "vendidos_faixa": None if vend is None else vend in FAIXAS_VENDIDOS, "full": full}
    reg["sem_dados"] = [k for k, v in reg.items() if v is None]
    return reg


def _ext_tenta(f, *a):
    try:
        return f(*a)
    except ErroLogin:
        raise
    except ErroMeli:
        return None


def painel_extensao(p, calib=None, max_concorrentes=200):
    """Tudo que a extensão mostra além da página: {loja, tarifas{tipo: {pct, fixa, total}}, frete, visitas{anuncio, catalogo,
    parte}, concorrentes[], total_concorrentes, criado_estimado}. Cada parte que o ML recusar fica vazia."""
    chave = "ext|" + "|".join(str(p.get(k) or "") for k in ("mlb", "pid", "vendedor", "categoria", "tipo", "preco"))
    if chave in _CACHE and time.time() - _CACHE[chave][0] < 1800:
        return _CACHE[chave][1]
    _ext_limite()
    out = {"loja": None, "tarifas": {}, "frete": None, "visitas": {}, "concorrentes": [], "total_concorrentes": None,
           "criado_estimado": None}
    mlb, pid, vend, preco = p.get("mlb"), p.get("pid"), p.get("vendedor"), p.get("preco")
    if vend:
        out["loja"] = (_ext_tenta(lojas, [vend]) or {}).get(vend)
    if preco and p.get("categoria"):
        for t in EXT_TIPOS:
            tf = _ext_tenta(tarifa, preco, p["categoria"], t)
            if tf:
                out["tarifas"][t] = tf
    if vend and mlb and preco and preco >= 79:
        out["frete"] = _ext_tenta(frete_do_vendedor, vend, mlb)
    ofs = []
    if pid:
        ofs = [_oferta(pid, None, x) for x in (_ext_tenta(ofertas_do_produto, pid, max_concorrentes) or [])]
        out["total_concorrentes"] = TOTAL_OFERTAS.get(pid, len(ofs))
        lj = _ext_tenta(lojas, [o["vendedor_id"] for o in sorted(ofs, key=lambda o: o["preco"] or 9e9)[:60]]) or {}
        out["concorrentes"] = [dict({k: o[k] for k in ("anuncio", "link", "vendedor_id", "preco", "preco_cheio", "full",
                                                       "frete_gratis", "tipo", "loja_oficial")},
                                    loja=(lj.get(str(o["vendedor_id"])) or {}).get("nome"),
                                    loja_link=(lj.get(str(o["vendedor_id"])) or {}).get("link"),
                                    vendas_loja=(lj.get(str(o["vendedor_id"])) or {}).get("vendas"),
                                    eu=o["anuncio"] == mlb)
                               for o in sorted(ofs, key=lambda o: o["preco"] or 9e9)]
    ids = [x for x in dict.fromkeys(([mlb] if mlb else []) + [o["anuncio"] for o in ofs][:50]) if x]
    vis = (_ext_tenta(visitas, ids) or {}) if ids else {}
    if mlb and mlb in vis:
        out["visitas"]["anuncio"] = vis[mlb]
    if ofs:
        cat = sum(v for k, v in vis.items() if k in {o["anuncio"] for o in ofs})
        out["visitas"]["catalogo"] = cat
        out["visitas"]["catalogo_lidos"] = sum(1 for o in ofs[:50] if o["anuncio"] in vis)
        if mlb in vis and cat:
            out["visitas"]["parte"] = round(100 * vis[mlb] / cat)
    if mlb:
        # com a conta do ML conectada, /items libera: data de criação, vendidos e estoque DE VERDADE
        it = ((_ext_tenta(itens, [mlb]) or {}).get(mlb) or {})
        if it and not it.get("bloqueado") and not it.get("sumiu"):
            out["item"] = {k: it.get(k) for k in ("criado_em", "vendidos", "disponivel", "vendedor_id", "tipo_id", "categoria",
                                                   "produto_catalogo", "full")}
        out["historico"] = _ext_tenta(historico_visitas, mlb) or {}
    if mlb and calib and not (out.get("historico") or {}).get("primeira_visita"):
        d, folga = data_pelo_mlb(mlb, calib)
        if d:
            out["criado_estimado"] = {"data": d.isoformat(), "folga_dias": round(folga)}
    _CACHE[chave] = (time.time(), out)
    return out


def historico_visitas(mlb):
    """29/09 (print do Hunter: "Tempo ativo 252 dias, desde 19/01/2026", "19.651 visitas no total"): o ML não dá ao app a
    data de criação de anúncio de outra loja (/items 403), mas dá as visitas. O 1º dia com visita ≈ o dia em que o anúncio
    entrou no ar; o total desde então = visitas na vida. Produção 29/09: a janela por dia vai até 150 dias; anúncio mais
    velho tenta a janela por semana. {primeira_visita, precisao, total, dias_lidos} ou {"mais_velho_que": data}."""
    def janela(unid, n):
        try:
            r = _get(f"/items/{mlb}/visits/time_window", {"last": n, "unit": unid}) or {}
        except ErroLogin:
            raise
        except ErroMeli:
            return None
        xs = sorted((str(x.get("date") or "")[:10], int(x.get("total") or 0)) for x in r.get("results") or [])
        return xs or None

    def ler():
        hoje = datetime.now(timezone.utc).date()
        out = {}
        for unid, n in (("day", 150), ("day", 90), ("week", 104), ("week", 52), ("month", 36), ("month", 24)):
            if out.get("primeira_visita") or (unid == "day" and out.get("dias_lidos")):
                continue
            xs = janela(unid, n)
            if not xs:
                continue
            com = [d for d, q in xs if q > 0]
            if unid == "day":
                out.update(dias_lidos=n, total_janela=sum(q for _, q in xs))
            if com and (com[0] > xs[0][0] or (unid == "day" and xs[0][0] > (hoje - timedelta(days=n - 5)).isoformat())):
                out.update(primeira_visita=com[0], precisao={"day": "dia", "week": "semana", "month": "mês"}[unid])
                out.pop("mais_velho_que", None)
            elif not out.get("mais_velho_que") or xs[0][0] < out["mais_velho_que"]:
                out["mais_velho_que"] = xs[0][0]
        # visitas na vida: da entrada (ou do mais antigo possível) até hoje; o ML pode limitar o período
        de0 = out.get("primeira_visita")
        for de in ([de0] if de0 else []) + [(hoje - timedelta(days=d)).isoformat() for d in (3 * 365, 730, 365)]:
            try:
                t = _get("/items/visits", {"ids": mlb, "date_from": f"{de}T00:00:00.000-00:00",
                                            "date_to": f"{hoje.isoformat()}T23:59:59.000-00:00"})
            except ErroLogin:
                raise
            except ErroMeli:
                continue
            t = t[0] if isinstance(t, list) and t else t
            if isinstance(t, dict) and t.get("total_visits") is not None:
                out.update(total=int(t["total_visits"]), total_desde=de)
                break
        return out
    return _mem("ext|hist|" + mlb, 6 * 3600, ler)


def ext_categorias():
    return _mem("ext|categorias", 86400, lambda: [{"id": c.get("id"), "nome": c.get("name")}
                                                  for c in (_get(f"/sites/{SITE}/categories") or [])])


def ext_tendencias(categoria=None):
    cat = categoria if categoria and re.fullmatch(r"MLB\d{1,9}", categoria) else None

    def ler():
        _ext_limite()
        r = _get(f"/trends/{SITE}" + (f"/{cat}" if cat else "")) or []
        return [{"termo": x.get("keyword"), "link": re.sub(r"^http://", "https://", x.get("url") or "")} for x in r if x.get("keyword")]
    return _mem(f"ext|tend|{cat or ''}", 3 * 3600, ler)


def _vendedor_do_anuncio(item, pid):
    """29/09 (página real da busca: o vendedor NÃO vem nela; vem o produto de cada anúncio em "printed_result"):
    MLBP<n> = produto de catálogo MLB<n> -> o anúncio entre as ofertas dele; MLBU<n> = produto do vendedor -> /user-products.
    Devolve (seller_id, dados da oferta) ou (None, {})."""
    pid = str(pid or "").upper()
    try:
        if pid.startswith("MLBP"):
            of = next((x for x in ofertas_do_produto("MLB" + pid[4:], 400) if x.get("item_id") == item), None)
            if of and of.get("seller_id"):
                sh = of.get("shipping") or {}
                return str(of["seller_id"]), {"preco": _num(of.get("price")), "full": sh.get("logistic_type") == "fulfillment",
                                              "tipo": TIPOS.get(of.get("listing_type_id"), ""), "oficial": of.get("official_store_id")}
        motivo = []
        if pid.startswith("MLBU"):
            try:
                u = _get(f"/user-products/{pid}") or {}
            except (NaoAchou, ErroMeli) as e:
                u = {}
                motivo.append("produto do vendedor: " + str(e)[:40])
            if u.get("user_id"):
                return str(u["user_id"]), {}
        # sem catálogo: as perguntas do anúncio trazem o vendedor (API pública de perguntas)
        q = _get("/questions/search", {"item": item, "limit": 1}) or {}
        sid = next((x.get("seller_id") for x in q.get("questions") or [] if x.get("seller_id")), None) or q.get("seller_id")
        if sid:
            return str(sid), {}
        motivo.append("sem perguntas no anúncio")
        return None, {"motivo": "o ML não libera o vendedor deste anúncio para o nosso app"}
    except ErroLogin:
        raise
    except ErroMeli:
        pass
    return None, {}


def _primeira_visita(mlb):
    """30/09 (print lado a lado com o Hunter: anúncios NOVOS saíam sem data): o 1º dia com visita nos últimos 150 dias =
    o dia em que o anúncio entrou no ar (1 pedido). Mais velho que 150 dias: None (fica a estimativa pelo nº do MLB)."""
    try:
        r = _get(f"/items/{mlb}/visits/time_window", {"last": 150, "unit": "day"}) or {}
    except ErroLogin:
        raise
    except ErroMeli:
        return None
    xs = sorted((str(x.get("date") or "")[:10], int(x.get("total") or 0)) for x in r.get("results") or [])
    com = [d for d, q in xs if q > 0]
    if not com or not xs:
        return None
    # 30/09 (ARENA_INFO, 14 dias no Hunter, saiu "—"): em anúncio novo o ML devolve a janela só desde a criação (sem os
    # dias zerados antes); janela que começa bem depois de 150 dias atrás = começa na criação
    # (anúncio de 212 dias no Hunter saiu com 143 pela 1ª visita: sem visita nos primeiros dias da janela; só confia na
    # janela "cortada" quando ela começa nos últimos 120 dias)
    corte = (datetime.now(timezone.utc).date() - timedelta(days=120)).isoformat()
    return com[0] if com[0] > xs[0][0] or xs[0][0] > corte else None


def ext_lista(mlbs, calib=None):
    """Busca do ML na extensão (29/09, prints do Hunter): para até 60 anúncios da página ("MLB" ou "MLB:pid", pid = o
    MLBP/MLBU que a página traz), as visitas dos últimos 30 dias (1 pedido para 50), a data de criação estimada pelo nº do
    MLB e o VENDEDOR com o perfil da loja (nome, cidade, reputação, medalha). Cache de 30 min por anúncio."""
    pares = []
    for x in mlbs or []:
        it, _, pid = str(x).strip().upper().partition(":")
        if re.fullmatch(r"MLB\d{6,14}", it) and (not pid or re.fullmatch(r"MLB[PU]\d{5,14}", pid)):
            pares.append((it, pid))
    pares = list(dict.fromkeys(pares))[:60]
    ids = list(dict.fromkeys(it for it, _ in pares))
    novo = lambda k: k not in _CACHE or time.time() - _CACHE[k][0] > 1800
    falta = [m for m in ids if novo(f"ext|vis30|{m}")]
    falta_v = [(it, pid) for it, pid in pares if pid and novo(f"ext|vend|{it}")]
    if falta or falta_v:
        _ext_limite()
    if falta:
        try:
            vs = visitas(falta, 30)
        except ErroLogin:
            raise
        except ErroMeli:
            vs = {}
        for m in falta:
            _CACHE[f"ext|vis30|{m}"] = (time.time(), vs.get(m))
    if falta_v:
        for (it, _), r in _em_paralelo(lambda c: (c, _vendedor_do_anuncio(*c)), falta_v):
            _CACHE[f"ext|vend|{it}"] = (time.time(), r)
    # data de entrada pela 1ª visita (a data não muda: cache de 1 dia)
    falta_d = [m for m in ids if f"ext|entrou|{m}" not in _CACHE or time.time() - _CACHE[f"ext|entrou|{m}"][0] > 86400]
    if falta_d:
        for m, d in _em_paralelo(lambda m: (m, _primeira_visita(m)), falta_d, n=10):
            _CACHE[f"ext|entrou|{m}"] = (time.time(), d)
    # 30/09 (Hunter mostra "Catálogo criado"): a data do produto de catálogo (MLBP) vem de /products (6 h de cache)
    cat = dict(_em_paralelo(lambda c: (c[0], (_produto_catalogo("MLB" + c[1][4:]) or {}).get("criado")),
                            [(it, pid) for it, pid in pares if pid.startswith("MLBP")], n=10))
    vend = {it: (_CACHE.get(f"ext|vend|{it}") or (0, (None, {})))[1] for it in ids}
    lj = lojas([v[0] for v in vend.values() if v and v[0]])
    out = {}
    for m in ids:
        d, folga = data_pelo_mlb(m, calib) if calib else (None, None)
        entrou = (_CACHE.get(f"ext|entrou|{m}") or (0, None))[1]
        sid, extra = vend.get(m) or (None, {})
        out[m] = {"visitas30": (_CACHE.get(f"ext|vis30|{m}") or (0, None))[1],
                  "criado": entrou or (d.isoformat() if d else None), "criado_por": "1ª visita" if entrou else "nº do anúncio" if d else None,
                  "folga": None if entrou else round(folga) if folga else None,
                  "catalogo_criado": cat.get(m), "vendedor": sid, "loja": lj.get(sid) if sid else None, **(extra or {})}
    return out


def ext_vencedores(pares):
    """Busca do ML na extensão (29/09, print do Bruno: "não achei a loja" em todos os cards): cada card de catálogo
    (/p/MLB…, com o anúncio do card em "wid" quando o link traz) -> o vendedor DESSE anúncio entre as ofertas do produto;
    sem o anúncio, quem ganha o produto agora (buy box). {"pid" ou "pid:item": {item, vendedor, preco, full, tipo, loja}}."""
    ok = []
    for x in pares or []:
        pid, _, it = str(x).upper().partition(":")
        if re.fullmatch(r"MLB\d{5,14}", pid) and (not it or re.fullmatch(r"MLB\d{6,14}", it)):
            ok.append((pid, it or None))
    ok = list(dict.fromkeys(ok))[:60]
    chave = lambda pid, it: f"ext|venc|{pid}|{it or ''}"
    if any(chave(*c) not in _CACHE or time.time() - _CACHE[chave(*c)][0] > 1800 for c in ok):
        _ext_limite()

    def um(c):
        pid, it = c

        def ler():
            try:
                bw = None
                if it:
                    bw = next((x for x in ofertas_do_produto(pid, 200) if x.get("item_id") == it), None)
                if not bw:
                    bw = (_get(f"/products/{pid}") or {}).get("buy_box_winner") or {}
                if not bw.get("seller_id"):
                    bw = ((_get(f"/products/{pid}/items", {"limit": 1}) or {}).get("results") or [{}])[0]
            except ErroLogin:
                raise
            except ErroMeli:
                return None
            if not bw.get("seller_id"):
                return None
            sh = bw.get("shipping") or {}
            return {"item": bw.get("item_id"), "vendedor": str(bw["seller_id"]), "preco": _num(bw.get("price")),
                    "full": sh.get("logistic_type") == "fulfillment", "tipo": TIPOS.get(bw.get("listing_type_id"), ""),
                    "oficial": bw.get("official_store_id"), "do_card": bool(it and bw.get("item_id") == it)}
        return (f"{pid}:{it}" if it else pid), _mem(chave(pid, it), 1800, ler)
    pids = ok
    out = {p: v for p, v in _em_paralelo(um, pids) if v}
    lj = lojas([v["vendedor"] for v in out.values()]) if out else {}
    for v in out.values():
        v["loja"] = lj.get(v["vendedor"])
    return out


# ---------------------------------------------------------------------------
# Comparar vendas Nubimetrics x API do ML (29/09, pedido do Bruno: "se descobrirmos como o Nubimetrics extrai, podemos extrair
# direto do ML — mas tem que bater os números; testes separados antes"). O ML não dá as vendas por dia de outra loja; dá o
# TOTAL vendido de cada anúncio. Uma foto por dia de todos os anúncios da loja; a diferença de um dia para o outro = as
# vendas do dia pelo ML. Precisa da conta do ML conectada (a busca por loja dá 403 para o app).
FAIXAS_VENDIDOS = {25, 50, 100, 150, 200, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000}


def foto_da_loja(sid, limite=1000):
    """{total, itens: {MLB: {v: vendidos, d: disponível, p: preço, g: GTIN, t: título, s: status, f: Full}}, bloqueados}."""
    try:
        primeiro = _get(f"/sites/{SITE}/search", {"seller_id": sid, "offset": 0, "limit": 50}) or {}
    except Bloqueado:
        raise ErroMeli("a busca por loja está bloqueada para o app: conecte a conta do Mercado Livre no nubi (🔐)")
    total = int((primeiro.get("paging") or {}).get("total") or 0)
    ids = [r.get("id") for r in primeiro.get("results") or []]
    offs = list(range(50, min(total, limite), 50))
    for r in _em_paralelo(lambda o: _get(f"/sites/{SITE}/search", {"seller_id": sid, "offset": o, "limit": 50}) or {}, offs, 4):
        ids += [x.get("id") for x in r.get("results") or []]
    ids = [str(i).upper() for i in dict.fromkeys(ids) if i][:limite]
    its = itens(ids)
    out, bloq = {}, 0
    for i in ids:
        m = its.get(i) or {}
        if m.get("bloqueado"):
            bloq += 1
            continue
        if m.get("sumiu"):
            continue
        out[i] = {"v": m.get("vendidos"), "d": m.get("disponivel"), "p": m.get("preco"), "g": m.get("gtin") or "",
                  "t": (m.get("titulo") or "")[:90], "s": m.get("status") or "", "f": bool(m.get("full"))}
    return {"total": total, "itens": out, "bloqueados": bloq}


def vendidos_em_faixa(fotos_itens):
    """Parte dos anúncios cujo 'vendidos' é número redondo de faixa (25, 50, 100…): o ML pode estar arredondando."""
    vs = [x.get("v") for x in fotos_itens.values() if isinstance(x.get("v"), int) and x.get("v") >= 25]
    return round(sum(1 for v in vs if v in FAIXAS_VENDIDOS) / len(vs), 2) if vs else None


def vendas_entre_fotos(antes, depois):
    """Vendas pelo ML entre duas fotos: soma do que o 'vendidos' de cada anúncio subiu (só anúncios nas duas fotos).
    Devolve {un, por_anuncio{MLB: un}, novos, sumiram, desceu} — 'desceu' = anúncios cujo vendido diminuiu (ML recontou)."""
    a, d = antes.get("itens") or {}, depois.get("itens") or {}
    por, desceu = {}, 0
    for i, x in d.items():
        if i in a and isinstance(x.get("v"), int) and isinstance(a[i].get("v"), int):
            dif = x["v"] - a[i]["v"]
            if dif > 0:
                por[i] = dif
            elif dif < 0:
                desceu += 1
    return {"un": sum(por.values()), "por_anuncio": por, "novos": sum(1 for i in d if i not in a),
            "sumiram": sum(1 for i in a if i not in d), "desceu": desceu}


# Card #126, etapa 2 (30/09): a vitrine da loja (lista.mercadolivre.com.br/_CustId_<seller_id>) dá TODOS os anúncios dela
# sem /items (403 ao app). O coletor abre as páginas e manda os cards (HTML) e os scripts com "printed_result" guardados no
# começo da página (o ML apaga depois); aqui cada card é lido com AS MESMAS REGRAS do doCartao da extensão (conteudo.js).
def vitrine_url(seller_id, pagina=0, por_pagina=48):
    sid = re.sub(r"\D", "", str(seller_id or ""))
    return f"https://lista.mercadolivre.com.br/_CustId_{sid}" if not pagina else \
        f"https://lista.mercadolivre.com.br/_Desde_{pagina * por_pagina + 1}_CustId_{sid}_NoIndex_True"


_VAZIOS = {"img", "br", "input", "meta", "link", "source", "hr", "wbr", "area", "col", "embed", "param", "track"}


def _arvore(html_):
    """HTML de um card -> árvore simples [tag, attrs, filhos] (texto = str), sem biblioteca de fora."""
    from html.parser import HTMLParser
    raiz = ["#", {}, []]
    pilha = [raiz]

    class P(HTMLParser):
        def handle_starttag(self, tag, attrs):
            no = [tag, {k: v or "" for k, v in attrs}, []]
            pilha[-1][2].append(no)
            if tag not in _VAZIOS:
                pilha.append(no)

        def handle_endtag(self, tag):
            for i in range(len(pilha) - 1, 0, -1):
                if pilha[i][0] == tag:
                    del pilha[i:]
                    break

        def handle_data(self, d):
            pilha[-1][2].append(d)
    p = P()
    p.feed(str(html_ or ""))
    p.close()
    return raiz


def _nos(no):
    for f in no[2]:
        if isinstance(f, list):
            yield f
            yield from _nos(f)


def _texto(no):
    return re.sub(r"\s+", " ", " ".join(f if isinstance(f, str) else _texto(f) for f in no[2]
                                        if not (isinstance(f, list) and f[0] in ("script", "style")))).strip()


def _tem_classe(no, *cls):
    cs = no[1].get("class", "").split()
    return any(c in cs for c in cls)


def _um(raiz, *cls, dentro=None):
    base = next((n for n in _nos(raiz) if _tem_classe(n, *dentro)), None) if dentro else raiz
    return next((n for n in _nos(base) if _tem_classe(n, *cls)), None) if base else None


def _preco_do_no(pr):
    fr = _um(pr, "andes-money-amount__fraction")
    ct = _um(pr, "andes-money-amount__cents")
    fr_ = re.sub(r"\D", "", _texto(fr) if fr else "")
    ct_ = re.sub(r"\D", "", _texto(ct) if ct else "") or "0"
    try:
        x = float(fr_ + "." + ct_.ljust(2, "0"))
    except ValueError:
        return None
    return x if x > 0 else None


def cartao_vitrine(html_):
    """Um card da busca/vitrine -> {mlb, link, titulo, foto, preco, full, vendidos, vendidos_mais, catalogo, apelido,
    marca}. Regras do doCartao (conteudo.js); o que o card não mostra fica None."""
    r = _arvore(html_)
    t = _texto(r)
    out = {"mlb": None, "link": "", "titulo": "", "foto": "", "preco": None, "full": False, "vendidos": None,
           "vendidos_mais": False, "catalogo": None, "apelido": "", "marca": ""}
    v = re.search(r"(\+)?\s*(\d+(?:[.,]\d+)?)\s*(mil)?\s*vendidos?", t, re.I)
    if v:
        out["vendidos"] = round(float(v.group(2).replace(".", "").replace(",", ".")) * (1000 if v.group(3) else 1))
        out["vendidos_mais"] = bool(v.group(1))
    nos = list(_nos(r))
    if any("full" in n[1].get("aria-label", "").lower() or (n[0] == "svg" and "full" in n[1].get("class", "").lower())
           or _tem_classe(n, "poly-component__shipped-from") or "fulfillment" in n[1].get("class", "") for n in nos) \
            or re.search(r"\bFULL\b", t):
        out["full"] = True
    sv = next((n for n in nos if _tem_classe(n, "poly-component__seller", "ui-search-official-store-label",
                                             "ui-search-item__group__element--seller")), None)
    nome_sv = re.sub(r"^(vendido\s+)?por\s+", "", _texto(sv), flags=re.I).strip() if sv else ""
    if nome_sv and len(nome_sv) < 60:
        out["apelido"] = nome_sv
    mc = next((n for n in nos if _tem_classe(n, "poly-component__brand", "ui-search-item__brand-discoverability")), None)
    if mc and _texto(mc):
        out["marca"] = _texto(mc)
    pr = _um(r, "andes-money-amount", dentro=("poly-price__current",)) or \
        _um(r, "andes-money-amount", dentro=("ui-search-price__second-line",))
    if pr:
        out["preco"] = _preco_do_no(pr)
    tt = next((n for n in nos if _tem_classe(n, "poly-component__title", "ui-search-item__title")), None) or \
        next((n for n in nos if n[0] in ("h2", "h3")), None)
    out["titulo"] = _texto(tt)[:200] if tt else ""
    links = [n[1]["href"] for n in nos if n[0] == "a" and n[1].get("href")]
    for h in links:
        u = urllib.parse.unquote(urllib.parse.unquote(h))
        cat = re.search(r"/p/(MLB\d{5,})", u, re.I)
        if cat and not out["catalogo"]:
            out["catalogo"] = cat.group(1).upper()
        m = re.search(r"(?:[?&#]wid=|item_id[:=])(MLB-?\d{6,})", u, re.I) or (None if cat else re.search(r"/MLB-?(\d{6,})", u, re.I))
        if m and not out["mlb"]:
            out["mlb"] = "MLB" + re.sub(r"\D", "", m.group(1))
    out["link"] = next((h for h in links if "mercadolivre.com.br" in h and not re.search(r"click\d?\.mercadolivre", h)), "") or \
        (f"https://produto.mercadolivre.com.br/MLB-{out['mlb'][3:]}" if out["mlb"] else "")
    for n in nos:
        if n[0] == "img":
            f = next((x for x in (n[1].get("data-src"), n[1].get("src")) if x and "mlstatic" in x), "")
            if f:
                out["foto"] = f.replace("-I.", "-O.")
                if not out["titulo"]:
                    out["titulo"] = (n[1].get("alt") or "")[:200]
                break
    return out


def vitrine_cartoes(cards, scripts=()):
    """Todos os cards de uma página da vitrine (sem repetir o MLB) + a lista "printed_result" dos scripts guardados
    (lerImpressos do fundo.js: vendidos, Full e preço completam o card; anúncio que só a lista tem entra com o link)."""
    out, por = [], {}
    for c in cards or []:
        a = cartao_vitrine(c)
        if a["mlb"] and a["mlb"] not in por:
            por[a["mlb"]] = a
            out.append(a)
    t = re.sub(r"\\u002[fF]", "/", re.sub(r'\\+"', '"', " ".join(str(s) for s in scripts or [])))
    for m in re.finditer(r'\{"item_id":"MLB\d{6,}"[^{}]*\}', t):
        try:
            x = json.loads(m.group(0))
        except ValueError:
            continue
        lg = x.get("first_shipping_logistic_type")
        a = por.get(x["item_id"])
        if not a:
            a = por[x["item_id"]] = {"mlb": x["item_id"], "link": f"https://produto.mercadolivre.com.br/MLB-{x['item_id'][3:]}",
                                     "titulo": "", "foto": "", "preco": None, "full": False, "vendidos": None,
                                     "vendidos_mais": False, "catalogo": None, "apelido": "", "marca": ""}
            out.append(a)
        if a["vendidos"] is None and x.get("sold_quantity") is not None:
            a["vendidos"] = int(x["sold_quantity"])
        if lg:
            a["full"] = lg == "fulfillment"
        if a["preco"] is None and x.get("price") is not None:
            a["preco"] = float(x["price"])
        pid = str(x.get("pid") or "").upper()
        if not a["catalogo"] and pid.startswith("MLBP"):
            a["catalogo"] = "MLB" + pid[4:]
    return out


# ---------------------------------------------------------------------------
# 03/10 (Bruno: "abre uma página dentro de Conexões só para a AURA e puxa os dados dela para testar: os ADS, os anúncios e
# as vendas; veja o que dá para puxar"). Tudo pela conta conectada (AURASCENT), SÓ LEITURA. Cada parte vem com ok/erro
# para a tela mostrar o que a API libera e o que recusa. Nada é gravado: é o teste de agora (cache de 10 min).
def _parte(f):
    try:
        return {"ok": True, **f()}
    except ErroMeli as e:
        return {"ok": False, "erro": str(e)[:220]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "erro": f"falhou: {str(e)[:200]}"}


def minha_loja(dias=7, agora=None):
    if not TOKEN_DA_VEZ.get() and not _token_usuario():
        raise ErroLogin("a conta do Mercado Livre não está conectada (ou não renovou o acesso): conecte em 🔌 Conexões")
    agora = agora or datetime.now(timezone.utc)
    ini = (agora - timedelta(days=dias)).strftime("%Y-%m-%dT00:00:00.000-03:00")
    d_ini, d_fim = (agora - timedelta(days=dias)).date().isoformat(), agora.date().isoformat()
    me = _get("/users/me") or {}
    uid = me.get("id")
    out = {"dias": dias, "de": d_ini, "ate": d_fim}
    rep = me.get("seller_reputation") or {}
    out["conta"] = {"ok": True, "id": uid, "nick": me.get("nickname"), "nivel": _nivel(rep.get("level_id")),
                    "medalha": MEDALHAS.get(rep.get("power_seller_status") or "", rep.get("power_seller_status")),
                    "vendas_total": ((rep.get("transactions") or {}).get("total")), "desde": str(me.get("registration_date") or "")[:10],
                    "cidade": ((me.get("address") or {}).get("city"))}

    def anuncios():
        tot = {}
        for st in ("active", "paused", "closed"):
            r = _get(f"/users/{uid}/items/search", {"status": st, "limit": 1}) or {}
            tot[st] = (r.get("paging") or {}).get("total")
        r = _get(f"/users/{uid}/items/search", {"status": "active", "limit": 50, "sort": "sold_quantity_desc"}) or {}
        ids = r.get("results") or []
        lista = []
        for i in range(0, len(ids), 20):
            for b in _get("/items", {"ids": ",".join(ids[i:i + 20]),
                                     "attributes": "id,title,price,available_quantity,sold_quantity,listing_type_id,permalink,thumbnail,shipping,health,status"}) or []:
                x = b.get("body") or {}
                if not x.get("id"):
                    continue
                lista.append({"id": x["id"], "titulo": x.get("title"), "preco": x.get("price"), "estoque": x.get("available_quantity"),
                              "vendidos": x.get("sold_quantity"), "tipo": TIPOS.get(x.get("listing_type_id"), x.get("listing_type_id")),
                              "full": (x.get("shipping") or {}).get("logistic_type") == "fulfillment", "saude": x.get("health"),
                              "link": x.get("permalink"), "foto": x.get("thumbnail")})
        lista.sort(key=lambda a: -(a.get("vendidos") or 0))
        return {"ativos": tot.get("active"), "pausados": tot.get("paused"), "finalizados": tot.get("closed"), "itens": lista}

    def vendas():
        res, offset, total = [], 0, None
        while offset < 600:
            r = _get("/orders/search", {"seller": uid, "order.date_created.from": ini, "sort": "date_desc", "limit": 50, "offset": offset}) or {}
            total = (r.get("paging") or {}).get("total") if total is None else total
            lote = r.get("results") or []
            res += lote
            offset += 50
            if len(lote) < 50:
                break
        pagos = [o for o in res if o.get("status") == "paid"]
        por_dia = {}
        for o in pagos:
            dia = str(o.get("date_created") or "")[:10]
            v = por_dia.setdefault(dia, {"pedidos": 0, "valor": 0.0})
            v["pedidos"] += 1
            v["valor"] += float(o.get("total_amount") or 0)
        ult = []
        for o in res[:25]:
            it = ((o.get("order_items") or [{}])[0]) or {}
            ult.append({"id": o.get("id"), "data": o.get("date_created"), "status": o.get("status"),
                        "titulo": (it.get("item") or {}).get("title"), "qtd": it.get("quantity"), "valor": o.get("total_amount"),
                        "tarifa": it.get("sale_fee"), "anuncio": (it.get("item") or {}).get("id")})
        return {"pedidos": total, "lidos": len(res), "pagos": len(pagos), "faturamento": round(sum(float(o.get("total_amount") or 0) for o in pagos), 2),
                "tarifas": round(sum(float(((o.get("order_items") or [{}])[0] or {}).get("sale_fee") or 0) * float(((o.get("order_items") or [{}])[0] or {}).get("quantity") or 1) for o in pagos), 2),
                "por_dia": [{"dia": k, **v} for k, v in sorted(por_dia.items())], "ultimas": ult}

    def ads():
        r = _get("/advertising/advertisers", {"product_id": "PADS"}, headers={"Api-Version": "1"}) or {}
        anunc = (r.get("advertisers") or [])
        if not anunc:
            return {"anunciante": None, "campanhas": [], "aviso": "a conta não tem anunciante de Product Ads (ADS) ou o app não tem a permissão de Publicidade"}
        adv = anunc[0].get("advertiser_id")
        met = "clicks,prints,ctr,cost,cpc,acos,direct_amount,indirect_amount,total_amount,direct_units_quantity,indirect_units_quantity"
        tentativas = [(f"/advertising/{SITE}/advertisers/{adv}/product_ads/campaigns/search",
                       {"limit": 50, "date_from": d_ini, "date_to": d_fim, "metrics": met, "metrics_summary": "true"}, "2"),
                      (f"/advertising/advertisers/{adv}/product_ads/campaigns",
                       {"limit": 50, "date_from": d_ini, "date_to": d_fim, "metrics": met, "metrics_summary": "true"}, "2")]
        erro = None
        for caminho, ps, ver in tentativas:
            try:
                c = _get(caminho, ps, headers={"Api-Version": ver}) or {}
                break
            except ErroMeli as e:
                erro, c = e, None
        if c is None:
            raise erro
        camps = [{"id": x.get("id"), "nome": x.get("name"), "status": x.get("status"), "orcamento": x.get("budget"),
                  "acos_alvo": x.get("acos_target"), **{k: (x.get("metrics") or {}).get(k) for k in met.split(",")}}
                 for x in c.get("results") or []]
        # 03/10 (Bruno: "quanto gastou de ADS só ontem e quanto até agora hoje"): o mesmo pedido, dia a dia (horário de
        # Brasília). O ML atualiza as métricas de ADS com algumas horas de atraso: "hoje" é o que ele já contou.
        hoje_br = (agora - timedelta(hours=3)).date()
        dias_ads = {}
        for rot, dia in (("ontem", hoje_br - timedelta(days=1)), ("hoje", hoje_br)):
            try:
                cd = _get(caminho, dict(ps, date_from=dia.isoformat(), date_to=dia.isoformat()), headers={"Api-Version": ver}) or {}
            except ErroMeli as e:
                dias_ads[rot] = {"erro": str(e)[:160], "dia": dia.isoformat()}
                continue
            por = {x.get("id"): (x.get("metrics") or {}) for x in cd.get("results") or []}
            for cp in camps:
                cp[f"cost_{rot}"] = (por.get(cp["id"]) or {}).get("cost")
            r_ = cd.get("metrics_summary") or {}
            dias_ads[rot] = {"dia": dia.isoformat(), "cost": r_.get("cost", round(sum(float(m.get("cost") or 0) for m in por.values()), 2)),
                             "total_amount": r_.get("total_amount", round(sum(float(m.get("total_amount") or 0) for m in por.values()), 2)),
                             "acos": r_.get("acos"), "clicks": r_.get("clicks")}
        return {"anunciante": adv, "campanhas": camps, "resumo": c.get("metrics_summary") or {}, "dias": dias_ads}

    def visitas():
        r = _get(f"/users/{uid}/items_visits", {"date_from": d_ini, "date_to": d_fim}) or {}
        return {"total": r.get("total_visits")}

    def perguntas():
        r = _get("/questions/search", {"seller_id": uid, "status": "UNANSWERED", "limit": 1, "api_version": 4}) or {}
        return {"sem_resposta": r.get("total")}

    def reclamacoes():
        r = _get("/post-purchase/v1/claims/search", {"status": "opened", "limit": 1}) or {}
        return {"abertas": (r.get("paging") or {}).get("total")}

    for nome, f in (("anuncios", anuncios), ("vendas", vendas), ("ads", ads), ("visitas", visitas),
                    ("perguntas", perguntas), ("reclamacoes", reclamacoes)):
        out[nome] = _parte(f)
    return out


# ---------------------------------------------------------------------------
# 03/10 (Bruno: "ADS do mês fechado da AURA e um card de ADS em tempo real no Dashboard, atualizando de hora em hora").
ADS_METRICAS = "clicks,prints,cost,acos,total_amount,direct_amount,direct_units_quantity,indirect_units_quantity"


def ads_anunciante():
    r = _get("/advertising/advertisers", {"product_id": "PADS"}, headers={"Api-Version": "1"}) or {}
    a = r.get("advertisers") or []
    if not a:
        raise ErroMeli("a conta não tem anunciante de Product Ads (ADS)")
    return a[0].get("advertiser_id")


def ads_periodo(adv, ini, fim):
    """Resumo de ADS (todas as campanhas) entre duas datas (aaaa-mm-dd, horário do ML)."""
    ps = {"limit": 50, "date_from": str(ini), "date_to": str(fim), "metrics": ADS_METRICAS, "metrics_summary": "true"}
    erro = None
    for caminho in (f"/advertising/{SITE}/advertisers/{adv}/product_ads/campaigns/search",
                    f"/advertising/advertisers/{adv}/product_ads/campaigns"):
        try:
            c = _get(caminho, ps, headers={"Api-Version": "2"}) or {}
            break
        except ErroMeli as e:
            erro, c = e, None
    if c is None:
        raise erro
    res = c.get("metrics_summary") or {}
    camps = c.get("results") or []
    soma = lambda k: round(sum(float((x.get("metrics") or {}).get(k) or 0) for x in camps), 2)
    out = {k: res.get(k, soma(k)) for k in ("cost", "total_amount", "clicks", "prints", "direct_amount")}
    out["acos"] = res.get("acos") if res.get("acos") is not None else (
        round(out["cost"] / out["total_amount"] * 100, 2) if out.get("total_amount") else None)
    out["campanhas"] = len(camps)
    out["roas"] = round(out["total_amount"] / out["cost"], 2) if out.get("cost") else None
    out["de"], out["ate"] = str(ini), str(fim)
    return out


def ads_anuncios(adv, ini, fim, limite=500):
    """03/10 (Bruno: "a lista de ADS dos produtos com margem, para saber o que alterar"): métricas de ADS por anúncio no
    período + o SKU de cada anúncio (para cruzar com a margem do Gestor). Só leitura."""
    met = "clicks,prints,cost,acos,total_amount,direct_amount,units_quantity,direct_units_quantity"
    lista, erro = [], None
    for caminho in (f"/advertising/{SITE}/advertisers/{adv}/product_ads/ads/search",
                    f"/advertising/advertisers/{adv}/product_ads/ads/search"):
        try:
            off = 0
            while off < limite:
                r = _get(caminho, {"limit": 100, "offset": off, "date_from": str(ini), "date_to": str(fim), "metrics": met},
                         headers={"Api-Version": "2"}) or {}
                lote = r.get("results") or []
                lista += lote
                off += 100
                if len(lote) < 100:
                    break
            erro = None
            break
        except ErroMeli as e:
            erro, lista = e, []
    if erro:
        raise erro
    out = []
    for x in lista:
        m = x.get("metrics") or {}
        cost, venda = float(m.get("cost") or 0), float(m.get("total_amount") or 0)
        out.append({"anuncio": x.get("item_id") or x.get("id"), "titulo": x.get("title"), "status": x.get("status"),
                    "campanha": x.get("campaign_id"), "preco": x.get("price"), "cost": round(cost, 2), "total_amount": round(venda, 2),
                    "clicks": m.get("clicks"), "prints": m.get("prints"), "unidades": m.get("units_quantity"),
                    "acos": m.get("acos"), "roas": round(venda / cost, 2) if cost else None})
    ids = [a["anuncio"] for a in out if a.get("anuncio")]
    sku = {}
    for i in range(0, len(ids), 20):
        try:
            for b in _get("/items", {"ids": ",".join(ids[i:i + 20]), "attributes": "id,seller_custom_field,attributes,title,thumbnail,permalink"}) or []:
                x = b.get("body") or {}
                s_ = x.get("seller_custom_field") or next((a.get("value_name") for a in x.get("attributes") or []
                                                          if a.get("id") == "SELLER_SKU"), None)
                sku[x.get("id")] = (s_, x.get("thumbnail"), x.get("permalink"), x.get("title"))
        except ErroMeli:
            pass
    for a in out:
        s_, foto, link, tit = sku.get(a["anuncio"]) or (None, None, None, None)
        a.update(sku=s_, foto=foto, link=link, titulo=a.get("titulo") or tit)
    return sorted(out, key=lambda a: -a["cost"])
