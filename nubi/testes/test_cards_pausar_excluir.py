"""30/09 (Bruno): status "pausada" (fora da fila, nenhum agente pega) e o botão 🗑 Excluir card (rota reuniao_tarefa_excluir)."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import nubi_web as w  # noqa: E402
import reuniao  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_assumir_aprovados import Repo as RepoBase  # noqa: E402


class Repo(RepoBase):
    def _req(self, m, tab, q=None, corpo=None, prefer=None):
        if m == "DELETE":
            q = q or {}
            k, v = next(iter(q.items()))
            rows = self.t.setdefault(tab, [])
            rows[:] = [x for x in rows if str(x.get(k)) != v.split(".", 1)[1]]
            return None
        return super()._req(m, tab, q, corpo, prefer)


def _rota(repo, rota, corpo, metodo="POST"):
    w.RepoSupabase = lambda token: repo
    st, _, dados, _ = w.atender(metodo, rota, {}, json.dumps(corpo).encode(), "tok")
    return st, json.loads(dados)


def test_pausada_fica_fora_da_fila_e_sem_situacao():
    assert "pausada" in reuniao.STATUS
    r = Repo(tarefas=[{"id": 7, "titulo": "guardado", "status": "pausada", "responsavel": "claude_mac", "prioridade": "alta"},
                      {"id": 8, "titulo": "na fila", "status": "aprovada", "responsavel": "claude_mac", "prioridade": "alta",
                       "descricao": "Escopo: x\nArquivo/função: y\nTeste: z\nCritério de aceite: w"}], online=True)
    assert w._situacao_card(r.card(7)) == (None, None, None)
    w.trabalhar_agentes(r, limite=2)
    w.distribuir_cards(r)
    assert r.card(7)["status"] == "pausada" and not r.textos(7)          # ninguém pega nem escreve no card pausado
    assert reuniao._tarefas_txt(r.t["reuniao_tarefas"]).startswith("#8 [") and "#7" not in reuniao._tarefas_txt(r.t["reuniao_tarefas"])


def test_salvar_aceita_pausada():
    r = Repo(tarefas=[{"id": 3, "titulo": "t", "status": "aprovada", "responsavel": "claude_code"}])
    st, j = _rota(r, "reuniao_tarefa_salvar", {"id": 3, "status": "pausada"})
    assert st == 200 and j["ok"] and r.card(3)["status"] == "pausada"
    assert r.textos(3) == ["Status mudou para: pausada"]


def test_excluir_apaga_card_e_passos_mas_nao_em_execucao():
    r = Repo(tarefas=[{"id": 5, "titulo": "velho", "status": "pausada"}, {"id": 6, "titulo": "rodando", "status": "em_desenvolvimento"}])
    r.t["tarefa_eventos"] = [{"id": 1, "tarefa_id": 5, "texto": "a"}, {"id": 2, "tarefa_id": 6, "texto": "b"}]
    st, j = _rota(r, "reuniao_tarefa_excluir", {"id": 5})
    assert st == 200 and j == {"ok": True, "id": 5, "titulo": "velho"}
    assert [t["id"] for t in r.t["reuniao_tarefas"]] == [6] and [e["tarefa_id"] for e in r.t["tarefa_eventos"]] == [6]
    st, j = _rota(r, "reuniao_tarefa_excluir", {"id": 6})
    assert st == 400 and "em execução" in j["erro"], j
    st, j = _rota(r, "reuniao_tarefa_excluir", {"id": 99})
    assert st == 404


def test_tela_tem_pausadas_e_botao_excluir():
    html = (Path(__file__).resolve().parents[1] / "public" / "index.html").read_text(encoding="utf-8")
    assert 'pausada: ["Pausadas"' in html and "⏸ Pausadas (" in html
    assert 'id="tf-excluir"' in html and 'api("reuniao_tarefa_excluir"' in html and "confirm(" in html


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
