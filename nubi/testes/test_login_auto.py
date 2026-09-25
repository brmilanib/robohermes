"""Login automático do coletor: páginas falsas (senha + código em 6 caixinhas), Chaveiro falso e Gmail (IMAP) falso.
Confere que a senha e o código nunca vão para o log. Roda sem Mac, sem sites e sem Gmail de verdade."""
import http.server
import os
import sys
import tempfile
import threading
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
SENHA, CODIGO = "SenhaSecreta#123", "482913"

PAGINAS = {
    "/pt/inventory/list": """<html><head><meta charset="utf-8"></head><body><form id="f">
      <input type="email" name="email"><input type="password" name="senha"><button>Ingressar</button>
      <a href="#">Esqueci a senha</a></form>
      <div id="cod" style="display:none">Digite o código enviado ao seu e-mail
        <input maxlength="1"><input maxlength="1"><input maxlength="1"><input maxlength="1"><input maxlength="1"><input maxlength="1">
        <button onclick="confere()">Verificar</button></div>
      <div id="ok" style="display:none">Importar & Exportar</div>
      <script>
        document.querySelector('#f button').onclick = e => { e.preventDefault();   // como o "Ingressar" do Nubimetrics
          if (document.querySelector('[name=senha]').value === '%s') { document.getElementById('f').style.display='none';
            document.getElementById('cod').style.display='block'; } };
        function confere(){ const c=[...document.querySelectorAll('[maxlength="1"]')].map(i=>i.value).join('');
          if (c === '%s') { document.getElementById('cod').style.display='none'; document.getElementById('ok').style.display='block'; } }
        document.querySelectorAll('[maxlength="1"]').forEach((i,k,a)=>i.addEventListener('input',()=>a[k+1]&&a[k+1].focus()));
      </script></body></html>""" % (SENHA, CODIGO),
}


class Pagina(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        corpo = PAGINAS.get(self.path.split("?")[0], "<html><body>404</body></html>").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), Pagina)
threading.Thread(target=srv.serve_forever, daemon=True).start()
os.environ["UPSELLER_URL"] = f"http://127.0.0.1:{srv.server_port}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402

c.CALMA = 0.2


class ImapFalso:
    """Gmail falso: um e-mail do UpSeller com o código, recebido agora."""
    def __init__(self, host):
        self.logado = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, u, s):
        self.logado = (u, s)

    def select(self, caixa, readonly=False):
        assert readonly                                  # só leitura
        return "OK", [b"1"]

    def search(self, charset, criterio):
        assert 'FROM "upseller"' in criterio             # só e-mails do próprio site
        return "OK", [b"1"]

    def fetch(self, i, partes):
        m = EmailMessage()
        m["From"], m["Subject"] = "UpSeller <no-reply@upseller.com>", "Seu código de verificação"
        m["Date"] = format_datetime(datetime.now(timezone.utc))
        m.set_content(f"Olá! Seu código de verificação é {CODIGO}. Ele vale por 10 minutos.")
        return "OK", [(b"1", m.as_bytes())]


def test_achar_codigo():
    assert c.achar_codigo("Seu código de verificação é 482913.") == "482913"
    assert c.achar_codigo("Pedido 2026 — code: 7788") == "7788"
    assert c.achar_codigo("nada aqui") == ""


def test_entra_sozinho_com_senha_e_codigo_do_email():
    c._credencial = lambda site, cfg=None: {"upseller": ("bruno@exemplo.com", SENHA),
                                            "gmail": ("bruno@gmail.com", "app-senha")}[site]
    original = c.codigo_email
    c.codigo_email = lambda site, desde, espera=150, imap=None: original(site, desde, 20, ImapFalso)
    c.LOG.clear()
    from playwright.sync_api import sync_playwright
    exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    if os.path.exists(exe):
        os.environ["NUBI_CHROMIUM"] = exe
    with sync_playwright() as p:
        assert c.entrar_sozinho(p, {}, "upseller", visivel=False, prazo=60)
    log = "\n".join(c.LOG)
    assert "login feito sozinho" in log and "código de verificação lido" in log
    assert SENHA not in log and CODIGO not in log      # nem a senha nem o código vão para o log


def test_sem_senha_nao_entra_e_nao_clica_em_esqueci():
    c._credencial = lambda site, cfg=None: ("", "")
    c.LOG.clear()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        assert not c.entrar_sozinho(p, {}, "upseller", visivel=False, prazo=20)
    assert "sem senha salva" in "\n".join(c.LOG)


def test_nunca_clica_em_esqueci_a_senha():
    assert c.PROIBIDO_CLICAR.search("Esqueci a senha") and c.PROIBIDO_CLICAR.search("Criar conta")
    assert not c.PROIBIDO_CLICAR.search("Entrar")


if __name__ == "__main__":
    c.enviar_foto = lambda *a, **k: None
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
