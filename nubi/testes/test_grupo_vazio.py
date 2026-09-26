"""Card #76: a tabela do grupo exportava vazia ("0 concorrente selecionado") porque o EXPORTAR era clicado enquanto a
tabela ainda carregava (barras cinza); e a página que não carregava a tabela não era recarregada. Páginas falsas e
planilha montada igual à real (mesmo título, linhas e colunas); roda sem sites."""
import io
import os
import sys
import tempfile
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import coletor as c  # noqa: E402

c.CALMA = 0.2
c.enviar_foto = lambda *a, **k: None

# tabela do grupo que carrega em 3 s (como a do Nubimetrics: esqueleto, depois 16 vendedores); o EXPORTAR baixa um arquivo
# com o número de vendedores na tabela no nome, como o real ("... - 0 concorrente selecionado - ...")
CARREGA = """<html><body><button id="exp">EXPORTAR</button>
  <table><thead><tr><th><input type="checkbox" checked></th><th>Vendedor</th><th>Vendas em $</th></tr></thead>
  <tbody id="corpo">%s</tbody></table>
  <script>
  document.getElementById('exp').onclick = () => {
    const n = document.querySelectorAll('td a[aria-label="Analise um concorrente"]').length;
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob(['x']));
    a.download = `Grupo de vendedores - perfumes - ${n} concorrente selecionado - 2026-09-22_2026-09-22.xlsx`;
    document.body.appendChild(a); a.click(); };
  setTimeout(() => { document.getElementById('corpo').innerHTML = Array.from({length: 16}, (_, i) =>
    `<tr><td><input type="checkbox" checked></td><td>VENDEDOR ${i + 1} <a aria-label="Analise um concorrente" href="#">🔍</a>` +
    `</td><td>R$ 100,00</td></tr>`).join(''); }, 3000);
  </script></body></html>""" % ('<tr><td><span class="MuiSkeleton-root"></span></td><td><span class="MuiSkeleton-root">'
                                '</span></td><td><span class="MuiSkeleton-root"></span></td></tr>' * 10)


def _navegador(p):
    exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    nav = p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)
    return nav, nav.new_page(accept_downloads=True)


def _planilha(nomes):
    """Igual ao arquivo real baixado em 22/09: título, período, linha em branco, cabeçalho e uma linha por vendedor."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Grupo de vendedores "
    ws.append([f"Grupo de vendedores - perfumes - {len(nomes)} concorrente selecionado"])
    ws.append(["2026-09-22 - 2026-09-22"])
    ws.append([])
    ws.append(["Vendedor", "Vendas em $", "Vendas em $ Variação", "Vendas em Unid.", "Vendas em Unid. Variação", "Visitas",
               "Visitas Variação", "Conversão", "Conversão Variação", "Share em $", "Share unid."])
    for n in nomes:
        ws.append([n, 1234.5, 0.1, 10, -0.2, 500, 0.05, 0.02, 0.0, 0.0625, 0.0625])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_arquivo_real_vazio_e_formato_lido():
    import vendedores
    try:
        vendedores.ler_grupo(_planilha([]), "grupo.xlsx")      # o que o coletor baixou em 21 e 22/09
        assert False, "devia reclamar da tabela vazia"
    except vendedores.ErroVendedor as e:
        assert "vazia" in str(e)
    linhas = vendedores.ler_grupo(_planilha([f"VENDEDOR {i}" for i in range(16)]), "grupo.xlsx")
    assert len(linhas) == 16 and linhas[0]["vendedor"] == "VENDEDOR 0" and linhas[0]["u"] == 10


def test_codigo_antigo_exporta_carregando():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        nav, pg = _navegador(p)
        pg.set_content(CARREGA)
        with pg.expect_download(timeout=30000) as d:          # como era: clica logo, com a tabela ainda carregando
            c.clicar_exportar(pg, pg.locator("#exp"), "2026-09-22")
        assert " 0 concorrente selecionado" in d.value.suggested_filename
        nav.close()


def test_espera_os_vendedores_e_recarrega_quando_nao_aparece():
    from playwright.sync_api import sync_playwright
    alvo = ((22, 9), (22, 9))
    c.periodo_na_tela = lambda pg: alvo
    visitas = []

    def ir_falso(pg, url, esperar):
        visitas.append(url)
        if len(visitas) == 1:                                   # 1ª vez: a página não carregou a tabela (23/09)
            raise c.Falha(f"a página não carregou o esperado ({esperar})")
        pg.set_content(CARREGA)
    c.ir = ir_falso
    c.LOG.clear()
    with sync_playwright() as p:
        nav, pg = _navegador(p)
        arq = c.baixar_grupo(pg, {"grupo": "1"}, "2026-09-22", Path(tempfile.mkdtemp()))
        nav.close()
    assert " 16 concorrente selecionado" in arq.name
    assert len(visitas) == 2 and "recarrego a página" in "\n".join(c.LOG)


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
