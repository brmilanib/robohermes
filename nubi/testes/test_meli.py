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
USUARIOS[2540338692] = {"id": 2540338692, "nickname": "KAIDOXSTOREE", "permalink": "https://perfil.mercadolivre.com.br/KAIDOXSTOREE",
                       "registration_date": ISO(1500), "address": {"city": "São Paulo", "state": "BR-SP"}, "tags": ["brand"],
                       "seller_reputation": {"level_id": "5_green", "power_seller_status": "platinum", "transactions": {"total": 180000, "completed": 179000}}}
USUARIOS[1395403852] = {"id": 1395403852, "nickname": "LUH20230609125415", "permalink": "http://perfil.mercadolivre.com.br/LUH20230609125415",
                       "registration_date": ISO(800), "address": {"city": "Curitiba", "state": "BR-PR"},
                       "seller_reputation": {"level_id": "4_light_green", "transactions": {"total": 230, "completed": 225}}}


def _of(mlb, vendedor, preco, full, oficial=None, tipo="gold_special", cheio=None):
    return {"item_id": mlb, "seller_id": vendedor, "price": preco, "original_price": cheio, "listing_type_id": tipo,
            "official_store_id": oficial, "condition": "new",
            "shipping": {"free_shipping": True, "logistic_type": "fulfillment" if full else "drop_off"}}


# catálogo: produto -> ofertas. 29/09 (ICARBONXX): a loja certa (2540338692, loja oficial 23829, Full) fica DEPOIS das 50
# primeiras ofertas; a LUH (1395403852, sem Full) aparece em todos os produtos dele, com preço parecido
PRODUTOS = {"6290362346548": "MLB9990999", "7899463112978": "MLB8880888", "6290360598352": "MLB7770777"}
OFERTAS = {
    "MLB9990999": [_of("MLB2000200", 222222222, 279.0, True, oficial=555),
                   _of("MLB1000100", 111111111, 265.28, False, cheio=389.93)],
    "MLB8880888": ([_of("MLB5000001", 1395403852, 148.0, False)]
                   + [_of(f"MLB59{i:05d}", 900000 + i, 120.0 + i, i % 3 == 0) for i in range(80)]
                   + [_of("MLB5000002", 2540338692, 142.9, True, oficial=23829)]
                   + [_of(f"MLB58{i:05d}", 800000 + i, 150.0 + i, i % 2 == 0) for i in range(40)]),
    "MLB7770777": ([_of("MLB6000001", 1395403852, 190.0, False)] + [_of(f"MLB69{i:05d}", 700000 + i, 180.0 + i, True) for i in range(60)]
                   + [_of("MLB6000002", 2540338692, 216.9, True, oficial=23829)]),
}
NOMES_PRODUTO = {"MLB9990999": "Lattafa Asad Elixir Eau de Parfum 100 ml", "MLB8880888": "Sabah Al Ward Sugar 100 ml",
                 "MLB7770777": "Lattafa The Kingdom Eau de Parfum 100 ml"}


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
        self.bloq_varios = self.bloq_um = self.bloq_busca = False      # o que o ML recusa para o token do app

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
            g = corpo["grant_type"][0]
            if g == "authorization_code":                    # conta do usuário: o código da volta do login
                assert corpo["code"] == ["CODIGO-OK"] and corpo["redirect_uri"][0].endswith("meli_retorno")
                self.refresh = "R1"
                return self._json({"access_token": "TOKEN-U1", "refresh_token": "R1", "expires_in": 21600, "user_id": 777})
            if g == "refresh_token":                         # o ML troca o refresh a cada uso
                assert corpo["refresh_token"] == [self.refresh], (corpo, self.refresh)
                n = int(self.refresh[1:]) + 1
                self.refresh = f"R{n}"
                return self._json({"access_token": f"TOKEN-U{n}", "refresh_token": self.refresh, "expires_in": 21600})
            assert g == "client_credentials"
            if self.token_recusado:
                self._erro(url, 400, b'{"error":"invalid_client"}')
            return self._json({"access_token": f"TOKEN{self.logins}", "expires_in": 21600})
        assert req.headers.get("Authorization", "").startswith("Bearer TOKEN"), req.headers
        self.pedidos.append(p)
        if self.falhar_401:
            self.falhar_401 -= 1
            self._erro(url, 401)
        self.usuario = req.headers.get("Authorization", "").startswith("Bearer TOKEN-U")
        if p == "/items":
            if self.bloq_varios and not self.usuario:
                self._erro(url, 403, b'{"message":"forbidden","error":"forbidden"}')
            return self._json([{"code": 200, "body": ITENS[i]} if i in ITENS else {"code": 404, "body": {"id": i}}
                               for i in q["ids"].split(",")])
        m = p.split("/")
        if p == "/users/me":
            return self._json({"id": 777, "nickname": "TESTE_BRUNO"})
        if len(m) == 3 and m[1] == "items" and m[2].startswith("MLB"):
            if self.bloq_um and not self.usuario:           # com a conta do usuário o ML libera
                self._erro(url, 403, b'{"message":"forbidden"}')
            return self._json(ITENS[m[2]]) if m[2] in ITENS else self._erro(url, 404)
        if p.startswith("/users/") and p.endswith("/shipping_options/free"):
            return self._json({"coverage": {"all_country": {"list_cost": 24.45}}})
        if p.startswith("/users/"):
            u2 = USUARIOS.get(int(m[2]))
            return self._json(u2) if u2 else self._erro(url, 404)
        if len(m) == 5 and m[1] == "items" and m[3] == "visits" and m[4] == "time_window":
            passo = {"day": 1, "week": 7, "month": 30}[q["unit"]]
            n = int(q["last"])
            if q["unit"] == "day" and n > 150:                  # produção: a janela por dia vai até 150
                self._erro(url, 400, b'{"message":"last must be lower than 150"}')
            ini = HOJE.date() - timedelta(days=passo * (n - 1))
            entrou = {"MLB2000200": HOJE.date() - timedelta(days=100), "MLB4000400": HOJE.date() - timedelta(days=300)}.get(m[2])
            return self._json({"item_id": m[2], "results": [{"date": f"{ini + timedelta(days=passo * k)}T00:00:00Z",
                                                             "total": (30 if ini + timedelta(days=passo * (k + 1)) > entrou else 0) if entrou else 5}
                                                            for k in range(n)]})
        if p == "/items/visits":
            return self._json([{"item_id": i, "total_visits": VISITAS.get(i, 0)} for i in q["ids"].split(",")])
        if p == "/sites/MLB/search":
            if self.bloq_busca:
                self._erro(url, 403, b'{"message":"forbidden","error":"forbidden","status":403}')
            res = [{"id": i} for i, x in ITENS.items() if str(x["seller_id"]) == q.get("seller_id")]
            off, lim = int(q.get("offset", 0)), int(q.get("limit", 50))
            return self._json({"paging": {"total": len(res)}, "results": res[off:off + lim]})
        if p == "/products/search":
            pid = PRODUTOS.get(q.get("product_identifier"))
            return self._json({"results": [{"id": pid}] if pid else []})
        if len(m) == 4 and m[1] == "products" and m[3] == "items" and m[2] in OFERTAS:
            xs = OFERTAS[m[2]]
            off, lim = int(q.get("offset", 0)), int(q.get("limit", 50))
            assert lim <= 50, "o ML devolve no máximo 50 por página"
            return self._json({"paging": {"total": len(xs), "offset": off, "limit": lim}, "results": xs[off:off + lim]})
        if len(m) == 3 and m[1] == "products" and m[2] in NOMES_PRODUTO:
            return self._json({"id": m[2], "name": NOMES_PRODUTO[m[2]],
                               "pictures": [{"url": "http://x/prod.jpg"}], "permalink": f"https://www.mercadolivre.com.br/p/{m[2]}",
                               "buy_box_winner": {"item_id": "MLB1000100"} if m[2] == "MLB9990999" else {}})
        if p == "/sites/MLB/categories":
            return self._json([{"id": "MLB1246", "name": "Beleza e Cuidado Pessoal"}, {"id": "MLB1000", "name": "Eletrônicos"}])
        if p.startswith("/trends/MLB"):
            base = [{"keyword": "asad elixir", "url": "http://lista.mercadolivre.com.br/asad-elixir"}] if p.endswith("MLB1246") else []
            return self._json(base + [{"keyword": "starlink mini", "url": "https://lista.mercadolivre.com.br/starlink-mini"}])
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

    def _eq(self, v):
        return f"eq.{v}"

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
        {"vendedor_id": "hashB", "gtin": "6290362346548", "preco": 279.50, "full": True, "dias_pub": None},   # só preço: não basta
        {"vendedor_id": "hashC", "gtin": "6290362346548", "preco": 279.00, "full": False, "dias_pub": None},  # Full não bate
        {"vendedor_id": "hashD", "gtin": "6290362346548", "preco": 265.28, "full": False, "dias_pub": 200},   # idade não bate
        {"vendedor_id": "hashE", "gtin": "6290362346548", "preco": 279.50, "full": True, "loja_oficial_id": 555},  # loja oficial + preço
        {"vendedor_id": "hashG", "gtin": "6290362346548", "preco": 289.00, "full": True, "loja_oficial_id": 555},  # só a loja oficial
        {"vendedor_id": "hashF", "gtin": "6290362346548", "preco": 279.00, "full": True, "loja_oficial_id": 0}]    # não é loja oficial
    assert "hashE" not in meli.casar_vendedores(linhas, ml, ref)             # nº do Nubimetrics sem tradução: não prova
    m = meli.casar_vendedores(linhas, ml, ref, oficiais={555: 555})           # tradução aprendida com o Bruno
    assert m["hashA"]["nome"] == "FINKE" and m["hashA"]["confianca"] == "provável"
    assert m["hashE"]["nome"] == "ESSENCEPRIMEBR" and m["hashE"]["confianca"] == "certa" and "loja oficial nº 555" in m["hashE"]["prova"]
    # 29/09 (ICARBONXX): preço parecido num produto só não prova nada (várias lojas cobram o mesmo) -> não liga
    # o nº da loja oficial pode ser de mais de um vendedor (20309 aparece em 5 no Explorador): num produto só precisa do preço
    assert "hashB" not in m and "hashC" not in m and "hashD" not in m and "hashF" not in m and "hashG" not in m, m
    r = Repo()
    meli.gravar_hash_lojas(r, {"hashA": dict(m["hashA"], confianca="manual")})
    meli.gravar_hash_lojas(r, {"hashA": {"id": "99", "nome": "OUTRA", "confianca": "provável"}, "hashE": m["hashE"]})
    lido = meli.ler_hash_lojas(r)
    assert lido["hashA"]["nome"] == "FINKE" and lido["hashE"]["nome"] == "ESSENCEPRIMEBR"      # o manual não é trocado
    meli.gravar_hash_lojas(r, {}, tirar=["hashA", "hashE"])                                     # o automático sai, o manual fica
    assert set(meli.ler_hash_lojas(r)) == {"hashA"}
    assert meli.loja_oficial_do_texto("LOJA.OFICIAL.23829") == 23829 and meli.loja_oficial_do_texto("") is None


