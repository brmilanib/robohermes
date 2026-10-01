# -*- coding: utf-8 -*-
"""01/10 (Bruno): Curva ABC do Gestor (ADS e lucro pós ADS), relatório de vendas do Gestor em CSV (colunas exatas, data do
pedido) e a lista "Para promoção" (sem venda há 60+ dias). Rodar: python3 testes/test_gestor_lucro.py, na pasta nubi."""
import io
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import estoque  # noqa: E402
import nubi_web as w  # noqa: E402

CSV = ('﻿"ID do pedido";Marketplace;Status;"Data de Compra";"Nome da Conta";ASIN;"SKU Externo";"SKU Interno";Título;Quantidade;'
       '"Preço Unitário";"Preço Total";Comissão;"Taxa de Envio";"Recebido do Marketplace";"Preço de Custo";Imposto;Lucro;"Margem (%)";'
       '"Estado do Comprador";Logística\n'
       '"n: 1";"Mercado Livre";Pago;"2026-09-30 10:00:00";"ESSENCE PRIME";1;EXT-1;XER-NAX-100;"Naxos";2;1500;3000;300;30;2600;1640;60;900;0.3;SP;full\n'
       '"n: 2";"Mercado Livre";Pago;"2026-09-10 10:00:00";"AURA SCENT";1;EXT-1;XER-NAX-100;"Naxos";1;1500;1500;150;20;1300;820;30;450;0.3;MG;not_full\n'
       '"n: 3";Shopee;Reembolsado parcialmente;"2026-09-29 10:00:00";"Purehome Shopee";;;TORINO-21;"Torino";1;900;900;90;0;800;870;20;-90;-0.1;RJ;"Shopee Xpress"\n'
       ).encode()


def _abc_xlsx():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Todas"
    ws.append(["SKU Interno", "Título", "Curva", "Unidades Vendidas", "Faturamento Total", "Lucro Bruto", "Lucro Pós Ads",
               "Margem (%)", "Margem Pós Ads (%)", "MPA (%)"])
    ws.append(["XER-NAX-100", "Naxos", "A", 3, 4500, 1350, 1000, 0.003, None, 0.22])
    ws.append(["TORINO-21", "Torino", "C", 1, 900, -90, -150, -0.001, None, -0.16])
    ws.append(["PARADO-1", "Parado", "Z", None, None, None, -40, None, None, -40])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


class R:
    def __init__(self):
        self.store = {}

    def _eq(self, v):
        return f"eq.{v}"

    def _todos(self, *a, **k):
        return []

    def _req(self, metodo, tabela, q=None, corpo=None, **k):
        if metodo == "POST":
            for c in corpo:
                self.store[c["chave"]] = c["texto"]
            return []
        if tabela == "ia_resumos":
            ch = (q or {}).get("chave", "")[3:]
            return [{"texto": self.store[ch]}] if ch in self.store else []
        if tabela == "estoque_atualizacoes":
            return [{"id": 1, "criado_em": "2026-10-01T03:30:00+00:00"}]
        return []


ESTOQUE = [{"sku": "XER-NAX-100", "titulo": "Naxos", "disponivel": 13, "custo_medio": 820},
           {"sku": "PARADO-1", "titulo": "Perfume parado", "disponivel": 5, "custo_medio": 100},
           {"sku": "SO-61", "titulo": "Vendeu há 61–90", "disponivel": 2, "custo_medio": 50}]


