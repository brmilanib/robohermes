# -*- coding: utf-8 -*-
"""Histórico do monitor de preços (01/10, Bruno: "que dia mudou o preço, quanto mudou"). Rodar na pasta nubi."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import precos  # noqa: E402


def test_mudancas_e_detalhe():
    h = [{"dia": "2026-10-01", "preco": 221.26, "preco_original": 299.9, "status": "ativo", "estoque": 50},
         {"dia": "2026-10-02", "preco": 221.26, "preco_original": 299.9, "status": "ativo", "estoque": 48},
         {"dia": "2026-10-03", "preco": 199.9, "preco_original": None, "status": "ativo", "estoque": 48},   # sem riscado: não é mudança
         {"dia": "2026-10-05", "preco": 209.9, "preco_original": 299.9, "status": "pausado", "estoque": 0}]
    mu = precos.mudancas(h)
    preco = [m for m in mu if m["campo"] == "preco"]
    assert [(m["dia"], m["de"], m["para"], m["diff"]) for m in preco] == [("2026-10-05", 199.9, 209.9, 10.0), ("2026-10-03", 221.26, 199.9, -21.36)], preco
    assert preco[1]["dia_antes"] == "2026-10-02" and round(preco[1]["pct"], 4) == round(199.9 / 221.26 - 1, 4)
    assert not any(m["campo"] == "preco_original" for m in mu)
    assert [m["para"] for m in mu if m["campo"] == "status"] == ["pausado"]
    assert [m["para"] for m in mu if m["campo"] == "estoque"] == [0, 48]

    class R:
        def __init__(self):
            self.d = {precos.LISTA: [{"mlb": "MLB7440859356", "titulo": "Club de Nuit", "preco_inicial": 221.26, "desde": "2026-10-01T03:00:00+00:00"}],
                      precos.HIST + "MLB7440859356": h}
    precos._ler = lambda repo, chave, padrao: repo.d.get(chave, padrao)
    d = precos.detalhe(R(), "MLB-7440859356")
    assert d["atual"] == 209.9 and d["minimo"] == 199.9 and d["maximo"] == 221.26 and d["dias"] == 4 and d["ultimo_dia"] == "2026-10-05"
    assert round(d["var_inicio"], 4) == round(209.9 / 221.26 - 1, 4) and len(d["mudancas"]) == len(mu)


def test_leitura_pela_api_de_hora_em_hora():
    d = {precos.LISTA: [{"mlb": "MLB1234567", "titulo": "X"}, {"mlb": "MLB2345678", "titulo": "Y"}]}
    precos._ler = lambda repo, chave, padrao: d.get(chave, padrao)
    precos._gravar = lambda repo, chave, valor: d.__setitem__(chave, valor)
    itens = {"MLB1234567": {"preco": 100.0, "preco_cheio": 150.0, "status": "active", "disponivel": 5},
             "MLB2345678": {"anuncio": "MLB2345678", "bloqueado": True}}
    assert precos.ler_pela_api(None, lambda ids: itens) == (1, 1)
    assert precos.ler_pela_api(None, lambda ids: itens) == (1, 1)                 # igual: não cria ponto novo
    assert len(d[precos.HIST + "MLB1234567"]) == 1 and d[precos.HIST + "MLB1234567"][0]["fonte"] == "api"
    itens["MLB1234567"]["preco"] = 95.0
    precos.ler_pela_api(None, lambda ids: itens)                                    # mudou no mesmo dia: ponto novo com a hora
    h = d[precos.HIST + "MLB1234567"]
    assert [p["preco"] for p in h] == [100.0, 95.0] and h[0]["status"] == "ativo"
    mu = precos.mudancas(h)
    assert mu[0]["campo"] == "preco" and mu[0]["de"] == 100.0 and mu[0]["para"] == 95.0 and mu[0]["em"]
    assert precos.pendente(None, {"ativo": True, "horario": "00:00"})["itens"] == [{"mlb": "MLB2345678", "link": precos.link_de("MLB2345678")}]
    # 01/10 (Bruno): cada leitura conta e guarda a hora; título "Clássico" (tipo do anúncio, vindo do cartão) é trocado
    x = [i for i in d[precos.LISTA] if i["mlb"] == "MLB1234567"][0]
    assert x["leituras"] == 3 and x["ultima_leitura"], x
    x["titulo"] = "Clássico"
    itens["MLB1234567"]["titulo"] = "Perfume Club De Nuit Intense Man 105ml"
    precos.ler_pela_api(None, lambda ids: itens)
    assert x["titulo"] == "Perfume Club De Nuit Intense Man 105ml" and precos.titulo_ruim("Premium")
    pn = [i for i in precos.painel(None) if i["mlb"] == "MLB1234567"][0]
    assert pn["leituras"] == 4 and pn["ultima_em"] and pn["titulo_ok"] and pn["menor_em"], pn


if __name__ == "__main__":
    test_mudancas_e_detalhe()
    test_leitura_pela_api_de_hora_em_hora()
    print("ok histórico de preços")
