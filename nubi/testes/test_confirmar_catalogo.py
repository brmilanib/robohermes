# -*- coding: utf-8 -*-
"""Etapa 3 da técnica (01/10, Bruno: "entrando no catálogo dá pra confirmar se a loja tá dentro"): os 50 produtos de
catálogo em que o seguido mais vendeu -> listagem de vendedores de cada um -> ranking; só confirma candidata.
Rodar: python3 testes/test_confirmar_catalogo.py, na pasta nubi."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import meli  # noqa: E402
import nubi_web as w  # noqa: E402

N = 20


def ean(base12):
    d = [int(c) for c in base12]
    dv = (10 - sum(x * (3 if i % 2 else 1) for i, x in enumerate(d)) % 10) % 10
    return base12 + str(dv)


G = {i: ean(f"7890000000{i:02d}") for i in range(1, 26)}
G[98], G[99] = ean("789000000098"), ean("789000000099")


class Repo:
    def __init__(self, seguidos=None):
        self.resumos = {"meli|seguidos": json.dumps(seguidos or {})}
        self.eventos, self.sala = [], []

    def _eq(self, v):
        return f"eq.{v}"

    def _req(self, metodo, tabela, q=None, corpo=None, **k):
        if tabela == "ia_resumos" and metodo == "GET":
            c = (q or {}).get("chave", "")[3:]
            return [{"texto": self.resumos[c]}] if c in self.resumos else []
        if tabela == "ia_resumos":
            for r in corpo:
                self.resumos[r["chave"]] = r["texto"]
        if tabela == "tarefa_eventos":
            self.eventos += corpo
        if tabela == "reuniao_mensagens":
            self.sala += corpo
        return []

    def _todos(self, tabela, q=None):
        if tabela == "vend_relatorios":
            rels = [{"id": 9, "vendedor": "AUMA PERFUMARIA P2", "mes": "2026-09-01"}]
            return [r for r in rels if (q or {}).get("vendedor", "eq." + r["vendedor"]) == "eq." + r["vendedor"]]
        if tabela == "vend_anuncios":
            # 25 anúncios de catálogo (GTIN 7890000000001..) + 1 fora do catálogo + 1 pausado
            ls = [{"gtin": G[i], "preco": 100 + i, "fulfillment": True, "catalogo": True, "unidades": 100 - i,
                   "vendas": 1000, "titulo": f"P{i}", "marca": "X", "sku": "", "tipo_pub": "", "estado": "active"} for i in range(1, 26)]
            ls.append({"gtin": G[99], "preco": 50, "fulfillment": True, "catalogo": False, "unidades": 500, "vendas": 1, "titulo": "fora", "marca": "X", "sku": "", "tipo_pub": "", "estado": "active"})
            ls.append({"gtin": G[98], "preco": 50, "fulfillment": True, "catalogo": True, "unidades": 900, "vendas": 1, "titulo": "pausado", "marca": "X", "sku": "", "tipo_pub": "", "estado": "paused"})
            return ls
        return []


def _ofertas(cenario):
    def f(gtins, limite_produtos=2, max_gtins=8, maximo=0):
        f.gtins = list(gtins)
        out = []
        for i, g in enumerate(gtins):
            pr = 100 + int(g[-3:-1])
            out.append({"vendedor_id": "999", "gtin_busca": g, "preco": pr * 1.5, "full": False})       # loja grande, preço longe
            if cenario in ("auma_forte", "empate"):
                out.append({"vendedor_id": "222", "gtin_busca": g, "preco": pr * 1.02, "full": True})  # AUMAPERFUMARIA
            if cenario == "empate" or (cenario == "auma_forte" and i < 4):
                out.append({"vendedor_id": "111", "gtin_busca": g, "preco": pr, "full": True})         # EAMCOSMETICOS
        return out
    return f


def _lojas(ids):
    nomes = {"111": "EAMCOSMETICOS", "222": "AUMAPERFUMARIA", "999": "MEGALOJA"}
    return {i: {"id": i, "nome": nomes.get(i, i), "link": f"https://perfil.mercadolivre.com.br/{nomes.get(i, i)}"} for i in ids}


def test_confirma_candidata_pelo_nome_e_troca_a_provavel():
    meli.ofertas_por_gtin, meli.lojas = _ofertas("auma_forte"), _lojas
    w._hashes_do_nome = lambda repo, nome: ["a" * 64]
    r = Repo({"AUMA PERFUMARIA P2": {"id": "111", "nome": "EAMCOSMETICOS", "confianca": "provável", "prova": "foto de catálogo", "votos": 1}})
    x = w.confirmar_pelo_catalogo(r, "AUMA PERFUMARIA P2", N)
    assert x["ok"] and x["testados"] == N and meli.ofertas_por_gtin.gtins[0] == G[1], x     # os que mais venderam; sem o pausado/fora
    assert G[98] not in meli.ofertas_por_gtin.gtins and G[99] not in meli.ofertas_por_gtin.gtins
    top = x["ranking"][0]
    assert top["nome"] == "AUMAPERFUMARIA" and top["candidata"] and top["produtos"] == N and top["preco_bate"] == N
    assert x["loja"]["id"] == "222" and x["loja"]["confianca"] == "certa" and "catálogo (01/10)" in x["loja"]["prova"]
    seg = json.loads(r.resumos["meli|seguidos"])["AUMA PERFUMARIA P2"]
    assert seg["id"] == "222" and seg["confianca"] == "certa"
    assert json.loads(r.resumos[meli.HASH_LOJAS])["a" * 64]["id"] == "222"
    assert x["texto"].startswith("✅") and r.eventos[0]["tarefa_id"] == 126 and r.sala[0]["autor"] == "sistema"


def test_nao_decide_em_empate_nem_loja_grande_sem_ser_candidata():
    meli.ofertas_por_gtin, meli.lojas = _ofertas("empate"), _lojas
    w._hashes_do_nome = lambda repo, nome: []
    r = Repo({"AUMA PERFUMARIA P2": {"id": "111", "nome": "EAMCOSMETICOS", "confianca": "provável", "votos": 1}})
    x = w.confirmar_pelo_catalogo(r, "AUMA PERFUMARIA P2", N)
    assert "loja" not in x and x["texto"].startswith("🤔") and "★" in x["texto"], x["texto"]
    assert json.loads(r.resumos["meli|seguidos"])["AUMA PERFUMARIA P2"]["confianca"] == "provável"
    # a loja grande (999) está em todos os produtos mas não é candidata: nunca vira "certa"
    meli.ofertas_por_gtin = _ofertas("so_grande")
    x = w.confirmar_pelo_catalogo(Repo({}), "AUMA PERFUMARIA P2", N)
    assert x["ranking"][0]["id"] == "999" and not x["ranking"][0]["candidata"] and "loja" not in x
    # confirmada à mão pelo Bruno: não mexe
    meli.ofertas_por_gtin = _ofertas("auma_forte")
    r = Repo({"AUMA PERFUMARIA P2": {"id": "222", "nome": "AUMAPERFUMARIA", "confianca": "manual"}})
    x = w.confirmar_pelo_catalogo(r, "AUMA PERFUMARIA P2", N)
    assert "loja" not in x and "à mão" in x["texto"]


def test_rotina_pendentes():
    meli.ofertas_por_gtin, meli.lojas, meli.tem_chave = _ofertas("auma_forte"), _lojas, lambda: True
    w._hashes_do_nome = lambda repo, nome: []
    r = Repo({})
    assert w.confirmar_pendentes(r) == "nada a confirmar"
    r.resumos[w.CONFIRMAR_CHAVE] = json.dumps([{"vendedor": "AUMA PERFUMARIA P2", "n": N}, {"vendedor": "NINGUEM", "n": 5}])
    res = w.confirmar_pendentes(r)
    assert res.startswith("✅ AUMA") and "sem relatório" in res, res
    assert json.loads(r.resumos[w.CONFIRMAR_CHAVE]) == []


if __name__ == "__main__":
    test_confirma_candidata_pelo_nome_e_troca_a_provavel()
    test_nao_decide_em_empate_nem_loja_grande_sem_ser_candidata()
    test_rotina_pendentes()
    print("ok confirmar catálogo")
