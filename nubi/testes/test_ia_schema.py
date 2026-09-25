# -*- coding: utf-8 -*-
"""erros_schema (ia.py): bool nunca deve passar como integer/number, nem em tipo único nem em lista de tipos."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ia  # noqa: E402


def test_integer_lista_recusa_bool():
    sc = {"type": ["integer", "null"]}
    assert ia.erros_schema(True, sc) and ia.erros_schema(False, sc)


def test_number_lista_recusa_bool():
    sc = {"type": ["number", "null"]}
    assert ia.erros_schema(True, sc) and ia.erros_schema(False, sc)


def test_integer_lista_aceita_int_e_null():
    sc = {"type": ["integer", "null"]}
    assert not ia.erros_schema(5, sc)
    assert not ia.erros_schema(None, sc)


def test_number_lista_aceita_float_int_e_null():
    sc = {"type": ["number", "null"]}
    assert not ia.erros_schema(5, sc)
    assert not ia.erros_schema(5.5, sc)
    assert not ia.erros_schema(None, sc)


def test_boolean_lista_continua_aceitando_bool():
    sc = {"type": ["boolean", "null"]}
    assert not ia.erros_schema(True, sc)
    assert not ia.erros_schema(None, sc)


def test_tipo_unico_continua_recusando_bool():
    assert ia.erros_schema(True, {"type": "integer"})
    assert ia.erros_schema(False, {"type": "number"})


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
