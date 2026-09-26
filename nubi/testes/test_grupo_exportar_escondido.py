"""Card #75: a tela do grupo tem um segundo EXPORTAR escondido depois do visível; o .last pegava o escondido, o clique
não chegava (log "coberto por DIV MuiBox…") e o clique pelo próprio botão baixava uma tabela vazia. Página falsa."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402

c.CALMA = 0.2
c.enviar_foto = lambda *a, **k: None

# EXPORTAR da tabela (visível) baixa "grupo.xlsx"; o de um menu fechado (escondido, depois no DOM) baixa "vazio.xlsx"
PAGINA = """<html><body style="margin:0">
  <div class="MuiBox-root" style="padding:40px"><button id="exp">EXPORTAR</button>
    <div class="MuiPaper-root" style="height:300px">tabela</div></div>
  <div class="MuiPopover-root" style="position:fixed;top:120px;left:40px;visibility:hidden"><button id="outro">EXPORTAR</button></div>
  <script>for (const [id, nome] of [['exp', 'grupo.xlsx'], ['outro', 'vazio.xlsx']])
    document.getElementById(id).onclick = () => { const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob(['x'])); a.download = nome; document.body.appendChild(a); a.click(); };
  </script></body></html>"""


def _pagina(p):
    exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    nav = p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)
    pg = nav.new_page(accept_downloads=True)
    pg.set_content(PAGINA)
    return nav, pg


def test_codigo_antigo_baixa_a_tabela_vazia():
    from playwright.sync_api import sync_playwright
    c.LOG.clear()
    with sync_playwright() as p:
        nav, pg = _pagina(p)
        antigo = pg.locator("button, [role=button]", has_text=c.re.compile(r"^\s*EXPORTAR\s*$", c.re.I)).last
        assert not antigo.is_visible()                  # como era: o .last é o escondido
        with pg.expect_download(timeout=60000) as d:
            antigo.evaluate("b => b.click()")           # o clique "pelo próprio botão" do card #74
        assert d.value.suggested_filename == "vazio.xlsx"
        nav.close()


def test_exporta_o_botao_visivel():
    from playwright.sync_api import sync_playwright
    c.LOG.clear()
    with sync_playwright() as p:
        nav, pg = _pagina(p)
        botao = c.botao_exportar(pg)
        assert botao.count() == 1
        with pg.expect_download(timeout=30000) as d:
            c.clicar_exportar(pg, botao.last, "2026-09-22")
        assert d.value.suggested_filename == "grupo.xlsx"
        nav.close()
    assert "coberto" not in "\n".join(c.LOG)


def test_nao_clica_pelo_botao_escondido():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        nav, pg = _pagina(p)
        try:
            c.clicar_exportar(pg, pg.locator("#outro"), "2026-09-22")
            assert False, "devia recusar o botão escondido"
        except c.Falha as ex:
            assert "não está visível" in str(ex)
        nav.close()


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
