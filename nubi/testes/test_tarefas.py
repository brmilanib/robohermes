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
import nubi_web  # noqa: E402

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


def _instantaneo(snap):
    return {"auditorias": [{"conferencias": [{"nivel": "info", "area": "categoria",
            "titulo": "Instantâneo de categorias em conflito", "detalhe": json.dumps(snap)}]}]}


def test_66_categoria_em_conflito_muda_vira_alerta():
    # JEANNEARTHES está em conflito (Designer x Importados low ticket) e classifica hoje para "Designer"
    # (test_58); ontem o instantâneo dizia "Importados low ticket" -> tem que virar alerta.
    s, g = _serie()
    r = Repo({"serie": s, "grupo": g, **_instantaneo({"JEANNEARTHES": "Importados low ticket"})})
    ach = auditoria.conferencias(r)
    alerta = next(a for a in ach if a["area"] == "categoria" and a["nivel"] == "alerta")
    assert alerta["titulo"] == "JEANNEARTHES: categoria mudou de Importados low ticket para Designer", alerta
    # o instantâneo de hoje sempre é gravado, pra amanhã comparar
    info = next(a for a in ach if a["area"] == "categoria" and a["nivel"] == "info")
    assert json.loads(info["detalhe"])["JEANNEARTHES"] == "Designer", info


def test_66_categoria_sem_mudanca_nao_gera_alerta():
    s, g = _serie()
    r = Repo({"serie": s, "grupo": g, **_instantaneo({"JEANNEARTHES": "Designer"})})
    ach = auditoria.conferencias(r)
    assert not [a for a in ach if a["area"] == "categoria" and a["nivel"] == "alerta"], ach


def test_66_sem_instantaneo_de_ontem_nao_inventa_alerta():
    s, g = _serie()
    ach = auditoria.conferencias(Repo({"serie": s, "grupo": g}))   # sem "auditorias" nenhuma no mock (1º dia)
    assert not [a for a in ach if a["area"] == "categoria" and a["nivel"] == "alerta"], ach
    assert any(a["area"] == "categoria" and a["nivel"] == "info" for a in ach), ach


def test_17_uso_sem_numero_fica_nulo():
    assert ia._tokens({"choices": []}) == (None, None, None, None)
    # input_tokens da Anthropic já vem SEM os tokens de cache: nunca somar aqui (card #21), senão cobra 2x no custo
    assert ia._tokens({"usage": {"input_tokens": 10, "output_tokens": 3, "cache_read_input_tokens": 5}}) == (10, 5, 0, 3)
    assert ia._tokens({"usage": {"input_tokens": 10, "output_tokens": 3}}) == (10, 0, 0, 3)   # sem cache: 0, não None


class RepoPrecos:
    def __init__(s, precos):
        s.precos = precos
        s.usos = []

    def _req(s, m, tab, params=None, corpo=None, prefer=None):
        if tab == "ia_precos" and m == "GET":
            return s.precos
        if tab == "agentes_uso" and m == "PATCH":
            s.usos.append(corpo)
            return []
        return []

    def _todos(s, tab, params, metodo="GET", corpo=None):
        return s._req(metodo, tab, params, corpo) or []

    def _eq(s, v):
        return f"eq.{v}"


def test_21_custo_com_cache_nao_cobra_duas_vezes():
    # claude-opus-5-5: US$ 4/1M entrada, US$ 20/1M saída (ia_precos); leitura de cache 0,1x, criação 1,25x (card #21)
    r = RepoPrecos([{"modelo": "claude-opus-5-5", "entrada": "4", "saida": "20"}])
    nubi_web.ligar_registro_uso(r, "teste")
    ia.USO["gravar"]("fim", {"id": 1, "ok": True, "modelo": "claude-opus-5-5", "tokens_in": 100,
                             "cache_read_tokens": 1000, "cache_creation_tokens": 200, "tokens_out": 50})
    esperado = round((100 * 4 + 1000 * 4 * 0.1 + 200 * 4 * 1.25 + 50 * 20) / 1e6, 6)
    assert r.usos[-1]["custo_usd"] == esperado, r.usos[-1]

    # usage sem campos de cache (tratados como 0, não None)
    r2 = RepoPrecos([{"modelo": "claude-opus-5-5", "entrada": "4", "saida": "20"}])
    nubi_web.ligar_registro_uso(r2, "teste")
    ia.USO["gravar"]("fim", {"id": 1, "ok": True, "modelo": "claude-opus-5-5", "tokens_in": 100,
                             "cache_read_tokens": 0, "cache_creation_tokens": 0, "tokens_out": 50})
    assert r2.usos[-1]["custo_usd"] == round((100 * 4 + 50 * 20) / 1e6, 6), r2.usos[-1]

    # usage ausente (tokens_in None): custo "sem dados", nunca 0
    r3 = RepoPrecos([{"modelo": "claude-opus-5-5", "entrada": "4", "saida": "20"}])
    nubi_web.ligar_registro_uso(r3, "teste")
    ia.USO["gravar"]("fim", {"id": 1, "ok": True, "modelo": "claude-opus-5-5", "tokens_in": None, "tokens_out": None})
    assert "custo_usd" not in r3.usos[-1], r3.usos[-1]

    # modelo sem preço cadastrado: sem custo, nunca 0 nem preço de outro modelo
    r4 = RepoPrecos([{"modelo": "gpt-4.1", "entrada": None, "saida": None}])
    nubi_web.ligar_registro_uso(r4, "teste")
    ia.USO["gravar"]("fim", {"id": 1, "ok": True, "modelo": "gpt-4.1", "tokens_in": 100, "tokens_out": 50})
    assert "custo_usd" not in r4.usos[-1], r4.usos[-1]


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


