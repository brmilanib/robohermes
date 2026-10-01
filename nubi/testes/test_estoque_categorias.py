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
# 01/10 (Sospiro Vibrato em Árabe): "PERFUME" existe como marca no Explorador, mas palavra de anúncio nunca é marca
con_p = dict(con, **{nubi.compacta(x): x for x in ["PERFUME", "SOSPIRO", "XERJOFF", "REVLON"]})
assert categorias.marca_do_titulo("Perfume Vibrato Sospiro Edp 100ml Importado Original", con_p) == "SOSPIRO"
assert categorias.marca_do_titulo("Perfume De Nicho Xerjoff Naxos Edp 100ml Importado", con_p) == "XERJOFF"
assert categorias.marca_do_titulo("Perfume Importado Original Kit", con_p) is None
assert categorias.tipo_produto("Escova Secadora Modeladora Revlon One-Step RVDR5222") == "Eletrônicos"
r_rev = categorias.estoque_por_categoria([{"sku": "REV-1", "titulo": "Escova Secadora Modeladora Revlon One-Step", "atual": 2, "custo_medio": 300},
                                          {"sku": "SOS-VIB-100", "titulo": "Perfume Vibrato Sospiro Edp 100ml", "atual": 26, "custo_medio": 900}], con_p, {})
cats_rev = {x["sku"]: (x["marca"], x["categoria"]) for x in r_rev["itens"]}
assert cats_rev["REV-1"] == ("REVLON", "Eletrônicos") and cats_rev["SOS-VIB-100"] == ("SOSPIRO", "Nicho"), cats_rev
assert "Eletrônicos" in r_rev["ordem"]
# 01/10 (prints do Bruno): utilidades domésticas, eletrônicos de verdade, skincare e casa; categoria por SKU (Bruno > Astra > tipo)
assert categorias.tipo_produto("Tabua Redonda Bambu Com Cabo Petisqueira Queijos E Frios") == "Utilidades domésticas"
assert categorias.tipo_produto("Tapete Capacho Para Porta 30x60 Em Fibra De Coco Natural") == "Utilidades domésticas"
assert categorias.tipo_produto("Conjunto Facas Shark Corte Profissional Inox Kit Com 5 Facas") == "Utilidades domésticas"
assert categorias.tipo_produto("FIRE TV STICK 4K SELECT") == "Eletrônicos" and categorias.tipo_produto("Drone Dji Neo Ultra Leve 4k") == "Eletrônicos"
# 01/10 (Bruno, "tudo errado ainda"): "blush" não manda perfume, body splash, shampoo e creme para Maquiagem
assert categorias.tipo_produto("Carolina Herrera Good Girl Blush Eau de Parfum Feminino 80ml") == "Perfume"
assert categorias.tipo_produto("Perfume Badee Al Oud Noble Blush By Lattafa Feminino 100 Ml") == "Perfume"
assert categorias.tipo_produto("Body Splash Badee Al Oud Noble Blush Perfume Mist Lattafa 250ml") == "Body splash"
assert categorias.tipo_produto("Shampoo A Seco Batiste Blush 200ml Kit 2 Unidades Com Brinde") == "Cabelo"
assert categorias.tipo_produto("Creamy Skincare Gel Creme Retinol 30g Anti Sinais Corretivo") == "Skincare"
assert categorias.tipo_produto("Blush Compacto Rosa Maquiagem Profissional") == "Maquiagem"
assert categorias.tipo_produto("Home Spray Perfume Interiores Linha Classicos Avatim 1100 Ml") == "Casa"
assert categorias.marca_do_titulo("Shampoo A Seco Batiste Blush 200ml", {"SHAMPOO": "SHAMPOO", "BATISTE": "BATISTE"}) == "BATISTE"
assert categorias.tipo_produto("Bronzeador Hawaiian Tropic Argan Oil Fps 15 Spray") == "Skincare"
assert categorias.tipo_produto("Difusor Eletrico Aromas Abajur Aromatizador De Ambientes") == "Casa"
r3 = categorias.estoque_por_categoria([{"sku": "A", "titulo": "Lenço De Algodão Demaquilante Bioré Refil", "atual": 1, "custo_medio": 10},
                                       {"sku": "B", "titulo": "Caneca Martelada Drinks Moscow Mule", "atual": 1, "custo_medio": 10}],
                                      con_p, {}, {}, {}, {}, {"A": "Maquiagem"}, {"A": "Skincare", "B": "Utilidades domésticas"})
