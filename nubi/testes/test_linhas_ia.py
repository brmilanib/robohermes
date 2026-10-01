# -*- coding: utf-8 -*-
"""Revisão das linhas de produto pela IA (01/10, Bruno: Light Blue juntou fem/masc/Intense/Capri in Love).
Rodar: python3 testes/test_linhas_ia.py, na pasta nubi."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import pandas as pd  # noqa: E402
import linhas_ia  # noqa: E402
import nubi  # noqa: E402

TITULOS = [("Perfume Dolce & Gabbana Light Blue Feminino Edp 100ml", 900), ("Dolce&gabbana Light Blue For Men Eau De Parfum 100ml", 300),
           ("Dolce & Gabbana Light Blue Capri In Love Masculino Eau De Parfum", 80), ("Light Blue Dolce & Gabbana Edp Intense 100ml", 50),
           ("Dolce Gabbana The One For Men Edp 100ml", 40)]


class Repo:
    def __init__(self):
        self.cfg = {"DOLCE & GABBANA": {"linhas": [["light blue", "Light Blue"], ["blue femin", "Blue Femin"], ["edpi", "Edpi"]]}}
        self.resumos, self.reconsolidadas = {}, []

    def _eq(self, v):
        return f"eq.{v}"

    def snapshots(self, marca=None):
        return pd.DataFrame([{"id": 9, "marca": "DOLCE & GABBANA"}])

    def _todos(self, tabela, q=None):
        if tabela == "anuncios":
            return [{"titulo": t, "un": u, "tipo": "EDP", "categoria": ""} for t, u in TITULOS] + [{"titulo": "Contratipo X", "un": 999, "tipo": "Outra marca", "categoria": ""}]
        if tabela == "ia_resumos":
            return [{"chave": k, "criado_em": "2026-10-01T00:00:00+00:00"} for k in self.resumos]
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
        return {k: dict(v) for k, v in self.cfg.items()}

    def salvar_config(self, cfg, marca=None, apagar=None):
        self.cfg[marca] = cfg[marca]


def test_valida_e_ordena_e_grava_antes_depois():
    r = Repo()
    nubi.reconsolidar = lambda repo, cfg, marcas=None: r.reconsolidadas.append(marcas)
    resposta = {"observacao": "Light Blue tem 4 variações", "linhas": [
        {"chave": "light blue capri in love", "rotulo": "Light Blue Capri in Love"}, {"chave": "Light Blue Intense", "rotulo": "Light Blue Intense"},
        {"chave": "light blue for men", "rotulo": "Light Blue Pour Homme"}, {"chave": "light blue pour homme", "rotulo": "Light Blue Pour Homme"},
        {"chave": "light blue", "rotulo": "Light Blue"}, {"chave": "the one for men", "rotulo": "The One For Men"},
        {"chave": "contratipo x", "rotulo": "Lixo"}, {"chave": "light blue", "rotulo": "Repetida"}]}
    x = linhas_ia.revisar_marca(r, "DOLCE & GABBANA", lambda pedido, schema: (resposta, "chatgpt"))
    assert x["ok"] and [k for k, _ in x["depois"]] == ["light blue capri in love", "light blue for men", "the one for men", "light blue"], x["depois"]
    # "light blue intense" não aparece nos títulos ("edp intense" vem depois): descartada; "pour homme" e o contratipo também
    assert "light blue intense" in x["descartadas"] and "contratipo x" in x["descartadas"]
    assert r.cfg["DOLCE & GABBANA"]["linhas"] == x["depois"] and r.reconsolidadas == [["DOLCE & GABBANA"]]
    reg = json.loads(r.resumos[linhas_ia.CHAVE + "DOLCE & GABBANA"])
    assert reg["antes"][0] == ["light blue", "Light Blue"] and reg["ia"] == "chatgpt"
    assert linhas_ia.pendentes(r) == []                                     # revisada hoje: não pende
    # o pedido leva os títulos por venda e nunca o contratipo
    ped = linhas_ia.pedido("DOLCE & GABBANA", r.cfg["DOLCE & GABBANA"]["linhas"], linhas_ia.titulos_da_marca(r, "DOLCE & GABBANA")[0])
    assert "(900 un.)" in ped and "Contratipo X" not in ped
    # desfazer volta a lista de antes
    d = linhas_ia.desfazer(r, "DOLCE & GABBANA")
    assert d["ok"] and r.cfg["DOLCE & GABBANA"]["linhas"][0] == ["light blue", "Light Blue"] and linhas_ia.CHAVE + "DOLCE & GABBANA" not in r.resumos
    assert linhas_ia.pendentes(r) == ["DOLCE & GABBANA"]


def test_sem_linha_valida_nao_grava():
    r = Repo()
    x = linhas_ia.revisar_marca(r, "DOLCE & GABBANA", lambda p, s: ({"observacao": "", "linhas": [{"chave": "nada a ver", "rotulo": "X"}]}, "claude"))
    assert not x["ok"] and r.cfg["DOLCE & GABBANA"]["linhas"][0] == ["light blue", "Light Blue"]


if __name__ == "__main__":
    test_valida_e_ordena_e_grava_antes_depois()
    test_sem_linha_valida_nao_grava()
    print("ok linhas ia")
