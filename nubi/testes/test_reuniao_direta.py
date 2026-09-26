# -*- coding: utf-8 -*-
"""Conversa direta na Sala (card #64, fase 2): lista de conversas e envio para um agente só, sem rede e sem banco."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.update(OPENAI_API_KEY="x", ANTHROPIC_API_KEY="x")

import agentes  # noqa: E402
import ia  # noqa: E402
import nubi_web  # noqa: E402


class RepoSala:
    def __init__(s, msgs=None):
        s.t = {"reuniao_mensagens": list(msgs or [])}

    def _req(s, m, tab, params=None, corpo=None, prefer=None):
        if m == "POST":
            linhas = []
            for r in corpo:
                r = dict(r, id=len(s.t.setdefault(tab, [])) + 1)
                s.t[tab].append(r)
                linhas.append(r)
            return linhas if prefer and "representation" in prefer else None
        return s._todos(tab, params)

    def _todos(s, tab, params=None, metodo="GET", corpo=None):
        rows = list(s.t.get(tab, []))
        p = params or {}
        if "id" in p and p["id"].startswith("gt."):
            lim = int(p["id"][3:])
            rows = [r for r in rows if r.get("id", 0) > lim]
        if p.get("or") == "(meta.is.null,meta->>conversa.neq.direta)":
            rows = [r for r in rows if not r.get("meta") or r["meta"].get("conversa") != "direta"]
        if p.get("meta->>conversa") == "eq.direta":
            rows = [r for r in rows if r.get("meta") and r["meta"].get("conversa") == "direta"]
        if "meta->>agente" in p:
            ag = p["meta->>agente"][3:]
            rows = [r for r in rows if r.get("meta") and r["meta"].get("agente") == ag]
        if p.get("order") == "id.desc":
            rows = sorted(rows, key=lambda r: r.get("id", 0), reverse=True)
        if p.get("limit"):
            rows = rows[:p["limit"]]
        return rows

    def _eq(s, v):
        return f"eq.{v}"


def _corpo(d):
    return json.dumps(d).encode()


def test_reuniao_filtra_sala_x_direta():
    msgs = [{"id": 1, "autor": "voce", "texto": "oi geral", "meta": None},
            {"id": 2, "autor": "voce", "texto": "oi chatgpt", "meta": {"conversa": "direta", "agente": "chatgpt"}},
            {"id": 3, "autor": "ChatGPT", "texto": "oi!", "meta": {"conversa": "direta", "agente": "chatgpt"}},
            {"id": 4, "autor": "Claude", "texto": "bom dia", "meta": {"decisao": True}}]
    r = RepoSala(msgs)
    nubi_web.RepoSupabase = lambda token: r
    nubi_web.ligar_registro_uso = lambda *a, **k: None
    ia.tem = lambda q: False
    status, ctype, body, _ = nubi_web.atender("GET", "reuniao", {}, None, "t")
    sala = json.loads(body)["mensagens"]
    assert [m["id"] for m in sala] == [1, 4], sala               # sem meta ou meta sem conversa=direta

    status, ctype, body, _ = nubi_web.atender("GET", "reuniao", {"conversa": "chatgpt"}, None, "t")
    direta = json.loads(body)["mensagens"]
    assert [m["id"] for m in direta] == [2, 3], direta


def test_reuniao_conversas_traz_a_ultima_mensagem_de_cada_uma():
    msgs = [{"id": 1, "autor": "voce", "texto": "oi geral", "meta": None},
            {"id": 2, "autor": "voce", "texto": "primeira pergunta", "meta": {"conversa": "direta", "agente": "deepseek"}},
            {"id": 3, "autor": "DeepSeek", "texto": "resposta mais nova\nsegunda linha", "meta": {"conversa": "direta", "agente": "deepseek"}}]
    r = RepoSala(msgs)
    nubi_web.RepoSupabase = lambda token: r
    nubi_web.ligar_registro_uso = lambda *a, **k: None
    status, ctype, body, _ = nubi_web.atender("GET", "reuniao_conversas", {}, None, "t")
    conversas = json.loads(body)["conversas"]
    assert conversas["sala"]["texto"] == "oi geral", conversas["sala"]
    assert conversas["deepseek"]["texto"] == "resposta mais nova\nsegunda linha", conversas["deepseek"]   # a última, não a 1ª
    assert conversas["hermes"] is None                                                                    # sem mensagens ainda


def test_enviar_direto_chama_so_o_agente_escolhido():
    r = RepoSala()
    nubi_web.RepoSupabase = lambda token: r
    nubi_web.ligar_registro_uso = lambda *a, **k: None
    ia.tem = lambda q: True
    chamado = {}

    def _perguntar(chave, texto, max_tokens=800):
        chamado[chave] = texto
        return f"resposta de {chave}"
    agentes.perguntar = _perguntar
    status, ctype, body, _ = nubi_web.atender("POST", "reuniao_enviar_direto", {}, _corpo({"agente": "deepseek", "texto": "confere esse número"}), "t")
    assert json.loads(body) == {"ok": True}
    assert chamado == {"deepseek": "confere esse número"}
    autores = [m["autor"] for m in r.t["reuniao_mensagens"]]
    assert autores == ["voce", "DeepSeek"], r.t["reuniao_mensagens"]
    assert r.t["reuniao_mensagens"][1]["texto"] == "resposta de deepseek"
    metas = {m["meta"]["agente"] for m in r.t["reuniao_mensagens"]}
    assert metas == {"deepseek"}


def test_enviar_direto_ao_claude_usa_ia_perguntar():
    r = RepoSala()
    nubi_web.RepoSupabase = lambda token: r
    nubi_web.ligar_registro_uso = lambda *a, **k: None
    ia.tem = lambda q: True
    ia.perguntar = lambda pedido, **kw: ("resposta do coordenador", None, "claude")
    nubi_web.atender("POST", "reuniao_enviar_direto", {}, _corpo({"agente": "claude", "texto": "e aí?"}), "t")
    assert [m["autor"] for m in r.t["reuniao_mensagens"]] == ["voce", "Claude"]


def test_enviar_direto_sem_resposta_nao_inventa():
    r = RepoSala()
    nubi_web.RepoSupabase = lambda token: r
    nubi_web.ligar_registro_uso = lambda *a, **k: None
    ia.tem = lambda q: True
    agentes.perguntar = lambda chave, texto, max_tokens=800: (_ for _ in ()).throw(RuntimeError("timeout"))
    nubi_web.atender("POST", "reuniao_enviar_direto", {}, _corpo({"agente": "gptoss", "texto": "e aí?"}), "t")
    autores_textos = [(m["autor"], m["texto"]) for m in r.t["reuniao_mensagens"]]
    assert autores_textos[1] == ("sistema", "sem resposta do agente"), autores_textos


def test_enviar_direto_hermes_e_ferreiro_avisam_sem_chamar_ia():
    r = RepoSala()
    nubi_web.RepoSupabase = lambda token: r
    nubi_web.ligar_registro_uso = lambda *a, **k: None
    ia.tem = lambda q: False   # nenhuma IA configurada: se tentasse chamar, cairia num ErroNuvem

    nubi_web.atender("POST", "reuniao_enviar_direto", {}, _corpo({"agente": "hermes", "texto": "como foi a coleta?"}), "t")
    nubi_web.atender("POST", "reuniao_enviar_direto", {}, _corpo({"agente": "claude_mac", "texto": "conserta isso"}), "t")
    nubi_web.atender("POST", "reuniao_enviar_direto", {}, _corpo({"agente": "copilot", "texto": "muda essa tela"}), "t")
    autores = [m["autor"] for m in r.t["reuniao_mensagens"]]
    assert autores == ["voce", "sistema"] * 3, autores
    assert "Mac" in r.t["reuniao_mensagens"][1]["texto"]
    assert "próxima fase" in r.t["reuniao_mensagens"][3]["texto"]
    assert "próxima fase" in r.t["reuniao_mensagens"][5]["texto"]


def test_enviar_direto_agente_invalido_ou_texto_vazio():
    # atender() captura ErroNuvem e devolve {"erro": ...} com o status certo, sem deixar a exceção subir
    r = RepoSala()
    nubi_web.RepoSupabase = lambda token: r
    nubi_web.ligar_registro_uso = lambda *a, **k: None
    status, ctype, body, _ = nubi_web.atender("POST", "reuniao_enviar_direto", {}, _corpo({"agente": "inventado", "texto": "oi"}), "t")
    assert status == 400 and "inválido" in json.loads(body)["erro"], (status, body)
    status, ctype, body, _ = nubi_web.atender("POST", "reuniao_enviar_direto", {}, _corpo({"agente": "claude", "texto": "  "}), "t")
    assert status == 400 and "mensagem" in json.loads(body)["erro"].lower(), (status, body)
    assert r.t["reuniao_mensagens"] == []           # nada gravado nos dois casos recusados


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