class RepoDuvida:
    def __init__(s, mensagens_hoje=0):
        s.t = {"reuniao_mensagens": [{"id": i} for i in range(mensagens_hoje)], "tarefa_eventos": [], "reuniao_tarefas": []}
        s.gets = []

    def _req(s, m, tab, params=None, corpo=None, prefer=None):
        if m == "GET":
            s.gets.append((tab, params))
            return s.t.get(tab, [])
        if m == "POST":
            linhas = [dict(r, id=len(s.t.setdefault(tab, [])) + i + 1) for i, r in enumerate(corpo)]
            s.t.setdefault(tab, []).extend(linhas)
            return linhas if prefer and "representation" in prefer else None
        return None


def test_37_duvida_chama_especialista_e_fecha_no_card():
    import reuniao
    reuniao.ia.tem = lambda q: True
    reuniao.ia.perguntar = lambda pedido, **kw: ("Decisão do coordenador: use o Preço Médio.", None, "claude")
    reuniao.agentes.perguntar = lambda chave, texto, max_tokens=800, **k: f"Resposta do {chave}"

    r = RepoDuvida()
    decisao = reuniao.duvida(r, 5, "Qual a regra de cálculo do preço médio?", quem="claude_code")
    assert "Decisão do coordenador" in decisao, decisao
    tipos = [m["meta"]["tipo"] for m in r.t["reuniao_mensagens"]]
    assert tipos == ["duvida", "resposta_duvida", "decisao"], tipos
    assert r.t["reuniao_mensagens"][0]["meta"]["para"] == "deepseek", r.t["reuniao_mensagens"][0]
    passo = next(e for e in r.t["tarefa_eventos"] if e["tipo"] == "passo")
    assert passo["tarefa_id"] == 5 and "Dúvida" in passo["texto"] and "Decisão do coordenador" in passo["texto"], passo
    # a checagem do limite diário usa exatamente o filtro jsonb que o Supabase real entende
    tab, params = r.gets[0]
    assert tab == "reuniao_mensagens" and params["meta->>tipo"] == "eq.duvida" and params["criado_em"].startswith("gte."), params

    r2 = RepoDuvida(mensagens_hoje=reuniao.LIMITE_DUVIDAS_DIA)
    try:
        reuniao.duvida(r2, 5, "outra pergunta de código", quem="claude_code")
        assert False, "devia recusar por limite diário"
    except reuniao.ErroDuvida as e:
        assert "Limite" in str(e), e


def test_37b_especialista_por_assunto_e_hermes_assincrono():
    import reuniao
    assert reuniao._especialista("mudar o layout do celular") == "astra"
    assert reuniao._especialista("conferir o custo da consulta no banco") == "deepseek"
    assert reuniao._especialista("bug nessa função, corrigir o endpoint") == "chatgpt"
    assert reuniao._especialista("qual foi o histórico dessa decisão?") == "hermes"
    assert reuniao._especialista("oi", para="@hermes") == "hermes"

    reuniao.ia.tem = lambda q: True
    reuniao.ia.perguntar = lambda pedido, **kw: ("Decisão sem o Hermes: segue o combinado antes.", None, "claude")
    chamou_especialista = []
    reuniao.agentes.perguntar = lambda chave, texto, max_tokens=800, **k: chamou_especialista.append(chave) or "nunca deveria chamar"

    r = RepoDuvida()
    decisao = reuniao.duvida(r, 7, "Qual foi o histórico dessa decisão?", quem="claude_code")
    assert not chamou_especialista, "Hermes não pode ser chamado na hora (roda assíncrono no Mac)"
    assert "Decisão sem o Hermes" in decisao, decisao
    tipos = [m["meta"]["tipo"] for m in r.t["reuniao_mensagens"]]
    assert tipos == ["duvida", "decisao"], tipos    # sem resposta_duvida: ninguém respondeu na hora