def test_hash_do_nubimetrics_tem_chave_secreta():
    # 29/09: PUREHOME (loja do Bruno) no Explorador x os MLB dela no relatório do UpSeller. Nenhum formato comum de hash
    # (sha256/sha512/md5/sha3/blake2 do MLB ou do número) bate: por isso a loja real sai do catálogo, não do hash.
    import hashlib
    mlb, hash_nubimetrics = "MLB6365511140", "125825609286136e13e4beb32c28adbb2236c09bde4c8ef873a98082bbaf1bf3"
    for v in (mlb, mlb[3:], mlb.lower(), "MLB-" + mlb[3:]):
        for a in ("sha256", "sha3_256", "blake2s", "sha512", "md5"):
            assert hashlib.new(a, v.encode()).hexdigest()[:64] != hash_nubimetrics


def test_catalogo_le_todas_as_paginas_e_o_numero_da_loja_oficial():
    d = _preparar()
    xs = meli.ofertas_do_produto("MLB8880888")
    assert len(xs) == 122 and d.pedidos.count("/products/MLB8880888/items") == 3             # 50 + 50 + 22
    o = [meli._oferta("MLB8880888", "7899463112978", x) for x in xs if x["seller_id"] == 2540338692][0]
    assert o["loja_oficial"] == 23829 and o["_tem_oficial"] and o["full"] and o["link"] == "https://produto.mercadolivre.com.br/MLB-5000002"
    antes = len(d.pedidos)
    meli.ofertas_do_produto("MLB8880888")
    assert len(d.pedidos) == antes                                                           # 20 min de cache
    assert len(meli.ofertas_por_gtin(["7899463112978"], maximo=50)) == 50                   # a tela do produto lê só a 1ª página
    assert meli.TOTAL_OFERTAS["MLB8880888"] == 122 and len(meli.ofertas_do_produto("MLB8880888", maximo=100)) == 100
    t = meli.testar("MLB1000100", "7899463112978")
    assert any(p["passo"] == "todas as páginas do catálogo" and "122 ofertas lidas de 122 no catálogo" in p["detalhe"] for p in t["passos"]), t
    assert meli.ofertas_do_produto("MLB0000000") == []                                       # produto sem oferta: vazio, sem erro
    # o ML manda o perfil da loja em http:// ("abrir no ML" abria o próprio nubi): sai sempre https://
    assert meli.lojas([1395403852])["1395403852"]["link"] == "https://perfil.mercadolivre.com.br/LUH20230609125415"


