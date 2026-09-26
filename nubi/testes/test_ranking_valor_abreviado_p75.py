# -*- coding: utf-8 -*-
"""Card #88: sem mudar a lógica de ranking.py, testes de valor_abreviado com valores brutos reais e do cálculo
do p75 (tamanho 1 a 5), documentando o off-by-one apontado pelo DeepSeek.

Valores brutos reais de "Vendas em $" (produção, Supabase ivsmadbyzbmugwfadwtg, tabela ranking_linhas.bruto,
800 linhas conferidas em 26/09): a coluna SEMPRE chega com sufixo k ou M (545 linhas com k, 255 com M);
nenhuma ocorrência sem sufixo, nenhuma com "b". Nenhuma vírgula seguida de 3 dígitos apareceu em "Vendas em $"
nem em "Quantidade vendas" nos dados coletados até agora — toda vírgula observada é separador decimal
pt-BR antes de 1 ou 2 dígitos (ex.: "61,3%" no Catálogo). Recomendação: valor_abreviado está correto para os
dados reais vistos até hoje; não há caso hoje que dispare o ramo "elif "," in num" (pt-BR "1.234,5") na coluna
Vendas em $. Se um valor sem sufixo e com vírgula de milhar aparecer no futuro (ex.: formato en-US "1,234"),
valor_abreviado o leria errado como 1.234 (vírgula tratada como decimal); não é o caso hoje, e qualquer
correção fica para um card próprio, como pede o card #88.

Rodar: python3 testes/test_ranking_valor_abreviado_p75.py, na pasta nubi."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ranking  # noqa: E402

# valores reais de "Vendas em $" (ranking_linhas.bruto, produção) -> valor esperado em reais
VALORES_REAIS_VENDAS = [
    ("+$20.9M", 20_900_000.0),     # a marca #1 (NATURA) da conferência de 25/09
    ("+$1.0M", 1_000_000.0),
    ("+$1.1M", 1_100_000.0),
    ("+$104.4k", 104_400.0),
    ("+$114.0k", 114_000.0),
]


def test_valor_abreviado_com_valores_reais_de_vendas_em_dolar():
    for bruto, esperado in VALORES_REAIS_VENDAS:
        assert ranking.valor_abreviado(bruto) == esperado, (bruto, ranking.valor_abreviado(bruto))


def test_valor_abreviado_catalogo_percentual_real():
    # "Catálogo" real (percentual, vírgula decimal pt-BR): "61,3%" -> 0,613
    assert ranking.valor_abreviado("61,3%") == 0.613
    assert ranking.valor_abreviado("65,14%") == 0.6514


def _linha(vendas, saturacao="alta", tendencia="diminuindo", variacao=0, vendedores=None, posicao=None, marca=None):
    # saturacao=alta, tendencia=diminuindo, variacao=0 e sem vendedores zeram sat/ten/rel/sub (ranking.analisar):
    # nota = 100 * tam * 0,10 = 10 * tam, isolando o efeito do p75 no fator de tamanho (tam).
    marca = marca or f"m{vendas}"
    return {"posicao": posicao, "variacao": variacao, "marca": marca, "marca_chave": marca, "vendas": vendas,
            "unidades": 1, "vendedores": vendedores, "saturacao": saturacao, "tendencia": tendencia,
            "catalogo": None, "ranking_demanda": None, "bruto": {}}


def _notas(vendas_lista):
    linhas = [_linha(v) for v in vendas_lista]
    saida, _saiu, _resumo = ranking.analisar(linhas)
    return {l["marca"]: l["nota"] for l in saida}


def test_p75_lista_tamanho_1():
    n = _notas([50])
    assert n["m50"] == 10                                        # única marca: é o próprio p75, tam=1


def test_p75_lista_tamanho_2():
    n = _notas([5, 20])                                          # p75 = maior valor (índice 1 de 2), igual ao nearest-rank
    assert n["m20"] == 10
    assert n["m5"] == round(10 * math.sqrt(5 / 20))


def test_p75_lista_tamanho_3():
    n = _notas([1, 2, 9])                                        # p75 = maior valor (índice 2 de 3), igual ao nearest-rank
    assert n["m9"] == 10
    assert n["m2"] == round(10 * math.sqrt(2 / 9))


def test_p75_lista_tamanho_4_off_by_one_do_deepseek():
    # FALHA ESPERADA vs. o percentil 75 "de livro" (nearest-rank): para n=4, ceil(0,75*4)=3º valor (índice 2),
    # mas ranking.analisar usa vendas_ord[int(4*0.75)] = índice 3 = o MAIOR valor. Documento o comportamento
    # atual (o teste passa mostrando o bug, sem corrigi-lo — qualquer correção de cálculo é card próprio):
    # a marca do meio (vendas=3, que deveria valer 100% do tamanho por já estar no p75 "de livro") sai com
    # nota baixa porque o código divide pelo maior valor (1000) em vez do 3º (3).
    n = _notas([1, 2, 3, 1000])
    tam_esperado_correto = 1.0                                    # se p75 fosse o 3º valor (índice 2) = 3
    tam_atual_do_codigo = math.sqrt(3 / 1000)                     # p75 atual = o maior valor (índice 3) = 1000
    assert n["m3"] == round(10 * tam_atual_do_codigo)             # comportamento hoje (documentado, não corrigido)
    assert n["m3"] != round(10 * tam_esperado_correto)            # prova que diverge do percentil 75 "de livro"


def test_p75_lista_tamanho_5():
    n = _notas([1, 2, 3, 4, 20])                                  # p75 = índice 3 de 5 (valor 4), igual ao nearest-rank
    assert n["m4"] == 10
    assert n["m1"] == round(10 * math.sqrt(1 / 4))


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
