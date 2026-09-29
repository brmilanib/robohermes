# -*- coding: utf-8 -*-
"""Extensão do Chrome nubi · Mercado Livre (29/09, pedido do Bruno: igual à do Hunter): lê a página do anúncio (vendedor,
data, vendas) e mostra a loja embaixo de cada anúncio da busca e num quadro na página do produto. Testa o leitor da
página (node), a tela (Playwright, com o chrome.runtime de mentira) e o zip igual à pasta."""
import json, os, subprocess, sys, zipfile
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

# 2) leitor da página do anúncio
js = """global.chrome={runtime:{onMessage:{addListener(){}}}};const {lerAnuncio}=require(process.argv[1]);
const h='<script>{"item_id":"MLB4350649763","seller_id":2540338692,"date_created":"2025-12-07T10:06:52.463Z","sold_quantity":10000}</script>'
 + '<a href="https://perfil.mercadolivre.com.br/KAIDOXSTOREE">x</a>';
console.log(JSON.stringify(lerAnuncio(h,'https://produto.mercadolivre.com.br/MLB-4350649763-x')));"""
a = json.loads(subprocess.run(["node", "-e", js, str(EXT / "fundo.js")], capture_output=True, text=True, check=True).stdout)
assert a == {"vendedor": "2540338692", "item": "MLB4350649763", "produto": None, "criado": "2025-12-07T10:06:52.463Z",
             "apelido": "KAIDOXSTOREE", "vendidos": 10000, "oficial": None, "categoria": None, "tipo": None, "preco": None,
             "titulo": None, "fotos": []}, a
