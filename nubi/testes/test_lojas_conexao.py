"""03/10 (Bruno: "tela de conexão de lojas igual à do Gestor Seller"): conectar ML (várias contas), Shopee e TikTok por
OAuth; state de uso único; refresh token só cifrado; nada de token na resposta."""
import io
import json
import os
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for k in ("ML_CLIENT_ID", "ML_CLIENT_SECRET", "SHOPEE_PARTNER_ID", "SHOPEE_PARTNER_KEY", "TIKTOK_APP_KEY", "TIKTOK_APP_SECRET", "TIKTOK_SERVICE_ID"):
    os.environ.pop(k, None)
import lojas_conexao as lc  # noqa: E402
import nubi_web  # noqa: E402


class Repo:
    email = "brmilani@gmail.com"

    def __init__(self):
        self.ia = {}

    def _req(self, metodo, t, params=None, corpo=None, prefer=None):
        if metodo == "GET":
            k = params["chave"][3:]
            return [{"texto": self.ia[k]}] if k in self.ia else []
        for r in corpo or []:
            self.ia[r["chave"]] = r["texto"]
        return []

    def _eq(self, v):
        return f"eq.{v}"

    def _todos(self, t, p):
        pre = p["chave"][len("like."):-1]
        return [{"chave": k, "texto": v} for k, v in self.ia.items() if k.startswith(pre)]


BASE = "https://nubi.test/api/app"
repo = Repo()
nubi_web._repo_agente = lambda: repo

# sem app configurado: painel mostra o que falta, conectar recusa
pn = lc.painel(repo, BASE)
assert [p["chave"] for p in pn["plataformas"]] == ["ml", "shopee", "tiktok"]
assert pn["plataformas"][1]["faltam"] == ["SHOPEE_PARTNER_ID", "SHOPEE_PARTNER_KEY"]
try:
    lc.url_conectar(repo, "shopee", BASE)
    raise AssertionError("devia recusar")
except lc.ErroConexao as e:
    assert "SHOPEE_PARTNER_KEY" in str(e)

os.environ.update(ML_CLIENT_ID="111", ML_CLIENT_SECRET="segml", SHOPEE_PARTNER_ID="222", SHOPEE_PARTNER_KEY="segsp",
                  TIKTOK_APP_KEY="ak", TIKTOK_APP_SECRET="segtt", TIKTOK_SERVICE_ID="999")

pedidos = []


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def abrir(req, timeout=20):
    u = req.full_url
    pedidos.append(u)
    if "/oauth/token" in u:
        n = len([x for x in pedidos if "/oauth/token" in x])
        return Resp(json.dumps({"access_token": f"AT{n}", "refresh_token": f"RTML{n}", "user_id": 500 + n}).encode())
    if "/users/me" in u:
        n = req.headers["Authorization"][-1]
        return Resp(json.dumps({"id": 500 + int(n), "nickname": f"LOJA{n}"}).encode())
    if "/auth/token/get" in u:
        return Resp(json.dumps({"access_token": "ATSP", "refresh_token": "RTSP"}).encode())
    if "get_shop_info" in u:
        return Resp(json.dumps({"shop_name": "Nubi Shopee", "region": "BR"}).encode())
    if "/api/v2/token/get" in u:
        return Resp(json.dumps({"data": {"access_token": "ATTT", "refresh_token": "RTTT", "open_id": "op1", "seller_name": "Nubi TT"}}).encode())
    raise AssertionError(u)


lc.ABRIR = abrir


def state(url, nome="state"):
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)[nome][0]


# ML: duas contas, uma de cada vez
for i in (1, 2):
    u = lc.url_conectar(repo, "ml", BASE)
    assert "redirect_uri=" + urllib.parse.quote(f"{BASE}?r=loja_retorno&p=ml", safe="") in u, u
    st, tipo, html, *_ = nubi_web._loja_retorno({"p": "ml", "code": f"C{i}", "state": state(u)}); html = html.decode() if isinstance(html, bytes) else html
    assert f"LOJA{i}" in html and "conectad" in html.lower(), html
