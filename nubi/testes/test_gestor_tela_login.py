"""Card #152: a tela de login do Gestor sem campo de senha visível tem que ser reconhecida como sessão expirada."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

_EXE = "/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None
LOGIN = """<html><body>
<input type=radio name=language_selection value=en><input type=radio name=language_selection value=es-MX>
<input type=text placeholder='Ex: 12334566789'></body></html>"""
RELATORIO = "<html><body><h1>Relatório de Vendas</h1><input value='01/09/2026 - 30/09/2026'><button>Baixar relatório de vendas</button></body></html>"


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=_EXE) if _EXE else p.chromium.launch()
        pg = b.new_page()
        pg.set_content(LOGIN)
        assert c._gestor_tela_de_login(pg), "login sem senha visível não reconhecido"
        pg.set_content(RELATORIO)
        assert not c._gestor_tela_de_login(pg), "página do relatório tomada por login"
        pg.set_content("<input type=password>")
        assert c._gestor_tela_de_login(pg), "senha visível não reconhecida"
        b.close()
    print("ok")


main()
