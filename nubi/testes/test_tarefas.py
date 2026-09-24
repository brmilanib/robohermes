# -*- coding: utf-8 -*-
"""
Testes das tarefas aprovadas na Sala (rodar: python3 testes/test_tarefas.py, na pasta nubi).
Sem rede e sem banco: as APIs e o Supabase são simulados.
"""
import io
import json
import os
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.update(OPENAI_API_KEY="x", ANTHROPIC_API_KEY="x")

import auditoria  # noqa: E402
import ia  # noqa: E402

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["categoria", "confianca"],
          "properties": {"categoria": {"type": "string", "enum": ["Árabe", "Designer"]},
                         "confianca": {"type": "string", "enum": ["alta", "baixa"]}}}


def test_12_estruturado_cai_no_claude_e_rejeita_fora_do_schema():
    chamadas = []

    def post(url, corpo, cab, timeout=90):
        chamadas.append(url.split("/")[2])
        if "openai" in url:
            raise urllib.error.HTTPError(url, 500, "fora", {}, io.BytesIO(b"erro"))
        txt = json.dumps({"categoria": "Árabe", "confianca": "alta"}) if len(chamadas) > 2 else json.dumps({"categoria": "Nicho"})
        return {"content": [{"type": "text", "text": txt}], "stop_reason": "end_turn"}
    ia._post_json = post
    j, qual = ia.perguntar_estruturado("classifique", SCHEMA)
    assert qual == "claude" and j == {"categoria": "Árabe", "confianca": "alta"}, (j, qual)
    assert chamadas == ["api.openai.com", "api.anthropic.com", "api.anthropic.com"], chamadas   # 1º JSON do Claude recusado
    assert ia.erros_schema({"categoria": "Nicho"}, SCHEMA)


def test_13_lote_lista_as_falhas():
    linhas = [{"custom_id": "a", "response": {"status_code": 200, "body": {"output": [{"type": "message", "content": [{"text": "{}"}]}]}}},
              {"custom_id": "b", "response": {"status_code": 500, "body": {}}},
              {"custom_id": "c", "error": {"message": "timeout"}}]
    ia._openai = lambda *a, **k: "\n".join(json.dumps(x) for x in linhas).encode()
    falhas = []
    ok = ia.lote_resultados("f1", falhas)
    assert set(ok) == {"a"} and [f["id"] for f in falhas] == ["b", "c"], (ok, falhas)


class Repo:
    def __init__(self, tabelas):
        self.t = tabelas

    def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
        rows = self.t.get(tab, [])
        if tab == "coletor_pedidos":
            return [r for r in rows if r.get("atendido_em") is None]
        if tab == "coletor_execucoes":
            return [r for r in rows if r.get("em_andamento")]
        if tab == "vend_vendas_dia" and params and params.get("limit") == 1:
            return [{"data": max(r["data"] for r in self.t["serie"])}]
        return rows

    def _todos(self, tab, params=None, metodo="GET", corpo=None):
        if tab == "rpc/vend_dia_serie":
            return self.t["serie"]
        if tab == "vend_grupo_dia":
            return self.t.get("grupo", [])
        return []


def _serie():
    from datetime import date, timedelta
    fim = date(2026, 9, 22)
    s = []
    for i in range(10):
        d = (fim - timedelta(days=i)).isoformat()
        s.append({"vendedor": "AUMA", "data": d, "v": 1000})
        if d != "2026-09-22":
            s.append({"vendedor": "SIENO", "data": d, "v": 2000})
    grupo = [{"vendedor": "SIENO", "data": "2026-09-22", "v": 1800}, {"vendedor": "AUMA", "data": "2026-09-22", "v": 1000},
             {"vendedor": "NOVO", "data": "2026-09-22", "v": 500}]
    return s, grupo


def test_6_pedido_pendente_vira_alerta_sem_pedido_vira_erro():
    s, g = _serie()
    sem = auditoria.conferencias(Repo({"serie": s, "grupo": g}))
    com = auditoria.conferencias(Repo({"serie": s, "grupo": g, "coletor_pedidos": [{"id": 1, "motivo": "retroativa", "atendido_em": None}]}))
    f = lambda ach: next(a for a in ach if a["titulo"].startswith("SIENO: 1 dia"))
    assert f(sem)["nivel"] == "erro", f(sem)
    assert f(com)["nivel"] == "alerta" and "coleta em andamento" in f(com)["titulo"], f(com)


