# -*- coding: utf-8 -*-
"""Card #124 (29/09, pedido do Bruno): o coletor baixa o 'Relatório de Vendas' do Gestor Seller (últimos 30 dias, todas as contas)
numa página FALSA do Gestor, sem clicar em salvar/importar/excluir; a rota gestor_vendas_importar lê uma planilha falsa com nomes de
colunas diferentes e o estoque.por_anuncio mostra a margem real do Gestor quando o SKU casa."""
import http.server
import io
import json
import os
import sys
import tempfile
import threading
from datetime import date, timedelta
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "public" / "coletor"))
import estoque  # noqa: E402


def _xlsx(cab, linhas, titulo=None):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    if titulo:
        ws.append([titulo])
    ws.append(cab)
    for x in linhas:
        ws.append(x)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


CAB = ["Nº do Pedido", "Conta", "Marketplace", "Título do produto", "SKU", "Qtde", "Valor total", "Custo do produto",
       "Imposto", "Comissão", "Custo de frete", "Lucro", "Margem (%)"]
LINHAS = [("P1", "PUREHOME", "Mercado Livre", "Perfume A", "a-100", 2, 400, 200, 20, 48, 30, 102, "25,5%"),
          ("P2", "AURASCENT", "Shopee", "Perfume A", "A-100", 1, 200, 100, 10, 30, 12, 48, "24%"),
          ("P3", "PUREHOME", "Mercado Livre", "Perfume B", "B-100", 1, 100, 70, 5, 16, 20, -11, "-11%"),
          ("", "", "", "Total", "Total", 4, 700, 370, 35, 94, 62, 139, "")]
PLANILHA = _xlsx(CAB, LINHAS, "Relatório de vendas — 30/08/2026 a 28/09/2026")


# ---- página falsa do Gestor Seller ----------------------------------------------------------------------------------------
CLIQUES = []
PAGINAS = {
    "/management/products": """<html><head><meta charset="utf-8"></head><body>
      <nav><a href="#" onclick="document.getElementById('rel').style.display='block'">Relatórios</a>
      <div id="rel" style="display:none"><a href="/reports/sales">Relatório de Vendas</a></div></nav>
      <button onclick="fetch('/clique?salvar')">Importar por planilha</button></body></html>""",
    "/reports/sales": """<html><head><meta charset="utf-8"></head><body><h1>Relatório de Vendas</h1>
      <label>Data início <input type="date" id="ini"></label><label>Data fim <input type="date" id="fim"></label>
      <label><input type="checkbox" class="conta" value="PUREHOME"> PUREHOME · Mercado Livre</label>
      <label><input type="checkbox" class="conta" value="AURASCENT" checked> AURASCENT · Shopee</label>
      <button onclick="fetch('/clique?salvar')">Salvar</button><button onclick="fetch('/clique?excluir')">Excluir</button>
      <button id="baixar" onclick="const c=[...document.querySelectorAll('.conta:checked')].map(x=>x.value).join(',');
        location.href='/baixar?ini='+document.getElementById('ini').value+'&fim='+document.getElementById('fim').value+'&contas='+c">
        Baixar relatório de vendas</button></body></html>""",
}


