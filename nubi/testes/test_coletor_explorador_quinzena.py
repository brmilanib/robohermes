"""Card #125: `coletor explorador-quinzena` — Explorador de anúncios de cada marca no período da quinzena, EXPORTAR e envio
ao nubi (importar com marca/início/fim). Nubimetrics falso num servidor local; nubi falso no lugar de api(). Sem sites."""
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402

c.CALMA = 0.05
c.EXPLORADOR_PAUSA = 0
c.enviar_foto = lambda *a, **k: None

MENU = """<html><body><nav><a href="/market/explorer">Explorador de anúncios</a></nav><main>Ranking</main></body></html>"""
# busca, período no calendário (APLICAR), tabela e EXPORTAR que abre o menu de formato; "SEMNADA" não tem anúncio
EXPLORADOR = r"""<html><body><main>
  <input id="q" placeholder="Buscar anúncios" type="text">
  <button id="per">01 SET - 27 SET</button>
  <div id="cal" style="display:none"><input id="d1" value="01/09/2026"><input id="d2" value="27/09/2026">
    <button id="ap">APLICAR</button></div>
  <div id="res"></div>
  <button id="exp">EXPORTAR</button><ul id="fmt" style="display:none"><li id="csv">CSV</li><li>XLSX</li></ul>
<script>
  const M = ['JAN','FEV','MAR','ABR','MAI','JUN','JUL','AGO','SET','OUT','NOV','DEZ'];
  const rot = v => v.slice(0, 2) + ' ' + M[+v.slice(3, 5) - 1];
  let marca = '';
  q.onkeydown = e => { if (e.key === 'Enter') { marca = q.value; desenhar(); } };
  per.onclick = () => cal.style.display = 'block';
  ap.onclick = () => { per.innerText = rot(d1.value) + ' - ' + rot(d2.value); cal.style.display = 'none'; desenhar(); };
  function desenhar() {
    res.innerHTML = marca.toUpperCase() === 'SEMNADA' ? '<p>Nenhum resultado encontrado</p>'
      : `<table><tbody><tr><td>${marca} Perfume</td><td>${per.innerText}</td></tr></tbody></table>`;
  }
  exp.onclick = () => fmt.style.display = 'block';
  csv.onclick = () => { const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([`Titulo;Marca;Periodo\n${marca} Perfume;${marca};${per.innerText}\n`]));
    a.download = 'Explorador.csv'; document.body.appendChild(a); a.click(); };
</script></main></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        html = EXPLORADOR if self.path.startswith("/market/explorer") else MENU
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())


def _servidor():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _navegador(p):
    exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    nav = p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)
    ctx = nav.new_context(accept_downloads=True)
    ctx.new_page()
    fechar = ctx.close
    ctx.close = lambda: (fechar(), nav.close())
    return ctx


def _marca(m, ini="2026-09-01", fim="2026-09-15"):
    return {"marca": m, "busca": m.title(), "arquivo": f"{m.replace(' ', '_')}__{ini}_{fim}.csv"}


def test_comando_da_central_e_do_terminal():
    assert c.comando_mac("explorador_quinzena")[-1] == "explorador-quinzena"


def test_exporta_as_marcas_manda_ao_nubi_e_segue_depois_da_falha():
    from playwright.sync_api import sync_playwright
    srv = _servidor()
    c.BASE = f"http://127.0.0.1:{srv.server_port}"
    c.FEITO_EXPLORADOR.clear()
    c.abrir_navegador = lambda p, cfg: _navegador(p)
    c.guardar_sessao = lambda ctx: None
    lotes = [[_marca("LATTAFA"), _marca("SEMNADA"), _marca("AL WATANIAH")], [_marca("SEMNADA")]]
    enviados, perguntas = [], []

    def api(token, rota, params=None, corpo=None, **k):
        if rota == "explorador_quinzena_pendente":
            perguntas.append(1)
            marcas = lotes.pop(0) if lotes else []
            return {"rodar": bool(marcas), "inicio": "2026-09-01", "fim": "2026-09-15", "total": 3, "feitas": 0, "marcas": marcas}
        if rota == "importar":
            enviados.append((params, corpo.decode()))
            return {"log": ["ok"]}
        return {}
    c.api = api
    try:
        with sync_playwright() as p:
            arquivos, importados, erros, msg = c.coletar_explorador_quinzena(p, {}, "T")
    finally:
        srv.shutdown()
    # lote 2 só tinha a que já falhou: para (não fica em laço)
    assert len(perguntas) == 2
    assert (arquivos, importados, erros) == (3, 2, 1), msg
    assert [e[0]["arquivo"] for e in enviados] == ["LATTAFA__2026-09-01_2026-09-15.csv",
                                                   "AL_WATANIAH__2026-09-01_2026-09-15.csv"]
    assert enviados[1][0] == {"arquivo": "AL_WATANIAH__2026-09-01_2026-09-15.csv", "marca": "AL WATANIAH",
                              "inicio": "2026-09-01", "fim": "2026-09-15"}
    # o CSV é o da busca certa, no período certo (calendário mudado para 01 SET - 15 SET)
    assert "Al Wataniah Perfume;Al Wataniah;01 SET - 15 SET" in enviados[1][1]
    assert "falharam 1: SEMNADA: sem anúncios no período" in msg and "2 de 3" in msg
    assert (c.PASTA / "arquivos" / "explorador" / "2026-09-01_2026-09-15" / "LATTAFA__2026-09-01_2026-09-15.csv").exists()


def test_nada_pendente():
    c.api = lambda *a, **k: {"rodar": False, "inicio": "2026-09-16", "fim": "2026-09-30", "motivo": "fora dos dias (2 e 17)"}
    assert c.coletar_explorador_quinzena(None, {}, "T") == (0, 0, 0, "Explorador por quinzena: nada pendente")


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
