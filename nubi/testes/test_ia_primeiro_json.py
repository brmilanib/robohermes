# -*- coding: utf-8 -*-
"""_primeiro_json (ia.py): pega o primeiro objeto JSON de verdade no texto, sem a regex gulosa antiga."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ia  # noqa: E402


def test_texto_antes_e_depois_do_json():
    texto = 'Claro, aqui está: {"a": 1, "b": "x"} — espero que ajude!'
    assert ia._primeiro_json(texto) == {"a": 1, "b": "x"}


def test_dois_objetos_seguidos_pega_o_primeiro():
    texto = '{"a": 1} {"b": 2}'
    assert ia._primeiro_json(texto) == {"a": 1}


def test_chave_solta_antes_do_json_de_verdade():
    # a regex gulosa antiga \{.*\} ia do "{" solto até o "}" do JSON de verdade e quebrava
    texto = 'o valor é {isso não é json} mas o resultado é {"ok": true}'
    assert ia._primeiro_json(texto) == {"ok": True}


def test_resposta_lista_nao_e_aceita():
    assert ia._primeiro_json("[1, 2, 3]") == {}


def test_resposta_string_nao_e_aceita():
    assert ia._primeiro_json('"apenas um texto"') == {}


def test_sem_chave_nenhuma():
    assert ia._primeiro_json("sem json nenhum aqui") == {}


def test_objeto_aninhado_completo():
    texto = 'resposta: {"a": {"b": 1, "c": [1, 2]}, "d": null}'
    assert ia._primeiro_json(texto) == {"a": {"b": 1, "c": [1, 2]}, "d": None}


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
