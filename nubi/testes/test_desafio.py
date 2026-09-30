"""30/09 (Bruno): página 🎯 Desafio (rota `desafio`): cards do tipo desafio, etapas, pesquisas do card e linha do tempo;
o DeepSeek só é liberado nos cards do tipo desafio de que é responsável."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("DEEPSEEK_API_KEY", "x")
import nubi_web as w  # noqa: E402
import agentes  # noqa: E402
import ia  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_assumir_aprovados import Repo as RepoBase  # noqa: E402


class Repo(RepoBase):
    def _todos(self, tab, q, metodo="GET", corpo=None):
        return self._req(metodo, tab, q, corpo)

DESC = "Escopo: x\nArquivo/função: y\nTeste: z\nCritério de aceite: w"


def _agora(h=0):
    return (datetime.now(timezone.utc) + timedelta(hours=h)).isoformat()


def test_painel_desafio_junta_cards_etapas_pesquisas_e_passos():
    r = Repo(tarefas=[{"id": 126, "titulo": "DESAFIO", "tipo": "desafio", "status": "aprovada", "responsavel": "claude_mac", "prioridade": "urgente"},
                      {"id": 127, "titulo": "Astra no desafio", "tipo": "desafio", "status": "em_desenvolvimento", "responsavel": "astra", "iniciado_em": _agora()},
                      {"id": 90, "titulo": "outro card", "tipo": "melhoria", "status": "pausada"}])
    r.t["tarefa_eventos"] = [
        {"id": 1, "tarefa_id": 126, "autor": "claude_code", "tipo": "relatorio", "texto": "## Etapa 1 publicada (card segue aberto)", "criado_em": _agora(-30)},
        {"id": 2, "tarefa_id": 127, "autor": "astra", "tipo": "passo", "texto": "Comecei a etapa 3", "criado_em": _agora()},
        {"id": 3, "tarefa_id": 90, "autor": "voce", "tipo": "passo", "texto": "fora do desafio", "criado_em": _agora()}]
    r.t["ia_resumos"] = [
        {"chave": "pesquisa|1c126", "texto": "## Relatório", "criado_em": _agora(-1),
         "dados": {"origem": "card #126", "pergunta": "conectores", "status": "feita", "motor": "astra", "hermes": {"status": "pendente"}}},
        {"chave": "pesquisa|2", "texto": "", "criado_em": _agora(-2), "dados": {"origem": "sala", "pergunta": "outra", "status": "feita"}}]
    p = w.painel_desafio(r)
    assert [c["id"] for c in p["cards"]] == [126, 127] and p["principal"] == 126
    assert [e["tarefa_id"] for e in p["eventos"]] == [126, 127]                  # o card fora do desafio não entra
    sit = {e["n"]: e["situacao"] for e in p["etapas"]}
    assert sit == {1: "feita", 2: "pendente", 3: "em_andamento", 4: "pendente", 5: "pendente"}, sit
    assert [q["chave"] for q in p["pesquisas"]] == ["pesquisa|1c126"] and p["pesquisas"][0]["hermes"] == "pendente"
    assert p["vendedores"] == [] and not p["erro_vendedores"]                    # sem relatórios do Nubimetrics: a página sai assim mesmo
    assert p["cards"][1]["situacao"] == "em_execucao"
    w.RepoSupabase = lambda token: r
    st, _, dados, _ = w.atender("GET", "desafio", {}, b"", "tok")
    assert st == 200 and json.loads(dados)["resumo"]["vendedores"] == 0


def test_deepseek_so_trabalha_em_card_desafio():
    chamadas = []
    velho = agentes.perguntar
    agentes.perguntar = lambda chave, texto, **k: (chamadas.append((chave, ia.tem("deepseek"))), "Entrega do DeepSeek: regras.")[1]
    try:
        r = Repo(tarefas=[{"id": 128, "titulo": "DeepSeek no desafio", "tipo": "desafio", "status": "aprovada", "responsavel": "deepseek",
                           "prioridade": "urgente", "descricao": DESC},
                          {"id": 129, "titulo": "DeepSeek comum", "tipo": "melhoria", "status": "aprovada", "responsavel": "deepseek",
                           "prioridade": "alta", "descricao": DESC}])
        velho_entregar = w.entregar_card
        w.entregar_card = lambda repo, tid, autor, txt: f"#{tid}: ok"
        try:
            w.trabalhar_agentes(r, limite=2)
        finally:
            w.entregar_card = velho_entregar
        assert chamadas == [("deepseek", True), ("deepseek", False)], chamadas   # liberado só no card desafio
        assert not ia.tem("deepseek")                                             # fora do card volta a ficar pausado
    finally:
        agentes.perguntar = velho


def test_tela_desafio_no_menu_e_na_rota():
    html = (Path(__file__).resolve().parents[1] / "public" / "index.html").read_text(encoding="utf-8")
    assert 'it("#/desafio", "🎯", "Desafio"' in html and "async function telaDesafio" in html
    assert 'location.hash.startsWith("#/desafio")) return telaDesafio()' in html and 'api("desafio")' in html
    assert 'JSON.stringify({id: P, texto})' in html                              # escrever na página vai para o card principal


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
