# -*- coding: utf-8 -*-
"""
🔌 Conexões das minhas lojas (03/10, Bruno: "prepare a tela de conexão de lojas igual à do Gestor Seller; quero conectar
as minhas 3 lojas do Mercado Livre, a da Shopee e a do TikTok, para puxar os dados, anúncios e ADS direto delas").

Regras (as mesmas da conta do ML de 29/09, estendidas pelo pedido do Bruno):
- o login é SEMPRE na página da própria plataforma (OAuth); a senha nunca passa pelo nubi;
- as chaves do app (ML_CLIENT_ID/SECRET, SHOPEE_PARTNER_ID/KEY, TIKTOK_APP_KEY/SECRET/SERVICE_ID) só na Vercel, postas
  pelo Bruno; nunca no código, banco, chat ou log;
- o refresh_token de cada loja fica CIFRADO em ia_resumos `loja|conta|<plataforma>|<id>` (chave derivada do segredo do app
  da plataforma, que só existe na Vercel); o access_token só na memória; nada de token em erro, log ou tela;
- só LEITURA (pedidos, anúncios, estoque, ADS): o nubi nunca altera anúncio, preço, pedido ou campanha.
"""
import base64
import re
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

PLATAFORMAS = {
    "ml": {"nome": "Mercado Livre", "envs": ["ML_CLIENT_ID", "ML_CLIENT_SECRET"], "segredo": "ML_CLIENT_SECRET", "max": 10},
    "shopee": {"nome": "Shopee", "envs": ["SHOPEE_PARTNER_ID", "SHOPEE_PARTNER_KEY"], "segredo": "SHOPEE_PARTNER_KEY", "max": 10},
    "tiktok": {"nome": "TikTok Shop", "envs": ["TIKTOK_APP_KEY", "TIKTOK_APP_SECRET", "TIKTOK_SERVICE_ID"], "segredo": "TIKTOK_APP_SECRET", "max": 10},
}
CONTA = "loja|conta|"            # + plataforma|id
ESTADO = "loja|estado|"          # + plataforma
SHOPEE_API = os.environ.get("NUBI_SHOPEE_API", "https://partner.shopeemobile.com")
TIKTOK_AUTH = os.environ.get("NUBI_TIKTOK_AUTH", "https://auth.tiktok-shops.com")
TIKTOK_AUTORIZAR = os.environ.get("NUBI_TIKTOK_AUTORIZAR", "https://services.tiktokshop.com/open/authorize")
ML_AUTH = os.environ.get("NUBI_ML_AUTH", "https://auth.mercadolivre.com.br")
ML_API = os.environ.get("NUBI_ML_API", "https://api.mercadolibre.com")
ABRIR = urllib.request.urlopen


class ErroConexao(Exception):
    pass


def configurada(p):
    return all(os.environ.get(e) for e in PLATAFORMAS[p]["envs"])


# ---- cifra (mesma construção de meli.cifrar: HMAC-SHA256 em contador + etiqueta), uma chave por plataforma ----
def _chave(p):
    seg = os.environ.get(PLATAFORMAS[p]["segredo"]) or ""
    if not seg:
        raise ErroConexao(f"{PLATAFORMAS[p]['nome']}: o app ainda não está configurado na Vercel")
    return hmac.new(seg.encode(), f"nubi|loja|{p}|v1".encode(), hashlib.sha256).digest()


