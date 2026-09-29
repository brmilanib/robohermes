"""Estoque → 🏷️ Por categoria (30/09, pedido do Bruno: "meu estoque por categoria, igual ao ranking de marcas"): a marca
sai do título e a categoria é a do ranking (Árabe, Designer…); valor pelo custo e vendas de 30 dias por categoria."""
import base64, io, os, subprocess, sys, time, urllib.request
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import categorias  # noqa: E402
import nubi  # noqa: E402
STUB = """window.supabase = { createClient: () => { const sess = {access_token: "TOKEN", user: {id: "u1", email: "brmilani@gmail.com"}};
  return { auth: { getSession: async () => ({data: {session: sess}}), signOut: async () => {}, updateUser: async () => ({}),
    onAuthStateChange: cb => setTimeout(() => cb("INITIAL_SESSION", sess), 0) }, storage: {from: () => ({createSignedUrls: async () => ({data: []})})} }; } };"""


def sem_rolagem(pg, nome, onde):
    larg = pg.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")
    assert larg[0] <= larg[1] + 1, (nome, onde, larg)

# ---- unidade: marca pelo título, tipo de produto e totais
con = {nubi.compacta(x): x for x in ["LATTAFA", "ASAD", "FERRARI", "BARBOURS", "MAISON ALHAMBRA"]}
assert categorias.marca_do_titulo("Perfume Asad Elixir Lattafa 100 Ml", con) == "LATTAFA"          # a mais longa ganha
assert categorias.marca_do_titulo("Body Splash Barbour's Seduction 200ml", con) == "BARBOURS"
assert categorias.marca_do_titulo("Protetor Solar Facial Creamy", con) is None
assert categorias.tipo_produto("Home Spray Perfume Interiores 1100 Ml") == "Casa"
assert categorias.tipo_produto("Body Splash Teriaq Perfume Mist Lattafa 250ml") == "Body splash"
assert categorias.tipo_produto("Perfume Ferrari Black 125ml Eau De Toilette") == "Perfume"
itens = [{"sku": "ASAD-100", "titulo": "Perfume Asad Elixir Lattafa 100 Ml", "atual": 10, "custo_medio": 100},
         {"sku": "FERRARI-125", "titulo": "Perfume Ferrari Black 125ml Eau De Toilette", "atual": 5, "custo_medio": 120},
         {"sku": "CREAMY-1", "titulo": "Protetor Solar Facial Creamy", "atual": 2, "custo_medio": 40},
         {"sku": "ZERO-1", "titulo": "Perfume Salvo Maison Alhambra Edp", "atual": 0, "custo_medio": 90}]
r = categorias.estoque_por_categoria(itens, con, {}, {"ASAD100": {"unidades": 30, "valor": 6000}})
c = {x["categoria"]: x for x in r["categorias"]}
assert c["Árabe"]["valor"] == 1000 and c["Árabe"]["skus"] == 2 and c["Árabe"]["zerados"] == 1, c["Árabe"]
assert c["Designer"]["valor"] == 600 and c["Sem categoria"]["valor"] == 80, c
assert c["Árabe"]["cobertura_dias"] == 10.0 and c["Árabe"]["pct_vendas"] == 1.0, c["Árabe"]      # 10 un. ÷ 1/dia
assert r["sem_marca"] == [{"sku": "CREAMY-1", "titulo": "Protetor Solar Facial Creamy", "atual": 2.0, "valor": 80.0}]
assert {x["tipo"] for x in r["tipos"]} == {"Perfume", "Skincare"}
print("ok estoque por categoria (unidade)")

# ---- tela
AQUI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servidor_teste")
PORTA = os.environ.get("PORTA_EC", "8813")
env = dict(os.environ, IA_FALSA="1", OLLAMA_API_KEY="x", PORTA=PORTA)
srv = subprocess.Popen([sys.executable, "-W", "ignore", os.path.join(AQUI, "servidor.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _xlsx():
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["SKU", "Título", "Armazém", "Estoque Baixo", "Em Trânsito(Compra)", "Disponível", "Estoque Atual", "Custo Médio", "Subtotal"])
    for it in itens:
        ws.append([it["sku"], it["titulo"], "My Warehouse", 0, 0, it["atual"], it["atual"], it["custo_medio"], it["atual"] * it["custo_medio"]])
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
            pg.goto(f"http://127.0.0.1:{PORTA}/#/estoque"); pg.wait_for_selector(".es-cab", timeout=15000)
            if nome == "pc":
                pg.evaluate("""async e => { const buf = s => Uint8Array.from(atob(s), c => c.charCodeAt(0)).buffer;
                  await api('estoque_importar', {arquivo: 'Lista_de_Estoque.xlsx', origem: 'manual'}, {method: 'POST', body: buf(e)}); }""",
                            base64.b64encode(_xlsx()).decode())
            pg.goto(f"http://127.0.0.1:{PORTA}/#/estoque/categorias")
            pg.wait_for_selector("text=Estoque por categoria", timeout=15000); pg.wait_for_selector("#ec-marcas table", timeout=15000)
            txt = pg.inner_text("#main")
            assert "Árabe" in txt and "Designer" in txt and "Lattafa" in txt and "Ferrari" in txt, txt[:1500]
            assert ("sem marca no título" in txt or nome == "cel") and "Por tipo de produto" in txt, txt[:1500]   # no cel a marca já foi corrigida
            if nome == "cel":
                assert "Nacional" in txt, txt[:1500]                                    # a categoria escolhida no pc valeu
            sem_rolagem(pg, nome, "estoque por categoria")
            if nome == "pc":
                # 30/09 (Bruno): clicar na categoria abre os produtos dela; marca por SKU e categoria da marca editáveis
                pg.click(".kpi.ec-clica[data-ev='Sem categoria']"); pg.wait_for_selector(".modal .ec-marca", timeout=8000)
                m = pg.inner_text(".modal")
                assert "CREAMY-1" in m and "ASAD-100" not in m, m[:800]
                pg.fill(".modal .ec-marca[data-sku='CREAMY-1']", "Creamy"); pg.press(".modal .ec-marca[data-sku='CREAMY-1']", "Enter")
                pg.wait_for_selector(".modal [data-eccat='Creamy']", timeout=10000)     # reabriu já com a marca nova
                pg.once("dialog", lambda d: d.accept())
                pg.select_option(".modal [data-eccat='Creamy']", "Nacional")
                pg.wait_for_function("() => !document.querySelector('.modal') || !document.querySelector('.modal').innerText.includes('CREAMY-1')", timeout=10000)
                pg.wait_for_selector(".modal", timeout=8000); pg.click(".modal [data-fechar]")
                pg.click(".kpi.ec-clica[data-ev='Nacional']")
                pg.wait_for_selector(".modal .ec-marca", timeout=8000)
                m = pg.inner_text(".modal")
                assert "Nacional" in m and "CREAMY-1" in m, m[:800]
                pg.click(".modal [data-fechar]")
            assert not erros, erros
            pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"estoque_categorias_{nome}.png"), full_page=True)
        b.close()
    print("ok estoque por categoria (tela)")
finally:
    srv.terminate()
