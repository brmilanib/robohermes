# -*- coding: utf-8 -*-
"""Card #107: produtos_ia guarda o embedding de cada título (hash do modelo + versão das regras + texto, em ia_lotes
tipo 'embedding') e a 2ª rodada seguida não chama a IA de novo; mudou a versão das regras ou o modelo, recalcula.
Os pares abaixo do corte continuam fora de produto_grupos e os GTINs com o mesmo nome continuam em gtin_conferir.
Banco e OpenAI falsos. Rodar: python3 testes/test_cache_embeddings.py, na pasta nubi."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.update(OPENAI_API_KEY="x", ANTHROPIC_API_KEY="x", OLLAMA_API_KEY="x")

import ia  # noqa: E402
import nubi_web as w  # noqa: E402
import produtos_iguais as pi  # noqa: E402

LINHAS = [  # (chave, título, vetor): marca LATTAFA em todos
    ("6291108735411", "Perfume Lattafa Asad 100ml", [1, 0, 0]),
    ("6291108735412", "Lattafa Asad Perfume 100ml", [0.95, 0.3122, 0]),        # outro GTIN, mesmo nome: conferir
    ("T:asad edp", "Asad Lattafa 100ml Original", [0.9, 0.4359, 0]),           # junta ao GTIN
    ("T:asad cinza", "Asad Lattafa Perfume 100ml Lacrado", [0.8, -0.6, 0]),   # abaixo do corte: fica sozinho
]
VET = {t: v for _, t, v in LINHAS}


class Repo:
    def __init__(self):
        self.t = {"produto_grupos": {}, "ia_lotes": {}}

    def _todos(self, caminho, params, metodo="GET", corpo=None):
        if caminho == "vend_relatorios":
            return [{"id": 1, "mes": "2026-09-01"}]
        if caminho == "rpc/vend_prod_mes":
            return [{"chave": c, "titulo": t, "marca": "LATTAFA", "vendas": 100 - i} for i, (c, t, _) in enumerate(LINHAS)]
        return self._req("GET", caminho, params)

    def _req(self, metodo, caminho, params=None, corpo=None, prefer=None):
        tab, params = self.t[caminho], params or {}
        pk = "chave" if caminho == "produto_grupos" else "id"
        if metodo == "POST":
            for r in corpo:
                tab[r[pk]] = r
            return None
        filtros = {k: v for k, v in params.items() if k not in ("select", "limit", "offset", "order")}

        def bate(r):
            for k, v in filtros.items():
                if v.startswith("eq.") and str(r.get(k)) != v[3:]:
                    return False
                if v.startswith("in.(") and str(r.get(k)) not in v[4:-1].split(","):
                    return False
            return True
        achados = [r for r in tab.values() if bate(r)]
        if metodo == "DELETE":
            for r in achados:
                del tab[r[pk]]
            return None
        return achados


CHAMADAS = []


def _emb_falso(textos, modelo=None):
    CHAMADAS.append(len(textos))
    return [VET[t.split(" | ", 1)[1]] for t in textos]


def _rodar(repo):
    CHAMADAS.clear()
    res = w.agrupar_produtos(repo)
    return sum(CHAMADAS), res


def _grupos(repo):
    return {k: (r["grupo"], r["metodo"]) for k, r in repo.t["produto_grupos"].items()}


def test_segunda_rodada_usa_o_cache_e_nao_muda_os_grupos():
    ia.embeddings, repo = _emb_falso, Repo()
    n1, _ = _rodar(repo)
    g1 = _grupos(repo)
    n2, _ = _rodar(repo)
    assert n1 > 0 and n2 < 0.1 * n1, (n1, n2)
    assert _grupos(repo) == g1
    # par cinza (0,80 < corte 0,82) nunca é juntado sozinho; GTINs com o mesmo nome só vão para conferência
    assert "T:asad cinza" not in g1
    assert g1["T:asad edp"][1] == "ia"
    assert g1["par:6291108735411|6291108735412"] == ("6291108735411", "gtin_conferir")
    assert not any(k.isdigit() for k in g1)                          # nenhum GTIN virou grupo sem conferência


def test_mudou_versao_das_regras_ou_modelo_recalcula():
    ia.embeddings, repo = _emb_falso, Repo()
    n1, _ = _rodar(repo)
    antes = pi.VERSAO_REGRAS
    try:
        pi.VERSAO_REGRAS = antes + 1
        assert _rodar(repo)[0] == n1
        assert _rodar(repo)[0] == 0                                   # e a versão nova também fica guardada
    finally:
        pi.VERSAO_REGRAS = antes
    os.environ["NUBI_IA_EMBED"] = "text-embedding-3-large"
    try:
        assert _rodar(repo)[0] == n1
    finally:
        del os.environ["NUBI_IA_EMBED"]
    assert _rodar(repo)[0] == 0                                       # voltou ao modelo/versão de antes: cache antigo vale


def test_vetor_do_cache_e_o_mesmo():
    ia.embeddings, repo = _emb_falso, Repo()
    textos = ["LATTAFA | " + t for _, t, _ in LINHAS]
    a = w._embeddings_cache(repo, textos)
    b = w._embeddings_cache(repo, textos)
    assert [[round(x, 6) for x in v] for v in a] == [[round(x, 6) for x in v] for v in b]


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
