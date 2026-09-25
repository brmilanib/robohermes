"""Memória de soluções (25/09): card 🩺 fechado vira 'Solução' fixa na caixa de conhecimento, uma vez só."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import nubi_web as w  # noqa: E402

REL = """## O que foi feito
Conferência do Gestor corrigida.
## Causa
A lista de Produtos internos do Gestor é feita de blocos (div), não de tabela.
## Solução
_linha_do_sku acha o SKU visível e lê o custo no bloco.
## Publicação
commit b0cc266"""


class Repo:
    def __init__(self):
        self.saber = []

    def _eq(self, v):
        return f"eq.{v}"

    def _req(self, m, t, q=None, corpo=None, prefer=None):
        if m == "GET" and t == "reuniao_tarefas":
            return [{"id": 60, "titulo": "🩺 Coletor: gestor falhando — conferência não bateu", "notas": "", "relatorio": REL}]
        if m == "GET" and t == "conhecimento":
            return [x for x in self.saber if x["fonte"] == q["fonte"][3:]]
        if m == "POST" and t == "conhecimento":
            self.saber += corpo
        return []


def test_card_fechado_vira_solucao_uma_vez():
    r = Repo()
    assert w.memorizar_solucoes(r) == "soluções guardadas: #60"
    s = r.saber[0]
    assert s["titulo"] == "Solução: gestor falhando — conferência não bateu" and s["fixo"] and s["autor"] == "Hermes"
    assert "Causa: A lista" in s["texto"] and "Solução: _linha_do_sku" in s["texto"] and "commit" not in s["texto"]
    assert w.memorizar_solucoes(r) == "" and len(r.saber) == 1      # não duplica


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
