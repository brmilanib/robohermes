"""Card #139: na coleta diária de 01/10 o MARCAS Maquiagem 2026-02 falhava rodada após rodada, ora com o Chrome fechado no
download ("Download.save_as: Target page, context or browser has been closed"), ora com os botões da categoria vazios; o
mesmo mês passava numa rodada seguinte. A tarefa 'diario' terminava "com erros" porque o MARCAS não abria outro Chrome,
como os vendedores (card #101) e a tabela do grupo (card #109). Nubimetrics falso (nada de site real)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import coletor as c  # noqa: E402

FECHADO = "Download.save_as: Target page, context or browser has been closed"


def _rodar(cai, erro=FECHADO):
    """cai: quantos Chromes seguidos falham. Devolve (resultado ou exceção, Chromes abertos)."""
    abertos = []

    def marcas(p, cfg, token, mes, categoria=None, nomes=None):
        abertos.append(mes)                       # cada chamada abre e fecha o seu Chrome
        if len(abertos) <= cai:
            raise (erro if isinstance(erro, Exception) else RuntimeError(erro))
        return 1, 1, 0

    troca = {"coletar_marcas": marcas, "PAUSA": 0,
             "time": type("T", (), {"sleep": staticmethod(lambda *a: None), "time": staticmethod(c.time.time)})}
    antes = {k: getattr(c, k) for k in troca}
    for k, v in troca.items():
        setattr(c, k, v)
    try:
        r = c.coletar_marcas_reabrindo(None, {}, "tok", "2026-02", categoria="MLB1246-MLB1248", nomes=["Maquiagem"])
    except Exception as ex:  # noqa: BLE001
        r = ex
    finally:
        for k, v in antes.items():
            setattr(c, k, v)
    return r, len(abertos)


def test_chrome_fecha_no_download_do_marcas_reabre_e_importa():
    r, chromes = _rodar(cai=2)
    assert r == (1, 1, 0) and chromes == 3, (r, chromes)


def test_categoria_vazia_tambem_tenta_outro_chrome():
    r, chromes = _rodar(cai=1, erro="Locator.click: Timeout 15000ms exceeded.")
    assert r == (1, 1, 0) and chromes == 2, (r, chromes)


def test_chrome_que_nunca_fica_de_pe_ainda_da_erro():
    r, chromes = _rodar(cai=99)
    assert isinstance(r, RuntimeError) and FECHADO in str(r) and chromes == 3, (r, chromes)


def test_login_vencido_nao_repete():
    r, chromes = _rodar(cai=99, erro=c.SessaoExpirada("login"))
    assert isinstance(r, c.SessaoExpirada) and chromes == 1, (r, chromes)


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
