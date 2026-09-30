"""30/09 (Bruno: a Sospiro "sumiu" — o arquivo misturado da Oriente trouxe só 12 anúncios dela e virou o período padrão):
o recorte de um arquivo misturado ATUALIZA o período completo que já existe com o mesmo início, em vez de criar um período
novo pela metade."""
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import pandas as pd  # noqa: E402
import nubi  # noqa: E402


def _linha(id_, titulo, un, vendedor="V1"):
    return {"titulo": titulo, "vendedor": vendedor, "vendedor_id": vendedor, "marca_anuncio": "SOSPIRO", "un": un, "fat": un * 100.0,
            "preco": 100.0, "bruto": {"ID do anúncio": id_}}


class Repo:
    def __init__(self, snaps, anuncios):
        self._snaps, self._an, self.apagados = pd.DataFrame(snaps), anuncios, []

    def snapshots(self, marca=None):
        s = self._snaps
        return s[s["marca"] == marca] if marca else s

    def anuncios(self, sid):
        df = pd.DataFrame(self._an.get(int(sid), []))
        return df.assign(rid=range(len(df)), snapshot_id=int(sid)) if len(df) else df

    def apagar_snapshot(self, sid):
        self.apagados.append(int(sid))


def test_recorte_atualiza_o_periodo_completo_e_nao_cria_pela_metade():
    completo = [_linha("A", "Sospiro Vibrato", 1000), _linha("B", "Sospiro Padrino", 30), _linha("C", "Sospiro Decant", 70)]
    velho_parcial = [_linha("A", "Sospiro Vibrato", 5)]                        # recorte antigo (Dolce&Gabbana, 22/09)
    repo = Repo([{"id": 49, "marca": "SOSPIRO", "inicio": "2026-08-01", "fim": "2026-09-27", "dias": 58, "arquivo": "sospiro.csv"},
                 {"id": 20, "marca": "SOSPIRO", "inicio": "2026-08-01", "fim": "2026-09-22", "dias": 53, "arquivo": "dg.csv"},
                 {"id": 3, "marca": "SOSPIRO", "inicio": "2026-07-01", "fim": "2026-07-31", "dias": 31, "arquivo": "julho.csv"},
                 {"id": 7, "marca": "LATTAFA", "inicio": "2026-08-01", "fim": "2026-09-27", "dias": 58, "arquivo": "lattafa.csv"}],
                {49: completo, 20: velho_parcial, 3: [_linha("A", "Sospiro Vibrato", 400)]})
    recorte = pd.DataFrame([_linha("A", "Sospiro Vibrato", 1115), _linha("D", "Sospiro Novo", 3)])   # o que a busca trouxe
    df, absorvidos = nubi._absorver_periodo(repo, "SOSPIRO", date(2026, 8, 1), date(2026, 9, 28), recorte)
    assert sorted(absorvidos) == [20, 49]                                        # os dois com o mesmo início; julho e Lattafa ficam
    por_id = dict(zip(df["anuncio"], df["un"]))
    assert por_id == {"ID:A": 1115, "ID:D": 3, "ID:B": 30, "ID:C": 70}          # A com o número novo; B e C mantidos; D novo
    assert len(df) == 4 and (df["anuncio"].value_counts() == 1).all()
    # marca sem período com o mesmo início: nada muda
    df2, ab2 = nubi._absorver_periodo(repo, "SOSPIRO", date(2026, 9, 1), date(2026, 9, 28), recorte)
    assert ab2 == [] and len(df2) == 2


if __name__ == "__main__":
    test_recorte_atualiza_o_periodo_completo_e_nao_cria_pela_metade()
    print("ok test_recorte_atualiza_o_periodo_completo_e_nao_cria_pela_metade")