def test_5_grupo_x_export_tres_casos():
    s, g = _serie()
    ach = auditoria.conferencias(Repo({"serie": s, "grupo": g}))
    tit = [a["titulo"] for a in ach]
    sieno = next(a for a in ach if a["titulo"].startswith("SIENO: 1 dia"))
    assert "falha de download" in sieno["detalhe"], sieno                          # no grupo com vendas, sem export
    assert any(t.startswith("NOVO: no grupo com vendas mas sem export") for t in tit), tit
    assert not any("ausente da tabela do grupo" in t for t in tit), tit
    g2 = [x for x in g if x["vendedor"] != "AUMA"]
    ach2 = auditoria.conferencias(Repo({"serie": s, "grupo": g2}))
    assert any(a["titulo"] == "AUMA: ausente da tabela do grupo" for a in ach2), [a["titulo"] for a in ach2]


def test_7_regras_da_juncao():
    r = auditoria.regras_juncao("Perfume Good Girl Edp 80ml Carolina Herrera", "Perfume Good Girl Blush Edp 80ml")
    assert "volume ✅" in r and "concentração ✅" in r and "nome ❌" in r, r


def test_17_uso_sem_numero_fica_nulo():
    assert ia._tokens({"choices": []}) == (None, None)
    assert ia._tokens({"usage": {"input_tokens": 10, "output_tokens": 3, "cache_read_input_tokens": 5}}) == (15, 3)


def test_aprovacao_automatica_por_risco():
    import reuniao
    reuniao.ia.tem = lambda q: q == "claude"
    decisao = {"resposta": "ok", "tarefas": [
        {"titulo": "Ajustar texto do alerta", "descricao": "trocar a frase", "status": "aprovada", "risco": "baixo"},
        {"titulo": "Mudar a senha do agente", "descricao": "trocar a senha", "status": "aprovada", "risco": "baixo"},
        {"titulo": "Reescrever o cálculo de comissão", "descricao": "regra nova", "status": "aprovada", "risco": "alto",
         "pergunta": "Posso mudar a regra?"}],
        "atualizar": [{"id": 50, "status": "aprovada", "risco": "medio", "nota": "ok"},
                      {"id": 51, "status": "aprovada", "risco": "baixo", "nota": "apagar dados antigos"}]}
    reuniao._decidir = lambda *a, **k: (decisao, "claude")
    reuniao.participantes = lambda texto: []

    class R:
        def __init__(s):
            s.t = {"reuniao_mensagens": [], "reuniao_tarefas": [
                {"id": 50, "titulo": "Tela de alertas mais limpa", "descricao": "cards", "status": "proposta", "prioridade": "media"},
                {"id": 51, "titulo": "Limpeza", "descricao": "apagar dados antigos de vend_vendas_dia", "status": "proposta", "prioridade": "media"}]}
            s.patch = {}

        def _req(s, m, tab, f=None, corpo=None, prefer=None):
            if m == "POST":
                for r in corpo:
                    r["id"] = 100 + len(s.t[tab])
                    s.t[tab].append(r)
                return corpo
            if m == "PATCH":
                s.patch[int(f["id"][3:])] = corpo

        def _todos(s, tab, p):
            return s.t[tab]
    r = R()
    reuniao.rodada(r, "teste")
    novas = {t["titulo"]: t for t in r.t["reuniao_tarefas"] if t.get("id", 0) >= 100}
    assert novas["Ajustar texto do alerta"]["status"] == "aprovada", novas
    assert novas["Mudar a senha do agente"]["status"] == "proposta" and novas["Mudar a senha do agente"]["aguardando"], novas
    assert novas["Reescrever o cálculo de comissão"]["aguardando"] == "Posso mudar a regra?", novas
    assert r.patch[50]["status"] == "aprovada" and "automático" in r.patch[50]["decidido_por"], r.patch
    assert "status" not in r.patch[51] and r.patch[51]["aguardando"], r.patch


if __name__ == "__main__":
    falhou = 0
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            try:
                f()
                print("ok  ", nome)
            except Exception as e:  # noqa: BLE001
                falhou += 1
                print("FALHOU", nome, repr(e)[:400])
    sys.exit(1 if falhou else 0)
