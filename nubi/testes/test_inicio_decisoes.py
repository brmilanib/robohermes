# -*- coding: utf-8 -*-
"""Card #24: painel "Decisões de hoje" na Início (risco de dado, oportunidade de preço, execução).
Sem rede e sem banco: repositório falso. Rodar: python3 nubi/testes/test_inicio_decisoes.py"""
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.update(OPENAI_API_KEY="x", ANTHROPIC_API_KEY="x")

import nubi_web  # noqa: E402


class Repo:
    def __init__(self, tabelas=None, falha=None):
        self.t = tabelas or {}
        self.falha = set(falha or ())          # nomes de tabela que devem "quebrar" (RuntimeError)

    def _eq(self, v):
        return f"eq.{v}"

    def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
        if tab in self.falha:
            raise RuntimeError(f"{tab} fora do ar")
        rows = list(self.t.get(tab, []))
        if tab == "auditorias":
            rows = sorted(rows, key=lambda r: r["data"], reverse=True)
        limit = (params or {}).get("limit")
        return rows[:limit] if limit else rows

    def _todos(self, tab, params=None, metodo="GET", corpo=None):
        if tab in self.falha:
            raise RuntimeError(f"{tab} fora do ar")
        rows = list(self.t.get(tab, []))
        params = params or {}
        status = params.get("status", "")
        if status.startswith("eq."):
            rows = [r for r in rows if r.get("status") == status[3:]]
        inicio = params.get("inicio", "")
        if inicio.startswith("gte."):
            rows = [r for r in rows if r.get("inicio", "") >= inicio[4:]]
        return rows


def _sem_painel():
    nubi_web._painel_dia = lambda repo, d=None: {"tem": False}


def test_sem_nenhuma_base_tudo_vira_sem_dados_nunca_zero():
    original = nubi_web._painel_dia
    _sem_painel()
    try:
        x = nubi_web.inicio_decisoes(Repo(falha={"reuniao_tarefas", "agentes_uso"}))
    finally:
        nubi_web._painel_dia = original
    assert x["risco"]["pendentes"] is None, x["risco"]           # sem painel do dia: sem dados, não 0 pendentes
    assert x["risco"]["alertas"] is None, x["risco"]             # nunca rodou a auditoria: sem dados
    assert x["preco"]["sem_dados"] is True and x["preco"]["motivo"]
    assert x["execucao"]["aguardando_aprovacao"] is None, x["execucao"]   # consulta falhou: sem dados, não 0
    assert x["execucao"]["travadas_por_custo"]["custo_hoje"] is None      # consulta falhou: sem dados, não US$ 0
    assert x["execucao"]["travadas_por_custo"]["total"] == 0     # sem teto de custo implementado (card #10): nunca lista


def test_pendentes_e_alertas_da_auditoria():
    original = nubi_web._painel_dia
    nubi_web._painel_dia = lambda repo, d=None: {
        "tem": True, "data": "2026-09-25", "sem_coleta": ["AUMA", "LOJA X"],
        "vendedores": [], "mais_venderam": [], "mais_cairam": [], "produtos_alta": [], "produtos_queda": [], "total": {}}
    repo = Repo({"auditorias": [{"data": "2026-09-25", "conferencias": [
        {"nivel": "erro", "area": "dados", "titulo": "X em 24/09: tabela do grupo x export"},
        {"nivel": "alerta", "area": "coleta", "titulo": "Y: coleta pendente"},
        {"nivel": "info", "area": "categoria", "titulo": "Instantâneo de categorias"},
    ]}]})
    try:
        x = nubi_web.inicio_decisoes(repo)
    finally:
        nubi_web._painel_dia = original
    pend = x["risco"]["pendentes"]
    assert pend == {"total": 2, "itens": [{"vendedor": "AUMA", "dia": "2026-09-25"}, {"vendedor": "LOJA X", "dia": "2026-09-25"}],
                     "fonte": "Central > Coletor", "referencia": "2026-09-25"}, pend
    alr = x["risco"]["alertas"]
    assert alr["total"] == 2, alr                                 # info não conta como risco
    assert {a["titulo"] for a in alr["itens"]} == {"X em 24/09: tabela do grupo x export", "Y: coleta pendente"}
    assert alr["referencia"] == "2026-09-25"


def test_nenhuma_pendencia_e_nenhum_alerta_nao_e_sem_dados():
    original = nubi_web._painel_dia
    nubi_web._painel_dia = lambda repo, d=None: {
        "tem": True, "data": "2026-09-25", "sem_coleta": [],
        "vendedores": [], "mais_venderam": [], "mais_cairam": [], "produtos_alta": [], "produtos_queda": [], "total": {}}
    repo = Repo({"auditorias": [{"data": "2026-09-25", "conferencias": []}]})
    try:
        x = nubi_web.inicio_decisoes(repo)
    finally:
        nubi_web._painel_dia = original
    assert x["risco"]["pendentes"] == {"total": 0, "itens": [], "fonte": "Central > Coletor", "referencia": "2026-09-25"}
    assert x["risco"]["alertas"] == {"total": 0, "itens": [], "fonte": "Central > Auditoria", "referencia": "2026-09-25"}


def test_execucao_aguardando_aprovacao_e_custo_do_dia():
    original = nubi_web._painel_dia
    _sem_painel()
    hoje = nubi_web._agora_br().date()
    ontem = hoje - timedelta(days=1)
    repo = Repo({
        "reuniao_tarefas": [
            {"id": 90, "titulo": "Ideia nova", "responsavel": None, "status": "proposta"},
            {"id": 91, "titulo": "Outra ideia", "responsavel": "astra", "status": "proposta"},
            {"id": 3, "titulo": "Já aprovada", "responsavel": "claude_code", "status": "aprovada"},
        ],
        "agentes_uso": [
            {"inicio": f"{hoje.isoformat()}T12:00:00+00:00", "custo_usd": 0.5},   # hoje (meio-dia UTC = manhã BRT)
            {"inicio": f"{hoje.isoformat()}T12:00:00+00:00", "custo_usd": 0.25},
            {"inicio": f"{ontem.isoformat()}T12:00:00+00:00", "custo_usd": 9.0},  # ontem: fora do dia
        ],
    })
    try:
        x = nubi_web.inicio_decisoes(repo)
    finally:
        nubi_web._painel_dia = original
    ap = x["execucao"]["aguardando_aprovacao"]
    assert ap["total"] == 2 and {t["id"] for t in ap["itens"]} == {90, 91}, ap   # só as 'proposta', não a 'aprovada'
    trav = x["execucao"]["travadas_por_custo"]
    assert trav["custo_hoje"] == 0.75, trav              # soma só de hoje (0.5+0.25), nunca conta o de ontem
    assert trav["total"] == 0 and trav["itens"] == []    # sem teto de custo registrado (card #10): nunca inventa bloqueio


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
