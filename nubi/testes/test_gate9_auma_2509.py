# -*- coding: utf-8 -*-
"""Card #105: regressão do gate #9 com os números da AUMA PERFUMARIA P2 em 25/09 (tabela do grupo 340 un x soma do
export 296 un, 44 un = 12,9%). A exceção do card #102 (unidades arredondadas por faixa: 2 = 2 a 4, 5 = 5 a 9,
10 = 10 a 14, 20 = 15 a 25, de 30 em diante ±5) só pode liberar o que a faixa explica: as mesmas 44 un sem anúncio
arredondado (296 anúncios de 1 un, faixa exata) têm que reprovar. Se alguém afrouxar a tolerância a ponto de
cobrir 44 un, o primeiro teste quebra. Obs.: o export real de 25/09 (98x1, 44x2, 10x5, 1x10, 1x20, 1x30) tem faixa
286 a 438 un e passa desde o #102 (ver test_gate9_unidades_faixa.py).
Rodar: python3 testes/test_gate9_auma_2509.py, na pasta nubi."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.update(OPENAI_API_KEY="x", ANTHROPIC_API_KEY="x")

import nubi_web  # noqa: E402
import vend_bi  # noqa: E402

VENDEDOR, DIA = "AUMA PERFUMARIA P2", "2026-09-25"


class RepoGrupo:
    def __init__(self, grupo):
        self.grupo = grupo

    def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
        return self.grupo if tab == "vend_grupo_dia" else []


def _itens(faixas):
    linhas, n = [], 0
    for u, qtd in faixas:
        for _ in range(qtd):
            n += 1
            linhas.append({"titulo": f"Perfume {n}", "marca": "M", "unidades": u, "vendas": u * 600.0,
                           "preco": 600.0, "estado": "active", "tipo_pub": "classico", "full": False})
    return vend_bi.itens_dia(linhas)


def _gate(faixas, u_grupo):
    itens = _itens(faixas)
    v, u = round(sum(i["v"] for i in itens), 2), sum(i["u"] for i in itens)
    return u, nubi_web.validar_reconciliacao_publicacao(RepoGrupo([{"v": v, "u": u_grupo}]), VENDEDOR, DIA,
                                                        v, u, itens)


def test_105_grupo_340_x_export_296_sem_faixa_reprova():
    u, (ok, motivo) = _gate([(1, 296)], 340)
    assert u == 296, u
    assert not ok and motivo == "tabela do grupo 340 unidade(s) x soma do export do dia 296 unidade(s)", motivo


def test_105_diferenca_pequena_explicada_pela_faixa_passa():
    # 10 anúncios de "2" (= 2 a 4 cada): export 20 un, faixa 20 a 40; grupo 30 un fica dentro da faixa
    u, (ok, motivo) = _gate([(2, 10)], 30)
    assert u == 20 and ok and motivo is None, (u, motivo)
    # a mesma faixa não cobre 44 un a mais (40 + tolerância de 5 < 64)
    u, (ok, motivo) = _gate([(2, 10)], 64)
    assert not ok and "unidade(s)" in motivo, motivo


def test_105_lado_ausente_fica_pendente_nunca_zero():
    itens = _itens([(1, 296)])
    # export ausente: não publica (pendente), não vira dia zerado
    ok, motivo = nubi_web.validar_reconciliacao_publicacao(RepoGrupo([{"v": 1, "u": 340}]), VENDEDOR, DIA,
                                                           None, None, [])
    assert not ok and "ausente" in motivo, motivo
    # unidades do grupo ausentes: o gate não compara as 296 un com zero
    ok, motivo = nubi_web.validar_reconciliacao_publicacao(RepoGrupo([{"v": 296 * 600.0, "u": None}]), VENDEDOR,
                                                           DIA, 296 * 600.0, 296, itens)
    assert ok and motivo is None, motivo


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_") and callable(f):
            f()
            print("ok", nome)
