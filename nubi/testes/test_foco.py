"""Análise diária do DeepSeek (25/09): concorrentes × meu estoque; os números saem do código, a IA só interpreta."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import nubi_web as w  # noqa: E402

ESTOQUE = [{"sku": "LAT-ASAD-100", "titulo": "Perfume Lattafa Asad Eau de Parfum 100ml Masculino", "disponivel": 7, "atual": 7, "custo_medio": "95.50"},
           {"sku": "ARMAF-ODY-200", "titulo": "Body Spray Odyssey Mega Armaf 200 ml", "disponivel": 0, "atual": 0, "custo_medio": "48.00"},
           {"sku": "LAT-ASAD-30", "titulo": "Lattafa Asad 30ml", "disponivel": 3, "atual": 3, "custo_medio": "40"}]
for it in ESTOQUE:
    it["_tok"] = w._tokens_produto(it["titulo"])


def test_casar_estoque():
    assert w.casar_estoque("Lattafa Asad EDP 100 ml masculino original", ESTOQUE)["sku"] == "LAT-ASAD-100"   # volume manda
    assert w.casar_estoque("Armaf Odyssey Mega body spray 200ml", ESTOQUE)["sku"] == "ARMAF-ODY-200"
    assert w.casar_estoque("Lattafa Khamrah 100ml", ESTOQUE) is None            # só a marca em comum não basta
    assert w.casar_estoque("Perfume", ESTOQUE) is None


class Repo:
    def __init__(self):
        self.gravados = []

    def _eq(self, v):
        return f"eq.{v}"

    def _todos(self, t, q=None):
        return [dict(x) for x in ESTOQUE] if t == "estoque_itens" else []

    def _req(self, m, t, q=None, corpo=None, prefer=None):
        if m == "GET" and t == "estoque_atualizacoes":
            return [{"id": 3, "criado_em": "2026-09-25T13:25:00+00:00"}]
        if m == "GET" and t == "ia_resumos":
            return [x for x in self.gravados if x["chave"] == q["chave"][3:]]
        if m == "POST" and t == "ia_resumos":
            self.gravados += corpo
        return []


def _preparar():
    w._vend_rels = lambda repo: [{"id": 1, "vendedor": "LOJA A", "mes": "2026-09-01", "importado_em": "x"},
                                 {"id": 2, "vendedor": "LOJA B", "mes": "2026-09-01", "importado_em": "x"},
                                 {"id": 9, "vendedor": "LOJA A", "mes": "2026-08-01", "importado_em": "x"}]
    linhas = {1: [{"titulo": "Lattafa Asad EDP 100ml", "marca": "LATTAFA", "gtin": "789", "vendas": 1000.0, "unidades": 10, "preco": 100.0},
                  {"titulo": "Lattafa Khamrah 100ml", "marca": "LATTAFA", "gtin": None, "vendas": 3000.0, "unidades": 20, "preco": 150.0}],
              2: [{"titulo": "Asad Lattafa 100 ml", "marca": "LATTAFA", "gtin": "789", "vendas": 600.0, "unidades": 5, "preco": 120.0},
                  {"titulo": "Armaf Odyssey Mega 200ml", "marca": "ARMAF", "gtin": None, "vendas": 90.0, "unidades": 1, "preco": 90.0}],
              9: [{"titulo": "mês velho não entra", "marca": "X", "gtin": None, "vendas": 99999.0, "unidades": 1, "preco": 1.0}]}
    w._vend_linhas = lambda repo, rid, bruto=False: linhas[rid]


def test_dados_foco_calcula_e_cruza():
    _preparar()
    d = w.dados_foco(Repo())
    assert d["mes"] == "2026-09" and d["vendedores"] == 2
    p = {x["produto"]: x for x in d["produtos"]}
    asad = p["Lattafa Asad EDP 100ml"]                       # o mesmo GTIN nas 2 lojas vira 1 produto
    assert asad["vendas"] == 1600.0 and asad["unidades"] == 15 and asad["vendedores"] == 2
    assert asad["preco_medio"] == round((100 * 10 + 120 * 5) / 15, 2) and asad["preco_min"] == 100.0
    assert asad["situacao"] == "tenho" and asad["meu_disponivel"] == 7 and asad["margem_antes_taxas"] == round(asad["preco_medio"] - 95.5, 2)
    assert p["Lattafa Khamrah 100ml"]["situacao"] == "não tenho"
    assert p["Armaf Odyssey Mega 200ml"]["situacao"] == "zerado"
    assert d["produtos"][0]["produto"] == "Lattafa Khamrah 100ml"   # ordenado por vendas
    assert "mês velho não entra" not in p


def test_gtin_vem_antes_do_titulo():
    _preparar()
    ESTOQUE.append({"sku": "7891234567895", "titulo": "Produto com outro nome no meu estoque", "disponivel": 2, "atual": 2, "custo_medio": "10"})
    try:
        linhas = {1: [{"titulo": "Nome bem diferente no concorrente", "marca": "X", "gtin": "7891234567895", "vendas": 50.0, "unidades": 1, "preco": 50.0}],
                  2: []}
        w._vend_linhas = lambda repo, rid, bruto=False: linhas.get(rid, [])
        p = w.dados_foco(Repo())["produtos"][0]
        assert p["meu_sku"] == "7891234567895" and p["casado_por"] == "gtin" and p["situacao"] == "tenho"
    finally:
        ESTOQUE.pop()


def test_analise_foco_grava_uma_vez_por_dia():
    _preparar()
    pedidos = []
    w.ia.perguntar = lambda pedido, **k: (pedidos.append(pedido) or "## Onde focar hoje\n- Khamrah", [], "deepseek")
    r = Repo()
    assert "gravada" in w.analise_foco(r)
    assert "NÃO invente" in pedidos[0] and "Khamrah" in pedidos[0] and "margem antes das taxas" in pedidos[0]
    assert r.gravados[0]["chave"].startswith("foco|") and r.gravados[0]["dados"]["produtos"]
    assert w.analise_foco(r) == "já feita hoje" and len(pedidos) == 1


def test_plano_semanal_separado():
    _preparar()
    pedidos = []
    w.ia.perguntar = lambda pedido, **k: (pedidos.append(pedido) or "## 5 prioridades da semana\n1. Repor Asad", [], "deepseek")
    r = Repo()
    assert "plano da semana gravado" in w.analise_foco(r, semanal=True)
    assert "PLANO DA SEMANA" in pedidos[0]
    assert r.gravados[0]["chave"].startswith("foco_semana|")
    assert "gravada" in w.analise_foco(r)               # a diária é outra, grava à parte
    assert r.gravados[1]["chave"].startswith("foco|")


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