def cifrar(p, texto):
    k, dado, nonce = _chave(p), texto.encode(), secrets.token_bytes(16)
    fluxo = b"".join(hmac.new(k, nonce + i.to_bytes(4, "big"), hashlib.sha256).digest() for i in range(len(dado) // 32 + 1))
    ct = bytes(a ^ b for a, b in zip(dado, fluxo))
    tag = hmac.new(k, b"tag" + nonce + ct, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + tag + ct).decode()


def decifrar(p, tok):
    k = _chave(p)
    raw = base64.urlsafe_b64decode(tok.encode())
    nonce, tag, ct = raw[:16], raw[16:48], raw[48:]
    if not hmac.compare_digest(tag, hmac.new(k, b"tag" + nonce + ct, hashlib.sha256).digest()):
        raise ErroConexao("dado cifrado não confere (o segredo do app mudou? conecte de novo)")
    fluxo = b"".join(hmac.new(k, nonce + i.to_bytes(4, "big"), hashlib.sha256).digest() for i in range(len(ct) // 32 + 1))
    return bytes(a ^ b for a, b in zip(ct, fluxo)).decode()


# ---- banco ----
def _ler(repo, chave):
    r = (repo._req("GET", "ia_resumos", {"select": "texto", "chave": f"eq.{chave}"}) or [None])[0]
    try:
        return json.loads(r["texto"]) if r and r.get("texto") else {}
    except (TypeError, ValueError):
        return {}


def _gravar(repo, chave, d):
    repo._req("POST", "ia_resumos", corpo=[{"chave": chave, "ia": "conexão de loja", "texto": json.dumps(d, ensure_ascii=False)}],
              prefer="resolution=merge-duplicates,return=minimal")


def contas(repo, p=None):
    pre = CONTA + (f"{p}|" if p else "")
    rs = repo._todos("ia_resumos", {"select": "chave,texto", "chave": f"like.{pre}*"}) or []
    out = []
    for r in rs:
        try:
            d = json.loads(r["texto"] or "{}")
        except (TypeError, ValueError):
            continue
        if d.get("refresh") or d.get("desconectada_em"):
            d = {k: v for k, v in d.items() if k != "refresh"} | {"ativa": bool(d.get("refresh"))}
            out.append(d)
    return sorted(out, key=lambda d: (d.get("plataforma") or "", bool(d.get("teste")), d.get("nome") or ""))


def retorno(base, p, estado=""):
    q = {"r": "loja_retorno", "p": p}
    if p == "shopee" and estado:                       # a Shopee não devolve state: vai no próprio endereço de volta
        q["s"] = estado
    return f"{base}?" + urllib.parse.urlencode(q)


# ---- iniciar a conexão ----
def url_conectar(repo, p, base):
    if p not in PLATAFORMAS:
        raise ErroConexao("plataforma desconhecida")
    if not configurada(p):
        faltam = [e for e in PLATAFORMAS[p]["envs"] if not os.environ.get(e)]
        raise ErroConexao(f"{PLATAFORMAS[p]['nome']}: falta configurar na Vercel: {', '.join(faltam)}")
    estado = secrets.token_urlsafe(24)
    _gravar(repo, ESTADO + p, {"estado": estado, "em": time.time()})
    if p == "ml":
        return f"{ML_AUTH}/authorization?" + urllib.parse.urlencode(
            {"response_type": "code", "client_id": os.environ["ML_CLIENT_ID"], "redirect_uri": retorno(base, "ml"), "state": estado})
    if p == "shopee":
        caminho, ts = "/api/v2/shop/auth_partner", int(time.time())
        return f"{SHOPEE_API}{caminho}?" + urllib.parse.urlencode(
            {"partner_id": os.environ["SHOPEE_PARTNER_ID"], "timestamp": ts, "sign": _sign_shopee(caminho, ts),
             "redirect": retorno(base, "shopee", estado)})
    return f"{TIKTOK_AUTORIZAR}?" + urllib.parse.urlencode({"service_id": os.environ["TIKTOK_SERVICE_ID"], "state": estado})


def conferir_estado(repo, p, estado):
    est = _ler(repo, ESTADO + p)
    ok = bool(estado) and est.get("estado") and hmac.compare_digest(str(estado), est["estado"]) \
        and time.time() - float(est.get("em") or 0) <= 15 * 60
    _gravar(repo, ESTADO + p, {})                       # uso único
    return bool(ok)


# ---- Shopee ----
def _sign_shopee(caminho, ts, token="", shop_id=""):
    base = f"{os.environ['SHOPEE_PARTNER_ID']}{caminho}{ts}{token}{shop_id}"
    return hmac.new(os.environ["SHOPEE_PARTNER_KEY"].encode(), base.encode(), hashlib.sha256).hexdigest()


def _json(req, timeout=20):
    try:
        with ABRIR(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            d = json.loads(e.read() or b"{}")
            motivo = str(d.get("message") or d.get("error") or d.get("msg") or "")[:90]
        except Exception:  # noqa: BLE001
            motivo = ""
        raise ErroConexao(f"a plataforma recusou ({e.code}{': ' + motivo if motivo else ''})")
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ErroConexao("sem resposta da plataforma")


def _shopee_post(caminho, corpo):
    ts = int(time.time())
    url = f"{SHOPEE_API}{caminho}?" + urllib.parse.urlencode({"partner_id": os.environ["SHOPEE_PARTNER_ID"], "timestamp": ts,
                                                              "sign": _sign_shopee(caminho, ts)})
    corpo = dict(corpo, partner_id=int(os.environ["SHOPEE_PARTNER_ID"]))
    return _json(urllib.request.Request(url, data=json.dumps(corpo).encode(), method="POST",
                                        headers={"Content-Type": "application/json"}))


def _shopee_get(caminho, token, shop_id, params=None):
    ts = int(time.time())
    q = {"partner_id": os.environ["SHOPEE_PARTNER_ID"], "timestamp": ts, "access_token": token, "shop_id": shop_id,
         "sign": _sign_shopee(caminho, ts, token, shop_id), **(params or {})}
    return _json(urllib.request.Request(f"{SHOPEE_API}{caminho}?" + urllib.parse.urlencode(q)))


# ---- concluir a conexão (volta do login) ----
def concluir(repo, p, q, base):
    """Troca o código pelo acesso, lê o nome da loja e guarda a conta com o refresh cifrado. -> conta (sem token)."""
    agora = datetime.now(timezone.utc).isoformat()
    if p == "ml":
        corpo = urllib.parse.urlencode({"grant_type": "authorization_code", "client_id": os.environ["ML_CLIENT_ID"],
                                        "client_secret": os.environ["ML_CLIENT_SECRET"], "code": q.get("code") or "",
                                        "redirect_uri": retorno(base, "ml")}).encode()
        d = _json(urllib.request.Request(f"{ML_API}/oauth/token", data=corpo, method="POST",
                                         headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}))
        if not d.get("access_token") or not d.get("refresh_token"):
            raise ErroConexao("o Mercado Livre não devolveu o acesso (o app precisa pedir 'offline_access')")
        eu = _json(urllib.request.Request(f"{ML_API}/users/me", headers={"Authorization": f"Bearer {d['access_token']}"}))
        conta = {"plataforma": "ml", "id": str(eu.get("id") or d.get("user_id")), "nome": eu.get("nickname") or "",
                 "refresh": cifrar("ml", d["refresh_token"]), "escopo": d.get("scope") or "", "em": agora}
    elif p == "shopee":
        shop_id = int(q.get("shop_id") or 0)
        d = _shopee_post("/api/v2/auth/token/get", {"code": q.get("code") or "", "shop_id": shop_id})
        if not d.get("access_token") or not d.get("refresh_token"):
            raise ErroConexao(f"a Shopee não devolveu o acesso ({str(d.get('message') or d.get('error') or '')[:80]})")
        try:
            info = _shopee_get("/api/v2/shop/get_shop_info", d["access_token"], shop_id)
        except ErroConexao:
            info = {}
        conta = {"plataforma": "shopee", "id": str(shop_id), "nome": info.get("shop_name") or f"Loja {shop_id}",
                 "refresh": cifrar("shopee", d["refresh_token"]), "regiao": info.get("region") or "BR", "em": agora}
    else:
        url = f"{TIKTOK_AUTH}/api/v2/token/get?" + urllib.parse.urlencode(
            {"app_key": os.environ["TIKTOK_APP_KEY"], "app_secret": os.environ["TIKTOK_APP_SECRET"],
             "auth_code": q.get("code") or "", "grant_type": "authorized_code"})
        r = _json(urllib.request.Request(url))
        d = r.get("data") or {}
        if not d.get("access_token") or not d.get("refresh_token"):
            raise ErroConexao(f"o TikTok Shop não devolveu o acesso ({str(r.get('message') or '')[:80]})")
        conta = {"plataforma": "tiktok", "id": str(d.get("open_id") or d.get("seller_name") or "loja"),
                 "nome": d.get("seller_name") or "Loja TikTok", "refresh": cifrar("tiktok", d["refresh_token"]),
                 "regiao": d.get("seller_base_region") or "", "em": agora}
    # 03/10 (Bruno: "ele não podia conectar a BRUNOMILANI sem eu pedir"): nada é ligado direto. A conta que a plataforma
    # devolveu fica PENDENTE (15 min) e a página de volta mostra o nome dela para o Bruno confirmar ou recusar.
    token = secrets.token_urlsafe(18)
    _gravar(repo, PENDENTE + token, dict(conta, pendente_em=time.time()))
    return dict({k: v for k, v in conta.items() if k != "refresh"}, confirmar=token)


PENDENTE = "loja|pendente|"


def confirmar(repo, token, aceitar):
    """Confirma (grava a conta) ou recusa (descarta) a conta pendente. Uso único, 15 min. -> conta (sem token) ou None."""
    if not token or not re.fullmatch(r"[\w-]{10,40}", token):
        raise ErroConexao("pedido de confirmação inválido")
    c = _ler(repo, PENDENTE + token)
    _gravar(repo, PENDENTE + token, {})
    if not c or time.time() - float(c.get("pendente_em") or 0) > 15 * 60:
        raise ErroConexao("a confirmação venceu; clique em Conectar de novo no nubi")
    if not aceitar:
        return None
    c.pop("pendente_em", None)
    antes = _ler(repo, f"{CONTA}{c['plataforma']}|{c['id']}")
    c.update({k: antes[k] for k in ("apelido", "teste") if k in antes})        # reconectar não perde o apelido
    _gravar(repo, f"{CONTA}{c['plataforma']}|{c['id']}", c)
    return {k: v for k, v in c.items() if k != "refresh"}


def desconectar(repo, p, id_):
    c = _ler(repo, f"{CONTA}{p}|{id_}")
    if not c:
        raise ErroConexao("conta não encontrada")
    _gravar(repo, f"{CONTA}{p}|{id_}", {k: v for k, v in c.items() if k != "refresh"} | {"desconectada_em": datetime.now(timezone.utc).isoformat()})
    return {"ok": True}


def painel(repo, base):
    """O que a tela mostra: cada plataforma, se o app está configurado, as contas e o endereço de volta a cadastrar."""
    cs = contas(repo)
    return {"plataformas": [{"chave": p, "nome": x["nome"], "configurada": configurada(p),
                             "faltam": [e for e in x["envs"] if not os.environ.get(e)],
                             "retorno": retorno(base, p).replace("&s=", "") if p != "tiktok" else retorno(base, p),
                             "contas": [c for c in cs if c.get("plataforma") == p]} for p, x in PLATAFORMAS.items()]}


# ---- acesso de uma loja (para ler os dados dela) ----
_ACESSO = {}                                        # memória: (plataforma, id) -> (token, válido até)


def acesso_ml(repo, id_):
    """Token de acesso de UMA conta do ML conectada aqui (renova pelo refresh; o ML troca o refresh a cada uso e o novo é
    gravado cifrado). Nunca sai do servidor."""
    k = ("ml", str(id_))
    if k in _ACESSO and time.time() < _ACESSO[k][1]:
        return _ACESSO[k][0]
    c = _ler(repo, f"{CONTA}ml|{id_}")
    if not c.get("refresh"):
        raise ErroConexao("esta loja não está conectada (conecte de novo em 🔌 Conexões)")
    corpo = urllib.parse.urlencode({"grant_type": "refresh_token", "client_id": os.environ["ML_CLIENT_ID"],
                                    "client_secret": os.environ["ML_CLIENT_SECRET"],
                                    "refresh_token": decifrar("ml", c["refresh"])}).encode()
    d = _json(urllib.request.Request(f"{ML_API}/oauth/token", data=corpo, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}))
    if not d.get("access_token"):
        raise ErroConexao("o Mercado Livre não renovou o acesso desta loja (conecte de novo)")
    if d.get("refresh_token"):
        _gravar(repo, f"{CONTA}ml|{id_}", dict(c, refresh=cifrar("ml", d["refresh_token"]),
                                                renovado_em=datetime.now(timezone.utc).isoformat()))
    _ACESSO[k] = (d["access_token"], time.time() + max(300, int(d.get("expires_in") or 21600) - 300))
    return d["access_token"]
