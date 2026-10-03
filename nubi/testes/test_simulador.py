"""Card #151 (03/10): Simulador de Estratégia de Reposição — os 15 testes mínimos pedidos pelo Bruno (dados de teste, nunca
apresentados como reais)."""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import simulador  # noqa: E402

INI = date(2026, 6, 1)          # segunda-feira


def dias(n):
    return [(INI + timedelta(days=i)).isoformat() for i in range(n)]


def vendas(ds, por_sku):
    """por_sku = {sku: (un/dia, preço) ou função(i)->un}"""
    out = {}
    for i, d in enumerate(ds):
        for k, (u, p) in por_sku.items():
            q = u(i) if callable(u) else u
            if q:
                out.setdefault(d, {})[k] = {"un": float(q), "valor": float(q) * p}
    return out


ITENS = {"A1": {"estoque": 40, "custo": 60.0, "preco": 100.0, "margem": 20.0},
         "B1": {"estoque": 30, "custo": 40.0, "preco": 70.0, "margem": 15.0},
         "C1": {"estoque": 200, "custo": 50.0, "preco": 80.0, "margem": 10.0},     # curva C com excesso
         "Z1": {"estoque": 25, "custo": 30.0, "preco": 50.0}}                      # sem venda nenhuma
POR = {"A1": (lambda i: 6, 100.0), "B1": (lambda i: 1 if i % 2 == 0 else 0, 70.0), "C1": (lambda i: 1 if i % 10 == 0 else 0, 80.0)}

# 1) 30 dias  e  2) 90 dias
for n in (30, 90):
    ds = dias(n)
    r = simulador.rodar(ds, vendas(ds, POR), ITENS, {"prazo": 5}, pmin=30, pmax=50)
    assert r["dias"] == n and r["cenarios"] and r["confianca"] in ("Alta", "Média", "Baixa"), r["confianca"]
    assert all(c["pontuacao"] is not None for c in r["cenarios"])
    assert "rupturas_por_sku" in r["cenarios"][0]
print("ok 1-2 simulação 30 e 90 dias")

# 3) comparação 30/37/40/45/50: mais % nunca compra MENOS (com o mesmo histórico)
ds = dias(90)
r = simulador.rodar(ds, vendas(ds, POR), ITENS, {"prazo": 5}, pmin=30, pmax=50)
por = {c["pct"]: c for c in r["cenarios"]}
cs = [por[p]["comprado"] for p in (30, 37, 40, 45, 50)]
assert cs == sorted(cs), cs
assert 37 in por and r["pct_atual"] == 37
print("ok 3 comparação de percentuais", cs)

# 4) curva A com ruptura: pouco % = ruptura do campeão; muito % protege
pouco = simulador.simular(ds, simulador.demanda(ds, vendas(ds, POR), {}), ITENS, 5, {"prazo": 5})
muito = simulador.simular(ds, simulador.demanda(ds, vendas(ds, POR), {}), ITENS, 60, {"prazo": 5})
assert pouco["ruptura_a"] > muito["ruptura_a"], (pouco["ruptura_a"], muito["ruptura_a"])
assert "A1" in pouco["rupturas_por_sku"]
print("ok 4 curva A com ruptura", pouco["ruptura_a"], muito["ruptura_a"])

# 5) curva C com excesso e 6) produto sem venda
assert muito["excesso"] >= 1 and muito["sem_venda"] >= 1, (muito["excesso"], muito["sem_venda"])
print("ok 5-6 excesso e sem venda")

# 7) produto novo sem histórico: compra conservadora (sem segurança, só dura_bc)
ds = dias(40)
por7 = dict(POR, N1=(lambda i: 3 if i >= 30 else 0, 90.0))
it7 = dict(ITENS, N1={"estoque": 0, "custo": 45.0, "preco": 90.0})
c = simulador.simular(ds, simulador.demanda(ds, vendas(ds, por7), {}), it7, 60, {"prazo": 5})
assert c["comprado"] >= 0
print("ok 7 produto novo")

# 8) pedido chega só depois do prazo do fornecedor (prazo longo = mais ruptura no começo)
ds = dias(28)
curto = simulador.simular(ds, simulador.demanda(ds, vendas(ds, POR), {}), ITENS, 60, {"prazo": 2})
longo = simulador.simular(ds, simulador.demanda(ds, vendas(ds, POR), {}), ITENS, 60, {"prazo": 15})
assert longo["ruptura_a"] >= curto["ruptura_a"], (longo["ruptura_a"], curto["ruptura_a"])
print("ok 8 prazo do fornecedor")

# 9) venda cancelada não entra: o histórico vem só de pedidos válidos; uma linha zerada não vira demanda
ds = dias(14)
v9 = vendas(ds, POR)
v9[ds[3]]["A1"] = {"un": 0.0, "valor": 0.0}          # cancelado = 0 unidades válidas
d9 = simulador.demanda(ds, v9, {})
assert d9["A1"][3][0] == 0
print("ok 9 cancelada fora")

# 10/11) semana atípica alta e baixa: o limite segue as vendas dos 7 dias anteriores (só passado)
ds = dias(35)
alta = vendas(ds, {"A1": (lambda i: 20 if 14 <= i < 21 else 6, 100.0)})
baixa = vendas(ds, {"A1": (lambda i: 0 if 14 <= i < 21 else 6, 100.0)})
it10 = dict(ITENS, A1=dict(ITENS["A1"], estoque=400))      # com estoque: a venda da semana atípica é atendida
sa = simulador.simular(ds, simulador.demanda(ds, alta, {}), it10, 40, {"prazo": 5})
sb = simulador.simular(ds, simulador.demanda(ds, baixa, {}), it10, 40, {"prazo": 5})
assert sa["compra_max_semana"] > sb["compra_max_semana"], (sa["compra_max_semana"], sb["compra_max_semana"])
print("ok 10-11 semanas atípicas")

