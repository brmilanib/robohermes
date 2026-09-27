"""Card #101: na coleta diária de 27/09 o Chrome reaberto (mesmo período do mês anterior e vendas do dia) fechou no 1º
download, a 2ª tentativa (outro Chrome) também fechou e só o 3º Chrome ficou de pé: o 1º vendedor contava erro e a tarefa
'diario' terminava "com erros". Navegador e Nubimetrics falsos (nada de site real): os dois primeiros Chromes fecham no
download, igual ao log do Mac."""
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

    def is_closed(self):
        return self.ctx.fechado


class Contexto:
    def __init__(self, n):
        self.n, self.fechado, self.pages = n, False, []

    def new_page(self):
        if self.fechado:
            raise RuntimeError("BrowserContext.new_page: Target page, context or browser has been closed")
        return Pagina(self)

    def close(self):
        self.fechado = True


def _rodar(cai):
    """cai: quantos Chromes seguidos fecham no 1º download. Devolve (arquivos, importados, erros, chromes abertos)."""
    abertos = []

    def abrir(p, cfg, visivel=None):
        abertos.append(Contexto(len(abertos)))
        return abertos[-1]

    def baixar(pg, h, ini, fim, rng, destino, nome=None):
        if pg.ctx.n < cai:
            pg.ctx.fechado = True
            raise RuntimeError(FECHADO)
        arq = destino / f"{nome}.xlsx"
        arq.write_bytes(b"x" * 4000)
        return arq

    nada = lambda *a, **k: None  # noqa: E731
    troca = {"abrir_navegador": abrir, "baixar_vendedor": baixar, "api": lambda *a, **k: {"log": ["OK"]},
             "listar_vendedores": lambda pg, cfg: ([("H1", "AUMA PERFUMARIA P2"), ("H2", "SIENO P13")], []),
             "guardar_sessao": nada, "salvar_config": nada, "enviar_foto": nada, "PAUSA": 0,
             "time": type("T", (), {"sleep": staticmethod(nada), "time": staticmethod(c.time.time)})}
    antes = {k: getattr(c, k) for k in troca}
    for k, v in troca.items():
        setattr(c, k, v)
    try:
        per = {"mes": "2026-08", "ate": "2026-08-25", "ini": "2026-08-01", "fim": "2026-08-25", "rng": "x"}
        a, i, e = c.coletar_vendedores(None, {}, "tok", [per], rota="vend_foto")
    finally:
        for k, v in antes.items():
            setattr(c, k, v)
    return a, i, e, len(abertos)


def test_chrome_fecha_duas_vezes_seguidas_nao_conta_erro():
    a, i, e, chromes = _rodar(cai=2)
    assert (a, i, e) == (2, 2, 0), (a, i, e)
    assert chromes == 3


def test_chrome_que_nunca_fica_de_pe_ainda_da_erro():
    a, i, e, _ = _rodar(cai=99)
    assert e == 2 and i == 0


if __name__ == "__main__":
    test_chrome_fecha_duas_vezes_seguidas_nao_conta_erro()
    test_chrome_que_nunca_fica_de_pe_ainda_da_erro()
    print("ok")
