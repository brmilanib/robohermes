"""Cache do briefing nas chamadas do Claude (26/09): SISTEMA longo vai com cache_control; curto vai como texto."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import ia  # noqa: E402


def _rodar(sistema):
    enviados = []
    ia._post_json = lambda url, corpo, cab, timeout=90: (enviados.append(corpo) or {
        "content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 2400}})
    assert ia.perguntar("oi", web=False, qual="claude", sistema=sistema)[0] == "ok"
    return enviados[0]


def test_sistema_longo_vai_com_cache():
    c = _rodar("regras " * 600)
    assert c["system"][0]["cache_control"] == {"type": "ephemeral"} and c["system"][0]["text"].startswith("regras")


def test_sistema_curto_sem_cache():
    assert _rodar("curto") ["system"] == "curto"


def test_leitura_de_cache_contada():
    assert ia._tokens({"usage": {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 2400,
                                 "cache_creation_input_tokens": 0}}) == (10, 2400, 0, 5)


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
