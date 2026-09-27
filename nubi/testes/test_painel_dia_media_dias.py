# -*- coding: utf-8 -*-
"""Card #106: no painel do dia a média de cada produto divide pelos dias com arquivo do vendedor daquele produto
(dia sem coleta fica fora, dia sem venda entra como zero), não pelo número global de datas; total e média com os
mesmos vendedores; rótulo 'base' = dias reais do denominador. Vendedor sem nenhum dia = sem média (nunca zero).
Rodar: python3 testes/test_painel_dia_media_dias.py, na pasta nubi."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.update(OPENAI_API_KEY="x", ANTHROPIC_API_KEY="x")

import nubi_web  # noqa: E402


class RepoFalso:
    """vend_vendas_dia em memória (formato já montado, como o _vendas_dias lê); sem grupos de produtos."""

    def __init__(self, linhas):
        self.linhas = linhas

    def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
        return []

    def _todos(self, tab, params=None, metodo="GET", corpo=None):
        if tab == "vend_vendas_dia":
            desde = (params or {}).get("data", "gte.").split("gte.", 1)[-1]
            return [dict(r) for r in self.linhas if r["data"] >= desde]
        return []

    def _eq(self, v):
        return f"eq.{v}"


def _linha(vendedor, data, v, u, itens):
    return {"vendedor": vendedor, "data": data, "v": v, "u": u,
            "itens": [{"k": k, "t": k, "m": "M", "v": iv, "u": iu} for k, iv, iu in itens]}


def _dados():
    datas = [f"2026-09-{d:02d}" for d in range(16, 23)]          # 7 datas antes do dia 23
    linhas = []
    for dt in datas:                                              # OUTRO: arquivo nos 7 dias (as 7 datas existem)
        linhas.append(_linha("OUTRO", dt, 100.0, 1, [("Perfume B", 100.0, 1)]))
    # AUMA: arquivo só em 4 das 7 datas, uma delas com venda zero (linha zerada)
    linhas.append(_linha("AUMA", datas[0], 400.0, 4, [("Perfume A", 400.0, 4)]))
    linhas.append(_linha("AUMA", datas[2], 200.0, 2, [("Perfume A", 200.0, 2)]))
    linhas.append(_linha("AUMA", datas[4], 0.0, 0, []))
    linhas.append(_linha("AUMA", datas[6], 600.0, 6, [("Perfume A", 600.0, 6)]))
    d = "2026-09-23"
    linhas.append(_linha("AUMA", d, 300.0, 3, [("Perfume A", 300.0, 3)]))
    linhas.append(_linha("NOVO", d, 50.0, 1, [("Perfume N", 50.0, 1)]))   # 0 dias anteriores
    return linhas, d


def test_106_media_do_produto_pelos_dias_do_vendedor():
    linhas, d = _dados()
    so_auma = [r for r in linhas if r["vendedor"] in ("AUMA", "NOVO")]
    resp = nubi_web._painel_dia(RepoFalso(so_auma), d)
    pa = next(p for p in resp["produtos_alta"] if p["chave"] == "Perfume A")
    assert pa["media"] == (400 + 200 + 0 + 600) / 4, pa                # soma ÷ 4 dias dele (não ÷ 7)
    assert resp["base"] == "4 dias" and resp["dias_base"] == 4, resp["base"]


def test_106_vendedor_sem_dias_fica_sem_dados():
    linhas, d = _dados()
    resp = nubi_web._painel_dia(RepoFalso(linhas), d)                 # com as 7 datas globais (OUTRO)
    vs = {x["vendedor"]: x for x in resp["vendedores"]}
    assert vs["NOVO"]["media"] is None and vs["NOVO"]["var"] is None, vs["NOVO"]   # sem dados, nunca zero
    pn = next(p for p in resp["produtos_alta"] if p["chave"] == "Perfume N")
    assert pn["media"] is None, pn
    pa = next(p for p in resp["produtos_alta"] if p["chave"] == "Perfume A")
    assert pa["media"] == 1200 / 4, pa                                 # n global (7) não entra


def test_106_total_e_media_com_os_mesmos_vendedores():
    linhas, d = _dados()
    so_auma = [r for r in linhas if r["vendedor"] in ("AUMA", "NOVO")]
    t = nubi_web._painel_dia(RepoFalso(so_auma), d)["total"]
    # só AUMA tem média: NOVO (0 dias) sai do total e da média juntos
    assert t["v"] == 300 and t["u"] == 3, t
    assert t["media"] * 4 == 400 + 200 + 0 + 600, t                   # média × denominador = soma da base
    assert abs(t["var"] - (300 / 300 - 1)) < 1e-9, t


if __name__ == "__main__":
    falhou = 0
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            try:
                f()
                print("ok  ", nome)
            except Exception as e:  # noqa: BLE001
                falhou += 1
                print("FALHOU", nome, repr(e)[:400])
    sys.exit(1 if falhou else 0)
