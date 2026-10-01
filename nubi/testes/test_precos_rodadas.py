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
    # lido só pela API (sem fonte = navegador aqui? não: gravar_leitura sem fonte = página) -> ninguém falta
    ini = precos.rodada_atual(agora)
    if agora >= ini + timedelta(minutes=20):
        assert p["itens"] == [] and not p["rodar"]
    precos.gravar_leitura(r, [{"mlb": "MLB4000000111", "preco": 10, "fonte": "api"}])
    x0 = next(x for x in precos.lista(r) if x["mlb"] == "MLB4000000111")
    x0.pop("ultima_pagina", None)
    precos._gravar(r, precos.LISTA, [x0] + [x for x in precos.lista(r) if x["mlb"] != "MLB4000000111"])
    if agora >= ini + timedelta(minutes=20):
        assert [x["mlb"] for x in precos.pendente(r, {"ativo": True}, agora)["itens"]] == ["MLB4000000111"]
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


PAGINA = """<html><head><script>window.x = {\\"category_id\\":\\"MLB6284\\",\\"listing_type_id\\":\\"gold_special\\"};</script></head><body>
<div class="ui-pdp-header"><span>Novo | +1000 vendidos</span>
<div><span class="ui-pdp-promotions-pill-label">MAIS VENDIDO</span> <a href="https://www.mercadolivre.com.br/mais-vendidos/MLB6284">2º em Perfumes Jacques Bogart</a></div>
<h1>Jacques Bogart Silver Scent Intense Edt 200ml Para Masculino</h1></div>
<div class="ui-pdp-price__second-line"><span class="andes-money-amount__fraction">309</span><span class="andes-money-amount__cents">99</span></div>
<div class="ui-pdp-buybox"><p>Estoque disponível</p><p>Armazenado e enviado pelo <svg class="ui-pdp-icon--full"></svg> FULL</p>
<p>Quantidade: 1 unidade (+50 disponíveis)</p><div class="ui-pdp-seller__header__title">Vendido por Sieno</div></div>
<div class="ui-pdp-other-sellers"><a>13 produtos novos a partir de R$ 309,99</a></div></body></html>"""


def test_pagina_do_anuncio_tags_e_calculadora():
    import importlib.util
    from playwright.sync_api import sync_playwright
    raiz = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("coletor", raiz / "public" / "coletor" / "coletor.py")
    col = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(col)
    exe = os.environ.get("NUBI_CHROMIUM") or "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = b.new_page()
        pg.set_content(PAGINA)
        x = pg.evaluate(col.JS_ML_PRECO)
        b.close()
    lido = precos.ler_pagina(x)
    assert lido["preco"] == 309.99 and lido["estoque"] == 50 and lido["estoque_mais"] is True, lido
    assert lido["full"] is True and lido["catalogo"] is True and lido["titulo"].startswith("Jacques Bogart Silver Scent")
    assert lido["mais_vendido"] == "MAIS VENDIDO · 2º em Perfumes Jacques Bogart", lido["mais_vendido"]
    assert lido["categoria"] == "MLB6284" and lido["tipo_id"] == "gold_special"
    r = Repo()
    precos.seguir(r, {"mlb": "MLB5141216661", "titulo": "Clássico", "seller_id": "1142362911", "gtin": "3355991004672"})
    precos.gravar_leitura(r, [dict(lido, mlb="MLB5141216661")])
    it = precos.lista(r)[0]
    assert it["mais_vendido"].startswith("MAIS VENDIDO") and it["estoque_mais"] and it["categoria"] == "MLB6284"
    # conta: 309,99 − tarifa 40,30 − frete 24,45 − imposto 10% 31,00 − custo 150 = 64,24
    c = precos.contas(309.99, 150.0, 40.30, 24.45, 10)
    assert c["recebido"] == 245.24 and c["imposto"] == 31.0 and c["lucro"] == 64.24
    assert c["margem"] == round(64.24 / 309.99, 4) and c["roi"] == round(64.24 / 150, 4)
    assert precos.contas(309.99, None, 40.3, 0, 0)["lucro"] is None
    # nubi_web: custo do MEU estoque pelo GTIN + tarifa/frete da API (falsos)
    import nubi_web as w
    import meli
    antes = (w._estoque_itens, meli.tarifa, meli.frete_do_vendedor, meli.tem_chave)
    w._estoque_itens = lambda repo, aid: [{"sku": "3355991004672", "titulo": "Silver Scent Intense 200ml", "custo_medio": 150, "disponivel": 7}]
    meli.tarifa = lambda preco, cat, tipo: {"total": 40.30}
    meli.frete_do_vendedor = lambda v, m: 24.45
    meli.tem_chave = lambda: True
    r2 = Repo()
    r2._req_orig = r2._req
    r2._req = lambda metodo, tabela, params=None, corpo=None, prefer=None: [{"id": 1}] if tabela == "estoque_atualizacoes" else r2._req_orig(metodo, tabela, params, corpo, prefer)
    r2.res[precos.CALC] = json.dumps({"imposto_pct": 10})
    try:
        itens = [{"mlb": "MLB5141216661", "atual": 309.99, "categoria": "MLB6284", "tipo_id": "gold_special", "seller_id": "1142362911",
                  "gtin": "3355991004672", "titulo": "Jacques Bogart Silver Scent Intense Edt 200ml"}]
        w._calc_monitor(r2, itens)
        assert itens[0]["meu"]["custo"] == 150 and itens[0]["meu"]["casado_por"] == "gtin"
        assert itens[0]["calc"]["lucro"] == 64.24 and not itens[0]["calc"]["sem_tarifa"]
    finally:
        w._estoque_itens, meli.tarifa, meli.frete_do_vendedor, meli.tem_chave = antes


