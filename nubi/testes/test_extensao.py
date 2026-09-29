# -*- coding: utf-8 -*-
"""Extensão do Chrome nubi · Mercado Livre (29/09, pedido do Bruno: igual à do Hunter): lê a página do anúncio (vendedor,
data, vendas) e mostra a loja embaixo de cada anúncio da busca e num quadro na página do produto. Testa o leitor da
página (node), a tela (Playwright, com o chrome.runtime de mentira) e o zip igual à pasta."""
import json, os, re, subprocess, sys, zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[1]
EXT = RAIZ / "public" / "extensao" / "nubi-ml"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gerar_extensao  # noqa: E402

# 1) o zip para baixar é a pasta de hoje
with zipfile.ZipFile(RAIZ / "public" / "extensao" / "nubi-ml.zip") as z:
    for f in EXT.iterdir():
        assert z.read(f"nubi-ml/{f.name}") == f.read_bytes(), f"zip desatualizado: rode python3 testes/gerar_extensao.py ({f.name})"
man = json.loads((EXT / "manifest.json").read_text())
assert man["manifest_version"] == 3 and "https://*.mercadolivre.com.br/*" in man["host_permissions"]
assert man["version"] == "0.7.4", man["version"]
assert man["action"]["default_popup"] == "popup.html"

# 2) leitor da página do anúncio
js = """global.chrome={runtime:{onMessage:{addListener(){}}}};const {lerAnuncio}=require(process.argv[1]);
const h='<script>{"item_id":"MLB4350649763","seller_id":2540338692,"date_created":"2025-12-07T10:06:52.463Z","sold_quantity":10000}</script>'
 + '<a href="https://perfil.mercadolivre.com.br/KAIDOXSTOREE">x</a>';
console.log(JSON.stringify(lerAnuncio(h,'https://produto.mercadolivre.com.br/MLB-4350649763-x')));"""
a = json.loads(subprocess.run(["node", "-e", js, str(EXT / "fundo.js")], capture_output=True, text=True, check=True).stdout)
assert a == {"vendedor": "2540338692", "item": "MLB4350649763", "produto": None, "criado": "2025-12-07T10:06:52.463Z",
             "apelido": None, "vendidos": 10000, "oficial": None, "categoria": None, "tipo": None, "preco": None,
             "titulo": None, "fotos": [], "estoque": None, "nota": None, "avaliacoes": None, "full": None, "logistica": None, "marca": None, "nome_loja": None,
             "produto_usuario": None}, a
# página de catálogo (/p/MLB…): produto do link, anúncio, categoria, tipo, preço e as fotos grandes
js2 = """global.chrome={runtime:{onMessage:{addListener(){}}}};const {lerAnuncio}=require(process.argv[1]);
const h='<meta itemprop="price" content="246.98"><h1 class="ui-pdp-title">Asad Elixir 100ml</h1><script>{"item_id":"MLB6123456789",'
 + '"category_id":"MLB6284","listing_type_id":"gold_pro","seller_id":1111222233}</script>'
 + '<img src="https://http2.mlstatic.com/D_NQ_NP_951134-MLB91143087125_082025-O.webp"><img src="https://http2.mlstatic.com/D_NQ_NP_2X_951134-MLB91143087125_082025-O.webp">';
console.log(JSON.stringify(lerAnuncio(h,'https://www.mercadolivre.com.br/asad/p/MLB67389993#polycard_client=search')));"""
b2 = json.loads(subprocess.run(["node", "-e", js2, str(EXT / "fundo.js")], capture_output=True, text=True, check=True).stdout)
assert (b2["produto"], b2["item"], b2["categoria"], b2["tipo"], b2["preco"], b2["titulo"]) == \
    ("MLB67389993", "MLB6123456789", "MLB6284", "gold_pro", 246.98, "Asad Elixir 100ml"), b2
