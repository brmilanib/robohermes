"""03/10 (Bruno: "página em Conexões só para a AURA: ADS, anúncios e vendas; veja o que dá para puxar"): meli.minha_loja
com respostas falsas do ML; cada parte ok/erro (um 403 numa parte não derruba as outras)."""
import io
import json
import sys
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import meli  # noqa: E402

meli._token_usuario = lambda forcar=False: "tok"
pedidos = []


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def abrir(req, timeout):
    u = req.full_url
    pedidos.append((u, dict(req.headers)))
    if "/users/me" in u:
        d = {"id": 3241025421, "nickname": "AURASCENT", "seller_reputation": {"level_id": "5_green", "power_seller_status": "gold",
                                                                          "transactions": {"total": 5400}}}
    elif "/items/search" in u:
        d = {"paging": {"total": {"active": 320, "paused": 40, "closed": 900}["active" if "active" in u else "paused" if "paused" in u else "closed"]},
             "results": ["MLB1", "MLB2"] if "limit=50" in u else []}
    elif "/items?" in u:
        d = [{"code": 200, "body": {"id": "MLB1", "title": "Silver Scent 100ml", "price": 199.9, "available_quantity": 12, "sold_quantity": 800,
                                    "listing_type_id": "gold_pro", "shipping": {"logistic_type": "fulfillment"}, "health": 0.92}},
             {"code": 200, "body": {"id": "MLB2", "title": "Cuba Gold", "price": 99.9, "available_quantity": 3, "sold_quantity": 50,
                                    "listing_type_id": "gold_special", "shipping": {}}}]
    elif "/orders/search" in u:
        d = {"paging": {"total": 3}, "results": [
            {"id": 1, "status": "paid", "date_created": "2026-10-02T10:00:00.000-03:00", "total_amount": 199.9,
             "order_items": [{"item": {"id": "MLB1", "title": "Silver Scent 100ml"}, "quantity": 1, "sale_fee": 30.0}]},
            {"id": 2, "status": "paid", "date_created": "2026-10-03T09:00:00.000-03:00", "total_amount": 99.9,
             "order_items": [{"item": {"id": "MLB2", "title": "Cuba Gold"}, "quantity": 1, "sale_fee": 12.0}]},
            {"id": 3, "status": "cancelled", "date_created": "2026-10-03T09:30:00.000-03:00", "total_amount": 50,
             "order_items": [{"item": {"id": "MLB2", "title": "Cuba Gold"}, "quantity": 1, "sale_fee": 6.0}]}]}
    elif "/advertising/advertisers?" in u:
        assert req.headers.get("Api-version") == "1"
        d = {"advertisers": [{"advertiser_id": 777, "site_id": "MLB"}]}
    elif "/product_ads/campaigns/search" in u:
        assert req.headers.get("Api-version") == "2"
        d = {"results": [{"id": 9, "name": "Campeões", "status": "active", "budget": 100, "metrics": {"cost": 80.5, "clicks": 300, "prints": 9000, "total_amount": 900, "acos": 8.9}}],
             "metrics_summary": {"cost": 80.5, "total_amount": 900, "acos": 8.9}}
    elif "/items_visits" in u:
        d = {"total_visits": 4321}
    elif "/questions/search" in u:
        d = {"total": 5}
    elif "/claims/search" in u:
        raise urllib.error.HTTPError(u, 403, "Forbidden", {}, io.BytesIO(b'{"message":"forbidden","code":"PA_UNAUTHORIZED"}'))
    else:
        raise AssertionError(u)
    return Resp(json.dumps(d).encode())


