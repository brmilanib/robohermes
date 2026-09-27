"""Atendimento ao cliente (26/09): dado real antes de responder, base por loja, conferência, aprovação humana e log."""
import itertools
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import atendimento as a  # noqa: E402
import ia  # noqa: E402


class Repo:
    """Supabase falso: guarda as linhas por tabela e entende os filtros eq./in./gte. usados pelo módulo."""

    def __init__(self):
        self.t, self.ids = {}, itertools.count(1)

    def _casa(self, linha, q):
        for k, v in (q or {}).items():
            if k in ("select", "order", "limit"):
                continue
            op, _, val = str(v).partition(".")
            atual = linha.get(k)
            if op == "eq" and (str(atual).lower() if isinstance(atual, bool) else str(atual)) != val:
                return False
            if op == "is" and atual is not None:
                return False
            if op == "in" and str(atual) not in val.strip("()").split(","):
                return False
            if op == "gte" and str(atual or "") < val:
                return False
        return True

    def _req(self, m, tabela, q=None, corpo=None, prefer=None):
        linhas = self.t.setdefault(tabela, [])
        if m == "GET":
            achou = [dict(x) for x in linhas if self._casa(x, q)]
            if "id.desc" in str((q or {}).get("order")):
                achou.sort(key=lambda x: -x.get("id", 0))
            return achou[: int((q or {}).get("limit") or 10**6)]
        if m == "POST":
            novos = [dict(x, id=x.get("id") or next(self.ids)) for x in corpo]
            linhas += novos
            return [dict(x) for x in novos]
        if m == "PATCH":
            for x in linhas:
                if self._casa(x, q):
                    x.update(corpo)
            return []
        return []


def _ia(respostas):
    feitas = []

    def gerar(prompt, sistema):
        feitas.append((prompt, sistema))
        return next(respostas), "gpt-oss"
    gerar.feitas = feitas
    return gerar


def test_pedido_com_dado_real_vira_rascunho_sem_dado_sensivel():
    r = Repo()
    r.t["store_orders"] = [{"source": "tiktok_shop", "id_externo": "578123456789012345", "status": "enviado",
                            "dados": {"transportadora": "J&T Express", "rastreio": "JT123BR", "previsao_entrega": "2026-10-02",
                                      "endereco": "Rua das Flores 10", "telefone": "11999998888", "valor": 199.9,
                                      "itens": [{"name": "Lattafa Asad", "sku_name": "100 ml", "quantity": 1}]}}]
    gerar = _ia(iter(["Oi, Ana! Entendo a preocupação. Seu pedido já foi enviado pela J&T Express (rastreio JT123BR) e a "
                      "previsão de entrega é 02/10. Qualquer coisa, é só chamar!"]))
    rasc = a.receber(r, "tiktok_shop", "Oi, cadê meu pedido 578123456789012345?", cliente="Ana", gerar=gerar)
    assert rasc["status"] == "pendente" and rasc["intencao"] == "rastreio"
    ped = rasc["fontes"]["pedido"]
    assert ped["transportadora"] == "J&T Express" and ped["itens"] == [{"nome": "Lattafa Asad", "variacao": "100 ml", "quantidade": 1}]
    enviado = json.dumps(gerar.feitas[0])
    assert "Rua das Flores" not in enviado and "11999998888" not in enviado and "199.9" not in enviado   # nunca chega à IA
    assert r.t["atendimento_conversas"][0]["status"] == "rascunho"


def test_sem_dado_nao_responde_e_pergunta_ao_lojista():
    r = Repo()
    gerar = _ia(iter([]))
    rasc = a.receber(r, "tiktok_shop", "Vocês vendem tester do Asad?", gerar=gerar)
    assert rasc["status"] == "precisa_info" and "não tenho essa informação" in rasc["pergunta_operador"]
    assert not gerar.feitas                                           # nem chamou a IA
    assert r.t["atendimento_conversas"][0]["status"] == "precisa_info"
    rasc2 = a.receber(r, "tiktok_shop", "meu pedido 578000000000000001 não chegou", gerar=gerar)
    assert rasc2["status"] == "precisa_info" and "578000000000000001" in rasc2["pergunta_operador"]
    rasc3 = a.receber(r, "tiktok_shop", "Chegou quebrado, que absurdo", gerar=gerar)
    assert rasc3["status"] == "precisa_info" and "Reclamação" in rasc3["pergunta_operador"]


