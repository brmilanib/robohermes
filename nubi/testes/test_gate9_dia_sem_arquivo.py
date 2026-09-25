# -*- coding: utf-8 -*-
"""Teste de regressão do gate #9 (card #59): dia sem arquivo de um vendedor fica "coleta pendente"
(fora dos totais, sem nascer linha zerada), diferente de um dia com arquivo e zero vendas (linha zerada
de verdade, entra nos totais). Caso real: AUMA sem export em 23/09.
Rodar: python3 testes/test_gate9_dia_sem_arquivo.py, na pasta nubi."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.update(OPENAI_API_KEY="x", ANTHROPIC_API_KEY="x")

import nubi_web  # noqa: E402


def linha_vend(titulo, unidades, vendas, preco, marca="M"):
    return {"titulo": titulo, "marca": marca, "unidades": unidades, "vendas": vendas, "preco": preco,
            "estado": "active", "tipo_pub": "classico", "full": False}


class RepoPainel:
    """vend_vendas_dia em memória, upsert por (vendedor, data) como o Supabase real (merge-duplicates);
    grupo vazio = gate #9 não bloqueia (regra "não bloqueia quando o grupo ainda não chegou")."""

    def __init__(self):
        self.vendas = []
        self.auditorias = []

    def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
        if tab == "vend_grupo_dia" and metodo == "GET":
            return []
        if tab == "auditorias":
            if metodo == "GET":
                return self.auditorias
            self.auditorias = [dict(corpo[0])]
            return corpo
        if tab == "vend_vendas_dia" and metodo == "POST":
            for novo in corpo:
                for i, r in enumerate(self.vendas):
                    if r["vendedor"] == novo["vendedor"] and str(r["data"])[:10] == str(novo["data"])[:10]:
                        self.vendas[i] = novo
                        break
                else:
                    self.vendas.append(novo)
            return corpo
        if tab == "vend_vendas_dia" and metodo == "GET":
            return sorted(self.vendas, key=lambda r: r["data"], reverse=True)[:1]
        return []

    def _todos(self, tab, params=None, metodo="GET", corpo=None):
        if tab == "vend_vendas_dia":
            desde = (params or {}).get("data", "gte.").split("gte.", 1)[-1]
            return [r for r in self.vendas if str(r["data"])[:10] >= desde]
        return []          # produto_grupos etc.: sem agrupamento no teste

    def _eq(self, v):
        return f"eq.{v}"


def _publicar(r, vendedor, dia, itens_raw):
    linhas = [linha_vend(*a) for a in itens_raw]
    nubi_web.vendedores.ler_vendedor = lambda corpo, nome: (linhas, vendedor, dia[:7])
    resp = nubi_web.rota_vendedores(r, "POST", "vend_dia", {"arquivo": "a.xlsx", "ate": dia}, b"x")
    assert resp["ok"], resp


def test_59_aum_sem_arquivo_fica_pendente_fora_dos_totais():
    r = RepoPainel()
    for dia in [f"2026-09-{d:02d}" for d in range(16, 23)]:            # AUMA: 7 dias seguidos com arquivo (base)
        _publicar(r, "AUMA", dia, [("Perfume A", 10, 1000, 100)])
    # 23/09: AUMA não manda arquivo nenhum (caso real) — nada é publicado para ela nesse dia
    nubi_web.rota_vendedores(r, "POST", "vend_dia_vazio", {"ate": "2026-09-23", "nome": "NOVO"}, b"")   # tem arquivo, vendeu 0
    _publicar(r, "SIENO", "2026-09-23", [("Perfume B", 5, 500, 100)])                                   # vendeu no dia

    # 1) não nasce linha nenhuma (nem zerada) pra AUMA em 23/09
    assert not [x for x in r.vendas if x["vendedor"] == "AUMA" and str(x["data"])[:10] == "2026-09-23"], r.vendas

    # 2) dia com arquivo e sem venda gera linha zerada de verdade
    novo_row = next(x for x in r.vendas if x["vendedor"] == "NOVO")
    assert novo_row["v"] == 0 and novo_row["u"] == 0, novo_row

    resp = nubi_web._painel_dia(r, "2026-09-23")

    # 3) aparece como coleta pendente no aviso
    assert "AUMA" in resp["sem_coleta"], resp["sem_coleta"]

    # 4) o dia sai dos totais: AUMA nem entra na lista de vendedores do dia (nem como zero)
    vendedores_hoje = {x["vendedor"]: x for x in resp["vendedores"]}
    assert "AUMA" not in vendedores_hoje, vendedores_hoje
    assert set(vendedores_hoje) == {"NOVO", "SIENO"}, vendedores_hoje

    # 5) quem tem linha zerada de verdade (NOVO) conta nos totais, não é "sem_dados"
    assert vendedores_hoje["NOVO"]["v"] == 0 and not vendedores_hoje["NOVO"]["sem_dados"], vendedores_hoje["NOVO"]
    assert resp["total"]["v"] == 500 and resp["total"]["u"] == 5, resp["total"]      # só SIENO: AUMA não soma nem falta


def test_59_regressao_dia_com_arquivo_sem_venda_nao_vira_pendente():
    # contraste explícito do card: dia COM arquivo e zero vendas nunca aparece em "sem_coleta"
    r = RepoPainel()
    for dia in [f"2026-09-{d:02d}" for d in range(16, 23)]:
        _publicar(r, "SIENO", dia, [("Perfume B", 5, 500, 100)])
    nubi_web.rota_vendedores(r, "POST", "vend_dia_vazio", {"ate": "2026-09-23", "nome": "SIENO"}, b"")
    resp = nubi_web._painel_dia(r, "2026-09-23")
    assert "SIENO" not in resp["sem_coleta"], resp["sem_coleta"]
    assert resp["vendedores"][0]["vendedor"] == "SIENO" and resp["vendedores"][0]["v"] == 0


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
