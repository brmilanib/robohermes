"""03/10 (Bruno: "tira todas as vendas com margem desde janeiro"): coletor historico-vendas (Curva ABC do Gestor por mês +
Vendas por Anúncio do UpSeller por dia) e o lado do servidor (dias/meses que faltam, curva do mês sem trocar a atual)."""
import json
import os
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "public" / "coletor"))
import coletor  # noqa: E402
import nubi_web  # noqa: E402

# ---- coletor ----
tmp = Path(tempfile.mkdtemp())
chamadas = []


def api_falsa(token, rota, params=None, corpo=None, **k):
    chamadas.append((rota, dict(params or {})))
    if rota == "gestor_abc_meses_pendentes":
        return {"meses": ["2026-01", "2026-02"]}
    if rota == "estoque_vendas_dias_pendentes":
        assert params == {"desde": "2026-01-01"}
        return {"dias": ["2026-10-02", "2026-10-01", "2026-09-30"]}
    return {"ok": True}


pedidos_abc = []


def abc_falso(pg, cfg, p=None, ini=None, fim=None):
    pedidos_abc.append((ini, fim))
    a = tmp / f"abc_{ini}.xlsx"
    a.write_bytes(b"x")
    return a


def vendas_falso(pg, cfg, p=None, dia=None, **k):
    if dia == "2026-10-01":
        raise coletor.Falha("o período não mudou")
    a = tmp / f"Vendas_{dia}.xlsx"
    a.write_bytes(b"x")
    return a


coletor.api = api_falsa
coletor.baixar_gestor_abc = abc_falso
coletor.baixar_vendas = vendas_falso
coletor._em_chrome_novo = lambda p, cfg, fn, ver=None: fn(None)
coletor.devagar = lambda *a: None
total, ok, erros, msg = coletor.coletar_historico_vendas(None, {}, "t")
assert pedidos_abc == [(date(2026, 1, 1), date(2026, 1, 31)), (date(2026, 2, 1), date(2026, 2, 28))], pedidos_abc
assert ("gestor_vendas_importar", {"arquivo": "abc_2026-01-01.xlsx", "mes": "2026-01"}) in chamadas
assert ok == 4 and erros == 1, (ok, erros, msg)          # 2 meses + 2 dias; 1 dia falhou e o resto seguiu
assert "faltam 1" in msg and "2026-01, 2026-02" in msg, msg
assert coletor.comando_mac("historico_vendas")[-1] == "historico-vendas"
assert "historico_vendas" not in coletor.SERVIDOR_PODE          # no Mac (Gestor e Gmail estão lá)

# tempo esgotado: para antes de começar
relogio = iter([0, 10 ** 9, 10 ** 9, 10 ** 9, 10 ** 9])
chamadas.clear()
pedidos_abc.clear()
total, ok, erros, msg = coletor.coletar_historico_vendas(None, {}, "t", agora=lambda: next(relogio))
assert not pedidos_abc and ok == 0, msg

# ---- servidor ----
class Repo:
    def __init__(self):
        self.linhas = {"vendas_anuncio_dia|2026-10-01": "{}", "gestor_abc|mes|2026-01": "{}", "gestor_abc|atual": '{"x": 1}'}

    def _todos(self, t, p):
        pre = p["chave"][len("like."):-1]
        return [{"chave": k} for k in self.linhas if k.startswith(pre)]

    def _req(self, metodo, t, params=None, corpo=None, prefer=None):
        for r in corpo or []:
            self.linhas[r["chave"]] = r["texto"]
        return []


r = Repo()
agora = datetime(2026, 10, 3, 9)
ds = nubi_web.vendas_dias_pendentes(r, agora=agora, desde="2026-09-28")
assert ds == ["2026-10-02", "2026-09-30", "2026-09-29", "2026-09-28"], ds
assert len(nubi_web.vendas_dias_pendentes(r, agora=agora)) == 29                # sem desde: os 30 de sempre
assert nubi_web.gestor_abc_meses_pendentes(r, "2026-01", agora=agora) == [f"2026-{m:02d}" for m in range(2, 10)]

nubi_web.estoque.ler_abc_gestor = lambda c: [{"sku": "A", "curva": "A", "valor": 100.0}]
nubi_web.estoque.resumo_abc_gestor = lambda ls: [{"curva": c, "produtos": 0, "ads": 0.0, "lucro_pos_ads": 10.0} for c in "ABCZ"]
nubi_web.estoque.eh_abc_gestor = lambda c: True
out = nubi_web.rota_estoque(r, "POST", "gestor_vendas_importar", {"arquivo": "abc.xlsx", "mes": "2026-02"}, b"x")
assert out["mes"] == "2026-02", out
d = json.loads(r.linhas["gestor_abc|mes|2026-02"])
assert d["inicio"] == "2026-02-01" and d["fim"] == "2026-02-28", d
assert r.linhas["gestor_abc|atual"] == '{"x": 1}'                                 # a atual não muda
print("ok historico de vendas")