meli._abrir = abrir
r = meli.minha_loja(7, agora=datetime(2026, 10, 3, 15, tzinfo=timezone.utc))
assert r["conta"]["nick"] == "AURASCENT" and r["conta"]["medalha"] == "Gold"
an = r["anuncios"]
assert an["ok"] and an["ativos"] == 320 and an["pausados"] == 40 and an["itens"][0]["full"] and an["itens"][0]["tipo"] == "Premium"
vd = r["vendas"]
assert vd["ok"] and vd["pagos"] == 2 and vd["faturamento"] == 299.8 and vd["tarifas"] == 42.0 and len(vd["por_dia"]) == 2
ad = r["ads"]
assert ad["dias"]["ontem"]["dia"] == "2026-10-02" and ad["dias"]["hoje"]["dia"] == "2026-10-03" and ad["dias"]["hoje"]["cost"] == 80.5
assert ad["campanhas"][0]["cost_ontem"] == 80.5
assert ad["ok"] and ad["anunciante"] == 777 and ad["campanhas"][0]["cost"] == 80.5 and ad["resumo"]["acos"] == 8.9
assert r["visitas"]["total"] == 4321 and r["perguntas"]["sem_resposta"] == 5
assert not r["reclamacoes"]["ok"] and "403" in r["reclamacoes"]["erro"]          # uma parte recusada não derruba as outras
assert all(h.get("Authorization") == "Bearer tok" for _, h in pedidos)
assert not any(m in u for u, _ in pedidos for m in ("PUT", "/items/MLB1?", "POST"))   # só leitura (GET)
# a página de OUTRA loja usa o token dela (só dentro da consulta) e não o da conta principal
pedidos.clear()
m = meli.TOKEN_DA_VEZ.set("tok-essence")
meli.minha_loja(7, agora=datetime(2026, 10, 3, 15, tzinfo=timezone.utc))
meli.TOKEN_DA_VEZ.reset(m)
assert pedidos and all(h.get("Authorization") == "Bearer tok-essence" for _, h in pedidos)
# ADS em tempo real (card do Dashboard): hoje, ontem, mês atual e mês fechado + a curva do dia
import nubi_web  # noqa: E402
datas = []
orig_periodo = meli.ads_periodo
meli.ads_periodo = lambda adv, a, b: datas.append((a, b)) or orig_periodo(adv, a, b)


class RepoAds:
    def __init__(self):
        self.ia = {}

    def _eq(self, v):
        return f"eq.{v}"

    def _req(self, metodo, t, params=None, corpo=None, prefer=None):
        if metodo == "GET":
            if t == "ia_resumos":
                k = params["chave"][3:]
                return [{"texto": self.ia[k]}] if k in self.ia else []
            return []
        for r in corpo or []:
            self.ia[r["chave"]] = r["texto"]
        return []


ra = RepoAds()
d = nubi_web.ads_tempo_real(ra, agora=datetime(2026, 10, 3, 14, tzinfo=timezone.utc))
assert ("2026-10-03", "2026-10-03") in datas and ("2026-10-02", "2026-10-02") in datas
assert ("2026-10-01", "2026-10-03") in datas and ("2026-09-01", "2026-09-30") in datas
assert d["hoje"]["cost"] == 80.5 and d["mes_fechado"]["acos"] == 8.9 and d["horas"] == [{"h": "11:00", "cost": 80.5, "vendas": 900}]
d = nubi_web.ads_tempo_real(ra, agora=datetime(2026, 10, 3, 15, tzinfo=timezone.utc))
assert [h["h"] for h in d["horas"]] == ["11:00", "12:00"]                    # um ponto por hora no dia
d = nubi_web.ads_tempo_real(ra, agora=datetime(2026, 10, 4, 12, tzinfo=timezone.utc))
assert [h["h"] for h in d["horas"]] == ["09:00"]                             # dia novo: curva recomeça
meli.ads_periodo = orig_periodo

meli._token_usuario = lambda forcar=False: None
try:
    meli.minha_loja(7)
    raise AssertionError("sem conta devia avisar")
except meli.ErroLogin as e:
    assert "Conexões" in str(e)
print("ok minha loja ML (API)")
