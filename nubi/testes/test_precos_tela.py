# -*- coding: utf-8 -*-
"""Tela do Monitor de preços (01/10, Bruno: "mais organizada: data e hora da última atualização, quantas atualizações e um
botão de histórico de preços com o gráfico, o maior e o menor preço"). Rodar: python3 testes/test_precos_tela.py, na pasta nubi."""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import precos  # noqa: E402

STUB = """window.supabase = { createClient: () => { const sess = {access_token: "TOKEN", user: {id: "u1", email: "brmilani@gmail.com"}};
  return { auth: { getSession: async () => ({data: {session: sess}}), signOut: async () => {}, updateUser: async () => ({}),
    onAuthStateChange: cb => setTimeout(() => cb("INITIAL_SESSION", sess), 0) }, storage: {from: () => ({createSignedUrls: async () => ({data: []})})} }; } };"""


def dados():
    d = {precos.LISTA: [{"mlb": "MLB7440859356", "titulo": "Clássico", "loja": "MAMS ECOMMERCE", "seller_id": "1", "vendedor": "MAMS ECOMMERCE TOP14",
                          "preco_inicial": 221.26, "desde": "2026-09-30T03:00:00+00:00", "leituras": 14, "ultima_leitura": "2026-10-01T17:05:00+00:00",
                          "mais_vendido": "MAIS VENDIDO · 2º em Perfumes Jacques Bogart", "full": True, "catalogo": True, "estoque_mais": True,
                          "alerta": {"de": 209.9, "para": 215.0, "pct": 0.0243, "em": "2026-10-01T17:05:00+00:00", "visto": False}}],
         precos.HIST + "MLB7440859356": [
             {"dia": "2026-09-30", "em": "2026-09-30T12:00:00+00:00", "preco": 221.26, "preco_original": 299.0, "status": "ativo", "estoque": 50},
             {"dia": "2026-10-01", "em": "2026-10-01T13:00:00+00:00", "preco": 209.9, "preco_original": 299.0, "status": "ativo", "estoque": 48},
             {"dia": "2026-10-01", "em": "2026-10-01T17:05:00+00:00", "preco": 215.0, "preco_original": 299.0, "status": "ativo", "estoque": 47}]}
    precos._ler = lambda repo, chave, padrao: d.get(chave, padrao)
    itens = precos.painel(None)
    itens[0]["meu"] = {"sku": "3355991004672", "titulo": "Silver Scent Intense 200ml", "custo": 150.0, "disponivel": 7, "casado_por": "gtin"}
    itens[0]["calc"] = dict(precos.contas(215.0, 150.0, 30.1, 24.45, 10), sem_tarifa=False, sem_frete=False)
    return {"itens": itens, "max": 300, "calc": {"imposto_pct": 10}}