def test_37c_fake_rest_filtra_jsonb_meta():
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servidor_teste")
    if caminho not in sys.path:
        sys.path.insert(0, caminho)
    import fake_rest
    hoje = "2026-09-25"
    linhas = [{"id": i, "meta": {"tipo": "duvida"}, "criado_em": f"{hoje}T10:00:00+00:00"} for i in range(20)]
    linhas += [{"id": 100, "meta": {"tipo": "decisao"}, "criado_em": f"{hoje}T11:00:00+00:00"},
               {"id": 101, "meta": {"tipo": "duvida"}, "criado_em": "2026-09-24T09:00:00+00:00"}]
    achadas = fake_rest.filtra(linhas, {"select": "id", "meta->>tipo": "eq.duvida", "criado_em": f"gte.{hoje}"})
    assert len(achadas) == 20, len(achadas)   # só as de hoje com tipo=duvida (não a de ontem nem a decisao)


class RepoCard:
    def __init__(s):
        s.eventos = []

    def _req(s, m, tab, params=None, corpo=None, prefer=None):
        if m == "GET":
            if tab == "reuniao_tarefas":
                return [{"id": 9, "status": "em_desenvolvimento", "responsavel": "claude_code", "titulo": "x", "descricao": "y", "notas": None}]
            if tab == "mac_estado":
                return [{"visto_em": None}]
            return []
        if m == "POST":
            s.eventos.extend(corpo)
            return corpo if prefer and "representation" in prefer else None
        return None

    def _eq(s, v):
        return f"eq.{v}"


def test_37d_falha_ao_abrir_duvida_nao_apaga_resposta_pronta():
    nubi_web.ia.perguntar_json = lambda *a, **k: (
        {"resposta": "Resposta pronta para o Bruno.", "comando": None, "duvida": "isso funciona mesmo?"}, None, "claude")
    nubi_web.reuniao.duvida = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("timeout de rede"))

    r = RepoCard()
    nubi_web.responder_card(r, 9)
    passo = next(e for e in r.eventos if e["tipo"] == "passo")
    assert "Resposta pronta para o Bruno." in passo["texto"], passo


class RepoPauta:
    def __init__(s, tabelas):
        s.t = {k: list(v) for k, v in tabelas.items()}

    def _req(s, m, tab, params=None, corpo=None, prefer=None):
        if m == "GET":
            import fake_rest
            return fake_rest.filtra(s.t.get(tab, []), params or {})
        return []

    def _todos(s, tab, params=None, metodo="GET", corpo=None):
        import fake_rest
        return fake_rest.filtra(s.t.get(tab, []), params or {})


def test_38_pauta_diaria_monta_4_secoes():
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servidor_teste")
    if caminho not in sys.path:
        sys.path.insert(0, caminho)

    ontem = "2026-09-24T11:00:00+00:00"
    hoje_iso = "2026-09-25T09:00:00+00:00"
    tabelas = {
        "reuniao_tarefas": [
            {"id": 1, "titulo": "Card concluído", "notas": "publicado", "status": "feita", "atualizado_em": hoje_iso, "prioridade": "alta", "aguardando": None},
            {"id": 2, "titulo": "Card travado", "status": "em_desenvolvimento", "aguardando": "Posso mudar a regra?", "atualizado_em": hoje_iso, "prioridade": "media", "notas": None},
            {"id": 3, "titulo": "Próximo da fila", "status": "aprovada", "aguardando": None, "prioridade": "alta", "atualizado_em": hoje_iso, "notas": None},
        ],
        "rotinas_execucoes": [], "coletor_execucoes": [], "auditorias": [], "rotinas": [],
        "reuniao_mensagens": [
            {"id": 10, "autor": "claude_code", "texto": "dúvida sem resposta", "meta": {"tipo": "duvida", "tarefa_id": 2}, "criado_em": hoje_iso},
        ],
        "agentes_uso": [{"agente": "deepseek", "custo_usd": 0.05, "inicio": hoje_iso}],
        "tarefa_eventos": [{"id": 20, "tarefa_id": 2, "tipo": "erro_teste", "criado_em": hoje_iso}],
    }
    r = RepoPauta(tabelas)
    texto = nubi_web._pauta_diaria(r, ontem)
    assert "## O que foi feito desde a última reunião" in texto and "Card concluído" in texto, texto
    assert "## O que travou" in texto and "Card travado" in texto and "dúvida sem resposta" in texto, texto
    assert "## O que dá para melhorar" in texto and "deepseek" in texto and "1 reprovação" in texto, texto
    assert "## Próximos da fila" in texto and "Próximo da fila" in texto, texto
    assert "Card travado" not in texto.split("## O que foi feito")[1].split("## O que travou")[0], texto


