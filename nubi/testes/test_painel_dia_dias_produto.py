# -*- coding: utf-8 -*-
"""Card #106: em _painel_dia, a média de cada produto usava o número global de datas da janela (pbase[k]['v'] / n),
em vez dos dias em que o(s) vendedor(es) daquele produto realmente têm arquivo (dia sem coleta não entra no
denominador; dia sem venda entra como zero). Isso deflacionava a média de produtos vendidos por um vendedor com
menos dias de coleta do que os outros na mesma janela. O rótulo fixo 'base': '7 dias' também não batia com o número
real de dias da janela (dias_base).
Rodar: python3 testes/test_painel_dia_dias_produto.py, na pasta nubi."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.update(OPENAI_API_KEY="x", ANTHROPIC_API_KEY="x")

import nubi_web  # noqa: E402


def linha_vend(titulo, unidades, vendas, preco, marca="M"):
    return {"titulo": titulo, "marca": marca, "unidades": unidades, "vendas": vendas, "preco": preco,
            "estado": "active", "tipo_pub": "classico", "full": False}


class RepoPainel:
    """vend_vendas_dia em memória, upsert por (vendedor, data) como o Supabase real (merge-duplicates)."""

    def __init__(self):
        self.vendas = []
        self.auditorias = []

    def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
        if tab == "vend_grupo_dia" and metodo == "GET":
            return []
        if tab == "auditorias":
            if metodo == "GET":
                return self.auditorias
            self.auditorias = [dict(corpo[0])]
            return corpo
        if tab == "vend_vendas_dia" and metodo == "POST":
            for novo in corpo:
                for i, r in enumerate(self.vendas):
                    if r["vendedor"] == novo["vendedor"] and str(r["data"])[:10] == str(novo["data"])[:10]:
                        self.vendas[i] = novo
                        break
                else:
                    self.vendas.append(novo)
            return corpo
        if tab == "vend_vendas_dia" and metodo == "GET":
            return sorted(self.vendas, key=lambda r: r["data"], reverse=True)[:1]
        return []

    def _todos(self, tab, params=None, metodo="GET", corpo=None):
        if tab == "vend_vendas_dia":
            desde = (params or {}).get("data", "gte.").split("gte.", 1)[-1]
            return [r for r in self.vendas if str(r["data"])[:10] >= desde]
        return []          # produto_grupos etc.: sem agrupamento no teste

    def _eq(self, v):
        return f"eq.{v}"


def _publicar(r, vendedor, dia, itens_raw):
    linhas = [linha_vend(*a) for a in itens_raw]
    nubi_web.vendedores.ler_vendedor = lambda corpo, nome: (linhas, vendedor, dia[:7])
    resp = nubi_web.rota_vendedores(r, "POST", "vend_dia", {"arquivo": "a.xlsx", "ate": dia}, b"x")
    assert resp["ok"], resp


def test_media_do_produto_usa_os_dias_do_vendedor_que_vendeu_nao_o_global():
    r = RepoPainel()
    # GRANDE: 7 dias seguidos (16 a 22) vendendo Produto A + hoje (23)
    for dia in [f"2026-09-{d:02d}" for d in range(16, 23)]:
        _publicar(r, "GRANDE", dia, [("Produto A", 10, 1000, 100)])
    _publicar(r, "GRANDE", "2026-09-23", [("Produto A", 10, 1000, 100)])
    # PEQUENO: só 4 dos mesmos 7 dias (19 a 22) vendendo Produto B (exclusivo dele) + hoje
    for dia in [f"2026-09-{d:02d}" for d in range(19, 23)]:
        _publicar(r, "PEQUENO", dia, [("Produto B", 10, 1000, 100)])
    _publicar(r, "PEQUENO", "2026-09-23", [("Produto B", 10, 1000, 100)])

    resp = nubi_web._painel_dia(r, "2026-09-23")
    assert resp["dias_base"] == 7, resp["dias_base"]      # janela global tem 7 dias distintos (por causa da GRANDE)

    produto_b = next(x for x in resp["produtos_alta"] if x["produto"] == "Produto B")
    # PEQUENO só tem 4 dias de coleta: a média do produto dela é 4000/4=1000, nunca 4000/7 (~571,43)
    assert produto_b["dias_base"] == 4, produto_b
    assert produto_b["media"] == 1000, produto_b

    produto_a = next(x for x in resp["produtos_alta"] if x["produto"] == "Produto A")
    assert produto_a["dias_base"] == 7 and produto_a["media"] == 1000, produto_a


def test_vendedor_sem_historico_conta_no_total_mas_nao_na_media():
    r = RepoPainel()
    for dia in [f"2026-09-{d:02d}" for d in range(16, 23)]:
        _publicar(r, "GRANDE", dia, [("Produto A", 10, 1000, 100)])
    _publicar(r, "GRANDE", "2026-09-23", [("Produto A", 10, 1000, 100)])
    # NOVATO: só vende hoje, sem nenhum dia anterior (sem média/baseline)
    _publicar(r, "NOVATO", "2026-09-23", [("Produto C", 3, 300, 100)])

    resp = nubi_web._painel_dia(r, "2026-09-23")
    novato = next(x for x in resp["vendedores"] if x["vendedor"] == "NOVATO")
    assert novato["media"] is None, novato          # sem histórico: sem_dados na média, não vira zero

    # a venda real de hoje (GRANDE + NOVATO) continua inteira no total, mesmo sem histórico de todo mundo
    assert resp["total"]["v"] == 1300, resp["total"]
    assert resp["total"]["media"] == 1000, resp["total"]      # só GRANDE tem histórico pra compor a média
    # a variação (var) compara só quem tem os dois lados (GRANDE): NOVATO não pode inflar o % só por não ter baseline
    assert resp["total"]["var"] == 0, resp["total"]


def test_rotulo_base_mostra_o_numero_real_de_dias_nao_7_fixo():
    r = RepoPainel()
    # SOLO: único vendedor, só 4 dos 7 dias possíveis da janela (19 a 22) + hoje
    for dia in [f"2026-09-{d:02d}" for d in range(19, 23)]:
        _publicar(r, "SOLO", dia, [("Produto D", 10, 1000, 100)])
    _publicar(r, "SOLO", "2026-09-23", [("Produto D", 10, 1000, 100)])

    resp = nubi_web._painel_dia(r, "2026-09-23")
    assert resp["dias_base"] == 4, resp["dias_base"]
    assert resp["base"] == "4 dias", resp["base"]      # antes vinha fixo "7 dias", não batia com dias_base


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
