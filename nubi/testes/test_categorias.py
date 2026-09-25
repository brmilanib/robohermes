# -*- coding: utf-8 -*-
"""Testes do desempate determinístico em categorias.py (card #58): classificar() não pode
depender da ordem de inserção do dict SEMENTE. Rodar: python3 testes/test_categorias.py, na pasta nubi."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import categorias as c  # noqa: E402
import nubi  # noqa: E402


def test_58_toda_categoria_de_semente_tem_prioridade_definida():
    assert set(c.SEMENTE) == set(c.PRIORIDADE_CATEGORIA), (set(c.SEMENTE), set(c.PRIORIDADE_CATEGORIA))
    assert len(c.PRIORIDADE_CATEGORIA) == len(set(c.PRIORIDADE_CATEGORIA)), "prioridade duplicada"


def test_58_indice_nao_muda_se_o_dict_semente_for_reordenado():
    # Simula reordenar o dict inteiro (inclusive na ordem contrária) e monta o índice a partir
    # disso: tem que dar exatamente o mesmo resultado do INDICE real, porque quem decide agora
    # é PRIORIDADE_CATEGORIA, não a ordem de definição do SEMENTE.
    for sementes in (dict(reversed(list(c.SEMENTE.items()))),
                     dict(sorted(c.SEMENTE.items(), key=lambda kv: kv[0]))):
        pertence = {}
        for cat, texto in sementes.items():
            for m in texto.split(","):
                m = m.strip()
                if m:
                    pertence.setdefault(nubi.compacta(m), set()).add(cat)
        assert c._indice(pertence) == c.INDICE


def test_58_marca_em_2_categorias_usa_a_prioridade_nao_a_ordem_do_dict():
    # JEANNE ARTHES está em Designer (índice 1 na prioridade) e em Importados low ticket
    # (índice 5): Designer tem que vencer.
    assert c.classificar("JEANNE ARTHES") == ("Designer", "auto")
    # BOTTEGA VENETA está em Alta perfumaria (0) e Designer (1): Alta perfumaria vence.
    assert c.classificar("BOTTEGA VENETA") == ("Alta perfumaria", "auto")
    # LOUIS VUITTON está em Alta perfumaria (0) e Nicho (2): Alta perfumaria vence.
    assert c.classificar("LOUIS VUITTON") == ("Alta perfumaria", "auto")


def test_58_paris_corner_paris_elysees_collection_tommy_hilfiger_brasil():
    # Casos concretos pedidos no card #58; confirma que o refactor não mudou nenhum resultado.
    assert c.classificar("PARIS CORNER") == ("Árabe", "auto")
    assert c.classificar("PARIS ELYSEES COLLECTION") == ("Importados low ticket", "auto")
    assert c.classificar("TOMMY HILFIGER BRASIL") == ("Designer", "auto")


def test_58_conflitos_lista_as_marcas_em_mais_de_uma_categoria():
    saida = c.conflitos()
    chaves = {linha[0] for linha in saida}
    assert "JEANNEARTHES" in chaves, saida
    assert "BOTTEGAVENETA" in chaves, saida
    # cada linha é (chave, categoria vencedora, todas as categorias que citam a marca, em ordem de prioridade)
    jeanne = next(l for l in saida if l[0] == "JEANNEARTHES")
    assert jeanne[1] == "Designer", jeanne
    assert jeanne[2] == ["Designer", "Importados low ticket"], jeanne
    # nenhuma marca sem conflito real (citada em só 1 categoria) pode aparecer na lista
    assert all(len(l[2]) > 1 for l in saida), saida


def test_58_categoria_sem_conflito_continua_igual():
    # marca que só existe numa lista (sem overlap) não pode ser afetada pela mudança.
    assert c.classificar("NATURA") == ("Nacional", "auto")
    assert c.classificar("XERJOFF") == ("Nicho", "auto")


def test_72_relatorio_soma_linhas_da_mesma_marca_no_mes():
    # XERJOFF (Nicho) aparece 2x no mesmo mês (marca já unificada, ex. junção de nomes do dia): soma
    # vendas/unidades em vez de sobrescrever, fica com a melhor (menor) posição das duas linhas.
    linhas = [
        {"marca": "XERJOFF", "vendas": 100.0, "unidades": 10, "posicao": 7},
        {"marca": "XERJOFF", "vendas": 50.0, "unidades": 5, "posicao": 3},
        {"marca": "CREED", "vendas": 20.0, "unidades": 2, "posicao": 1},
    ]
    r = c.relatorio(["2026-09-01"], [linhas])
    nicho = r["serie"]["Nicho"]
    assert nicho["vendas"][0] == 170.0, nicho
    assert nicho["unidades"][0] == 17, nicho
    # marcas = número de marcas únicas com venda no mês (XERJOFF, CREED), não o número de linhas (3)
    assert nicho["marcas"][0] == 2, nicho
    xerjoff = next(m for m in r["marcas"] if m["marca"] == "XERJOFF")
    assert xerjoff["vendas"][0] == 150.0, xerjoff
    assert xerjoff["un"][0] == 15, xerjoff
    assert xerjoff["posicao"][0] == 3, xerjoff
    # soma das marcas da categoria == total da categoria (share_cat bate)
    assert sum(m["vendas"][0] for m in r["marcas"] if m["categoria"] == "Nicho") == nicho["vendas"][0]
    assert xerjoff["share_cat"] == 150.0 / 170.0, xerjoff


def test_72_categoria_manual_fora_de_categorias_vira_sem_categoria():
    chave = nubi.compacta("MARCA TESTE 72")
    manuais = {chave: "Categoria antiga que não existe mais"}
    assert c.classificar("MARCA TESTE 72", manuais) == (c.SEM, "sem")
    # categoria manual válida continua funcionando normalmente
    assert c.classificar("MARCA TESTE 72", {chave: "Nicho"}) == ("Nicho", "manual")


def test_72_relatorio_com_categoria_manual_invalida_nao_quebra_e_vira_sem_categoria():
    linhas = [{"marca": "MARCA TESTE 72", "vendas": 10.0, "unidades": 1, "posicao": 1}]
    manuais = {nubi.compacta("MARCA TESTE 72"): "Categoria antiga que não existe mais"}
    r = c.relatorio(["2026-09-01"], [linhas], manuais)  # não pode levantar KeyError em serie[cat]
    assert r["serie"][c.SEM]["vendas"][0] == 10.0
    m = next(x for x in r["marcas"] if x["marca"] == "MARCA TESTE 72")
    assert m["categoria"] == c.SEM and m["fonte"] == "sem", m
    assert m in r["sem_categoria"]


def test_72_auditoria_avisa_categoria_manual_invalida():
    import auditoria
    manuais = {"XERJOFF": "Nicho", "MARCATESTE72": "Categoria antiga que não existe mais"}
    ach = auditoria.achados_categoria_manual_invalida(manuais)
    assert len(ach) == 1, ach
    assert ach[0]["nivel"] == "alerta" and ach[0]["area"] == "categoria"
    assert "MARCATESTE72" in ach[0]["titulo"]
    # categoria manual válida não gera aviso
    assert auditoria.achados_categoria_manual_invalida({"XERJOFF": "Nicho"}) == []


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
