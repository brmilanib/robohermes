"""01/10 (Bruno): monitor de preços ao meio-dia e às 19 h; preço mudou = aviso piscando até ele ver; título certo do ML
(o coletor abre a página dos que estão sem título) e as tags Catálogo / FULL."""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import precos  # noqa: E402
from test_precos_monitor import Repo  # noqa: E402

BR = precos.BRASILIA


def test_rodadas_12_e_19():
    assert precos.rodada_atual(datetime(2026, 10, 1, 11, 59, tzinfo=BR)) == datetime(2026, 9, 30, 19, 0, tzinfo=BR)
    assert precos.rodada_atual(datetime(2026, 10, 1, 12, 0, tzinfo=BR)) == datetime(2026, 10, 1, 12, 0, tzinfo=BR)
    assert precos.rodada_atual(datetime(2026, 10, 1, 21, 5, tzinfo=BR)) == datetime(2026, 10, 1, 19, 0, tzinfo=BR)
    r = Repo()
    t = datetime(2026, 10, 1, 12, 10, tzinfo=BR)
    ini = precos.api_devida(r, t)
    assert ini == datetime(2026, 10, 1, 12, 0, tzinfo=BR)
    precos.marcar_rodada(r, ini)
    assert precos.api_devida(r, t + timedelta(hours=2)) is None              # 14h: a das 12h já foi
    assert precos.api_devida(r, datetime(2026, 10, 1, 19, 3, tzinfo=BR)) is not None


def test_pendente_titulo_e_rodada():
    r = Repo()
    precos.seguir(r, {"mlb": "MLB4000000111", "titulo": "Clássico"})
    precos.seguir(r, {"mlb": "MLB4000000222", "titulo": "Perfume Cuba Gold Masculino 100ml"})
    precos.gravar_leitura(r, [{"mlb": "MLB4000000111", "preco": 10}, {"mlb": "MLB4000000222", "preco": 20}])
    agora = datetime.now(BR)
    p = precos.pendente(r, {"ativo": True}, agora)
    # lido só pela API (sem fonte = navegador aqui? não: gravar_leitura sem fonte = página) -> ninguém falta
    ini = precos.rodada_atual(agora)
    if agora >= ini + timedelta(minutes=20):
        assert p["itens"] == [] and not p["rodar"]
    precos.gravar_leitura(r, [{"mlb": "MLB4000000111", "preco": 10, "fonte": "api"}])
    x0 = next(x for x in precos.lista(r) if x["mlb"] == "MLB4000000111")
    x0.pop("ultima_pagina", None)
    precos._gravar(r, precos.LISTA, [x0] + [x for x in precos.lista(r) if x["mlb"] != "MLB4000000111"])
    if agora >= ini + timedelta(minutes=20):
        assert [x["mlb"] for x in precos.pendente(r, {"ativo": True}, agora)["itens"]] == ["MLB4000000111"]
    lido = precos.ler_pagina({"fracao": "10", "centavos": "00", "titulo": "Perfume Ferrari Black 125ml Eau De Toilette",
                              "catalogo": True, "full": True})
    precos.gravar_leitura(r, [dict(lido, mlb="MLB4000000111")])
    x = next(x for x in precos.lista(r) if x["mlb"] == "MLB4000000111")
    assert x["titulo"].startswith("Perfume Ferrari") and x["catalogo"] is True and x["full"] is True
    assert not [i for i in precos.pendente(r, {"ativo": True}, agora)["itens"] if i["mlb"] == "MLB4000000111"]


def test_aviso_quando_o_preco_muda():
    r = Repo()
    precos.seguir(r, {"mlb": "MLB4000000333", "titulo": "Perfume Yara Lattafa 100ml", "catalogo": False, "full": True})
    precos.gravar_leitura(r, [{"mlb": "MLB4000000333", "preco": 130.19}], dia="2026-10-01")
    assert precos.alertas(r) == []
    precos.gravar_leitura(r, [{"mlb": "MLB4000000333", "preco": 130.19}], dia="2026-10-01")      # igual: sem aviso
    assert precos.alertas(r) == []
    precos.gravar_leitura(r, [{"mlb": "MLB4000000333", "preco": 119.9}], dia="2026-10-02")
    a = precos.alertas(r)
    assert len(a) == 1 and a[0]["de"] == 130.19 and a[0]["para"] == 119.9 and a[0]["pct"] < 0
    assert precos.marcar_visto(r, "MLB-4000000333") == 1 and precos.alertas(r) == []
    x = precos.lista(r)[0]
    assert x["catalogo"] is False and x["full"] is True