# página de catálogo (/p/MLB…): produto do link, anúncio, categoria, tipo, preço e as fotos grandes
js2 = """global.chrome={runtime:{onMessage:{addListener(){}}}};const {lerAnuncio}=require(process.argv[1]);
const h='<meta itemprop="price" content="246.98"><h1 class="ui-pdp-title">Asad Elixir 100ml</h1><script>{"item_id":"MLB6123456789",'
 + '"category_id":"MLB6284","listing_type_id":"gold_pro","seller_id":1111222233}</script>'
 + '<img src="https://http2.mlstatic.com/D_NQ_NP_951134-MLB91143087125_082025-O.webp"><img src="https://http2.mlstatic.com/D_NQ_NP_2X_951134-MLB91143087125_082025-O.webp">';
console.log(JSON.stringify(lerAnuncio(h,'https://www.mercadolivre.com.br/asad/p/MLB67389993#polycard_client=search')));"""
b2 = json.loads(subprocess.run(["node", "-e", js2, str(EXT / "fundo.js")], capture_output=True, text=True, check=True).stdout)
assert (b2["produto"], b2["item"], b2["categoria"], b2["tipo"], b2["preco"], b2["titulo"]) == \
    ("MLB67389993", "MLB6123456789", "MLB6284", "gold_pro", 246.98, "Asad Elixir 100ml"), b2
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
    for w, h in ((1440, 900), (390, 800)):
        pg = b.new_page(viewport={"width": w, "height": h})
        erros = []; pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.set_content(f"<html><body>{BUSCA}</body></html>")
        pg.add_style_tag(content=(EXT / "estilo.css").read_text())
        pg.add_script_tag(content=STUB); pg.add_script_tag(content=(EXT / "conteudo.js").read_text())
        pg.wait_for_function("document.querySelectorAll('.nubi-ml-linha b').length === 3", timeout=5000)
        t = pg.inner_text("li")
        assert "KAIDOXSTOREE" in t and "São Paulo-SP" in t and "rep 5/5" in t and "180.000 vendas" in t and "criado 07/12/2025" in t, t
        assert pg.get_attribute(".nubi-ml-bt", "href") == "https://nubi-explorador.vercel.app/#/ml/loja/2540338692"
        assert len(pg.evaluate("PEDIDOS")) == 3 and pg.evaluate("PEDIDOS[0].tipo") == "anuncio"          # o link de ajuda não conta
        assert not erros, erros

    # 3b) busca com cards de catálogo (/p/MLB…, o do print do Bruno): o nubi diz a loja; o que ele não achar lê a página,
    #     e a página que não traz o vendedor mostra o motivo
    BUSCA2 = ('<ul><li class="ui-search-layout__item"><a href="https://www.mercadolivre.com.br/asad/p/MLB67389993#wid=MLB4350649763&sid=search">A</a></li>'
              '<li class="ui-search-layout__item"><a href="https://www.mercadolivre.com.br/asad/p/MLB11111111#polycard_client=search">B</a></li>'
              '<li class="ui-search-layout__item"><a href="https://www.mercadolivre.com.br/x/p/MLB22222222">C</a></li>'
              '<li class="ui-search-layout__item"><a href="https://produto.mercadolivre.com.br/MLB-4999999999-x">D</a></li></ul>')
    VENC = {"produtos": {"MLB67389993:MLB4350649763": {"item": "MLB4350649763", "vendedor": "2540338692", "do_card": True, "loja": LOJA["loja"]},
                         "MLB11111111": {"item": "MLB9", "vendedor": "1111222233", "do_card": False,
                                         "loja": {"nome": "PEREIRAELOISA", "cidade": "Curitiba", "uf": "PR", "vendas": 36}}}}
    STUB3 = ("window.chrome={runtime:{sendMessage:(m,cb)=>{window.PEDIDOS=(window.PEDIDOS||[]).concat([m]);"
             "setTimeout(()=>cb(m.tipo==='nubi'?%s:{item:'MLB4999999999',motivo:'página 403, 2 KB'}),10);}}};" % json.dumps(VENC))
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    erros = []; pg.on("pageerror", lambda e: erros.append(str(e)))
    pg.set_content(f"<html><body>{BUSCA2}</body></html>")
    pg.add_script_tag(content=STUB3); pg.add_script_tag(content=(EXT / "conteudo.js").read_text())
    pg.wait_for_function("[...document.querySelectorAll('.nubi-ml-linha')].every(x => !x.innerText.includes('lendo'))", timeout=5000)
    ls = pg.eval_on_selector_all(".nubi-ml-linha", "xs => xs.map(x => x.innerText)")
    assert "KAIDOXSTOREE" in ls[0] and "quem ganha" not in ls[0], ls
    assert "PEREIRAELOISA" in ls[1] and "quem ganha o produto agora" in ls[1], ls
    assert "não achei a loja" in ls[2] and "página 403, 2 KB" in ls[2] and "não achei a loja" in ls[3], ls
    ped = pg.evaluate("PEDIDOS")
    assert [m["params"]["pids"] for m in ped if m["tipo"] == "nubi"] == ["MLB67389993:MLB4350649763,MLB11111111,MLB22222222"], ped
    assert sorted(m["url"] for m in ped if m["tipo"] == "anuncio") == ["https://produto.mercadolivre.com.br/MLB-4999999999-x",
                                                                       "https://www.mercadolivre.com.br/x/p/MLB22222222"], ped
    assert not erros, erros
    pg.close()

    # 4) página do produto: quadro nubi Spy (os números do print do Hunter: Asad Elixir R$ 246,98 Premium)
    PAG = {"vendedor": "1111222233", "item": "MLB6123456789", "produto": "MLB67389993", "criado": None, "apelido": "PEREIRAELOISA",
           "vendidos": 100, "categoria": "MLB6284", "tipo": "gold_pro", "preco": 246.98, "titulo": "Asad Elixir",
           "fotos": ["https://http2.mlstatic.com/D_NQ_NP_2X_1-O.webp"], "loja": None}
    NUB = {"loja": {"id": 1111222233, "nome": "PEREIRAELOISA20220126003352", "link": "https://perfil.mercadolivre.com.br/P",
                    "cidade": "Curitiba", "uf": "PR", "nivel": "5", "vendas": 36, "desde": None},
           "tarifas": {"gold_pro": {"pct": 17, "fixa": 0, "total": 41.99}, "gold_special": {"pct": 12, "fixa": 0, "total": 29.64}},
           "frete": 24.45, "visitas": {"anuncio": 142, "catalogo": 944, "catalogo_lidos": 21, "parte": 15},
           "total_concorrentes": 21, "criado_estimado": {"data": "2026-03-29", "folga_dias": 4},
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
    pg.add_script_tag(content=js_conteudo)
    pg.wait_for_function("(document.querySelector('#nubi-ml-quadro')||{}).innerText?.replace(/\\u00a0/g,' ').includes('R$ 180,54')", timeout=5000)
    t = pg.inner_text("#nubi-ml-quadro").replace("\xa0", " ")
    for x in ("nubi Spy", "CATÁLOGO", "PREMIUM", "R$ 24,45", "R$ 41,99", "R$ 180,54", "31/dia", "0,5/dia", "944 nos últimos 30 dias", "15%",
              "+100 total", "R$ 24,7 mil", "≈", "dias", "desde 29/03/2026", "estimado pelo nº MLB6123456789", "Menor preço do catálogo", "R$ 239,90", "este é o 2º de 2", "Ver 21 concorrentes", "PEREIRAELOISA20220126003352",
              "Curitiba - PR", "Vendas totais", "Baixar mídias (1)", "Abrir na calculadora", "Nota nubi"):
        assert x in t, (x, t)
    assert pg.evaluate("document.querySelector('.ui-pdp-container__row--price').nextElementSibling.id") == "nubi-ml-quadro"
    ped = [m for m in pg.evaluate("PEDIDOS") if m["tipo"] == "nubi"][0]
    assert ped["rota"] == "ext_ml" and ped["params"] == {"mlb": "MLB6123456789", "pid": "MLB67389993", "vendedor": "1111222233",
                                                         "categoria": "MLB6284", "tipo": "gold_pro", "preco": 246.98}, ped
    pg.click("[data-nubi=conc]")
    assert pg.is_visible(".nubi-spy-lista") and "KAIDOXSTOREE" in pg.inner_text(".nubi-spy-lista")
    pg.click("[data-nubi=midias]")
    assert [m for m in pg.evaluate("PEDIDOS") if m["tipo"] == "baixar"][0]["urls"] == PAG["fotos"]
    pg.click("[data-nubi=calc]")
    assert pg.is_visible("#nubi-ml-painel") and pg.get_attribute("#nubi-ml-painel", "src") == "about:blank#painel.html"
    assert pg.is_visible("#nubi-ml-aba") and not erros, erros

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
print("ok extensão do Chrome (leitor, busca, quadro nubi Spy, painel e zip)")