def test_resposta_do_lojista_vira_base_e_proxima_vez_nao_pergunta():
    r = Repo()
    rasc = a.receber(r, "tiktok_shop", "Vocês vendem tester do Asad?", gerar=_ia(iter([])))
    gerar = _ia(iter(["Oi! Não trabalhamos com tester, só perfumes lacrados. Qualquer coisa, é só chamar!"] * 2))
    res = a.responder_operador(r, rasc["id"], "Não vendemos tester, só lacrado.", pergunta_tipo="Vendemos perfumes tester?",
                               gerar=gerar)
    assert res["rascunho"].get("automatico") and res["kb"]["confirmado_por"] == "Bruno" and res["kb"]["status"] == "ativa"
    assert "resposta_do_lojista" in res["rascunho"]["fontes"]
    novo = a.receber(r, "tiktok_shop", "vocês vendem perfume tester?", gerar=gerar)       # outro cliente, outras palavras
    assert novo.get("automatico") and novo["fontes"]["base_de_conhecimento"][0]["pergunta"] == "Vendemos perfumes tester?"


def test_numero_inventado_e_barrado():
    r = Repo()
    a.salvar_item_kb(r, "principal", "Qual o prazo de envio?", "Enviamos em até 2 dias úteis após a confirmação.")
    gerar = _ia(iter(["Oi! Enviamos em 1 dia. Qualquer coisa, é só chamar!", "Oi! Chega com certeza em 5 dias!"]))
    rasc = a.receber(r, "tiktok_shop", "qual o prazo de envio?", gerar=gerar)
    assert rasc["status"] == "precisa_info" and "número que não está nos dados" in rasc["motivo"]
    assert len(gerar.feitas) == 2 and "barrada" in gerar.feitas[1][0]
    ok = a.receber(r, "tiktok_shop", "qual o prazo de envio?", gerar=_ia(iter(["Oi! Enviamos em até 2 dias úteis após a confirmação."])))
    assert ok["status"] == "pendente" and ok["texto_gerado"].endswith(a.ENCERRAMENTO)   # fechamento sempre presente


def test_conferencia_de_promessa_e_dado_sensivel():
    fatos = {"base_de_conhecimento": [{"resposta": "Trocas em até 7 dias."}]}
    assert any("promessa" in p for p in a.conferir("Te dou um cupom de desconto!", fatos, "oi"))
    assert any("telefone" in p for p in a.conferir("Me chama no (11) 98888-7777", fatos, "oi"))
    assert a.conferir("Trocas em até 7 dias! Qualquer coisa, é só chamar!", fatos, "posso trocar?") == []
    controle = {"base_de_conhecimento": [{"id": 3, "resposta": "Enviamos rápido.", "confirmado_em": "2026-09-26T10:00"}]}
    assert a.conferir("Chega em 26 dias!", controle, "oi")          # data de confirmação não vale como prazo


def test_despedida_nao_repete():
    t = a._com_encerramento("Oi! Obrigado! 😊 Qualquer dúvida, é só chamar. Qualquer coisa, é só chamar!")
    assert t == "Oi! Obrigado! 😊 Qualquer dúvida, é só chamar."
    assert a._com_encerramento("Por nada!").endswith(a.ENCERRAMENTO)
    assert a._com_encerramento("Seu pedido está **Em trânsito**. Qualquer coisa, é só chamar!") == \
        "Seu pedido está Em trânsito. Qualquer coisa, é só chamar!"


