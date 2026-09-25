# -*- coding: utf-8 -*-
"""Testes do diagnóstico de SKU do Gestor Seller e da deduplicação de alerta (card #57).
Rodar: python3 testes/test_gestor_sku.py, na pasta nubi."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COLETOR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public", "coletor")
if COLETOR not in sys.path:
    sys.path.insert(0, COLETOR)

import coletor  # noqa: E402
import nubi_web  # noqa: E402


def test_normalizar_sku_trim_maiuscula_e_invisivel():
    assert coletor._normalizar_sku("  armaf-mega-200  ") == "ARMAF-MEGA-200"
    assert coletor._normalizar_sku("arm​af-200") == "ARMAF-200"          # zero-width space some
    assert coletor._normalizar_sku("SKU\xa0100") == "SKU 100"                 # nbsp vira espaço normal
    assert coletor._normalizar_sku("") == "" and coletor._normalizar_sku(None) == ""
    # a mesma regra do servidor tem que bater com a do coletor (card diz "mesmo padrão")
    assert nubi_web._normalizar_sku("  armaf-mega-200  ") == coletor._normalizar_sku("  armaf-mega-200  ")


def test_diagnostico_sku_traz_os_4_campos_sku_nao_encontrado():
    msg = coletor._diagnostico_sku_nao_bate("armaf-mega-200 ", 48.0, None, "campo de busca (Enter)", False)
    assert "sku_original=armaf-mega-200 " in msg, msg
    assert "sku_normalizado=ARMAF-MEGA-200" in msg, msg
    assert "etapa=campo de busca (Enter)" in msg, msg
    assert "existe_em_estoque=não" in msg, msg
    assert "SKU não encontrado" in msg, msg


def test_diagnostico_sku_encontrado_no_estoque_mas_custo_diferente():
    msg = coletor._diagnostico_sku_nao_bate("XYZ-1", 10.5, "XYZ-1  R$ 9,00", "busca por link (?search=)", True)
    assert "existe_em_estoque=sim" in msg, msg
    assert "etapa=busca por link (?search=)" in msg, msg
    assert "R$ 9,00" in msg, msg


def test_diagnostico_sem_dados_do_estoque_sku_existe():
    # api() falhou (nubi fora do ar): existe_em_estoque fica "sem_dados", não bloqueia o erro original nem custo
    msg = coletor._diagnostico_sku_nao_bate("Z-9", 1.0, None, "campo de busca (Enter)", None)
    assert "existe_em_estoque=sem_dados" in msg, msg


def test_dedup_mesmo_sku_e_erro_no_mesmo_dia_alerta_uma_vez():
    with tempfile.TemporaryDirectory() as tmp:
        coletor.ALERTAS_DEDUP = Path(tmp) / "alertas_dedup.json"
        erro = coletor._diagnostico_sku_nao_bate("ARMAF-MEGA-200", 48.0, None, "campo de busca (Enter)", False)
        chave = coletor._chave_dedup_gestor("gestor", erro)
        assert chave is not None
        assert coletor._alerta_repetido_hoje(chave) is False    # 1ª vez: pode alertar
        assert coletor._alerta_repetido_hoje(chave) is True     # 2ª e 3ª vezes no mesmo dia: já alertou
        assert coletor._alerta_repetido_hoje(chave) is True


def test_dedup_sku_diferente_nao_e_bloqueado_pelo_outro():
    with tempfile.TemporaryDirectory() as tmp:
        coletor.ALERTAS_DEDUP = Path(tmp) / "alertas_dedup.json"
        erro1 = coletor._diagnostico_sku_nao_bate("SKU-A", 10.0, None, "campo de busca (Enter)", False)
        erro2 = coletor._diagnostico_sku_nao_bate("SKU-B", 20.0, None, "campo de busca (Enter)", False)
        assert coletor._alerta_repetido_hoje(coletor._chave_dedup_gestor("gestor", erro1)) is False
        assert coletor._alerta_repetido_hoje(coletor._chave_dedup_gestor("gestor", erro2)) is False


def test_dedup_so_vale_para_a_tarefa_gestor():
    assert coletor._chave_dedup_gestor("estoque", "TargetClosedError: navegador fechou") is None
    assert coletor._chave_dedup_gestor("gestor", "erro qualquer sem os campos do card #57") is None


class RepoEstoque:
    def __init__(self, itens_por_atualizacao):
        self.t = itens_por_atualizacao   # {aid: [itens]}

    def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
        if tab == "estoque_atualizacoes" and metodo == "GET":
            aids = sorted(self.t)
            return [{"id": aids[-1]}] if aids else []
        return []

    def _todos(self, tab, params=None, metodo="GET", corpo=None):
        if tab == "estoque_itens":
            aid = int(str(params["atualizacao_id"]).split(".")[-1])
            return self.t.get(aid, [])
        return []

    def _eq(self, v):
        return f"eq.{v}"


def test_rota_estoque_sku_existe_normaliza_para_comparar():
    r = RepoEstoque({5: [{"sku": " armaf-mega-200 "}]})
    resp = nubi_web.rota_estoque(r, "GET", "estoque_sku_existe", {"sku": "ARMAF-MEGA-200"}, None)
    assert resp == {"existe": True}, resp
    resp2 = nubi_web.rota_estoque(r, "GET", "estoque_sku_existe", {"sku": "OUTRO-SKU"}, None)
    assert resp2 == {"existe": False}, resp2


def test_rota_estoque_sku_existe_sem_atualizacao_nenhuma():
    r = RepoEstoque({})
    resp = nubi_web.rota_estoque(r, "GET", "estoque_sku_existe", {"sku": "X"}, None)
    assert resp == {"existe": False}, resp


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