def test_loja_oficial_acha_a_loja_certa_e_nao_a_parecida():
    """29/09 (Bruno): 'o teste com icarbonx não rolou, trouxe uma loja nada a ver'. A LUH (sem Full) aparecia nos produtos
    dele com preço parecido; a certa está depois da 1ª página. Com o nº da loja oficial do Explorador sai a certa."""
    _preparar()
    hoje = HOJE.date()
    exp = [{"vendedor_id": "b" * 64, "gtin": "7899463112978", "preco": 142.9, "full": 1, "catalogo": 1, "loja_oficial_id": 23829,
            "exposicao": "Clássica", "un": 8600, "data_ref": hoje - timedelta(days=1)},
           {"vendedor_id": "b" * 64, "gtin": "6290360598352", "preco": 219.9, "full": 1, "catalogo": 1, "loja_oficial_id": 23829,
            "exposicao": "Clássica", "un": 2600, "data_ref": hoje - timedelta(days=1)}]
    refs = [meli.ref_explorador(l, hoje) for l in exp]
    ofs = meli.ofertas_por_gtin(["7899463112978", "6290360598352"])
    x0, c0 = meli.achar_loja("ICARBONXX P3", refs, ofs)                       # sem a tradução do nº: não liga sozinho
    assert x0 is None and c0[0]["id"] == "2540338692" and all(c["id"] != "1395403852" for c in c0), (x0, c0)
    x, cands = meli.achar_loja("ICARBONXX P3", refs, ofs, oficiais={23829: 23829})
    assert x["id"] == "2540338692" and x["nome"] == "KAIDOXSTOREE" and x["confianca"] == "certa", (x, cands)
    assert x["oficial"] == [23829] and "loja oficial nº 23829" in x["prova"] and x["votos"] == 2 and x["sondados"] == 2
    assert {a["anuncio"] for a in x["anuncios"]} == {"MLB5000002", "MLB6000002"}
    assert x["anuncios"][0]["titulo"] and x["anuncios"][0]["link"].startswith("https://produto.mercadolivre.com.br/MLB-")
    assert all(c["id"] != "1395403852" for c in cands)                                        # a LUH não tem Full: fora
    # só o relatório do seguido (preço MÉDIO do mês, sem loja oficial): Full e preço perto nos 2 produtos -> provável
    seg = [{"gtins": ["7899463112978", "5055810099459"], "preco": 142.9, "full": True, "catalogo": True, "tipo": "Clássico"},
           {"gtins": ["6290360598352"], "preco": 216.86, "full": True, "catalogo": True, "tipo": "Clássico"}]
    x2, _ = meli.achar_loja("ICARBONXX P3", seg, ofs)
    assert x2 and x2["id"] == "2540338692" and x2["confianca"] == "provável", x2
    # 29/09 (ROCHA -> OUD_ESSENCE): vendedor de loja oficial no Explorador, casando só pelo relatório do mês -> não liga
    rocha = seg + [dict(r, catalogo=False) for r in refs]                     # o Explorador diz: loja oficial 23829
    xr, cr = meli.achar_loja("ROCHA IMPORTADOS", rocha, ofs)
    assert xr is None and cr[0]["id"] == "2540338692", (xr, cr)
    xr2, _ = meli.achar_loja("KAIDOXSTOREE P1", rocha, ofs)                   # com o nome batendo, liga
    assert xr2 and xr2["id"] == "2540338692" and xr2["confianca"] == "provável" and xr2["nome_bate"]
    # um produto só e preço médio: não dá certeza -> não escolhe, mostra as candidatas
    x3, c3 = meli.achar_loja("ICARBONXX P3", seg[:1], ofs)
    assert x3 is None and c3 and c3[0]["id"] == "2540338692" and "em 1 de 1 produto" in c3[0]["prova"], c3
    # trava do Cowork: ele vende 25,7 mil un./mês; loja com menos de metade disso em vendas NA VIDA não pode ser ele
    x4, _ = meli.achar_loja("ICARBONXX P3", refs, ofs, un_mes=25708, oficiais={23829: 23829})
    assert x4["id"] == "2540338692"                                                          # 180 mil vendas na vida: passa
    assert meli.achar_loja("ICARBONXX P3", refs, ofs, un_mes=400000, oficiais={23829: 23829}) == (None, [])           # ninguém tem 200 mil: nenhuma
    luh = [dict(r, full=False, loja_oficial=0) for r in refs]                                # o que casaria com a LUH
    x5, c5 = meli.achar_loja("X", luh, ofs, un_mes=25708)
    assert x5 is None and all(c["id"] != "1395403852" for c in c5), (x5, c5)                  # 230 vendas na vida: fora


def test_sem_o_anuncio_o_nubi_para_de_pedir():
    # 29/09 (produção): /items de outra loja não vem para o token do app; depois de 3 falhas seguidas não repete 40 pedidos
    d = _preparar()
    d.bloq_varios = d.bloq_um = True
    r = meli.itens(["MLB1000100", "MLB2000200", "MLB4000400"])
    assert all(v.get("bloqueado") for v in r.values())
    antes = len(d.pedidos)
    assert meli.itens(["MLB3000300"])["MLB3000300"]["bloqueado"] and len(d.pedidos) == antes


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
            if t != "anuncios":
                return []                                        # não é vendedor seguido
            nada = {"Loja oficial": "", "Exposição": "Clássica"}
            oficial = {"Loja oficial": "LOJA.OFICIAL.555", "Exposição": "Clássica"}
            linhas = [
                {"vendedor_id": "a" * 64, "vendedor": "HIMALAIA.INDIGO", "gtin": "6290362346548", "sku": "X", "preco": 265.28, "full": False,
                 "dias_pub": 322, "un": 2800, "fat": 742000, "produto": "Lattafa Asad Elixir EDP 100 ml", "titulo": "Asad Elixir", "snapshot_id": 7,
                 "tipo": "EDP", "loja_oficial": 0, "catalogo": 1, "bruto": dict(nada)},
                {"vendedor_id": "b" * 64, "vendedor": "ICARBONXX P3", "gtin": "6290362346548", "sku": "ASADELIXIR", "preco": 279.0, "full": True,
                 "dias_pub": 340, "un": 1300, "fat": 363000, "produto": "Lattafa Asad Elixir EDP 100 ml", "titulo": "Asad Elixir", "snapshot_id": 8,
                 "tipo": "EDP", "loja_oficial": 1, "catalogo": 1, "bruto": dict(oficial)},
                {"vendedor_id": "b" * 64, "vendedor": "ICARBONXX P3", "gtin": "", "sku": "ASADELIXIR", "preco": 274.9, "full": True,
                 "dias_pub": 161, "un": 740, "fat": 204000, "produto": "Lattafa Asad Elixir EDP 100 ml", "titulo": "Asad Elixir", "snapshot_id": 8,
                 "tipo": "EDP", "loja_oficial": 1, "catalogo": 1, "bruto": json.dumps(oficial)}]
            if "snapshot_id" in q:
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
    assert not d["achou"] and d["candidatas"][0]["nome"] == "ESSENCEPRIMEBR", d      # nº do Nubimetrics sem tradução
    r.resumos[w.OFICIAIS] = json.dumps({"555": 555})                                # aprendida com uma loja confirmada
    d = w.rota_meli(r, "POST", "meli_descobrir", {}, json.dumps({"vendedor_id": "b" * 64}).encode())
    assert d["achou"] and d["loja"]["nome"] == "ESSENCEPRIMEBR" and d["loja"]["medalha"] == "Platinum", d
    assert d["loja"]["confianca"] == "certa" and d["loja"]["oficial"] == [555]      # nº da loja oficial do Explorador = do ML
    n = w.rota_meli(r, "POST", "meli_nomear", {}, json.dumps({"vendedor_id": "b" * 64, "loja": "https://produto.mercadolivre.com.br/MLB-1000100-x"}).encode())
    assert n["loja"]["nome"] == "FINKE" and meli.ler_hash_lojas(r)["b" * 64]["confianca"] == "manual"
    # o botão 🔌 confere, nas lojas confirmadas à mão, se o nº da loja oficial do Explorador é o do ML
    t = w.rota_meli(r, "GET", "meli_teste", {}, b"")
    p = [x for x in t["passos"] if x["passo"].startswith("nº da loja oficial")][0]
    assert p["ok"] and "1 aprendida" in p["detalhe"] and "FINKE: Explorador 555 x ML sem nº (1 oferta(s))" in p["detalhe"] and "NÃO é o do ML" in p["detalhe"], p
    guardado = r.resumos[meli.HASH_LOJAS]                                       # (o manual não se troca: troca direto)
    r.resumos[meli.HASH_LOJAS] = json.dumps({**json.loads(guardado), "b" * 64: {"id": "222222222", "nome": "ESSENCEPRIMEBR",
                                                                                "confianca": "manual"}})
    p = [x for x in w.rota_meli(r, "GET", "meli_teste", {}, b"")["passos"] if x["passo"].startswith("nº da loja oficial")][0]
    assert p["ok"] and "Explorador 555 x ML 555" in p["detalhe"] and "a prova da loja oficial vale" in p["detalhe"], p
    assert json.loads(r.resumos[w.OFICIAIS]) == {"555": 555}                    # aprendeu a tradução com a confirmada
    r.resumos[meli.HASH_LOJAS] = guardado
    meli.gravar_hash_lojas(r, {"c" * 64: {"id": "3153658428", "nome": "GLBRASIL2026", "confianca": "provável", "votos": 2}})
    hl = w.rota_meli(r, "GET", "meli_hash_lojas", {}, b"")                       # a tela #/ml mostra o nome de lá
    assert "c" * 64 not in hl["lojas"]                                         # regra antiga, sem prova: some da tela
    assert hl["nomes"] == {"a" * 64: "HIMALAIA.INDIGO", "b" * 64: "ICARBONXX P3"} and hl["lojas"]["b" * 64]["confianca"] == "manual", hl
    p = w.rota_meli(r, "GET", "meli_loja", {"id": "111111111"}, b"")
    nb = p["nubimetrics"]
    assert set(nb["nomes"]) == {"HIMALAIA.INDIGO", "ICARBONXX P3"} and nb["un"] == 2800 + 1300 + 740, nb
    assert nb["produtos"][0]["produto"] == "Lattafa Asad Elixir EDP 100 ml"
    try:
        w.rota_meli(r, "POST", "meli_descobrir", {}, json.dumps({"vendedor_id": "x'; drop"}).encode())
        raise AssertionError("aceitou vendedor inválido")
    except w.ErroNuvem:
        pass



