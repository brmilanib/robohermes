"""Card #89: agente livre assume na hora os cards aprovados dele (aprovar, terminar, evento duplicado, executor indisponível)."""
import copy
import fnmatch
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import nubi_web as w  # noqa: E402

w.indexar_aos_poucos = lambda repo: None


def _agora(min_=0):
    return (datetime.now(timezone.utc) + timedelta(minutes=min_)).isoformat()


def _casa(x, k, v):
    v, val = str(v), x.get(k)
    if v == "is.null":
        return val is None
    op, arg = v.split(".", 1)
    if op == "eq":
        return str(val) == arg
    if op == "neq":
        return str(val) != arg
    if op == "in":
        return str(val) in arg[1:-1].split(",")
    if op == "gte":
        return str(val or "") >= arg
    if op == "like":
        return fnmatch.fnmatchcase(str(val or ""), arg)
    return True


class Repo:
    """Banco falso com os filtros do PostgREST que a fila usa (PATCH devolve as linhas mudadas com return=representation)."""

    def __init__(self, tarefas=(), online=True):
        self.t = {"reuniao_tarefas": [dict(x) for x in tarefas], "tarefa_eventos": [], "mac_comandos": [], "ia_resumos": [],
                  "mac_estado": [{"id": 1, "visto_em": _agora(0 if online else -30)}], "reuniao_mensagens": []}
        self.foto = None                                   # corrida: os dois processos leram antes de qualquer um gravar

    def _eq(self, v):
        return f"eq.{v}"

    def _req(self, m, tab, q=None, corpo=None, prefer=None):
        q, rows = q or {}, self.t.setdefault(tab, [])
        filtros = {k: v for k, v in q.items() if k not in ("select", "order", "limit", "or")}
        if m == "POST":
            for c in corpo:
                if tab in ("ia_resumos", "mac_estado"):
                    chave = "chave" if tab == "ia_resumos" else "id"
                    rows[:] = [x for x in rows if x.get(chave) != c.get(chave)]
                if tab in ("mac_comandos", "tarefa_eventos"):
                    c = dict(c, id=len(rows) + 1)
                rows.append(c)
            return copy.deepcopy(corpo)
        if m == "GET" and self.foto is not None and tab in ("mac_comandos", "reuniao_tarefas", "ia_resumos"):
            rows = self.foto[tab]
        alvo = [x for x in rows if all(_casa(x, k, v) for k, v in filtros.items())]
        if m == "PATCH":
            for x in alvo:
                x.update(corpo)
            return copy.deepcopy(alvo) if prefer and "representation" in prefer else None
        alvo = sorted(alvo, key=lambda x: x.get("id") or 0, reverse=str(q.get("order", "")).endswith(".desc"))
        return copy.deepcopy(alvo[:q["limit"]] if q.get("limit") else alvo)

    def card(self, tid):
        return next(x for x in self.t["reuniao_tarefas"] if x["id"] == tid)

    def textos(self, tid):
        return [e["texto"] for e in self.t["tarefa_eventos"] if e["tarefa_id"] == tid]

    def cmds(self, comando="programar_card"):
        return [c for c in self.t["mac_comandos"] if c["comando"] == comando]


def _card(tid, **k):
    return dict({"id": tid, "titulo": f"card {tid}", "status": "aprovada", "responsavel": "claude_code", "prioridade": "media",
                 "risco": "medio", "aguardando": None}, **k)


def test_aprovar_com_ferreiro_livre_comeca_na_hora():
    r = Repo([_card(84)])
    out = w.assumir_aprovados(r, 84)
    assert "Ferreiro pegou o card #84" in out, out
    assert r.card(84)["status"] == "em_desenvolvimento" and r.card(84)["responsavel"] == "claude_mac"
    assert [c["arg"] for c in r.cmds()] == ["84"]


def test_ocupado_que_termina_pega_o_proximo_no_mesmo_sinal():
    r = Repo([_card(84), _card(85), _card(86, titulo="🩺 URGENTE coletor", prioridade="urgente")])
    r.t["mac_comandos"].append({"id": 1, "comando": "programar_card", "arg": "80", "status": "rodando", "tarefa_id": 80})
    w.assumir_aprovados(r, 85)
    assert r.card(85)["status"] == "aprovada" and "Aguardando: Ferreiro espera" in r.textos(85)[-1]   # ocupado: diz por quê
    corpo = json.dumps({"info": {}, "saidas": [{"id": 1, "status": "ok", "saida": "feito"}]}).encode()
    w.rota_mac(r, "POST", "mac_tick", {}, corpo, "tok")
    assert r.card(86)["status"] == "em_desenvolvimento" and r.cmds()[-1]["arg"] == "86"             # 🩺 primeiro, na hora
    assert r.cmds()[-1]["status"] == "rodando"                                                    # já foi para o Mac
    assert w.ferreiro_proximo(r, a_cada_min=0) == "Ferreiro espera (o clone do projeto no Mac está em uso)"


def test_evento_duplicado_so_um_pega():
    r = Repo([_card(87)])
    r.foto = copy.deepcopy(r.t)                           # os dois viram o card livre e o Mac sem comando
    a = w.ferreiro_proximo(r, a_cada_min=0)
    b = w.ferreiro_proximo(r, a_cada_min=0)
    assert [a, b].count("Ferreiro pegou o card #87") == 1 and len(r.cmds()) == 1
    assert sum("livre: peguei" in x for x in r.textos(87)) == 1


def test_executor_indisponivel_mostra_o_motivo():
    r = Repo([_card(88, responsavel="claude_mac")], online=False)
    w.assumir_aprovados(r, 88)
    assert "Mac mini está sem sinal" in r.textos(88)[-1] and not r.cmds()
    w.assumir_aprovados(r, 88)
    assert len(r.textos(88)) == 1                                                                 # sem repetir o aviso
    # Mac voltou, mas o Ferreiro devolveu um card sem chave: não gasta a fila inteira, espera 1 h com o motivo no card
    r = Repo([_card(88, responsavel="claude_mac"), _card(90, responsavel="claude_mac")])
    r.t["tarefa_eventos"].append({"id": 1, "tarefa_id": 90, "autor": "claude_mac", "tipo": "erro_teste", "criado_em": _agora(),
                                  "texto": "⏸ Ferreiro indisponível: sem a chave da Anthropic. O card volta para a fila."})
    w.assumir_aprovados(r, 88)
    assert r.card(88)["status"] == "aprovada" and not r.cmds()
    assert "Ferreiro indisponível" in r.textos(88)[-1] and "sem a chave" in r.textos(88)[-1]


def test_risco_alto_e_tentativas_nao_andam_sozinhos():
    r = Repo([_card(77, risco="alto")])
    w.assumir_aprovados(r, 77)
    assert r.card(77)["status"] == "aprovada" and "risco alto" in r.textos(77)[-1] and not r.cmds()
    r = Repo([_card(81)])                                 # card do Chefe que o Ferreiro já pegou 2 vezes: fica com o Chefe
    for i in range(w.FERREIRO_TENTATIVAS):
        r.t["tarefa_eventos"].append({"id": i + 1, "tarefa_id": 81, "autor": "claude_mac", "tipo": "passo", "criado_em": _agora(-200),
                                      "texto": "🔨 Ferreiro livre: peguei este card agora (fila automática)."})
    assert w.ferreiro_proximo(r, a_cada_min=0) is None and r.card(81)["status"] == "aprovada"


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
