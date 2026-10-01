"""01/10 (Bruno): monitor de preços ao meio-dia e às 19 h; preço mudou = aviso piscando até ele ver; título certo do ML
(o coletor abre a página dos que estão sem título) e as tags Catálogo / FULL."""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import precos  # noqa: E402
from test_precos_monitor import Repo  # noqa: E402

BR = precos.BRASILIA


def test_rodadas_12_e_19():
    assert precos.rodada_atual(datetime(2026, 10, 1, 11, 59, tzinfo=BR)) == datetime(2026, 9, 30, 19, 0, tzinfo=BR)
    assert precos.rodada_atual(datetime(2026, 10, 1, 12, 0, tzinfo=BR)) == datetime(2026, 10, 1, 12, 0, tzinfo=BR)
    assert precos.rodada_atual(datetime(2026, 10, 1, 21, 5, tzinfo=BR)) == datetime(2026, 10, 1, 19, 0, tzinfo=BR)
    r = Repo()
    t = datetime(2026, 10, 1, 12, 10, tzinfo=BR)
    ini = precos.api_devida(r, t)
    assert ini == datetime(2026, 10, 1, 12, 0, tzinfo=BR)
    precos.marcar_rodada(r, ini)
    assert precos.api_devida(r, t + timedelta(hours=2)) is None              # 14h: a das 12h já foi
    assert precos.api_devida(r, datetime(2026, 10, 1, 19, 3, tzinfo=BR)) is not None


def test_pendente_titulo_e_rodada():
    r = Repo()
    precos.seguir(r, {"mlb": "MLB4000000111", "titulo": "Clássico"})
    precos.seguir(r, {"mlb": "MLB4000000222", "titulo": "Perfume Cuba Gold Masculino 100ml"})
    precos.gravar_leitura(r, [{"mlb": "MLB4000000111", "preco": 10}, {"mlb": "MLB4000000222", "preco": 20}])
    agora = datetime.now(BR)
    p = precos.pendente(r, {"ativo": True}, agora)
    # o lido com título bom não volta; o de título "Clássico" volta para o coletor ler o <h1>
    ini = precos.rodada_atual(agora)
    if agora >= ini + timedelta(minutes=20):
        assert [x["mlb"] for x in p["itens"]] == ["MLB4000000111"] and p["rodar"]
    lido = precos.ler_pagina({"fracao": "10", "centavos": "00", "titulo": "Perfume Ferrari Black 125ml Eau De Toilette",
                              "catalogo": True, "full": True})
    precos.gravar_leitura(r, [dict(lido, mlb="MLB4000000111")])
    x = next(x for x in precos.lista(r) if x["mlb"] == "MLB4000000111")
    assert x["titulo"].startswith("Perfume Ferrari") and x["catalogo"] is True and x["full"] is True
    assert not [i for i in precos.pendente(r, {"ativo": True}, agora)["itens"] if i["mlb"] == "MLB4000000111"]


def test_aviso_quando_o_preco_muda():
    r = Repo()
    precos.seguir(r, {"mlb": "MLB4000000333", "titulo": "Perfume Yara Lattafa 100ml", "catalogo": False, "full": True})
    precos.gravar_leitura(r, [{"mlb": "MLB4000000333", "preco": 130.19}], dia="2026-10-01")
    assert precos.alertas(r) == []
    precos.gravar_leitura(r, [{"mlb": "MLB4000000333", "preco": 130.19}], dia="2026-10-01")      # igual: sem aviso
    assert precos.alertas(r) == []
    precos.gravar_leitura(r, [{"mlb": "MLB4000000333", "preco": 119.9}], dia="2026-10-02")
    a = precos.alertas(r)
    assert len(a) == 1 and a[0]["de"] == 130.19 and a[0]["para"] == 119.9 and a[0]["pct"] < 0
    assert precos.marcar_visto(r, "MLB-4000000333") == 1 and precos.alertas(r) == []
    x = precos.lista(r)[0]
    assert x["catalogo"] is False and x["full"] is True


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
