"""Conferência do custo no Gestor Seller (25/09): a lista de Produtos internos é feita de blocos (div), não de tabela, e a
busca pode não achar pelo SKU. Página falsa igual à do print do Bruno: ARMAF-MEGA-200, custo 48.00."""
import http.server
import os
import sys
import tempfile
import threading
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()

PAGINA = """<html><head><meta charset="utf-8"></head><body>
<input placeholder="Pesquisar" id="q"><div id="lista"></div>
<script>
const P = [["ARMAF-MEGA-200", "Body Spray Odyssey Mega Armaf 200 ml", "48.00", "0.00"],
           ["LATTAFA-ASAD-100", "Perfume Asad Lattafa 100 ml", "95.50", "0.00"]];
function mostra(s) {   // como no Gestor: a busca procura só no TÍTULO
  document.getElementById('lista').innerHTML = P.filter(p => !s || p[1].toLowerCase().includes(s.toLowerCase()))
    .map(p => `<div class="row"><div class="c">${p[0]}</div><div class="c"><img></div><div class="c">${p[1]}</div>
               <div class="c">${p[2]}</div><div class="c">${p[3]}</div></div>`).join('');
}
const u = new URLSearchParams(location.search).get('search') || ''; document.getElementById('q').value = u; mostra(u);
document.getElementById('q').addEventListener('keydown', e => { if (e.key === 'Enter') mostra(e.target.value); });
</script></body></html>"""


class Pagina(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGINA.encode())

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), Pagina)
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["GESTOR_URL"] = f"http://127.0.0.1:{srv.server_port}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402

_dorme = c.time.sleep


def _abrir(p):
    exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    b = p.chromium.launch(**({"executable_path": exe} if os.path.exists(exe) else {}))
    pg = b.new_page()
    pg.goto(f"{os.environ['GESTOR_URL']}/management/products")
    return b, pg


def test_confere_custo_na_lista_de_blocos():
    c.time.sleep = lambda s: _dorme(min(s, 0.3))
    c.api = lambda *a, **k: {"existe": True}
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b, pg = _abrir(p)
        amostra = [{"sku": "ARMAF-MEGA-200", "custo": 48.0, "titulo": "Body Spray Odyssey Mega Armaf 200 ml"},
                   {"sku": "LATTAFA-ASAD-100", "custo": 95.5, "titulo": "Perfume Asad Lattafa 100 ml"}]
        assert c.conferir_gestor(pg, amostra, "T") == "custo conferido no Gestor: ARMAF-MEGA-200 48.00, LATTAFA-ASAD-100 95.50"
        try:
            c.conferir_gestor(pg, [{"sku": "ARMAF-MEGA-200", "custo": 50.0, "titulo": "Body Spray Odyssey Mega Armaf 200 ml"}], "T")
            assert False, "custo errado tinha que falhar"
        except c.Falha as e:
            assert "não bateu" in str(e) and "48.00" in str(e)   # achou o produto e mostra o custo que está lá
        b.close()


def test_linha_do_sku_ignora_escondido_e_sku_parecido():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b, pg = _abrir(p)
        pg.set_content("""<div><div style="display:none">X-1</div><div>9.99</div></div>
                          <div><div>X-10</div><div>1.00</div></div>""")
        assert c._linha_do_sku(pg, "X-1") == ""           # escondido não conta; X-10 não é X-1
        b.close()


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
