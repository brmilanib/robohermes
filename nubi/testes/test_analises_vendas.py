# -*- coding: utf-8 -*-
"""01/10 (Bruno): Minhas Lojas → 📊 Análises de Vendas → Vendas por Anúncio (relatório de 30 dias do UpSeller × estoque).
Rodar: python3 testes/test_analises_vendas.py, na pasta nubi."""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import nubi_web as w  # noqa: E402

VENDAS = {"arquivo": "Vendas_por_Anuncio.xlsx", "inicio": "2026-09-01", "fim": "2026-09-30", "dias": 30,
          "importado_em": "2026-10-01T03:40:00+00:00",
          "linhas": [
              {"sku": "XER-NAX-100", "loja": "Purehome [Mercado Livre]", "anuncio": "MLB123", "produto": "Xerjoff Naxos 100ml",
               "pedidos": 10, "unidades": 10, "valor": 15000, "preco_medio": 1500},
              {"sku": "XER-NAX-100", "loja": "Purehome [Shopee]", "anuncio": "2299", "produto": "Xerjoff Naxos 100ml",
               "pedidos": 5, "unidades": 5, "valor": 7000, "preco_medio": 1400},
              {"sku": "TORINO-21", "loja": "Purehome [Mercado Livre]", "anuncio": "MLB777", "produto": "Torino 21",
               "pedidos": 12, "unidades": 12, "valor": 18000, "preco_medio": 1500}]}
ESTOQUE = [{"sku": "XER-NAX-100", "titulo": "Naxos", "disponivel": 13, "atual": 14, "custo_medio": 820, "transito_compra": 2},
           {"sku": "TORINO-21", "titulo": "Torino", "disponivel": 0, "atual": 1, "custo_medio": 870}]


STUB = """window.supabase = { createClient: () => { const sess = {access_token: "TOKEN", user: {id: "u1", email: "brmilani@gmail.com"}};
  return { auth: { getSession: async () => ({data: {session: sess}}), signOut: async () => {}, updateUser: async () => ({}),
    onAuthStateChange: cb => setTimeout(() => cb("INITIAL_SESSION", sess), 0) }, storage: {from: () => ({createSignedUrls: async () => ({data: []})})} }; } };"""


class R:
    def _eq(self, v):
        return f"eq.{v}"

    def _req(self, metodo, tabela, q=None, corpo=None, **k):
        if tabela == "ia_resumos":
            return [{"texto": json.dumps(VENDAS)}] if "vendas_anuncio" in (q or {}).get("chave", "") else []
        if tabela == "estoque_atualizacoes":
            return [{"id": 1, "criado_em": "2026-10-01T03:30:00+00:00"}]
        return []


def test_unidade():
    w._estoque_itens = lambda repo, aid: ESTOQUE
    r = w.rota_estoque(R(), "GET", "estoque_vendas_anuncio", {}, b"")
    an = {(a["sku"], a["anuncio"]): a for a in r["anuncios"]}
    nax = an[("XER-NAX-100", "MLB123")]
    assert nax["estoque"] == 13 and nax["transito"] == 2 and nax["custo"] == 820, nax
    assert nax["cobertura_dias"] == 26.0, nax                    # 13 ÷ (15 un. do SKU em 30 dias) = 26 dias
    assert nax["link"] == "https://produto.mercadolivre.com.br/MLB-123" and an[("XER-NAX-100", "2299")]["link"] == ""
    assert an[("TORINO-21", "MLB777")]["cobertura_dias"] == 0.0
    t = r["totais"]
    assert t["unidades"] == 27 and t["valor"] == 40000 and t["skus"] == 2 and t["sem_estoque"] == 1, t
    lojas = {l["loja"]: l for l in r["lojas"]}
    assert lojas["PUREHOME (Mercado Livre)"]["valor"] == 33000 and lojas["PUREHOME (Shopee)"]["unidades"] == 5, lojas
    print("ok análises de vendas (unidade)")
    return r


def test_tela(r):
    from playwright.sync_api import sync_playwright
    aqui = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servidor_teste")
    porta = os.environ.get("PORTA_AV", "8817")
    env = dict(os.environ, IA_FALSA="1", OLLAMA_API_KEY="x", OPENAI_API_KEY="x", PORTA=porta)
    srv = subprocess.Popen([sys.executable, "-W", "ignore", os.path.join(aqui, "servidor.py")], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
                pg.route("**/api/app?r=estoque_vendas_anuncio*", lambda rt: rt.fulfill(content_type="application/json", body=json.dumps(r)))
                pg.goto(f"http://127.0.0.1:{porta}/#/analises-vendas/anuncio")
                try:
                    pg.wait_for_selector("#mv-tab tbody tr", timeout=15000)
                except Exception:
                    raise AssertionError((erros, pg.inner_text("body")[:1500]))
                txt = pg.inner_text("#main")
                assert "Análises de Vendas" in txt and "Por loja" in txt and "MLB123" in txt, txt[:800]
                assert pg.query_selector("#mv-tab tr.ec-urg") is not None           # Torino zerado vendendo
                assert "Análises de Vendas" in pg.inner_text("body")                 # item do menu
                pg.select_option("#mv-loja", "PUREHOME (Shopee)")
                assert pg.inner_text("#mv-n").startswith("1 de 3"), pg.inner_text("#mv-n")
                pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"analises_vendas_{nome}.png"), full_page=True)
                larg = pg.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")
                assert larg[0] <= larg[1] + 1, (nome, larg)
                assert not erros, erros
            b.close()
    finally:
        srv.terminate()
    print("ok análises de vendas (tela)")


if __name__ == "__main__":
    test_tela(test_unidade())