def test_ml_recusa_o_pedido_de_varios_e_a_busca_por_loja():
    # 29/09 (produção): /items?ids= não devolveu o anúncio e /sites/MLB/search deu 403 para o token do app
    d = _preparar()
    d.bloq_varios = True
    m = meli.itens(["MLB1000100"])["MLB1000100"]
    assert m["titulo"].startswith("Perfume Árabe Asad")                # veio um por um
    d2 = _preparar()
    d2.bloq_varios = d2.bloq_um = True
    assert meli.itens(["MLB1000100"])["MLB1000100"]["bloqueado"] is True
    xs = meli.por_gtin(["6290362346548"])                                  # título e foto vêm do produto de catálogo
    assert xs[0]["titulo"] == "Lattafa Asad Elixir Eau de Parfum 100 ml" and xs[0]["foto"] == "https://x/prod.jpg"
    assert xs[0]["loja"]["nome"] == "FINKE" and xs[0]["link"].startswith("https://produto.mercadolivre.com.br/MLB-")
    try:
        meli.pagina_anuncio("MLB1000100")
        raise AssertionError("devia avisar que o ML não libera")
    except meli.ErroMeli as e:
        assert "não libera" in str(e)
    d3 = _preparar()
    d3.bloq_busca = True
    prods, total, fonte = meli.produtos_da_loja("222222222", gtins_fn=lambda sid: ["6290362346548"])
    assert fonte == "catálogo" and total is None and [p["anuncio"] for p in prods] == ["MLB2000200"], prods
    assert prods[0]["visitas"]["total"] == 3000
    assert meli.produtos_da_loja("222222222")[2] == "bloqueada"
    try:
        meli._get("/sites/MLB/search", {"seller_id": 1})
    except meli.Bloqueado as e:
        assert "403" in str(e) and "forbidden" in str(e)
    t = meli.testar("MLB1000100", "6290362346548")
    assert [p["ok"] for p in t["passos"]][-1] is False and all(p["ok"] for p in t["passos"][:-1]), t


def test_vendedor_seguido_nome_do_bruno_so_desempata():
    # 29/09 (Bruno): "o nome ICARBONXX foi eu que coloquei" -> o nome do seguido não prova nada sozinho
    assert meli.gtins_do_texto("78994631129785055810099459") == ["7899463112978", "5055810099459"]
    assert meli.gtins_do_texto("6290362346548") == ["6290362346548"] and meli.gtins_do_texto("123") == []
    assert meli._base_nome("ICARBONXX P3") == "ICARBONXX" and meli._base_nome("MAMS ECOMMERCE TOP14") == "MAMSECOMMERCE"
    _preparar()
    ofs = meli.ofertas_por_gtin(["6290362346548"])
    refs = [{"gtins": ["6290362346548"], "preco": 281.0, "full": True, "catalogo": True}]
    x, cands = meli.achar_loja("ESSENCE PRIME P9", refs, ofs)                       # nome parecido, 1 produto, preço médio
    assert x is None and cands[0]["nome"] == "ESSENCEPRIMEBR" and "nome parecido" in cands[0]["prova"], cands
    assert meli.achar_loja("XYZ", [{"gtins": ["000"], "preco": 1, "full": False}], ofs) == (None, [])


def test_rota_do_vendedor_seguido():
    """O seguido é achado no Explorador pelo nome que o Bruno deu (lá aparece igual) e o nº da loja oficial de lá prova a
    loja. Sem prova: não grava, tira o de-para automático antigo e mostra as candidatas. O manual do Bruno nunca muda."""
    os.environ.setdefault("OLLAMA_API_KEY", "x")
    os.environ.setdefault("ANTHROPIC_API_KEY", "x")
    import pandas as pd
    import nubi_web as w
    _preparar()
    exp = (HOJE - timedelta(days=1)).isoformat()
    linha_exp = {"vendedor_id": "e" * 64, "vendedor": "ESSENCE PRIME P9", "gtin": "6290362346548", "sku": "ASADX", "preco": 279.0,
                 "full": 1, "dias_pub": 300, "un": 900, "fat": 251100, "produto": "Lattafa Asad Elixir EDP 100 ml", "titulo": "Asad Elixir",
                 "snapshot_id": 8, "tipo": "EDP", "loja_oficial": 1, "catalogo": 1,
                 "bruto": {"Loja oficial": "LOJA.OFICIAL.555", "Exposição": "Clássica"}}

    class R(Repo):
        def snapshots(self, marca=None):
            df = pd.DataFrame([{"id": 8, "marca": "LATTAFA", "inicio": "2026-09-01", "fim": "2026-09-27", "importado_em": exp}])
            return df[df["marca"] == marca] if marca else df

        def _todos(self, t, q=None):
            q = q or {}
            if t == "vend_relatorios":
                rels = [{"id": 5, "vendedor": "ESSENCE PRIME P9", "mes": "2026-09-01", "ate": "2026-09-27", "arquivo": "x",
                         "importado_em": "x", "seller_hash": "H" * 128, "nome_exibido": "ESSENCE PRIME P9"},
                        {"id": 6, "vendedor": "SEM PROVA P1", "mes": "2026-09-01", "ate": None, "arquivo": "y",
                         "importado_em": "y", "seller_hash": "J" * 128, "nome_exibido": "SEM PROVA P1"}]
                return [r for r in rels if not q.get("vendedor") or q["vendedor"] == "eq." + r["vendedor"]]
            if t == "vend_anuncios":
                preco = 280.0 if q["relatorio_id"] == "eq.5" else 281.0
                return [{"titulo": "Asad Elixir", "marca": "LATTAFA", "marca_chave": "LATTAFA", "gtin": "62903623465486290362346548",
                         "sku": "A", "vendas": 30000, "unidades": 100, "preco": preco, "tipo_pub": "Clássico", "fulfillment": True,
                         "catalogo": True, "frete_gratis": True, "desconto": False, "estado": "active"}]
            if t == "anuncios":
                v, vid = q.get("vendedor", ""), q.get("vendedor_id", "")
                if v == "eq.ESSENCE PRIME P9" or ("e" * 64) in vid:
                    return [json.loads(json.dumps(linha_exp))]
            return []
    r = R()
    assert w.rota_meli(r, "GET", "meli_seguido", {"vendedor": "ESSENCE PRIME P9"}, b"")["loja"] is None
    r.resumos[w.OFICIAIS] = json.dumps({"555": 555})
    d = w.rota_meli(r, "POST", "meli_seguido_descobrir", {}, json.dumps({"vendedor": "ESSENCE PRIME P9"}).encode())
    assert d["achou"] and d["loja"]["nome"] == "ESSENCEPRIMEBR" and d["loja"]["confianca"] == "certa", d
    assert d["loja"]["anuncios"][0]["anuncio"] == "MLB2000200" and d["loja"]["anuncios"][0]["titulo"].startswith("Lattafa Asad")
    assert d["explorador"] == {"hashes": ["e" * 64], "como": "nome", "oficial": [555]}, d["explorador"]
    assert w.rota_meli(r, "GET", "meli_seguido", {"vendedor": "ESSENCE PRIME P9"}, b"")["loja"]["id"] == "222222222"
    assert meli.ler_hash_lojas(r)["e" * 64]["id"] == "222222222"                    # o hash do Explorador ficou ligado também
    assert "anuncios" not in meli.ler_hash_lojas(r)["e" * 64]
    assert w._gtins_da_loja(r, "222222222") == ["6290362346548"]
    # sem prova: o de-para automático errado (como o da LUH) sai e aparecem as candidatas
    meli.gravar_hash_lojas(r, {"SEM PROVA P1": {"id": "1395403852", "nome": "LUH20230609125415", "confianca": "dúvida"}}, meli.SEGUIDOS)
    d2 = w.rota_meli(r, "POST", "meli_seguido_descobrir", {}, json.dumps({"vendedor": "SEM PROVA P1"}).encode())
    assert not d2["achou"] and d2["candidatas"][0]["id"] == "222222222" and "candidatas" in d2["motivo"], d2
    assert "SEM PROVA P1" not in meli.ler_hash_lojas(r, meli.SEGUIDOS)
    # o Bruno escolhe a candidata ("É esta"): vira manual e a busca não troca mais
    n = w.rota_meli(r, "POST", "meli_seguido_nomear", {}, json.dumps({"vendedor": "SEM PROVA P1", "loja": "222222222"}).encode())
    assert n["loja"]["nome"] == "ESSENCEPRIMEBR" and meli.ler_hash_lojas(r, meli.SEGUIDOS)["SEM PROVA P1"]["confianca"] == "manual"
    d3 = w.rota_meli(r, "POST", "meli_seguido_descobrir", {}, json.dumps({"vendedor": "SEM PROVA P1"}).encode())
    assert d3["confirmada"]["id"] == "222222222" and d3["confere"] is False
    assert meli.ler_hash_lojas(r, meli.SEGUIDOS)["SEM PROVA P1"]["confianca"] == "manual"


