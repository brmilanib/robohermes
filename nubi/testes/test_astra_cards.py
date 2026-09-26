"""Astra grava cards (design/usabilidade/organização) e o Ferreiro livre pega o próximo card aprovado dele (26/09)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import nubi_web as w  # noqa: E402


class Repo:
    def __init__(self, tarefas=(), comandos=(), resumos=None):
        self.tarefas, self.comandos, self.resumos = list(tarefas), list(comandos), dict(resumos or {})
        self.eventos, self.patches = [], []

    def _eq(self, v):
        return f"eq.{v}"

    def _req(self, m, t, q=None, corpo=None, prefer=None):
        q = q or {}
        if t == "reuniao_tarefas" and m == "POST":
            for c in corpo:
                c["id"] = 100 + len(self.tarefas)
                self.tarefas.append(c)
            return corpo
        if t == "reuniao_tarefas" and m == "GET":
            xs = self.tarefas
            for k in ("titulo", "status", "responsavel", "proposto_por"):
                if k in q and q[k].startswith("eq."):
                    xs = [x for x in xs if x.get(k) == q[k][3:]]
                if k in q and q[k].startswith("neq."):
                    xs = [x for x in xs if x.get(k) != q[k][4:]]
            return xs
        if t == "reuniao_tarefas" and m == "PATCH":
            self.patches.append((q, corpo))
        if t == "mac_comandos":
            if m == "POST":
                self.comandos += corpo
            return [c for c in self.comandos if c.get("status") in ("pendente", "rodando")]
        if t == "ia_resumos":
            if m == "POST":
                self.resumos.update({c["chave"]: c for c in corpo})
            return [self.resumos[q["chave"][3:]]] if m == "GET" and q.get("chave", "")[3:] in self.resumos else []
        if t == "tarefa_eventos" and m == "POST":
            self.eventos += corpo
        return []


def test_astra_cria_cards_e_confirma_com_numero():
    r = Repo()
    resp = ('Vou organizar o quadro.\n'
            'CRIAR_CARD: {"titulo": "Painel do card maior", "escopo": "720 px", "arquivo": "index.html", "teste": "celular", '
            '"aceite": "sem cortes", "prioridade": "alta", "risco": "baixo", "executor": "ferreiro"}\n'
            'CRIAR_CARD: {"titulo": "Apagar cards velhos", "escopo": "limpar", "risco": "alto", "executor": "chefe"}')
    out = w.criar_cards_do_agente(r, "astra", resp)
    assert "CRIAR_CARD" not in out and "✅ **Card #100 criado**: Painel do card maior · executor: Ferreiro · já na fila" in out
    assert "#101" in out and "esperando sua aprovação" in out
    a, b = r.tarefas
    assert a["status"] == "aprovada" and a["responsavel"] == "claude_mac" and a["proposto_por"] == "Astra (design)"
    assert "## Escopo\n720 px" in a["descricao"] and "## Critério de aceite\nsem cortes" in a["descricao"]
    assert b["status"] == "proposta" and b["aguardando"] and b["responsavel"] == "claude_code"
    out2 = w.criar_cards_do_agente(r, "astra", 'CRIAR_CARD: {"titulo": "Painel do card maior"}')
    assert "não dupliquei" in out2 and len(r.tarefas) == 2


def test_limite_por_dia_e_json_quebrado():
    r = Repo(tarefas=[{"id": i, "titulo": f"t{i}", "proposto_por": "Astra (design)", "status": "aprovada"} for i in range(w.CARDS_POR_DIA)])
    assert "limite de" in w.criar_cards_do_agente(r, "astra", 'CRIAR_CARD: {"titulo": "mais um"}')
    assert "não entendi" in w.criar_cards_do_agente(Repo(), "astra", "CRIAR_CARD: {quebrado")


def test_ferreiro_livre_pega_o_proximo():
    r = Repo(tarefas=[{"id": 91, "titulo": "Detalhe do card", "status": "aprovada", "responsavel": "claude_mac", "prioridade": "alta"},
                      {"id": 89, "titulo": "🩺 URGENTE fila", "status": "aprovada", "responsavel": "claude_mac", "prioridade": "alta"},
                      {"id": 77, "titulo": "ML", "status": "aprovada", "responsavel": "claude_mac", "aguardando": "Bruno"},
                      {"id": 5, "titulo": "alto", "status": "aprovada", "responsavel": "claude_mac", "risco": "alto"}])
    assert w.ferreiro_proximo(r) == "Ferreiro pegou o card #89"                      # 🩺 primeiro
    assert r.comandos[0]["comando"] == "programar_card" and r.comandos[0]["arg"] == "89"
    assert r.patches[0][1]["status"] == "em_desenvolvimento"
    assert w.ferreiro_proximo(r) is None                                              # espera 5 min entre vezes
    r.resumos.clear()
    assert "clone do projeto no Mac está em uso" in w.ferreiro_proximo(r)


def test_astra_programa_os_cards_dele_primeiro():
    r = Repo(tarefas=[{"id": 90, "titulo": "Quadro: executor", "status": "aprovada", "responsavel": "astra", "prioridade": "alta"},
                      {"id": 95, "titulo": "Erro técnico", "status": "aprovada", "responsavel": "claude_mac", "prioridade": "alta"}])
    assert w.ferreiro_proximo(r, quem="astra") == "Astra pegou o card #90"
    assert r.comandos[0]["comando"] == "programar_astra" and r.comandos[0]["arg"] == "90"
    assert "Astra livre" in r.eventos[0]["texto"]
    assert "espera" in w.ferreiro_proximo(r)                                          # um de cada vez no clone do Mac
    out = w.criar_cards_do_agente(Repo(), "astra", 'CRIAR_CARD: {"titulo": "Botões maiores no celular", "risco": "baixo"}')
    assert "executor: Astra (eu mesmo)" in out


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
