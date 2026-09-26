"""GTINs diferentes com o mesmo nome (26/09): aponta o par para o Bruno conferir, nunca junta sozinho; junção manual vale nas análises."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import produtos_iguais as pi  # noqa: E402
import nubi_web as w  # noqa: E402

CDNI = {"chave": "6085010044712", "titulo": "Perfume Armaf Club De Nuit Intense 105ml", "marca": "ARMAF", "v": 1000}
CDNI2 = {"chave": "6085010094144", "titulo": "Perfume Club De Nuit Intense Da Armaf Ed", "marca": "ARMAF", "v": 900}
OVERDOSE = {"chave": "7896184313431", "titulo": "Armaf Club De Nuit Intense Overdose Extr", "marca": "ARMAF", "v": 5}
SEM_GTIN = {"chave": "T:club de nuit", "titulo": "Club De Nuit Intense 105ml", "marca": "ARMAF", "v": 50}


def test_final_105ml_nao_e_palavra_cortada():
    assert pi._final_cortado("Perfume Armaf Club De Nuit Intense 105ml") is None
    assert pi.compativeis(CDNI, CDNI2)                        # antes: "ml" x "ed" barrava o par
    assert not pi.compativeis(CDNI, OVERDOSE)                  # "Overdose" é outro perfume


def test_aponta_o_par_e_nao_mistura_sem_gtin():
    itens = [CDNI, CDNI2, OVERDOSE, SEM_GTIN]
    pares = pi.gtins_parecidos(itens, [[1, 0, 0]] * 4)
    assert pares == [("6085010044712", "6085010094144", pares[0][2])]    # o que vende mais fica como principal


class Repo:
    def __init__(self, linhas):
        self.linhas = linhas

    def _todos(self, t, q=None):
        return [r for r in self.linhas if r["metodo"] in q["metodo"][4:-1].split(",")] if t == "produto_grupos" else []


def test_mapa_resolve_a_corrente_titulo_gtin_gtin():
    m = w._mapa_grupos(Repo([{"chave": "T:cdn", "grupo": "6085010094144", "metodo": "ia"},
                             {"chave": "6085010094144", "grupo": "6085010044712", "metodo": "manual"},
                             {"chave": "par:a|b", "grupo": "a", "metodo": "gtin_conferir"}]))
    assert m == {"T:cdn": "6085010044712", "6085010094144": "6085010044712"}   # par a conferir não entra


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