def test_painel_dos_vendedores_seguidos():
    # 29/09 (Bruno): todos os seguidos, dados técnicos do último relatório e a loja no ML quando achada
    os.environ.setdefault("OLLAMA_API_KEY", "x")
    os.environ.setdefault("ANTHROPIC_API_KEY", "x")
    import pandas as pd
    import nubi_web as w
    _preparar()

    class R(Repo):
        def _todos(self, t, q=None):
            if t == "vend_relatorios":
                return [{"id": 4, "vendedor": "ICARBONXX P3", "mes": "2026-08-01", "ate": None, "arquivo": "a", "importado_em": "x",
                         "seller_hash": "A" * 128, "nome_exibido": "ICARBONXX P3"},
                        {"id": 9, "vendedor": "ICARBONXX P3", "mes": "2026-09-01", "ate": "2026-09-27", "arquivo": "b", "importado_em": "y",
                         "seller_hash": "A" * 128, "nome_exibido": "ICARBONXX P3"},
                        {"id": 7, "vendedor": "AIRON-AMBAR", "mes": "2026-09-01", "ate": None, "arquivo": "c", "importado_em": "z",
                         "seller_hash": "B" * 128, "nome_exibido": "AIRON-AMBAR"}]
            if t == "vend_anuncios":
                rid = int(q["relatorio_id"][3:])
                if rid == 9:
                    return [{"marca_chave": "LATTAFA", "gtin": "62903623465486290362346548", "vendas": 30000, "unidades": 100, "catalogo": True,
                             "fulfillment": True, "frete_gratis": True, "tipo_pub": "Clássico", "estado": "active"},
                            {"marca_chave": "LIPX", "gtin": "", "vendas": 1000, "unidades": 5, "catalogo": False,
                             "fulfillment": False, "frete_gratis": True, "tipo_pub": "Premium", "estado": "paused"}]
                return [{"marca_chave": "X", "gtin": "", "vendas": 10, "unidades": 1, "catalogo": False, "fulfillment": False,
                         "frete_gratis": False, "tipo_pub": "Clássico", "estado": "active"}]
            if t == "anuncios" and q.get("vendedor") == "eq.ICARBONXX P3":       # no Explorador ele aparece com o mesmo nome
                return [{"vendedor_id": "c" * 64, "loja_oficial": 1}, {"vendedor_id": "c" * 64, "loja_oficial": 0}]
            return []

        def snapshots(self, marca=None):
            return pd.DataFrame([{"id": 8, "marca": "LIPX", "inicio": "2026-09-01", "fim": "2026-09-27", "importado_em": "2026-09-28"}])

        def _req(self, metodo, tabela, q=None, corpo=None, **k):
            if tabela == "anuncios":                                            # nº da loja oficial (linha original)
                assert q["loja_oficial"] == "eq.1" and q["vendedor"] == "eq.ICARBONXX P3" and q["snapshot_id"] == "in.(8)"
                return [{"bruto": {"Loja oficial": "LOJA.OFICIAL.23829"}}, {"bruto": json.dumps({"Loja oficial": "LOJA.OFICIAL.23829"})}]
            return super()._req(metodo, tabela, q, corpo, **k)
    r = R()
    meli.gravar_hash_lojas(r, {"ICARBONXX P3": {"id": "222222222", "nome": "ICARBONXX", "link": "https://perfil.mercadolivre.com.br/ICARBONXX",
                                                "confianca": "provável", "votos": 6, "anuncios": [{"anuncio": "MLB1"}, {"anuncio": "MLB2"}]}},
                           meli.SEGUIDOS)
    xs = w.rota_meli(r, "GET", "meli_seguidos_lista", {}, b"")["vendedores"]
    assert [x["vendedor"] for x in xs] == ["ICARBONXX P3", "AIRON-AMBAR"]                   # quem mais fatura primeiro
    a = xs[0]
    assert a["relatorio_id"] == 9 and a["mes"] == "2026-09" and a["meses"] == 2 and a["hash"] == "A" * 128
    assert (a["anuncios"], a["ativos"], a["com_gtin"], a["catalogo"], a["full"], a["premium"]) == (2, 1, 1, 1, 1, 1)
    assert a["vendas"] == 31000 and a["unidades"] == 105 and a["marcas"] == 2 and a["top_marca"] == "Lattafa"
    assert a["ml"]["nome"] == "ICARBONXX" and a["ml"]["anuncios"] == 2 and xs[1]["ml"] is None
    assert a["ml"]["confianca"] == "a conferir"                   # feito antes da prova nova (sem "prova"): a conferir
    assert a["explorador"] == {"hashes": ["c" * 64], "anuncios": 2, "oficial": [23829]} and xs[1]["explorador"] is None

# anúncios do Bruno (PUREHOME): nº do MLB (UpSeller) x "Data de criação" (Explorador), 29/09 — duas sequências de nº
CALIB_REAL = [(4502422545, "2026-03-02"), (4506216155, "2026-03-04"), (4564678013, "2026-03-27"), (4564749711, "2026-03-27"),
              (4580665857, "2026-04-02"), (4580674031, "2026-04-02"), (4620989177, "2026-04-20"),
              (4646114313, "2026-04-30"), (4908236905, "2026-07-17"), (4936759727, "2026-07-23"), (5056539183, "2026-08-13"),
              (6181824276, "2026-01-19"), (6209410920, "2026-01-29"), (6290732514, "2026-02-23"), (6365509112, "2026-03-02"),
              (6527218268, "2026-03-27"), (6557028920, "2026-04-02"), (6630741268, "2026-04-16"),
              (6646618654, "2026-04-20"), (6756032596, "2026-05-11"), (6858090042, "2026-05-28"), (6896330166, "2026-06-03"),
              (6944852660, "2026-06-11"), (7177006460, "2026-07-15"), (7238819528, "2026-07-23"), (7304418818, "2026-07-31")]