def test_43_ordem_fila_prioridade_depois_risco_depois_id():
    # ordem alfabética de prioridade (o bug antigo) seria alta, baixa, media, urgente — bem diferente da certa
    cards = [
        {"id": 101, "titulo": "Baixa/baixo", "prioridade": "baixa", "risco": "baixo"},
        {"id": 102, "titulo": "Urgente", "prioridade": "urgente", "risco": "medio"},
        {"id": 103, "titulo": "Alta/alto", "prioridade": "alta", "risco": "alto"},
        {"id": 104, "titulo": "Media/medio", "prioridade": "media", "risco": "medio"},
        {"id": 106, "titulo": "Media/baixo", "prioridade": "media", "risco": "baixo"},
    ]
    ordem = [t["id"] for t in sorted(cards, key=nubi_web.ordem_fila)]
    assert ordem == [102, 103, 106, 104, 101], ordem   # urgente > alta > média(risco baixo antes de médio) > baixa


def test_43_pauta_proximos_da_fila_usa_ordem_fila():
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servidor_teste")
    if caminho not in sys.path:
        sys.path.insert(0, caminho)
    tabelas = {
        "reuniao_tarefas": [
            {"id": 41, "titulo": "Card do Bruno", "status": "aprovada", "aguardando": None, "prioridade": "media", "risco": "baixo", "atualizado_em": None, "notas": None},
            {"id": 29, "titulo": "Card comum", "status": "aprovada", "aguardando": None, "prioridade": "media", "risco": "medio", "atualizado_em": None, "notas": None},
        ],
        "rotinas_execucoes": [], "coletor_execucoes": [], "auditorias": [], "rotinas": [],
        "reuniao_mensagens": [], "agentes_uso": [], "tarefa_eventos": [],
    }
    r = RepoPauta(tabelas)
    texto = nubi_web._pauta_diaria(r, "2026-09-24T11:00:00+00:00")
    fila = texto.split("## Próximos da fila")[1]
    assert fila.index("#41") < fila.index("#29"), fila   # mesma prioridade: risco baixo sai antes de médio


def test_71_previsao_min_card_execucao():
    from datetime import datetime, timedelta, timezone
    agora = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)

    def feita(dur, i):
        fim = agora - timedelta(hours=i + 1)
        ini = fim - timedelta(minutes=dur)
        return {"status": "feita", "responsavel": "claude_code", "iniciado_em": ini.isoformat(), "atualizado_em": fim.isoformat()}

    refs = nubi_web._duracoes_feitas_por_responsavel([feita(40, 0), feita(60, 1), feita(80, 2)])
    em_exec = {"status": "em_desenvolvimento", "responsavel": "claude_code", "iniciado_em": (agora - timedelta(minutes=20)).isoformat()}
    assert nubi_web._previsao_min_card_execucao(em_exec, refs, agora=agora) == 40

    refs_2 = nubi_web._duracoes_feitas_por_responsavel([feita(40, 0), feita(55, 1)])
    assert nubi_web._previsao_min_card_execucao(em_exec, refs_2, agora=agora) is None

    refs_curta = nubi_web._duracoes_feitas_por_responsavel([feita(10, 0), feita(10, 1), feita(10, 2)])
    em_exec_longo = {"status": "em_desenvolvimento", "responsavel": "claude_code", "iniciado_em": (agora - timedelta(minutes=30)).isoformat()}
    assert nubi_web._previsao_min_card_execucao(em_exec_longo, refs_curta, agora=agora) == 5


class RepoReuniao:
    def __init__(s):
        s.t = {"reuniao_mensagens": [], "reuniao_tarefas": []}

    def _req(s, m, tab, params=None, corpo=None, prefer=None):
        if m == "POST":
            linhas = [dict(x, id=len(s.t.setdefault(tab, [])) + i + 1) for i, x in enumerate(corpo)]
            s.t.setdefault(tab, []).extend(linhas)
            return linhas if prefer and "representation" in prefer else None
        return s.t.get(tab, [])

    def _todos(s, tab, params=None):
        return s.t.get(tab, [])


