# -*- coding: utf-8 -*-
"""02/10 (Bruno: "no nubi temos até 28/09; só queremos a diferença, os dias 29 e 30"): histórico do novo − do antigo por ID
do anúncio; anúncio fora do antigo = o que vendeu no novo; nunca soma duas vezes. Rodar na pasta nubi."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import pandas as pd  # noqa: E402
import nubi  # noqa: E402


def linha(i, un, hist, dias_pub=200, vend="MNZIMPORTS P11", vid="v1"):
    return {"bruto": {"ID do anúncio": f"id{i}"}, "vendedor_id": vid, "vendedor": vend, "titulo": f"t{i}", "un": un,
            "fat": un * 100.0, "un_hist": hist, "fat_hist": hist * 100.0, "dias_pub": dias_pub}


def test_diferenca_pelo_historico():
    antigo = pd.DataFrame([linha(1, 900, 5000), linha(2, 10, 300), linha(3, 5, 50)])
    novo = pd.DataFrame([linha(1, 610, 5060),                       # vendeu 60 em 29-30/09
                         linha(2, 4, 300),                           # nada
                         linha(4, 7, 7, dias_pub=1, vend="GARCA.AMETISTA.LACTEO", vid="v9"),   # anúncio novo
                         linha(5, 3, 40, dias_pub=300),              # sem venda no período antigo: as 3 são do intervalo
                         linha(3, 5, 45)])                           # histórico diminuiu: 0, nunca negativo
    d = nubi.diferenca_exports(antigo, novo, 2).set_index("titulo")
    assert d.at["t1", "du"] == 60 and d.at["t1", "dfat"] == 6000
    assert d.at["t2", "du"] == 0
    assert d.at["t4", "du"] == 7 and d.at["t4", "situacao"] == "anúncio novo"
    assert d.at["t5", "du"] == 3 and d.at["t5", "situacao"] == "sem venda no export antigo"
    assert d.at["t3", "du"] == 0 and "diminuiu" in d.at["t3", "situacao"]
    assert d["du"].sum() == 70



def test_rota_da_diferenca():
    import nubi_web as w
    base = {c: None for c in nubi.CAMPOS_ANUNCIO}

    def ans(sid, xs):
        return pd.DataFrame([dict(base, rid=i, snapshot_id=sid, marca_anuncio="AL WATANIAH", categoria="", gtin="", sku="",
                                  produto="Al Wataniah Sabah Al Ward EDP 100 ml", **x) for i, x in enumerate(xs)])

    class R:
        def snapshots(self, marca=None):
            return pd.DataFrame([{"id": 93, "marca": "AL WATANIAH", "inicio": "2026-08-01", "fim": "2026-09-28", "dias": 59},
                                 {"id": 1000, "marca": "AL WATANIAH", "inicio": "2026-09-01", "fim": "2026-09-30", "dias": 30}])

        def anuncios(self, sid):
            if sid == 93:
                return ans(93, [linha(1, 900, 5000), linha(2, 10, 300)])
            return ans(1000, [linha(1, 610, 5060), linha(2, 4, 300), linha(4, 7, 7, dias_pub=1, vend="GARCA.AMETISTA.LACTEO", vid="v9")])
    r = w.explorador_diferenca(R(), "AL WATANIAH")
    assert r["ok"] and r["dias"] == ["2026-09-29", "2026-09-30"], r
    assert r["totais"]["un"] == 67 and r["totais"]["vendedores_novos"] == 1, r["totais"]
    pv = {x["nome"]: x for x in r["por_vendedor"]}
    assert pv["MNZIMPORTS P11"]["seguido"] and not pv["MNZIMPORTS P11"]["novo"]
    assert pv["GARCA.AMETISTA.LACTEO"]["novo"] and not pv["GARCA.AMETISTA.LACTEO"]["seguido"]


if __name__ == "__main__":
    test_diferenca_pelo_historico()
    test_rota_da_diferenca()
    print("ok diferença")
