"""Card #143: em 02/10 a coleta do mês fechado de setembro dos vendedores parou com "o calendário não mostrou os campos
de data" (6 erros seguidos). Setembro era o mês anterior e ia no endereço como range=PREVMONTH; o Nubimetrics ainda
chamava de "MÊS ANTERIOR" o mês de agosto (01 AGO - 31 AGO, os dados atrasam 2 dias), ignorava o from/to e o
calendário dele só mostrava os atalhos. Página falsa no mesmo endereço do Nubimetrics; roda sem sites."""
import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import coletor as c  # noqa: E402

c.CALMA = 0.2
c.enviar_foto = lambda *a, **k: None

MES = {"08": "AGO", "09": "SET"}

# análise do vendedor como a do Nubimetrics: PREVMONTH = agosto (ignora o from/to); CUSTOM = o período do endereço.
# O botão do período abre só os atalhos (sem campos de data), como na tela de 02/10.
PAGINA = """<html><head><title>Nubimetrics</title></head><body>
  <input placeholder="Buscar por Anúncios"><input value="VENDEDOR TESTE">
  <button>%(rotulo)s</button><button>%(ini)s - %(fim)s</button>
  <ul id="atalhos" style="display:none"><li>MÊS ANTERIOR</li><li>ÚLTIMOS 30 DIAS</li></ul>
  <button id="tab-1">ANÚNCIOS</button><button id="dashboardByCompetitor_exportBtn_table">EXPORTAR</button>
  <table><tbody id="corpo"></tbody></table>
  <script>
  document.querySelectorAll('button')[1].onclick = () => { document.getElementById('atalhos').style.display = 'block'; };
  fetch('/api/analysisitems?from=%(de)s&to=%(ate)s').then(r => r.json()).then(j => {
    document.getElementById('corpo').innerHTML = j.items.map(i => `<tr><td>${i}</td></tr>`).join(''); });
  document.getElementById('dashboardByCompetitor_exportBtn_table').onclick = () => {
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob(['x'.repeat(5000)]));
    a.download = 'VENDEDOR TESTE.xlsx'; document.body.appendChild(a); a.click(); };
  </script></body></html>"""


def _servir(route):
    u = urlparse(route.request.url)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    if "analysisitems" in u.path:
        return route.fulfill(content_type="application/json", body='{"items": ["Perfume A", "Perfume B"]}')
    de, ate = ("2026-08-01", "2026-08-31") if q.get("range") == "PREVMONTH" else (q["from"], q["to"])
    rotulo = "MÊS ANTERIOR" if q.get("range") == "PREVMONTH" else "PERSONALIZADO"
    html = PAGINA % {"rotulo": rotulo, "de": de, "ate": ate, "ini": f"{de[8:10]} {MES[de[5:7]]}",
                     "fim": f"{ate[8:10]} {MES[ate[5:7]]}"}
    route.fulfill(content_type="text/html", body=html)


def _baixar(rng):
    from playwright.sync_api import sync_playwright
    exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    with sync_playwright() as p:
        nav = p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)
        pg = nav.new_page(accept_downloads=True)
        pg.route("https://app.nubimetrics.com/**", _servir)
        try:
            return c.baixar_vendedor(pg, "HASH", "2026-09-01", "2026-09-30", rng, Path(tempfile.mkdtemp()),
                                     "VENDEDOR TESTE")
        finally:
            nav.close()


def test_setembro_fechado_em_02_10_vai_com_as_datas():
    per = c.periodos({"desde": "2026-09", "atraso_dias": 2}, hoje=date(2026, 10, 2))
    assert per == [{"mes": "2026-09", "ini": "2026-09-01", "fim": "2026-09-30", "ate": None, "rng": "CUSTOM"}], per


def test_prevmonth_reproduz_o_erro_do_card():
    try:
        _baixar("PREVMONTH")
        assert False, "devia falhar como no Mac"
    except c.Falha as e:
        assert "calendário não mostrou os campos de data" in str(e), e


def test_custom_baixa_setembro():
    per = c.periodo_fechado("2026-09", hoje=date(2026, 10, 2))
    arq = _baixar(per["rng"])
    assert arq.name == "VENDEDOR TESTE.xlsx" and arq.stat().st_size >= 3000


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
