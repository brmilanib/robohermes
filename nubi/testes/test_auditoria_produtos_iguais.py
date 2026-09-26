# -*- coding: utf-8 -*-
"""Card #86: na conferência "Junção com parecença baixa" da auditoria, o título de cada lado já vem inteiro de
produto_grupos (não corta de novo na exibição); o que faltava era mostrar volume/concentração/gênero de cada lado
e explicar se um "—" é campo vazio no anúncio ou o título cortado nos ~40 caracteres do export do Nubimetrics
(vend_anuncios/produto_grupos sempre têm esse tamanho quando cortados — ver produtos_iguais.numeros).
Casos reais da auditoria de 2026-09-26 (Fakhar Black, Ameeri, D&G The One, CK One, Tommy) usados como regressão.
Rodar: python3 testes/test_auditoria_produtos_iguais.py, na pasta nubi."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.update(OPENAI_API_KEY="x", ANTHROPIC_API_KEY="x")

import auditoria as au  # noqa: E402

CASOS = [
    ("Dolce&gabbana The One Feminino Edp 30ml", "Perfume Dolce & Gabbana The One Eau De P", 0.8285),
    ("Perfume Árabe - Al Wataniah Ameeri Edp 1", "Ameeri Al Wataniah Eau De Parfum 100ml M", 0.8431),
    ("Tommy Hilfiger Tommy Tradicional Edt 200", "Tommy ( Tradicional ) 200ml Masculino |", 0.8494),
    ("Perfume Lattafa Fakhar Black Masculino E", "Perfume Árabe Fakhar Black Lattafa 100ml", 0.8581),
    ("Calvin Klein Ck One 100ml - Original", "Perfume Unissex Calvin Klein Ck One 100m", 0.8585),
]


def test_titulo_inteiro_de_produto_grupos_nao_e_cortado_de_novo():
    for titulo, grupo_titulo, sim in CASOS:
        ach = au.achados_parecenca_baixa([{"titulo": titulo, "grupo_titulo": grupo_titulo, "similaridade": sim}])[0]
        assert titulo in ach["detalhe"] and grupo_titulo in ach["detalhe"], ach["detalhe"]


def test_atributo_ausente_por_corte_e_diferente_de_campo_vazio():
    # D&G The One: lado B (39 caracteres visíveis, "...Eau De P") está cortado -> "—" explica que pode ter mais
    b = "Perfume Dolce & Gabbana The One Eau De P"
    la = au.atributos_lado(b)
    assert la["cortado"] and "cortado" in la["volume"] and "cortado" in la["concentracao"]
    # CK One: "Calvin Klein Ck One 100ml - Original" tem 36 caracteres (não cortado) e não fala concentração/gênero
    a = "Calvin Klein Ck One 100ml - Original"
    la2 = au.atributos_lado(a)
    assert not la2["cortado"]
    assert "campo vazio" in la2["concentracao"] and "campo vazio" in la2["genero"]
    assert la2["volume"] == "100ml"


def test_dg_the_one_extrai_volume_genero_e_concentracao_do_lado_completo():
    # o lado sem corte (39 caracteres, mas com informação legível) mostra os valores extraídos, não "—"
    a = "Dolce&gabbana The One Feminino Edp 30ml"
    la = au.atributos_lado(a)
    assert la["volume"] == "30ml" and la["concentracao"] == "edp" and la["genero"] == "feminino"


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
