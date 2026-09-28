# -*- coding: utf-8 -*-
"""Card #111: o resumo do Atendente (TikTok/Shopee) na Sala vira contadores reais e junta as rodadas normais da mesma
hora de Brasília numa única mensagem; falha e aviso de login continuam saindo na hora, fora do agrupamento.
Rodar: python3 testes/test_atendente_resumo_hora.py (na pasta nubi)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.update(OPENAI_API_KEY="x", ANTHROPIC_API_KEY="x")

import nubi_web  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
os.environ.setdefault("NUBI_COLETOR_DIR", "/tmp/nubi-coletor-teste-111")
import coletor as c  # noqa: E402


class Repo:
    """Simula só o pedaço de reuniao_mensagens usado pelo agrupamento (GET com filtro por autor/meta, POST, PATCH)."""

    def __init__(self):
        self.linhas = []
        self._id = 0

    @staticmethod
    def _eq(v):
        return f"eq.{v}"

    def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
        assert tab == "reuniao_mensagens", tab
        if metodo == "GET":
            autor = str((params or {}).get("autor") or "").replace("eq.", "")
            tipo = str((params or {}).get("meta->>tipo") or "").replace("eq.", "")
            hora = str((params or {}).get("meta->>hora") or "").replace("eq.", "")
            ach = [r for r in self.linhas if r["autor"] == autor and (r.get("meta") or {}).get("tipo") == tipo
                   and (r.get("meta") or {}).get("hora") == hora]
            return sorted(ach, key=lambda r: -r["id"])[:1]
        if metodo == "POST":
            saida = []
            for c_ in corpo:
                self._id += 1
                row = dict(c_, id=self._id)
                self.linhas.append(row)
                saida.append(row)
            return saida
        if metodo == "PATCH":
            rid = int(str(params["id"]).replace("eq.", ""))
            for r in self.linhas:
                if r["id"] == rid:
                    r.update(corpo)
            return []
        raise AssertionError(metodo)


def test_1_resumo_agrupado_soma_contadores_e_atualiza_a_mesma_mensagem():
    repo = Repo()
    id1 = nubi_web._atendente_resumo_agrupado(repo, "Atendente TikTok", {
        "canal": "tiktok_shop", "registradas": 1, "enviadas": 0, "gratis": 17, "pago": 0, "custo": 0.0})
    assert len(repo.linhas) == 1 and repo.linhas[0]["id"] == id1
    id2 = nubi_web._atendente_resumo_agrupado(repo, "Atendente TikTok", {
        "canal": "tiktok_shop", "registradas": 2, "enviadas": 1, "gratis": 9, "pago": 0, "custo": 0.12})
    assert id2 == id1 and len(repo.linhas) == 1                        # a 2ª rodada da mesma hora atualiza a 1ª, não cria outra
    m = repo.linhas[0]["meta"]
    assert m["registradas"] == 3 and m["enviadas"] == 1 and m["rodadas"] == 2 and round(m["custo"], 2) == 0.12
    assert "3 mensagem(ns) trazida(s)" in repo.linhas[0]["texto"] and "1 resposta(s) enviada(s)" in repo.linhas[0]["texto"]
    assert "2 rodada(s)" in repo.linhas[0]["texto"]


def test_2_hora_diferente_abre_mensagem_nova():
    repo = Repo()
    nubi_web._atendente_resumo_agrupado(repo, "Atendente Shopee", {"canal": "shopee", "registradas": 1, "enviadas": 0})
    # força a mensagem gravada para "outra hora", simulando o relógio ter virado
    repo.linhas[0]["meta"]["hora"] = "2020-01-01T00"
    nubi_web._atendente_resumo_agrupado(repo, "Atendente Shopee", {"canal": "shopee", "registradas": 1, "enviadas": 0})
    assert len(repo.linhas) == 2                                        # hora nova: mensagem nova, não mexe na antiga
    assert repo.linhas[0]["meta"]["rodadas"] == 1 and repo.linhas[1]["meta"]["rodadas"] == 1


def test_3_texto_do_resumo_agrupado_so_tem_contadores():
    txt = nubi_web._texto_atendente_resumo("Atendente TikTok", "tiktok_shop", {
        "registradas": 0, "enviadas": 0, "gratis": 5, "pago": 0, "custo": 0.0, "rodadas": 3})
    assert "0 resposta(s) enviada(s)" in txt and "enviei" not in txt.lower() and "mandei" not in txt.lower()


def test_4_reuniao_postar_com_agrupar_nao_cria_uma_linha_por_rodada():
    r = Repo()
    for _ in range(3):
        d = {"autor": "Atendente TikTok", "texto": "rodada",
             "agrupar": {"canal": "tiktok_shop", "registradas": 1, "enviadas": 0}}
        agrupar = d.get("agrupar") or {}
        assert agrupar and d["autor"] in nubi_web.ATENDENTES_AGRUPAVEIS
        nubi_web._atendente_resumo_agrupado(r, d["autor"], agrupar)
    assert len(r.linhas) == 1 and r.linhas[0]["meta"]["registradas"] == 3


def test_5_sem_envio_falso_corta_frase_de_envio_com_0_enviadas():
    fim = "Registrei a conversa e enviei a resposta aprovada. Nenhuma outra pendência."
    assert c._sem_envio_falso(fim, 0) == "Nenhuma outra pendência."
    assert "enviei" not in c._sem_envio_falso(fim, 0).lower()
    assert c._sem_envio_falso(fim, 1) == fim                            # com envio de verdade, a frase fica


def test_6_sem_envio_falso_mantem_texto_sem_mencao_a_envio():
    fim = "Não há outras conversas recentes a processar."
    assert c._sem_envio_falso(fim, 0) == fim


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
