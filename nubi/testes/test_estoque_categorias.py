"""Estoque → 🏷️ Por categoria (30/09, pedido do Bruno: "meu estoque por categoria, igual ao ranking de marcas"): a marca
sai do título e a categoria é a do ranking (Árabe, Designer…); valor pelo custo e vendas de 30 dias por categoria."""
import base64, io, os, re, subprocess, sys, time, urllib.request
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
            if nome == "pc":
                # 02/10 (Bruno): gráfico estoque × vendas no Estoque (1 atualização só = aviso de poucos dias, sem erro)
                pg.goto(f"http://127.0.0.1:{PORTA}/#/estoque?x=1"); pg.wait_for_selector("#es-niveis", timeout=15000)
                pg.wait_for_function("() => !document.querySelector('#es-niveis').innerText.includes('Carregando')", timeout=15000)
                nv = pg.inner_text("#es-niveis")
                assert "Estoque × vendas" in nv and ("Poucos dias" in nv or "Vendas do dia" in nv), nv
                # 02/10 (Bruno: "potencial = custo × 1,85, editável; em todos os cards e o total")
                pg.goto(f"http://127.0.0.1:{PORTA}/#/estoque/marcas"); pg.wait_for_selector("#em-mk", timeout=15000)
                assert pg.input_value("#em-mk") == "1.85", pg.input_value("#em-mk")
                assert "custo total × markup 1,85×" in pg.inner_text(".kpis")
                pg.fill("#em-mk", "2"); pg.dispatch_event("#em-mk", "change")
                pg.wait_for_function("() => document.querySelector('.kpis') && document.querySelector('.kpis').innerText.includes('markup 2,00×')", timeout=15000)
                assert "sem venda em 30 d" not in pg.inner_text("#main")
                pg.fill("#em-mk", "1.85"); pg.dispatch_event("#em-mk", "change")
                pg.wait_for_function("() => document.querySelector('.kpis') && document.querySelector('.kpis').innerText.includes('markup 1,85×')", timeout=15000)
                # 02/10 (Bruno: "vou marcar as marcas que parei de vender, para tirar do relatório")
                pg.once("dialog", lambda dl: dl.accept())
                mp = pg.get_attribute(".em-card", "data-m"); sel = f".em-card[data-m='{mp}']"
                tot0 = pg.inner_text(".kpis")
                pg.click(sel); pg.wait_for_selector("#em-parar", timeout=8000); pg.click("#em-parar")
                pg.wait_for_selector(f"[data-voltar='{mp}']", timeout=15000)
                assert not pg.query_selector(sel), f"{mp} continua nos cards"
                assert "Marcas que não vendo mais" in pg.inner_text("#main") and pg.inner_text(".kpis") != tot0   # saiu dos totais
                pg.click(f"[data-voltar='{mp}']"); pg.wait_for_selector(sel, timeout=15000)
                assert pg.inner_text(".kpis") == tot0
                # 02/10 (Bruno): Estoque → 🔁 Reposição abre, troca de aba, guarda o caixa e lê o mercado sem erro
                def com_pedido(route):                       # a base de teste não tem o que comprar: põe 2 linhas no pedido
                    resp = route.fetch(); j = resp.json()
                    if j.get("pedido") is not None and not j["pedido"]:
                        base = {"classe": "A", "disponivel": 2, "transito": 3, "nivel_max": 20, "media_dia": 1.0, "venda_base": 1.4,
                                "faixa": 1, "cabe_no_caixa": True, "custo": 50.0, "ultimo_custo": 48.0, "categoria": "Perfumes › Árabe", "grupo": "Perfumes árabes",
                                "mercado": {"un_dia": 12.5, "preco_lider": 199.9, "preco_top5": 205.3}}
                        j["pedido"] = [dict(base, sku="TESTE-1", chave="TESTE1", titulo="Perfume Teste Um 100ml", marca="Lattafa", compra=15),
                                       dict(base, sku="TESTE-2", chave="TESTE2", titulo="Perfume Teste Dois 100ml", marca="Armaf", compra=4, mercado=None, classe="B", faixa=2)]
                        j["faixas"] = [{"faixa": 1, "nome": "Campeões", "skus": 1, "unidades": 15, "valor": 750.0},
                                       {"faixa": 2, "nome": "Classe B", "skus": 1, "unidades": 4, "valor": 200.0}]
                    route.fulfill(response=resp, json=j)
                pg.route(lambda u: "/api/app?" in u and re.search(r"[?&]r=estoque_reposicao(&|$)", u), com_pedido)
                pg.goto(f"http://127.0.0.1:{PORTA}/#/estoque/reposicao"); pg.wait_for_selector("#rp-dura-a", timeout=20000)
                assert "Reposição" in pg.inner_text(".es-cab") and "Pedido completo" in pg.inner_text(".kpis")
                for a in ("precos", "full", "campeoes", "parado", "mao", "pedido"):
                    pg.click(f"[data-rpa='{a}']"); pg.wait_for_selector(f"[data-rpa='{a}'].on", timeout=15000)
                # 02/10 (Bruno): lista de compra para imprimir / WhatsApp, por marca
                # 02/10 (Bruno: "junta a lista no pedido, coloca para eu digitar e lá embaixo gerar pedido")
                assert not pg.query_selector("#rp-lista")
                if pg.query_selector(".rp-t"):
                    th = pg.inner_text(".rp-t thead")
                    assert "Minha venda/dia" in th and "Média dos 5 primeiros" in th and "Acumulado" not in th, th
                else:
                    assert "Nada a comprar" in pg.inner_text("#main")
                if pg.query_selector("[data-q]"):
                    assert pg.input_value("[data-q='TESTE-1']") == "15" and "R$ 205" in pg.inner_text(".rp-t"), pg.inner_text(".rp-t")[:800]
                    # 02/10 (Bruno: "faixinha dividindo curva A, B e C e quantos % de cada no pedido")
                    assert "Este pedido por curva" in pg.inner_text("#rp-mix") and "Curva A 79%" in pg.inner_text("#rp-mix"), pg.inner_text("#rp-mix")
                    pg.click("[data-rpc='todos']"); pg.wait_for_selector("[data-rpc='todos'].on", timeout=15000)
                    assert pg.query_selector("tr.rp-curva-A") and pg.query_selector("tr.rp-curva-B") and not pg.query_selector("tr.rp-curva-C")
                    pg.fill("[data-q='TESTE-2']", "0"); pg.dispatch_event("[data-q='TESTE-2']", "input")
                    assert "Curva A 100%" in pg.inner_text("#rp-mix") and "Curva B 0%" in pg.inner_text("#rp-mix"), pg.inner_text("#rp-mix")
                    pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"reposicao_todos_{nome}.png"), full_page=False)
                    pg.click("[data-rpc='A']"); pg.wait_for_selector("[data-rpc='A'].on", timeout=15000)
                    pg.fill("[data-q='TESTE-1']", "7"); pg.dispatch_event("[data-q='TESTE-1']", "input")
                    assert "Campeões: 1 produtos · 7 un." in pg.inner_text("#rp-tot"), pg.inner_text("#rp-tot")
                    pg.click("#rp-gerar"); pg.wait_for_selector("#gp-corpo .lc-item", timeout=8000)
                    assert "Pedido de compra" in pg.inner_text(".modal") and "Perfumes árabes" in pg.inner_text("#gp-corpo")
                    # 02/10 (Bruno: "separado por fornecedor: árabes, nicho, eletrônicos; escrito e sem o total")
                    assert pg.query_selector("[data-gpc='0']") and pg.query_selector("[data-gpz='0']")
                    txt = pg.evaluate("() => { let t = ''; navigator.clipboard.writeText = x => { t = x; return Promise.resolve(); }; document.querySelector('[data-gpc=\\'0\\']').click(); return t; }")
                    assert txt.startswith("Olá") and "*Perfumes árabes*" in txt and "7 un. —" in txt and "Total" not in txt, txt
                    pg.click("[data-gpor='categoria']"); pg.wait_for_selector("[data-gpor='categoria'].on", timeout=5000)
                    pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"gerar_pedido_{nome}.png"), full_page=False)
                    pg.click(".modal [data-fechar]")
                    pg.click("#rp-zerar"); pg.wait_for_selector("#rp-tot", timeout=15000)
                    assert "Campeões: 0" in pg.inner_text("#rp-tot"), pg.inner_text("#rp-tot")
                    pg.click("#rp-sug"); pg.wait_for_selector("#rp-tot", timeout=15000)
                # 02/10 (Bruno: "campeão dura 30 dias, B e C 15; pedido separado por curva; cabeçalho fixo")
                assert pg.input_value("#rp-dura-a") == "30" and pg.input_value("#rp-dura-bc") == "15"
                assert pg.evaluate("getComputedStyle(document.querySelector('.rp-t thead th')).position") == "sticky"
                pg.click("[data-rpc='C']"); pg.wait_for_selector("[data-rpc='C'].on", timeout=15000)
                assert "Nada a comprar nesta curva" in pg.inner_text("#main") and "Curva C:" in pg.inner_text("#rp-tot")
                pg.click("[data-rpc='A']"); pg.wait_for_selector("[data-rpc='A'].on", timeout=15000)
                pg.fill("#rp-dura-a", "45"); pg.dispatch_event("#rp-dura-a", "change"); pg.wait_for_selector("#rp-dura-a[value='45']", timeout=15000)
                pg.fill("#rp-dura-a", "30"); pg.dispatch_event("#rp-dura-a", "change"); pg.wait_for_selector("#rp-dura-a[value='30']", timeout=15000)
                assert "Vendi 7 · 15 · 30 dias" in pg.inner_text(".rp-t thead") and "🚀" not in pg.inner_text(".rp-t") and "🧮" not in pg.inner_text(".rp-t")
                pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"reposicao_{nome}.png"), full_page=False)
                # 02/10: calculadora livre no cabeçalho, sem buscar produto
                pg.click("#bcalc"); pg.wait_for_selector("#pc-preco", timeout=8000)
                assert "Calculadora livre" in pg.inner_text(".modal") and not pg.query_selector("#pc-merc")
                pg.fill("#pc-preco", "200"); pg.fill("#pc-custo", "100"); pg.dispatch_event("#pc-custo", "input")
                assert "Lucro líquido" in pg.inner_text("#pc-res")
                pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"calc_livre_{nome}.png"), full_page=False)
                pg.click(".modal [data-fechar]")
                # 02/10 (Bruno: "as regras num botão que abre no meio"): ⚙️ Regras guarda o caixa
                pg.click("#rp-regras"); pg.wait_for_selector("#rg-caixa", timeout=8000)
                assert "Como o nubi calcula" in pg.inner_text(".modal")
                pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"regras_{nome}.png"), full_page=False)
                pg.fill("#rg-caixa", "50000"); pg.click("#rg-salvar")
                pg.wait_for_function("() => document.querySelector('.kpis') && document.querySelector('.kpis').innerText.includes('Cabe no caixa')", timeout=15000)
                with pg.expect_response(lambda r_: "estoque_reposicao_mercado" in r_.url, timeout=60000) as rm:
                    pg.click("#rp-merc")
                assert rm.value.status == 200, rm.value.text()[:400]
                pg.wait_for_selector("#rp-dura-a", timeout=20000)
                pg.click("#rp-regras"); pg.wait_for_selector("#rg-caixa", timeout=8000)
                pg.fill("#rg-caixa", ""); pg.click("#rg-salvar"); pg.wait_for_timeout(1500)
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
            # 02/10 (Bruno: "refaz a Início para um Dashboard, tudo organizado e clicável")
            pg.goto(f"http://127.0.0.1:{PORTA}/#/inicio"); pg.wait_for_selector(".dash-topo", timeout=15000)
            pg.wait_for_function("() => !document.querySelector('#ds-meus').innerText.includes('Carregando') && !document.querySelector('#ds-hoje').innerText.includes('Lendo')", timeout=30000)
            pg.wait_for_function("() => !document.querySelector('#ds-repo b') || document.querySelector('#ds-repo b').innerText !== '…'", timeout=30000)
            pg.wait_for_timeout(1500)
            t = pg.inner_text("#main")
            assert "Dashboard" in t and "Minha loja" in t and "Mercado" in t and "Meus destaques do mês" in t and "quem eu sigo" in t, t[:1500]
            assert "Dashboard" in pg.inner_text("#side")
            pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"dashboard_{nome}.png"), full_page=True)
            assert not erros, erros
            pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"estoque_categorias_{nome}.png"), full_page=True)
        b.close()
    print("ok estoque por categoria (tela)")