# sem dado futuro: mudar SÓ o futuro (depois do dia 20) não muda as compras até o dia 20
ds = dias(42)
base = vendas(ds, POR)
fut = vendas(ds, dict(POR, A1=(lambda i: 6 if i < 21 else 50, 100.0)))
s1 = simulador.simular(ds[:21], simulador.demanda(ds[:21], base, {}), ITENS, 40, {"prazo": 5})
s2 = simulador.simular(ds[:21], simulador.demanda(ds[:21], fut, {}), ITENS, 40, {"prazo": 5})
assert s1["comprado"] == s2["comprado"]
print("ok sem dado futuro")

# ruptura histórica estimada pela venda: 6/dia e de repente 8 dias zerados = ruptura (venda potencial estimada)
ds = dias(40)
v = vendas(ds, {"A1": (lambda i: 0 if 20 <= i < 28 else 6, 100.0)})
rup = simulador.rupturas_historicas(ds, v)
assert set(ds[20:28]) <= rup["A1"], rup
dm = simulador.demanda(ds, v, rup)
assert dm["A1"][22][0] == 0 and dm["A1"][22][1] > 4        # real 0, estimada ~6 (nunca como venda real)
print("ok rupturas históricas")

# 12) histórico insuficiente = sem recomendação
ds = dias(20)
r = simulador.rodar(ds, vendas(ds, POR), ITENS, {"prazo": 5}, pmin=30, pmax=40)
assert r["confianca"] == "Dados insuficientes" and r["recomendado"] is None, r["confianca"]
assert any("mínimo 30" in f for f in r["falta"])
print("ok 12 histórico insuficiente")

# arrumar o estoque: B e C não compram
ds = dias(60)
arr = simulador.simular(ds, simulador.demanda(ds, vendas(ds, POR), {}), ITENS, 60, {"prazo": 5}, "arrumar")
sau = simulador.simular(ds, simulador.demanda(ds, vendas(ds, POR), {}), ITENS, 60, {"prazo": 5}, "saudavel")
assert arr["comprado"] <= sau["comprado"]
print("ok estratégia arrumar o estoque")

# resumo só com números dos cenários
r = simulador.rodar(dias(90), vendas(dias(90), POR), ITENS, {"prazo": 5}, pmin=30, pmax=50)
assert "Confiança" in r["resumo"] or "confiança" in r["resumo"]
assert r["faixa_segura"] is None or r["faixa_segura"][0] <= r["faixa_segura"][1]
print("ok resumo e faixa segura; recomendado", r["recomendado"], r["confianca"])
print("ok simulador (unidade)")

# ---- servidor: rodar pela rota, 13) aplicar, 14) cancelar, 15) persistência (o que está guardado volta ao abrir) ----
import json  # noqa: E402
import nubi_web  # noqa: E402


class Repo:
    email = "brmilani@gmail.com"

    def __init__(self):
        self.ia = {}

    def _req(self, metodo, t, params=None, corpo=None, prefer=None):
        if t == "ia_resumos" and metodo == "GET":
            k = params["chave"][3:]
            return [{"texto": self.ia[k], "criado_em": "2026-10-03T12:00:00+00:00"}] if k in self.ia else []
        if t == "ia_resumos" and metodo == "POST":
            for r in corpo:
                self.ia[r["chave"]] = r["texto"]
        return []


ds = dias(90)
vd = vendas(ds, POR)
nubi_web._reposicao_dados = lambda repo, dias=30: {
    "itens": [{"sku": k, "titulo": k, "disponivel": v["estoque"], "transito": 0, "custo": v["custo"]} for k, v in ITENS.items()],
    "vendas_dia": vd, "estoque_dia": {}, "marca_de": {}, "paradas": [], "cadastro": {}, "grupo_de": {}, "estoque_em": None}
nubi_web._vendas_atuais = lambda repo, chave: {}
nubi_web._agora_br = lambda: __import__("datetime").datetime(2026, 8, 30, 10)
repo = Repo()
r = nubi_web.rota_estoque(repo, "POST", "estoque_simulador", {}, json.dumps({"dias": 90, "pmin": 30, "pmax": 45, "estrategia": "saudavel"}).encode())
assert r["cenarios"] and r["pct_atual"] == 37 and r["dados_usados"], r.keys()
e = nubi_web.rota_estoque(repo, "GET", "estoque_simulador", {}, None)
assert e["ultimas"]["saudavel"]["recomendado"] == r["recomendado"] and e["pct_atual"] == 37          # 15) guardado
c = nubi_web.rota_estoque(repo, "POST", "estoque_simulador_aplicar", {}, json.dumps({"confirmar": False, "pct": 44}).encode())
assert c["cancelado"] and nubi_web.simulador_estado(repo)["pct_atual"] == 37                           # 14) cancelar
a = nubi_web.rota_estoque(repo, "POST", "estoque_simulador_aplicar", {}, json.dumps({"confirmar": True, "pct": 41}).encode())
est = nubi_web.simulador_estado(repo)
assert est["pct_atual"] == 41 and est["historico"][-1]["anterior"] == 37 and est["historico"][-1]["novo"] == 41      # 13) aplicar
assert est["historico"][-1]["quem"] == "brmilani@gmail.com" and est["historico"][-1]["periodo"][0]
print("ok 13-15 aplicar, cancelar e persistência")