PAGINA = """<html><head><script>window.x = {\\"category_id\\":\\"MLB6284\\",\\"listing_type_id\\":\\"gold_special\\"};</script></head><body>
<div class="ui-pdp-header"><span>Novo | +1000 vendidos</span>
<div><span class="ui-pdp-promotions-pill-label">MAIS VENDIDO</span> <a href="https://www.mercadolivre.com.br/mais-vendidos/MLB6284">2º em Perfumes Jacques Bogart</a></div>
<h1>Jacques Bogart Silver Scent Intense Edt 200ml Para Masculino</h1></div>
<div class="ui-pdp-price__second-line"><span class="andes-money-amount__fraction">309</span><span class="andes-money-amount__cents">99</span></div>
<div class="ui-pdp-buybox"><p>Estoque disponível</p><p>Armazenado e enviado pelo <svg class="ui-pdp-icon--full"></svg> FULL</p>
<p>Quantidade: 1 unidade (+50 disponíveis)</p><div class="ui-pdp-seller__header__title">Vendido por Sieno</div></div>
<div class="ui-pdp-other-sellers"><a>13 produtos novos a partir de R$ 309,99</a></div></body></html>"""


def test_pagina_do_anuncio_tags_e_calculadora():
    import importlib.util
    from playwright.sync_api import sync_playwright
    raiz = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("coletor", raiz / "public" / "coletor" / "coletor.py")
    col = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(col)
    exe = os.environ.get("NUBI_CHROMIUM") or "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = b.new_page()
        pg.set_content(PAGINA)
        x = pg.evaluate(col.JS_ML_PRECO)
        b.close()
    lido = precos.ler_pagina(x)
    assert lido["preco"] == 309.99 and lido["estoque"] == 50 and lido["estoque_mais"] is True, lido
    assert lido["full"] is True and lido["catalogo"] is True and lido["titulo"].startswith("Jacques Bogart Silver Scent")
    assert lido["mais_vendido"] == "MAIS VENDIDO · 2º em Perfumes Jacques Bogart", lido["mais_vendido"]
    assert lido["categoria"] == "MLB6284" and lido["tipo_id"] == "gold_special"
    r = Repo()
    precos.seguir(r, {"mlb": "MLB5141216661", "titulo": "Clássico", "seller_id": "1142362911", "gtin": "3355991004672"})
    precos.gravar_leitura(r, [dict(lido, mlb="MLB5141216661")])
    it = precos.lista(r)[0]
    assert it["mais_vendido"].startswith("MAIS VENDIDO") and it["estoque_mais"] and it["categoria"] == "MLB6284"
    # conta: 309,99 − tarifa 40,30 − frete 24,45 − imposto 10% 31,00 − custo 150 = 64,24
    c = precos.contas(309.99, 150.0, 40.30, 24.45, 10)
    assert c["recebido"] == 245.24 and c["imposto"] == 31.0 and c["lucro"] == 64.24
    assert c["margem"] == round(64.24 / 309.99, 4) and c["roi"] == round(64.24 / 150, 4)
    assert precos.contas(309.99, None, 40.3, 0, 0)["lucro"] is None
    # nubi_web: custo do MEU estoque pelo GTIN + tarifa/frete da API (falsos)
    import nubi_web as w
    import meli
    antes = (w._estoque_itens, meli.tarifa, meli.frete_do_vendedor, meli.tem_chave)
    w._estoque_itens = lambda repo, aid: [{"sku": "3355991004672", "titulo": "Silver Scent Intense 200ml", "custo_medio": 150, "disponivel": 7}]
    meli.tarifa = lambda preco, cat, tipo: {"total": 40.30}
    meli.frete_do_vendedor = lambda v, m: 24.45
    meli.tem_chave = lambda: True
    r2 = Repo()
    r2._req_orig = r2._req
    r2._req = lambda metodo, tabela, params=None, corpo=None, prefer=None: [{"id": 1}] if tabela == "estoque_atualizacoes" else r2._req_orig(metodo, tabela, params, corpo, prefer)
    r2.res[precos.CALC] = json.dumps({"imposto_pct": 10})
    try:
        itens = [{"mlb": "MLB5141216661", "atual": 309.99, "categoria": "MLB6284", "tipo_id": "gold_special", "seller_id": "1142362911",
                  "gtin": "3355991004672", "titulo": "Jacques Bogart Silver Scent Intense Edt 200ml"}]
        w._calc_monitor(r2, itens)
        assert itens[0]["meu"]["custo"] == 150 and itens[0]["meu"]["casado_por"] == "gtin"
        assert itens[0]["calc"]["lucro"] == 64.24 and not itens[0]["calc"]["sem_tarifa"]
        # 01/10 (print do Bruno): sem a categoria lida na página, a tarifa usa a categoria sugerida pelo título
        meli.categoria_pelo_titulo, cat_antes = (lambda t: "MLB6284"), getattr(meli, "categoria_pelo_titulo")
        try:
            sem_cat = [dict(itens[0], categoria=None, titulo="Perfume Silver Scent Intense 200 ml X", meu=None, calc=None)]
            w._calc_monitor(r2, sem_cat)
            assert sem_cat[0]["calc"]["tarifa"] == 40.30 and not sem_cat[0]["calc"]["sem_tarifa"]
        finally:
            meli.categoria_pelo_titulo = cat_antes
    finally:
        w._estoque_itens, meli.tarifa, meli.frete_do_vendedor, meli.tem_chave = antes


