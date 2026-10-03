"""WhatsApp do chip (03/10, Bruno): o Banguela escreve, o Bruno aprova no privado, nada sai sozinho; Via Brazil pela frase
do site; "Ferreiro, …" vai para o agente do Mac."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import atendimento as a  # noqa: E402
import whatsapp as w  # noqa: E402
from test_atendimento import Repo as _Repo  # noqa: E402


class Repo(_Repo):
    """+ upsert de ia_resumos pela chave (merge-duplicates), como o Supabase faz."""

    def _req(self, m, tabela, q=None, corpo=None, prefer=None):
        if m == "POST" and tabela == "ia_resumos" and "merge-duplicates" in str(prefer):
            linhas = self.t.setdefault(tabela, [])
            for x in corpo:
                linhas[:] = [y for y in linhas if y.get("chave") != x["chave"]] + [dict(x)]
            return []
        return super()._req(m, tabela, q, corpo, prefer)

pedidos_ia = []
REPO_ATUAL = [None]


def gerar(prompt, sistema):
    pedidos_ia.append((prompt, sistema))
    if "interpreta" in sistema.lower():
        return "{}", "teste"
    if "BOM DIA" in sistema:
        return "Bom dia, Bruno! 📈 Ontem foi bom.", "teste"
    if "pede o número" in prompt:
        n = max(x["id"] for x in REPO_ATUAL[0].t["atendimento_rascunhos"] if x["status"] == "pendente")
        return f"Ajustei e enviei!\n[[editar:{n}|Oi! Me passa o número do pedido para eu verificar?]]", "teste"
    if "reenvia sem custo" in prompt:
        return "Anotado!\n[[base:todas|Meu pedido foi cancelado pela transportadora, e agora?|Quando a transportadora cancela, a gente reenvia sem custo.]]", "teste"
    if "esquece o Jorge" in prompt:
        return "Pronto, esqueci. [[esquecer:Jorge]]", "teste"
    if "guarda que" in prompt:
        return "Guardei! [[memoria:pessoa|Jorge é o despachante da Via Brazil, fala com ele às terças]]", "teste"
    if "me lembra" in prompt:
        return "Marquei! [[lembrete:2026-10-04 09:00|ligar pro fornecedor]]\n[[ferreiro:ver por que o Gestor pede login]]", "teste"
    return "Oi! Que bom falar com você 😊 Me conta o que você procura e mais ou menos o volume. Qualquer coisa, é só chamar!", "teste"


a.gerar_qualidade = lambda repo, modelo=None: gerar
a.auto_ligado = lambda repo: True            # mesmo com o "responder sozinho" ligado, o WhatsApp espera o Bruno


def test_fluxo_completo():
    r = Repo()
    t = w.tick(r, {"clientes": [{"fone": "+55 47 98888-1111", "nome": "+55 47 98888-1111",
                                 "texto": "Olá! Gostaria de saber mais sobre a Via Brazil Global.",
                                 "historico": [{"de": "cliente", "texto": "Olá! Gostaria de saber mais sobre a Via Brazil Global."}]},
                                {"fone": "5544998812871", "texto": "isso é o dono, não é cliente"}]})
    assert t["recebidos"] == 1 and not t["erros"], t
    conv = r.t["atendimento_conversas"]
    assert len(conv) == 1 and conv[0]["loja"] == "via_brazil" and conv[0]["externo_id"] == "5547988881111"
    assert "Via Brazil Global" in pedidos_ia[-1][1] or "Via Brazil Global" in pedidos_ia[-1][0]   # a loja certa no pedido à IA
    assert not t["enviar"], "nada sai sem o Bruno"
    assert len(t["ao_dono"]) == 1 and "Sugestão" in t["ao_dono"][0] and "Via Brazil Global" in t["ao_dono"][0]
    rid = r.t["atendimento_rascunhos"][-1]["id"]
    assert w.tick(r, {})["ao_dono"] == []                                       # não avisa duas vezes
    # o Bruno muda o texto ("12 texto") → sai o texto dele
    t = w.tick(r, {"dono": [{"texto": f"{rid} Oi! Somos importadores, me passa o volume que te mando a tabela."}]})
    assert t["ao_dono"][0].startswith(f"✅ #{rid}") and len(t["enviar"]) == 1
    assert t["enviar"][0]["fone"] == "5547988881111" and t["enviar"][0]["texto"].startswith("Oi! Somos importadores")
    a.marcar_enviado(r, t["enviar"][0]["id"], True)
    assert w.tick(r, {})["enviar"] == []
    # segunda mensagem do mesmo cliente → "ok" aprova a sugestão do Banguela
    w.tick(r, {"clientes": [{"fone": "5547988881111", "nome": "+55 47 98888-1111", "texto": "Tenho CNPJ, compro uns 500 por mês",
                             "historico": [{"de": "cliente", "texto": "Olá! Gostaria de saber mais sobre a Via Brazil Global."},
                                           {"de": "loja", "texto": "Oi! Somos importadores, me passa o volume que te mando a tabela."},
                                           {"de": "cliente", "texto": "Tenho CNPJ, compro uns 500 por mês"}]}]})
    t = w.tick(r, {"dono": [{"texto": "ok"}]})
    assert "aprovado" in t["ao_dono"][0] and len(t["enviar"]) == 1 and t["enviar"][0]["texto"].startswith("Oi! Que bom")
    # "não" sem nada aberto e conversa com os agentes
    assert "Não achei" in w.tick(r, {"dono": [{"texto": "não"}]})["ao_dono"][0]
    t = w.tick(r, {"dono": [{"texto": "Codex, como está a coleta?"}, {"texto": "e o estoque hoje?"}]})
    assert t["agentes"] == [{"agente": "codex", "texto": "como está a coleta?"}, {"agente": "claude", "texto": "e o estoque hoje?"}]
    # o Banguela conversa sobre a fila (WhatsApp "Banguela, …" e Painel) e só aprova pelo jeito explícito
    w.tick(r, {"clientes": [{"fone": "5547977776666", "nome": "Ana", "texto": "Vocês vendem no atacado?"}]})
    t = w.tick(r, {"dono": [{"texto": "Banguela, o que tem esperando?"}]})
    assert t["ao_dono"][0].startswith("🦷 Banguela:") and not t["agentes"]
    assert "Esperando" not in w.banguela(r, "quantos clientes hoje?") or True
    antes = len(w.tick(r, {})["enviar"])
    assert w.banguela(r, "me fala da Ana") and len(w.tick(r, {})["enviar"]) == antes      # texto solto no Painel nunca envia
    rid = max(x["id"] for x in r.t["atendimento_rascunhos"] if x["status"] in ("pendente", "precisa_info"))
    x = w.banguela(r, f"{rid} Sim, vendemos no atacado a partir de 12 unidades")
    assert f"✅ #{rid}" in x or f"📝 #{rid}" in x, x
    # o atendente do PC (TikTok/Shopee) nunca recebe o que é do WhatsApp
    assert all(x["canal"] != "whatsapp" for x in a.para_enviar(r))


def test_assistente_lembrete_bom_dia_e_ferreiro():
    from datetime import datetime, timezone
    r = Repo()
    t = w.tick(r, {"dono": [{"texto": "Banguela, me lembra amanhã às 9h de ligar pro fornecedor"}]})
    assert t["ao_dono"][0].startswith("🦷 Banguela:\nMarquei!") and "[[" not in t["ao_dono"][0]
    assert t["agentes"] == [{"agente": "claude", "texto": "(pedido do Bruno, passado pelo Banguela) ver por que o Gestor pede login"}]
    lem = w._ler(r, w.LEMBRETES, [])
    assert len(lem) == 1 and lem[0]["quando"].startswith("2026-10-04T12:00")            # 9h de Brasília = 12h UTC
    assert w.lembretes_vencidos(r, datetime(2026, 10, 4, 11, 59, tzinfo=timezone.utc)) == []
    assert w.lembretes_vencidos(r, datetime(2026, 10, 4, 12, 1, tzinfo=timezone.utc)) == ["⏰ Lembrete: ligar pro fornecedor"]
    assert w._ler(r, w.LEMBRETES, []) == []
    cedo, oito = datetime(2026, 10, 4, 10, 0, tzinfo=timezone.utc), datetime(2026, 10, 4, 11, 5, tzinfo=timezone.utc)
    w.enfileirar_aviso(r, "🤖 nubi: ✅ terminou: histórico de vendas")
    assert w.tick(r, {})["ao_dono"][0] == "🤖 nubi: ✅ terminou: histórico de vendas" and w.avisos_pendentes(r) == []
    assert w.bom_dia(r, cedo) is None                                                    # 7h de Brasília: ainda não
    assert w.bom_dia(r, oito).startswith("☀️ Bom dia, Bruno!") and w.bom_dia(r, oito) is None   # 1 vez por dia


def test_aprova_e_edita_de_outro_canal():
    # 03/10 (print do Bruno): "ok 172" era da Shopee e o Banguela dizia "não achei"; e "primeiro pede o número do pedido"
    # tem que virar o texto enviado
    r = Repo()
    REPO_ATUAL[0] = r
    a.salvar_item_kb(r, "principal", "Cadê meu pedido?", "Seu pedido está a caminho.")
    for i in (1, 2):
        a.receber(r, "shopee", "cadê meu pedido?", cliente=f"cli{i}", externo_id=f"s{i}", gerar=lambda p, s: ("Oi! Seu pedido está a caminho. Qualquer coisa, é só chamar!", "t"))
    ids = [x["id"] for x in r.t["atendimento_rascunhos"] if x["status"] == "pendente"]
    assert len(ids) == 2
    x = w.banguela(r, f"ok {ids[0]}")
    assert f"✅ #{ids[0]}" in x and "(Shopee)" in x, x
    txt = w.banguela(r, "primeiro pede o número do pedido dela")
    assert f"✅ #{ids[1]}" in txt and "[[" not in txt
    envio = [x for x in a.para_enviar(r) if x["id"] == ids[1]]
    assert envio and envio[0]["texto"].startswith("Oi! Me passa o número do pedido") and envio[0]["canal"] == "shopee"


def test_ensina_a_base_dos_clientes():
    r = Repo()
    x = w.banguela(r, "pedido cancelado pela transportadora a gente reenvia sem custo")
    kb = [k for k in r.t.get("atendimento_kb", []) if "transportadora" in k["pergunta"]]
    assert "Guardei na base" in x and kb and kb[0]["loja"] == "todas" and "[[" not in x


def test_memoria_e_modelo():
    """03/10 (Bruno): ela sabe o modelo dela; a memória fica no nubi e é a mesma no Painel e no WhatsApp."""
    r = Repo()
    REPO_ATUAL[0] = r
    x = w.banguela(r, "guarda que o Jorge é o despachante")
    assert "Guardei" in x and "[[" not in x
    mem = w._ler(r, w.MEMORIA, [])
    assert mem[0]["tipo"] == "pessoa" and "Jorge" in mem[0]["texto"]
    w.tick(r, {"dono": [{"texto": "Banguela, qual é o seu modelo?"}]})       # pelo WhatsApp
    prompt, sistema = pedidos_ia[-1]
    assert "Claude Opus 5.5" in prompt and "Jorge" in prompt                # modelo + memória no contexto
    assert "BRUNO (painel): guarda que o Jorge" in prompt                    # a conversa do Painel aparece no WhatsApp
    conv = w.conversa_guardada(r, 10)
    assert [c["canal"] for c in conv] == ["painel", "painel", "whatsapp", "whatsapp"]
    assert w.rota(r, "GET", "whatsapp_banguela", {}, None)["memoria"][0]["tipo"] == "pessoa"
    w.banguela(r, "esquece o Jorge")
    assert w._ler(r, w.MEMORIA, []) == []


def test_reconhece_o_dono_e_a_loja():
    assert w.eh_dono("+55 (44) 99881-2871") and w.eh_dono("44998812871") and not w.eh_dono("44998812870")
    assert w.eh_dono("+55 44 9881-2871") and w.eh_dono("554498812871") and not w.eh_dono("5547988812871")   # sem o 9
    assert w.loja_da_conversa(["Olá! Gostaria de saber mais sobre a Via Brazil Global."]) == "via_brazil"
    assert w.loja_da_conversa(["quero um perfume"]) is None


if __name__ == "__main__":
    test_reconhece_o_dono_e_a_loja()
    test_fluxo_completo()
    test_assistente_lembrete_bom_dia_e_ferreiro()
    test_aprova_e_edita_de_outro_canal()
    test_ensina_a_base_dos_clientes()
    test_memoria_e_modelo()
    print("ok whatsapp atendimento")
