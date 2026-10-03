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
HASH = {"lojas": {HA: GTIN["casados"][HA]}, "nomes": {HA: "HIMALAIA.INDIGO"},
        "seguidos": {"ICARBONXX P3": {"id": "2540338692", "nome": "KAIDOXSTOREE", "link": "http://perfil.mercadolivre.com.br/KAIDOXSTOREE",
                                      "confianca": "manual", "prova": "conferida no navegador"}}}
TESTE = meli.testar("MLB1000100", "6290362346548")
DESC = {"achou": True, "loja": {"id": "222222222", "nome": "ESSENCEPRIMEBR", "link": "https://perfil.mercadolivre.com.br/ESSENCEPRIMEBR",
                                "votos": 2, "confianca": "provável", "nivel": 5, "medalha": "Platinum"}}
SEG = {"achou": True, "loja": {"id": "222222222", "nome": "ICARBONXX", "link": "https://perfil.mercadolivre.com.br/ICARBONXX", "votos": 6,
                                "confianca": "certa", "prova": "em 6 de 8 produto(s) dele no catálogo; loja oficial nº 23829; Full e tipo iguais",
                                "anuncios": [{"anuncio": "MLB2000200", "link": "https://produto.mercadolivre.com.br/MLB-2000200",
                                                                      "titulo": "Perfume Asad Elixir Lattafa 100ml", "preco": 279.0, "full": True}]}}
# 29/09: sem prova o nubi não grava: devolve as lojas que mais bateram e o Bruno escolhe ("É esta")
CANDS = {"achou": False, "testados": 3, "motivo": "nenhuma loja bateu com prova suficiente nos 3 produtos dele que estão no catálogo — confira as candidatas abaixo",
         "candidatas": [{"id": "2540338692", "nome": "KAIDOXSTOREE", "link": "https://perfil.mercadolivre.com.br/KAIDOXSTOREE", "produtos": 2, "sondados": 3,
                         "exato": 0, "perto": 2, "oficial": [], "prova": "em 2 de 3 produto(s) dele no catálogo; preço perto em 2; Full e tipo iguais"},
                        {"id": "900001", "nome": "OUTRALOJA", "link": "https://perfil.mercadolivre.com.br/OUTRALOJA", "produtos": 1, "sondados": 3,
                         "exato": 0, "perto": 1, "oficial": [], "prova": "em 1 de 3 produto(s) dele no catálogo; preço perto em 1; Full e tipo iguais"}]}
NOMEADA = {"ok": True, "loja": {"id": "2540338692", "nome": "KAIDOXSTOREE", "link": "https://perfil.mercadolivre.com.br/KAIDOXSTOREE",
                                "votos": 0, "confianca": "manual", "prova": "confirmada pelo Bruno", "anuncios": []}}
PEDIDOS = []
# 29/09: conta do ML (OAuth) e a comparação Nubimetrics x API do ML
CONTA = {"conectada": False, "retorno": "https://nubi-explorador.vercel.app/api/app?r=meli_retorno"}
COMP = {"loja": "222222222", "vendedor": "ESSENCE", "desde": "2026-09-27", "fotos": ["2026-09-27", "2026-09-28", "2026-09-29"],
        "hoje": {"anuncios": 120, "total_na_busca": 124, "bloqueados": 0, "faixa": 0.1, "em": "x", "vendidos_total": 26000},
        "dias": [{"de": "2026-09-27", "ate": "2026-09-28", "dias": ["2026-09-27"], "ml": 15, "nubi": 15, "novos": 0, "sumiram": 0, "desceu": 0, "faltam_nubi": []},
                 {"de": "2026-09-28", "ate": "2026-09-29", "dias": ["2026-09-28"], "ml": 10, "nubi": 14, "novos": 1, "sumiram": 0, "desceu": 1, "faltam_nubi": []}],
        "total": {"ml": 25, "nubi": 29}, "produtos": [{"chave": "6290362346548", "titulo": "Perfume Asad Elixir", "ml": 20, "nubi": 21}],
        "so_no_nubimetrics": [{"chave": "T:kit x", "nubi": 3}]}