def test_tela():
    from playwright.sync_api import sync_playwright
    r = dados()
    x = r["itens"][0]
    assert x["leituras"] == 14 and not x["titulo_ok"] and x["minimo"] == 209.9 and x["maximo"] == 221.26, x
    aqui = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servidor_teste")
    porta = os.environ.get("PORTA_PT", "8826")
    srv = subprocess.Popen([sys.executable, "-W", "ignore", os.path.join(aqui, "servidor.py")],
                           env=dict(os.environ, IA_FALSA="1", OPENAI_API_KEY="x", PORTA=porta), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=2)
            break
        except OSError:
            time.sleep(0.5)
    try:
        with sync_playwright() as p:
            exe = os.environ.get("NUBI_CHROMIUM") or "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
            b = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
            for wd, ht, nome in ((1440, 900, "pc"), (390, 800, "cel")):
                pg = b.new_page(viewport={"width": wd, "height": ht})
                erros = []
                pg.on("pageerror", lambda e: erros.append(str(e)))
                pg.route("https://cdn.jsdelivr.net/**", lambda rt: rt.fulfill(content_type="application/javascript", body=STUB))
                pg.route("https://fonts.**", lambda rt: rt.abort())
                pg.route("**/api/app?r=ml_precos_lista*", lambda rt: rt.fulfill(content_type="application/json", body=json.dumps(r)))
                ML = {"categoria": "MLB6284", "origem_categoria": "meu anúncio", "tipo": "gold_special", "full": False,
                      "tarifas": {"gold_special": {"pct": 14, "fixa": 0, "total": 30.1}, "gold_pro": {"pct": 19, "fixa": 0, "total": 40.85}},
                      "dimensoes": "10x8x20,600", "frete": 24.45, "origem_frete": "pelas medidas do pacote, na minha conta do ML",
                      "meu": {"mlb": "MLB999", "tipo_id": "gold_special", "full": False, "dimensoes": "10x8x20,600", "preco": 229.9},
                      "mercado": {"top": [{"vendedor": "MAMS ECOMMERCE", "real": True, "unidades": 320, "preco_medio": 214.5},
                                          {"vendedor": "ICARBONXX P3", "real": False, "unidades": 150, "preco_medio": 219.9}],
                                  "vendedores": 12, "unidades": 610, "preco_medio": 217.3, "inicio": "2026-09-01", "fim": "2026-09-30"},
                      "minhas_vendas": {"inicio": "2026-09-01", "fim": "2026-09-30", "unidades": 41, "preco_medio": 226.4, "anuncios": []}}
                pg.route("**/api/app?r=ml_precos_calc_ml*", lambda rt: rt.fulfill(content_type="application/json", body=json.dumps(ML)))
                pg.goto(f"http://127.0.0.1:{porta}/#/precos")
                pg.wait_for_selector(".pm-card", timeout=15000)
                txt = pg.inner_text("#main")
                assert "Última atualização" in txt and "14 atualização(ões)" in txt and "Anúncio MLB7440859356" in txt, txt[:800]
                assert "01/10" in txt and "14:05" in txt, txt[:800]                   # 17:05 UTC = 14:05 em Brasília
                # 01/10 (print do Bruno): tags, "+50 disponíveis", aviso de preço e a calculadora com o meu custo
                assert "MAIS VENDIDO" in txt and "CATÁLOGO" in txt and "FULL" in txt and "+47 disponíveis" in txt, txt[:900]
                assert pg.locator(".pm-mudou").count() == 1 and "O preço mudou" in txt and "Lucro líquido" in txt and "R$ 150,00" in txt and "trocar" in txt
                # 01/10 (Bruno: "o iconezinho da calculadora da extensão"): 🧮 abre com os dados do ML e recalcula com outro preço
                pg.click("button.pm-calcbtn")
                pg.wait_for_selector("#pc-res .pc-lucro", timeout=5000)
                assert pg.input_value("#pc-pct") == "14" and pg.input_value("#pc-custo") == "150" and pg.input_value("#pc-imp") == "10"
                pg.wait_for_selector("#pc-ml >> text=Meu anúncio", timeout=5000)
                merc = pg.inner_text("#pc-merc")                                       # 5 maiores vendedores + o meu preço
                assert "MAMS ECOMMERCE" in merc and "R$ 214,50" in merc and "R$ 217,30" in merc and "R$ 229,90" in merc and "R$ 226,40" in merc, merc
                assert pg.input_value("#pc-g") == "600" and "Clássico 14%" in pg.inner_text("#pc-ml")
                assert "R$ -11,05" in pg.inner_text("#pc-res") or "-R$ 11,05" in pg.inner_text("#pc-res"), pg.inner_text("#pc-res")
                pg.fill("#pc-preco", "250")
                assert "R$ 15,55" in pg.inner_text("#pc-res"), pg.inner_text("#pc-res")   # 250 − 35 − 24,45 − 25 − 150
                assert "Venda a" in pg.inner_text("#pc-alvo-r")
                pg.click("#pc-usar")
                assert "15,0%" in pg.inner_text("#pc-res"), pg.inner_text("#pc-res")      # o preço sugerido dá a margem pedida
                pg.evaluate("document.querySelector('.pc-modal').scrollTop = 0")
                pg.screenshot(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), f"saida_calc_{nome}.png"))
                pg.click("[data-tipo=gold_pro]")                                         # Premium: 19% da API
                assert pg.input_value("#pc-pct") == "19", pg.input_value("#pc-pct")
                pg.click(".modal [data-fechar]")
                pg.click("button[data-hist]")
                pg.wait_for_selector(".pm-hist svg", timeout=5000)
                h = pg.inner_text(".pm-hist")
                assert "Menor preço" in h and "R$ 209,90" in h and "Maior preço" in h and "R$ 221,26" in h, h
                pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"precos_{nome}.png"), full_page=True)
                larg = pg.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")
                assert larg[0] <= larg[1] + 1, (nome, larg)
                assert not erros, erros
            b.close()
    finally:
        srv.terminate()
    print("ok monitor de preços (tela)")


if __name__ == "__main__":
    test_tela()
