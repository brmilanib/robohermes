# -*- coding: utf-8 -*-
"""01/10 (Bruno): estoque do UpSeller meia hora antes de cada Gestor (00:30, 11:30, 18:30); Gestor Seller 3 vezes por dia (01:00, 12:00, 19:00), sempre com o
estoque atualizado depois do horário. Rodar: python3 testes/test_estoque_hora.py, na pasta nubi."""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import nubi_web as w  # noqa: E402

BR = timezone.utc          # o nubi guarda a hora de Brasília como UTC deslocado (_agora_br)


class R:
    def __init__(self, estoque_em, gestor_ok_em=None):
        self.est, self.gest = estoque_em, gestor_ok_em

    def _eq(self, v):
        return f"eq.{v}"

    def _req(self, metodo, tabela, q=None, corpo=None, **k):
        if tabela == "rotinas":
            rid = (q or {}).get("id", "")[3:]
            return [{"id": rid, "ativo": True, "horario": {"estoque": "00:30", "gestor": "01:00"}[rid], "dias_semana": ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]}]
        if tabela == "estoque_atualizacoes":
            return [{"criado_em": (self.est + timedelta(hours=3)).isoformat()}] if self.est else []
        if tabela == "coletor_execucoes":
            return [{"iniciado_em": (self.gest + timedelta(hours=3)).isoformat()}] if self.gest else []
        return []


def test_estoque_meia_hora_antes_e_gestor_tres_vezes():
    hoje = datetime(2026, 10, 1, tzinfo=BR)
    w._so_no_mac = lambda repo, t: False
    def em(h, m=0):
        return hoje.replace(hour=h, minute=m)
    # estoque do UpSeller: 00:30, 11:30 e 18:30 (meia hora antes de cada Gestor) — não mais de hora em hora
    assert w.ESTOQUE_HORARIOS == ("00:30", "11:30", "18:30")
    w._agora_br = lambda: em(10, 5)
    assert w.rota_estoque(R(em(0, 35)), "GET", "estoque_pendente", {}, b"")["rodar"] is False     # 00:30 já feito
    assert w.rota_estoque(R(hoje - timedelta(hours=2)), "GET", "estoque_pendente", {}, b"")["rodar"] is True   # ontem
    w._agora_br = lambda: em(11, 40)
    assert w.rota_estoque(R(em(0, 35)), "GET", "estoque_pendente", {}, b"")["rodar"] is True      # 11:30 devido
    assert w.rota_estoque(R(em(11, 32)), "GET", "estoque_pendente", {}, b"")["rodar"] is False
    w._agora_br = lambda: em(0, 10)
    assert w.rota_estoque(R(hoje - timedelta(hours=1)), "GET", "estoque_pendente", {}, b"")["rodar"] is False  # antes de 00:30
    # gestor: às 12:10, devido (último às 01:00) e precisa de estoque depois das 12:00
    w._agora_br = lambda: em(12, 10)
    assert w.rota_estoque(R(em(9, 30), em(1, 5)), "GET", "gestor_pendente", {}, b"")["rodar"] is False    # sem o estoque das 11:30
    assert w.rota_estoque(R(em(11, 31), em(1, 5)), "GET", "gestor_pendente", {}, b"")["rodar"] is True    # o das 11:30 serve
    assert w.rota_estoque(R(em(12, 5), em(1, 5)), "GET", "gestor_pendente", {}, b"")["rodar"] is True
    assert w.rota_estoque(R(em(12, 5), em(12, 8)), "GET", "gestor_pendente", {}, b"")["rodar"] is False   # já feito às 12:08
    assert w.rota_estoque(R(em(12, 5), em(1, 5)), "GET", "gestor_auto", {}, b"")["ligado"] is True
    w._agora_br = lambda: em(15, 0)                       # entre 12:00 e 19:00, já feito: estoque de hora em hora não dispara o Gestor
    assert w.rota_estoque(R(em(14, 55), em(12, 8)), "GET", "gestor_auto", {}, b"")["ligado"] is False
    w._agora_br = lambda: em(19, 20)
    x = w.rota_estoque(R(em(18, 35), em(12, 8)), "GET", "gestor_pendente", {}, b"")
    assert x["rodar"] is True and x["horario"] == "19:00", x
    w._agora_br = lambda: em(0, 40)                       # antes da 01:00: nada
    assert w.rota_estoque(R(em(0, 35), None), "GET", "gestor_pendente", {}, b"")["rodar"] is False


if __name__ == "__main__":
    test_estoque_meia_hora_antes_e_gestor_tres_vezes()
    print("ok estoque 00:30/11:30/18:30 e gestor 01/12/19")
