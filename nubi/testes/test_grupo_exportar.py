"""Card #74: EXPORTAR da tabela do grupo coberto (balão do chat) ou desabilitado enquanto carrega; e tarefa "com erros"
(sem exceção) chamando o Hermes vigia. Páginas falsas; roda sem sites."""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402

c.CALMA = 0.2
c.enviar_foto = lambda *a, **k: None

# EXPORTAR que baixa um arquivo; %s = o que atrapalha o clique
PAGINA = """<html><body style="margin:0"><div style="padding:40px"><button id="exp" %s>EXPORTAR</button></div>
  %s
  <script>document.getElementById('exp').onclick = () => { const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob(['x'])); a.download = 'grupo.xlsx'; document.body.appendChild(a); a.click(); };
  %s</script></body></html>"""
COBERTO = PAGINA % ("", '<div id="chat" style="position:fixed;inset:0;z-index:9;background:rgba(0,0,0,.1)">Vi que deseja'
                        ' incluir mais concorrentes…</div>', "")
DESABILITADO = PAGINA % ("disabled", "", "setTimeout(() => document.getElementById('exp').disabled = false, 2000);")


def _pagina(p, html):
    exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    nav = p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)
    pg = nav.new_page(accept_downloads=True)
    pg.set_content(html)
    return nav, pg


def _botao(pg):
    return pg.locator("button, [role=button]", has_text=c.re.compile(r"^\s*EXPORTAR\s*$", c.re.I)).last


def test_codigo_antigo_reproduz_o_timeout():
    from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
    with sync_playwright() as p:
        nav, pg = _pagina(p, COBERTO)
        try:
            _botao(pg).click(timeout=3000)             # como era: o balão por cima segura o clique até estourar
            assert False, "devia ter estourado o tempo"
        except PwTimeout:
            pass
        nav.close()


def test_exporta_com_balao_por_cima_e_com_botao_desabilitado():
    from playwright.sync_api import sync_playwright
    c.LOG.clear()
    with sync_playwright() as p:
        for html in (COBERTO, DESABILITADO):
            nav, pg = _pagina(p, html)
            with pg.expect_download(timeout=30000) as d:
                c.clicar_exportar(pg, _botao(pg), "2026-09-23")
            assert d.value.suggested_filename == "grupo.xlsx"
            nav.close()
    assert "EXPORTAR estava coberto por DIV chat" in "\n".join(c.LOG)


def test_tarefa_com_erros_sem_excecao_vai_para_o_hermes():
    c.token_nubi = lambda cfg: "T"
    c.api = lambda *a, **k: {}
    c.aviso_mac = lambda *a: None
    c.FALHAS.unlink(missing_ok=True)
    assert c._executar("diario", lambda p, cfg, token: (4, 4, 3, "tabela do grupo: 0 dia(s), 3 erro(s)")) == 1
    falhas = json.loads(c.FALHAS.read_text())
    assert falhas[-1]["tarefa"] == "diario" and "3 erro(s)" in falhas[-1]["erro"]
    assert c._falhas_pendentes()


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
