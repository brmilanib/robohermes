"""Pesquisador nubi (26/09): abre a sessão do agente gerenciado, respeita o teto e guarda o relatório na base."""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import pesquisador as p  # noqa: E402


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
    assert cria["agent"] == p.AGENTE and cria["environment_id"] == "env_1"
    assert cria["budget"]["max_list_cost"] == {"amount": "200", "currency": "USD"}
    assert "TikTok" in cria["initial_events"][0]["content"][0]["text"] and "Shopee?" in cria["initial_events"][0]["content"][0]["text"]
    assert r.resumos[p.CHAVE_AMBIENTE]["dados"]["id"] == "env_1"          # ambiente criado uma vez e guardado
    p.pedir(r, "Outra pergunta sobre a Amazon", "sala")
    assert len([c for c in ch if c[1] == "environments"]) == 1


def test_teto_do_dia_segura_na_fila():
    ch = []
    p._api = _api_falsa(ch)
    r = Repo()
    for i in range(4):                                                     # teto 6 / 2 por pesquisa = 3 abertas
        p.pedir(r, f"pergunta número {i} sobre frete", "sala")
    st = [x["dados"]["status"] for k, x in r.resumos.items() if k.startswith("pesquisa|")]
    assert st.count("rodando") == 3 and st.count("pedida") == 1
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


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