def test_eventos_de_tags_full_estoque_posicao():
    r = Repo()
    precos.seguir(r, {"mlb": "MLB5141216661", "titulo": "Silver Scent Intense 200ml Jacques Bogart"})
    pag = lambda **k: dict({"mlb": "MLB5141216661", "preco": 309.99, "status": "ativo", "estoque": 50, "full": True, "catalogo": True,
                            "mais_vendido": "MAIS VENDIDO · 2º em Perfumes Jacques Bogart"}, **k)
    precos.gravar_leitura(r, [pag()])                                          # 1ª leitura: ponto de partida, sem alerta
    x = precos.lista(r)[0]
    assert x["posicao_mv"] == 2 and precos.alertas(r) == [] and "1ª leitura" in x["eventos"][0]["texto"]
    precos.gravar_leitura(r, [pag(mais_vendido="MAIS VENDIDO · 1º em Perfumes Jacques Bogart")])
    precos.gravar_leitura(r, [pag(mais_vendido="", full=False)])
    precos.gravar_leitura(r, [pag(mais_vendido="", full=False, estoque=0, status="esgotado")])
    precos.gravar_leitura(r, [pag(mais_vendido="MAIS VENDIDO · 3º em Perfumes Jacques Bogart", full=True, estoque=12)])
    tipos = [e["tipo"] for e in precos.lista(r)[0]["eventos"]]
    assert tipos == ["mais_vendido_on", "posicao", "mais_vendido_off", "full_off", "estoque_zerou",
                     "mais_vendido_on", "full_on", "estoque_voltou"], tipos
    a = precos.alertas(r)
    assert len(a) == 1 and len(a[0]["eventos"]) == 7 and "2º → 1º" in a[0]["eventos"][0]["texto"]
    # a API (só preço) não mexe nas tags
    precos.gravar_leitura(r, [{"mlb": "MLB5141216661", "preco": 309.99, "status": "ativo", "estoque": 12, "fonte": "api"}])
    assert len(precos.lista(r)[0]["eventos"]) == 9 - 1
    # histórico de mudanças (tela de detalhes) também mostra tag, posição e FULL
    campos = {m["campo"] for m in precos.mudancas(precos.historico(r, "MLB5141216661"))}
    assert {"mais_vendido", "posicao_mv", "full", "estoque"} <= campos, campos
    precos.marcar_visto(r, "MLB5141216661")
    assert precos.alertas(r) == []


