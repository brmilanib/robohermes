# -*- coding: utf-8 -*-
"""Card #110: ia.embeddings trata HTTP 429 com espera (Retry-After do provedor, senão 30s/60s/120s) e tenta de
novo, até 3 vezes por lote de 500; esgotou, levanta ia.LimiteProvedor (nunca sobe como erro genérico). OpenAI
falsa (ia._post_json trocado). Rodar: python3 testes/test_ia_retry_429.py, na pasta nubi."""
import os
import sys
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.update(OPENAI_API_KEY="x")

import ia  # noqa: E402


def _429(retry_after=None):
    hdrs = {"Retry-After": str(retry_after)} if retry_after is not None else {}
    return urllib.error.HTTPError("https://api.openai.com/v1/embeddings", 429, "Too Many Requests", hdrs, None)


def _emb(index_para_vetor):
    return {"data": [{"index": i, "embedding": v} for i, v in index_para_vetor.items()]}


def test_retry_after_do_provedor_e_usado():
    esperas = []
    respostas = iter([_429(2), _emb({0: [1.0]})])

    def _post_falso(url, corpo, cab, timeout=90):
        r = next(respostas)
        if isinstance(r, Exception):
            raise r
        return r

    ia._post_json, antigo = _post_falso, ia.time.sleep
    ia.time.sleep = lambda s: esperas.append(s)
    try:
        assert ia.embeddings(["a"]) == [[1.0]]
        assert esperas == [2.0]
    finally:
        ia.time.sleep = antigo


def test_sem_retry_after_usa_30_60_120():
    esperas = []
    respostas = iter([_429(), _429(), _emb({0: [1.0]})])

    def _post_falso(url, corpo, cab, timeout=90):
        r = next(respostas)
        if isinstance(r, Exception):
            raise r
        return r

    ia._post_json, antigo = _post_falso, ia.time.sleep
    ia.time.sleep = lambda s: esperas.append(s)
    try:
        assert ia.embeddings(["a"]) == [[1.0]]
        assert esperas == [30, 60]
    finally:
        ia.time.sleep = antigo


def test_esgotou_3_tentativas_levanta_limite_provedor_sem_4a_espera():
    esperas = []

    def _post_sempre_429(url, corpo, cab, timeout=90):
        raise _429()

    ia._post_json, antigo = _post_sempre_429, ia.time.sleep
    ia.time.sleep = lambda s: esperas.append(s)
    try:
        try:
            ia.embeddings(["a"])
            raise AssertionError("devia levantar LimiteProvedor")
        except ia.LimiteProvedor:
            pass
        assert esperas == [30, 60]                        # 2 esperas entre as 3 tentativas, nenhuma depois da 3ª
    finally:
        ia.time.sleep = antigo


def test_outro_erro_http_nao_e_engolido():
    def _post_500(url, corpo, cab, timeout=90):
        raise urllib.error.HTTPError("https://api.openai.com/v1/embeddings", 500, "Internal Server Error", {}, None)

    ia._post_json, antigo = _post_500, ia.time.sleep
    try:
        try:
            ia.embeddings(["a"])
            raise AssertionError("devia propagar o erro 500")
        except ia.LimiteProvedor:
            raise AssertionError("500 não é limite do provedor")
        except urllib.error.HTTPError as e:
            assert e.code == 500
    finally:
        ia.time.sleep = antigo


def test_limite_seg_evita_estourar_o_tempo_da_funcao():
    """Card #110 (achado da revisão): rate limit sustentado em muitos lotes não pode somar minutos de espera e
    estourar o tempo da função da Vercel (a plataforma mata o processo sem levantar exceção); limite_seg corta
    antes disso, com LimiteProvedor, mesmo sem nenhum lote sozinho esgotar as 3 tentativas."""
    relogio = {"t": 0.0}
    tentativa_do_lote = {}

    def _monotonic():
        return relogio["t"]

    def _sleep(s):
        relogio["t"] += s

    def _post_flaky_429(url, corpo, cab, timeout=90):
        chave = tuple(corpo["input"][:1])
        c = tentativa_do_lote.get(chave, 0) + 1
        tentativa_do_lote[chave] = c
        if c < 3:                                          # cada lote passa na 3ª tentativa (nunca esgota sozinho)
            raise _429()
        return _emb({i: [0.0] for i in range(len(corpo["input"]))})

    ia._post_json = _post_flaky_429
    monot_antigo, sleep_antigo = ia.time.monotonic, ia.time.sleep
    ia.time.monotonic, ia.time.sleep = _monotonic, _sleep
    try:
        textos = [str(i) for i in range(4000)]             # 8 lotes de 500 (o máximo que agrupar_produtos manda)
        try:
            ia.embeddings(textos, limite_seg=200)
            raise AssertionError("devia esgotar o orçamento antes de terminar todos os lotes")
        except ia.LimiteProvedor:
            pass
        # sem limite_seg isso somaria ~720s (30+60 por lote x 8); com o orçamento, para bem antes
        assert relogio["t"] < 200 + 120, relogio["t"]
    finally:
        ia.time.monotonic, ia.time.sleep = monot_antigo, sleep_antigo


def test_progresso_recebe_cada_lote_pronto():
    chamadas = []

    def _post_ok(url, corpo, cab, timeout=90):
        return _emb({i: [float(i)] for i in range(len(corpo["input"]))})

    ia._post_json = _post_ok
    textos = [str(i) for i in range(1200)]                 # 3 lotes: 500, 500, 200
    v = ia.embeddings(textos, progresso=lambda inicio, vet: chamadas.append((inicio, len(vet))))
    assert len(v) == 1200
    assert chamadas == [(0, 500), (500, 500), (1000, 200)]


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
