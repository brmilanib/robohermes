"""Card #114: um aviso do UpSeller (modal ant-design) abria por cima da Lista de Estoque e o clique na aba My Warehouse
esperava 30 s ("<div class="ant-modal-body"> intercepts pointer events") e a tarefa estoque falhava. Página falsa."""
import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402

c.CALMA = 0.2
c.enviar_foto = lambda *a, **k: None

LISTA = """<div style="padding:20px"><span class="tit" onclick="document.body.dataset.aba='ok'">My Warehouse</span> 12
  <button id="ie">Importar &amp; Exportar</button></div>"""


def _aviso(com_x=True, fecha_esc=True):
    x = '<button class="ant-modal-close" onclick="this.closest(\'.ant-modal-root\').remove()">×</button>' if com_x else ""
    esc = "document.onkeydown = e => { if (e.key === 'Escape') document.querySelector('.ant-modal-root')?.remove(); };" \
        if fecha_esc else ""
    return f"""<div class="ant-modal-root"><div class="ant-modal-mask" style="position:fixed;inset:0;background:#0005"></div>
      <div class="ant-modal-wrap" style="position:fixed;inset:0"><div class="ant-modal" style="margin:0 auto;width:600px">
        <div class="ant-modal-content">{x}<div class="ant-modal-body" style="height:300px">Novidades do UpSeller</div>
      </div></div></div></div><script>{esc}</script>"""


def _pagina(p, html):
    exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    nav = p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)
    pg = nav.new_page()
    pg.set_content(f"<html><body style='margin:0'>{LISTA}{html}</body></html>")
    return nav, pg


def _aba(pg):
    return pg.get_by_text(re.compile(r"^\s*My Warehouse\s*\d*\s*$")).first


def test_aviso_por_cima_bloqueia_o_clique():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        nav, pg = _pagina(p, _aviso())
        try:
            _aba(pg).click(timeout=2000)
            assert False, "o clique deveria ser bloqueado pelo aviso"
        except Exception as e:  # noqa: BLE001
            assert "intercepts pointer events" in str(e)
        nav.close()


def test_fecha_aviso_e_clica_a_aba():
    from playwright.sync_api import sync_playwright
    for kw in ({}, {"com_x": False}, {"com_x": False, "fecha_esc": False}):
        c.LOG.clear()
        with sync_playwright() as p:
            nav, pg = _pagina(p, _aviso(**kw))
            c._fechar_avisos(pg)
            _aba(pg).click(timeout=3000)
            pg.locator("#ie").click(timeout=3000)
            assert pg.evaluate("document.body.dataset.aba") == "ok"
            nav.close()
        assert "aviso aberto por cima" in "\n".join(c.LOG), kw


def test_sem_aviso_nao_faz_nada():
    from playwright.sync_api import sync_playwright
    c.LOG.clear()
    with sync_playwright() as p:
        nav, pg = _pagina(p, "")
        c._fechar_avisos(pg)
        _aba(pg).click(timeout=3000)
        nav.close()
    assert "aviso" not in "\n".join(c.LOG)


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