def test_ia_diz_que_falta_vira_pergunta():
    r = Repo()
    a.salvar_item_kb(r, "principal", "Qual o horário de atendimento?", "Seg a sex, 9h às 18h.")
    rasc = a.receber(r, "tiktok_shop", "qual o horário de atendimento no sábado?",
                     gerar=_ia(iter(["FALTA: não sei se atendemos sábado"])))
    assert rasc["status"] == "precisa_info" and "sábado" in rasc["motivo"]


def test_aprovar_editar_rejeitar_e_metricas():
    r = Repo()
    a.salvar_item_kb(r, "principal", "Vocês enviam para todo o Brasil?", "Sim, enviamos para todo o Brasil.")
    texto = "Oi! Sim, enviamos para todo o Brasil. Qualquer coisa, é só chamar!"
    ids = [a.receber(r, "whatsapp", "vocês enviam para todo o Brasil?", externo_id=str(i), gerar=_ia(iter([texto])))["id"]
           for i in range(3)]
    x = a.decidir(r, ids[0], "aprovar")
    assert x["status"] == "aprovado" and x["semelhanca"] == 1.0 and "copie" in x["aviso"]   # canal sem integração: copiar
    y = a.decidir(r, ids[1], "editar", texto.replace("Oi!", "Oi, tudo bem?"))
    assert y["status"] == "editado" and y["semelhanca"] < 1
    assert a.decidir(r, ids[2], "rejeitar")["status"] == "rejeitado"
    try:
        a.decidir(r, ids[0], "aprovar")
        assert False, "não pode decidir duas vezes"
    except ValueError:
        pass
    m = a.metricas(r)["total"]
    assert m["decididos"] == 3 and m["acerto"] == round(1 / 3, 3)
    assert [x["de"] for x in r.t["atendimento_mensagens"]].count("loja") == 2


def test_canal_novo_pluga_sem_mudar_a_logica():
    enviados = []

    class Zap(a.Canal):
        def enviar(self, conversa, texto):
            enviados.append(texto)
    a.registrar_canal(Zap("whatsapp_teste", "WhatsApp (teste)"))
    a.AUTO_CHAVE_ANTES = a.AUTO_CHAVE
    r = Repo()
    a.salvar_item_kb(r, "todas", "Vocês enviam para todo o Brasil?", "Sim, para todo o Brasil.")
    rasc = a.receber(r, "whatsapp_teste", "enviam para todo o Brasil?", loja="haya",
                     gerar=_ia(iter(["Oi! Sim, para todo o Brasil. Qualquer coisa, é só chamar!"])))
    assert rasc["status"] == "pendente" and not enviados     # canal sem 'envia': nada sai sozinho
    assert a.decidir(r, rasc["id"], "aprovar")["status"] == "enviado" and enviados


def test_ia_de_verdade_usa_so_as_gratis():
    chamadas = []
    ia.tem = lambda q: q in ("ollama", "claude")
    ia.perguntar = lambda p, **k: (chamadas.append(k["qual"]) or "Oi!", [], k["qual"])
    assert a.gerar_ia("x", "y") == ("Oi!", "ollama") and chamadas == ["ollama"]
    ia.tem = lambda q: q == "claude"
    try:
        a.gerar_ia("x", "y")
        assert False, "não pode cair na IA paga"
    except ia.SemIA:
        pass


