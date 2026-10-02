# -*- coding: utf-8 -*-
"""02/10 (Bruno: "abre uma aba em Minhas Lojas → Financeiro, DRE Simplificado todo mês fechado; o Resumo analítico toda semana;
calcule meu markup médio para o potencial de vendas do estoque"). Textos iguais aos do PDF e da tela do Gestor Seller."""
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import categorias  # noqa: E402
import financeiro  # noqa: E402

DRE = """Período: 09/2026
Custo de produtos reembolsados: Incluído
 Faturamento R$ 820.464,00
Amazon: R$ 81.345,82
Mercado livre: R$ 690.281,37
Shopee: R$ 28.841,81
TikTok Shop: R$ 19.995,00
 Líquido Marketplace R$ 661.186,71
Amazon: R$ 81.349,60
Comissão: - R$ 10.856,62
Valor Final: R$ 72.978,09
Mercado livre: R$ 690.281,37
Frete Pago pelo vendedor: - R$ 58.589,50
Valor Final: R$ 550.327,47
Shopee: R$ 28.841,81
Valor Final: R$ 19.990,13
TikTok Shop: R$ 19.995,00
Valor Final: R$ 17.891,02
 Lucro Bruto R$ 131.386,36 (16,01%)
Amazon: R$ 72.978,09
Custo dos produtos: - R$ 49.576,80
Custo dos produtos reembolsados: - R$ 180,06
Imposto: - R$ 2.506,53
Valor Final: R$ 17.044,60
Mercado Livre: R$ 550.327,47
Custo dos produtos: - R$ 416.600,56
Custo dos produtos reembolsados: - R$ 6.100,29
Imposto: - R$ 16.586,16
Valor Final: R$ 111.032,56
Shopee: R$ 19.990,13
Custo dos produtos: - R$ 15.897,49
Custo dos produtos reembolsados: - R$ 459,19
Imposto: - R$ 291,74
Valor Final: R$ 3.341,71
TikTok Shop: R$ 17.891,02
Custo dos produtos: - R$ 15.455,11
Custo dos produtos reembolsados: - R$ 322,10
Imposto: - R$ 231,48
Valor Final: -R$ 32,51
 ADS
Amazon: R$ 0,00
Mercado livre: R$ 23.408,58
-R$ 25.343,33
Shopee: R$ 1.934,75
TikTok Shop: R$ 0,00
 Lucro bruto depois de ads R$ 106.043,03 (12,92%)
 Despesas operacionais
Pessoal: R$ 23.000,00
-R$ 23.000,00
 Lucro Líquido Operacional R$ 83.043,03 (10,12%)
"""

RESUMO = "\n".join(["Resumo Analítico", "MARÇO", "ABRIL", "SETEMBRO", "OUTUBRO",
                    "[IMG:mercado-livre.svg]", "Faturamento", "R$ 471.075,48", "R$ 672.483,43", "R$ 690.281,37", "R$ 23.360,82",
                    "Líq. do Marketplace", "R$ 367.830,13", "R$ 528.265,90", "R$ 550.327,47", "R$ 18.788,41",
                    "Lucro Bruto", "R$ 105.548,51", "R$ 136.902,94", "R$ 117.132,85", "R$ 4.399,94",
                    "Margem", "22,41%", "20,36%", "16,97%", "18,83%",
                    "Custo de ads", "R$ 15.774,82", "R$ 18.875,16", "R$ 23.408,58", "R$ 779,54",
                    "Lucro Bruto pós ads", "R$ 89.773,69", "R$ 118.027,78", "R$ 93.724,27", "R$ 3.620,40",
                    "MPA", "19,06%", "17,55%", "13,58%", "15,5%",
                    "[IMG:a1b2.png]", "Faturamento", "R$ 71.625,13", "R$ 96.468,80", "R$ 28.802,33", "R$ 518,95",      # 2º bloco = Shopee (ordem da tela)
                    "Líq. do Marketplace", "R$ 51.517,61", "R$ 69.088,92", "R$ 19.990,13", "R$ 357,48",
                    "Lucro Bruto", "R$ 8.068,45", "R$ 12.051,93", "R$ 3.800,90", "R$ 93,63",
                    "Margem", "11,26%", "12,49%", "13,2%", "18,04%",
                    "Custo de ads", "R$ 4.148,38", "R$ 10.477,64", "R$ 1.934,75", "R$ 0,00",
                    "Lucro Bruto pós ads", "R$ 3.920,07", "R$ 1.574,29", "R$ 1.866,15", "R$ 93,63",
                    "MPA", "5,47%", "1,63%", "6,48%", "18,04%",
                    "[IMG:amazon.png]", "Faturamento", "R$ 83.233,48", "R$ 81.345,82", "R$ 4.103,95",        # a Amazon começou em abril: alinha pela direita
                    "Líq. do Marketplace", "R$ 77.397,66", "R$ 72.987,41", "R$ 3.717,54",
                    "Lucro Bruto", "R$ 20.212,07", "R$ 17.233,98", "R$ 675,05",
                    "Margem", "24,28%", "21,19%", "16,45%",
                    "Custo de ads", "R$ 0,00", "R$ 0,00", "R$ 0,00",
                    "Lucro Bruto pós ads", "R$ 20.212,07", "R$ 17.233,98", "R$ 675,05",
                    "MPA", "24,28%", "21,19%", "16,45%"])


