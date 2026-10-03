"""Meta de faturamento do mês no card Minha Loja (03/10, Bruno: "meta de 1,25 mi: quanto por dia temos que vender")."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SUPABASE_URL", "http://x")
os.environ.setdefault("SUPABASE_KEY", "x")
import nubi_web as w  # noqa: E402


class R:
    def __init__(self):
        self.ia = {"reposicao|config": json.dumps({"meta_fat": 1250000}),
                   "vendas_hoje|2026-10-01": json.dumps({"total_final": {"valor": 40000}}),
                   "vendas_anuncio_dia|2026-10-01": json.dumps({"valor": 23000}),      # o "Ontem" do UpSeller vence
                   "vendas_anuncio_dia|2026-10-02": json.dumps({"valor": 30000})}

    def _eq(self, v):
        return f"eq.{v}"

    def _req(self, m, t, q=None, corpo=None, prefer=None):
        if t != "ia_resumos":
            return []
        c = q["chave"]
        if c.startswith("like."):
            p = c[5:].rstrip("%")
            return [{"chave": k, "texto": v} for k, v in self.ia.items() if k.startswith(p)]
        k = c[3:]
        return [{"texto": self.ia[k]}] if k in self.ia else []


def test_meta():
    w.vendas_hoje.tv = lambda repo, agora=None: {"ate_agora": {"valor": 10000}}
    r = w.meta_mes(R(), datetime(2026, 10, 3, 18, tzinfo=timezone.utc))
    assert r["vendido"] == 80000 and r["fechado"] == 70000 and r["media_dia"] == 35000 and r["dias_restantes"] == 29
    assert r["precisa_por_dia"] == round((1250000 - 70000) / 29, 2) and r["projecao"] == 70000 + 35000 * 29
    assert r["acima"] is False and r["pct_meta"] == 6.4 and [d["fonte"] for d in r["dias"]] == ["upseller", "anuncio"]


if __name__ == "__main__":
    test_meta()
    print("ok meta do mês")