def test_tiktok_aprendido_sai_sozinho_pelo_mac_e_duvida_vai_ao_bruno():
    r = Repo()
    a.salvar_item_kb(r, "principal", "Vendemos perfumes tester?", "Sim, vendemos tester. Pergunte qual perfume o cliente quer.")
    texto = "Oi! Sim, vendemos tester! Qual perfume você quer? Qualquer coisa, é só chamar!"
    x = a.receber(r, "tiktok_shop", "vocês vendem tester?", cliente="leidi", externo_id="leidi", gerar=_ia(iter([texto])))
    assert x.get("automatico") and x["pelo_mac"] and a.para_enviar(r) == [{"id": x["id"], "cliente": "leidi", "texto": texto, "canal": "tiktok_shop"}]
    a.marcar_enviado(r, x["id"])
    assert a.para_enviar(r) == [] and a.metricas(r)["automaticas"] == 1
    # a mesma mensagem lida de novo pelo atendente não duplica nada
    a.receber(r, "tiktok_shop", "vocês vendem tester?", cliente="leidi", externo_id="leidi", gerar=_ia(iter([])))
    assert len(r.t["atendimento_rascunhos"]) == 1
    y = a.receber(r, "shopee", "", cliente="samia", externo_id="samia", respondido=True, historico=[
        {"de": "loja", "texto": "Oi! Tudo bem?"}, {"de": "cliente", "texto": "(nenhuma mensagem)"}], gerar=_ia(iter([])))
    assert y["status"] == "historico"                                       # marcador do modelo não vira pergunta
    # pedido: nunca sai sozinho; o pedido lido no painel do chat vale como dado real
    tela = {"id": "586222884320019967", "status": "Em trânsito", "previsao_entrega": "entre 28/09 e 04/10", "transportadora": "J&T"}
    y = a.receber(r, "tiktok_shop", "cadê meu pedido?", cliente="ana", externo_id="ana", pedido_ref="586222884320019967",
                  pedido_dados=tela, gerar=_ia(iter(["Oi! Entendo a preocupação. Seu pedido está Em trânsito pela J&T, entrega entre 28/09 e 04/10. Qualquer coisa, é só chamar!"])))
    assert y["status"] == "pendente" and not y.get("automatico") and y["fontes"]["pedido"]["status"] == "Em trânsito"
    # dúvida: o Bruno responde embaixo e a resposta já vai para o cliente
    z = a.receber(r, "tiktok_shop", "o Sabah vem com tampa preta ou transparente?", cliente="manu", externo_id="manu", gerar=_ia(iter([])))
    assert z["status"] == "precisa_info"
    res = a.responder_operador(r, z["id"], "Tem as duas versões, é o mesmo perfume: mudou o design, depende do lote; a caixa é selada.",
                               pergunta_tipo="O Sabah vem com tampa preta ou transparente?",
                               gerar=_ia(iter(["Oi! Temos as duas versões, é o mesmo perfume: só mudou o design e depende do lote. Qualquer coisa, é só chamar!"])))
    assert res["rascunho"].get("automatico") and {i["cliente"] for i in a.para_enviar(r)} == {"manu"}
    # desligado: nada sai sozinho
    r.t["ia_resumos"] = [{"chave": a.AUTO_CHAVE, "texto": "desligado"}]
    w = a.receber(r, "tiktok_shop", "vocês vendem tester?", cliente="bia", externo_id="bia", gerar=_ia(iter([texto])))
    assert w["status"] == "pendente" and not w.get("automatico")


def test_mensagem_livre_do_bruno_sai_e_fica_fora_do_acerto():
    r = Repo()
    z = a.receber(r, "tiktok_shop", "tem o Asad?", cliente="bia", externo_id="bia", gerar=_ia(iter([])))
    x = a.mensagem_manual(r, z["conversa_id"], "Oi Bia! Tem sim, pode comprar pelo link do anúncio 😊")
    assert x["pelo_mac"] and a.para_enviar(r)[0]["texto"].startswith("Oi Bia")
    assert a.metricas(r)["total"]["decididos"] == 0


