"""Posição do anúncio (card #78): lê a busca do Mercado Livre na ordem da tela, separa patrocinados e calcula posição e página."""
import os
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import coletor as c  # noqa: E402
import nubi_web as w  # noqa: E402

CLIQUE = "https://click1.mercadolivre.com.br/mclics/clicks/external/MLB/count?a=" + urllib.parse.quote(
    "https://produto.mercadolivre.com.br/MLB-5550001111-perfume-x?searchVariation=1", safe="")

PAGINA = f"""<html><head><title>Club de nuit intense | MercadoLivre</title></head><body><ol>
<li class="ui-search-layout__item"><div class="poly-card"><a class="poly-component__title" href="{CLIQUE}">Perfume Patrocinado X</a>
  <span>Patrocinado</span><span>Por OUTRALOJA</span><span class="andes-money-amount__fraction">199</span></div></li>
<li class="ui-search-layout__item"><div class="poly-card"><a class="poly-component__title" href="https://www.mercadolivre.com.br/club-de-nuit/p/MLB19876543?pdp_filters=item_id%3AMLB4440002222">Club De Nuit Intense 105ml</a>
  <span class="poly-component__seller">Por AURASCENT</span><img data-src="https://http2.mlstatic.com/foto1.webp"><span class="andes-money-amount__fraction">1.249</span></div></li>
<li class="ui-search-layout__item"><div class="poly-card"><a class="poly-component__title" href="https://produto.mercadolivre.com.br/MLB-3330003333-club-de-nuit-_JM">Club De Nuit Intense Armaf</a>
  <span>Por SIENO</span></div></li>
</ol></body></html>"""


def test_ml_id_prefere_o_item():
    assert c.ml_id([CLIQUE]) == "MLB5550001111"                              # patrocinado: destino codificado no clique
    assert c.ml_id(["https://www.mercadolivre.com.br/x/p/MLB19876543?pdp_filters=item_id%3AMLB4440002222"]) == "MLB4440002222"
    assert c.ml_id(["https://produto.mercadolivre.com.br/MLB-3330003333-club"]) == "MLB3330003333"
    assert c.ml_id(["https://www.mercadolivre.com.br/ajuda"]) is None


def test_le_a_pagina_de_busca_na_ordem():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
        b = p.chromium.launch(**({"executable_path": exe} if os.path.exists(exe) else {}))
        pg = b.new_page()
        pg.set_content(PAGINA)
        c.devagar = lambda *a, **k: None
        r = c.ml_resultados(pg)
        b.close()
    assert [x["id"] for x in r] == ["MLB5550001111", "MLB4440002222", "MLB3330003333"]
    assert r[0]["patrocinado"] and not r[1]["patrocinado"]
    assert r[1]["vendedor"] == "AURASCENT" and r[1]["preco"] == 1249 and r[1]["foto"].endswith("foto1.webp")


def test_acha_a_loja_pelos_meus_produtos():
    """Dica do Bruno: busca o meu produto, acha o card 'Por AURASCENT', abre o anúncio e segue para a lista do vendedor."""
    from playwright.sync_api import sync_playwright
    busca = PAGINA.replace("https://www.mercadolivre.com.br/club-de-nuit/p/MLB19876543?pdp_filters=item_id%3AMLB4440002222",
                           "https://produto.mercadolivre.com.br/MLB-4440002222-club")
    anuncio = '<html><body><h1>Club</h1><a href="https://lista.mercadolivre.com.br/_CustId_123">Ver mais anúncios do vendedor</a></body></html>'
    loja = ('<html><body><ol><li class="ui-search-layout__item"><a href="https://produto.mercadolivre.com.br/MLB-4440002222-a">Club</a></li>'
            '<li class="ui-search-layout__item"><a href="https://produto.mercadolivre.com.br/MLB-4440007777-b">Asad</a></li></ol></body></html>')
    with sync_playwright() as p:
        exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
        b = p.chromium.launch(**({"executable_path": exe} if os.path.exists(exe) else {}))
        pg = b.new_page()
        pg.route("https://lista.mercadolivre.com.br/_CustId_123", lambda r: r.fulfill(body=loja, content_type="text/html; charset=utf-8"))
        pg.route("https://lista.mercadolivre.com.br/club-*", lambda r: r.fulfill(body=busca, content_type="text/html; charset=utf-8"))
        pg.route("https://lista.mercadolivre.com.br/asad*", lambda r: r.fulfill(body="<html><body>nada</body></html>", content_type="text/html; charset=utf-8"))
        pg.route("https://produto.mercadolivre.com.br/**", lambda r: r.fulfill(body=anuncio, content_type="text/html; charset=utf-8"))
        c.devagar = lambda *a, **k: None
        out = c.ml_achar_pelos_produtos(pg, ["aurascent", "pureperfumaria"], ["asad lattafa 100ml", "club nuit intense 105ml"])
        b.close()
    assert list(out) == ["aurascent"]                                     # a outra loja não apareceu nas buscas
    url, an = out["aurascent"]
    assert url.endswith("_CustId_123") and [x["id"] for x in an] == ["MLB4440002222", "MLB4440007777"]


def test_posicao_organica_e_pagina():
    itens = [{"id": "MLB1", "patrocinado": True}] + [{"id": f"MLB{i}", "vendedor": "X"} for i in range(2, 60)]
    ls = w.posicoes_de_busca("club de nuit", itens, {"MLB55"}, "2026-09-26")
    meu = next(x for x in ls if x["meu"])
    assert meu["posicao"] == 55 and meu["posicao_organica"] == 54 and meu["pagina"] == 2      # 48 por página
    assert sum(1 for x in ls if not x["meu"]) == 3                                           # só os 3 primeiros concorrentes orgânicos
    assert not any(x["anuncio_id"] == "MLB1" for x in ls)                                     # patrocinado não é concorrente do topo


def test_termo_padrao():
    assert w.termo_padrao("Perfume Club De Nuit Intense Man 105ml Masculino Armaf") == "club nuit intense man armaf 105ml"


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