def test_38b_segunda_volta_reune_comentarios_antes_da_decisao():
    import reuniao
    reuniao.participantes = lambda texto: ["chatgpt", "deepseek"]

    def fake_perguntar(chave, texto, max_tokens=800, **k):
        if "Você já deu sua opinião" in texto:
            return f"(comentário 2ª volta de {chave})"
        return f"(opinião 1ª rodada de {chave})"
    reuniao.agentes.perguntar = fake_perguntar
    reuniao._decidir = lambda hist, tt, opinioes, extra: (
        {"resposta": "Decisão fechando a reunião.", "tarefas": [], "atualizar": []}, "claude")

    r = RepoReuniao()
    reuniao.rodada(r, "Reunião diária — pauta de hoje: ...", extra="", autor_extra="sistema", segunda_volta=True)

    msgs = r.t["reuniao_mensagens"]
    da_2volta = [m for m in msgs if (m.get("meta") or {}).get("segunda_volta")]
    assert {m["autor"] for m in da_2volta} == {"ChatGPT", "DeepSeek"}, da_2volta
    assert all("comentário 2ª volta" in m["texto"] for m in da_2volta), da_2volta
    assert any("(opinião 1ª rodada de chatgpt)" in m["texto"] for m in msgs if m["autor"] == "ChatGPT"), msgs
    assert any("Decisão fechando a reunião" in m["texto"] for m in msgs), msgs


def test_38c_sem_segunda_volta_nao_muda_o_fluxo_normal():
    import reuniao
    reuniao.participantes = lambda texto: ["chatgpt"]
    chamadas = []
    reuniao.agentes.perguntar = lambda chave, texto, max_tokens=800, **k: chamadas.append(texto) or "opinião única"
    reuniao._decidir = lambda hist, tt, opinioes, extra: (
        {"resposta": "Decisão.", "tarefas": [], "atualizar": []}, "claude")

    r = RepoReuniao()
    reuniao.rodada(r, "Mensagem do Bruno", extra="", autor_extra="voce")   # segunda_volta=False (padrão)
    assert len(chamadas) == 1, chamadas    # sem 2ª volta: só a opinião normal, nenhum comentário extra
    assert not any((m.get("meta") or {}).get("segunda_volta") for m in r.t["reuniao_mensagens"])


class RepoMac:
    def __init__(self):
        self.mac_comandos = []

    def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
        assert tab == "mac_comandos" and metodo == "POST"
        linhas = [dict(l, id=len(self.mac_comandos) + i + 1) for i, l in enumerate(corpo)]
        self.mac_comandos.extend(linhas)
        return linhas if prefer and "representation" in prefer else None


def test_11_terminal_recusa_comando_fora_da_lista_e_registra():
    r = RepoMac()
    try:
        nubi_web.rota_mac(r, "POST", "mac_pedir", {}, json.dumps({"comando": "rm -rf /", "arg": ""}).encode(), "tok")
        assert False, "devia recusar comando fora da lista"
    except nubi_web.ErroNuvem as e:
        assert "fora da lista" in str(e), e
    assert len(r.mac_comandos) == 1 and r.mac_comandos[0]["status"] == "recusado" and r.mac_comandos[0]["comando"] == "rm -rf /", r.mac_comandos

    r2 = RepoMac()
    try:
        nubi_web.rota_mac(r2, "POST", "mac_pedir", {}, json.dumps({"comando": "baixar_modelo", "arg": "modelo-malicioso"}).encode(), "tok")
        assert False, "devia recusar modelo fora da lista"
    except nubi_web.ErroNuvem as e:
        assert "Modelo fora da lista" in str(e), e
    assert r2.mac_comandos[0]["status"] == "recusado" and r2.mac_comandos[0]["comando"] == "baixar_modelo", r2.mac_comandos

    r3 = RepoMac()
    resp = nubi_web.rota_mac(r3, "POST", "mac_pedir", {}, json.dumps({"comando": "status", "arg": ""}).encode(), "tok")
    assert resp["ok"] and r3.mac_comandos[0]["status"] == "pendente", (resp, r3.mac_comandos)