def test_historico_do_chat_e_agradecimento():
    r = Repo()
    hist = [{"de": "cliente", "texto": "Boa noite"}, {"de": "cliente", "texto": "Qual endereço consta no envio?"},
            {"de": "loja", "texto": "Oi! O CEP registrado é 39535-000."}, {"de": "cliente", "texto": "Obgd"}]
    x = a.receber(r, "tiktok_shop", "", cliente="alana", externo_id="alana", historico=hist,
                  gerar=_ia(iter(["Por nada! Qualquer coisa, é só chamar! 😊"])))
    assert x["intencao"] == "agradecimento" and x.get("automatico")                 # agradeceu: responde sozinho
    msgs = [(m["de"], m["texto"]) for m in sorted(r.t["atendimento_mensagens"], key=lambda m: m["criado_em"])]
    assert msgs[:4] == [(h["de"], h["texto"]) for h in hist]                        # histórico na ordem, sem repetir
    a.receber(r, "tiktok_shop", "", cliente="alana", externo_id="alana", historico=hist, gerar=_ia(iter([])))
    assert len([m for m in r.t["atendimento_mensagens"] if m["texto"] == "Boa noite"]) == 1
    y = a.receber(r, "tiktok_shop", "", cliente="sami", externo_id="sami", respondido=True,
                  historico=[{"de": "cliente", "texto": "cadê?"}, {"de": "loja", "texto": "Está a caminho!"}])
    assert y["status"] == "historico" and not [z for z in r.t["atendimento_rascunhos"] if z["conversa_id"] == y["conversa_id"]]


def test_duvida_antiga_se_resolve_quando_a_base_aprende():
    r = Repo()
    z = a.receber(r, "tiktok_shop", "vocês vendem tester?", cliente="leo", externo_id="leo", gerar=_ia(iter([])))
    assert z["status"] == "precisa_info"
    assert a.receber(r, "tiktok_shop", "vocês vendem tester?", cliente="leo", externo_id="leo", gerar=_ia(iter([])))["id"] == z["id"]
    a.salvar_item_kb(r, "principal", "Vendemos perfumes tester?", "Sim, vendemos tester.")
    y = a.receber(r, "tiktok_shop", "vocês vendem tester?", cliente="leo", externo_id="leo",
                  gerar=_ia(iter(["Oi! Sim, vendemos tester! Qualquer coisa, é só chamar!"])))
    assert y.get("automatico") and [x["status"] for x in r.t["atendimento_rascunhos"]][0] == "substituido"


def test_aprende_padroes_dos_chats_como_propostas():
    r = Repo()
    a.receber(r, "tiktok_shop", "", cliente="ana", externo_id="ana", respondido=True, historico=[
        {"de": "cliente", "texto": "Vocês trocam se eu não gostar do cheiro?"},
        {"de": "loja", "texto": "Trocamos em até 7 dias se o lacre estiver intacto."}])
    a.receber(r, "tiktok_shop", "", cliente="bia", externo_id="bia", respondido=True, historico=[
        {"de": "cliente", "texto": "oi"}])                                  # sem resposta da loja: nada a aprender
    resp = json.dumps({"padroes": [{"pergunta": "Vocês trocam se eu não gostar do cheiro?", "resposta": "Trocamos em até 7 dias se o lacre estiver intacto.", "tags": ["troca"]},
                                   {"pergunta": "Qual meu telefone?", "resposta": "Ligue (11) 98888-7777"}]})
    res = a.aprender_padroes(r, gerar=_ia(iter([resp])))
    assert res == {"lidas": 2, "propostas": 1}
    kb = r.t["atendimento_kb"]
    assert kb[0]["status"] == "proposta" and kb[0]["confirmado_por"] == "chat de ana"
    assert a.buscar_kb(r, "principal", "vocês trocam?") == []              # proposta não responde sozinha
    a.rota(r, "POST", "atendimento_kb_salvar", {}, json.dumps({"aprovar": [kb[0]["id"]]}).encode())
    assert kb[0]["status"] == "ativa" and a.buscar_kb(r, "principal", "vocês trocam se eu não gostar?")
    assert a.aprender_padroes(r, gerar=_ia(iter([])))["lidas"] == 0            # não lê de novo


