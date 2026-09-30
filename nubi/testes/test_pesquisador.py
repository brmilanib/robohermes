"""Pesquisador nubi (26/09): abre a sessão do agente gerenciado, respeita o teto e guarda o relatório na base."""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
os.environ.setdefault("DEEPSEEK_API_KEY", "x")
import pesquisador as p  # noqa: E402

p.PELO_ASTRA = False        # os testes abaixo são do agente da Anthropic; o do Astra está em test_pesquisa_pelo_astra


class Repo:
    def __init__(self):
        self.resumos, self.saber, self.sala, self.uso = {}, [], [], []

    def _eq(self, v):
        return f"eq.{v}"

    def _req(self, m, t, q=None, corpo=None, prefer=None):
        q = q or {}
        if t == "ia_resumos":
            if m == "POST":
                for r in corpo:
                    self.resumos[r["chave"]] = dict(r, criado_em=datetime.now(timezone.utc).isoformat())
                return []
            if m == "PATCH":
                self.resumos[q["chave"][3:]].update(corpo)
                return []
            if q.get("chave", "").startswith("eq."):
                r = self.resumos.get(q["chave"][3:])
                return [r] if r else []
            xs = [r for k, r in self.resumos.items() if k.startswith("pesquisa|")]
            if "dados->>status" in q:
                xs = [r for r in xs if r["dados"].get("status") == q["dados->>status"][3:]]
            return xs
        if t == "saber":
            self.saber += corpo
        elif t == "reuniao_mensagens":
            self.sala += corpo
        elif t == "agentes_uso":
            self.uso += corpo
        elif t == "tarefa_eventos":
            self.__dict__.setdefault("passos", []).extend(corpo)
        return []


def _api_falsa(chamadas, status="idle"):
    def api(metodo, caminho, corpo=None, timeout=60):
        chamadas.append((metodo, caminho, corpo))
        if caminho == "environments":
            return {"id": "env_1"}
        if caminho == "sessions":
            return {"id": f"sesn_{len(chamadas)}"}
        if caminho.endswith("/events?limit=1000"):
            return {"data": [{"type": "user.message", "content": [{"type": "text", "text": "pergunta"}]},
                             {"type": "agent.message", "content": [{"type": "text", "text": "Vou pesquisar."}]},
                             {"type": "agent.message", "content": [{"type": "text", "text": "## Resumo\nNo Mercado Livre e na Shopee… "
                                                                    "fonte https://vendedores.mercadolivre.com.br/x. " + "a" * 700}]}],
                    "next_page": None}
        if caminho.startswith("sessions/") and metodo == "GET":
            return {"id": caminho.split("/")[1], "status": status, "usage": {"list_cost": {"amount": "137", "currency": "USD"},
                                                                             "input_tokens": 1000, "output_tokens": 500}}
        return {}
    return api


def test_pedir_abre_sessao_com_teto_e_contexto():
    ch = []
    p._api = _api_falsa(ch)
    r = Repo()
    chave = p.pedir(r, "Como funciona o rankeamento na Shopee?", "sala")
    assert r.resumos[chave]["dados"]["status"] == "rodando"
    cria = [c for c in ch if c[1] == "sessions"][0][2]
    assert cria["agent"] == {"type": "agent_with_overrides", "id": p.AGENTE, "model": "claude-sonnet-5"} and cria["environment_id"] == "env_1"
    assert cria["budget"]["max_list_cost"] == {"amount": "75", "currency": "USD"}
    assert "NO MÁXIMO 3 fontes" in cria["initial_events"][0]["content"][0]["text"]
    assert "TikTok" in cria["initial_events"][0]["content"][0]["text"] and "Shopee?" in cria["initial_events"][0]["content"][0]["text"]
    assert r.resumos[p.CHAVE_AMBIENTE]["dados"]["id"] == "env_1"          # ambiente criado uma vez e guardado
    p.pedir(r, "Outra pergunta sobre a Amazon", "sala")
    assert len([c for c in ch if c[1] == "environments"]) == 1


