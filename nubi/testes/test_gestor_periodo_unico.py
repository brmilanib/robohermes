# -*- coding: utf-8 -*-
"""Card #152 (03/10): no Relatório de Vendas do Gestor, escolhido "Personalizado", aparece UMA caixa de texto SEM
placeholder cujo VALOR é "Selecione um período" (o log: 'text||Selecione um período'). O coletor só procurava a caixa pelo
placeholder, não achava ('sem') e a tarefa gestor_relatorio parava em 2026-01. Página FALSA, nunca o site real."""
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "public" / "coletor"))
import coletor as c  # noqa: E402

c.CALMA = 0.2
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

PAGINA = """<html><head><meta charset="utf-8"></head><body><h1>Relatório de Vendas</h1>
  <select id="sel" onchange="document.getElementById('caixa').style.display = this.value === 'p' ? '' : 'none'">
    <option>Hoje</option><option>Ontem</option><option>Últimos 7 dias</option><option>Últimos 30 dias</option>
    <option>Mês passado</option><option value="p">Personalizado</option></select>
  <input type="text" id="caixa" value="Selecione um período" style="display:none">
  <button>Baixar relatório de vendas</button></body></html>"""


def test_caixa_unica_com_o_periodo_no_valor():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        extra = {"executable_path": CHROME} if Path(CHROME).exists() else {}
        if os.environ.get("NUBI_CHROMIUM"):
            extra = {"executable_path": os.environ["NUBI_CHROMIUM"]}
        nav = p.chromium.launch(headless=True, **extra)
        try:
            pg = nav.new_page()
            pg.set_content(PAGINA)
            assert c._gestor_periodo(pg, date(2026, 1, 1), date(2026, 1, 31))
            v = pg.locator("#caixa").input_value()
        finally:
            nav.close()
    assert "01/01/2026" in v and "31/01/2026" in v, v


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
