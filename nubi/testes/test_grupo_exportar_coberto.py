"""Card #79: com a tabela já carregada, a tela do grupo tem um segundo EXPORTAR "visível" (tem tamanho) depois do da
tabela, mas atrás do conteúdo da página. O .last pegava esse: o log mostrava "coberto por" 4 camadas MUI diferentes
(MuiBox, MuiPaper…), o clique pelo próprio botão baixava uma tabela vazia e a diario terminava com 3 erros. Página falsa."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402

c.CALMA = 0.2
c.enviar_foto = lambda *a, **k: None

# o EXPORTAR da tabela baixa "grupo.xlsx"; o outro (depois no DOM, embaixo do conteúdo, z-index menor) baixa "vazio.xlsx"
LINHAS = "".join(f'<tr><td>VENDEDOR {i} <a aria-label="Analise um concorrente" href="#">🔍</a></td></tr>' for i in range(16))
PAGINA = f"""<html><body style="margin:0"><div class="MuiBox-root" style="position:relative">
  <div class="MuiBox-root css-5vb4lz" style="position:relative;z-index:1;background:#fff;min-height:600px">
    <div class="MuiPaper-root MuiPaper-elevation1" style="padding:40px"><button id="exp">EXPORTAR</button>
      <table><tbody>{LINHAS}</tbody></table></div></div>
  <div class="MuiBox-root css-1fijj2c" style="position:absolute;top:0;left:0"><button id="outro">EXPORTAR</button></div>
  </div>
  <script>for (const [id, nome] of [['exp', 'grupo.xlsx'], ['outro', 'vazio.xlsx']])
    document.getElementById(id).onclick = () => {{ const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob(['x'])); a.download = nome; document.body.appendChild(a); a.click(); }};
  </script></body></html>"""


def _pagina(p):
    exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    nav = p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)
    pg = nav.new_page(accept_downloads=True)
    pg.set_content(PAGINA)
    return nav, pg


def test_codigo_antigo_clica_o_coberto_e_baixa_vazio():
    from playwright.sync_api import sync_playwright
    c.LOG.clear()
    with sync_playwright() as p:
        nav, pg = _pagina(p)
        botoes = c.botao_exportar(pg)
        assert botoes.count() == 2 and botoes.last.get_attribute("id") == "outro"   # os dois contam como visíveis
        with pg.expect_download(timeout=60000) as d:
            c.clicar_exportar(pg, botoes.last, "2026-09-22")                      # como era: o .last
        assert d.value.suggested_filename == "vazio.xlsx"
        nav.close()
    assert "EXPORTAR estava coberto por DIV MuiBox-root css-5vb4lz" in "\n".join(c.LOG)


def test_baixar_grupo_exporta_o_da_tabela():
    from playwright.sync_api import sync_playwright
    c.periodo_na_tela = lambda pg: ((22, 9), (22, 9))
    c.ir = lambda pg, url, esperar: pg.set_content(PAGINA)
    c.LOG.clear()
    with sync_playwright() as p:
        nav, _ = _pagina(p)
        pg = nav.contexts[0].pages[0]
        arq = c.baixar_grupo(pg, {"grupo": "1"}, "2026-09-22", Path(tempfile.mkdtemp()))
        nav.close()
    assert arq.name == "grupo.xlsx"
    assert "coberto" not in "\n".join(c.LOG)


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
