# -*- coding: utf-8 -*-
"""Testes do StoreConnector base e da gravação idempotente de pedidos (card #1).
Rodar: python3 testes/test_store_connector.py, na pasta nubi."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import store_connector as sc  # noqa: E402


class RepoStore:
    """Simula a constraint única (source, id_externo) do Supabase real: POST com
    resolution=merge-duplicates faz upsert pela chave, nunca duplica linha."""

    def __init__(self):
        self.linhas = {}

    def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
        assert tab == "store_orders" and metodo == "POST", (tab, metodo)
        assert prefer and "merge-duplicates" in prefer, prefer
        for r in corpo:
            self.linhas[(r["source"], r["id_externo"])] = r
        return None


def test_1_mesmo_pedido_2x_fica_1_registro():
    r = RepoStore()
    n1, av1 = sc.persistir_pedidos(r, "mercado_livre", [{"id_externo": "123", "status": "pago", "dados": {"total": 10}}])
    n2, av2 = sc.persistir_pedidos(r, "mercado_livre", [{"id_externo": "123", "status": "pago", "dados": {"total": 10}}])
    assert n1 == 1 and n2 == 1 and not av1 and not av2, (n1, n2, av1, av2)
    assert len(r.linhas) == 1, r.linhas


def test_1_mesmo_id_externo_em_sources_diferentes_gera_2_registros():
    r = RepoStore()
    sc.persistir_pedidos(r, "mercado_livre", [{"id_externo": "123"}])
    sc.persistir_pedidos(r, "shopee", [{"id_externo": "123"}])
    assert len(r.linhas) == 2, r.linhas
    assert ("mercado_livre", "123") in r.linhas and ("shopee", "123") in r.linhas, r.linhas


def test_1_id_externo_vazio_ou_ausente_nao_grava():
    r = RepoStore()
    n, avisos = sc.persistir_pedidos(r, "mercado_livre", [{"id_externo": ""}, {"id_externo": None}, {}])
    assert n == 0 and len(avisos) == 3, (n, avisos)
    assert not r.linhas, r.linhas


def test_1_source_vazio_recusa():
    r = RepoStore()
    try:
        sc.persistir_pedidos(r, "", [{"id_externo": "1"}])
        assert False, "devia recusar source vazio"
    except sc.ErroConector as e:
        assert "source" in str(e), e
    assert not r.linhas


def test_1_atualiza_status_do_mesmo_pedido_sem_duplicar():
    r = RepoStore()
    sc.persistir_pedidos(r, "mercado_livre", [{"id_externo": "9", "status": "pendente"}])
    sc.persistir_pedidos(r, "mercado_livre", [{"id_externo": "9", "status": "pago"}])
    assert len(r.linhas) == 1, r.linhas
    assert r.linhas[("mercado_livre", "9")]["status"] == "pago", r.linhas


def test_1_id_externo_zero_e_valido_nao_e_falsy():
    # id_externo=0 (int) é um valor legítimo, não "vazio": "or" trataria como falsy e descartaria por engano
    r = RepoStore()
    n, avisos = sc.persistir_pedidos(r, "mercado_livre", [{"id_externo": 0}])
    assert n == 1 and not avisos, (n, avisos)
    assert r.linhas[("mercado_livre", "0")]["id_externo"] == "0", r.linhas


def test_1_interface_base_nao_implementada():
    c = sc.StoreConnector()
    for metodo in (c.fetch_orders, c.fetch_ads_ranking):
        try:
            metodo()
            assert False, "devia levantar NotImplementedError"
        except NotImplementedError:
            pass


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