def test_eventos_de_tags_full_estoque_posicao():
    r = Repo()
    precos.seguir(r, {"mlb": "MLB5141216661", "titulo": "Silver Scent Intense 200ml Jacques Bogart"})
    pag = lambda **k: dict({"mlb": "MLB5141216661", "preco": 309.99, "status": "ativo", "estoque": 50, "full": True, "catalogo": True,
                            "mais_vendido": "MAIS VENDIDO · 2º em Perfumes Jacques Bogart"}, **k)
    precos.gravar_leitura(r, [pag()])                                          # 1ª leitura: ponto de partida, sem alerta
    x = precos.lista(r)[0]
    assert x["posicao_mv"] == 2 and precos.alertas(r) == [] and "1ª leitura" in x["eventos"][0]["texto"]
    precos.gravar_leitura(r, [pag(mais_vendido="MAIS VENDIDO · 1º em Perfumes Jacques Bogart")])
    precos.gravar_leitura(r, [pag(mais_vendido="", full=False)])
    precos.gravar_leitura(r, [pag(mais_vendido="", full=False, estoque=0, status="esgotado")])
    precos.gravar_leitura(r, [pag(mais_vendido="MAIS VENDIDO · 3º em Perfumes Jacques Bogart", full=True, estoque=12)])
    tipos = [e["tipo"] for e in precos.lista(r)[0]["eventos"]]
    assert tipos == ["mais_vendido_on", "posicao", "mais_vendido_off", "full_off", "estoque_zerou",
                     "mais_vendido_on", "full_on", "estoque_voltou"], tipos
    a = precos.alertas(r)
    assert len(a) == 1 and len(a[0]["eventos"]) == 7 and "2º → 1º" in a[0]["eventos"][0]["texto"]
    # a API (só preço) não mexe nas tags
    precos.gravar_leitura(r, [{"mlb": "MLB5141216661", "preco": 309.99, "status": "ativo", "estoque": 12, "fonte": "api"}])
    assert len(precos.lista(r)[0]["eventos"]) == 9 - 1
    # histórico de mudanças (tela de detalhes) também mostra tag, posição e FULL
    campos = {m["campo"] for m in precos.mudancas(precos.historico(r, "MLB5141216661"))}
    assert {"mais_vendido", "posicao_mv", "full", "estoque"} <= campos, campos
    precos.marcar_visto(r, "MLB5141216661")
    assert precos.alertas(r) == []


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