def test_44_card_pronto_exige_os_4_itens():
    completo = ("Escopo: mudar a cor do botão.\nArquivo/função: public/index.html, devCard.\n"
                "Teste: abrir Central e ver o botão verde.\nCritério de aceite: botão fica verde em todas as telas.")
    ok, faltando = nubi_web.card_pronto(completo)
    assert ok and not faltando, (ok, faltando)

    vazio_ok, vazio_falt = nubi_web.card_pronto("")
    assert not vazio_ok and vazio_falt == ["Escopo", "Arquivo/função", "Teste", "Critério de aceite"], vazio_falt

    so_placeholder = ("Escopo: mudar a cor do botão.\nArquivo/função: [onde implementar]\n"
                       "Teste: abrir Central e ver o botão verde.\nCritério de aceite: botão fica verde em todas as telas.")
    ok2, falt2 = nubi_web.card_pronto(so_placeholder)
    assert not ok2 and falt2 == ["Arquivo/função"], falt2

    sem_teste = "Escopo: x.\nArquivo/função: y.\nCritério de aceite: z."
    ok3, falt3 = nubi_web.card_pronto(sem_teste)
    assert not ok3 and falt3 == ["Teste"], falt3

    # variações de maiúsculas/espaço e o rótulo alternativo "arquivo e função" continuam válidas
    variado = "  ESCOPO : a.\nArquivo e Função:  b.\nteste:c.\nCRITÉRIO DE ACEITE:d."
    ok4, falt4 = nubi_web.card_pronto(variado)
    assert ok4 and not falt4, falt4


class RepoAgentes:
    def __init__(s, cards):
        s.cards = {c["id"]: dict(c) for c in cards}
        s.eventos = []

    def _req(s, m, tab, params=None, corpo=None, prefer=None):
        if tab == "reuniao_tarefas" and m == "GET":
            return list(s.cards.values())
        if tab == "reuniao_tarefas" and m == "PATCH":
            tid = int(str(params["id"]).split(".")[-1])
            s.cards[tid].update(corpo)
            return []
        if tab == "tarefa_eventos" and m == "POST":
            s.eventos.extend(corpo)
            return []
        if tab == "tarefa_eventos" and m == "GET":
            tid = int(str(params["tarefa_id"]).split(".")[-1])
            evs = [e for e in s.eventos if e["tarefa_id"] == tid]
            return [evs[-1]] if evs else []
        return []

    def _eq(s, v):
        return f"eq.{v}"


def test_44_trabalhar_agentes_pula_card_incompleto():
    incompleto = {"id": 60, "status": "aprovada", "aguardando": None, "responsavel": "chatgpt", "risco": "baixo",
                  "titulo": "Card sem modelo", "descricao": "Só um texto solto, sem os 4 itens."}
    completo = {"id": 61, "status": "aprovada", "aguardando": None, "responsavel": "chatgpt", "risco": "baixo",
                "titulo": "Card com modelo", "descricao": ("Escopo: a.\nArquivo/função: b.\nTeste: c.\nCritério de aceite: d.")}
    r = RepoAgentes([incompleto, completo])
    nubi_web.agentes.perguntar = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sem rede no teste"))
    nubi_web.trabalhar_agentes(r, limite=2)

    # o incompleto nunca sai de "aprovada" nem ganha "Peguei o card"; fica só o aviso de card não executado
    assert r.cards[60]["status"] == "aprovada", r.cards[60]
    textos60 = [e["texto"] for e in r.eventos if e["tarefa_id"] == 60]
    assert textos60 == ["Card não executado: preencha Escopo, Arquivo/função, Teste, Critério de aceite na descrição."], textos60

    # o completo passou pelo gate: recebeu "Peguei o card" antes de tentar (e falhar) a chamada real
    textos61 = [e["texto"] for e in r.eventos if e["tarefa_id"] == 61]
    assert "Peguei o card e estou trabalhando nele." in textos61, textos61

    # rodando de novo não duplica o aviso do card incompleto (dedup pelo último evento)
    nubi_web.trabalhar_agentes(r, limite=2)
    textos60_de_novo = [e["texto"] for e in r.eventos if e["tarefa_id"] == 60]
    assert textos60_de_novo == textos60, textos60_de_novo


def linha_vend(titulo, unidades, vendas, preco, marca="M"):
    return {"titulo": titulo, "marca": marca, "unidades": unidades, "vendas": vendas, "preco": preco,
            "estado": "active", "tipo_pub": "classico", "full": False}