def test_avisos_do_sistema_e_do_chatbot_ficam_de_fora():
    r = Repo()
    x = a.receber(r, "tiktok_shop", "", cliente="silvia", externo_id="silvia", respondido=True,
                  historico=[{"de": "cliente", "texto": "O bate-papo foi encerrado devido à inatividade do cliente"}])
    assert x["status"] == "so_avisos" and not r.t.get("atendimento_conversas")
    y = a.receber(r, "tiktok_shop", "", cliente="angela", externo_id="angela", historico=[
        {"de": "loja", "texto": "[chatbot]Olá, obrigado por entrar em contato conosco."},
        {"de": "cliente", "texto": "vocês vendem tester?"}, {"de": "loja", "texto": "Temos sim! Qual perfume?"}])
    assert y["status"] == "historico" and [m["texto"] for m in r.t["atendimento_mensagens"]] == ["vocês vendem tester?", "Temos sim! Qual perfume?"]


def test_so_a_previa_depois_o_historico_entra_antes_na_ordem():
    r = Repo()
    a.receber(r, "tiktok_shop", "", cliente="sami", externo_id="sami", respondido=True,
              historico=[{"de": "loja", "texto": "Está a caminho pela J&T!"}])          # só a prévia (1ª rodada)
    assert a.rota(r, "GET", "atendimento_para_enviar", {}, None)["conhecidos"] == []    # prévia não conta como conhecida
    a.receber(r, "tiktok_shop", "", cliente="sami", externo_id="sami", respondido=True, historico=[
        {"de": "cliente", "texto": "cadê meu pedido?"}, {"de": "cliente", "texto": "já faz 5 dias"},
        {"de": "loja", "texto": "Está a caminho pela J&T!"}])
    ordem = [m["texto"] for m in sorted(r.t["atendimento_mensagens"], key=lambda m: m["criado_em"])]
    assert ordem == ["cadê meu pedido?", "já faz 5 dias", "Está a caminho pela J&T!"]
    assert a.rota(r, "GET", "atendimento_para_enviar", {}, None)["conhecidos"] == ["sami"]


def test_chat_da_aba_fechados_fica_fechado_ate_o_cliente_voltar():
    r = Repo()
    x = a.receber(r, "tiktok_shop", "", cliente="moi", externo_id="moi", respondido=True, fechado=True,
                  historico=[{"de": "cliente", "texto": "chegou certinho"}, {"de": "loja", "texto": "Que ótimo!"}])
    assert r.t["atendimento_conversas"][0]["status"] == "fechada"
    a.receber(r, "tiktok_shop", "vocês vendem tester?", cliente="moi", externo_id="moi", gerar=_ia(iter([])))
    assert r.t["atendimento_conversas"][0]["status"] == "precisa_info"                # voltou para a caixa de entrada


def test_gpt_oss_com_ferramentas_no_formato_da_anthropic():
    enviados = []
    ia.tem = lambda q: q == "ollama"
    ia._post_json = lambda url, corpo, cab, timeout=150: (enviados.append(corpo) or {
        "message": {"content": "", "tool_calls": [{"function": {"name": "clicar", "arguments": {"n": 3}}}]},
        "prompt_eval_count": 100, "eval_count": 10})
    msgs = [{"role": "user", "content": "comece"},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "ler", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "PÁGINA " * 500}]}]
    r = ia.ollama_ferramentas(msgs, "sistema", [{"name": "clicar", "description": "x", "input_schema": {"type": "object"}}])
    assert r["content"][0]["name"] == "clicar" and r["content"][0]["input"] == {"n": 3}
    c = enviados[0]
    assert c["tools"][0]["function"]["name"] == "clicar" and c["messages"][2]["tool_calls"][0]["function"]["name"] == "ler"
    assert c["messages"][3]["role"] == "tool"


