"""Card #94: ao abrir um card longo em Central → Desenvolvimento a rolagem travava. O painel (.tf) tinha overflow:hidden e
só a linha do tempo rolava; com a descrição aberta e o relatório final longo, o resto era cortado sem jeito de chegar
ao fim, e o quadro atrás continuava rolando. Página falsa com o CSS real do index.html e o mesmo HTML do painel."""
import os
import re
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1] / "public" / "index.html").read_text(encoding="utf-8")
CSS = re.search(r"<style>(.*?)</style>", HTML, re.S).group(1)

LONGO = "<p>" + "Linha comprida do relatório final. " * 8 + "</p>"
PAGINA = f"""<html><head><style>{CSS}</style></head><body>
  <div id="quadro" style="height:4000px">quadro de desenvolvimento</div>
  <script>
  function abrir(relatorio) {{
    const bg = document.createElement("div"); bg.className = "modal-bg tarefa";
    bg.innerHTML = `<div class="card modal"><div class="tf" id="tf">
      <div class="tf-cab"><h2 style="margin:0;font-size:17px">Card longo</h2><div style="flex:1"></div><button class="btn small">✕</button></div>
      <details class="tf-desc" open><summary>O que é para fazer</summary><textarea rows="6"></textarea></details>
      <details class="tf-rel" open><summary>📄 Relatório final</summary>${{relatorio}}
        <pre>${{"x".repeat(400)}}</pre></details>
      <div class="tf-lin" id="tf-lin">${{'<div class="tf-b">passo</div>'.repeat(30)}}</div>
      <div class="tf-in"><textarea id="tf-txt" rows="1"></textarea><button class="btn primary">➤</button></div>
      <div class="tf-st" id="fim"><select id="tf-status"><option>Feita</option></select></div></div></div>`;
    document.body.appendChild(bg);
    return bg;
  }}
  </script></body></html>"""


def _navegador(p):
    exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    return p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)


def test_card_longo_rola_ate_o_fim_e_libera_o_fundo():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        nav = _navegador(p)
        pg = nav.new_page(viewport={"width": 390, "height": 700})
        pg.set_content(PAGINA)
        pg.evaluate("scrollTo(0, 1200)")
        for _ in range(3):   # fechar e reabrir várias vezes
            pg.evaluate(f"abrir({LONGO * 12!r})")
            tf = pg.locator("#tf")
            # o painel rola: chega ao seletor de status no fim, sem corte nem rolagem horizontal
            pg.mouse.move(200, 400)
            pg.mouse.wheel(0, 20000)
            pg.wait_for_timeout(300)
            fim = pg.locator("#fim").bounding_box()
            assert fim and fim["y"] + fim["height"] <= 700 + 1, fim
            assert tf.evaluate("e => e.scrollWidth <= e.clientWidth")
            assert pg.evaluate("document.documentElement.scrollWidth <= innerWidth")
            # a linha do tempo não some (continua com altura para ler os passos)
            assert pg.locator("#tf-lin").bounding_box()["height"] >= 150
            # o fundo não rola enquanto a janela está aberta
            assert pg.evaluate("getComputedStyle(document.documentElement).overflow") == "hidden"
            assert pg.evaluate("scrollY") == 1200
            pg.evaluate("document.querySelector('.modal-bg').remove()")
            # fechou: o quadro volta a rolar e mantém a posição
            assert pg.evaluate("getComputedStyle(document.documentElement).overflow") != "hidden"
            assert pg.evaluate("scrollY") == 1200
        pg.mouse.wheel(0, 300)
        pg.wait_for_timeout(300)
        assert pg.evaluate("scrollY") > 1200
        nav.close()


def test_card_curto_usa_a_altura_toda():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        nav = _navegador(p)
        pg = nav.new_page(viewport={"width": 1280, "height": 800})
        pg.set_content(PAGINA)
        pg.evaluate("abrir('')")
        assert pg.locator("#tf").evaluate("e => e.scrollHeight <= e.clientHeight + 1")   # nada para rolar no painel
        fim = pg.locator("#fim").bounding_box()
        assert fim["y"] + fim["height"] <= 800 + 1
        nav.close()


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
