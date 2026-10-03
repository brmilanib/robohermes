"""02/10 (Bruno: "as margens em tempo real do Gestor no Dashboard"): ler_painel_gestor tira totais, 7 dias, produtos e vendas
das respostas que a tela do Gestor pede (formato real de 02/10)."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SUPABASE_URL", "http://x")
import nubi_web  # noqa: E402

q = "from=2026-10-02+00:00:00&to=2026-10-02+23:59:59&accountsIds%5B%5D=9760"
cards = {"success": True, "data": {"invoice": 27927.11, "platform": 22943.15, "profit": 4347.35, "margin": 0.15567, "roi": 0.2442,
                                     "ads": 0, "tacos": 0, "profit_after_ads": 4347.35, "margin_after_ads": 0.15567, "quantity_units_sold": 98,
                                     "quantity_sold": 95, "avg_price_products": 293.97, "invoice_cancelled": 178, "costPrice": 17804.39}}
chart = {"success": True, "data": {"invoice": {"daily": {"2026-10-01": 23040.39, "2026-10-02": 27926.29}},
                                     "profit": {"daily": {"2026-10-01": 3000.0, "2026-10-02": 4347.35}}}}
rank = {"success": True, "data": {"total": 44, "data": [{"title": "Perfume Vibrato Sospiro Edp 100ml", "internal_sku": "SOS-VIB-100",
         "thumbnail": "http://http2.mlstatic.com/D_1.jpg", "total_sales": 2, "total_invoice": 2758, "total_profit": 319.14, "margin": 0.1157,
         "ads_cost": 0, "meli_sales": 2, "shopee_sales": 0}]}}
sales = {"success": True, "data": {"total": 98, "data": [{"approval_date": "2026-10-02 21:06:09", "account_name": "ESSENCE PRIME",
         "marketplace": "Mercado Livre", "order_total": 223.15, "status": "paid", "logistic_type": "not_full",
         "items": [{"title": "Perfume Britney Spears Fantasy", "sku": "FANTASY-EDP-100", "quantity": 1, "margin": 18.9, "profit": 42.18,
                    "thumbnail": "http://http2.mlstatic.com/D_2.jpg", "permalink": "https://produto.mercadolivre.com.br/MLB-6636224170"}]}]}}
J = lambda url, c, qq="": {"url": "https://apiv3.gestorseller.com.br/api/" + url, "q": qq, "corpo": json.dumps(c)}
telas = [{"tela": "painel", "jsons": [J("dashboard/cards", cards, q), J("dashboard/chart", chart, q), J("products/rank-v2", rank, q)]},
         {"tela": "vendas", "jsons": [J("sales", sales, q)]}]
r = nubi_web.ler_painel_gestor(telas)
assert r["dia"] == "2026-10-02" and r["cards"]["faturamento"] == 27927.11 and r["cards"]["margem"] == 0.1557 and r["cards"]["pedidos"] == 95, r["cards"]
assert r["dias"][-1] == {"dia": "2026-10-02", "faturamento": 27926.29, "lucro": 4347.35, "margem": 0.1557}, r["dias"]
p = r["produtos"][0]
assert p["sku"] == "SOS-VIB-100" and p["foto"].startswith("https://") and p["canais"] == {"meli": 2} and p["margem"] == 0.1157, p
v = r["vendas"][0]
assert v["hora"] == "21:06" and v["lucro"] == 42.18 and v["margem"] == round(42.18 / 223.15, 4) and v["itens"][0]["sku"] == "FANTASY-EDP-100", v
assert r["total_vendas"] == 98
assert "doc" not in json.dumps(r) and "phone" not in json.dumps(r)
print("ok painel gestor")