def test_data_de_criacao_pelo_numero_do_anuncio():
    """O ML não dá a data de criação do anúncio de outra loja ao app, mas o nº do MLB cresce com o tempo (em sequências).
    Calibrado com os anúncios do Bruno, estima a data; os que ficaram de fora da calibração conferem."""
    cal = [(n, date.fromisoformat(d)) for n, d in CALIB_REAL]
    for mlb, real in (("MLB4575881755", "2026-04-01"), ("MLB6551180856", "2026-04-01"), ("MLB6636199952", "2026-04-17"),
                      ("MLB6938013644", "2026-06-10")):                        # fora da calibração: SHAHEEN, AFEEF, MIX, KIT DOLCE
        est, folga = meli.data_pelo_mlb(mlb, cal)
        assert est and abs((est - date.fromisoformat(real)).days) <= folga, (mlb, est, real, folga)
    assert meli.data_pelo_mlb("MLB5500000000", cal) == (None, None)             # entre as duas sequências: não sabe
    est, folga = meli.data_pelo_mlb("MLB7400000000", cal)                      # depois do maior: segue o ritmo, com folga
    assert est and date(2026, 8, 5) <= est <= date(2026, 8, 20) and folga > 3, (est, folga)
    assert meli.data_pelo_mlb("MLB9900000000", cal) == (None, None)             # longe demais
    assert meli._data_br("16-07-2026") == date(2026, 7, 16) and meli._data_br("x") is None
    # 2 anúncios dele com a data de criação batendo (pelo nº) = certa, mesmo sem loja oficial e sem preço do dia
    of = lambda mlb, sid, g, preco: {"anuncio": mlb, "vendedor_id": sid, "preco": preco, "full": True, "tipo_id": "gold_special",
                                     "loja_oficial": None, "_tem_oficial": True, "gtin_busca": g, "produto_catalogo": "P" + g}
    ofertas = [of("MLB4575881755", 11, "1", 150.0), of("MLB4906000000", 22, "1", 151.0),       # 11: criado ~01/04
               of("MLB6636199952", 11, "2", 200.0), of("MLB6290732514", 22, "2", 199.0)]       # 11: ~17/04; 22: 23/02
    refs = [{"gtins": ["1"], "preco": 150.0, "full": True, "exato": False, "loja_oficial": 0, "criado": date(2026, 4, 1)},
            {"gtins": ["2"], "preco": 200.0, "full": True, "exato": False, "loja_oficial": 0, "criado": date(2026, 4, 17)}]
    cands, n = meli.casar(refs, ofertas, cal)
    assert cands[0]["id"] == "11" and cands[0]["idade"] == 2 and meli.decidir(cands, n) == "certa", cands
    assert meli.decidir(meli.casar(refs, ofertas)[0], 2) is None                # sem a calibração: dois iguais, não decide
    assert "data de criação batendo em 2" in meli._prova(cands[0], n)


def test_calibracao_com_os_anuncios_do_bruno():
    os.environ.setdefault("OLLAMA_API_KEY", "x")
    os.environ.setdefault("ANTHROPIC_API_KEY", "x")
    import nubi_web as w
    vendas = {"linhas": [{"sku": f"SKU-{i:02d}", "loja": "ESSENCE PRIME[Mercado Libre BR]", "anuncio": f"MLB{6181824276 + i * 10000000}"}
                         for i in range(8)] + [{"sku": "SKU-DUPLO", "loja": "X", "anuncio": "MLB1111111"},
                                               {"sku": "SKU-DUPLO", "loja": "X", "anuncio": "MLB2222222"}]}

    class R(Repo):
        pedidos = 0

        def _todos(self, t, q=None):
            assert t == "anuncios" and q["sku"].startswith("in.(")
            R.pedidos += 1
            meus = [{"vendedor_id": "p" * 64, "sku": f"SKU{i:02d}", "bruto": {"Data de criação": f"{19 + i:02d}-01-2026"}} for i in range(8)]
            outro = [{"vendedor_id": "o" * 64, "sku": "SKU00", "bruto": {"Data de criação": "01-01-2020"}}]    # outro vendedor, mesmo SKU
            return meus + outro
    r = R()
    r.resumos[w.VENDAS_CHAVE] = json.dumps(vendas)
    pts = w._calibracao_mlb(r)
    assert len(pts) == 8 and pts[0] == (6181824276, date(2026, 1, 19)) and pts[-1][1] == date(2026, 1, 26), pts
    assert json.loads(r.resumos[w.CALIBRA])["lojas"] == ["p" * 64]              # a loja do Bruno: 5+ SKUs dele
    assert w._calibracao_mlb(r) == pts and R.pedidos == 1                      # 1 vez por dia
    _preparar()
    t = w.rota_meli(r, "GET", "meli_teste", {}, b"")                             # o botão 🔌 mostra a calibração
    cal = [x for x in t["passos"] if x["passo"].startswith("data de criação")][0]
    assert cal["ok"] and "8 anúncios seus, de 19/01/2026 a 26/01/2026" in cal["detalhe"], cal


