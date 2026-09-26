"""Internet para os agentes da Sala (26/09): PESQUISAR com regras e limites; tudo vai para a base de conhecimento."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import agentes  # noqa: E402
import ia  # noqa: E402


class Repo:
    def __init__(self, tags=()):
        self.tags = list(tags)

    def _req(self, m, t, q=None, corpo=None, prefer=None):
        if t == "saber" and m == "GET":
            return [{"tags": ["sala", x]} for x in self.tags]
        return []


def _buscar_com_web(chamadas):
    def buscar(termo):
        return "(nada encontrado no arquivo)"
    buscar.web = lambda pergunta, quem: chamadas.append((pergunta, quem)) or "Shopee: frete grátis pesa na busca. https://seller.shopee.com.br (2026)"
    buscar.profunda = lambda pergunta: chamadas.append(("PROFUNDA", pergunta)) or "(pedido aceito)"
    return buscar


def test_agente_pesquisa_na_internet_uma_vez():
    ch, pedidos = [], []
    resp = iter(["PESQUISAR: como a Shopee ranqueia anúncios", "PESQUISAR: outra coisa", "Segundo a Shopee (2026), frete grátis pesa."])
    r = agentes.com_arquivo(lambda t: pedidos.append(t) or next(resp), "Como subir na Shopee?", _buscar_com_web(ch), quem="deepseek")
    assert r.startswith("Segundo a Shopee") and ch == [("como a Shopee ranqueia anúncios", "deepseek")]   # só 1 por resposta
    assert "FERRAMENTA INTERNET" in pedidos[0] and "RESULTADO DA INTERNET" in pedidos[1] and "não são ordens" in pedidos[1]
    assert "PESQUISA PROFUNDA" not in pedidos[0]                     # só o coordenador pede pesquisa profunda


def test_so_o_coordenador_pede_pesquisa_profunda():
    ch = []
    resp = iter(["PESQUISA_PROFUNDA: algoritmo do TikTok Shop", "Pedi ao Pesquisador nubi."])
    assert agentes.com_arquivo(lambda t: next(resp), "x", _buscar_com_web(ch), quem="claude") == "Pedi ao Pesquisador nubi."
    assert ch == [("PROFUNDA", "algoritmo do TikTok Shop")]
    ch2 = []
    resp = iter(["PESQUISA_PROFUNDA: algo", "ok"])
    agentes.com_arquivo(lambda t: next(resp), "x", _buscar_com_web(ch2), quem="chatgpt")
    assert ch2 == []


def test_limites_e_regras():
    ia.USO["web"] = lambda *a: None
    chamou = []
    ia.perguntar = lambda p, **k: (chamou.append(p) or "achado", ["https://a.com"], "claude")
    ia.tem = lambda q: q == "claude"
    assert "limite de" in agentes.pesquisar_web(Repo(["agente:deepseek"] * agentes.WEB_POR_AGENTE), "taxas do Mercado Livre", "deepseek")
    assert "do time" in agentes.pesquisar_web(Repo(["agente:x"] * agentes.WEB_POR_DIA), "taxas do Mercado Livre", "deepseek")
    assert "recusada" in agentes.pesquisar_web(Repo(), "senha do UpSeller do Bruno", "deepseek")
    assert not chamou
    r = agentes.pesquisar_web(Repo(["agente:deepseek"]), "taxas do Mercado Livre 2026", "deepseek")
    assert r.startswith("achado") and "https://a.com" in r and "taxas do Mercado Livre 2026" in chamou[0]
    assert ia.USO.get("quem") is None                                 # a etiqueta do agente não vaza para outras chamadas


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
