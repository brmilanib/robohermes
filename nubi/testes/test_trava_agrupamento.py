# -*- coding: utf-8 -*-
"""Trava do agrupamento (01/10, Bruno: "esses dados são o coração das nossas análises; precisa ter regras mais firmes").
Reproduz o Sabah Al Ward picado pela IA. Rodar: python3 testes/test_trava_agrupamento.py, na pasta nubi."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import pandas as pd  # noqa: E402
import nubi  # noqa: E402
import trava_agrupamento as trava  # noqa: E402
import linhas_ia  # noqa: E402

M = "AL WATANIAH"
G = "5055810013110"
TITULOS = [("Al Wataniah Sabah Al Ward Edp 100 Ml Feminino", G, 25000, "PHTEC"),
           ("Perfume Arabe Feminino Al Wataniah Sabah Al Ward Original 100ml", "7899463112978", 8000, "ICARBONXX"),
           ("Sabah Al Ward Sugar Al Wataniah Eau De Parfum 100ml", "087946041335", 3000, "MAMS"),
           ("Al Wataniah Durrat Al Aroos Eau De Parfum 85ml", "6291108735411", 2000, "WATHIQ"),
           ("Al Wataniah Attar Al Wesal Eau De Parfum 100ml", "6291108733486", 1500, "PIPIT")]


def df():
    linhas = [{"rid": i, "snapshot_id": 1, "titulo": t, "vendedor": v, "vendedor_id": v.lower() * 4, "marca_anuncio": "AL WATANIAH", "categoria": "",
               "gtin": g, "sku": "", "un": u, "fat": u * 140.0, "preco": 140.0, "un_hist": u, "fat_hist": 0, "dias_pub": 100, "exposicao": "",
               "catalogo": 1, "full": 1, "flex": 0, "internacional": 0, "loja_oficial": 0, "frete_gratis": 1, "bruto": {}}
              for i, (t, g, u, v) in enumerate(TITULOS)]
    return nubi.preparar(pd.DataFrame(linhas))


ANTES = {M: {"linhas": [["sabah", "Sabah"], ["durrat", "Durrat"], ["attar", "Attar"]]}}
IA = {M: {"linhas": [["sabah al ward original", "Sabah Al Ward Original"], ["sabah al ward sugar", "Sabah Al Ward Sugar"],
                     ["sabah al ward", "Sabah Al Ward"], ["durrat al aroos", "Durrat Al Aroos"], ["attar al wesal", "Attar Al Wesal"]]}}


def test_recusa_o_sabah_picado():
    nubi.definir_gtin_global({})
    t = trava.simular(df(), M, ANTES, IA)
    assert not t["ok"] and any("picado" in m for m in t["motivos"]), t
    assert t["metricas"]["produtos_depois"] > t["metricas"]["produtos_antes"]
    # renomear sem partir (Durrat -> Durrat Al Aroos) passa
    ok = {M: {"linhas": [["sabah", "Sabah"], ["durrat al aroos", "Durrat Al Aroos"], ["attar al wesal", "Attar Al Wesal"]]}}
    t2 = trava.simular(df(), M, ANTES, ok)
    assert t2["ok"], t2
    # título inteiro como linha (Jequiti) é recusado
    t3 = trava.simular(df(), M, ANTES, {M: {"linhas": [["perfume cebolinha jequiti 50ml desodorante colonia", "X"]]}})
    assert not t3["ok"] and "mais de 5 palavras" in t3["motivos"][0]


class Repo:
    def __init__(self):
        self.cfg = {k: {"linhas": [list(x) for x in v["linhas"]]} for k, v in ANTES.items()}
        self.resumos, self.recons = {}, []

    def _eq(self, v):
        return f"eq.{v}"

    def snapshots(self, marca=None):
        return pd.DataFrame([{"id": 1, "marca": M}])

    def anuncios(self, sid):
        return df()

    def _todos(self, tabela, q=None):
        if tabela == "anuncios":
            return [{"titulo": t, "un": u, "tipo": "EDP", "categoria": ""} for t, g, u, v in TITULOS]
        return []

    def _req(self, metodo, tabela, q=None, corpo=None, **k):
        if tabela == "ia_resumos" and metodo == "POST":
            for r in corpo:
                self.resumos[r["chave"]] = r["texto"]
        if tabela == "ia_resumos" and metodo == "GET":
            c = (q or {}).get("chave", "")[3:]
            return [{"texto": self.resumos[c]}] if c in self.resumos else []
        if tabela == "ia_resumos" and metodo == "DELETE":
            self.resumos.pop((q or {}).get("chave", "")[3:], None)
        return []

    def carregar_config(self):
        return {k: {"linhas": [list(x) for x in v["linhas"]]} for k, v in self.cfg.items()}

    def salvar_config(self, cfg, marca=None, apagar=None):
        self.cfg[marca] = cfg[marca]


def test_ia_so_propoe_e_aplicar_exige_trava():
    nubi.definir_gtin_global({})
    r = Repo()
    nubi.reconsolidar = lambda repo, cfg, marcas=None: r.recons.append(marcas)
    x = linhas_ia.revisar_marca(r, M, lambda p, s: ({"observacao": "", "linhas": [{"chave": k, "rotulo": v} for k, v in IA[M]["linhas"]]}, "chatgpt"))
    assert x["ok"] and not x["aplicada"] and not x["trava"]["ok"]
    assert r.cfg[M]["linhas"][0] == ["sabah", "Sabah"] and r.recons == []                # nada gravado
    y = linhas_ia.aplicar_proposta(r, M)
    assert not y["ok"] and "trava recusou" in y["motivo"] and r.cfg[M]["linhas"][0] == ["sabah", "Sabah"]
    z = linhas_ia.aplicar_proposta(r, M, forcar=True)                                     # só o Bruno, marcando forçar
    assert z["ok"] and z["forcada"] and r.recons == [[M]]
    assert linhas_ia.ler_proposta(r, M) is None


if __name__ == "__main__":
    test_recusa_o_sabah_picado()
    test_ia_so_propoe_e_aplicar_exige_trava()
    print("ok trava agrupamento")
