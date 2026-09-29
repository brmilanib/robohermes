"""Explorador → clicar no produto DE VERDADE (30/09, pedido do Bruno): quadro maior e, no cabeçalho, o mercado do produto e o
meu lado (vendo? preço médio, estoque, custo, minha posição), no computador e no celular."""
import base64, io, os, subprocess, sys, time, urllib.request
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_compras_estoque import _xlsx  # noqa: E402
AQUI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servidor_teste")
STUB = """window.supabase = { createClient: () => { const sess = {access_token: "TOKEN", user: {id: "u1", email: "brmilani@gmail.com"}};
  return { auth: { getSession: async () => ({data: {session: sess}}), signOut: async () => {}, updateUser: async () => ({}),
    onAuthStateChange: cb => setTimeout(() => cb("INITIAL_SESSION", sess), 0) }, storage: {from: () => ({createSignedUrls: async () => ({data: []})})} }; } };"""
PORTA = os.environ.get("PORTA_QUADRO", "8799")
env = dict(os.environ, IA_FALSA="1", OLLAMA_API_KEY="x", PORTA=PORTA)
srv = subprocess.Popen([sys.executable, "-W", "ignore", os.path.join(AQUI, "servidor.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _estoque():
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["SKU", "Título", "Armazém", "Estoque Baixo", "Em Trânsito(Compra)", "Disponível", "Estoque Atual", "Custo Médio", "Subtotal"])
    ws.append(["XJ-NAX100", "Perfume Xerjoff Naxos 1861 Edp 100ml", "My Warehouse", 5, 6, 4, 4, 900, 3600])
    ws.append(["XJ-ERBA100", "Xerjoff Erba Pura Edp 100ml", "My Warehouse", 0, 0, 2, 2, 800, 1600])
    b = io.BytesIO(); wb.save(b); return b.getvalue()


VENDAS = [("Xerjoff Naxos", "PUREHOME[Mercado Libre BR]", "XJ-NAX100", "MLB1", 10, 10, 15000, 1500),
          ("Xerjoff Naxos", "Purehome[Shopee]", "XJ-NAX100", "S1", 2, 2, 2800, 1400)]
LISTA = [{"codigo": "V01", "vendedor": "LOJA.LIDER", "un": 50, "fat": 80000, "share": 0.62, "preco_medio": 1600, "ultimo_preco": 1590,
          "anuncios": 3, "full": 2, "catalogo": 1, "loja_oficial": False},
         {"codigo": "V02", "vendedor": "PUREHOME", "un": 30, "fat": 45000, "share": 0.38, "preco_medio": 1500, "ultimo_preco": 1499,
          "anuncios": 1, "full": 0, "catalogo": 0, "loja_oficial": False}]
PROD = "Xerjoff Naxos 1861 EDP 100 ml"
REL = {"atual": {"inicio": "2026-08-01", "fim": "2026-09-27"}, "resumo": {"dias": 58}, "colunas_arquivo": ["Título"],
       "tabelas": {"produtos": [{"produto": PROD, "linha": "Naxos 1861", "tipo": "EDP", "volume": "100 ml", "abc": "A",
                                 "pct_full": 0.5, "pct_catalogo": 0.25}],
                   "gtins": [{"gtin": "8033488155025", "produto": PROD}],
                   "anuncios": [{"produto": PROD, "c0": "Perfume Xerjoff 1861 Naxos Eau De Parfum 100ml"}]},
       "vendedores_produto": {PROD: LISTA}, "produtos_vendedor": {}}

for _ in range(40):
    try: urllib.request.urlopen(f"http://127.0.0.1:{PORTA}/", timeout=2); break
    except OSError: time.sleep(0.5)
try:
    with sync_playwright() as p:
        exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
        b = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        for w, h, nome in ((1440, 900, "pc"), (390, 800, "cel")):
            pg = b.new_page(viewport={"width": w, "height": h})
            erros = []; pg.on("pageerror", lambda e: erros.append(str(e)))
            pg.route("https://cdn.jsdelivr.net/**", lambda r: r.fulfill(content_type="application/javascript", body=STUB))
            pg.route("https://fonts.**", lambda r: r.abort())
            pg.goto(f"http://127.0.0.1:{PORTA}/#/estoque"); pg.wait_for_selector(".es-cab", timeout=15000)
            if nome == "pc":
                pg.evaluate("""async ([e, v]) => { const buf = s => Uint8Array.from(atob(s), c => c.charCodeAt(0)).buffer;
                  await api('estoque_importar', {arquivo: 'Lista_de_Estoque.xlsx', origem: 'manual'}, {method: 'POST', body: buf(e)});
                  await api('estoque_vendas_importar', {arquivo: 'Vendas_por_Produtos_20260830-20260928_1.xlsx', origem: 'manual'}, {method: 'POST', body: buf(v)}); }""",
                            [base64.b64encode(_estoque()).decode(), base64.b64encode(_xlsx(VENDAS)).decode()])
            import json
            pg.evaluate(f"S.rel = {json.dumps(REL)}; abrirVendedoresProduto({json.dumps(PROD)})")
            pg.wait_for_function("() => document.querySelector('#pq-meu') && !document.querySelector('#pq-meu').innerText.includes('carregando')", timeout=15000)
            txt = pg.inner_text(".modal.pq")
            assert "Linha Naxos 1861" in txt and "8033488155025" in txt, txt[:600]
            assert "Sim" in txt and "12 un." in txt, txt[:1500]                             # vendo: 12 un. em 30 dias
            assert "R$ 1.483,33" in txt, txt[:1500]                                         # meu preço médio 17.800 ÷ 12
            assert "4 un." in txt and "trânsito 6" in txt and "mínimo 5" in txt, txt[:1500]
            assert "XJ-NAX100" in txt and "achado pelo título" in txt, txt[:1500]
            assert "margem antes das taxas" in txt and "LOJA.LIDER" in txt, txt[:1500]
            larg = pg.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")
            assert larg[0] <= larg[1] + 1, (nome, larg)                                    # sem rolagem de lado
            if nome == "pc":
                caixa = pg.evaluate("() => document.querySelector('.modal.pq').getBoundingClientRect().width")
                assert caixa > 1200, caixa                                                 # quadro maior
            pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"quadro_produto_{nome}.png"))
            assert not erros, erros
    print("ok quadro do produto (pc e celular)")
finally:
    srv.terminate()