def test_unidade():
    # colunas exatas: Preço Total (não o unitário), SKU Interno, Nome da Conta; data, estado e logística
    ls = estoque.ler_gestor_vendas(CSV)
    assert ls[0]["valor"] == 3000 and ls[0]["sku"] == "XER-NAX-100" and ls[0]["conta"] == "ESSENCE PRIME", ls[0]
    assert ls[0]["data"] == "2026-09-30 10:00:00" and ls[0]["estado"] == "SP" and ls[0]["logistica"] == "full", ls[0]
    a = estoque.ler_abc_gestor(_abc_xlsx())
    nax = a[0]
    assert nax["ads"] == 350 and nax["mpa_pct"] == 22.22 and nax["margem_pct"] == 30.0, nax      # 1000 ÷ 4500
    z = [c for c in estoque.resumo_abc_gestor(a) if c["curva"] == "Z"][0]
    assert z["produtos"] == 1 and z["ads"] == 40 and z["lucro_pos_ads"] == -40, z
    r = R()
    w._estoque_itens = lambda repo, aid: ESTOQUE
    w._agora_br = lambda: datetime(2026, 10, 1, 9, tzinfo=timezone.utc)
    x = w.gestor_vendas_importar(r, _abc_xlsx(), "relatorio_curva_abc.xlsx")
    assert x["abc"] and "1 na curva Z" in x["log"][0], x
    w.gestor_vendas_importar(r, CSV, "reports_sales.csv", "2026-09-01", "2026-09-30")
    lu = w.rota_estoque(r, "GET", "estoque_analise_lucro", {}, b"")
    assert lu["totais"]["valor"] == 4500 and lu["fora"] == 1, lu["totais"]           # reembolsado fica fora
    pn = {p["sku"]: p for p in lu["produtos"]}
    assert pn["XER-NAX-100"]["un7"] == 2 and pn["XER-NAX-100"]["un15"] == 2 and pn["XER-NAX-100"]["disponivel"] == 13, pn
    assert [g["nome"] for g in lu["por_logistica"]] == ["Full", "Não Full"], lu["por_logistica"]
    # ROAS (01/10): faturamento ÷ ADS; geral = 5.400 ÷ 450; mínimo = faturamento ÷ lucro bruto
    assert pn["XER-NAX-100"]["roas"] == 12.86 and pn["XER-NAX-100"]["roas_min"] == 3.33, pn["XER-NAX-100"]
    assert [l["loja"] for l in pn["XER-NAX-100"]["lojas"]] == ["ESSENCE PRIME", "AURA SCENT"], pn["XER-NAX-100"]["lojas"]
    assert pn["TORINO-21"]["lojas"] == [], pn["TORINO-21"]                     # só venda reembolsada: fora
    assert pn["PARADO-1"]["roas"] == 0.0 and lu["totais"]["roas_geral"] == 12.0 and lu["totais"]["produtos_prejuizo"] == 2, lu["totais"]
    # blocos 31–60 / 61–90 / 91–120 dias atrás e a lista para promoção
    pend = w.rota_estoque(r, "GET", "estoque_vendas_blocos_pendentes", {}, b"")["blocos"]
    assert [b["bloco"] for b in pend] == ["31-60", "61-90", "91-120"] and pend[0] == {"bloco": "31-60", "inicio": "2026-08-02", "fim": "2026-08-31"}, pend
    def xl(linhas):
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Produtos", "Loja", "SKU Principal", "ID do Anúncios", "Pedidos Válidos", "Unidades Vendidas", "Valor de Vendas", "Preço Médio"])
        for l in linhas:
            ws.append(l)
        b = io.BytesIO()
        wb.save(b)
        return b.getvalue()
    w.vendas_importar(r, xl([["Naxos", "L[ML]", "XER-NAX-100", "MLB1", 3, 3, 4500, 1500]]), "Vendas_por_Produtos_20260901-20260930_x.xlsx")
    for nome, b in (("31-60", ["X", "L[ML]", "OUTRO", "MLB9", 1, 1, 10, 10]), ("61-90", ["Y", "L[ML]", "SO-61", "MLB8", 1, 1, 50, 50]),
                    ("91-120", ["X", "L[ML]", "OUTRO", "MLB9", 1, 1, 10, 10])):
        p = [x for x in pend if x["bloco"] == nome][0]
        y = w.vendas_importar(r, xl([b]), f"Vendas_por_Produtos_{p['inicio'].replace('-', '')}-{p['fim'].replace('-', '')}_x.xlsx", bloco=nome)
        assert y["bloco"] == nome, y
    assert w.rota_estoque(r, "GET", "estoque_vendas_blocos_pendentes", {}, b"")["blocos"] == []
    pr = w.rota_estoque(r, "GET", "estoque_para_promocao", {}, b"")
    it = {x["sku"]: x for x in pr["itens"]}
    assert "XER-NAX-100" not in it and it["PARADO-1"]["sem_venda_dias"] == 120 and it["PARADO-1"]["ads_sem_venda"] == 40, it
    assert it["SO-61"]["sem_venda_dias"] == 60 and it["PARADO-1"]["parado"] == 500, it
    assert pr["totais"]["31-60"]["skus"] == 2 and pr["totais"]["91-120"]["skus"] == 1, pr["totais"]
    print("ok gestor lucro e promoção (unidade)")
    return lu, pr


