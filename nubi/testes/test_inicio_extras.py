# -*- coding: utf-8 -*-
"""Card #69: dados novos do Início (dólar do dia, datas de vendas, notícias dos marketplaces e análises dos agentes).
Sem rede e sem banco: a AwesomeAPI, a IA e o Supabase são falsos. Rodar: python3 nubi/testes/test_inicio_extras.py"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.update(OPENAI_API_KEY="x", ANTHROPIC_API_KEY="x")

import ia  # noqa: E402
import nubi  # noqa: E402
import nubi_web  # noqa: E402

COTACAO = {"USDBRL": {"code": "USD", "codein": "BRL", "bid": "5.3120", "ask": "5.3150", "pctChange": "-0.42",
                      "create_date": "2026-09-25 10:00:00"}}


class Repo:
    def __init__(self, tabelas=None):
        self.t = tabelas or {}

    def _eq(self, v):
        return f"eq.{v}"

    def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
        rows = self.t.setdefault(tab, [])
        if metodo == "POST":
            for r in corpo:
                rows[:] = [x for x in rows if x.get("chave") != r.get("chave")] + [r]
            return None
        params = params or {}
        ch = params.get("chave", "")
        if ch.startswith("eq."):
            rows = [r for r in rows if r.get("chave") == ch[3:]]
        elif ch.startswith("not.like."):
            rows = [r for r in rows if not r.get("chave", "").startswith(ch[9:].rstrip("*"))]
        elif ch.startswith("like."):
            rows = [r for r in rows if r.get("chave", "").startswith(ch[5:].rstrip("*"))]
        if tab == "rotinas":
            rows = []
        return list(reversed(rows))[:params.get("limit") or None]


def _limpa_cache():
    nubi_web._DOLAR.update(quando=0.0, valor=None)


def test_dolar_da_api_falsa_com_cache():
    _limpa_cache()
    chamadas = []
    nubi._get_json = lambda url, cab=None: chamadas.append(url) or COTACAO
    d = nubi_web.dolar_do_dia()
    assert d["compra"] == 5.312 and d["venda"] == 5.315 and d["variacao"] == -0.42, d
    nubi_web.dolar_do_dia()
    assert chamadas == [nubi_web.URL_DOLAR], chamadas            # 2ª chamada veio do cache de 30 min


def test_dolar_sem_dados_quando_a_api_falha():
    _limpa_cache()

    def fora(url, cab=None):
        raise nubi.SemConexao("URLError")
    nubi._get_json = fora
    assert nubi_web.dolar_do_dia() is None
    nubi._get_json = lambda url, cab=None: {"items": []}         # resposta estranha também vira "sem dados"
    assert nubi_web.dolar_do_dia() is None


def test_datas_dias_que_faltam():
    ds = {d["nome"]: d for d in nubi_web.datas_vendas(date(2026, 9, 25))}
    assert ds["Dia das Crianças"] == {"nome": "Dia das Crianças", "data": "2026-10-12", "faltam": 17}
    assert ds["Black Friday"]["data"] == "2026-11-27"            # 4ª quinta de novembro (26) + 1
    assert ds["Natal"]["faltam"] == 91
    assert nubi_web.datas_vendas(date(2026, 9, 25))[0]["nome"] == "10.10"   # ordenado pelo que está mais perto


def test_datas_virada_do_ano():
    ds = {d["nome"]: d for d in nubi_web.datas_vendas(date(2026, 12, 26))}
    assert ds["Natal"]["data"] == "2027-12-25" and ds["Natal"]["faltam"] == 364
    assert ds["Dia do Consumidor"]["data"] == "2027-03-15" and ds["Dia do Consumidor"]["faltam"] == 79
    assert ds["Dia das Mães"]["data"] == "2027-05-09"            # 2º domingo de maio de 2027
    assert ds["Dia dos Pais"]["data"] == "2027-08-08"
    assert all(d["faltam"] >= 0 for d in ds.values())
    assert {d["nome"]: d for d in nubi_web.datas_vendas(date(2026, 12, 25))}["Natal"]["faltam"] == 0   # hoje é o dia


def test_noticias_ia_falsa_grava_uma_vez_por_dia():
    perguntas = []

    def falsa(pergunta, web=True, max_tokens=1500, qual=None, sistema=None):
        perguntas.append(web)
        return {"noticias": [{"marketplace": "Shopee", "titulo": "Nova taxa de frete", "resumo": "Sobe em outubro.",
                              "fonte": "https://exemplo.com/a"},
                             {"marketplace": "Amazon", "titulo": "Sem fonte", "resumo": "descartada"}]
                + [{"marketplace": "ML", "titulo": f"N{i}", "fonte": f"https://x/{i}"} for i in range(10)]}, [], "claude"
    ia.perguntar_json = falsa
    repo = Repo()
    x = nubi_web.gerar_noticias(repo)
    assert x["novo"] and x["n"] == 8, x                           # no máximo 8 e só com fonte
    assert perguntas == [True]                                    # com busca na web
    reg = repo.t["ia_resumos"]
    assert len(reg) == 1 and reg[0]["chave"] == f"noticias|{nubi_web._agora_br().date().isoformat()}", reg
    assert reg[0]["dados"]["noticias"][0]["fonte"] == "https://exemplo.com/a"
    assert "[fonte](https://exemplo.com/a)" in reg[0]["texto"] and "Sem fonte" not in reg[0]["texto"]
    assert nubi_web.gerar_noticias(repo) == {"chave": reg[0]["chave"], "novo": False}
    assert perguntas == [True] and len(repo.t["ia_resumos"]) == 1  # 2ª vez no mesmo dia não chama a IA


def test_rota_devolve_os_4_blocos_com_sem_dados():
    _limpa_cache()
    nubi._get_json = lambda url, cab=None: {}
    x = nubi_web.inicio_extras(Repo())
    assert set(x) == {"dolar", "datas", "noticias", "analises"}, x
    assert x["dolar"] is None and x["noticias"] is None and x["analises"] is None and x["datas"]
    _limpa_cache()
    nubi._get_json = lambda url, cab=None: COTACAO
    repo = Repo({"ia_resumos": [{"chave": "vendedores|2026-09-23", "texto": "resumo do dia", "ia": "ChatGPT"},
                                {"chave": "noticias|2026-09-25", "texto": "-",
                                 "dados": {"noticias": [{"titulo": "T", "fonte": "https://f"}]}}],
                 "auditorias": [{"data": "2026-09-25", "resumo": "3 conferências ok"}]})
    x = nubi_web.inicio_extras(repo)
    assert x["dolar"]["venda"] == 5.315
    assert x["noticias"] == {"data": "2026-09-25", "itens": [{"titulo": "T", "fonte": "https://f"}]}
    assert [r["chave"] for r in x["analises"]["resumos"]] == ["vendedores|2026-09-23"]   # notícias fora das análises
    assert x["analises"]["auditoria"]["resumo"] == "3 conferências ok"


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
