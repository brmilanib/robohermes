# -*- coding: utf-8 -*-
"""Testes do retry/rate-limit isolado por conector (card #3), com conectores falsos (nunca as lojas
reais). Rodar: python3 testes/test_retry_conector.py, na pasta nubi."""
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import store_connector as sc  # noqa: E402

PEDIDOS = {"mercado_livre": [{"id_externo": "1"}], "amazon": [{"id_externo": "2"}]}


class Sadio(sc.StoreConnector):
    def __init__(self, source):
        self.source, self.chamadas, self.fim = source, 0, None

    def fetch_orders(self, **kwargs):
        self.chamadas += 1
        self.fim = time.monotonic()
        return PEDIDOS[self.source]


class RateLimit(sc.StoreConnector):
    source = "shopee"

    def __init__(self):
        self.chamadas = 0

    def fetch_orders(self, **kwargs):
        self.chamadas += 1
        raise sc.ErroRateLimit("HTTP 429", retry_after="5")


class Quebrado(sc.StoreConnector):
    source = "tiktok"

    def __init__(self):
        self.chamadas = 0

    def fetch_orders(self, **kwargs):
        self.chamadas += 1
        raise RuntimeError("conexão recusada")


def test_3_falha_numa_loja_nao_para_nem_atrasa_as_outras():
    esperas, trava = {}, threading.Lock()

    def dormir(s):
        # grava a espera pedida e dorme de verdade (escala 1/100) para provar que as sãs não esperam
        nome = threading.current_thread().name
        with trava:
            esperas.setdefault(nome, []).append(s)
        time.sleep(s / 100)

    ml, amz, shp, tt = Sadio("mercado_livre"), Sadio("amazon"), RateLimit(), Quebrado()
    inicio = time.monotonic()
    res = sc.coletar_lojas([ml, shp, amz, tt], max_tentativas=3, backoff_inicial_s=2, backoff_max_s=60,
                           jitter=0.5, dormir=dormir, aleatorio=lambda: 0.5)
    total = time.monotonic() - inicio

    # lojas sãs: coleta completa, 1 tentativa, terminaram logo (sem esperar as que falharam)
    for c in (ml, amz):
        r = res[c.source]
        assert r["status"] == "ok" and r["dados"] == PEDIDOS[c.source] and r["tentativas"] == 1, r
        assert r["erro"] is None and c.chamadas == 1, r
        assert c.fim - inicio < 0.05, (c.source, c.fim - inicio)
    assert total >= 0.05, total  # as com falha dormiram de verdade, e as sãs não esperaram por elas

    # 429 com Retry-After: esgota 3 tentativas; espera = max(Retry-After, backoff com jitter)
    r = res["shopee"]
    assert shp.chamadas == 3 and r["tentativas"] == 3 and r["status"] == "pendente", r
    assert "429" in r["erro"] and r["aviso"], r
    assert esperas["coleta-shopee"] == [5.0, 5.0], esperas  # max(5, 2*1.25=2.5) e max(5, 4*1.25=5)

    # exceção comum: esgota 3 tentativas com backoff exponencial + jitter
    r = res["tiktok"]
    assert tt.chamadas == 3 and r["tentativas"] == 3 and r["status"] == "pendente", r
    assert "conexão recusada" in r["erro"], r
    assert esperas["coleta-tiktok"] == [2.5, 5.0], esperas

    # loja pendente nunca vira zero: sem dados, fora dos totais
    for s in ("shopee", "tiktok"):
        assert res[s]["dados"] is None, res[s]
    assert "coleta-mercado_livre" not in esperas and "coleta-amazon" not in esperas, esperas


def test_3_recupera_na_segunda_tentativa():
    class Instavel(sc.StoreConnector):
        source = "shopee"
        chamadas = 0

        def fetch_orders(self, **kwargs):
            self.chamadas += 1
            if self.chamadas == 1:
                raise sc.ErroRateLimit("HTTP 429")
            return [{"id_externo": "7"}]

    esperas = []
    r = sc.coletar_com_retry(Instavel(), dormir=esperas.append, aleatorio=lambda: 0.0)
    assert r["status"] == "ok" and r["tentativas"] == 2 and r["dados"] == [{"id_externo": "7"}], r
    assert r["erro"] is None, r
    assert esperas == [2.0], esperas


def test_3_backoff_tem_teto():
    assert sc.espera_backoff(10, 2, 60, 0.0, lambda: 0.0) == 60
    assert sc.espera_backoff(2, 2, 60, 0.5, lambda: 1.0) == 3.0


def test_3_retry_after_em_segundos_e_data_http():
    assert sc.segundos_retry_after("12") == 12.0
    assert sc.segundos_retry_after(None) is None and sc.segundos_retry_after("lixo") is None
    agora = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    assert sc.segundos_retry_after(format_datetime(agora + timedelta(seconds=30), usegmt=True), agora=agora) == 30.0
    assert sc.segundos_retry_after(format_datetime(agora - timedelta(seconds=30), usegmt=True), agora=agora) == 0.0


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