c3 = {x["sku"]: (x["categoria"], x["categoria_fonte"]) for x in r3["itens"]}
assert c3["A"] == ("Maquiagem", "manual_sku") and c3["B"] == ("Utilidades domésticas", "astra"), c3
assert "Utilidades domésticas" in r3["opcoes_produto"] and categorias.categoria_produto_nome("utilidades domesticas") == "Utilidades domésticas"
assert categorias.categoria_produto_nome("ferramentas") == "Ferramentas" and categorias.categoria_produto_nome("") == ""
assert categorias.tipo_produto("Home Spray Perfume Interiores 1100 Ml") == "Casa"
assert categorias.tipo_produto("Body Splash Teriaq Perfume Mist Lattafa 250ml") == "Body splash"
assert categorias.tipo_produto("Perfume Ferrari Black 125ml Eau De Toilette") == "Perfume"
itens = [{"sku": "ASAD-100", "titulo": "Perfume Asad Elixir Lattafa 100 Ml", "atual": 10, "custo_medio": 100},
         {"sku": "FERRARI-125", "titulo": "Perfume Ferrari Black 125ml Eau De Toilette", "atual": 5, "custo_medio": 120},
         {"sku": "CREAMY-1", "titulo": "Protetor Solar Facial Creamy", "atual": 2, "custo_medio": 40},
         {"sku": "ZERO-1", "titulo": "Perfume Salvo Maison Alhambra Edp", "atual": 0, "custo_medio": 90}]
itens_tela = itens + [{"sku": "KIT-DOLCE", "titulo": "Q by Dolce and Gabbana Conjunto EDP", "atual": 3, "custo_medio": 200},
                      {"sku": "SERUM-X", "titulo": "Serum Facial Vitamina Zeta 30ml", "atual": 4, "custo_medio": 30}]
r = categorias.estoque_por_categoria(itens, con, {}, {"ASAD100": {"unidades": 30, "valor": 6000}})
c = {x["categoria"]: x for x in r["categorias"]}
assert c["Árabe"]["valor"] == 1000 and c["Árabe"]["skus"] == 2 and c["Árabe"]["zerados"] == 1, c["Árabe"]
assert c["Designer"]["valor"] == 600 and c["Skincare"]["valor"] == 80 and "Sem categoria" not in c, c   # 01/10: tipo fora de perfumaria = categoria própria
assert c["Árabe"]["cobertura_dias"] == 10.0 and c["Árabe"]["pct_vendas"] == 1.0, c["Árabe"]      # 10 un. ÷ 1/dia
pv = {x["sku"]: x["preco_venda"] for x in r["itens"]}
assert pv["ASAD-100"] == 200.0 and pv["FERRARI-125"] is None, pv          # 01/10: preço médio das vendas de 30 dias
assert r["sem_marca"] == [{"sku": "CREAMY-1", "titulo": "Protetor Solar Facial Creamy", "atual": 2.0, "valor": 80.0}]
assert {x["tipo"] for x in r["tipos"]} == {"Perfume", "Skincare"}
# 30/09 (print do Bruno): "Lattafa Yara" (marca+linha) é Árabe; "Dolce and Gabbana" = Dolce & Gabbana
assert categorias.classificar("LATTAFA YARA")[0] == "Árabe"
con2 = {nubi.compacta(x): x for x in ["DOLCE & GABBANA", "LATTAFA"]}
assert categorias.marca_do_titulo("Q by Dolce and Gabbana para mulheres EDP 100 ml", con2) == "DOLCE & GABBANA"
# ordem: a do Bruno > a do título > a do Astra
r2 = categorias.estoque_por_categoria(itens, con, {}, {}, {}, {"CREAMY1": "Creamy", "ASAD100": "Outra"})
assert {x["sku"]: x["marca"] for x in r2["itens"]}["CREAMY-1"] == "Creamy" and {x["sku"]: x["marca"] for x in r2["itens"]}["ASAD-100"] == "LATTAFA"
print("ok estoque por categoria (unidade)")