def test_teto_do_dia_segura_na_fila():
    ch = []
    p._api = _api_falsa(ch)
    r = Repo()
    for i in range(5):                                                     # teto 3 / 0,75 por pesquisa = 4 abertas
        p.pedir(r, f"pergunta número {i} sobre frete", "sala")
    st = [x["dados"]["status"] for k, x in r.resumos.items() if k.startswith("pesquisa|")]
    assert st.count("rodando") == 4 and st.count("pedida") == 1
    assert any("teto do dia" in m["texto"] for m in r.sala)


def test_conferir_guarda_relatorio_na_base_e_na_sala():
    ch = []
    p._api = _api_falsa(ch)
    r = Repo()
    chave = p.pedir(r, "Etiquetas do Mercado Livre", "laboratorio")
    r.resumos[chave]["dados"]["iniciada_em"] = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    assert "concluída" in p.conferir(r, forcar=True)
    d = r.resumos[chave]
    assert d["dados"]["status"] == "feita" and d["dados"]["custo_usd"] == 1.37 and d["texto"].startswith("## Resumo")
    s = r.saber[0]
    assert s["fonte_tabela"] == "pesquisa_profunda" and s["tipo"] == "pesquisa_web"
    assert "https://vendedores.mercadolivre.com.br/x" in s["links"] and "shopee" in s["tags"] and "mercado_livre" in s["tags"]
    assert any("Pesquisa pronta" in m["texto"] for m in r.sala) and r.uso[0]["custo_usd"] == 1.37
    assert any(c[1].endswith("/archive") for c in ch)
    assert p.gasto_hoje(r) == 1.37                                         # custo real substitui o teto reservado


def test_nao_fecha_sessao_recem_criada_nem_rodando():
    ch = []
    p._api = _api_falsa(ch, status="running")
    r = Repo()
    chave = p.pedir(r, "Buy box na Amazon Brasil", "sala")
    p.conferir(r, forcar=True)
    assert r.resumos[chave]["dados"]["status"] == "rodando" and not r.saber
    p._api = _api_falsa(ch, status="idle")                                  # idle logo após criar (< 60 s) ainda não fecha
    p.conferir(r, forcar=True)
    assert r.resumos[chave]["dados"]["status"] == "rodando"


def test_pesquisa_pelo_astra():
    """30/09 (Bruno): o Pesquisador é o Astra (busca na web da OpenAI), na hora; falhou, volta para a fila e tenta 2 vezes."""
    import ia
    p.PELO_ASTRA = True
    velho = ia.perguntar
    pedidos = []

    def falso(pergunta, web=True, max_tokens=1500, qual=None, modelo=None, **k):
        pedidos.append((web, qual, modelo))
        if qual == "ollama":                                  # o Hermes resume as páginas da busca grátis
            assert "FONTES:" in pergunta and "https://blog.exemplo.com/full" in pergunta
            return "## Resumo\nO Full ajuda [1] https://blog.exemplo.com/full", [], "ollama"
        return "## Resumo\nNo Mercado Livre o Full pesa no ranking.", ["https://vendedores.mercadolivre.com.br/x"], "chatgpt"
    ia.perguntar = falso
    velho_web = ia.ollama_web
    ia.ollama_web = lambda pergunta, max_resultados=5: [{"titulo": "Full no ML", "url": "https://blog.exemplo.com/full", "texto": "O Full…"}]
    try:
        r = Repo()
        chave = p.pedir(r, "Como o Full afeta o ranking no Mercado Livre?")
        d = r.resumos[chave]["dados"]
        d = r.resumos[chave]["dados"]
        assert d["status"] == "feita" and d["motor"] == "astra" and pedidos[0] == (True, "chatgpt", "gpt-6-astra"), (d, pedidos)
        # 30/09 (Bruno): o Hermes pesquisa junto, grátis (busca do Ollama + gpt-oss), e posta como Hermes
        assert pedidos[1] == (False, "ollama", None) and d["hermes"]["status"] == "feita", (d, pedidos)
        assert [m["autor"] for m in r.sala][-2:] == ["Pesquisador nubi", "Hermes"] and "grátis" in r.sala[-1]["texto"]
        assert len(r.saber) == 2 and r.saber[1]["autor"] == "Hermes"
        assert "Fontes" in r.resumos[chave]["texto"] and "vendedores.mercadolivre.com.br" in r.resumos[chave]["texto"]
        assert r.saber[0]["fonte_tabela"] == "pesquisa_profunda" and "(Astra)" in r.sala[-2]["texto"]
        # sem crédito / fora do ar: fica na fila e, na 2ª falha, vira erro com aviso na Sala
        ia.perguntar = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("HTTP 429"))
        r2 = Repo()
        ch2 = p.pedir(r2, "Outra pergunta sobre a Shopee")
        assert r2.resumos[ch2]["dados"]["status"] == "pedida"
        p._ULTIMA["t"] = 0
        p.conferir(r2, forcar=True)
        assert r2.resumos[ch2]["dados"]["status"] == "erro" and any("não conseguiu" in m["texto"] for m in r2.sala if m["autor"] == "Pesquisador nubi")
        assert sum(1 for m in r2.sala if m["autor"] == "Hermes") == 1           # o Hermes não repete na nova tentativa
    finally:
        ia.perguntar = velho
        ia.ollama_web = velho_web
        p.PELO_ASTRA = False