class RepoGate:
    def __init__(s, grupo=None, auditoria_hoje=None):
        s.grupo = grupo or []
        s.auditorias = [dict(auditoria_hoje)] if auditoria_hoje else []
        s.vendas = []

    def _req(s, m, tab, params=None, corpo=None, prefer=None):
        if tab == "vend_grupo_dia" and m == "GET":
            return s.grupo
        if tab == "auditorias":
            if m == "GET":
                return s.auditorias
            s.auditorias = [dict(corpo[0])]
            return corpo
        if tab == "vend_vendas_dia" and m == "POST":
            s.vendas.extend(corpo)
            return corpo
        return []

    def _eq(s, v):
        return f"eq.{v}"


def test_9_gate_bloqueia_valor_negativo():
    ok, motivo = nubi_web.validar_reconciliacao_publicacao(RepoGate(), "AUMA", "2026-09-20", -10, 5, [])
    assert not ok and "negativo" in motivo, motivo


def test_9_gate_bloqueia_item_sem_preco():
    itens = [{"k": "T:x", "t": "x", "u": 3, "v": 90, "p": 0}]
    ok, motivo = nubi_web.validar_reconciliacao_publicacao(RepoGate(), "AUMA", "2026-09-20", 90, 3, itens)
    assert not ok and "sem preço médio" in motivo, motivo


def test_9_gate_permite_brinde_unidade_com_preco_zero():
    # unidade vendida por R$ 0 (brinde/amostra grátis do Nubimetrics): preço médio 0 é esperado, não é erro
    # (achado real da revisão: bloquear isso escondia o dia inteiro do vendedor pra sempre, o Nubimetrics reexporta igual)
    itens = [{"k": "T:x", "t": "x", "u": 5, "v": 0, "p": 0}]
    ok, motivo = nubi_web.validar_reconciliacao_publicacao(RepoGate(), "AUMA", "2026-09-20", 0, 5, itens)
    assert ok and motivo is None, motivo


def test_9_gate_bloqueia_venda_sem_unidade():
    itens = [{"k": "T:x", "t": "x", "u": 0, "v": 90, "p": 0}]
    ok, motivo = nubi_web.validar_reconciliacao_publicacao(RepoGate(), "AUMA", "2026-09-20", 90, 0, itens)
    assert not ok and "sem nenhuma unidade" in motivo, motivo


def test_9_gate_bloqueia_grupo_fora_da_tolerancia():
    itens = [{"k": "T:x", "t": "x", "u": 10, "v": 1000, "p": 100}]
    grupo = [{"v": 2000, "u": 10}]
    ok, motivo = nubi_web.validar_reconciliacao_publicacao(RepoGate(grupo=grupo), "AUMA", "2026-09-20", 1000, 10, itens)
    assert not ok and "tabela do grupo" in motivo, motivo


def test_9_gate_publica_dentro_da_tolerancia():
    itens = [{"k": "T:x", "t": "x", "u": 10, "v": 1000, "p": 100}]
    grupo = [{"v": 1020, "u": 10}]   # 2% de diferença: dentro da tolerância de 3%
    ok, motivo = nubi_web.validar_reconciliacao_publicacao(RepoGate(grupo=grupo), "AUMA", "2026-09-20", 1000, 10, itens)
    assert ok and motivo is None, motivo


def test_9_gate_nao_bloqueia_quando_grupo_ainda_nao_chegou():
    itens = [{"k": "T:x", "t": "x", "u": 10, "v": 1000, "p": 100}]
    ok, motivo = nubi_web.validar_reconciliacao_publicacao(RepoGate(grupo=[]), "AUMA", "2026-09-20", 1000, 10, itens)
    assert ok and motivo is None, motivo


def test_9_gate_bloqueia_contagem_de_unidades_fora_da_tolerancia():
    # soma de R$ bate, mas a quantidade de unidades diverge muito do grupo (a checagem que faltava na 1ª volta)
    itens = [{"k": "T:x", "t": "x", "u": 10, "v": 1000, "p": 100}]
    grupo = [{"v": 1000, "u": 25}]
    ok, motivo = nubi_web.validar_reconciliacao_publicacao(RepoGate(grupo=grupo), "AUMA", "2026-09-20", 1000, 10, itens)
    assert not ok and "unidade(s)" in motivo, motivo