def test_shopee_tem_atendente_proprio():
    r = Repo()
    a.rota(r, "POST", "atendimento_ligar", {}, json.dumps({"canal": "shopee", "ligado": True}).encode())
    assert a.canais_ligados(r) == ["shopee"] and not a.atendente_ligado(r, "tiktok_shop")
    a.salvar_item_kb(r, "principal", "Vocês vendem perfumes tester?", "Sim, vendemos tester.")
    x = a.receber(r, "shopee", "vocês vendem tester?", cliente="joao", externo_id="joao",
                  gerar=_ia(iter(["Oi! Sim, vendemos tester! Qualquer coisa, é só chamar!"])))
    assert x.get("automatico") and a.para_enviar(r)[0]["canal"] == "shopee"
    f = a.rota(r, "GET", "atendimento_fila", {"canal": "shopee"}, None)
    assert [c["cliente"] for c in f["conversas"]] == ["joao"] and f["atendente"]
    assert a.rota(r, "GET", "atendimento_fila", {"canal": "tiktok_shop"}, None)["conversas"] == []


def test_atendente_do_mac_e_chamado_quando_ligado():
    r = Repo()
    assert a.atendente_proximo(r) is None                                # desligado
    r.t["ia_resumos"] = [{"chave": a.ATENDENTE_CHAVE, "texto": "ligado"}]
    assert a.atendente_proximo(r) == "atendente chamado"
    assert a.atendente_proximo(r) is None                                # já tem um na fila
    r.t["mac_comandos"][0]["status"] = "ok"
    assert a.atendente_proximo(r) is None                                # menos de 5 min e nada para enviar
    assert a.atendente_proximo(r, mac_online=False) is None
    r.t["mac_comandos"] = []
    a.rota(r, "GET", "atendimento_para_enviar", {"computador": "pc"}, None)       # o PC do Bruno está atendendo
    assert a.atendente_no_pc(r) and a.atendente_proximo(r) is None


def test_resposta_do_robo_da_shopee_nao_conta_como_resposta():
    # 27/09: o "Assistente AI" da Shopee respondeu "aguarde" / "não consigo responder"; a cliente continuava esperando
    r = Repo()
    x = a.receber(r, "shopee", "", cliente="fernanda", externo_id="fernanda", respondido=True, historico=[
        {"de": "cliente", "texto": "Tem outro perfume feminino pra menina de 15 anos?"},
        {"de": "loja", "texto": "Lamento, mas não posso responder a essa pergunta. Você será transferido para um agente do "
                               "vendedor para receber melhor assistência. Agradeço sua paciência."},
        {"de": "loja", "texto": "Olá! Recebemos sua mensagem 😊 Em breve nossa equipe irá analisar e responder sua "
                               "solicitação. Pedimos, por gentileza, que aguarde nosso retorno."}], gerar=_ia(iter([])))
    assert x["status"] != "historico" and r.t["atendimento_conversas"][0]["status"] != "respondida"
    assert [m["texto"] for m in r.t["atendimento_mensagens"]] == ["Tem outro perfume feminino pra menina de 15 anos?"]
    assert len(r.t["atendimento_rascunhos"]) == 1


def test_conversa_ja_guardada_como_respondida_pelo_robo_e_retomada():
    r = Repo()
    a.receber(r, "shopee", "", cliente="naiara", externo_id="naiara", respondido=True, fechado=True, historico=[
        {"de": "cliente", "texto": "Qual a validade ?"}, {"de": "loja", "texto": "Qual perfume?"}])
    conv = r.t["atendimento_conversas"][0]
    conv["status"] = "respondida"
    for t in ("Qual o ano de validade ?", "Olá! Recebemos sua mensagem 😊 Em breve nossa equipe irá responder."):
        r._req("POST", "atendimento_mensagens", corpo=[{"conversa_id": conv["id"], "de": "loja" if "Recebemos" in t else "cliente",
                                                          "texto": t, "criado_em": a._agora()}])
    feitas = a.retomar_esquecidas(r)
    assert len(feitas) == 1 and r.t["atendimento_rascunhos"][0]["conversa_id"] == conv["id"]
    assert a.retomar_esquecidas(r, a_cada_min=0) == []                     # não repete o rascunho


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