class Pagina(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        caminho, _, q = self.path.partition("?")
        if caminho == "/clique":
            CLIQUES.append(q)
        if caminho == "/baixar":
            CLIQUES.append("baixar?" + q)
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", 'attachment; filename="relatorio_de_vendas.xlsx"')
            self.end_headers()
            self.wfile.write(PLANILHA)
            return
        corpo = PAGINAS.get(caminho, "<html><body>ok</body></html>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Pagina)
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["GESTOR_URL"] = f"http://127.0.0.1:{srv.server_port}"
import coletor as c  # noqa: E402

c.CALMA = 0.2
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def test_baixa_o_relatorio_so_lendo():
    from playwright.sync_api import sync_playwright
    cfg = {}
    c.salvar_config = lambda cfg: None
    with sync_playwright() as p:
        extra = {"executable_path": CHROME} if Path(CHROME).exists() else {}
        if os.environ.get("NUBI_CHROMIUM"):
            extra = {"executable_path": os.environ["NUBI_CHROMIUM"]}
        ctx = p.chromium.launch_persistent_context(str(c.PASTA / "perfil"), headless=True, accept_downloads=True, **extra)
        try:
            arq, ini, fim = c.baixar_gestor_vendas(ctx.pages[0] if ctx.pages else ctx.new_page(), cfg, p)
        finally:
            ctx.close()
    assert arq.name == "relatorio_de_vendas.xlsx" and arq.read_bytes() == PLANILHA            # nome do Gestor, sem renomear
    assert fim == date.today() - timedelta(days=1) and (fim - ini).days == 29                  # últimos 30 dias
    baixou = [x for x in CLIQUES if x.startswith("baixar?")]
    assert baixou == [f"baixar?ini={ini.isoformat()}&fim={fim.isoformat()}&contas=PUREHOME,AURASCENT"], CLIQUES   # todas as contas
    assert not [x for x in CLIQUES if not x.startswith("baixar?")], CLIQUES                    # nunca salvar/importar/excluir
    assert cfg["gestor_vendas_url"].endswith("/reports/sales")                                  # da próxima vez vai direto


def test_falha_do_gestor_nao_derruba_o_estoque():
    class Ctx:
        pages = []
        def new_page(self): return object()
        def close(self): pass
    antes = (c.abrir_navegador, c.baixar_estoque, c.baixar_vendas, c.baixar_gestor_vendas, c.guardar_sessao, c.enviar_foto, c.api)
    arq = c.PASTA / "estoque.xlsx"
    arq.write_bytes(b"PK x")
    enviados = []
    c.abrir_navegador = lambda p, cfg, visivel=None: Ctx()
    c.baixar_estoque = lambda pg, p=None: (arq, None)
    c.baixar_vendas = lambda pg, cfg, p=None: (_ for _ in ()).throw(c.Falha("sem vendas"))
    def gestor(pg, cfg, p=None):
        raise c.Falha("não achei 'Relatório de Vendas'")
    c.baixar_gestor_vendas = gestor
    c.guardar_sessao = c.enviar_foto = lambda *a, **k: None
    c.api = lambda token, rota, q=None, corpo=None, **k: enviados.append(rota) or {"log": ["OK: estoque", "640 SKUs"]}
    try:
        r = c.coletar_estoque(None, {}, "T")
        # 01/10: depois do estoque, o coletor pergunta quais dias do Vendas por Anúncio faltam (aqui nenhum)
        assert enviados == ["estoque_importar", "estoque_vendas_dias_pendentes", "estoque_vendas_blocos_pendentes"] and r[1] == 1, (enviados, r)
        assert "vendas do Gestor: não baixou" in r[3], r
        g = c.PASTA / "gestor_vendas.xlsx"
        g.write_bytes(PLANILHA)
        c.baixar_gestor_vendas = lambda pg, cfg, p=None: (g, date(2026, 8, 30), date(2026, 9, 28))
        enviados.clear()
        c.coletar_estoque(None, {}, "T")
        assert enviados == ["estoque_importar", "gestor_vendas_importar", "estoque_vendas_dias_pendentes",
                            "estoque_vendas_blocos_pendentes"], enviados
    finally:
        (c.abrir_navegador, c.baixar_estoque, c.baixar_vendas, c.baixar_gestor_vendas, c.guardar_sessao, c.enviar_foto, c.api) = antes


def test_le_a_planilha_com_nomes_diferentes():
    ls = estoque.ler_gestor_vendas(PLANILHA)
    assert len(ls) == 3 and ls[0]["sku"] == "a-100" and ls[0]["conta"] == "PUREHOME" and ls[0]["pedido"] == "P1"
    assert ls[0]["valor"] == 400 and ls[0]["custo"] == 200 and ls[0]["imposto"] == 20 and ls[0]["taxa"] == 48
    assert ls[0]["frete"] == 30 and ls[0]["lucro"] == 102 and ls[0]["margem"] == 25.5 and ls[0]["unidades"] == 2
    try:
        estoque.ler_gestor_vendas(_xlsx(["Produto", "Estoque"], [("x", 1)]))
        raise AssertionError("leu planilha errada")
    except estoque.ErroEstoque as e:
        assert "Gestor" in str(e)


def test_rota_importar_guarda_linhas_e_totais():
    import nubi_web
    gravado = []

    class Repo:
        def _eq(self, v): return "eq." + str(v)

        def _req(self, metodo, tabela, params=None, corpo=None, **k):
            if metodo == "POST":
                gravado.extend(corpo)
            return [{"texto": gravado[0]["texto"]}] if metodo == "GET" and gravado else []
    r = nubi_web.rota_estoque(Repo(), "POST", "gestor_vendas_importar",
                              {"arquivo": "relatorio_de_vendas.xlsx", "inicio": "2026-08-30", "fim": "2026-09-28"}, PLANILHA)
    assert r["ok"] and "3 linhas" in r["log"][0], r
    ch = [x["chave"] for x in gravado]
    assert ch[0] == "gestor_vendas|atual" and ch[1].startswith("gestor_vendas|20") and len(ch[1]) == len("gestor_vendas|2026-09-29")
    d, tot = json.loads(gravado[0]["texto"]), json.loads(gravado[1]["texto"])
    assert len(d["linhas"]) == 3 and "linhas" not in tot and tot["dias"] == 30 and tot["skus"] == 2 and tot["pedidos"] == 3
    assert tot["lucro"] == 139 and tot["valor"] == 700 and tot["margem_pct"] == 19.9, tot
    assert nubi_web.rota_estoque(Repo(), "POST", "gestor_vendas_importar", {}, PLANILHA)["repetido"]


def test_por_anuncio_usa_a_margem_real_do_gestor():
    vendas = [{"sku": "A-100", "anuncio": "MLB1", "loja": "PUREHOME[Mercado Libre BR]", "pedidos": 3, "unidades": 3, "valor": 600, "preco_medio": 200},
              {"sku": "C-100", "anuncio": "MLB3", "loja": "PUREHOME[Mercado Libre BR]", "pedidos": 1, "unidades": 1, "valor": 100, "preco_medio": 100}]
    est = [{"sku": "A-100", "custo_medio": 100, "disponivel": 5}, {"sku": "C-100", "custo_medio": 50, "disponivel": 1}]
    a = {x["anuncio"]: x for x in estoque.listas(est, vendas, gestor=estoque.ler_gestor_vendas(PLANILHA))["anuncios"]}
    assert a["MLB1"]["margem_pct"] == 50.0 and a["MLB1"]["margem_real_pct"] == 25.0 and a["MLB1"]["lucro_un"] == 50.0
    assert a["MLB3"]["margem_real_pct"] is None and a["MLB3"]["lucro_un"] is None               # SKU fora do Gestor
    assert "margem_real_pct" in estoque.por_anuncio(est, vendas)[0]                              # sem Gestor: None


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