STUB = """window.supabase = { createClient: () => { const sess = {access_token: "TOKEN", user: {id: "u1", email: "brmilani@gmail.com"}};
  return { auth: { getSession: async () => ({data: {session: sess}}), signOut: async () => {}, updateUser: async () => ({}),
    onAuthStateChange: cb => setTimeout(() => cb("INITIAL_SESSION", sess), 0) }, storage: {from: () => ({createSignedUrls: async () => ({data: []})})} }; } };"""


def test_tela(lu, pr):
    from playwright.sync_api import sync_playwright
    aqui = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servidor_teste")
    porta = os.environ.get("PORTA_GL", "8819")
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
                pg.route("**/api/app?r=estoque_analise_lucro*", lambda rt: rt.fulfill(content_type="application/json", body=json.dumps(lu)))
                pg.route("**/api/app?r=estoque_para_promocao*", lambda rt: rt.fulfill(content_type="application/json", body=json.dumps(pr)))
                pg.goto(f"http://127.0.0.1:{porta}/#/analises-vendas/lucro")
                pg.wait_for_selector("#lu-tab tbody tr", timeout=15000)
                txt = pg.inner_text("#main")
                assert "Lucro e ADS" in txt and "Curva Z" in txt and "Full × não Full" in txt, txt[:600]
                assert "Gasto total com ADS" in txt and "ROAS geral" in txt and "12,0x" in txt and "gastou sem vender" in txt, txt[:900]
                assert pg.query_selector("#lu-tab tr.ec-urg")                       # Torino com MPA negativa / Z
                # 01/10 (Bruno): botões por situação com a quantidade; clicar mostra só esses
                pg.click(".lu-sit[data-sit='0']")
                assert "1 produto(s)" in pg.inner_text("#lu-n") and "PARADO-1" in pg.inner_text("#lu-tab"), pg.inner_text("#lu-n")
                assert "ROAS" in pg.inner_text(".lu-sits") and "gastou" in pg.inner_text(".lu-sits"), pg.inner_text(".lu-sits")
                pg.click(".lu-sit[data-sit='']")
                pg.select_option("#lu-loja", "AURA SCENT")                         # 01/10: por loja
                t = pg.inner_text("#lu-tab")
                assert "XER-NAX-100" in t and "TORINO-21" not in t and "AURA SCENT" in t, t
                pg.select_option("#lu-loja", "")
                pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"lucro_ads_{nome}.png"), full_page=True)
                pg.goto(f"http://127.0.0.1:{porta}/#/analises-vendas/promocao")
                pg.wait_for_selector("#pr-tab tbody tr", timeout=15000)
                assert "PARADO-1" in pg.inner_text("#pr-tab") and "120+ dias" in pg.inner_text("#pr-tab"), pg.inner_text("#pr-tab")[:400]
                pg.click("[data-min='120']")
                assert "SO-61" not in pg.inner_text("#pr-tab")
                pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"promocao_{nome}.png"), full_page=True)
                larg = pg.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")
                assert larg[0] <= larg[1] + 1, (nome, larg)
                assert not erros, erros
            b.close()
    finally:
        srv.terminate()
    print("ok gestor lucro e promoção (tela)")


if __name__ == "__main__":
    test_tela(*test_unidade())
