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
from datetime import datetime as _dt, timezone as _tz  # noqa: E402


def datetime_br(*a):
    return _dt(*a, tzinfo=_tz.utc)          # o nubi guarda a hora de Brasília como UTC deslocado

VENDAS = {"arquivo": "Vendas_por_Anuncio.xlsx", "inicio": "2026-09-01", "fim": "2026-09-30", "dias": 30,
          "importado_em": "2026-10-01T03:40:00+00:00",
          "linhas": [
              {"sku": "XER-NAX-100", "loja": "Purehome [Mercado Livre]", "anuncio": "MLB123", "produto": "Xerjoff Naxos 100ml",
               "pedidos": 10, "unidades": 10, "valor": 15000, "preco_medio": 1500},
              {"sku": "XER-NAX-100", "loja": "Purehome [Shopee]", "anuncio": "2299", "produto": "Xerjoff Naxos 100ml",
               "pedidos": 5, "unidades": 5, "valor": 7000, "preco_medio": 1400},
              {"sku": "TORINO-21", "loja": "Purehome [Mercado Livre]", "anuncio": "MLB777", "produto": "Torino 21",
               "pedidos": 12, "unidades": 12, "valor": 18000, "preco_medio": 1500},
              {"sku": "", "sem_sku": True, "loja": "Pure [TikTok Shop BR]", "anuncio": "1734815535096432238", "produto": "Sem vínculo",
               "pedidos": 1, "unidades": 1, "valor": 100, "preco_medio": 100}]}
ESTOQUE = [{"sku": "XER-NAX-100", "titulo": "Naxos", "disponivel": 13, "atual": 14, "custo_medio": 820, "transito_compra": 2},
           {"sku": "TORINO-21", "titulo": "Torino", "disponivel": 0, "atual": 1, "custo_medio": 870}]


STUB = """window.supabase = { createClient: () => { const sess = {access_token: "TOKEN", user: {id: "u1", email: "brmilani@gmail.com"}};
  return { auth: { getSession: async () => ({data: {session: sess}}), signOut: async () => {}, updateUser: async () => ({}),
    onAuthStateChange: cb => setTimeout(() => cb("INITIAL_SESSION", sess), 0) }, storage: {from: () => ({createSignedUrls: async () => ({data: []})})} }; } };"""


# 01/10: histórico por dia — 7 dias de 30/09 para trás com 1 Naxos por dia no ML
DIAS = {f"2026-09-{d:02d}": {"dia": f"2026-09-{d:02d}", "unidades": 1, "valor": 1500, "pedidos": 1,
                              "linhas": [{"sku": "XER-NAX-100", "loja": "Purehome [Mercado Livre]", "anuncio": "MLB123",
                                          "unidades": 1, "valor": 1500, "pedidos": 1}]} for d in range(24, 31)}


class R:
    def __init__(self):
        self.gravados = []

    def _eq(self, v):
        return f"eq.{v}"

    def _todos(self, tabela, q):
        if tabela == "ia_resumos" and q.get("chave", "").startswith("like.vendas_anuncio_dia|"):
            return [{"chave": "vendas_anuncio_dia|" + d, "texto": json.dumps(x)} for d, x in DIAS.items()]
        return []

    def _req(self, metodo, tabela, q=None, corpo=None, **k):
        if metodo == "POST":
            self.gravados += corpo
            return []
        if tabela == "ia_resumos":
            return [{"texto": json.dumps(VENDAS)}] if (q or {}).get("chave", "") == "eq.vendas_anuncio|atual" else []
        if tabela == "estoque_atualizacoes":
            return [{"id": 1, "criado_em": "2026-10-01T03:30:00+00:00"}]
        return []


def _xlsx(linhas):
    import io
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Produtos", "Loja", "SKU Principal", "ID do Anúncios", "Pedidos Válidos", "Unidades Vendidas", "Valor de Vendas", "Preço Médio"])
    for l in linhas:
        ws.append(l)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def test_dia_abc_sem_sku():
    import estoque
    from datetime import datetime, timedelta, timezone
    # anúncio sem SKU Principal entra (arquivo real do Bruno: 49 de 320, R$ 34,7 mil), fora das listas por SKU
    b = _xlsx([["Naxos", "PURE [TikTok Shop BR]", "XER-NAX-100", "MLB1", 2, 2, 3000, 1500],
               ["Sem sku", "PURE [TikTok Shop BR]", "", "1734815535096432238", 3, 3, 300, 100]])
    ls = estoque.ler_vendas(b)
    assert len(ls) == 2 and ls[1]["sem_sku"], ls
    l = estoque.listas([], ls)
    assert len(l["anuncios"]) == 2 and [x["sku"] for x in l["mais_vendidos"]] == ["XER-NAX-100"], l["mais_vendidos"]
    # relatório de 1 dia vai para o histórico por dia e não troca o de 30 dias
    r = R()
    x = w.vendas_importar(r, b, "Vendas_por_Produtos_20260930-20260930_20261001.xlsx")
    assert x["dia"] == "2026-09-30" and r.gravados[0]["chave"] == "vendas_anuncio_dia|2026-09-30", (x, r.gravados)
    assert len(r.gravados) == 1
    # dias que faltam: ontem primeiro, só os que não estão guardados
    agora = datetime(2026, 10, 1, 12, tzinfo=timezone.utc) - timedelta(hours=3)
    pend = w.vendas_dias_pendentes(R(), agora)
    assert pend[0] == "2026-09-23" and "2026-09-30" not in pend and len(pend) == 23, pend[:3]
    # curva ABC com a regra do UpSeller (A até 80% acumulado, B até 95%)
    vs = [{"sku": f"S{i}", "anuncio": f"MLB{i}", "loja": "L", "valor": v, "unidades": 1} for i, v in enumerate([50, 30, 10, 5, 3, 2])]
    c = estoque.curva_abc(vs)
    assert [x["classe"] for x in c["itens"]] == ["A", "A", "B", "B", "C", "C"], c["itens"]
    assert [k["anuncios"] for k in c["classes"]] == [2, 2, 2] and c["classes"][0]["pct"] == 80.0, c["classes"]
    # 01/10: a Análise ABC do próprio UpSeller ("Classificação ABC") é guardada à parte e a letra dela vence a conta
    import openpyxl
    import io
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Produtos", "Loja", "SKU Principal", "ID do Anúncios", "Classificação ABC", "Valor de Vendas Válidas",
               "Percentual de vendas", "Percentual acumulado de vendas", "Volume de vendas válido", "Preço Médio"])
    ws.append(["Naxos", "PURE [TikTok Shop BR]", "XER-NAX-100", "MLB1", "A", 3000, "90%", "90%", 2, 1500])
    ws.append(["Sem sku", "PURE [TikTok Shop BR]", "", "1734815535096432238", "C", 300, "10%", "100%", 3, 100])
    bb = io.BytesIO()
    wb.save(bb)
    r = R()
    x = w.vendas_importar(r, bb.getvalue(), "Product_Sales_20260901_20260930_20261001140845.xlsx")
    assert x["abc"] and r.gravados[0]["chave"] == "vendas_abc|atual" and "A 1, B 0, C 1" in x["log"][0], (x, r.gravados)
    up = {("MLB2", "L"): "B"}
    c2 = estoque.curva_abc(vs, classes_upseller=up)
    assert c2["itens"][2]["classe"] == "B" and c2["itens"][1]["classe"] == "A", c2["itens"][:3]
    print("ok análises de vendas (dia, ABC, sem SKU)")


