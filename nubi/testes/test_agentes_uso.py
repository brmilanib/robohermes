# -*- coding: utf-8 -*-
"""
Uso auditável da aba Central > Agentes (card #18): Ontem, seletor Hoje/7/30 dias, detalhamento por rotina
e "Sem dados" (nunca zero) quando não há chamada no período. Sem tabela nem cron novos: tudo calculado sob
demanda a partir de agentes_uso (mesma tabela que já alimenta Hoje/No mês), o que já garante idempotência
(nenhuma escrita: rodar duas vezes nunca duplica nem muda o total).

Rodar: python3 testes/test_agentes_uso.py (na pasta nubi).
"""
import copy
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import nubi_web  # noqa: E402


class Repo:
    def __init__(self, agentes, usos, mensagens=None):
        self.agentes = agentes
        self.usos = usos
        self.mensagens = mensagens or []

    def _todos(self, tab, params=None, metodo="GET", corpo=None):
        if tab == "agentes":
            return copy.deepcopy(self.agentes)
        if tab == "agentes_uso":
            gte = (params or {}).get("inicio", "gte.").split("gte.", 1)[1]
            return copy.deepcopy([u for u in self.usos if u["inicio"] >= gte])
        return []

    def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
        if tab == "reuniao_mensagens":
            return self.mensagens
        return []


UM_AGENTE = [{"id": "deepseek", "nome": "DeepSeek", "ordem": 1}]


def _uso(dia_br, hora_br=12, **k):
    """Uma linha de agentes_uso cujo 'inicio' (UTC) cai no dia de Brasília 'dia_br' às 'hora_br'."""
    inicio = dia_br.replace(hour=hora_br) + timedelta(hours=3)   # Brasília -> UTC
    return dict({"agente": "deepseek", "modelo": "deepseek", "origem": "sala", "inicio": inicio.isoformat(),
                 "fim": inicio.isoformat(), "ok": True, "tokens_in": 100, "tokens_out": 50, "custo_usd": 0.01}, **k)


def test_cutoff_utc_menos_3():
    # 02:00 UTC do dia 23 é 23:00 de Brasília do dia 22 (regra do teste do card #18)
    assert nubi_web._br("2026-09-23T02:00:00+00:00").date().isoformat() == "2026-09-22"
    assert nubi_web._br("2026-09-23T04:00:00+00:00").date().isoformat() == "2026-09-23"


def test_ontem_hoje_e_janelas_7_30_dias():
    hoje = nubi_web._agora_br().replace(hour=0, minute=0, second=0, microsecond=0)
    usos = [_uso(hoje, custo_usd=0.01), _uso(hoje, custo_usd=0.02),          # 2 chamadas hoje
            _uso(hoje - timedelta(days=1), custo_usd=0.03),                  # 1 chamada ontem
            _uso(hoje - timedelta(days=5), custo_usd=0.04),                  # dentro dos 7 dias, fora de ontem/hoje
            _uso(hoje - timedelta(days=20), custo_usd=0.05),                 # dentro dos 30 dias, fora dos 7
            _uso(hoje - timedelta(days=40), custo_usd=0.06)]                 # fora de tudo (fora até da janela buscada)
    r = nubi_web._agentes_painel(Repo(UM_AGENTE, usos))
    a = r["agentes"][0]
    assert a["hoje"]["chamadas"] == 2 and round(a["hoje"]["custo"], 2) == 0.03, a["hoje"]
    assert a["ontem"]["chamadas"] == 1 and round(a["ontem"]["custo"], 2) == 0.03, a["ontem"]
    assert a["dia7"]["chamadas"] == 4, a["dia7"]        # hoje(2) + ontem(1) + 5 dias atrás(1)
    assert a["dia30"]["chamadas"] == 5, a["dia30"]       # os 4 acima + 20 dias atrás
    assert round(a["dia30"]["custo"], 2) == 0.15, a["dia30"]


def test_sem_chamada_no_periodo_fica_com_chamadas_zero_nunca_numero_inventado():
    hoje = nubi_web._agora_br().replace(hour=0, minute=0, second=0, microsecond=0)
    usos = [_uso(hoje - timedelta(days=15))]   # só dentro dos 30 dias
    r = nubi_web._agentes_painel(Repo(UM_AGENTE, usos))
    a = r["agentes"][0]
    for periodo in ("hoje", "ontem", "dia7"):
        assert a[periodo] == {"chamadas": 0, "tokens_in": 0, "tokens_out": 0, "custo": 0.0, "detalhe": []}, (periodo, a[periodo])
    assert a["dia30"]["chamadas"] == 1


def test_detalhamento_por_rotina_soma_igual_ao_total():
    hoje = nubi_web._agora_br().replace(hour=0, minute=0, second=0, microsecond=0)
    usos = [_uso(hoje, origem="sala", custo_usd=0.02), _uso(hoje, origem="sala", custo_usd=0.03),
            _uso(hoje, origem="auditoria", custo_usd=0.05)]
    r = nubi_web._agentes_painel(Repo(UM_AGENTE, usos))
    hoje_r = r["agentes"][0]["hoje"]
    assert hoje_r["chamadas"] == 3 and round(hoje_r["custo"], 2) == 0.10, hoje_r
    assert sum(d["chamadas"] for d in hoje_r["detalhe"]) == hoje_r["chamadas"], hoje_r["detalhe"]
    assert round(sum(d["custo"] for d in hoje_r["detalhe"]), 2) == round(hoje_r["custo"], 2), hoje_r["detalhe"]
    por_origem = {d["origem"]: d for d in hoje_r["detalhe"]}
    assert por_origem["sala"]["chamadas"] == 2 and por_origem["auditoria"]["chamadas"] == 1


def test_rodar_duas_vezes_nao_muda_nem_duplica():
    hoje = nubi_web._agora_br().replace(hour=0, minute=0, second=0, microsecond=0)
    usos = [_uso(hoje), _uso(hoje - timedelta(days=1)), _uso(hoje - timedelta(days=10))]
    repo = Repo(UM_AGENTE, usos)
    r1 = nubi_web._agentes_painel(repo)
    r2 = nubi_web._agentes_painel(repo)
    for k in ("hoje", "ontem", "dia7", "dia30", "mes"):
        assert r1["agentes"][0][k] == r2["agentes"][0][k], (k, r1["agentes"][0][k], r2["agentes"][0][k])


if __name__ == "__main__":
    test_cutoff_utc_menos_3()
    test_ontem_hoje_e_janelas_7_30_dias()
    test_sem_chamada_no_periodo_fica_com_chamadas_zero_nunca_numero_inventado()
    test_detalhamento_por_rotina_soma_igual_ao_total()
    test_rodar_duas_vezes_nao_muda_nem_duplica()
    print("ok")
