"""Card #115: a coleta diária abre a lista de vendedores do grupo várias vezes (meses, mesmo período, dias); em 29/09 a
2ª abertura ficou só com as barras cinza ("1–0 de 0") e a tarefa inteira falhou com "a página não carregou o esperado".
Agora recarrega a página 1 vez, como a tabela do grupo (card #76). Página falsa; roda sem sites."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402

c.CALMA = 0.2

# a tabela de vendedores do grupo já carregada: 3 vendedores, links com o hash no seller=
LISTA = "<html><body><table><tbody>%s</tbody></table></body></html>" % "".join(
    f'<tr><td>VENDEDOR {i} <a aria-label="Analise um concorrente" href="/competition/competitor?seller=H{i}">🔍</a></td>'
    f"</tr>" for i in range(3))
ESQUELETO = ('<html><body><table><tbody>' + '<tr><td><span class="MuiSkeleton-root"></span></td></tr>' * 10 +
             '</tbody></table><p>1–0 de 0</p></body></html>')


def _navegador(p):
    exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    nav = p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)
    return nav, nav.new_page()


def test_recarrega_quando_a_lista_fica_carregando():
    from playwright.sync_api import sync_playwright
    visitas = []
    ir_antigo = c.ir

    def ir_falso(pg, url, esperar):
        visitas.append(url)
        if len(visitas) == 1:                                   # 1ª vez: tabela só com esqueleto, como em 29/09
            pg.set_content(ESQUELETO)
            raise c.Falha(f"a página não carregou o esperado ({esperar})")
        pg.set_content(LISTA)
    c.ir = ir_falso
    c.LOG.clear()
    try:
        with sync_playwright() as p:
            nav, pg = _navegador(p)
            lista, _ = c.listar_vendedores(pg, {"grupo": "1"})
            nav.close()
    finally:
        c.ir = ir_antigo
    assert sorted(lista) == [("H0", "VENDEDOR 0"), ("H1", "VENDEDOR 1"), ("H2", "VENDEDOR 2")]
    assert len(visitas) == 2 and "recarrego a página" in "\n".join(c.LOG)


def test_sessao_vencida_nao_recarrega():
    visitas = []
    ir_antigo = c.ir

    def ir_falso(pg, url, esperar):
        visitas.append(url)
        raise c.SessaoExpirada("login")
    c.ir = ir_falso
    try:
        c.listar_vendedores(None, {"grupo": "1"})
        assert False, "devia subir a sessão vencida"
    except c.SessaoExpirada:
        pass
    finally:
        c.ir = ir_antigo
    assert len(visitas) == 1


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
