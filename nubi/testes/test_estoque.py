# -*- coding: utf-8 -*-
"""Comparação do estoque (UpSeller): entradas, saídas, zerados, voltaram, novos e removidos."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import estoque  # noqa: E402


def it(sku, atual, **k):
    return dict({"sku": sku, "titulo": sku.lower(), "atual": atual, "disponivel": atual}, **k)


def test_comparar():
    a = [it("A", 6), it("B", 12), it("C", 0), it("D", 3), it("R", 1)]
    b = [it("A", 2), it("B", 0), it("C", 4), it("D", 3), it("N", 10, subtotal=500)]
    d = estoque.comparar(a, b)
    assert d["n"] == {"entradas": 1, "saidas": 2, "zeraram": 1, "voltaram": 1, "novos": 1, "removidos": 1}
    assert d["unidades_entraram"] == 4 and d["unidades_sairam"] == 16
    assert d["saidas"][0]["sku"] == "B" and d["zeraram"][0]["sku"] == "B"
    assert d["totais"]["unidades"] == 19 and d["totais"]["valor"] == 500 and d["totais"]["zerados"] == 1
    assert "saldo −3 un." in " ".join(estoque.resumo_texto(d))


def test_primeira_foto():
    d = estoque.comparar([], [it("A", 1)])
    assert not d["tem_anterior"] and "Primeira foto" in estoque.resumo_texto(d)[1]


if __name__ == "__main__":
    test_comparar()
    test_primeira_foto()
    print("ok")
