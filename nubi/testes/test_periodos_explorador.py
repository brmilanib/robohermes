"""30/09 (Bruno: "analisar os últimos 30 dias e os últimos 7 dias no Explorador"): cada período importado da marca é uma
opção; o padrão é o que termina por último e é mais longo; o "anterior" termina antes do escolhido começar."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import pandas as pd  # noqa: E402
import nubi_web as w  # noqa: E402


def test_escolher_periodo():
    s = pd.DataFrame([{"id": 1, "inicio": "2026-08-01", "fim": "2026-09-28", "dias": 59},
                      {"id": 2, "inicio": "2026-09-22", "fim": "2026-09-28", "dias": 7},
                      {"id": 3, "inicio": "2026-07-01", "fim": "2026-07-31", "dias": 31},
                      {"id": 4, "inicio": "2026-08-30", "fim": "2026-09-28", "dias": 30}])
    a, b = w.escolher_periodo(s)
    assert a["id"] == 1 and b["id"] == 3                     # padrão: o completo; anterior: julho
    a, b = w.escolher_periodo(s, "2")
    assert a["id"] == 2 and b["id"] == 3                     # 7 dias: o de 59 dias não é "anterior" (sobrepõe)
    a, b = w.escolher_periodo(s, 3)
    assert a["id"] == 3 and b is None
    try:
        w.escolher_periodo(s, 99)
        raise AssertionError("período inexistente deveria dar erro")
    except w.ErroNuvem:
        pass


if __name__ == "__main__":
    test_escolher_periodo()
    print("ok test_escolher_periodo")