def test_fotos_do_nubimetrics_para_comparar_com_o_ml():
    """29/09 (Bruno: 'a foto do anúncio no Nubimetrics é a mesma do ML'): o coletor lê a resposta 'analysisitems' da tela
    do vendedor e o nubi guarda as fotos por vendedor."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
    import coletor
    resp = {"data": {"items": [
        {"title": "Perfume Árabe Al Wataniah Bareeq Al Dhah", "price": 149.9, "sku": "BAREEQ",
         "thumbnail": "https://http2.mlstatic.com/D_951134-MLB91143087125_082025-I.jpg", "extra": {"x": 1}},
        {"title": "Sem foto", "price": 10}]}, "total": 1}
    xs = coletor.fotos_do_json(resp)
    assert xs == [{"foto": "https://http2.mlstatic.com/D_951134-MLB91143087125_082025-I.jpg", "title": "Perfume Árabe Al Wataniah Bareeq Al Dhah",
                   "price": 149.9, "sku": "BAREEQ", "thumbnail": "https://http2.mlstatic.com/D_951134-MLB91143087125_082025-I.jpg"}], xs
    os.environ.setdefault("OLLAMA_API_KEY", "x")
    os.environ.setdefault("ANTHROPIC_API_KEY", "x")
    import nubi_web as w
    r = Repo()
    out = w.rota_posicoes(r, "POST", "ml_vend_fotos", {}, json.dumps({"nome": "ICARBONXX P3", "seller_hash": "H", "mes": "2026-09",
                                                                    "itens": xs + [{"sem": "foto"}]}).encode())
    assert out == {"ok": True, "itens": 1}
    lido = w.rota_meli(r, "GET", "meli_fotos_seguido", {"vendedor": "ICARBONXX P3"}, b"")
    assert lido["itens"][0]["sku"] == "BAREEQ" and lido["mes"] == "2026-09"
    assert w.rota_meli(r, "GET", "meli_fotos_seguido", {"vendedor": "OUTRO"}, b"") == {"itens": []}
    assert "vend_fotos" in w.COMANDOS_MAC and coletor.comando_mac("vend_fotos")[-1] == "fotos-vendedores"



def test_extensao_do_chrome_dado_publico_do_ml():
    """29/09 (Bruno: "as mesmas funções do Hunter"): a rota ext_* é SEM login e só devolve dado público do ML: comissão
    (Clássico e Premium), frete, visitas do anúncio e do catálogo, concorrentes com a loja real, data pelo nº do MLB e
    tendências. Parâmetros conferidos; nada do nubi."""
    d = _preparar()
    os.environ.setdefault("OLLAMA_API_KEY", "x")
    os.environ.setdefault("ANTHROPIC_API_KEY", "x")
    import nubi_web as w
    p = meli.ext_parametros({"mlb": "MLB2000200", "pid": "MLB9990999", "vendedor": "222222222", "categoria": "MLB6284",
                             "tipo": "gold_pro", "preco": "279", "lixo": "x"})
    assert p == {"mlb": "MLB2000200", "pid": "MLB9990999", "vendedor": "222222222", "categoria": "MLB6284", "tipo": "gold_pro",
                 "preco": 279.0}, p
    ruim = meli.ext_parametros({"mlb": "MLB2000200&x=1", "vendedor": "abc", "categoria": "../users", "tipo": "hack", "preco": "-3"})
    assert set(ruim.values()) == {None}, ruim
    calib = [(2000000, date(2026, 1, 1)), (2000400, date(2026, 2, 10))]
    x = meli.painel_extensao(p, calib=calib)
    assert x["loja"]["nome"] == "ESSENCEPRIMEBR" and x["frete"] == 24.45 and x["loja"]["vendas_ok"] == 25000     # sem as canceladas, como o Hunter
    assert set(x["tarifas"]) == {"gold_special", "gold_pro"} and x["tarifas"]["gold_pro"]["pct"] == 14
    assert x["visitas"] == {"anuncio": 3000, "catalogo": 5260, "catalogo_lidos": 2, "parte": 57}, x["visitas"]
    assert x["total_concorrentes"] == 2 and [c["loja"] for c in x["concorrentes"]] == ["FINKE", "ESSENCEPRIMEBR"]
    assert [c["eu"] for c in x["concorrentes"]] == [False, True] and x["concorrentes"][0]["preco"] == 265.28
    # a 1ª visita (histórico de visitas do ML) é a data de entrada; com ela não precisa estimar pelo nº
    assert x["historico"]["primeira_visita"] == str(HOJE.date() - timedelta(days=100)) and x["historico"]["precisao"] == "dia", x["historico"]
    h3 = meli.historico_visitas("MLB4000400")                       # entrou há 300 dias: a janela por dia não alcança, a semanal sim
    assert h3["precisao"] == "semana" and abs((date.fromisoformat(h3["primeira_visita"]) - (HOJE.date() - timedelta(days=300))).days) <= 7, h3
    assert x["historico"]["total"] == 3000 and x["criado_estimado"] is None
    h2 = meli.historico_visitas("MLB1000100")                       # visita desde o 1º dia da janela: mais velho que ela
    assert "primeira_visita" not in h2 and h2["mais_velho_que"] == str(HOJE.date() - timedelta(days=30 * 35)), h2
    assert meli.painel_extensao(dict(p, mlb="MLB4000400"), calib=calib)["criado_estimado"] is None     # fora da calibração
    n = len(d.pedidos)
    assert meli.painel_extensao(p, calib=calib) == x and len(d.pedidos) == n                  # 30 min na memória
    # só o anúncio, abaixo de R$ 79: sem frete (quem paga é o comprador)
    y = meli.painel_extensao(meli.ext_parametros({"mlb": "MLB3000300", "vendedor": "222222222", "categoria": "MLB1234",
                                                  "tipo": "gold_special", "preco": "69.90"}))
    assert y["frete"] is None and y["visitas"] == {"anuncio": 22} and not y["concorrentes"] and "mais_velho_que" in y["historico"]
    # a rota: sem login (token vazio), e o que não é ext_ continua pedindo login
    st, _, corpo, cab = w.atender("GET", "ext_tendencias", {"categoria": "mlb1246"}, b"", "")
    assert cab.get("Access-Control-Allow-Origin") == "*"            # a extensão não depende da permissão de site do Chrome
    assert st == 200 and [t["termo"] for t in json.loads(corpo)["termos"]] == ["asad elixir", "starlink mini"]
    assert json.loads(corpo)["termos"][0]["link"].startswith("https://")
    st, _, corpo, _ = w.atender("GET", "ext_categorias", {}, b"", "")
    assert st == 200 and json.loads(corpo)["categorias"][0] == {"id": "MLB1246", "nome": "Beleza e Cuidado Pessoal"}
    st, _, corpo, _ = w.atender("GET", "ext_ml", {"mlb": "nada"}, b"", "")
    assert st == 400
    w._EXT_CALIB.update(ts=9e12, pts=[])
    st, _, corpo, _ = w.atender("GET", "ext_ml", {"mlb": "MLB2000200", "vendedor": "222222222"}, b"", "")
    assert st == 200 and json.loads(corpo)["loja"]["nome"] == "ESSENCEPRIMEBR"
    assert w.atender("GET", "meli_hash_lojas", {}, b"", "")[0] == 401
    # busca: card de catálogo -> o vendedor do anúncio DO CARD (wid) entre as ofertas; sem wid, quem ganha o produto
    v = meli.ext_vencedores(["MLB9990999:MLB1000100", "MLB9990999", "MLB8880888:MLB5000002", "lixo", "MLB1:../x"])
    assert set(v) == {"MLB9990999:MLB1000100", "MLB9990999", "MLB8880888:MLB5000002"}, v
    assert v["MLB9990999:MLB1000100"]["loja"]["nome"] == "FINKE" and v["MLB9990999:MLB1000100"]["do_card"]
    assert v["MLB9990999"]["item"] == "MLB2000200" and v["MLB9990999"]["loja"]["nome"] == "ESSENCEPRIMEBR" and not v["MLB9990999"]["do_card"]
    assert v["MLB8880888:MLB5000002"]["loja"]["nome"] == "KAIDOXSTOREE" and v["MLB8880888:MLB5000002"]["full"]
    st, _, corpo, _ = w.atender("GET", "ext_vencedores", {"pids": "MLB9990999:MLB1000100"}, b"", "")
    assert st == 200 and json.loads(corpo)["produtos"]["MLB9990999:MLB1000100"]["vendedor"] == "111111111"
    # limite de pedidos novos por minuto (rota sem login)
    meli._EXT_CONTA.update(min=int(__import__("time").time() // 60), n=meli.EXT_POR_MINUTO)
    try:
        meli.painel_extensao(meli.ext_parametros({"vendedor": "111111111"}))
        assert False, "devia recusar"
    except meli.ErroMeli as e:
        assert "muitos pedidos" in str(e)
    meli._EXT_CONTA.update(n=0)



def test_conta_do_ml_conectada_por_oauth():
    """29/09 (autorizado pelo Bruno: conta de teste, a mesma do app): login na página do ML, volta com código + state,
    refresh CIFRADO no banco (nunca em texto), renova sozinho (o ML troca o refresh a cada uso) e /items passa a funcionar."""
    d = _preparar()
    d.bloq_um = d.bloq_varios = True                      # produção 29/09: /items e /items?ids= dão 403 ao app
    os.environ.setdefault("OLLAMA_API_KEY", "x")
    os.environ.setdefault("ANTHROPIC_API_KEY", "x")
    import nubi_web as w
    # cifra: volta igual, muda a cada vez, e um byte trocado é recusado
    c1, c2 = meli.cifrar("R-SEGREDO"), meli.cifrar("R-SEGREDO")
    assert c1 != c2 and meli.decifrar(c1) == "R-SEGREDO" and "SEGREDO" not in c1
    ruim = c1[:-2] + ("A" if c1[-2] != "A" else "B") + c1[-1]
    try:
        meli.decifrar(ruim)
        assert False, "devia recusar"
    except ValueError:
        pass
    r = Repo()
    velho = (w._repo_agente, meli.USUARIO_REPO)
    w._repo_agente = lambda: r
    meli.USUARIO_REPO = lambda: r
    meli._USUARIO.update(valor=None, ate=0.0, erro=None, nick=None, falhou_em=0.0)
    try:
        # sem conta: /items do anúncio de outra loja continua 403 (token do app)
        assert meli.itens(["MLB1000100"])["MLB1000100"].get("bloqueado")
        meli._CACHE.clear()
        # botão Conectar: grava o state; a volta com state errado não conecta
        u = w.rota_meli(r, "POST", "meli_conectar", {}, b"{}")
        estado = json.loads(r.resumos["meli|estado"])["estado"]
        assert "auth.mercadolivre.com.br/authorization" in u["url"] and f"state={estado}" in u["url"] and "client_id=123" in u["url"]
        st, tipo, corpo, _ = w.atender("GET", "meli_retorno", {"code": "CODIGO-OK", "state": "outro"}, b"", "")
        assert st == 200 and "não conectada" in corpo.decode() and not meli.ler_conta(r)
        st, tipo, corpo, _ = w.atender("GET", "meli_retorno", {"code": "CODIGO-OK", "state": estado}, b"", "")
        assert "text/html" in tipo and "TESTE_BRUNO" in corpo.decode() and "conectada" in corpo.decode()
        conta = meli.ler_conta(r)
        assert conta["nick"] == "TESTE_BRUNO" and meli.decifrar(conta["refresh"]) == "R1"
        assert "R1" not in r.resumos["meli|conta"] and "TOKEN" not in r.resumos["meli|conta"]      # nada em texto puro
        # o state é de uso único
        st, _, corpo, _ = w.atender("GET", "meli_retorno", {"code": "CODIGO-OK", "state": estado}, b"", "")
        assert "não conectada" in corpo.decode()
        # com a conta, /items do anúncio de outra loja vem
        x = meli.itens(["MLB1000100"])["MLB1000100"]
        assert not x.get("bloqueado") and x.get("vendedor_id") == 111111111, x
        # vence o acesso: renova pelo refresh e grava o NOVO refresh (cifrado)
        meli._USUARIO.update(valor=None, ate=0.0)
        meli._CACHE.clear()
        assert not meli.itens(["MLB2000200"])["MLB2000200"].get("bloqueado")
        assert meli.decifrar(meli.ler_conta(r)["refresh"]) == "R2" and d.refresh == "R2"
        st = w.rota_meli(r, "GET", "meli_conta", {}, b"")
        assert st["conectada"] and st["funcionando"] and st["nick"] == "TESTE_BRUNO" and "refresh" not in st
        # desconectar: volta para o token do app
        w.rota_meli(r, "POST", "meli_desconectar", {}, b"{}")
        meli._CACHE.clear()
        assert not meli.ler_conta(r) and meli.itens(["MLB1000100"])["MLB1000100"].get("bloqueado")
    finally:
        w._repo_agente, meli.USUARIO_REPO = velho
        meli._USUARIO.update(valor=None, ate=0.0, erro=None, nick=None, falhou_em=0.0)



def test_comparar_vendas_nubimetrics_com_o_ml():
    """29/09 (Bruno: "comparar as vendas do mesmo período do Nubimetrics com as da API do ML; tem que bater"): uma foto por
    dia dos anúncios da loja; a diferença dos 'vendidos' = vendas do dia pelo ML, ao lado do vend_vendas_dia."""
    d = _preparar()
    os.environ.setdefault("OLLAMA_API_KEY", "x")
    os.environ.setdefault("ANTHROPIC_API_KEY", "x")
    import nubi_web as w
    # foto de hoje pela busca da loja (dublê: a loja 222222222 tem 3 anúncios)
    f = meli.foto_da_loja("222222222")
    assert f["total"] == 3 and set(f["itens"]) == {"MLB2000200", "MLB3000300", "MLB4000400"}
    assert f["itens"]["MLB2000200"] == {"v": 500, "d": 50, "p": 279.0, "g": "6290362346548", "t": "Perfume Asad Elixir Lattafa 100ml",
                                        "s": "active", "f": True}, f["itens"]["MLB2000200"]
    assert meli.vendidos_em_faixa(f["itens"]) == 1.0                    # 500 e 1000: números de faixa -> avisar
    d.bloq_busca = True
    try:
        meli.foto_da_loja("222222222")
        assert False, "devia pedir a conta"
    except meli.ErroMeli as e:
        assert "conecte a conta" in str(e)
    d.bloq_busca = False
    # 3 fotos (27, 28 e hoje) e o Nubimetrics dos mesmos dias
    hoje = w._hoje_br()
    d1, d2 = hoje - timedelta(days=2), hoje - timedelta(days=1)
    foto = lambda vs: {"total": 3, "itens": {i: {"v": v, "g": g, "t": t} for i, (v, g, t) in vs.items()}}
    fotos = {d1: foto({"MLB2000200": (480, "6290362346548", "Asad"), "MLB4000400": (990, "8002135111", "Ferrari")}),
             d2: foto({"MLB2000200": (490, "6290362346548", "Asad"), "MLB4000400": (995, "8002135111", "Ferrari")}),
             hoje: foto({"MLB2000200": (500, "6290362346548", "Asad"), "MLB4000400": (994, "8002135111", "Ferrari"),
                         "MLB3000300": (0, "", "Caneca")})}

    class RepoC(Repo):
        def _todos(self, tabela, q=None):
            if tabela == "ia_resumos":
                pre = q["chave"][5:].rstrip("*")
                return [{"chave": k, "texto": v} for k, v in sorted(self.resumos.items()) if k.startswith(pre)]
            if tabela == "vend_vendas_dia":
                assert q["vendedor"] == "eq.ESSENCE" and q["data"] == f"gte.{d1.isoformat()}"
                return [{"data": d1.isoformat(), "u": 10, "itens": [{"k": "6290362346548", "u": 10}]},
                        {"data": d2.isoformat(), "u": 12, "itens": [{"k": "6290362346548", "u": 9}, {"k": "8002135111", "u": 3}]}]
            return []
    r = RepoC()
    for dia, fx in fotos.items():
        r.resumos[f"meli|foto|222222222|{dia.isoformat()}"] = json.dumps(fx)
    c = w.comparar_loja(r, "222222222", "ESSENCE")
    assert json.loads(r.resumos["meli|comparar"])["222222222"]["vendedor"] == "ESSENCE"
    assert c["fotos"] == [d1.isoformat(), d2.isoformat(), hoje.isoformat()]
    assert [(x["ml"], x["nubi"]) for x in c["dias"]] == [(15, 10), (10, 12)], c["dias"]     # d1→d2: 10 + 5; d2→hoje: 10
    assert c["dias"][1]["desceu"] == 1 and c["dias"][1]["novos"] == 1                   # Ferrari 995→994; caneca nova
    assert c["total"] == {"ml": 25, "nubi": 22}
    p = {x["chave"]: x for x in c["produtos"]}
    assert p["6290362346548"]["ml"] == 20 and p["6290362346548"]["nubi"] == 19 and p["8002135111"] == {
        "chave": "8002135111", "titulo": "Ferrari", "ml": 5, "nubi": 3}
    # sem loja: a lista de opções vem dos seguidos com a loja real achada
    r.resumos["meli|seguidos"] = json.dumps({"ESSENCE": {"id": 222222222, "nome": "ESSENCEPRIMEBR", "confianca": "manual"},
                                             "DUVIDA": {"id": 1, "nome": "X", "confianca": "dúvida"}})
    o = w.rota_meli(r, "GET", "meli_comparar", {}, b"")
    assert [x["vendedor"] for x in o["opcoes"]] == ["ESSENCE"] and "222222222" in o["lojas"]


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