def test_9_achado_junta_com_auditoria_do_dia_sem_apagar():
    hoje = nubi_web._agora_br().date().isoformat()
    r = RepoGate(auditoria_hoje={"data": hoje, "resumo": "1 erro(s), 0 alerta(s), 2 informação(ões)",
                                  "conferencias": [{"nivel": "erro", "area": "coleta", "titulo": "já tinha", "detalhe": ""}],
                                  "modulo": "x.py (1/2)", "conversa": []})
    nubi_web._registrar_achado_auditoria(r, {"nivel": "erro", "area": "dados", "titulo": "novo achado", "detalhe": "d"})
    reg = r.auditorias[0]
    titulos = [a["titulo"] for a in reg["conferencias"]]
    assert titulos == ["já tinha", "novo achado"], titulos
    assert reg["resumo"].startswith("2 erro(s)"), reg["resumo"]
    assert reg["modulo"] == "x.py (1/2)", reg          # não mexe no que já tinha
    assert reg["conferencias"][1]["origem"] == "gate_publicacao", reg["conferencias"][1]


def test_9_achado_repetido_atualiza_em_vez_de_duplicar():
    r = RepoGate()
    nubi_web._registrar_achado_auditoria(r, {"nivel": "erro", "area": "dados", "titulo": "AUMA em 20/09", "detalhe": "1ª tentativa"})
    nubi_web._registrar_achado_auditoria(r, {"nivel": "erro", "area": "dados", "titulo": "AUMA em 20/09", "detalhe": "2ª tentativa"})
    conf = r.auditorias[0]["conferencias"]
    assert len(conf) == 1 and conf[0]["detalhe"] == "2ª tentativa", conf


def test_9_rota_vend_dia_nao_publica_lote_reprovado_e_registra_auditoria():
    linhas = [linha_vend("Perfume A", 10, 1000, 100)]
    nubi_web.vendedores.ler_vendedor = lambda corpo, nome: (linhas, "AUMA", "2026-09")
    r = RepoGate(grupo=[{"v": 3000, "u": 10}])         # grupo bem diferente do export: reprova
    try:
        nubi_web.rota_vendedores(r, "POST", "vend_dia", {"arquivo": "a.xlsx", "ate": "2026-09-20"}, b"x")
        assert False, "devia recusar (gate reprovou)"
    except nubi_web.ErroNuvem as e:
        assert "pendente" in str(e), e
    assert r.vendas == [], "não pode publicar o lote reprovado"
    assert r.auditorias and r.auditorias[0]["conferencias"][0]["nivel"] == "erro", r.auditorias


def test_9_rota_vend_dia_publica_lote_aprovado():
    linhas = [linha_vend("Perfume A", 10, 1000, 100)]
    nubi_web.vendedores.ler_vendedor = lambda corpo, nome: (linhas, "AUMA", "2026-09")
    r = RepoGate(grupo=[{"v": 1010, "u": 10}])         # dentro da tolerância
    resp = nubi_web.rota_vendedores(r, "POST", "vend_dia", {"arquivo": "a.xlsx", "ate": "2026-09-20"}, b"x")
    assert resp["ok"] and r.vendas and r.vendas[0]["vendedor"] == "AUMA", (resp, r.vendas)
    assert not r.auditorias, "lote bom não deve gerar achado"


class RepoAuditoriaRodar:
    def __init__(s, auditoria_hoje=None):
        s.auditorias = [dict(auditoria_hoje)] if auditoria_hoje else []

    def _req(s, m, tab, params=None, corpo=None, prefer=None):
        if tab == "vend_vendas_dia" and m == "GET":
            return []                    # conferencias() encerra cedo: "Ainda sem vendas diárias"
        if tab == "auditorias":
            if m == "GET":
                return s.auditorias
            s.auditorias = [dict(corpo[0])]
            return corpo
        return []


def test_9_auditoria_rodar_preserva_achado_do_gate_em_vez_de_apagar():
    # achado da revisão (1ª volta): a rotina noturna 'auditoria' recomputava tudo do zero e apagava o que o gate
    # de publicação já tinha gravado hoje; agora rodar() preserva os achados com origem=gate_publicacao.
    auditoria.ia.tem = lambda q: False
    hoje = auditoria._hoje_br().isoformat()
    r = RepoAuditoriaRodar(auditoria_hoje={
        "data": hoje, "resumo": "1 erro(s), 0 alerta(s), 0 informação(ões)", "modulo": "antigo.py (1/1)", "conversa": [],
        "conferencias": [{"nivel": "erro", "area": "dados", "origem": "gate_publicacao",
                          "titulo": "AUMA em 20/09/2026: gate de publicação reprovou (card #9)", "detalhe": "x"}]})
    reg = auditoria.rodar(r)
    titulos = [a["titulo"] for a in reg["conferencias"]]
    assert "AUMA em 20/09/2026: gate de publicação reprovou (card #9)" in titulos, titulos
    assert reg["data"] == hoje, reg


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
