"""Card #138 (01/10, Maquiagem): a diario terminava com erros no relatório MARCAS, ora um mês, ora outro, por dois motivos
do coletor.log: (1) "Categoria na tela: '    '": a página abriu antes do menu de categorias carregar (botões sem texto,
itens com data-name=""), o coletor tentava escolher a categoria e o clique no item escondido esperava 15 s (TimeoutError);
(2) "Download.save_as: Target page, context or browser has been closed": o Chrome fechou no download (como o card #101
nos vendedores) e o mês contava erro sem tentar com outro Chrome. Nubimetrics falso (nada de site real)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402

c.CALMA = 0.05
c.enviar_foto = lambda *a, **k: None
CAT, NOMES = "MLB1246-MLB1248", ["Beleza e Cuidado Pessoal", "Maquiagem"]

# o menu de categorias já vem do endereço, mas o texto dos botões só aparece depois de 2 s; os itens ficam escondidos
PAGINA = """<html><body>
  <button class="calendar-btn">Fevereiro 2026</button>
  <div class="dropdown-category"><button class="dropdown-toggle"> </button>
    <ul style="display:none"><li><a data-id="MLB1246" data-parent="MLB" data-name="" href="#"></a></li></ul></div>
  <div class="dropdown-category"><button class="dropdown-toggle"> </button>
    <ul style="display:none"><li><a data-id="MLB1248" data-parent="MLB1246" data-name="" href="#"></a></li></ul></div>
  <button id="simple-tab-3" aria-selected="false">MARCAS</button>
  <table><tbody><tr><td>MARCA</td></tr></tbody></table>
  <button id="exp">EXPORTAR</button>
  <script>
    setTimeout(() => { const b = document.querySelectorAll('.dropdown-toggle');
      b[0].innerText = 'Beleza e Cuidado Pessoal'; b[1].innerText = 'Maquiagem'; }, 2000);
    document.getElementById('simple-tab-3').onclick = () =>
      fetch('/api/ranking/tree?Topic=brands&Date=2026-02-01&CategoryPath=MLB1246-MLB1248&Limit=10');
    document.getElementById('exp').onclick = () => { const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob(['PK'])); a.download = 'MARCAS-2026-02-01.xlsx';
      document.body.appendChild(a); a.click(); };
  </script></body></html>"""


def _rodar(p, cai=0):
    """cai: quantos Chromes seguidos fecham no download. Devolve (resultado ou erro, Chromes abertos)."""
    exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    nav = p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)
    abertos = []

    def abrir(p_, cfg):
        ctx = nav.new_context(accept_downloads=True)
        ctx.route("http://nubimetrics.teste/**", lambda r: r.fulfill(
            body="{}" if "ranking/tree" in r.request.url else PAGINA, content_type="text/html"))
        abertos.append(ctx)
        return ctx

    def devagar(seg=2.0):
        if seg == 3 and len(abertos) <= cai:           # o Chrome cai na hora de exportar
            abertos[-1].close()

    antes = {k: getattr(c, k) for k in ("abrir_navegador", "ir", "guardar_sessao", "devagar")}
    c.abrir_navegador, c.guardar_sessao, c.devagar = abrir, lambda ctx: None, devagar
    c.ir = lambda pg, url, esperar: pg.goto("http://nubimetrics.teste/market/sellerranking")
    c.LOG.clear()
    try:
        r = c.coletar_marcas(None, {"categoria": "MLB1246-MLB6284"}, "tok", "2026-02", enviar=False,
                             categoria=CAT, nomes=NOMES)
    except Exception as e:  # noqa: BLE001
        r = e
    finally:
        for k, v in antes.items():
            setattr(c, k, v)
        nav.close()
    return r, len(abertos)


def test_espera_o_menu_de_categorias_carregar():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        r, _ = _rodar(p)
    assert r == (1, 0, 0), r
    assert "escolhendo" not in "\n".join(c.LOG), c.LOG          # não mexeu na categoria que já estava certa


def test_chrome_fecha_no_download_abre_de_novo():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        r, chromes = _rodar(p, cai=2)
    assert r == (1, 0, 0), r
    assert chromes == 3
    assert "o navegador fechou" in "\n".join(c.LOG)


def test_chrome_que_nunca_fica_de_pe_ainda_da_erro():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        r, chromes = _rodar(p, cai=99)
    assert isinstance(r, Exception) and "has been closed" in str(r), r
    assert chromes == 3


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