def test_busca_termo_posicao_e_eventos():
    assert precos.termo_busca("Perfume Jacques Bogart Silver Scent Intense Edt 200ml Para Masculino") == "jacques bogart silver scent intense"
    assert precos.termo_busca("Perfume Feminino Yara Elixir Lattafa Eau De Parfum 100 Ml") == "yara elixir lattafa"
    import importlib.util
    from playwright.sync_api import sync_playwright
    raiz = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("coletor", raiz / "public" / "coletor" / "coletor.py")
    col = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(col)
    col.devagar = lambda *a: None
    card = lambda href, t, pat=False: f'<li class="ui-search-layout__item"><a href="{href}"><h3>{t}</h3></a>{"<span>Patrocinado</span>" if pat else ""}</li>'
    pagina = "<ol>" + card("https://produto.mercadolivre.com.br/MLB-111111111-outro", "Outro perfume", True) + \
        card("https://www.mercadolivre.com.br/silver-scent/p/MLB6181234?pdp_filters=item_id:MLB9999999999", "Silver Scent catálogo") + \
        card("https://produto.mercadolivre.com.br/MLB-5141216661-silver", "Silver Scent Sieno") + "</ol>"
    exe = os.environ.get("NUBI_CHROMIUM") or "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = b.new_page()
        pg.route("https://lista.mercadolivre.com.br/**", lambda rt: rt.fulfill(content_type="text/html", body=pagina))
        x = col.posicao_na_busca(pg, "jacques bogart silver scent intense", "MLB5141216661", paginas=1)
        y = col.posicao_na_busca(pg, "silver scent", "MLB5141216661", "MLB6181234", paginas=1)   # catálogo: casa pelo produto
        z = col.posicao_na_busca(pg, "silver scent", "MLB7777777777", paginas=1)
        b.close()
    assert x["posicao"] == 3 and x["pagina"] == 1 and not x["patrocinado"], x
    assert y["posicao"] == 2 and y["vencedor"] is False, y                    # o buy box é de outro (wid MLB9999999999)
    assert z["posicao"] is None and z["lidos"] == 3, z
    r = Repo()
    precos.seguir(r, {"mlb": "MLB5141216661", "titulo": "Jacques Bogart Silver Scent Intense Edt 200ml"})
    assert precos.pendente(r, {"ativo": True}, precos.rodada_atual() + timedelta(minutes=25))["itens"][0]["busca"] == "jacques bogart silver scent intense"
    g = lambda pos, pag: precos.gravar_leitura(r, [dict(precos.ler_pagina({"fracao": "309", "centavos": "99", "titulo": "Jacques Bogart Silver Scent",
                                                                          "busca_pos": {"termo": "silver", "posicao": pos, "pagina": pag, "lidos": 144}}),
                                                         mlb="MLB5141216661")])
    g(3, 1); g(5, 1); g(60, 2); g(None, None)
    evs = precos.lista(r)[0]["eventos"]
    assert [e["tipo"] for e in evs] == ["busca_posicao", "busca_posicao", "busca_saiu"]
    assert [e["visto"] for e in evs] == [True, False, False] and "pág. 1 → 2" in evs[1]["texto"]
    assert precos.salvar_busca(r, "MLB5141216661", "silver scent 200") == "silver scent 200"


