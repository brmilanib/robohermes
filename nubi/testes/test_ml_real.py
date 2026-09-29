"""Mercado Livre DE VERDADE na tela (29/09, pedido do Bruno): #/ml (lojas identificadas e teste de conexão), análise do
anúncio (nota, KPIs, calculadora de margem), página da loja (perfil, nossos números, insights, grade com filtros e
exportar) e, no Explorador, "No Mercado Livre agora" no quadro do produto + "Descobrir a loja real" no quadro do vendedor.
As respostas da API vêm do dublê do test_meli (sem rede). Computador e celular, sem rolagem de lado e sem erro de JS."""
import json, os, subprocess, sys, time, urllib.parse, urllib.request
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import test_meli as tm  # noqa: E402
import meli  # noqa: E402
AQUI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servidor_teste")
PORTA = os.environ.get("PORTA_ML", "8805")
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_compras_real.py"), encoding="utf-8").read()
i = src.index('STUB = """'); STUB = eval(src[i + 7:src.index('"""', i + 10) + 3])
env = dict(os.environ, IA_FALSA="1", OLLAMA_API_KEY="x", PORTA=PORTA)
srv = subprocess.Popen([sys.executable, "-W", "ignore", os.path.join(AQUI, "servidor.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# respostas da API geradas com o dublê
tm._preparar()
HA, HB = "a" * 64, "b" * 64
ANUNCIO = meli.pagina_anuncio("MLB1000100")
ANUNCIO["meu"] = {"estoque": [{"sku": "XJ-ASAD-EL", "titulo": "Lattafa Asad Elixir", "custo_medio": 150.0, "disponivel": 3}]}
LOJA = meli.pagina_loja(tm.Repo(), "222222222")
LOJA["nubimetrics"] = {"hashes": [HB], "nomes": ["ICARBONXX P3"], "un": 2040, "fat": 567000.0, "marcas": ["Lipx"],
                       "produtos": [{"marca": "Lipx", "produto": "Lattafa Asad Elixir EDP 100 ml", "un": 2040, "fat": 567000.0, "anuncios": 2, "preco_medio": 277.94}]}
GTIN = {"anuncios": meli.por_gtin(["6290362346548"]),
        "casados": {HA: {"id": "111111111", "nome": "FINKE", "link": "https://perfil.mercadolivre.com.br/FINKE", "votos": 1, "confianca": "provável"}}}
HASH = {"lojas": {HA: GTIN["casados"][HA]}}
TESTE = meli.testar("MLB1000100", "6290362346548")
DESC = {"achou": True, "loja": {"id": "222222222", "nome": "ESSENCEPRIMEBR", "link": "https://perfil.mercadolivre.com.br/ESSENCEPRIMEBR",
                                "votos": 2, "confianca": "provável", "nivel": 5, "medalha": "Platinum"}}
SEG = {"achou": True, "loja": {"id": "222222222", "nome": "ICARBONXX", "link": "https://perfil.mercadolivre.com.br/ICARBONXX", "votos": 6,
                                "confianca": "provável", "anuncios": [{"anuncio": "MLB2000200", "link": "https://produto.mercadolivre.com.br/MLB-2000200",
                                                                      "titulo": "Perfume Asad Elixir Lattafa 100ml", "preco": 279.0, "full": True}]}}
RESP = {"meli_anuncio": ANUNCIO, "meli_loja": LOJA, "meli_gtin": GTIN, "meli_hash_lojas": HASH, "meli_teste": TESTE, "meli_descobrir": DESC,
        "meli_seguido": {"loja": None}, "meli_seguido_descobrir": SEG}
PROD = "Lattafa Asad Elixir EDP 100 ml"
LISTA = [{"codigo": "V01", "vendedor": "HIMALAIA.INDIGO", "vid": HA, "un": 2800, "fat": 742000, "share": 0.68, "preco_medio": 265.0,
          "ultimo_preco": 265.28, "anuncios": 3, "full": 0, "catalogo": 1, "loja_oficial": False},
         {"codigo": "V02", "vendedor": "ICARBONXX P3", "vid": HB, "un": 1300, "fat": 363000, "share": 0.32, "preco_medio": 279.0,
          "ultimo_preco": 279.0, "anuncios": 1, "full": 1, "catalogo": 1, "loja_oficial": False}]
REL = {"marca": "LATTAFA", "atual": {"inicio": "2026-08-01", "fim": "2026-09-27"}, "resumo": {"dias": 58}, "colunas_arquivo": ["Título"],
       "tabelas": {"produtos": [{"produto": PROD, "linha": "Asad Elixir", "tipo": "EDP", "volume": "100 ml"}],
                   "gtins": [{"gtin": "6290362346548", "produto": PROD}], "anuncios": [],
                   "vendedores": [{"codigo": "V01", "vendedor": "HIMALAIA.INDIGO", "vid": HA, "share": 0.1},
                                  {"codigo": "V02", "vendedor": "ICARBONXX P3", "vid": HB, "share": 0.05}]},
       "vendedores_produto": {PROD: LISTA},
       "produtos_vendedor": {"V02": [{"produto": PROD, "un": 1300, "fat": 363000, "anuncios": 1, "preco_medio": 279, "ultimo_preco": 279,
                                      "full": 1, "catalogo": 1, "share_no_produto": 0.32, "share_do_vendedor": 1, "categoria": "Perfumes", "marca": "Lattafa"}]},
       "lojas_ml": {}}


def responder(route):
    r = urllib.parse.parse_qs(urllib.parse.urlparse(route.request.url).query).get("r", [""])[0]
    if r in RESP:
        return route.fulfill(content_type="application/json", body=json.dumps(RESP[r]))
    return route.continue_()


for _ in range(40):
    try: urllib.request.urlopen(f"http://127.0.0.1:{PORTA}/", timeout=2); break
    except OSError: time.sleep(0.5)
try:
    with sync_playwright() as p:
        exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
        b = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        for w, h, nome in ((1440, 900, "pc"), (390, 800, "cel")):
            pg = b.new_page(viewport={"width": w, "height": h}, accept_downloads=True)
            erros = []; pg.on("pageerror", lambda e: erros.append(str(e)))
            pg.route("https://cdn.jsdelivr.net/**", lambda r: r.fulfill(content_type="application/javascript", body=STUB))
            pg.route("https://fonts.**", lambda r: r.abort())
            pg.route("**/api/app?r=meli_*", responder)
            larg = lambda: pg.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")
            tmp = os.environ.get("TMPDIR", "/tmp")
            # 1) início: lojas identificadas + teste de conexão
            pg.goto(f"http://127.0.0.1:{PORTA}/#/ml"); pg.wait_for_selector("#ml-lojas table", timeout=15000)
            assert "FINKE" in pg.inner_text("#ml-lojas")
            pg.click("#ml-teste"); pg.wait_for_selector("#ml-teste-res li", timeout=5000)
            assert "token do app" in pg.inner_text("#ml-teste-res") and "❌" not in pg.inner_text("#ml-teste-res")
            # 2) análise do anúncio
            pg.goto(f"http://127.0.0.1:{PORTA}/#/ml/anuncio/MLB1000100"); pg.wait_for_selector(".ml-score", timeout=15000)
            t = pg.inner_text("#main")
            assert "Anúncio forte" in t and "FINKE" in t and "R$ 265,28" in t and "-32%" in t and "Frete: R$ 24,45" in t, t[:800]
            assert "+1.000" in t and "2.260" in t, t[:1500]
            larg1 = larg(); assert larg1[0] <= larg1[1] + 1, (nome, "anuncio", larg1)
            pg.screenshot(path=f"{tmp}/ml_anuncio_{nome}.png", full_page=True)
            pg.click("#ml-calc"); pg.wait_for_selector("#cm-res .kpi", timeout=5000)
            res = pg.inner_text("#cm-res")                                   # 265,28 − 14% − 6,25 − 24,45 − 150 = 47,44
            assert "R$ 47,44" in res, res
            pg.fill("#cm-custo", "300"); assert "-" in pg.inner_text("#cm-res"), pg.inner_text("#cm-res")
            pg.keyboard.press("Escape"); pg.evaluate("document.querySelectorAll('.modal-bg').forEach(x => x.remove())")
            # 3) página da loja
            pg.goto(f"http://127.0.0.1:{PORTA}/#/ml/loja/222222222"); pg.wait_for_selector("#ml-grade .ml-card", timeout=15000)
            t = pg.inner_text("#main")
            assert "ESSENCEPRIMEBR" in t and "Platinum" in t and "Maringá" in t and "ICARBONXX P3" in t and "Nos nossos dados" in t, t[:1200]
            assert "Faturamento acumulado estimado" in t and "Produto destaque" in t, t[:2500]
            assert pg.locator("#ml-grade .ml-card").count() == 3
            pg.select_option("#ml-log", "full"); assert pg.locator("#ml-grade .ml-card").count() == 2
            pg.fill("#ml-q", "ferrari"); assert pg.locator("#ml-grade .ml-card").count() == 1
            with pg.expect_download() as dl:
                pg.click("#ml-csv")
            assert dl.value.suggested_filename.startswith("loja_ESSENCEPRIMEBR")
            larg1 = larg(); assert larg1[0] <= larg1[1] + 1, (nome, "loja", larg1)
            pg.screenshot(path=f"{tmp}/ml_loja_{nome}.png", full_page=True)
            # 4) Explorador: quadro do produto com "No Mercado Livre agora" e a loja real na tabela
            pg.evaluate(f"S.rel = {json.dumps(REL)}; S.marca = 'LATTAFA'; abrirVendedoresProduto({json.dumps(PROD)})")
            pg.wait_for_selector("#pq-ml .ml-item", timeout=15000)
            q = pg.inner_text(".modal.pq")
            assert "ESSENCEPRIMEBR" in q and "FINKE" in q and "= V01 no Nubimetrics" in q, q[:2000]
            assert "FINKE" in pg.inner_text(f"[data-mlvid='{HA}']")                  # a tabela ganhou o nome real
            larg1 = larg(); assert larg1[0] <= larg1[1] + 1, (nome, "quadro", larg1)
            pg.screenshot(path=f"{tmp}/ml_quadro_{nome}.png")
            pg.evaluate("document.querySelectorAll('.modal-bg').forEach(x => x.remove())")
            # 5) quadro do vendedor: descobrir a loja real
            pg.evaluate("abrirProdutosVendedor('V02')"); pg.wait_for_selector("#pv-ml-desc", timeout=5000)
            pg.click("#pv-ml-desc"); pg.wait_for_selector("#pv-ml .ml-loja", timeout=5000)
            assert "ESSENCEPRIMEBR" in pg.inner_text("#pv-ml")
            pg.screenshot(path=f"{tmp}/ml_vendedor_{nome}.png")
            pg.evaluate("document.querySelectorAll('.modal-bg').forEach(x => x.remove())")
            # 6) vendedor seguido (Concorrentes -> Vendedores): descobrir a loja, o link dela e os IDs/links dos anúncios
            pg.evaluate("() => { const d = document.createElement('div'); d.id = 'vml-loja'; document.querySelector('#main').prepend(d); lojaMLSeguido('ICARBONXX P3'); }")
            pg.wait_for_selector("#vml-desc", timeout=5000); pg.click("#vml-desc"); pg.wait_for_selector("#vml-loja .ml-loja", timeout=5000)
            pg.click("#vml-loja summary")
            v = pg.inner_text("#vml-loja")
            assert "ICARBONXX" in v and "MLB2000200" in v and "provável" in v, v
            assert pg.get_attribute("#vml-loja td a", "href").startswith("https://produto.mercadolivre.com.br/")
            assert not erros, erros
        # 6) sem as chaves na Vercel (hoje): só o aviso, nada quebra
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        erros = []; pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.route("https://cdn.jsdelivr.net/**", lambda r: r.fulfill(content_type="application/javascript", body=STUB))
        pg.route("https://fonts.**", lambda r: r.abort())
        pg.route("**/api/app?r=meli_*", lambda r: r.fulfill(status=400, content_type="application/json",
                                                           body=json.dumps({"erro": meli.FALTA_CHAVE})))
        pg.goto(f"http://127.0.0.1:{PORTA}/#/ml/anuncio/MLB1000100"); pg.wait_for_selector(".es-aviso", timeout=15000)
        assert "ainda não está ativa" in pg.inner_text("#main")
        pg.evaluate(f"S.rel = {json.dumps(REL)}; abrirVendedoresProduto({json.dumps(PROD)})")
        pg.wait_for_selector("#pq-ml .es-aviso", timeout=15000)
        assert "ML_CLIENT_ID" in pg.inner_text("#pq-ml") and "HIMALAIA.INDIGO" in pg.inner_text(".modal.pq")   # o resto do quadro segue igual
        assert not erros, erros
    print("ok mercado livre na tela (pc e celular)")
finally:
    srv.terminate()
