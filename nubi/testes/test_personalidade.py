"""Personalidade dos agentes (25/09): muda o jeito de falar, entra no pedido à IA e aparece no perfil."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import agentes  # noqa: E402


def test_todo_agente_da_sala_tem_voz_e_perfil_tem_jeito():
    for k in list(agentes.AGENTES) + ["claude"]:
        assert "Seu jeito" in agentes.voz(k) and agentes.REGRA_PERSONALIDADE in agentes.voz(k), k
    for k, p in agentes.PERFIS.items():
        assert p.get("jeito"), f"{k} sem personalidade na aba Agentes"
    assert agentes.voz("nao_existe") == ""


def test_voz_vai_no_pedido():
    pedidos = []
    agentes.ia.perguntar = lambda pedido, **k: (pedidos.append((pedido, k)) or "ok", [], "deepseek")
    assert agentes.perguntar("deepseek", "confira a conta") == "ok"
    pedido, k = pedidos[0]
    assert "cético dos números" in pedido and pedido.endswith("confira a conta")
    assert k["sistema"].startswith(agentes.SISTEMA)          # regras do sistema continuam iguais


def test_hermes_e_qwen_no_mac_tem_a_mesma_voz():
    src = (Path(__file__).resolve().parents[1] / "public/coletor/coletor.py").read_text()
    assert "vigia da noite, calmo, leal e protetor" in src and "bibliotecário meticuloso" in src
    assert agentes.PERSONALIDADES["hermes"]["voz"].startswith("Seu jeito: vigia da noite, calmo, leal e protetor")


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
