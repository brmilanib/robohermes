# -*- coding: utf-8 -*-
"""Card #102: o export de 1 dia do Nubimetrics arredonda as unidades de cada anúncio por faixa (2 = 2 a 4,
5 = 5 a 9, 10 = 10 a 14, 20 = 15 a 25, de 30 em diante ±5), então a soma do export fica abaixo da tabela do grupo.
Caso real: AUMA PERFUMARIA P2 em 25/09, export com 98 anúncios de 1, 44 de 2, 10 de 5, 1 de 10, 1 de 20 e 1 de 30
(296 unidades) x tabela do grupo 340 unidades: o gate #9 reprovava e a tarefa diario falhava todo dia.
Rodar: python3 testes/test_gate9_unidades_faixa.py, na pasta nubi."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.update(OPENAI_API_KEY="x", ANTHROPIC_API_KEY="x")

import nubi_web  # noqa: E402
import vend_bi  # noqa: E402


class RepoGrupo:
    def __init__(self, v, u):
        self.grupo = [{"v": v, "u": u}]

    def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
        return self.grupo if tab == "vend_grupo_dia" else []


def _linhas_25_09():
    faixas = [(1, 98), (2, 44), (5, 10), (10, 1), (20, 1), (30, 1)]
    linhas, n = [], 0
    for u, qtd in faixas:
        for _ in range(qtd):
            n += 1
            linhas.append({"titulo": f"Perfume {n}", "marca": "M", "unidades": u, "vendas": u * 600.0,
                           "preco": 600.0, "estado": "active", "tipo_pub": "classico", "full": False})
    return linhas


def _gate(u_grupo):
    itens = vend_bi.itens_dia(_linhas_25_09())
    v, u = round(sum(i["v"] for i in itens), 2), sum(i["u"] for i in itens)
    assert u == 296, u
    return nubi_web.validar_reconciliacao_publicacao(RepoGrupo(v, u_grupo), "AUMA PERFUMARIA P2", "2026-09-25",
                                                     v, u, itens)


def test_unidades_arredondadas_pelo_export_nao_bloqueiam():
    ok, motivo = _gate(340)
    assert ok and motivo is None, motivo


def test_unidades_muito_acima_da_faixa_ainda_bloqueiam():
    ok, motivo = _gate(600)       # nem com todos os anúncios no topo da faixa (438) chega perto
    assert not ok and "unidade(s)" in motivo, motivo


def test_unidades_abaixo_do_export_ainda_bloqueiam():
    ok, motivo = _gate(200)       # o grupo não pode ter menos do que o piso das faixas (286)
    assert not ok and "unidade(s)" in motivo, motivo


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_") and callable(f):
            f()
            print("ok", nome)
