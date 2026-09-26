"""ARQUIVO da Sala (26/09): os agentes pesquisam mensagens antigas e a caixa de conhecimento antes de responder."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import agentes  # noqa: E402


def test_agente_busca_e_responde_com_o_achado():
    pedidos, buscas = [], []
    respostas = iter(["BUSCAR: decisão cobertura início", "Em 25/09 decidimos mostrar a cobertura no topo."])
    r = agentes.com_arquivo(lambda t: pedidos.append(t) or next(respostas), "O que decidimos sobre o Início?",
                            lambda termo: buscas.append(termo) or "[2026-09-25 · conversa sala · Claude] Início: cobertura no topo")
    assert r.startswith("Em 25/09") and buscas == ["decisão cobertura início"]
    assert "FERRAMENTA ARQUIVO" in pedidos[0] and "RESULTADO DO ARQUIVO" in pedidos[1] and "cobertura no topo" in pedidos[1]


def test_no_maximo_duas_buscas():
    n = {"i": 0}

    def sempre_busca(t):
        n["i"] += 1
        return "BUSCAR: mais" if n["i"] <= 3 else "ok"
    assert agentes.com_arquivo(sempre_busca, "x", lambda termo: "nada") == "ok" and n["i"] == 4


def test_sem_arquivo_responde_direto():
    assert agentes.com_arquivo(lambda t: "resposta", "x", None) == "resposta"


def test_texto_do_arquivo():
    t = agentes.arquivo_texto([{"origem": "conhecimento", "titulo": "Regra", "autor": "Chefe", "texto": "publicar a ponta", "criado_em": "2026-09-25T10:00"},
                               {"origem": "mensagem", "conversa": "deepseek", "autor": "voce", "texto": "oi", "criado_em": "2026-09-26T08:00"}])
    assert "conhecimento: Regra" in t and "conversa deepseek" in t and agentes.arquivo_texto([]) == "(nada encontrado no arquivo)"


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