def test_pesquisa_de_um_card_entra_no_card_e_hermes_espera_se_o_astra_demorou():
    """30/09 (Bruno, card #126): pedida de dentro de um card, a pesquisa do Astra e a do Hermes viram passos do card; o
    Astra espera até TIMEOUT_ASTRA e, se demorou, o Hermes fica para a próxima passada do conferir."""
    import ia
    p.PELO_ASTRA = True
    velho, velho_web, velho_tempo = ia.perguntar, ia.ollama_web, p.HERMES_DEPOIS_S
    vistos = []

    def falso(pergunta, web=True, max_tokens=1500, qual=None, modelo=None, **k):
        vistos.append(k.get("timeout"))
        if qual == "ollama":
            return "## Hermes\nAchei [1] https://a.b/c", [], "ollama"
        if qual == "deepseek":
            assert ia.tem("deepseek") and "RELATÓRIO DO ASTRA:\n## Astra" in pergunta   # liberado só aqui, com o relatório
            return "## DeepSeek\n1. Testar o Actor da Apify [a confirmar]", [], "deepseek"
        assert "até 12" in pergunta and "NO MÁXIMO 3 fontes" not in pergunta            # o Astra lê mais fontes
        return "## Astra\nConectores: Apify.", ["https://apify.com/x"], "chatgpt"
    ia.perguntar = falso
    ia.ollama_web = lambda pergunta, max_resultados=5: [{"titulo": "t", "url": "https://a.b/c", "texto": "x"}]
    try:
        r = Repo()
        p.HERMES_DEPOIS_S = -1                                 # qualquer demora conta como "demorou"
        chave = p.pedir(r, "Quais conectores trazem os anúncios de um vendedor?", origem="card #126")
        d = r.resumos[chave]["dados"]
        assert vistos[0] == p.TIMEOUT_ASTRA and d["status"] == "feita" and d["hermes"] == {"status": "pendente"}, (vistos, d)
        assert [x["autor"] for x in r.passos] == ["astra"] and r.passos[0]["tarefa_id"] == 126 and "Apify" in r.passos[0]["texto"]
        p._ULTIMA["t"] = 0
        assert "hermes" in p.conferir(r, forcar=True)
        assert r.resumos[chave]["dados"]["hermes"]["status"] == "feita"
        assert [x["autor"] for x in r.passos] == ["astra", "hermes", "deepseek"] and "grátis" in r.passos[1]["texto"]
        assert "Visão do DeepSeek" in r.passos[2]["texto"] and r.resumos[chave]["dados"]["deepseek"]["status"] == "feita"
        p._ULTIMA["t"] = 0
        p.conferir(r, forcar=True)
        assert len(r.passos) == 3                              # não repete o Hermes nem o DeepSeek
        # pesquisa da Sala (sem card): nenhum passo em card
        p.HERMES_DEPOIS_S = 100
        r2 = Repo()
        p.pedir(r2, "Pergunta comum da Sala sem card")
        assert not getattr(r2, "passos", []) and r2.resumos[list(r2.resumos)[0]]["dados"]["hermes"]["status"] == "feita"
    finally:
        ia.perguntar, ia.ollama_web, p.HERMES_DEPOIS_S = velho, velho_web, velho_tempo
        p.PELO_ASTRA = False


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
