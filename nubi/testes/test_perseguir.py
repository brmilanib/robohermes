# -*- coding: utf-8 -*-
"""28/09 (Bruno): anúncios perseguidos no Mercado Livre pelo Apify: cadastrar, disparar, guardar posição e variação."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import perseguir as p  # noqa: E402


class Repo:
    def __init__(self):
        self.t = {}

    def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
        if metodo == "GET":
            ch = (params or {}).get("chave", "")[3:]
            return [{"texto": self.t[ch]}] if ch in self.t else []
        for r in corpo:
            self.t[r["chave"]] = r["texto"]


def _apify(respostas, chamadas):
    def http(metodo, caminho, corpo=None, timeout=60):
        chamadas.append((metodo, caminho, corpo))
        for k, v in respostas.items():
            if k in caminho:
                return v
        return None
    return http


def test_cadastra_confere_e_guarda_a_posicao():
    os.environ["APIFY_TOKEN"] = "x"
    r, ch = Repo(), []
    p.salvar(r, {"acao": "adicionar", "anuncio": "https://produto.mercadolivre.com.br/MLB-4577439527-perfume", "termo": "ferrari black", "cep": "01001-000"})
    assert json.loads(r.t[p.LISTA])[0]["anuncio"] == "MLB4577439527"
    try:
        p.salvar(r, {"acao": "adicionar", "anuncio": "MLB4577439527", "termo": "Ferrari Black"})
        raise AssertionError("aceitou repetido")
    except p.ErroPerseguir:
        pass
    p._http = _apify({"/acts/": {"data": {"id": "R1", "defaultDatasetId": "D1"}}}, ch)
    ex = p.iniciar(r)
    assert ex["status"] == "rodando" and ch[0][2]["rankChecks"][0] == {"keyword": "ferrari black", "productId": "MLB4577439527",
                                                                       "country": "br", "postalCode": "01001-000"}
    try:
        p.iniciar(r)
        raise AssertionError("disparou duas vezes")
    except p.ErroPerseguir:
        pass
    p._http = _apify({"/actor-runs/R1": {"data": {"status": "SUCCEEDED", "usageTotalUsd": 0.0125}},
                      "/datasets/D1": [{"productId": "MLB4577439527", "keyword": "ferrari black", "organicPosition": 14,
                                        "pagesChecked": 1, "appliedPostalCode": "01001-000"}]}, ch)
    assert p.conferir(r)["status"] == "ok"
    # 2ª conferência: subiu para 9º
    r.t[p.EXEC] = json.dumps({"status": "rodando", "run_id": "R1", "dataset_id": "D2"})
    p._http = _apify({"/actor-runs/R1": {"data": {"status": "SUCCEEDED"}},
                      "/datasets/D2": [{"productId": "MLB4577439527", "keyword": "ferrari black", "organicPosition": 9}]}, ch)
    x = p.painel(r)["lista"][0]
    assert x["atual"]["posicao"] == 9 and x["variacao"] == 5 and [h["posicao"] for h in x["historico"]] == [14, 9]


def test_semanal_uma_vez_por_semana_e_sem_chave_avisa():
    os.environ["APIFY_TOKEN"] = "x"
    r, ch = Repo(), []
    p.salvar(r, {"acao": "adicionar", "anuncio": "MLB123456789", "termo": "perfume"})
    p._http = _apify({"/acts/": {"data": {"id": "R9", "defaultDatasetId": "D9"}}, "/actor-runs/R9": {"data": {"status": "RUNNING"}}}, ch)
    assert "disparada" in p.semanal(r)
    assert p.semanal(r) == "conferência ainda rodando no Apify"
    r.t[p.EXEC] = json.dumps({"status": "ok"})
    assert p.semanal(r) == "já conferido nesta semana"
    del os.environ["APIFY_TOKEN"]
    assert p.painel(r)["chave"] is False


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
