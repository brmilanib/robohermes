"""Card #109: na coleta diária de 28/09 o Chrome aberto para a tabela do grupo fechou no download do 1º dia
("Download.save_as: Target page, context or browser has been closed") e o 2º dia caiu na mesma aba fechada: 2 erros e a
tarefa 'diario' terminava "com erros". A tabela do grupo não reabria o navegador como os vendedores (card #101).
Navegador e Nubimetrics falsos (nada de site real)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import coletor as c  # noqa: E402

FECHADO = "Download.save_as: Target page, context or browser has been closed"


class Pagina:
    def __init__(self, ctx):
        self.ctx = ctx


class Contexto:
    def __init__(self, n):
        self.n, self.fechado = n, False
        self.pages = [Pagina(self)]

    def new_page(self):
        return Pagina(self)

    def close(self):
        self.fechado = True


def _rodar(cai):
    """cai: quantos Chromes seguidos fecham no download. Devolve (arquivos, importados, erros, chromes abertos)."""
    abertos = []

    def abrir(p, cfg, visivel=None):
        abertos.append(Contexto(len(abertos)))
        return abertos[-1]

    def baixar(pg, cfg, dia, destino):
        if pg.ctx.fechado or pg.ctx.n < cai:
            pg.ctx.fechado = True
            raise RuntimeError(FECHADO)
        arq = destino / f"grupo-{dia}.xlsx"
        arq.write_bytes(b"x" * 4000)
        return arq

    nada = lambda *a, **k: None  # noqa: E731
    troca = {"abrir_navegador": abrir, "baixar_grupo": baixar, "api": lambda *a, **k: {"log": ["OK"]},
             "guardar_sessao": nada, "salvar_config": nada, "PAUSA": 0,
             "time": type("T", (), {"sleep": staticmethod(nada), "time": staticmethod(c.time.time)})}
    antes = {k: getattr(c, k) for k in troca}
    for k, v in troca.items():
        setattr(c, k, v)
    try:
        a, i, e = c.coletar_grupo(None, {"grupo": "g"}, "tok", ["2026-09-26", "2026-08-26"])
    finally:
        for k, v in antes.items():
            setattr(c, k, v)
    return a, i, e, len(abertos)


def test_chrome_do_grupo_fecha_no_download_reabre_e_baixa():
    a, i, e, chromes = _rodar(cai=2)
    assert (a, i, e) == (2, 2, 0), (a, i, e)
    assert chromes == 3


def test_chrome_do_grupo_que_nunca_fica_de_pe_ainda_da_erro():
    a, i, e, _ = _rodar(cai=99)
    assert i == 0 and e == 2, (a, i, e)


if __name__ == "__main__":
    test_chrome_do_grupo_fecha_no_download_reabre_e_baixa()
    test_chrome_do_grupo_que_nunca_fica_de_pe_ainda_da_erro()
    print("ok")