js3 = """global.chrome={runtime:{onMessage:{addListener(){}}}};const {lerAnuncio}=require(process.argv[1]);
const h='<script id="__NORDIC_RENDERING_CTX__">_n.ctx.r={"components":{"bookmark":{"item_id":"MLB4430562169"},"header":{"reviews":{"rating":4.7,"amount":124}}},'
 + '"melidata_event":{"event_data":{"item_id":"MLB4430562169","seller_id":2162683356,"seller_name":"Essence Prime","listing_type_id":"gold_special",'
 + '"category_id":"MLB6284","logistic_type":"self_service","stock_type":"normal","quantity":98,"sold_quantity":500}}}</script>';
console.log(JSON.stringify(lerAnuncio(h,'https://www.mercadolivre.com.br/perfume-asad/up/MLBU3736729421#polycard_client=search')));"""
b3 = json.loads(subprocess.run(["node", "-e", js3, str(EXT / "fundo.js")], capture_output=True, text=True, check=True).stdout)
assert (b3["item"], b3["vendedor"], b3["tipo"], b3["categoria"], b3["estoque"], b3["vendidos"], b3["nota"], b3["avaliacoes"], b3["full"],
        b3["nome_loja"], b3["produto_usuario"], b3["criado"]) == ("MLB4430562169", "2162683356", "gold_special", "MLB6284", 98, 500, 4.7, 124,
                                                                   False, "Essence Prime", "MLBU3736729421", None), b3
# 29/09 (print do Bruno: vendedor "BRUNOMILANI"): na página /up/ o JSON vem num texto com as aspas escapadas e o
# apelido/perfil de QUEM ESTÁ LOGADO aparece antes; o leitor tem que achar o vendedor do anúncio
js4 = r"""global.chrome={runtime:{onMessage:{addListener(){}}}};const {lerAnuncio}=require(process.argv[1]);
const h='<a href="https://perfil.mercadolivre.com.br/BRUNOMILANI">bruno</a><script id="__NORDIC_RENDERING_CTX__">_n.ctx.r="{\\"viewer\\":{\\"nickname\\":\\"BRUNOMILANI\\"},'
 + '\\"event_data\\":{\\"item_id\\":\\"MLB4430562169\\",\\"seller_id\\":2162683356,\\"seller_name\\":\\"Essence Prime\\"}}"</script>';
console.log(JSON.stringify(lerAnuncio(h,'https://www.mercadolivre.com.br/x/up/MLBU3736729421')));"""
b4 = json.loads(subprocess.run(["node", "-e", js4, str(EXT / "fundo.js")], capture_output=True, text=True, check=True).stdout)
assert (b4["vendedor"], b4["item"], b4["apelido"]) == ("2162683356", "MLB4430562169", "Essence Prime"), b4
assert b2["fotos"] == ["https://http2.mlstatic.com/D_NQ_NP_2X_951134-MLB91143087125_082025-O.webp"], b2["fotos"]

# 3) na tela: a linha embaixo de cada anúncio da busca e o quadro na página do produto
LOJA = {"vendedor": "2540338692", "item": "MLB4350649763", "criado": "2025-12-07T10:06:52Z", "apelido": "KAIDOXSTOREE",
        "loja": {"id": 2540338692, "nome": "KAIDOXSTOREE", "link": "https://perfil.mercadolivre.com.br/KAIDOXSTOREE",
                 "cidade": "São Paulo", "uf": "SP", "nivel": "5", "medalha": "platinum", "vendas": 180000}}
BUSCA = """<ul>""" + "".join(f"""<li class="ui-search-layout__item"><a href="https://produto.mercadolivre.com.br/MLB-43506497{i:02d}-x">Perfume {i}</a></li>"""
                             for i in range(3)) + """<li class="ui-search-layout__item"><a href="https://www.mercadolivre.com.br/ajuda">ajuda</a></li></ul>"""