# state reaproveitado não vale
st, tipo, html, *_ = nubi_web._loja_retorno({"p": "ml", "code": "C9", "state": state(u)}); html = html.decode() if isinstance(html, bytes) else html
assert "venceu" in html

# Shopee: state no próprio endereço de volta (param s), assinatura no pedido
u = lc.url_conectar(repo, "shopee", BASE)
red = state(u, "redirect")
assert "sign=" in u and "r=loja_retorno" in red
s = urllib.parse.parse_qs(urllib.parse.urlparse(red).query)["s"][0]
st, tipo, html, *_ = nubi_web._loja_retorno({"p": "shopee", "s": s, "code": "CS", "shop_id": "777"}); html = html.decode() if isinstance(html, bytes) else html
assert "Nubi Shopee" in html, html

# TikTok
u = lc.url_conectar(repo, "tiktok", BASE)
assert "service_id=999" in u
st, tipo, html, *_ = nubi_web._loja_retorno({"p": "tiktok", "state": state(u), "code": "CT"}); html = html.decode() if isinstance(html, bytes) else html
assert "Nubi TT" in html, html

# tokens: nunca em claro no banco; o painel não devolve o refresh
banco = json.dumps(repo.ia)
for t in ("RTML1", "RTML2", "RTSP", "RTTT", "AT1", "ATSP", "ATTT"):
    assert t not in banco, t
c = json.loads(repo.ia["loja|conta|ml|501"])
assert lc.decifrar("ml", c["refresh"]) == "RTML1"
pn = nubi_web.rota_lojas_conexoes(repo, "GET", "lojas_conexoes", {}, None)
assert "refresh" not in json.dumps(pn)
ml = pn["plataformas"][0]
assert [x["nome"] for x in ml["contas"]] == ["LOJA1", "LOJA2"] and all(x["ativa"] for x in ml["contas"])

# desconectar
nubi_web.rota_lojas_conexoes(repo, "POST", "loja_desconectar", {}, json.dumps({"plataforma": "ml", "id": "502"}).encode())
pn = lc.painel(repo, BASE)
assert [x["ativa"] for x in pn["plataformas"][0]["contas"]] == [True, False]
assert "refresh" not in repo.ia["loja|conta|ml|502"]

# conectar pela rota devolve só a url
j = nubi_web.rota_lojas_conexoes(repo, "POST", "loja_conectar", {}, json.dumps({"plataforma": "tiktok"}).encode())
assert list(j) == ["url"]
# acesso de UMA loja (renova pelo refresh, grava o refresh novo cifrado) e a rota da página dela
def abrir2(req, timeout=20):
    if "/oauth/token" in req.full_url:
        assert b"grant_type=refresh_token" in req.data and b"RTML1" in req.data
        return Resp(json.dumps({"access_token": "AT-LOJA1", "refresh_token": "RTML1-novo", "expires_in": 21600}).encode())
    raise AssertionError(req.full_url)


lc.ABRIR = abrir2
assert lc.acesso_ml(repo, "501") == "AT-LOJA1"
assert lc.decifrar("ml", json.loads(repo.ia["loja|conta|ml|501"])["refresh"]) == "RTML1-novo"
assert lc.acesso_ml(repo, "501") == "AT-LOJA1"                        # da memória, sem pedir de novo
try:
    lc.acesso_ml(repo, "502")                                          # desconectada
    raise AssertionError("devia recusar")
except lc.ErroConexao:
    pass
visto = []
nubi_web.meli.minha_loja = lambda dias: visto.append(nubi_web.meli.TOKEN_DA_VEZ.get()) or {"ok": 1}
assert nubi_web.rota_meli(repo, "GET", "meli_minha_loja", {"conta": "501", "dias": "7"}, None) == {"ok": 1}
assert visto == ["AT-LOJA1"] and nubi_web.meli.TOKEN_DA_VEZ.get() is None   # o token da loja não vaza para fora da consulta
print("ok conexões de lojas")
