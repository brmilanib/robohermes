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
    minimizadas = []
    c._janela = lambda pg, e, t, estado="normal": minimizadas.append(estado) or True
    c.sys.platform = "darwin"
    try:
        P.chromium.abertos.clear()
        c.abrir_navegador(P, {}, visivel=True)                                    # Mac: minimizada no Dock, sem freio
        a = P.chromium.abertos[-1]["args"]
        assert not any("window-position" in x for x in a) and "--disable-renderer-backgrounding" in a
        assert c.mandar_para_fora(object(), {}) and minimizadas[-1] == "minimized"
        c.abrir_navegador(P, {}, visivel=True, na_tela=True)                     # login: na tela
        assert "--disable-renderer-backgrounding" not in P.chromium.abertos[-1]["args"]
    finally:
        c.sys.platform = orig
    c.sys.platform = "linux"
    try:
        c.abrir_navegador(P, {}, visivel=True)                                    # Linux: como antes
        assert not any("window-position" in a for a in P.chromium.abertos[-1]["args"])
    finally:
        c.sys.platform = orig
    # os comandos em que o Bruno mexe na janela abrem na tela
    fonte = Path(c.__file__).read_text(encoding="utf-8")
    for fn in ("cmd_entrar", "cmd_entrar_ml", "cmd_entrar_gestor", "cmd_navegar"):
        i = fonte.index(f"def {fn}("); j = fonte.find("\ndef ", i + 5)
        assert "na_tela=True" in fonte[i:j], fn


def test_perfil_em_uso_espera_ou_destrava():
    """01/10 (print do Bruno: entrar-gestor caiu com "ProcessSingleton… profile is already in use")."""
    os.environ["NUBI_CHROMIUM"] = "/x/chrome"
    erro = Exception("BrowserType.launch_persistent_context: Failed to create a ProcessSingleton for your profile directory")
    class Q:
        class chromium:
            n = 0
            @staticmethod
            def launch_persistent_context(**k):
                Q.chromium.n += 1
                if Q.chromium.n == 1:
                    raise erro
                class Ctx:
                    def add_cookies(self, *a):
                        pass
                return Ctx()
    feito = []
    antes = (c._outra_rodando, c._chrome_do_perfil_vivo, c._destravar_perfil, c.time.sleep)
    try:
        c.time.sleep = lambda s: None
        c._destravar_perfil = lambda perfil=None: feito.append("destravou")
        c._outra_rodando = lambda: None
        c._chrome_do_perfil_vivo = lambda perfil: False                  # trava velha: limpa e abre
        assert c.abrir_navegador(Q, {}, visivel=True, na_tela=True) and feito == ["destravou"] and Q.chromium.n == 2
        Q.chromium.n, feito[:] = 0, []
        vivo = iter([True, True, False, False, False])                    # outra tarefa usando: espera, não fecha nada
        c._chrome_do_perfil_vivo = lambda perfil: next(vivo, False)
        assert c.abrir_navegador(Q, {}, visivel=True, na_tela=True) and Q.chromium.n == 2
        Q.chromium.n = 0
        erro = Exception("outra coisa")
        try:
            c.abrir_navegador(Q, {}, visivel=True)
            raise AssertionError("engoliu um erro que não é de perfil em uso")
        except Exception as e:  # noqa: BLE001
            assert "outra coisa" in str(e)
    finally:
        c._outra_rodando, c._chrome_do_perfil_vivo, c._destravar_perfil, c.time.sleep = antes


if __name__ == "__main__":
    test_fora_da_tela_no_windows()
    test_perfil_em_uso_espera_ou_destrava()
    print("ok janela fora da tela")
