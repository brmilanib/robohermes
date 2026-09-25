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
    reuniao.agentes.perguntar = lambda chave, texto, max_tokens=800: f"Resposta do {chave}"

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
    reuniao.agentes.perguntar = lambda chave, texto, max_tokens=800: chamou_especialista.append(chave) or "nunca deveria chamar"

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

    def fake_perguntar(chave, texto, max_tokens=800):
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
    reuniao.agentes.perguntar = lambda chave, texto, max_tokens=800: chamadas.append(texto) or "opinião única"
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