def test_vincular_ao_meu_estoque():
    import nubi_web as w
    import meli
    est = [{"sku": "SHISEIDO-BB-30", "titulo": "Shiseido BB For Sports FPS 50 Light 30ml", "custo_medio": 120.0, "disponivel": 4, "transito_compra": 2},
           {"sku": "CK-ONE-200", "titulo": "Calvin Klein CK One EDT 200ml", "custo_medio": 140.0, "disponivel": 9}]
    antes = (w._estoque_itens, meli.tem_chave)
    w._estoque_itens = lambda repo, aid: [dict(x) for x in est]
    meli.tem_chave = lambda: False
    r = Repo()
    r._req_orig = r._req
    r._req = lambda metodo, tabela, params=None, corpo=None, prefer=None: [{"id": 1}] if tabela == "estoque_atualizacoes" else r._req_orig(metodo, tabela, params, corpo, prefer)
    try:
        precos.seguir(r, {"mlb": "MLB3055037392", "titulo": "Shiseido BB For Sports FPS 50 Light - Base Líquida 30ml"})
        assert [i["sku"] for i in w._estoque_busca_monitor(r, "", "MLB3055037392")][:1] == ["SHISEIDO-BB-30"]
        assert [i["sku"] for i in w._estoque_busca_monitor(r, "ck one", None)] == ["CK-ONE-200"]
        precos.vincular(r, "MLB3055037392", "CK-ONE-200")                       # o vínculo do Bruno vence o título
        itens = [{"mlb": "MLB3055037392", "atual": 291.25, "titulo": "Shiseido BB 30ml", **{k: v for k, v in precos.lista(r)[0].items() if k in ("sku_meu", "sem_vinculo")}}]
        w._calc_monitor(r, itens)
        m = itens[0]["meu"]
        assert m["sku"] == "CK-ONE-200" and m["custo"] == 140.0 and m["casado_por"] == "manual" and itens[0]["calc"]["lucro"] == round(291.25 - 140, 2)
        precos.vincular(r, "MLB3055037392", "", nenhum=True)
        itens = [{"mlb": "MLB3055037392", "atual": 291.25, "titulo": "Shiseido BB For Sports 30ml", "sem_vinculo": True}]
        w._calc_monitor(r, itens)
        assert itens[0]["meu"] is None
        x = precos.vincular(r, "MLB3055037392", "")                              # volta ao automático
        assert "sku_meu" not in x and "sem_vinculo" not in x
        out = w.rota_posicoes(r, "POST", "ml_precos_vincular", {}, json.dumps({"mlb": "MLB3055037392", "sku": "SHISEIDO-BB-30"}).encode())
        assert out["item"]["sku_meu"] == "SHISEIDO-BB-30"
    finally:
        w._estoque_itens, meli.tem_chave = antes




def test_calculadora_com_o_meu_anuncio_do_ml():
    """01/10 (Bruno: "pegar a minha categoria, o peso do produto, e marcar clássico ou premium"): tarifa dos 2 tipos pela
    categoria do MEU anúncio do SKU e o frete pelas medidas do pacote na minha conta."""
    import nubi_web as w
    import meli
    meli._CACHE.clear()
    assert meli.dimensoes_do_item({"attributes": [{"id": "SELLER_PACKAGE_HEIGHT", "value_name": "12 cm"},
        {"id": "SELLER_PACKAGE_WIDTH", "value_name": "8.5 cm"}, {"id": "SELLER_PACKAGE_LENGTH", "value_name": "20 cm"},
        {"id": "SELLER_PACKAGE_WEIGHT", "value_name": "0,6 kg"}]}) == "12x8.5x20,600"
    chamadas = []
    def get(caminho, params=None, timeout=20):
        chamadas.append((caminho, params))
        if caminho == "/users/me":
            return {"id": 77}
        if caminho == "/users/77/items/search":
            assert params["seller_sku"] == "SILVER-200"
            return {"results": ["MLB111"]}
        if caminho == "/items/MLB111":
            return {"id": "MLB111", "category_id": "MLB6284", "listing_type_id": "gold_pro", "price": 299,
                    "shipping": {"logistic_type": "fulfillment", "dimensions": "10x8x20,600"}}
        if caminho == "/sites/MLB/listing_prices":
            pct = 14 if params["listing_type_id"] == "gold_special" else 19
            return {"sale_fee_amount": round(params["price"] * pct / 100, 2), "sale_fee_details": {"percentage_fee": pct, "fixed_fee": 0}}
        if caminho == "/users/77/shipping_options/free":
            assert params["dimensions"] == "10x8x20,600" and params["logistic_type"] == "fulfillment"
            return {"coverage": {"all_country": {"list_cost": 21.9}}}
        raise AssertionError(caminho)
    antes = (meli._get, meli.tem_chave, w.precos.lista)
    meli._get, meli.tem_chave = get, (lambda: True)
    w.precos.lista = lambda repo: [{"mlb": "MLB7285008092", "categoria": "MLB1000", "tipo_id": "gold_special", "seller_id": "9"}]
    try:
        r = w._calc_ml(None, {"mlb": "MLB7285008092", "sku": "SILVER-200", "preco": 309.99})
        assert r["categoria"] == "MLB6284" and r["origem_categoria"] == "meu anúncio" and r["tipo"] == "gold_pro" and r["full"]
        assert r["tarifas"]["gold_special"]["pct"] == 14 and r["tarifas"]["gold_pro"]["pct"] == 19
        assert r["frete"] == 21.9 and "medidas" in r["origem_frete"] and r["meu"]["mlb"] == "MLB111"
        r2 = w._calc_ml(None, {"mlb": "MLB7285008092", "sku": "SILVER-200", "preco": 60, "tipo": "gold_special"})
        assert r2["frete"] == 0 and r2["tipo"] == "gold_special"                 # abaixo de R$ 79 o comprador paga
    finally:
        meli._get, meli.tem_chave, w.precos.lista = antes
        meli._CACHE.clear()