STUB = "window.chrome={runtime:{sendMessage:(m,cb)=>{window.PEDIDOS=(window.PEDIDOS||[]).concat([m]);setTimeout(()=>cb(%s),10);}}};" % json.dumps(LOJA)
with sync_playwright() as p:
    exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    b = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
    # 3) busca: cada card ganha os blocos na hora, sem abrir a página do anúncio (dava captcha no ML de verdade); o nubi
    #    completa em lote (ext_lista) vendedor, visitas e data. A busca real está no teste da página salva, mais abaixo.
    for w, h in ((1440, 900), (390, 800)):
        pg = b.new_page(viewport={"width": w, "height": h})
        erros = []; pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.set_content(f"<html><body>{BUSCA}</body></html>")
        pg.add_style_tag(content=(EXT / "estilo.css").read_text())
        pg.add_script_tag(content=STUB); pg.add_script_tag(content=(EXT / "conteudo.js").read_text())
        pg.wait_for_function("document.querySelectorAll('.nubi-ml-linha').length === 3", timeout=5000)
        pg.wait_for_function("(window.PEDIDOS||[]).some(m => m.rota === 'ext_lista')", timeout=5000)
        t = pg.inner_text("li").replace("\xa0", " ")
        for x in ("Vendas", "Envio", "Faturamento", "Visitas · 30 dias", "Participação na busca", "Anúncio criado", "Abrir análise"):
            assert x in t, (x, t)
        ped = pg.evaluate("PEDIDOS")
        assert not [m for m in ped if m["tipo"] == "anuncio"], ped                                    # nada aberto por trás
        assert [m for m in ped if m.get("rota") == "ext_lista"][0]["params"]["mlbs"] == "MLB4350649700,MLB4350649701,MLB4350649702"
        assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth + 1") and not erros, erros

    # 4) página do produto: quadro nubi Spy (os números do print do Hunter: Asad Elixir R$ 246,98 Premium)
    PAG = {"vendedor": "1111222233", "item": "MLB6123456789", "produto": "MLB67389993", "criado": None, "apelido": "PEREIRAELOISA",
           "estoque": 2, "nota": 5.0, "avaliacoes": 2, "full": True, "nome_loja": "Pereira Eloisa",
           "vendidos": 100, "categoria": "MLB6284", "tipo": "gold_pro", "preco": 246.98, "titulo": "Asad Elixir",
           "fotos": ["https://http2.mlstatic.com/D_NQ_NP_2X_1-O.webp"], "loja": None}
    NUB = {"loja": {"id": 1111222233, "nome": "PEREIRAELOISA20220126003352", "link": "https://perfil.mercadolivre.com.br/P",
                    "cidade": "Curitiba", "uf": "PR", "nivel": "5", "vendas": 36, "desde": None},
           "tarifas": {"gold_pro": {"pct": 17, "fixa": 0, "total": 41.99}, "gold_special": {"pct": 12, "fixa": 0, "total": 29.64}},
           "frete": 24.45, "visitas": {"anuncio": 142, "catalogo": 944, "catalogo_lidos": 21, "parte": 15},
           "total_concorrentes": 21, "criado_estimado": {"data": "2026-03-29", "folga_dias": 4},
           "historico": {"primeira_visita": "2026-01-19", "total": 19651, "dias_lidos": 365},
           "concorrentes": [{"anuncio": "MLB1", "link": "https://x/1", "vendedor_id": 1, "preco": 239.9, "full": True, "tipo": "Clássico",
                             "loja": "KAIDOXSTOREE", "eu": False},
                            {"anuncio": "MLB6123456789", "link": "https://x/2", "vendedor_id": 1111222233, "preco": 246.98, "full": False,
                             "tipo": "Premium", "loja": "PEREIRAELOISA20220126003352", "eu": True}]}
    STUB2 = ("window.chrome={runtime:{getURL:p=>'about:blank#'+p,sendMessage:(m,cb)=>{window.PEDIDOS=(window.PEDIDOS||[]).concat([m]);"
             "setTimeout(()=>cb(m.tipo==='pagina'?%s:m.tipo==='nubi'?%s:{ok:true}),10);}}};" % (json.dumps(PAG), json.dumps(NUB)))
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    erros = []; pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.set_content('<html><body><div class="ui-pdp-container__row--price"><span class="ui-pdp-price">R$ 246,98</span></div>'
                   '<meta itemprop="price" content="246.98"></body></html>')
    pg.add_style_tag(content=(EXT / "estilo.css").read_text())
    pg.add_script_tag(content=STUB2)
    js_conteudo = (EXT / "conteudo.js").read_text().replace("location.href", "'https://www.mercadolivre.com.br/asad/p/MLB67389993'")
    pg.add_script_tag(content=(EXT / "icones.js").read_text()); pg.add_script_tag(content=js_conteudo)
    pg.wait_for_function("(document.querySelector('#nubi-ml-quadro')||{}).innerText?.replace(/\\u00a0/g,' ').includes('R$ 180,54')", timeout=5000)
    t = pg.inner_text("#nubi-ml-quadro").replace("\xa0", " ")
    dias = (__import__("datetime").date.today() - __import__("datetime").date(2026, 1, 19)).days
    # 29/09 (Bruno): conversão pelos últimos 30 dias = vendas/dia × 30 ÷ visitas de 30 dias (142)
    v30 = 100 / max(dias, 1) * 30
    conv_txt = f"{100 * v30 / 142:.1f}%".replace(".", ",")
    for x in ("nubi Spy", "CATÁLOGO", "PREMIUM", "R$ 24,45", "R$ 41,99", "17%", "R$ 180,54",
              "Visitas do catálogo", "/dia", "944 nos últimos 30 dias", "15% deste anúncio",
              "Conversão (30 dias)", conv_txt, f"1 a cada {round(142 / v30)}",
              "+100 total", "Faturamento previsto", "R$ 24,7 mil", "Projeção 30 dias", f"≈ {round(v30)} vendas", "desde 19/01/2026",
              "menor R$ 239,90", "FULL", "2 un. · dura ≈ 5 dias", "Avaliações", "5 ★", "2 no total", "Ver 21 concorrentes", "PEREIRAELOISA20220126003352",
              "Curitiba - BR-PR", "Vendas totais", "Baixar mídias (1)", "Abrir na calculadora", "Pontuação nubi", "Ver mais dados", "Ver página", "No nubi"):
        assert x in t, (x, t)
    assert f"{dias} dias" in t or f"{dias - 1} dias" in t, t                    # fuso: conta dias inteiros
    assert "estimado" not in t and "1ª visita" not in t and "≈2" not in t        # 29/09: tempo ativo sem "estimado"
    assert "ML /items" not in t                                                  # a linha de diagnóstico saiu do quadro
    pg.locator("#nubi-ml-quadro").screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), "spy_quadro.png"))
    # o perfil do vendedor fica num cartão próprio (na página de verdade, embaixo do "Comprar agora")
    assert "PEREIRAELOISA20220126003352" in pg.inner_text("#nubi-ml-vendedor")                               # com a 1ª visita não precisa estimar
    assert pg.evaluate("document.querySelectorAll('#nubi-ml-quadro svg.nubi-ic').length") >= 15      # ícones de linha, não emoji
    assert pg.evaluate("document.querySelectorAll('.nubi-spy-termo i').length") == 5
    assert pg.evaluate("document.querySelector('.ui-pdp-container__row--price').nextElementSibling.id") == "nubi-ml-quadro"
    ped = [m for m in pg.evaluate("PEDIDOS") if m["tipo"] == "nubi"][0]
    assert ped["rota"] == "ext_ml" and ped["params"] == {"mlb": "MLB6123456789", "pid": "MLB67389993", "vendedor": "1111222233",
                                                         "categoria": "MLB6284", "tipo": "gold_pro", "preco": 246.98}, ped
    # card #121: o que a página mostrou vai para o nubi (ext_coleta), depois do quadro
    pg.wait_for_function("(window.PEDIDOS||[]).some(m => m.rota === 'ext_coleta')", timeout=5000)
    col = [m for m in pg.evaluate("PEDIDOS") if m.get("rota") == "ext_coleta"]
    assert len(col) == 1 and col[0]["params"] == {"mlb": "MLB6123456789", "vendedor": "1111222233", "loja": "Pereira Eloisa", "preco": 246.98,
                                                  "vendidos": 100, "full": 1, "fotos": "https://http2.mlstatic.com/D_NQ_NP_2X_1-O.webp"}, col
    pg.click("[data-nubi=conc]")
    assert pg.is_visible(".nubi-spy-lista") and "KAIDOXSTOREE" in pg.inner_text(".nubi-spy-lista")
    pg.click("[data-nubi=midias]")
    assert [m for m in pg.evaluate("PEDIDOS") if m["tipo"] == "baixar"][0]["urls"] == PAG["fotos"]
    pg.click("[data-nubi=calc]")
    assert pg.is_visible("#nubi-ml-painel") and pg.get_attribute("#nubi-ml-painel", "src") == "about:blank#painel.html"
    assert pg.is_visible("#nubi-ml-aba") and not erros, erros

    # 29/09 (Bruno): preço de venda = o de "outros meios" (R$ 167,90); o do Pix (142,71) tem rebate do próprio ML
    pg2 = b.new_page(viewport={"width": 1440, "height": 900})
    pg2.set_content('<html><body><div class="ui-pdp-container__row--price"><span class="ui-pdp-price">R$ 142,71</span>'
                    '<p class="ui-pdp-price__subtitles">ou <span class="andes-money-amount"><span class="andes-money-amount__currency-symbol">R$</span>'
                    '<span class="andes-money-amount__fraction">167</span><span class="andes-money-amount__cents">90</span></span> em outros meios</p></div>'
                    '<meta itemprop="price" content="142.71"></body></html>')
    pg2.add_style_tag(content=(EXT / "estilo.css").read_text())
    pg2.add_script_tag(content=STUB2)
    pg2.add_script_tag(content=(EXT / "icones.js").read_text()); pg2.add_script_tag(content=js_conteudo)
    pg2.wait_for_function("(window.PEDIDOS||[]).some(m => m.tipo === 'nubi')", timeout=5000)
    ped2 = [m for m in pg2.evaluate("PEDIDOS") if m["tipo"] == "nubi"][0]
    assert ped2["params"]["preco"] == 167.9, ped2

    # 5) painel lateral: calculadora (números do print do Hunter), histórico e gerador EAN
    pp = b.new_page(viewport={"width": 420, "height": 900})
    erros = []; pp.on("pageerror", lambda e: erros.append(str(e)))
    pp.goto((EXT / "painel.html").as_uri())
    pp.wait_for_selector("text=Olá, Bruno")
    pp.evaluate("""window.postMessage({tipo:'nubi-painel',aba:'calc',atual:%s},'*')""" % json.dumps(
        {"item": "MLB6123456789", "titulo": "Asad Elixir", "preco": 246.98, "tipo": "gold_pro", "tarifas": NUB["tarifas"], "frete": 24.45}))
    pp.wait_for_selector("text=Lucro líquido")
    t = pp.inner_text("#pn-corpo").replace("\xa0", " ")
    assert "R$ 180,54" in t and "73,10%" in t and "Clássico\n12%" in t and "Premium\n17%" in t, t
    pp.fill("#c-custo", "")
    pp.type("#c-custo", "99,5")                                                  # 29/09: a vírgula não some ao digitar
    pp.wait_for_timeout(300)
    assert pp.input_value("#c-custo") == "99,5", pp.input_value("#c-custo")
    pp.fill("#c-custo", "100")
    pp.wait_for_function("document.querySelector('.lucro .v').innerText.includes('80,54')")
    assert "80,54%" in pp.inner_text(".lucro")                                   # ROI = 80,54 / 100
    pp.fill("#c-imp", "10")
    pp.wait_for_function("document.querySelector('.lucro .v').innerText.includes('55,85')")   # − 10% de 246,98 (taxa 17% sem arredondar)
    pp.click("[data-tipo=gold_special]")
    assert "68,19" in pp.inner_text(".lucro .v")                                 # Clássico 12%: 246,98 − 29,64 − 24,45 − 24,70 − 100
    pp.click("#c-salvar")
    pp.wait_for_selector("text=Histórico de análises")
    assert "Asad Elixir" in pp.inner_text("#pn-corpo") and "R$ 68,19" in pp.inner_text("#pn-corpo").replace("\xa0", " ")
    pp.click("[data-aba=ean]"); pp.fill("#e-qtd", "3"); pp.click("#e-gerar")
    cods = pp.eval_on_selector_all(".ean", "xs => xs.map(x => x.textContent)")
    def ok13(c):
        return len(c) == 13 and c.startswith("789") and (10 - sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(c[:12])) % 10) % 10 == int(c[12])
    assert len(cods) == 3 and all(ok13(c) for c in cods), cods
    pp.fill("#e-conf", "6290362346548"); assert "válido" in pp.inner_text("#e-res")
    pp.fill("#e-conf", "6290362346549"); assert "não bate" in pp.inner_text("#e-res")
    pp.click("[data-aba=tend]"); pp.wait_for_selector("text=Tendências de busca")
    assert "extensão sem conexão" in pp.inner_text("#pn-corpo")                 # sem o chrome.runtime: avisa, não quebra
    assert not erros, erros
    b.close()