OPCOES = {"lojas": {}, "opcoes": [{"vendedor": "ESSENCE", "loja": "222222222", "nome": "ESSENCEPRIMEBR", "confianca": "manual"}]}
RESP = {"meli_conta": CONTA, "meli_comparar": lambda d: COMP if d.get("loja") else OPCOES,"meli_anuncio": ANUNCIO, "meli_loja": LOJA, "meli_gtin": GTIN, "meli_hash_lojas": HASH, "meli_teste": TESTE, "meli_descobrir": DESC,
        "meli_seguido": {"loja": None}, "meli_seguido_nomear": NOMEADA,
        "meli_fotos_seguido": {"ini": "2026-09-01", "fim": "2026-09-27", "em": "2026-09-29T12:00:00+00:00", "itens": [
            {"foto": "https://http2.mlstatic.com/D_951134-MLB91143087125_082025-I.jpg", "title": "Perfume Bareeq Al Dhahab", "price": 149.9}]},
        "meli_seguido_descobrir": lambda d: CANDS if d.get("vendedor") == "SEM PROVA P1" else SEG,
        "meli_seguidos_lista": {"vendedores": [
            {"vendedor": "ICARBONXX P3", "nome_exibido": "ICARBONXX P3", "hash": "37E3A268395D" + "0" * 116, "relatorio_id": 9, "mes": "2026-09",
             "ate": "2026-09-27", "meses": 4, "importado_em": "x", "anuncios": 116, "ativos": 110, "com_gtin": 104, "catalogo": 80, "full": 60,
             "frete_gratis": 116, "premium": 3, "vendas": 1450000.0, "unidades": 5200, "marcas": 9, "top_marca": "Lattafa", "ml": None,
             "explorador": {"hashes": ["bdc86b8785bb706d" + "0" * 48], "anuncios": 102, "oficial": [23829]}},
            {"vendedor": "SEM PROVA P1", "nome_exibido": "SEM PROVA P1", "hash": "AB12" + "0" * 124, "relatorio_id": 5, "mes": "2026-09",
             "ate": None, "meses": 1, "importado_em": "x", "anuncios": 20, "ativos": 20, "com_gtin": 10, "catalogo": 5, "full": 20,
             "frete_gratis": 20, "premium": 0, "vendas": 90000.0, "unidades": 600, "marcas": 2, "top_marca": "Lattafa", "ml": None, "explorador": None},
            {"vendedor": "AIRON-AMBAR-INQUIETANTE", "nome_exibido": "AIRON-AMBAR-INQUIETANTE", "hash": "39918302BAC6" + "0" * 116, "relatorio_id": 3,
             "mes": "2026-09", "ate": None, "meses": 1, "importado_em": "x", "anuncios": 11, "ativos": 11, "com_gtin": 7, "catalogo": 2, "full": 0,
             "frete_gratis": 11, "premium": 0, "vendas": 12000.0, "unidades": 60, "marcas": 3, "top_marca": "Lattafa",
             "ml": {"id": "333", "nome": "AIRONSTORE", "link": "https://perfil.mercadolivre.com.br/AIRONSTORE", "confianca": "dúvida", "votos": 2, "anuncios": 1}}]}}
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
        corpo = json.loads(route.request.post_data or "{}") if route.request.method == "POST" else \
            {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(route.request.url).query).items() if k != "r"}
        PEDIDOS.append((r, corpo))
        x = RESP[r](corpo) if callable(RESP[r]) else RESP[r]
        return route.fulfill(content_type="application/json", body=json.dumps(x))
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
            t = pg.inner_text("#ml-lojas")                                           # 29/09: o nome que está no Nubimetrics
            assert "FINKE" in t and "HIMALAIA.INDIGO" in t and "KAIDOXSTOREE" in t and "ICARBONXX P3" in t and "(seguido)" in t, t
            links = pg.eval_on_selector_all("#ml-lojas td a[target=_blank]", "as => as.map(a => a.getAttribute('href'))")
            assert "https://perfil.mercadolivre.com.br/KAIDOXSTOREE" in links and all(l.startswith("https://") for l in links), links   # o ML manda http://
            pg.click("#ml-teste"); pg.wait_for_selector("#ml-teste-res li", timeout=5000)
            assert "token do app" in pg.inner_text("#ml-teste-res") and "❌" not in pg.inner_text("#ml-teste-res")
            assert "Conexões" in pg.inner_text("#main") and not pg.locator("#ml-conta").count()   # 03/10: a conta mudou de tela
            # 1a) a conta do ML mora em 🔌 Conexões (cartão do Mercado Livre)
            painel = {"plataformas": [{"chave": "ml", "nome": "Mercado Livre", "configurada": True, "faltam": [], "retorno": "x?r=loja_retorno&p=ml", "contas": []},
                                      {"chave": "shopee", "nome": "Shopee", "configurada": False, "faltam": ["SHOPEE_PARTNER_ID"], "retorno": "x", "contas": []}]}
            pg.route("**/api/app?r=lojas_conexoes*", lambda r: r.fulfill(content_type="application/json", body=json.dumps(painel)))
            pg.goto(f"http://127.0.0.1:{PORTA}/#/conexoes"); pg.wait_for_selector("#ml-conta button", timeout=15000)
            assert "Conectar conta do ML" in pg.inner_text("#ml-conta") and "Conta principal" in pg.inner_text("#ml-conta")
            assert "SHOPEE_PARTNER_ID" in pg.inner_text("#main")
            pg.screenshot(path=os.path.join(os.path.dirname(__file__), "saida_conexoes.png"), full_page=True)
            # 1b) comparação Nubimetrics x ML
            pg.goto(f"http://127.0.0.1:{PORTA}/#/ml/comparar?loja=222222222&vendedor=ESSENCE"); pg.wait_for_selector("#cmp-res table", timeout=15000)
            t = pg.inner_text("#cmp-res").replace("\xa0", " ")
            assert "ESSENCE" in t and "27/09" in t and "28/09" in t and "Total" in t and "✅" in t and "🔴" in t and "-13,8%" in t, t
            assert "Perfume Asad Elixir" in t and "T:kit x (3)" in t and "1 com vendido menor" in t, t
            assert pg.eval_on_selector("#cmp-sel", "s => s.value") == "222222222|ESSENCE"
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
            PEDIDOS.clear()
            pg.evaluate(f"S.rel = {json.dumps(REL)}; S.marca = 'LATTAFA'; abrirVendedoresProduto({json.dumps(PROD)})")
            pg.wait_for_selector("#pq-ml-abrir", timeout=15000); pg.wait_for_timeout(300)
            assert not [x for x in PEDIDOS if x[0] == "meli_gtin"], PEDIDOS             # 29/09: não abre sozinho
            pg.click("#pq-ml-abrir"); pg.wait_for_selector("#pq-ml .ml-item", timeout=15000)
            q = pg.inner_text(".modal.pq")
            assert "ESSENCEPRIMEBR" in q and "FINKE" in q and "= V01 no Nubimetrics" in q, q[:2000]
            assert "FINKE" in pg.inner_text(f"[data-mlvid='{HA}']")                  # a tabela ganhou o nome real
            pg.click("#pq-ml-fechar"); assert pg.locator("#pq-ml .ml-item").count() == 0 and pg.is_visible("#pq-ml-abrir")
            pg.click("#pq-ml-abrir"); assert pg.locator("#pq-ml .ml-item").count() == 2
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
            pg.wait_for_selector("#vml-fotos .ml-foto", timeout=5000)
            v = pg.inner_text("#vml-loja") + pg.inner_text("#vml-fotos")
            assert "ICARBONXX" in v and "MLB2000200" in v and "certa" in v and "loja oficial nº 23829" in v, v
            assert "Fotos dos anúncios no Nubimetrics" in v and "951134-MLB91143087125" in v and "R$ 149,90" in v, v
            assert pg.get_attribute("#vml-loja td a", "href").startswith("https://produto.mercadolivre.com.br/")
            # 6b) sem prova: candidatas com link; "É esta" grava a escolhida (manual)
            pg.evaluate("() => { document.querySelector('#vml-loja').remove(); document.querySelector('#vml-fotos').remove(); const d = document.createElement('div'); d.id = 'vml-loja'; document.querySelector('#main').prepend(d); lojaMLSeguido('SEM PROVA P1'); }")
            pg.wait_for_selector("#vml-desc", timeout=5000); pg.click("#vml-desc"); pg.wait_for_selector("#vml-cands .ml-cand", timeout=5000)
            v = pg.inner_text("#vml-loja")
            assert "Sem certeza" in v and "KAIDOXSTOREE" in v and "em 2 de 3 produto" in v and pg.locator("#vml-cands .ml-cand").count() == 2, v
            pg.click("#vml-cands [data-escolher='2540338692']")
            pg.wait_for_function("() => document.querySelector('#vml-loja').innerText.includes('confirmada pelo Bruno')", timeout=5000)
            assert "confirmada pelo Bruno" in pg.inner_text("#vml-loja"), (pg.inner_text("#vml-loja"), PEDIDOS[-3:])
            assert ("meli_seguido_nomear", {"vendedor": "SEM PROVA P1", "loja": "2540338692"}) in PEDIDOS, PEDIDOS[-3:]
            pg.evaluate("document.querySelector('#vml-loja').remove()")
            # 7) painel Vendedores × ML: todos os seguidos, dados técnicos e o botão em cada um
            pg.goto(f"http://127.0.0.1:{PORTA}/#/vendedores-ml"); pg.wait_for_selector("#sml-tab tbody tr", timeout=15000)
            t = pg.inner_text("#sml-tab")
            assert "ICARBONXX P3" in t and "37E3A268395D" in t and "116" in t and "R$ 1.450.000,00" in t and "AIRONSTORE" in t, t[:1500]
            pg.click("[data-desc='ICARBONXX P3']")
            pg.wait_for_function("() => document.querySelector(\"[data-sml='ICARBONXX P3'] .sml-loja\").innerText.includes('ICARBONXX')", timeout=5000)
            assert "ID 222222222" in pg.inner_text("[data-sml='ICARBONXX P3']") and "loja oficial nº 23829" in pg.inner_text("[data-sml='ICARBONXX P3']")
            assert "bdc86b8785" in t, t[:1500]
            pg.click("[data-desc='SEM PROVA P1']"); pg.wait_for_selector("[data-sml='SEM PROVA P1'] .ml-cand", timeout=5000)
            pg.click("[data-sml='SEM PROVA P1'] [data-escolher='2540338692']")
            pg.wait_for_function("() => document.querySelector(\"[data-sml='SEM PROVA P1'] .sml-loja\").innerText.includes('manual')", timeout=5000)
            assert "KAIDOXSTOREE" in pg.inner_text("[data-sml='SEM PROVA P1']")
            larg1 = larg(); assert larg1[0] <= larg1[1] + 1, (nome, "painel", larg1)
            pg.screenshot(path=f"{tmp}/ml_painel_{nome}.png")
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
        pg.click("#pq-ml-abrir"); pg.wait_for_selector("#pq-ml .es-aviso", timeout=15000)
        assert "ML_CLIENT_ID" in pg.inner_text("#pq-ml") and "HIMALAIA.INDIGO" in pg.inner_text(".modal.pq")   # o resto do quadro segue igual
        assert not erros, erros
    print("ok mercado livre na tela (pc e celular)")
finally:
    srv.terminate()
