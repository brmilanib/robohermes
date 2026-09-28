"""Estoque → 🛒 Compras e vendas DE VERDADE (28/09, pedido do Bruno): importa o estoque e o relatório de vendas por anúncio
pela tela e confere as listas (preciso comprar, mais vendidos, zerados) no computador e no celular."""
import base64, io, os, subprocess, sys, time, urllib.request
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_compras_estoque import _xlsx, VENDAS  # noqa: E402
AQUI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servidor_teste")
PORTA = os.environ.get("PORTA_COMPRAS", "8797")
env = dict(os.environ, IA_FALSA="1", OLLAMA_API_KEY="x", PORTA=PORTA)
srv = subprocess.Popen([sys.executable, "-W", "ignore", os.path.join(AQUI, "servidor.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
STUB = """window.supabase = { createClient: () => { const sess = {access_token: "TOKEN", user: {id: "u1", email: "brmilani@gmail.com"}};
  return { auth: { getSession: async () => ({data: {session: sess}}), signOut: async () => {}, updateUser: async () => ({}),
    onAuthStateChange: cb => setTimeout(() => cb("INITIAL_SESSION", sess), 0) }, storage: {from: () => ({createSignedUrls: async () => ({data: []})})} }; } };"""


def _estoque_xlsx(linhas=(("A-100", 10, 20, 50, 0), ("B-100", 100, 0, 50, 0), ("C-100", 0, 0, 50, 0), ("E-100", 0, 0, 50, 0))):
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["SKU", "Título", "Armazém", "Estoque Baixo", "Em Trânsito(Compra)", "Disponível", "Estoque Atual", "Custo Médio", "Subtotal"])
    for sku, disp, trans, custo, minimo in linhas:
        ws.append([sku, "Perfume " + sku[0], "My Warehouse", minimo, trans, disp, disp, custo, disp * custo])
    b = io.BytesIO(); wb.save(b); return b.getvalue()


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
            pg.goto(f"http://127.0.0.1:{PORTA}/#/estoque/compras"); pg.wait_for_selector(".es-cab", timeout=15000)
            if nome == "pc":
                pg.evaluate("""async ([e, v]) => { const buf = s => Uint8Array.from(atob(s), c => c.charCodeAt(0)).buffer;
                  await api('estoque_importar', {arquivo: 'Lista_de_Estoque.xlsx', origem: 'manual'}, {method: 'POST', body: buf(e)});
                  await api('estoque_vendas_importar', {arquivo: 'Vendas_por_Produtos_20260829-20260927_1.xlsx', origem: 'manual'}, {method: 'POST', body: buf(v)}); }""",
                            [base64.b64encode(_estoque_xlsx()).decode(), base64.b64encode(_xlsx(VENDAS)).decode()])
                pg.evaluate("telaCompras()"); pg.wait_for_selector("[data-cp-aba]", timeout=15000)
            txt = pg.inner_text("#main")
            assert "A-100" in txt and "fora do estoque" in txt, txt[:800]                   # D-100 vendeu e não está no estoque
            assert "Preciso comprar (3)" in txt and "Zerados (2)" in txt, txt[:600]
            pg.click("[data-cp-aba=zerados]"); pg.wait_for_timeout(800)
            assert pg.inner_text("tbody").strip().startswith("C-100")                      # zerado que vendeu vem primeiro
            pg.click("[data-cp-aba=vendidos]"); pg.wait_for_timeout(800)
            larg = pg.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")
            assert larg[0] <= larg[1] + 1, (nome, larg)                                    # sem rolagem de lado
            pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"compras_{nome}.png"), full_page=True)
            assert not erros, erros
        pg = b.new_page(viewport={"width": 1440, "height": 900})
        erros = []; pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.route("https://cdn.jsdelivr.net/**", lambda r: r.fulfill(content_type="application/javascript", body=STUB))
        pg.route("https://fonts.**", lambda r: r.abort())
        pg.goto(f"http://127.0.0.1:{PORTA}/#/estoque"); pg.wait_for_selector(".es-cab", timeout=15000)
        # 28/09 (Bruno): nas listas do Estoque, custo médio com a variação e, nos zerados, trânsito e mínimo
        pg.evaluate("""async e => { const buf = s => Uint8Array.from(atob(s), c => c.charCodeAt(0)).buffer;
          await api('estoque_importar', {arquivo: 'Lista_de_Estoque_2.xlsx', origem: 'manual'}, {method: 'POST', body: buf(e)}); }""",
                    base64.b64encode(_estoque_xlsx((("A-100", 40, 0, 55, 0), ("B-100", 0, 30, 50, 20), ("C-100", 0, 0, 50, 0),
                                                    ("E-100", 0, 0, 50, 0)))).decode())
        pg.evaluate("telaEstoque()"); pg.wait_for_selector(".es-mud", timeout=15000)
        mud = pg.inner_text(".es-mud")
        assert "▲ 10%" in mud and "em trânsito 30" in mud and "mín. 20" in mud, mud
        assert pg.locator(".es-mud .pos", has_text="em trânsito 30").count() == 2             # em Saíram e Zeraram; cobre o mínimo: verde
        pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), "estoque_listas.png"), full_page=True)
        # 28/09 (Bruno): perseguir anúncios (sem a chave do Apify aqui: cadastra e avisa da chave)
        pg.goto(f"http://127.0.0.1:{PORTA}/#/estoque/perseguir"); pg.wait_for_selector("#pg-form", timeout=15000)
        assert "APIFY_TOKEN" in pg.inner_text("#main")
        pg.fill("#pg-anuncio", "MLB4577439527"); pg.fill("#pg-termo", "ferrari black"); pg.fill("#pg-apelido", "Ferrari Black 125")
        pg.click("#pg-form button"); pg.wait_for_selector("text=Ferrari Black 125", timeout=10000)
        assert "“ferrari black”" in pg.inner_text("tbody") and "ainda não conferido" in pg.inner_text("tbody")
        pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), "perseguir.png"), full_page=True)
        assert not erros, erros
        b.close()
finally:
    srv.terminate()
print("ok compras real")
