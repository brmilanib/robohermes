"""01/10: os relatórios do Gestor Seller (vendas e curva ABC) chegam por e-mail com o arquivo em anexo; o coletor lê o
Gmail (IMAP falso aqui, só leitura) e pega o anexo certo, com o período escrito no e-mail."""
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402

AGORA = datetime.now(timezone.utc)


def _msg(assunto, nome, dados, quando, texto):
    m = EmailMessage()
    m["From"], m["Subject"] = "Gestor Seller <contato@gestorseller.com.br>", assunto
    m["Date"] = format_datetime(quando)
    m.set_content(texto)
    m.add_attachment(dados, maintype="application", subtype="octet-stream", filename=nome)
    return m.as_bytes()


CAIXA = {
    b"1": _msg("Relatório de vendas Gestor Seller", "velho.csv", b"x", AGORA - timedelta(hours=3), "antigo"),
    b"2": _msg("Relatório Curva ABC - Gestor Seller", "relatorio_curva_abc.xlsx", b"ABC", AGORA,
               "Seu relatório da Curva ABC entre 2026-09-01 00:00:00 até 2026-09-30 23:59:59 ficou pronto!"),
    b"3": _msg("Relatório de vendas Gestor Seller", "reports_sales.csv", b"a;b\n1;2\n", AGORA,
               "Olá, Bruno Seu relatório de vendas entre 2026-09-01 00:00:00 até 2026-09-30 23:59:59 ficou pronto!"),
}
BUSCAS = []


class ImapFalso:
    def __init__(self, host): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def login(self, u, s): assert s == "app-senha"
    def select(self, caixa, readonly=False): assert readonly, "o Gmail é só leitura"
    def search(self, _, crit):
        BUSCAS.append(crit)
        return "OK", [b" ".join(CAIXA)]
    def fetch(self, i, _): return "OK", [(i, CAIXA[i])]


def test_pega_o_anexo_de_vendas_com_periodo():
    c._credencial = lambda site, cfg=None: ("bruno@gmail.com", "app-senha")
    destino = Path(tempfile.mkdtemp())
    arq, ini, fim = c.anexo_email(c.GESTOR_REMETENTE, r"relat[óo]rio de vendas", AGORA - timedelta(minutes=1), destino,
                                  espera=5, imap=ImapFalso)
    assert arq.name == "reports_sales.csv" and arq.read_bytes() == b"a;b\n1;2\n"
    assert (ini, fim) == (date(2026, 9, 1), date(2026, 9, 30))
    assert "gestorseller.com.br" in BUSCAS[-1]


def test_pega_a_curva_abc():
    c._credencial = lambda site, cfg=None: ("bruno@gmail.com", "app-senha")
    arq, _, _ = c.anexo_email(c.GESTOR_REMETENTE, "curva abc", AGORA - timedelta(minutes=1), Path(tempfile.mkdtemp()),
                              espera=5, imap=ImapFalso)
    assert arq.name == "relatorio_curva_abc.xlsx"


def test_email_velho_nao_vale():
    c._credencial = lambda site, cfg=None: ("bruno@gmail.com", "app-senha")
    assert c.anexo_email(c.GESTOR_REMETENTE, "vendas", AGORA + timedelta(hours=1), Path(tempfile.mkdtemp()),
                         espera=1, imap=ImapFalso) is None


def test_sem_senha_do_gmail_avisa():
    c._credencial = lambda site, cfg=None: ("", "")
    c.LOG.clear()
    assert c.anexo_email(c.GESTOR_REMETENTE, "vendas", AGORA, Path(tempfile.mkdtemp()), espera=1) is None
    assert "guardar-senha gmail" in "\n".join(c.LOG)


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
