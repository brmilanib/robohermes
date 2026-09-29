# -*- coding: utf-8 -*-
"""API oficial do Mercado Livre (29/09, pedido do Bruno): dublê da API (sem rede). Token do app só na memória e nunca na
mensagem de erro; anúncio normalizado; nota e insights; loja com os anúncios; catálogo pelo GTIN; vendedor embaralhado do
Nubimetrics (hash) casado com a loja real por preço, Full e idade. Rodar: python3 testes/test_meli.py, na pasta nubi."""
import io
import json
import os
import sys
import urllib.error
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import meli  # noqa: E402

HOJE = datetime.now(timezone.utc)
ISO = lambda dias: (HOJE - timedelta(days=dias)).isoformat()


def item(mlb, titulo, preco, vendedor, dias=100, vendidos=500, cheio=None, full=False, frete=True, disp=50, cat="MLB6284",
         gtin="6290362346548", catalogo=False, status="active"):
    return {"id": mlb, "title": titulo, "price": preco, "original_price": cheio, "available_quantity": disp,
            "sold_quantity": vendidos, "listing_type_id": "gold_special", "condition": "new",
            "permalink": f"https://produto.mercadolivre.com.br/{mlb.replace('MLB', 'MLB-')}-x", "thumbnail": "http://x/t.jpg",
            "pictures": [{"secure_url": f"https://x/{mlb}.jpg"}], "seller_id": vendedor, "category_id": cat,
            "catalog_listing": catalogo, "catalog_product_id": "MLB9990999" if catalogo else None,
            "shipping": {"free_shipping": frete, "logistic_type": "fulfillment" if full else "drop_off", "tags": ["self_service_in"]},
            "seller_address": {"city": {"name": "São Bernardo do Campo"}, "state": {"id": "BR-SP"}},
            "date_created": ISO(dias), "start_time": ISO(dias), "status": status,
            "attributes": [{"id": "GTIN", "value_name": gtin}, {"id": "BRAND", "value_name": "Lattafa"}]}


ITENS = {
    "MLB1000100": item("MLB1000100", "Perfume Árabe Asad Elixir Masculino Edp 100ml", 265.28, 111111111, dias=324, vendidos=1000, cheio=389.93, disp=2),
    "MLB2000200": item("MLB2000200", "Perfume Asad Elixir Lattafa 100ml", 279.00, 222222222, dias=342, vendidos=500, full=True),
    "MLB3000300": item("MLB3000300", "Kit 3 Canecas Martelada Moscow Mule", 69.90, 222222222, dias=120, vendidos=0, cat="MLB1234", gtin=""),
    "MLB4000400": item("MLB4000400", "Perfume Ferrari Black 125ml Eau De Toilette", 208.89, 222222222, dias=180, vendidos=1000, full=True, gtin="8002135111"),
}
USUARIOS = {
    111111111: {"id": 111111111, "nickname": "FINKE", "permalink": "https://perfil.mercadolivre.com.br/FINKE", "registration_date": ISO(3000),
         "address": {"city": "São Bernardo do Campo", "state": "BR-SP"},
         "seller_reputation": {"level_id": "4_light_green", "power_seller_status": None, "transactions": {"total": 8000, "completed": 7900}}},
    222222222: {"id": 222222222, "nickname": "ESSENCEPRIMEBR", "permalink": "https://perfil.mercadolivre.com.br/ESSENCEPRIMEBR", "registration_date": ISO(2500),
         "address": {"city": "Maringá", "state": "BR-PR"},
         "seller_reputation": {"level_id": "5_green", "power_seller_status": "platinum", "transactions": {"total": 25957, "completed": 25000}}},
}
VISITAS = {"MLB1000100": 2260, "MLB2000200": 3000, "MLB3000300": 22, "MLB4000400": 12100}


class Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class DubleML:
    """Responde como a API do ML; conta os pedidos (e os logins do app)."""

    def __init__(self):
        self.pedidos, self.logins, self.falhar_401 = [], 0, 0
        self.token_recusado = False

    def _json(self, d):
        return Resp(json.dumps(d).encode())

    def _erro(self, url, code, corpo=b"{}"):
        raise urllib.error.HTTPError(url, code, "x", {}, io.BytesIO(corpo))

    def __call__(self, req, timeout=None):
        url = req.full_url
        u = urllib.parse.urlparse(url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        p = u.path
        if p == "/oauth/token":
            self.logins += 1
            corpo = urllib.parse.parse_qs(req.data.decode())
            assert corpo["grant_type"] == ["client_credentials"]
            if self.token_recusado:
                self._erro(url, 400, b'{"error":"invalid_client"}')
            return self._json({"access_token": f"TOKEN{self.logins}", "expires_in": 21600})
        assert req.headers.get("Authorization", "").startswith("Bearer TOKEN"), req.headers
        self.pedidos.append(p)
        if self.falhar_401:
            self.falhar_401 -= 1
            self._erro(url, 401)
        if p == "/items":
            return self._json([{"code": 200, "body": ITENS[i]} if i in ITENS else {"code": 404, "body": {"id": i}}
                               for i in q["ids"].split(",")])
        m = p.split("/")
        if p.startswith("/users/") and p.endswith("/shipping_options/free"):
            return self._json({"coverage": {"all_country": {"list_cost": 24.45}}})
        if p.startswith("/users/"):
            u2 = USUARIOS.get(int(m[2]))
            return self._json(u2) if u2 else self._erro(url, 404)
        if p == "/items/visits":
            return self._json([{"item_id": i, "total_visits": VISITAS.get(i, 0)} for i in q["ids"].split(",")])
        if p == "/sites/MLB/search":
            res = [{"id": i} for i, x in ITENS.items() if str(x["seller_id"]) == q.get("seller_id")]
            off, lim = int(q.get("offset", 0)), int(q.get("limit", 50))
            return self._json({"paging": {"total": len(res)}, "results": res[off:off + lim]})
        if p == "/products/search":
            return self._json({"results": [{"id": "MLB9990999"}]} if q.get("product_identifier") == "6290362346548" else {"results": []})
        if p == "/products/MLB9990999/items":
            return self._json({"results": [
                {"item_id": "MLB2000200", "seller_id": 222222222, "price": 279.0, "shipping": {"free_shipping": True, "logistic_type": "fulfillment"}},
                {"item_id": "MLB1000100", "seller_id": 111111111, "price": 265.28, "original_price": 389.93,
                 "shipping": {"free_shipping": True, "logistic_type": "drop_off"}}]})
        if p == "/products/MLB9990999":
            return self._json({"id": "MLB9990999", "buy_box_winner": {"item_id": "MLB1000100"}})
        if p == "/sites/MLB/listing_prices":
            return self._json([{"sale_fee_amount": round(float(q["price"]) * 0.14 + 6.25, 2),
                                "sale_fee_details": {"percentage_fee": 14, "fixed_fee": 6.25}}])
        self._erro(url, 404)


def _preparar(chaves=True):
    for k in ("ML_CLIENT_ID", "ML_CLIENT_SECRET"):
        os.environ.pop(k, None)
    if chaves:
        os.environ["ML_CLIENT_ID"], os.environ["ML_CLIENT_SECRET"] = "123", "SEGREDO-NAO-VAZA"
    meli._TOKEN.update(valor=None, ate=0.0)
    meli._CACHE.clear()
    d = DubleML()
    meli._abrir = d
    return d


class Repo:
    def __init__(self):
        self.resumos = {}

    def _req(self, metodo, tabela, q=None, corpo=None, **k):
        if tabela == "ia_resumos" and metodo == "GET":
            c = (q or {}).get("chave", "")[3:]
            return [{"texto": self.resumos[c], "criado_em": "x"}] if c in self.resumos else []
        if tabela == "ia_resumos" and metodo == "POST":
            for r in corpo:
                self.resumos[r["chave"]] = r["texto"]
        return []


def test_sem_chave_avisa_e_nao_chama_nada():
    d = _preparar(chaves=False)
    try:
        meli.itens(["MLB1000100"])
        raise AssertionError("devia pedir as chaves")
    except meli.ErroMeli as e:
        assert "ML_CLIENT_ID" in str(e)
    assert d.pedidos == [] and d.logins == 0
    assert meli.testar()["chaves"] is False


def test_token_do_app_so_na_memoria_e_segredo_nunca_na_mensagem():
    d = _preparar()
    meli.itens(["MLB1000100"]); meli.lojas([111111111]); meli.visitas(["MLB1000100"])
    assert d.logins == 1                                            # um login do app para vários pedidos
    meli._CACHE.clear()
    d.falhar_401 = 1                                                # token vencido: pede outro e segue
    assert meli.itens(["MLB2000200"])["MLB2000200"]["titulo"].startswith("Perfume Asad")
    assert d.logins == 2
    d2 = _preparar()
    d2.token_recusado = True
    try:
        meli.itens(["MLB1000100"])
        raise AssertionError("devia recusar")
    except meli.ErroMeli as e:
        assert "SEGREDO" not in str(e) and "invalid_client" in str(e) and "TOKEN" not in str(e), str(e)


def test_codigos_e_links():
    c = meli.codigo_do_texto
    assert c("https://produto.mercadolivre.com.br/MLB-4577439527-perfume-ferrari-_JM") == ("item", "MLB4577439527")
    assert c("https://www.mercadolivre.com.br/perfume-asad/p/MLB12345678") == ("produto", "MLB12345678")
    assert c("https://www.mercadolivre.com.br/perfume/p/MLB12345678?pdp_filters=item_id:MLB4577439527") == ("item", "MLB4577439527")
    assert c("mlb4577439527") == ("item", "MLB4577439527")
    assert c("https://perfil.mercadolivre.com.br/ESSENCEPRIMEBR") == ("apelido", "ESSENCEPRIMEBR")
    assert c("https://lista.mercadolivre.com.br/_CustId_123456") == ("loja", "123456")
    assert c("qualquer coisa") is None
    assert meli.link_do_item("MLB4577439527") == "https://produto.mercadolivre.com.br/MLB-4577439527"


def test_anuncio_normalizado_com_loja_real():
    _preparar()
    m = meli.anuncios(["MLB1000100", "MLB4040404"], com_visitas=True)
    a = m["MLB1000100"]
    assert a["preco"] == 265.28 and a["preco_cheio"] == 389.93 and a["tipo"] == "Clássico" and a["frete_gratis"] and not a["full"]
    assert a["flex"] and a["cidade"] == "São Bernardo do Campo" and a["uf"] == "SP" and a["dias_pub"] == 324 and a["gtin"] == "6290362346548"
    assert a["foto"] == "https://x/MLB1000100.jpg" and a["link"].startswith("https://produto.mercadolivre.com.br/MLB-100")
    assert a["loja"]["nome"] == "FINKE" and a["loja"]["nivel"] == 4 and a["loja"]["uf"] == "SP"
    assert a["visitas"] == {"total": 2260, "por_dia": 75.3}
    assert m["MLB4040404"] == {"anuncio": "MLB4040404", "sumiu": True}
    b = meli.anuncios(["MLB2000200"])["MLB2000200"]
    assert b["preco_cheio"] is None and b["full"] and b["loja"]["medalha"] == "Platinum" and b["loja"]["nivel"] == 5


def test_pagina_do_anuncio_nota_kpis_tarifa_e_frete():
    _preparar()
    m = meli.pagina_anuncio("https://produto.mercadolivre.com.br/MLB-1000100-perfume")
    an = m["analise"]
    assert 60 <= an["nota"] <= 80 and an["rotulo"] == "Anúncio forte", an
    assert an["pontos"][0]["tipo"] == "alerta" and "2 unidades" in an["pontos"][0]["texto"]      # estoque acabando vem primeiro
    textos = " ".join(p["texto"] for p in an["pontos"])
    assert "2,3k visitas" in textos and "4,1%" in textos and "fora do filtro de Full" in textos, textos
    k = an["kpis"]
    assert k["vendas_totais"] == 1000 and k["visitas_30d"] == 2260 and k["visitas_dia"] == 75 and 4.0 <= k["conversao"] <= 4.2
    assert m["tarifa"]["pct"] == 14 and m["tarifa"]["fixa"] == 6.25 and m["frete_custo"] == 24.45
    # página de catálogo (/p/) -> o anúncio que está ganhando
    assert meli.pagina_anuncio("https://www.mercadolivre.com.br/x/p/MLB9990999")["anuncio"] == "MLB1000100"


def test_pagina_da_loja_insights_e_cache():
    d = _preparar()
    r = Repo()
    p = meli.pagina_loja(r, "https://produto.mercadolivre.com.br/MLB-2000200-x")
    assert p["loja"]["nome"] == "ESSENCEPRIMEBR" and p["loja"]["anuncios"] == 3 and len(p["produtos"]) == 3
    titulos = [i["titulo"] for i in p["insights"]]
    assert "Faturamento acumulado estimado" in titulos and "Perfil: Veterano" in titulos, titulos
    textos = " ".join(i["texto"] for i in p["insights"])
    assert "analisados, os produtos dele acumulam cerca de R$ 348.390 em vendas" in textos and "reputação 5/5" in textos, textos
    assert any(t.startswith("Cauda morta") for t in titulos) and "Logística: Full" in titulos, titulos
    k = p["kpis"]
    assert k["vendas_totais"] == 1500 and k["visitas_30d"] == 15122 and k["destaque"]["anuncio"] == "MLB4000400"
    assert round(k["mercado"]) == round(279 * 500 + 208.89 * 1000)
    antes = len(d.pedidos)
    assert meli.pagina_loja(r, "222222222")["loja"]["nome"] == "ESSENCEPRIMEBR" and len(d.pedidos) == antes     # 6 h de cache


def test_catalogo_pelo_gtin_quem_vende_agora():
    _preparar()
    xs = meli.por_gtin(["6290362346548", "000"])
    assert [x["anuncio"] for x in xs] == ["MLB1000100", "MLB2000200"]                          # do mais barato para o mais caro
    assert xs[0]["loja"]["nome"] == "FINKE" and xs[0]["preco_cheio"] == 389.93 and xs[1]["full"] is True
    assert xs[1]["loja"]["nome"] == "ESSENCEPRIMEBR" and xs[1]["link"].startswith("https://produto.mercadolivre.com.br/")


def test_vendedor_embaralhado_do_nubimetrics_vira_a_loja_real():
    _preparar()
    ml = meli.por_gtin(["6290362346548"])
    ref = HOJE.date() - timedelta(days=2)                                    # export de 2 dias atrás
    linhas = [
        {"vendedor_id": "hashA", "gtin": "6290362346548", "preco": 265.28, "full": False, "dias_pub": 322},   # FINKE, idade exata
        {"vendedor_id": "hashB", "gtin": "6290362346548", "preco": 279.00, "full": True, "dias_pub": None},
        {"vendedor_id": "hashB", "gtin": "6290362346548", "preco": 279.50, "full": True, "dias_pub": None},   # 2 votos
        {"vendedor_id": "hashC", "gtin": "6290362346548", "preco": 279.00, "full": False, "dias_pub": None},  # Full não bate
        {"vendedor_id": "hashD", "gtin": "6290362346548", "preco": 265.28, "full": False, "dias_pub": 200}]   # idade não bate
    m = meli.casar_vendedores(linhas, ml, ref)
    assert m["hashA"]["nome"] == "FINKE" and m["hashA"]["confianca"] == "provável"
    assert m["hashB"]["nome"] == "ESSENCEPRIMEBR" and m["hashB"]["votos"] == 2
    assert "hashC" not in m and "hashD" not in m, m
    r = Repo()
    meli.gravar_hash_lojas(r, {"hashA": dict(m["hashA"], confianca="manual")})
    meli.gravar_hash_lojas(r, {"hashA": {"id": "99", "nome": "OUTRA", "confianca": "provável"}, "hashB": m["hashB"]})
    lido = meli.ler_hash_lojas(r)
    assert lido["hashA"]["nome"] == "FINKE" and lido["hashB"]["nome"] == "ESSENCEPRIMEBR"      # o manual não é trocado


def test_diagnostico_com_chaves():
    _preparar()
    t = meli.testar("MLB1000100", "6290362346548")
    assert t["chaves"] is True and all(p["ok"] for p in t["passos"]), t
    assert [p["passo"] for p in t["passos"]][0] == "token do app"


def test_rotas_do_servidor_ligam_o_vendedor_do_nubimetrics_a_loja():
    """nubi_web: catálogo do produto casa os hashes do Nubimetrics (e grava o de-para); descobrir a loja de um hash; o Bruno
    informa a loja à mão; a página da loja traz os NOSSOS números (Nubimetrics) dos hashes ligados."""
    os.environ.setdefault("OLLAMA_API_KEY", "x")
    os.environ.setdefault("ANTHROPIC_API_KEY", "x")
    import pandas as pd
    import nubi_web as w
    _preparar()
    exp = (HOJE - timedelta(days=2)).isoformat()

    class R(Repo):
        def snapshots(self, marca=None):
            df = pd.DataFrame([{"id": 7, "marca": "LATTAFA", "inicio": "2026-08-01", "fim": "2026-09-27", "importado_em": exp},
                               {"id": 8, "marca": "LIPX", "inicio": "2026-08-01", "fim": "2026-09-27", "importado_em": exp}])
            return df[df["marca"] == marca] if marca else df

        def _todos(self, t, q=None):
            assert t == "anuncios"
            linhas = [
                {"vendedor_id": "a" * 64, "vendedor": "HIMALAIA.INDIGO", "gtin": "6290362346548", "sku": "X", "preco": 265.28, "full": False,
                 "dias_pub": 322, "un": 2800, "fat": 742000, "produto": "Lattafa Asad Elixir EDP 100 ml", "titulo": "Asad Elixir", "snapshot_id": 7, "tipo": "EDP"},
                {"vendedor_id": "b" * 64, "vendedor": "ICARBONXX P3", "gtin": "6290362346548", "sku": "ASADELIXIR", "preco": 279.0, "full": True,
                 "dias_pub": 340, "un": 1300, "fat": 363000, "produto": "Lattafa Asad Elixir EDP 100 ml", "titulo": "Asad Elixir", "snapshot_id": 8, "tipo": "EDP"},
                {"vendedor_id": "b" * 64, "vendedor": "ICARBONXX P3", "gtin": "", "sku": "ASADELIXIR", "preco": 274.9, "full": True,
                 "dias_pub": 161, "un": 740, "fat": 204000, "produto": "Lattafa Asad Elixir EDP 100 ml", "titulo": "Asad Elixir", "snapshot_id": 8, "tipo": "EDP"}]
            ids = [int(x) for x in q["snapshot_id"][4:-1].split(",")]
            linhas = [l for l in linhas if l["snapshot_id"] in ids]
            if "gtin" in q:
                linhas = [l for l in linhas if l["gtin"] in q["gtin"][4:-1].split(",")]
            if "vendedor_id" in q:
                v = q["vendedor_id"]
                linhas = [l for l in linhas if (v.startswith("eq.") and l["vendedor_id"] == v[3:]) or (v.startswith("in.") and l["vendedor_id"] in v[4:-1].split(","))]
            return linhas

    r = R()
    out = w.rota_meli(r, "GET", "meli_gtin", {"marca": "LATTAFA", "gtins": "6290362346548"}, b"")
    assert [x["loja"]["nome"] for x in out["anuncios"]] == ["FINKE", "ESSENCEPRIMEBR"]
    assert out["casados"]["a" * 64]["nome"] == "FINKE"                         # HIMALAIA (Nubimetrics) = FINKE (preço, idade, sem Full)
    assert meli.ler_hash_lojas(r)["a" * 64]["id"] == "111111111"
    d = w.rota_meli(r, "POST", "meli_descobrir", {}, json.dumps({"vendedor_id": "b" * 64}).encode())
    assert d["achou"] and d["loja"]["nome"] == "ESSENCEPRIMEBR" and d["loja"]["medalha"] == "Platinum", d
    n = w.rota_meli(r, "POST", "meli_nomear", {}, json.dumps({"vendedor_id": "b" * 64, "loja": "https://produto.mercadolivre.com.br/MLB-1000100-x"}).encode())
    assert n["loja"]["nome"] == "FINKE" and meli.ler_hash_lojas(r)["b" * 64]["confianca"] == "manual"
    p = w.rota_meli(r, "GET", "meli_loja", {"id": "111111111"}, b"")
    nb = p["nubimetrics"]
    assert set(nb["nomes"]) == {"HIMALAIA.INDIGO", "ICARBONXX P3"} and nb["un"] == 2800 + 1300 + 740, nb
    assert nb["produtos"][0]["produto"] == "Lattafa Asad Elixir EDP 100 ml"
    try:
        w.rota_meli(r, "POST", "meli_descobrir", {}, json.dumps({"vendedor_id": "x'; drop"}).encode())
        raise AssertionError("aceitou vendedor inválido")
    except w.ErroNuvem:
        pass


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