# 29/09 (Bruno: "a listagem é horrível", print com captcha): a página REAL da busca, salva pelo coletor (ml-pagina), com os 6
# primeiros cards e a lista "printed_result" do estado. O vendedor não vem na página: a extensão NÃO abre anúncios (dava
# captcha) e pede ao nubi, em lote, o vendedor pelo produto (MLBU/MLBP), as visitas de 30 dias e a data.
with sync_playwright() as p3:
    exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    b3 = p3.chromium.launch(executable_path=exe) if os.path.exists(exe) else p3.chromium.launch()
    REAL = (RAIZ / "testes" / "dados" / "ml_busca_real.html").read_text()
    pr = b3.new_page(viewport={"width": 1440, "height": 1000})
    erros = []; pr.on("pageerror", lambda e: erros.append(str(e)))
    pr.set_content(f"<html><body>{REAL}</body></html>")
    pr.add_style_tag(content=(EXT / "estilo.css").read_text())
    pr.add_script_tag(content=(EXT / "fundo.js").read_text())
    pr.add_script_tag(content="""window.chrome={runtime:{sendMessage:(m,cb)=>{window.PEDIDOS=(window.PEDIDOS||[]).concat([m]);setTimeout(()=>cb(
      m.tipo==='busca'?{resultados:lerBusca(m.html)}:
      m.tipo==='nubi'&&m.rota==='ext_lista'?{itens:Object.fromEntries(m.params.mlbs.split(',').map(x=>[x.split(':')[0],
        {visitas30:300,vendedor:'111',loja:{nome:'LOJA TESTE',cidade:'Maringá',uf:'PR',nivel:'5',medalha:'platinum'}}]))}:{}),10);}}};""")
    pr.add_script_tag(content=(EXT / "icones.js").read_text()); pr.add_script_tag(content=(EXT / "conteudo.js").read_text())
    pr.wait_for_function("document.querySelectorAll('.nubi-ml-linha').length === 6 && document.body.innerText.includes('LOJA TESTE')", timeout=8000)
    pr.wait_for_timeout(300)
    cs = [x.replace("\xa0", " ") for x in pr.eval_on_selector_all(".nubi-ml-linha", "xs => xs.map(x => x.innerText)")]
    assert all("LOJA TESTE" in c and "~300" in c and "Agência" in c or "FULL" in c for c in cs), cs
    assert "+5.000" in cs[0] and "Abrir análise" in cs[0] and "R$ 1,4 mi" in cs[0], cs[0]
    assert pr.evaluate("[...document.querySelectorAll('li.ui-search-layout__item')].every(li => li.style.height === 'auto')")   # sem sobrepor
    ped = pr.evaluate("PEDIDOS")
    assert not [m for m in ped if m["tipo"] == "anuncio"], ped                         # nenhuma página aberta por trás
    lista = [m for m in ped if m.get("rota") == "ext_lista"]
    assert lista and "MLB5832648414:MLBU3510508734" in lista[0]["params"]["mlbs"], lista
    assert not erros, erros
    pr.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), "busca_real.png"), full_page=True)

    # 0.7.2 (print do Bruno no Chrome dele: "Vendas —" e "a página não trouxe o produto" em todos): no navegador de verdade o ML
    # tira o script do estado depois de montar. cedo.js (document_start) guarda a cópia; sem estado nenhum, o card é lido na tela.
    FALSO = """window.chrome={runtime:{sendMessage:(m,cb)=>{window.PEDIDOS=(window.PEDIDOS||[]).concat([m]);setTimeout(()=>cb(
      m.tipo==='busca'?{resultados:lerBusca(m.html)}:
      m.tipo==='nubi'&&m.rota==='ext_lista'?{itens:Object.fromEntries(m.params.mlbs.split(',').map(x=>[x.split(':')[0],{visitas30:300}]))}:{}),10);}}};"""
    def pagina(html, com_cedo=True):
        pg = b3.new_page(viewport={"width": 1440, "height": 1000})
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.route("https://lista.mercadolivre.com.br/teste", lambda r: r.fulfill(status=200, content_type="text/html", body=html))
        if com_cedo: pg.add_init_script((EXT / "cedo.js").read_text())
        pg.goto("https://lista.mercadolivre.com.br/teste")
        pg.add_script_tag(content=(EXT / "fundo.js").read_text()); pg.add_script_tag(content=FALSO)
        pg.add_script_tag(content=(EXT / "icones.js").read_text()); pg.add_script_tag(content=(EXT / "conteudo.js").read_text())
        pg.wait_for_function("document.querySelectorAll('.nubi-ml-linha').length === 6 && document.body.innerText.includes('~300')", timeout=8000)
        pg.wait_for_timeout(300)
        return pg, errs
    TIRA = "<script>document.querySelectorAll('#__NORDIC_RENDERING_CTX__').forEach(s => s.remove())</script>"
    pt, errs = pagina(f"<html><body>{REAL}{TIRA}</body></html>")
    assert pt.evaluate("!document.getElementById('__NORDIC_RENDERING_CTX__')")
    lista = [m for m in pt.evaluate("PEDIDOS") if m.get("rota") == "ext_lista"]
    assert lista and "MLB5832648414:MLBU3510508734" in lista[0]["params"]["mlbs"], lista     # o pid veio da cópia
    c0 = pt.eval_on_selector_all(".nubi-ml-linha", "xs => xs.map(x => x.innerText)")[0].replace("\xa0", " ")
    assert "+5.000" in c0, c0
    assert not errs, errs
    # sem estado nenhum (script apagado antes da extensão): vendidos lidos no próprio card ("+5mil vendidos")
    SEM = re.sub(r'<script id="__NORDIC_RENDERING_CTX__">.*?</script>', "", REAL, flags=re.S)
    SEM = SEM.replace('<li class="ui-search-layout__item" style="height: 443.094px;"><div class="ui-search-result__wrapper ui-search-result__wrapper--large"><div class="andes-card poly-card poly-card--grid-card poly-card--xlarge poly-card--CORE andes-card--flat andes-card--primary andes-card--padding-0" id="_R_85kqcla_" data-andes-card="true" data-andes-card-hierarchy="primary">',                  # o card como no Chrome do Bruno
                      '<li class="ui-search-layout__item" style="height: 443.094px;"><div class="ui-search-result__wrapper ui-search-result__wrapper--large"><div class="andes-card poly-card poly-card--grid-card poly-card--xlarge poly-card--CORE andes-card--flat andes-card--primary andes-card--padding-0" id="_R_85kqcla_" data-andes-card="true" data-andes-card-hierarchy="primary"><span class="poly-component__seller">CHINAINK</span><span class="poly-reviews__total">| +5mil vendidos</span>', 1)
    assert "printed_result" not in SEM
    ps, errs = pagina(f"<html><body>{SEM}</body></html>", com_cedo=False)
    cs = [x.replace("\xa0", " ") for x in ps.eval_on_selector_all(".nubi-ml-linha", "xs => xs.map(x => x.innerText)")]
    assert "+5.000" in cs[0] and "CHINAINK" in cs[0], cs[0]                                 # loja pelo nome do card
    assert not errs, errs
    b3.close()

