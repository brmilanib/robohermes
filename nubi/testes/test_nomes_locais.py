# -*- coding: utf-8 -*-
"""29/09: uma variável local 'apelidos' dentro de atender() escondeu a função apelidos() e quebrou a importação dos CSVs
do Nubimetrics ("Algo deu errado no servidor"). Nenhuma função do módulo pode ser reatribuída como variável local em atender."""
import ast
from pathlib import Path


def test_atender_nao_esconde_funcoes_do_modulo():
    arv = ast.parse((Path(__file__).resolve().parents[1] / "nubi_web.py").read_text(encoding="utf-8"))
    funcoes = {n.name for n in arv.body if isinstance(n, ast.FunctionDef)}
    atender = next(n for n in arv.body if isinstance(n, ast.FunctionDef) and n.name == "atender")
    locais = {t.id for n in ast.walk(atender) if isinstance(n, (ast.Assign, ast.AugAssign, ast.AnnAssign))
              for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)}
    locais |= {n.target.id for n in ast.walk(atender) if isinstance(n, (ast.For, ast.comprehension)) and isinstance(n.target, ast.Name)}
    assert not (locais & funcoes), f"variável local com nome de função do módulo em atender(): {sorted(locais & funcoes)}"


if __name__ == "__main__":
    test_atender_nao_esconde_funcoes_do_modulo()
    print("ok test_atender_nao_esconde_funcoes_do_modulo")