def test_unidade():
    w._estoque_itens = lambda repo, aid: ESTOQUE
    w._agora_br = lambda: datetime_br(2026, 10, 1, 9)
    r = w.rota_estoque(R(), "GET", "estoque_vendas_anuncio", {}, b"")
    an = {(a["sku"], a["anuncio"]): a for a in r["anuncios"]}
    nax = an[("XER-NAX-100", "MLB123")]
    assert nax["estoque"] == 13 and nax["transito"] == 2 and nax["custo"] == 820, nax
    assert nax["cobertura_dias"] == 26.0, nax                    # 13 ÷ (15 un. do SKU em 30 dias) = 26 dias
    assert nax["link"] == "https://produto.mercadolivre.com.br/MLB-123" and an[("XER-NAX-100", "2299")]["link"] == ""
    assert an[("TORINO-21", "MLB777")]["cobertura_dias"] == 0.0
    assert nax["un7"] == 7 and "un15" not in nax and r["janelas"] == [7], (nax, r["janelas"])   # 7 dias guardados
    assert len(r["serie"]) == 7 and r["abc"]["valor"]["classes"][0]["classe"] == "A" and nax["abc"], r["abc"]["valor"]["classes"]
    t = r["totais"]
    assert t["unidades"] == 28 and t["valor"] == 40100 and t["skus"] == 2 and t["sem_estoque"] == 1 and t["sem_sku"] == 1, t
    lojas = {l["loja"]: l for l in r["lojas"]}
    assert lojas["PUREHOME (Mercado Livre)"]["valor"] == 33000 and lojas["PUREHOME (Shopee)"]["unidades"] == 5, lojas
    # atalho do Mapeamento: só endereço do UpSeller
    rr = R()
    assert w.upseller_links(rr, {"mapeamento": "https://app.upseller.com/pt/products/mapping"})["mapeamento"].endswith("mapping")
    try:
        w.upseller_links(rr, {"mapeamento": "https://outro.site/x"})
        raise AssertionError("aceitou endereço de fora do UpSeller")
    except w.ErroNuvem:
        pass
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
                assert "7d: 7" in pg.inner_text("#mv-tab"), pg.inner_text("#mv-tab")[:400]
                pg.click("#mv-semsku")                                               # 01/10: lista dos sem SKU
                assert pg.inner_text("#mv-n").startswith("1 de 4") and "Sem vínculo" in pg.inner_text("#mv-tab"), pg.inner_text("#mv-n")
                assert pg.is_visible("#mv-aviso-semsku") and pg.is_visible("#mv-mapa") and pg.query_selector(".mv-copiar")
                pg.click("#mv-semsku-x")
                pg.select_option("#mv-loja", "PUREHOME (Shopee)")
                assert pg.inner_text("#mv-n").startswith("1 de 4"), pg.inner_text("#mv-n")
                pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"analises_vendas_{nome}.png"), full_page=True)
                pg.goto(f"http://127.0.0.1:{porta}/#/analises-vendas/abc")
                pg.wait_for_selector("#abc-tab tbody tr", timeout=15000)
                assert "Categoria A" in pg.inner_text("#main") and "Curva ABC" in pg.inner_text("#main")
                pg.click("[data-por='volume']")
                pg.wait_for_selector("#abc-tab tbody tr", timeout=5000)
                pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"analises_abc_{nome}.png"), full_page=True)
                larg = pg.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")
                assert larg[0] <= larg[1] + 1, (nome, larg)
                assert not erros, erros
            b.close()
    finally:
        srv.terminate()
    print("ok análises de vendas (tela)")


if __name__ == "__main__":
    test_dia_abc_sem_sku()
    test_tela(test_unidade())
