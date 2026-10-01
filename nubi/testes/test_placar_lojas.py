# -*- coding: utf-8 -*-
"""Placar das lojas (01/10, Bruno: "AUMAPERFUMARIA e AUMAFLEX são duas lojas do mesmo dono; tem que bater foto, preço,
número de anúncios: são várias variáveis"). Rodar: python3 testes/test_placar_lojas.py, na pasta nubi."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import meli  # noqa: E402
import nubi_web as w  # noqa: E402


def _sem_rede(*a, **k):
    raise RuntimeError("sem rede no teste")


meli._get = _sem_rede

V = "AUMA PERFUMARIA P2"


def foto(i, tipo="MLB"):
    return f"http://http2.mlstatic.com/D_{100000 + i}-{tipo}{9000000000 + i}_092025-I.jpg"


class Repo:
    def __init__(self, vit, seguido):
        itens = [{"foto": foto(i), "Price": 100.0 + i, "IsFull": True, "Status": "active"} for i in range(40)]
        itens += [{"foto": foto(i, "MLA"), "Price": 50.0, "IsFull": True, "Status": "active"} for i in range(30)]   # catálogo
        self.resumos = {"vend_fotos|" + V: json.dumps({"itens": itens}), "meli|seguidos": json.dumps({V: seguido}),
                        w.CANDIDATAS_CHAVE: json.dumps({V: [{"id": "358625041", "nome": "AUMAPERFUMARIA"}, {"id": "777", "nome": "AUMAFLEX"}]})}
        self.vit, self.eventos = vit, []

    def _eq(self, v):
        return f"eq.{v}"

    def _req(self, metodo, tabela, q=None, corpo=None, **k):
        if tabela == "ia_resumos" and metodo == "GET":
            c = (q or {}).get("chave", "")[3:]
            return [{"texto": self.resumos[c]}] if c in self.resumos else []
        if tabela == "ia_resumos" and metodo == "POST":
            for r in corpo:
                self.resumos[r["chave"]] = r["texto"]
        if tabela == "tarefa_eventos":
            self.eventos += corpo
        return []

    def _todos(self, tabela, q=None):
        if tabela == "vend_relatorios":
            return [{"id": 9, "vendedor": V, "mes": "2026-09-01"}]
        if tabela == "vend_anuncios":                       # relatório mensal: 1.751 anúncios, 1.496 ativos
            return [{"estado": "active"}] * 1496 + [{"estado": "paused"}] * 255
        if tabela == "vend_anuncios_ml":
            sid = (q or {}).get("seller_id", "")[3:]
            return [a for a in self.vit if a["seller_id"] == sid]
        return []


def vit(sid, idx, preco_mais=0.0, mla=()):
    xs = [{"seller_id": sid, "mlb": f"MLB{sid}{i}", "foto": foto(i), "preco": 100.0 + i + preco_mais, "full": True, "visto_em": "2026-10-02"} for i in idx]
    return xs + [{"seller_id": sid, "mlb": f"MLB{sid}A{i}", "foto": foto(i, "MLA"), "preco": 50.0, "full": True, "visto_em": "2026-10-02"} for i in mla]


def test_decide_pela_vitrine_e_ignora_foto_de_catalogo():
    meli.lojas = lambda ids: {i: {"nome": {"358625041": "AUMAPERFUMARIA", "777": "AUMAFLEX"}.get(i, i), "link": "x"} for i in ids}
    w._hashes_do_nome = lambda repo, nome: []
    # AUMAPERFUMARIA tem 30 das 40 fotos próprias com o mesmo preço; AUMAFLEX (mesmo dono) reaproveita 4 fotos e tem MUITA foto de catálogo igual
    v = vit("358625041", range(30)) + vit("777", range(4), preco_mais=30, mla=range(30)) + vit("3168346514", [1], mla=range(25))
    r = Repo(v, {"id": "3168346514", "nome": "EAMCOSMETICOS", "confianca": "provável"})
    # total de anúncios de cada loja ("N resultados" da vitrine): AUMAPERFUMARIA 1.520 bate com os 1.496 ativos; AUMAFLEX 300 não
    w.gravar_total_loja(r, "358625041", 1520, "vitrine"); w.gravar_total_loja(r, "777", 300, "vitrine"); w.gravar_total_loja(r, "3168346514", 957, "vitrine")
    pl = w.placar_lojas(r, V)
    assert pl["fotos_proprias"] == 40 and pl["anuncios_ativos"] == 1496 and pl["anuncios_relatorio"] == 1751
    por = {x["id"]: x for x in pl["lojas"]}
    assert por["358625041"]["fotos"] == 30 and por["358625041"]["preco"] == 30 and por["777"]["fotos"] == 4 and por["777"]["preco"] == 0
    assert por["3168346514"]["fotos"] == 1                                      # foto de catálogo (MLA) não conta
    assert por["358625041"]["total_bate"] and not por["777"]["total_bate"] and por["777"]["total_ml"] == 300
    t = w.decidir_pelo_placar(r, V)
    assert "1520 anúncios na loja (bate)" in t, t
    assert "✅ Decidido: AUMAPERFUMARIA (358625041), no lugar de EAMCOSMETICOS" in t, t
    seg = json.loads(r.resumos["meli|seguidos"])[V]
    assert seg["id"] == "358625041" and seg["confianca"] == "certa" and "30 de 40 fotos próprias" in seg["prova"]
    assert "1520 anúncios na loja x 1496 ativos" in seg["prova"]
    # o mesmo placar com o total da 1ª muito diferente do relatório: não decide
    r2 = Repo(v, {"id": "3168346514", "nome": "EAMCOSMETICOS", "confianca": "provável"})
    w.gravar_total_loja(r2, "358625041", 400, "vitrine"); w.gravar_total_loja(r2, "777", 300, "vitrine"); w.gravar_total_loja(r2, "3168346514", 957, "vitrine")
    t2 = w.decidir_pelo_placar(r2, V)
    assert "Não decide" in t2 and "não bate com os 1496 ativos" in t2, t2


def test_espera_vitrine_e_nao_decide_empate():
    w._hashes_do_nome = lambda repo, nome: []
    r = Repo(vit("358625041", range(30)), {"id": "358625041", "nome": "AUMAPERFUMARIA", "confianca": "provável"})
    assert w.decidir_pelo_placar(r, V).startswith("⏳") and "AUMAFLEX" in w.decidir_pelo_placar(r, V)
    r = Repo(vit("358625041", range(12)) + vit("777", range(10, 22)), {"id": "358625041", "nome": "AUMAPERFUMARIA", "confianca": "provável"})
    t = w.decidir_pelo_placar(r, V)
    assert "Não decide" in t and json.loads(r.resumos["meli|seguidos"])[V]["confianca"] == "provável", t
    # manual do Bruno: não muda
    r = Repo(vit("358625041", range(30)) + vit("777", range(2)), {"id": "777", "nome": "AUMAFLEX", "confianca": "manual"})
    assert "confirmada por você é outra" in w.decidir_pelo_placar(r, V)
    assert json.loads(r.resumos["meli|seguidos"])[V]["id"] == "777"


def test_rotulo_e_vitrine_da_candidata():
    assert w.rotulo_candidata(w.rotulo_cand(V, "777")) == (V, "777") and w.rotulo_candidata(V) is None
    r = Repo([], {"id": "358625041", "nome": "AUMAPERFUMARIA", "confianca": "provável"})
    gravados = []
    r._req_o = r._req
    r._req = lambda m, t, q=None, corpo=None, **k: gravados.extend(corpo) if t == "vend_anuncios_ml" else r._req_o(m, t, q, corpo, **k)
    meli.vitrine_cartoes = lambda cards, scripts: [{"mlb": "MLB1", "link": "l", "titulo": "t", "foto": foto(1), "preco": 101.0, "full": True,
                                                     "vendidos": None, "catalogo": None}]
    w.gravar_vitrine(r, w.rotulo_cand(V, "777"), "777", ["x"])
    assert gravados[0]["vendedor"] == "cand|777|" + V and gravados[0]["seller_id"] == "777"
    try:
        w.gravar_vitrine(r, w.rotulo_cand(V, "999"), "999", ["x"])
        raise AssertionError("loja que não é candidata devia ser recusada")
    except w.ErroNuvem:
        pass


def test_candidata_sem_id_ganha_o_id_sem_duplicar():
    r = Repo([], {})
    r.resumos[w.CANDIDATAS_CHAVE] = json.dumps({V: [{"id": "", "nome": "AUMAFLEX"}, {"id": "358625041", "nome": "AUMAPERFUMARIA"}]})
    xs = w.gravar_candidatas(r, V, [{"id": "777", "nome": "AUMAFLEX"}])
    assert sorted((x["id"], x["nome"]) for x in xs) == [("358625041", "AUMAPERFUMARIA"), ("777", "AUMAFLEX")], xs


if __name__ == "__main__":
    test_candidata_sem_id_ganha_o_id_sem_duplicar()
    test_decide_pela_vitrine_e_ignora_foto_de_catalogo()
    test_espera_vitrine_e_nao_decide_empate()
    test_rotulo_e_vitrine_da_candidata()
    print("ok placar lojas")
