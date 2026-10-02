"""02/10 (Bruno: "Explorador, pesquisa expandida, digitando a marca AL WATANIAH"): o coletor busca a marca pela busca do
topo, escolhe a pesquisa expandida, lê o período da tela, exporta e manda ao nubi com marca/início/fim. Páginas falsas."""
import http.server
import os
import sys
import tempfile
import threading
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402

c.CALMA = 0.1
c.devagar = lambda *a, **k: None
c.enviar_foto = lambda *a, **k: None

TOPO = """<html><body><input placeholder="Buscar por Anúncios" id="b">
<script>document.getElementById('b').onkeydown = e => { if (e.key === 'Enter') location.href = '/explorer?q=' + encodeURIComponent(e.target.value); };</script>
</body></html>"""
EXPLORADOR = """<html><body><h1>Explorador de anúncios</h1><input placeholder="Buscar anúncios, codinome do vendedor, marcas e muito mais"><p><b>Anúncios com vendas:</b> 01 set - 30 set 2026</p>
<label><input type="radio" name="t" checked> Pesquisa exata</label>
<label><input type="radio" name="t" id="exp"> Pesquisa expandida por IA</label>
<p id="n">1–50 de 23496 resultados</p>
<div style="display:flex;justify-content:space-between;width:900px"><button id="f" style="width:24px;height:24px">⫶</button>
<span id="selo"></span><button id="x">EXPORTAR</button></div>
<div id="painel" style="display:none"><p>Categoria</p><ul><li id="bel">Beleza e Cuidado Pessoal (4497)</li><li>Casa (10)</li></ul></div>
<script>let filtrado = false;
document.getElementById('f').onclick = () => document.getElementById('painel').style.display = 'block';
document.getElementById('bel').onclick = () => { filtrado = true; document.getElementById('n').innerText = '1–50 de 4497 resultados';
  document.getElementById('selo').innerText = 'Beleza e Cuidado Pessoal'; document.getElementById('painel').style.display = 'none'; };
document.getElementById('x').onclick = () => { if (!document.getElementById('exp').checked || !filtrado) return;
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob(['Titulo;Marca\\n' + 'x;AL WATANIAH\\n'.repeat(40)]));
  a.download = 'Explorador.csv'; document.body.appendChild(a); a.click(); };</script></body></html>"""


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        corpo = (EXPLORADOR if self.path.startswith(("/explorer", "/market/publicationsexplorer")) else TOPO).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *a):
        pass


def test_periodo_da_tela():
    assert c.periodo_do_explorador("Anúncios com vendas: 01 set - 30 set 2026") == ("2026-09-01", "2026-09-30")
    assert c.periodo_do_explorador("Anúncios com vendas: 16 dez - 15 jan 2027") == ("2026-12-16", "2027-01-15")
    assert c.periodo_do_explorador("nada") is None


def test_comando_da_central():
    assert c.comando_mac("explorador_marca", "AL WATANIAH")[-1] == "AL WATANIAH"
    assert c.comando_mac("explorador_marca", "ARMAF|exata")[-2:] == ["ARMAF", "--exata"]
    assert c.comando_mac("explorador_marca", "x; rm -rf /") is None


def test_exporta_e_manda_com_o_periodo():
    from playwright.sync_api import sync_playwright
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    c.BASE = f"http://127.0.0.1:{srv.server_address[1]}"
    enviados = []
    c.api = lambda token, rota, params=None, corpo=None, **k: enviados.append((rota, params, len(corpo or b""))) or {"log": ["ok"]}
    c.guardar_sessao = lambda ctx: None
    c.salvar_config = lambda cfg: None
    exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    with sync_playwright() as p:
        nav = p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)
        c.abrir_navegador = lambda p_, cfg, **k: nav.new_context(accept_downloads=True)
        cfg = {}
        r = c.coletar_explorador_marca(p, cfg, "T", "al wataniah")
        nav.close()
    srv.shutdown()
    assert r[:3] == (1, 1, 0), r
    rota, params, n = enviados[0]
    assert rota == "importar" and params == {"arquivo": "AL_WATANIAH__2026-09-01_2026-09-30.csv", "marca": "AL WATANIAH",
                                             "inicio": "2026-09-01", "fim": "2026-09-30"} and n > 200, enviados
    assert cfg["explorador_url"].endswith("/market/publicationsexplorer")
    assert "filtro Beleza e Cuidado Pessoal: 23496 -> 4497" in "\n".join(c.LOG)


def test_sem_filtro_mais_de_10_mil_nao_importa():
    from playwright.sync_api import sync_playwright
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    c.BASE = f"http://127.0.0.1:{srv.server_address[1]}"
    exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    with sync_playwright() as p:
        nav = p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)
        c.abrir_navegador = lambda p_, cfg, **k: nav.new_context(accept_downloads=True)
        try:
            c.coletar_explorador_marca(p, {}, "T", "AL WATANIAH", categoria=None)
            assert False, "devia recusar"
        except c.Falha as e:
            assert "23496 resultados" in str(e)
        nav.close()
    srv.shutdown()


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
