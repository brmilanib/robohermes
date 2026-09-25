# -*- coding: utf-8 -*-
"""Testes do StoreConnector base, da gravação idempotente de pedidos (card #1) e do
dry-run obrigatório (card #2). Rodar: python3 testes/test_store_connector.py, na pasta nubi."""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import store_connector as sc  # noqa: E402

# Os testes de gravação (card #1) escrevem de verdade: ligam os dois flags explícitos
# exigidos pelo dry-run obrigatório (card #2). Sem eles, persistir_pedidos fica em dry-run.
ESCREVE = dict(dry_run=False, checklist_aprovado_por_bruno=True)


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
    n1, av1 = sc.persistir_pedidos(r, "mercado_livre", [{"id_externo": "123", "status": "pago", "dados": {"total": 10}}], **ESCREVE)
    n2, av2 = sc.persistir_pedidos(r, "mercado_livre", [{"id_externo": "123", "status": "pago", "dados": {"total": 10}}], **ESCREVE)
    assert n1 == 1 and n2 == 1 and not av1 and not av2, (n1, n2, av1, av2)
    assert len(r.linhas) == 1, r.linhas


def test_1_mesmo_id_externo_em_sources_diferentes_gera_2_registros():
    r = RepoStore()
    sc.persistir_pedidos(r, "mercado_livre", [{"id_externo": "123"}], **ESCREVE)
    sc.persistir_pedidos(r, "shopee", [{"id_externo": "123"}], **ESCREVE)
    assert len(r.linhas) == 2, r.linhas
    assert ("mercado_livre", "123") in r.linhas and ("shopee", "123") in r.linhas, r.linhas


def test_1_id_externo_vazio_ou_ausente_nao_grava():
    r = RepoStore()
    n, avisos = sc.persistir_pedidos(r, "mercado_livre", [{"id_externo": ""}, {"id_externo": None}, {}], **ESCREVE)
    assert n == 0 and len(avisos) == 3, (n, avisos)
    assert not r.linhas, r.linhas


def test_1_source_vazio_recusa():
    r = RepoStore()
    try:
        sc.persistir_pedidos(r, "", [{"id_externo": "1"}], **ESCREVE)
        assert False, "devia recusar source vazio"
    except sc.ErroConector as e:
        assert "source" in str(e), e
    assert not r.linhas


def test_1_atualiza_status_do_mesmo_pedido_sem_duplicar():
    r = RepoStore()
    sc.persistir_pedidos(r, "mercado_livre", [{"id_externo": "9", "status": "pendente"}], **ESCREVE)
    sc.persistir_pedidos(r, "mercado_livre", [{"id_externo": "9", "status": "pago"}], **ESCREVE)
    assert len(r.linhas) == 1, r.linhas
    assert r.linhas[("mercado_livre", "9")]["status"] == "pago", r.linhas


def test_1_id_externo_zero_e_valido_nao_e_falsy():
    # id_externo=0 (int) é um valor legítimo, não "vazio": "or" trataria como falsy e descartaria por engano
    r = RepoStore()
    n, avisos = sc.persistir_pedidos(r, "mercado_livre", [{"id_externo": 0}], **ESCREVE)
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


def test_2_dry_run_por_padrao_nao_grava_e_loga():
    # dry_run ausente (None) = dry-run ligado por padrão; nenhum flag de escrita foi passado.
    r = RepoStore()
    pedidos = [{"id_externo": str(i)} for i in range(8)]
    saida_capturada = io.StringIO()
    with contextlib.redirect_stdout(saida_capturada):
        n, avisos = sc.persistir_pedidos(r, "mercado_livre", pedidos)
    assert n == 0 and not r.linhas, (n, r.linhas)
    assert len(avisos) == 1 and "8 pedido" in avisos[0], avisos
    saida = saida_capturada.getvalue()
    assert "[dry-run:mercado_livre]" in saida and "8 pedido" in saida, saida


def test_2_dry_run_string_false_normaliza_sem_bool_de_string():
    # bool("false") é True em Python; normalizar_flag precisa tratar a string certo.
    assert sc.normalizar_flag("false", True) is False
    assert sc.normalizar_flag("False", True) is False
    assert sc.normalizar_flag("0", True) is False
    assert sc.normalizar_flag("true", False) is True
    assert sc.normalizar_flag(None, True) is True
    assert sc.normalizar_flag("", False) is False

    r = RepoStore()
    n, avisos = sc.persistir_pedidos(r, "mercado_livre", [{"id_externo": "1"}], dry_run="false",
                                      checklist_aprovado_por_bruno=True)
    assert n == 1 and not avisos, (n, avisos)
    assert len(r.linhas) == 1, r.linhas


def test_2_dry_run_false_com_checklist_pendente_continua_dry_run():
    r = RepoStore()
    n, avisos = sc.persistir_pedidos(r, "mercado_livre", [{"id_externo": "1"}], dry_run=False,
                                      checklist_aprovado_por_bruno=False)
    assert n == 0 and not r.linhas, (n, r.linhas)
    assert avisos and "checklist pendente" in avisos[0], avisos


def test_2_dry_run_true_com_checklist_aprovado_continua_dry_run():
    r = RepoStore()
    n, avisos = sc.persistir_pedidos(r, "mercado_livre", [{"id_externo": "1"}], dry_run=True,
                                      checklist_aprovado_por_bruno=True)
    assert n == 0 and not r.linhas, (n, r.linhas)
    assert avisos and "dry-run" in avisos[0], avisos


def test_2_valor_vazio_nao_string_tambem_cai_no_default_nunca_grava():
    # Achado da revisão: dry_run=[] / {} / 0 não pode "destravar" a escrita — são vazios,
    # têm que cair no default (dry-run), não em bool(valor) (que trataria como desligado).
    for vazio in ([], {}, 0, 0.0):
        assert sc.normalizar_flag(vazio, True) is True, vazio
        assert sc.normalizar_flag(vazio, False) is False, vazio
        r = RepoStore()
        n, avisos = sc.persistir_pedidos(r, "mercado_livre", [{"id_externo": "999"}], dry_run=vazio,
                                          checklist_aprovado_por_bruno=True)
        assert n == 0 and not r.linhas, (vazio, n, r.linhas)

    # Valor truthy explícito (não vazio) continua virando True normalmente.
    assert sc.normalizar_flag([1], False) is True
    assert sc.normalizar_flag(1, False) is True


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
