"""_br(): horário UTC do banco vira horário de Brasília no chat do Hermes (card #63)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402


def test_utc_vira_brasilia():
    assert c._br("2026-09-25T15:04:00+00:00") == "25/09 12:04"


def test_virada_do_dia_com_z():
    assert c._br("2026-09-25T02:30:00Z") == "24/09 23:30"


def test_texto_invalido_volta_sem_quebrar():
    assert c._br("ontem à noite") == "ontem à noite"
    assert c._br("") == ""
    assert c._br(None) == "None"


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
