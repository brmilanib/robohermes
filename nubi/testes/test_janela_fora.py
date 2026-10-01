# -*- coding: utf-8 -*-
"""01/10 (Bruno: "fica abrindo navegador no meio da tela do PC"): no Windows o Chrome abre fora da área visível;
login/entrar/navegar abrem na tela. Rodar: python3 testes/test_janela_fora.py, na pasta nubi."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402


class P:
    class chromium:
        abertos = []

        @staticmethod
        def launch_persistent_context(**k):
            P.chromium.abertos.append(k)
            class Ctx:
                def add_cookies(self, *a):
                    pass
            return Ctx()


def test_fora_da_tela_no_windows():
    os.environ["NUBI_CHROMIUM"] = "/x/chrome"
    orig = c.sys.platform
    c.sys.platform = "win32"
    try:
        c.abrir_navegador(P, {}, visivel=True)
        assert "--window-position=-32000,-32000" in P.chromium.abertos[-1]["args"]
        c.abrir_navegador(P, {}, visivel=True, na_tela=True)                     # entrar/navegar: na tela
        assert not any("window-position" in a for a in P.chromium.abertos[-1]["args"])
        c.abrir_navegador(P, {"janela_na_tela": True}, visivel=True)              # o Bruno pode desligar
        assert not any("window-position" in a for a in P.chromium.abertos[-1]["args"])
        c.abrir_navegador(P, {}, visivel=False)                                   # invisível: nada muda
        assert not any("window-position" in a for a in P.chromium.abertos[-1]["args"])
    finally:
        c.sys.platform = orig
    c.abrir_navegador(P, {}, visivel=True)                                        # Mac/Linux: como antes
    assert not any("window-position" in a for a in P.chromium.abertos[-1]["args"])
    # os comandos em que o Bruno mexe na janela abrem na tela
    fonte = Path(c.__file__).read_text(encoding="utf-8")
    for fn in ("cmd_entrar", "cmd_entrar_ml", "cmd_entrar_gestor", "cmd_navegar"):
        i = fonte.index(f"def {fn}("); j = fonte.find("\ndef ", i + 5)
        assert "na_tela=True" in fonte[i:j], fn


if __name__ == "__main__":
    test_fora_da_tela_no_windows()
    print("ok janela fora da tela")