finally:
    srv.terminate()

# 02/10 (Bruno: "ranking de marcas dentro do meu estoque… sugestão de compra baseada na venda com crescimento de 20%")
rk = categorias.ranking_marcas(r["itens"], 0.20)
m = {x["marca"]: x for x in rk["marcas"]}
assert m["LATTAFA"]["skus"] == 1 and m["LATTAFA"]["unidades"] == 10 and m["LATTAFA"]["custo"] == 1000 and m["LATTAFA"]["potencial"] == 1850, m["LATTAFA"]   # custo × 1,85
assert m["LATTAFA"]["sugestao"] == 26 and m["LATTAFA"]["sugestao_custo"] == 2600          # 30 × 1,2 − 10 disponíveis = 26
assert m["FERRARI"]["potencial"] == round(m["FERRARI"]["custo"] * 1.85, 2) > 0 and m["FERRARI"]["sugestao"] == 0   # sem venda também tem potencial
assert rk["total"]["potencial"] == round(rk["total"]["custo"] * 1.85, 2) and rk["markup_usado"] == 1.85
assert rk["marcas"][0]["marca"] == "LATTAFA" and rk["marcas"][0]["posicao"] == 1           # ranking pelo custo em estoque
it = rk["itens"]["LATTAFA"][0]
assert (it["sku"], it["disponivel"], it["transito"], it["sugestao"], it["preco_venda"]) == ("ASAD-100", 10.0, 0.0, 26, 200.0), it
assert rk["total"]["sugestao"] == 26 and rk["total"]["custo"] == 1680

# 02/10: marca parada sai das listas do estoque (pela marca resolvida do SKU)
import nubi_web  # noqa: E402
sim, nao = nubi_web._separar_paradas([{"sku": "A", "marca": "LATTAFA"}, {"sku": "B", "marca": "Ferrari"}], ["Lattafa"])
assert [x["sku"] for x in sim] == ["B"] and [x["sku"] for x in nao] == ["A"]
ls = nubi_web._tirar_skus({"comprar": [{"sku": "A-1"}, {"sku": "B"}], "dias": 30}, {nubi_web.estoque._chave("A-1")})
assert ls == {"comprar": [{"sku": "B"}], "dias": 30}, ls
print("ok marcas paradas")