def test_cinco_maiores_vendedores_do_produto():
    """01/10 (Bruno: "os 5 maiores vendedores dos últimos 30 dias e o preço médio deles"): pelo último export da marca no
    Explorador (busca pelo snapshot, que tem índice), vendedores do GTIN somados, preço = faturamento ÷ unidades."""
    import pandas as pd
    import nubi_web as w
    import meli
    class R:
        def snapshots(self, marca=None):
            return pd.DataFrame([{"id": 1, "marca": "ARMAF", "inicio": "2026-08-01", "fim": "2026-08-31"},
                                 {"id": 2, "marca": "ARMAF", "inicio": "2026-09-01", "fim": "2026-09-30"},
                                 {"id": 3, "marca": "LATTAFA", "inicio": "2026-09-01", "fim": "2026-09-30"}])
        def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
            assert tab in ("gtin_info", "ia_resumos"), tab
            return []
        def _todos(self, tab, params=None):
            assert tab == "anuncios" and params["snapshot_id"] == "in.(2)", params      # só o último export da marca
            return [{"vendedor": "MAMS", "vendedor_id": "h1", "un": 200, "fat": 43000, "snapshot_id": 2},
                    {"vendedor": "MAMS", "vendedor_id": "h1", "un": 100, "fat": 21000, "snapshot_id": 2},
                    {"vendedor": "OUTRA", "vendedor_id": "h2", "un": 50, "fat": 11500, "snapshot_id": 2},
                    {"vendedor": "ZERO", "vendedor_id": "h3", "un": 0, "fat": 0, "snapshot_id": 2}]
    antes = meli.ler_hash_lojas
    meli.ler_hash_lojas = lambda repo, chave=None: {"h1": {"nome": "MAMS ECOMMERCE", "confianca": "manual"}}
    try:
        m = w._calc_mercado(R(), {"titulo": "Perfume Club De Nuit Intense Da Armaf Edt 105ml"}, "6085010044644")
    finally:
        meli.ler_hash_lojas = antes
    assert [t["vendedor"] for t in m["top"]] == ["MAMS ECOMMERCE", "OUTRA"] and m["top"][0]["real"] and not m["top"][1]["real"]
    assert m["top"][0]["unidades"] == 300 and m["top"][0]["preco_medio"] == 213.33 and m["top"][1]["preco_medio"] == 230.0
    assert m["vendedores"] == 2 and m["unidades"] == 350 and m["preco_medio"] == 215.71 and m["fim"] == "2026-09-30"
    assert w._calc_mercado(R(), {"titulo": "x"}, "")["sem"]


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