# 29/09 (Bruno: "quando dou um clique na extensão quero esse menu igual [ao do Hunter]"): o menu abre o painel na aba do ML
with sync_playwright() as p2:
    exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    b2 = p2.chromium.launch(executable_path=exe) if os.path.exists(exe) else p2.chromium.launch()
    pm = b2.new_page(viewport={"width": 360, "height": 700})
    erros = []; pm.on("pageerror", lambda e: erros.append(str(e)))
    pm.add_init_script("""window.ENVIADOS=[];window.chrome={runtime:{lastError:null},storage:{local:{get:(k,cb)=>cb({ajustes:{nome:'Bruno Milani'}})}},
      tabs:{query:(q,cb)=>cb([{id:7,url:'https://www.mercadolivre.com.br/x/p/MLB1'}]),
            sendMessage:(id,m,cb)=>{window.ENVIADOS.push(m);cb(m.tipo==='oi'?{ok:true,anuncio:{titulo:'x'}}:{ok:true});}}};window.close=()=>{};""")
    pm.goto((EXT / "popup.html").as_uri())
    pm.wait_for_selector("text=Painel disponível")
    tp = pm.inner_text("body")
    for x in ("nubi", "Abrir painel nesta página", "Mercado Livre", "ATALHOS", "Calculadora", "Histórico", "Tendências", "Gerador EAN", "BM", "Dashboard"):
        assert x in tp, (x, tp)
    pm.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), "spy_menu.png"))
    pm.click("[data-aba=calc]")
    assert pm.evaluate("ENVIADOS.map(m => m.tipo + ':' + (m.aba || ''))") == ["oi:", "abrir_painel:calc"]
    assert not erros, erros
    b2.close()
print("ok extensão do Chrome (leitor, busca, quadro nubi Spy, painel e zip)")