class Repo:
    def __init__(self):
        self.dados = {}

    def _req(self, metodo, tabela, params=None, corpo=None, **k):
        if metodo == "POST":
            for r in corpo:
                self.dados[r["chave"]] = r["texto"]
            return []
        ch = (params or {}).get("chave", "")
        if ch.startswith("like."):
            pref = ch[5:].rstrip("%")
            return [{"chave": c, "texto": t} for c, t in self.dados.items() if c.startswith(pref)]
        if ch.startswith("eq."):
            return [{"texto": self.dados[ch[3:]]}] if ch[3:] in self.dados else []
        return []


def test_dre():
    d = financeiro.ler_dre(DRE)
    assert d["mes"] == "2026-09" and d["faturamento"] == 820464.0 and d["liquido"] == 661186.71
    assert d["custo_produtos"] == 497529.96 and d["custo_reembolsados"] == 7061.64 and d["imposto"] == 19615.91
    assert d["lucro_bruto"] == 131386.36 and round(d["lucro_bruto_pct"], 4) == 0.1601 and d["ads"] == 25343.33
    assert d["lucro_liquido"] == 83043.03 and d["lucro_liquido_pct"] == 0.1012 and d["despesas"] == 23000.0
    assert d["markup"] == 1.6491 and d["markup_liquido"] == 1.3289                      # 820.464 ÷ 497.530
    assert d["faturamento_canal"]["Mercado Livre"] == 690281.37 and d["custo_canal"]["Amazon"] == 49576.8
    assert d["ads_canal"]["Shopee"] == 1934.75 and d["liquido_canal"]["TikTok Shop"] == 17891.02


def test_resumo_e_markup_do_ano():
    r = financeiro.ler_resumo(RESUMO, date(2026, 10, 2))
    assert r["meses"] == ["2026-03", "2026-04", "2026-09", "2026-10"]
    assert sorted(r["canais"]) == ["Amazon", "Mercado Livre", "Shopee"]
    assert r["canais"]["Mercado Livre"]["2026-09"]["faturamento"] == 690281.37 and r["canais"]["Mercado Livre"]["2026-09"]["mpa"] == 0.1358
    assert "2026-03" not in r["canais"]["Amazon"] and r["canais"]["Amazon"]["2026-04"]["faturamento"] == 83233.48
    p = r["por_mes"]["2026-09"]
    assert p["faturamento"] == 800429.52 and p["lucro_bruto"] == 138167.73 and p["markup_aprox"] == 1.6472, p   # exato do DRE: 1,6491
    # painel: o DRE de setembro é exato, março/abril ficam com o aproximado do Resumo
    repo = Repo()
    financeiro.gravar_dre(repo, financeiro.ler_dre(DRE))
    financeiro.gravar_resumo(repo, r)
    pn = financeiro.painel(repo, date(2026, 10, 2))
    assert pn["markup_medio"]["markup"] == 1.6491 and pn["markup_medio"]["meses"] == ["2026-09"]
    ma = pn["markup_ano"]
    assert [(m["mes"], m["exato"]) for m in ma["meses"]] == [("2026-03", False), ("2026-04", False), ("2026-09", True), ("2026-10", False)], ma
    assert ma["meses_exatos"] == 1 and ma["so_exatos"] == 1.6491 and 1.55 < ma["markup"] < 1.75
    assert financeiro.markup_para_estoque(repo) == {"markup": 1.6491, "fonte": "DRE 2026-09", "exato": True}
    # coletor: o que falta (Resumo velho, meses fechados sem DRE)
    pend = financeiro.pendente(repo, date(2026, 10, 2))
    assert pend["rodar"] and not pend["resumo"] and pend["meses"] == [f"2026-0{m}" for m in range(1, 9)], pend
    pend2 = financeiro.pendente(repo, date(2026, 10, 9))
    assert pend2["resumo"] and pend2["meses"][-1] == "2026-09"                           # 7 dias depois: Resumo de novo e refresca o último mês


def test_potencial_pelo_markup():
    lista = [{"sku": "A", "titulo": "Perfume X", "marca": "LATTAFA", "disponivel": 10, "atual": 10, "transito": 0, "custo": 100.0,
              "vend_un": 30, "vend_valor": 3000.0, "preco_venda": 100.0, "cobertura_dias": 10}]
    rk = categorias.ranking_marcas(lista, 0.2, 1.6491)
    assert rk["marcas"][0]["potencial"] == 1649.1 and rk["markup_usado"] == 1.6491      # custo em estoque × markup, não o preço de agora (100)
    assert categorias.ranking_marcas(lista, 0.2)["marcas"][0]["potencial"] == 1000.0


if __name__ == "__main__":
    test_dre()
    test_resumo_e_markup_do_ano()
    test_potencial_pelo_markup()
    print("ok financeiro")
