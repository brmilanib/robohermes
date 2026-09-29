"""Explorador por quinzena (30/09, Bruno: "atualizar todas as marcas todo dia 02 e 16 para ver se o mercado cresce ou cai"):
a última quinzena fechada com o atraso de 2 dias do Nubimetrics e a lista das marcas que ainda não têm o export dela."""
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import nubi_web as w  # noqa: E402


def test_ultima_quinzena():
    q = lambda d: tuple(x.isoformat() for x in w.ultima_quinzena(date.fromisoformat(d)))
    assert q("2026-10-02") == ("2026-09-16", "2026-09-30")        # dia 2: 2ª quinzena do mês anterior (D-2 = 30/09)
    assert q("2026-09-17") == ("2026-09-01", "2026-09-15")        # dia 17: 1ª quinzena (D-2 = 15)
    assert q("2026-09-16") == ("2026-08-16", "2026-08-31")        # dia 16 o Nubimetrics só tem até o dia 14
    assert q("2026-03-02") == ("2026-02-16", "2026-02-28")        # fevereiro
    assert q("2026-09-29") == ("2026-09-01", "2026-09-15")


class _Repo:
    def __init__(self, snaps, pedido=None):
        self.snaps, self.pedido, self.apagou = snaps, pedido, False

    def _req(self, metodo, tabela, q=None, **k):
        if tabela == "ia_resumos" and metodo == "GET":
            return [{"texto": json.dumps(self.pedido)}] if self.pedido else []
        if tabela == "ia_resumos" and metodo == "DELETE":
            self.apagou = True
        return []

    def _todos(self, tabela, q=None):
        return self.snaps


def test_pendentes():
    snaps = [{"marca": "FERRARI", "inicio": "2026-08-01", "fim": "2026-09-28"},
             {"marca": "LATTAFA", "inicio": "2026-09-01", "fim": "2026-09-15"},
             {"marca": "XERJOFF", "inicio": "2026-08-01", "fim": "2026-09-27"}]
    r = w.explorador_quinzena_pendente(_Repo(snaps), datetime(2026, 9, 17, 8, 0))
    assert r["rodar"] and (r["inicio"], r["fim"]) == ("2026-09-01", "2026-09-15"), r
    assert [m["marca"] for m in r["marcas"]] == ["FERRARI", "XERJOFF"], r          # a Lattafa já tem esta quinzena
    assert r["marcas"][0]["arquivo"] == "FERRARI__2026-09-01_2026-09-15.csv" and r["marcas"][0]["busca"] == "Ferrari"
    assert not w.explorador_quinzena_pendente(_Repo(snaps), datetime(2026, 9, 29, 8, 0))["rodar"]   # fora dos dias
    # pedido do Bruno: qualquer período, qualquer dia; terminou, o pedido é apagado
    rp = _Repo(snaps, {"inicio": "2026-09-01", "fim": "2026-09-15"})
    r = w.explorador_quinzena_pendente(rp, datetime(2026, 9, 29, 8, 0))
    assert r["rodar"] and len(r["marcas"]) == 2
    rp.snaps = [dict(x, inicio="2026-09-01", fim="2026-09-15") for x in snaps]
    assert not w.explorador_quinzena_pendente(rp, datetime(2026, 9, 29, 8, 0))["rodar"] and rp.apagou


if __name__ == "__main__":
    test_ultima_quinzena()
    test_pendentes()
    print("ok explorador por quinzena")