# ---- tela
AQUI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servidor_teste")
PORTA = os.environ.get("PORTA_EC", "8813")
env = dict(os.environ, IA_FALSA="1", OLLAMA_API_KEY="x", OPENAI_API_KEY="x", PORTA=PORTA)
srv = subprocess.Popen([sys.executable, "-W", "ignore", os.path.join(AQUI, "servidor.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _xlsx():
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["SKU", "Título", "Armazém", "Estoque Baixo", "Em Trânsito(Compra)", "Disponível", "Estoque Atual", "Custo Médio", "Subtotal"])
    for it in itens_tela:
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
                assert "Skincare" in txt and "Zeta" in txt, txt[:1500]                 # a marca escolhida no pc valeu
            sem_rolagem(pg, nome, "estoque por categoria")
            if nome == "pc":
                # 30/09 (Bruno: "o Astra já tem crédito; o título já fala a marca"): o Astra completa marca e categoria
                with pg.expect_response(lambda r_: "estoque_marcas_astra" in r_.url, timeout=20000) as ri:
                    pg.click("#ec-astra")
                assert ri.value.status == 200, ri.value.text()[:400]
                pg.wait_for_function("() => !document.querySelector('#ec-astra') || document.body.innerText.includes('Astra leu') || document.body.innerText.includes('banco do nubi')", timeout=15000)
                pg.wait_for_timeout(1500)
                pg.click(".kpi.ec-clica[data-ev='Designer']"); pg.wait_for_selector(".modal table", timeout=8000)
                # 01/10 (Bruno): o modo normal mostra disponível, custo médio e cobertura; marca/categoria só no "Editar"
                cab = pg.inner_text(".modal thead")
                assert "Disponível" in cab and "Custo médio" in cab and "Cobertura" in cab and "Categoria do produto" not in cab, cab
                # 01/10 (Bruno): em trânsito e preço de venda; sem "em pedido", sem Valor e Média/dia; linha pintada pela cobertura
                assert "Em trânsito" in cab and "Preço de venda" in cab and "Média/dia" not in cab, cab
                assert "em pedido" not in pg.inner_text(".modal tbody")
                assert pg.evaluate("[...document.querySelectorAll('.modal tbody tr')].every(tr => /ec-(urg|alerta|ok|)/.test(tr.className))")
                assert pg.query_selector(".modal .ec-marca") is None
                pg.click(".modal #ec-editar"); pg.wait_for_selector(".modal .ec-marca", timeout=8000)
                assert "KIT-DOLCE" in pg.inner_text(".modal"), pg.inner_text(".modal")[:800]      # Dolce & Gabbana pelo nome
                pg.click(".modal [data-fechar]")
                # 30/09 (Bruno): clicar na categoria abre os produtos dela; marca por SKU e categoria da marca editáveis.
                # 01/10: sérum é Skincare (categoria do tipo de produto), mesmo sem marca ou com marca de perfumaria
                pg.click(".kpi.ec-clica[data-ev='Skincare']"); pg.wait_for_selector(".modal .ec-marca", timeout=8000)
                m = pg.inner_text(".modal")
                assert "SERUM-X" in m and "ASAD-100" not in m, m[:800]
                pg.fill(".modal .ec-marca[data-sku='SERUM-X']", "Zeta"); pg.press(".modal .ec-marca[data-sku='SERUM-X']", "Enter")
                pg.wait_for_selector(".modal [data-eccat='Zeta']", timeout=10000)     # reabriu já com a marca nova
                pg.once("dialog", lambda d: d.accept())
                pg.select_option(".modal [data-eccat='Zeta']", "Nacional")
                pg.wait_for_timeout(1500)
                pg.wait_for_selector(".modal", timeout=8000); pg.click(".modal [data-fechar]")
                pg.click(".kpi.ec-clica[data-ev='Skincare']")
                pg.wait_for_selector(".modal .ec-marca", timeout=8000)
                m = pg.inner_text(".modal")
                assert "SERUM-X" in m and "Zeta" in m, m[:800]                       # continua Skincare, com a marca
                pg.click(".modal [data-fechar]")
            assert not erros, erros
            pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"estoque_categorias_{nome}.png"), full_page=True)
        b.close()
    print("ok estoque por categoria (tela)")
finally:
    srv.terminate()
