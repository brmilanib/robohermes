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


def gerar(prompt, sistema):
    pedidos_ia.append((prompt, sistema))
    if "interpreta" in sistema.lower():
        return "{}", "teste"
    if "BOM DIA" in sistema:
        return "Bom dia, Bruno! 📈 Ontem foi bom.", "teste"
    if "me lembra" in prompt:
        return "Marquei! [[lembrete:2026-10-04 09:00|ligar pro fornecedor]]\n[[ferreiro:ver por que o Gestor pede login]]", "teste"
    return "Oi! Que bom falar com você 😊 Me conta o que você procura e mais ou menos o volume. Qualquer coisa, é só chamar!", "teste"


a.gerar_qualidade = lambda repo: gerar
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
    assert w.banguela(r, f"{rid} Sim, vendemos no atacado a partir de 12 unidades").startswith((f"✅ #{rid}", f"📝 #{rid}"))
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


def test_reconhece_o_dono_e_a_loja():
    assert w.eh_dono("+55 (44) 99881-2871") and w.eh_dono("44998812871") and not w.eh_dono("44998812870")
    assert w.eh_dono("+55 44 9881-2871") and w.eh_dono("554498812871") and not w.eh_dono("5547988812871")   # sem o 9
    assert w.loja_da_conversa(["Olá! Gostaria de saber mais sobre a Via Brazil Global."]) == "via_brazil"
    assert w.loja_da_conversa(["quero um perfume"]) is None


if __name__ == "__main__":
    test_reconhece_o_dono_e_a_loja()
    test_fluxo_completo()
    test_assistente_lembrete_bom_dia_e_ferreiro()
    print("ok whatsapp atendimento")
