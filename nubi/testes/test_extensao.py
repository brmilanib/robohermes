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
assert a == {"vendedor": "2540338692", "item": "MLB4350649763", "criado": "2025-12-07T10:06:52.463Z", "apelido": "KAIDOXSTOREE",
             "vendidos": 10000, "oficial": None}, a

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
    b.close()
print("ok extensão do Chrome (leitor, busca e zip)")
