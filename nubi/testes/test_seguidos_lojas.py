# -*- coding: utf-8 -*-
"""Card #126, etapa 1: cada vendedor seguido ligado (meli|seguidos) ganha a cidade/UF do perfil público da loja
(/users/{id}, dublê da API do ML, sem rede) e vira 1 linha em vend_lojas_ml; o painel #/vendedores-ml mostra a cidade.
Sem resposta do ML a cidade fica None (nunca inventada). Rodar: python3 testes/test_seguidos_lojas.py, na pasta nubi."""
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
from test_meli import Repo, _preparar  # noqa: E402


class R(Repo):
    def __init__(self, sem_tabela=False):
        super().__init__()
        self.lojas_ml, self.sem_tabela, self.anuncios_ml = {}, sem_tabela, {}

    def _todos(self, t, q=None):
        if t == "vend_anuncios_ml":
            v = (q or {}).get("vendedor", "")[3:]
            return [dict(x) for x in self.anuncios_ml.values() if not v or x["vendedor"] == v]
        return []

    def _req(self, metodo, tabela, q=None, corpo=None, **k):
        if tabela == "vend_anuncios_ml" and metodo == "POST":
            assert q == {"on_conflict": "mlb"} and "merge-duplicates" in k.get("prefer", "")
            for x in corpo:
                self.anuncios_ml[x["mlb"]] = {**self.anuncios_ml.get(x["mlb"], {}), **x}
            return []
        if tabela == "vend_lojas_ml" and metodo == "POST":
            if self.sem_tabela:
                raise w.ErroNuvem("relation vend_lojas_ml does not exist", 404)
            assert q == {"on_conflict": "vendedor"} and "merge-duplicates" in k.get("prefer", "")
            for x in corpo:
                self.lojas_ml[x["vendedor"]] = x
            return []
        return super()._req(metodo, tabela, q, corpo, **k)


SEG = {"SIENO P13": {"id": "222222222", "nome": "SIENO.", "link": "https://perfil.mercadolivre.com.br/SIENO.",
                     "confianca": "manual", "prova": "confirmada pelo Bruno", "anuncios": []},
       "ICARBONXX P3": {"id": "2540338692", "nome": "KAIDOXSTOREE", "link": "", "confianca": "provável",
                        "prova": "preço exato em 2 produtos", "anuncios": []},
       "VANVIC P4": {"id": "999", "nome": "VANVICWEB", "link": "https://perfil.mercadolivre.com.br/VANVICWEB",
                     "confianca": "provável", "prova": "x", "anuncios": []},           # o ML não acha: sem cidade
       "PHTEC P7": {"id": "111111111", "nome": "PHTECHSP", "confianca": "dúvida"}}      # dúvida não entra


def test_cidade_e_uf_dos_seguidos_ligados_gravadas():
    d = _preparar()
    r = R()
    meli.gravar_hash_lojas(r, SEG, meli.SEGUIDOS)
    out = w.rota_meli(r, "POST", "meli_seguidos_lojas", {}, b"{}")["lojas"]
    assert {x["vendedor"] for x in out} == {"SIENO P13", "ICARBONXX P3", "VANVIC P4"}
    a, b, c = r.lojas_ml["SIENO P13"], r.lojas_ml["ICARBONXX P3"], r.lojas_ml["VANVIC P4"]
    assert (a["seller_id"], a["cidade"], a["uf"], a["nickname"], a["nome"]) == ("222222222", "Maringá", "PR", "ESSENCEPRIMEBR", "SIENO.")
    assert a["confianca"] == "manual" and a["prova"] == "confirmada pelo Bruno" and a["link"].startswith("https://perfil.")
    assert (b["cidade"], b["uf"], b["link"]) == ("São Paulo", "SP", "https://perfil.mercadolivre.com.br/KAIDOXSTOREE")
    assert (c["cidade"], c["uf"], c["nickname"], c["link"]) == (None, None, "VANVICWEB", "https://perfil.mercadolivre.com.br/VANVICWEB")
    assert "PHTEC P7" not in r.lojas_ml
    assert d.pedidos.count("/users/222222222") == 1
    w.rota_meli(r, "POST", "meli_seguidos_lojas", {}, b"{}")                        # de novo: 1 linha por vendedor (upsert)
    assert len(r.lojas_ml) == 3 and d.pedidos.count("/users/222222222") == 1         # perfil em cache (7 dias)


def test_sem_a_tabela_ou_sem_as_chaves_nao_quebra():
    _preparar()
    r = R(sem_tabela=True)                                     # o Chefe ainda não aplicou o SQL
    meli.gravar_hash_lojas(r, SEG, meli.SEGUIDOS)
    out = {x["vendedor"]: x for x in w.lojas_seguidos(r).values()}
    assert out["SIENO P13"]["cidade"] == "Maringá"
    _preparar(chaves=False)                                    # sem ML_CLIENT_ID/SECRET: loja fica, cidade None
    r = R()
    meli.gravar_hash_lojas(r, SEG, meli.SEGUIDOS)
    out = w.lojas_seguidos(r)
    assert out["SIENO P13"]["cidade"] is None and out["SIENO P13"]["nickname"] == "SIENO."


def test_painel_mostra_a_cidade_e_a_tela_desenha():
    _preparar()

    class P(R):
        def _todos(self, t, q=None):
            if t == "vend_relatorios":
                return [{"id": 9, "vendedor": "SIENO P13", "mes": "2026-09-01", "ate": None, "arquivo": "a", "importado_em": "x",
                         "seller_hash": "A" * 128, "nome_exibido": "SIENO P13"}]
            return super()._todos(t, q)
    r = P()
    meli.gravar_hash_lojas(r, SEG, meli.SEGUIDOS)
    xs = w.rota_meli(r, "GET", "meli_seguidos_lista", {}, b"")["vendedores"]
    assert (xs[0]["ml"]["cidade"], xs[0]["ml"]["uf"]) == ("Maringá", "PR")
    assert "SIENO P13" in r.lojas_ml                         # abrir o painel já grava vend_lojas_ml
    html = (Path(__file__).resolve().parents[1] / "public" / "index.html").read_text(encoding="utf-8")
    assert "📍 ${esc(v.ml.cidade)}" in html and "cidade: l.cidade, uf: l.uf" in html and "na vitrine" in html
    assert xs[0]["ml"]["vitrine"] == 0
    sql = (Path(__file__).resolve().parents[1] / "supabase" / "vend_lojas_ml.sql").read_text(encoding="utf-8")
    for col in ("vendedor text primary key", "seller_id", "nickname", "nome", "cidade", "uf", "link", "confianca", "prova", "atualizado_em"):
        assert col in sql, col


# Etapa 2: página falsa da vitrine _CustId_ no formato polycard (como a busca real), com um card de catálogo Full, um
# normal cujo vendido só vem na lista "printed_result" do script, um patrocinado (link de clique) e um repetido.
CARD_CAT = """<li class="ui-search-layout__item" style="height: 443px"><div class="andes-card poly-card poly-card--grid-card">
  <div class="poly-card__portada"><img class="poly-component__picture" data-src="https://http2.mlstatic.com/D_Q_NP_951134-MLB91143087125_082025-I.webp" src="data:image/gif;base64,R0l" alt="Perfume Asad Elixir Lattafa 100ml"></div>
  <div class="poly-card__content"><span class="poly-component__brand">LATTAFA</span>
  <h3 class="poly-component__title-wrapper"><a class="poly-component__title" href="https://www.mercadolivre.com.br/asad-elixir/p/MLB19876543?pdp_filters=item_id%3AMLB4440002222#polycard_client=search-nordic">Perfume Asad Elixir Lattafa Eau De Parfum 100ml</a></h3>
  <span class="poly-component__seller">Por SIENO. </span><span class="poly-reviews__total">| +5mil vendidos</span>
  <div class="poly-component__price"><div class="poly-price__current"><span class="andes-money-amount"><span class="andes-money-amount__currency-symbol">R$</span><span class="andes-money-amount__fraction">1.249</span><span class="andes-money-amount__cents">90</span></span></div></div>
  <div class="poly-component__shipping"><span>Enviado pelo</span><svg aria-label="FULL" class="poly-shipping__full"></svg></div></div></div></li>"""
CARD_NORMAL = """<li class="ui-search-layout__item"><div class="poly-card"><img src="https://http2.mlstatic.com/D_Q_NP_222-MLB333_092025-I.webp">
  <a class="poly-component__title" href="https://produto.mercadolivre.com.br/MLB-3330003333-club-de-nuit-intense-_JM">Club De Nuit Intense Armaf 105ml</a>
  <div class="poly-price__current"><span class="andes-money-amount"><span class="andes-money-amount__fraction">199</span></span></div></div></li>"""
CARD_PAD = """<li class="ui-search-layout__item"><div class="poly-card"><span>Patrocinado</span>
  <a class="poly-component__title" href="https://click1.mercadolivre.com.br/mclics/clicks/external/MLB/count?a=x&amp;url=https%3A%2F%2Fproduto.mercadolivre.com.br%2FMLB-7770007777-yara-_JM">Yara Lattafa 100ml</a>
  <div class="poly-price__current"><span class="andes-money-amount"><span class="andes-money-amount__fraction">159</span><span class="andes-money-amount__cents">9</span></span></div><span>+500 vendidos</span></div></li>"""
SCRIPT = ('{\\"printed_result\\":[{\\"item_id\\":\\"MLB3330003333\\",\\"type\\":\\"ORGANIC\\",\\"sold_quantity\\":25,'
          '\\"first_shipping_logistic_type\\":\\"xd_drop_off\\",\\"price\\":199,\\"pid\\":\\"MLBP44455566\\"},'
          '{\\"item_id\\":\\"MLB5550005555\\",\\"type\\":\\"ORGANIC\\",\\"sold_quantity\\":3,\\"first_shipping_logistic_type\\":\\"fulfillment\\",\\"price\\":89.9}]}') * 2


def test_vitrine_lida_com_as_regras_do_docartao():
    xs = meli.vitrine_cartoes([CARD_CAT, CARD_NORMAL, CARD_PAD, CARD_CAT], [SCRIPT])
    por = {x["mlb"]: x for x in xs}
    assert [x["mlb"] for x in xs] == ["MLB4440002222", "MLB3330003333", "MLB7770007777", "MLB5550005555"]
    a = por["MLB4440002222"]                          # catálogo: MLB do item_id do link, produto pai do /p/
    assert (a["catalogo"], a["preco"], a["full"], a["vendidos"], a["vendidos_mais"]) == ("MLB19876543", 1249.9, True, 5000, True)
    assert a["foto"] == "https://http2.mlstatic.com/D_Q_NP_951134-MLB91143087125_082025-O.webp"   # foto grande (-O.)
    assert (a["apelido"], a["marca"], a["titulo"]) == ("SIENO.", "LATTAFA", "Perfume Asad Elixir Lattafa Eau De Parfum 100ml")
    assert a["link"].startswith("https://www.mercadolivre.com.br/asad-elixir/p/MLB19876543")
    b = por["MLB3330003333"]                          # vendido e envio só na lista do script; catálogo pelo pid MLBP
    assert (b["preco"], b["vendidos"], b["full"], b["catalogo"]) == (199.0, 25, False, "MLB44455566")
    c = por["MLB7770007777"]                          # patrocinado: MLB do destino do clique, link de produto montado
    assert (c["preco"], c["vendidos"], c["vendidos_mais"]) == (159.9, 500, True)
    assert c["link"] == "https://produto.mercadolivre.com.br/MLB-7770007777"
    d = por["MLB5550005555"]                          # só na lista: entra com o link, Full e preço de lá
    assert (d["full"], d["preco"], d["vendidos"], d["foto"]) == (True, 89.9, 3, "")
    assert meli.vitrine_url("222222222") == "https://lista.mercadolivre.com.br/_CustId_222222222"
    assert meli.vitrine_url("222222222", 1) == "https://lista.mercadolivre.com.br/_Desde_49_CustId_222222222_NoIndex_True"


def test_vitrine_gravada_ligada_ao_seguido_e_rota_dos_anuncios():
    _preparar()
    r = R()
    seg = dict(SEG)
    seg["SIENO P13"] = dict(SEG["SIENO P13"], anuncios=[{"anuncio": "MLB4440002222", "produto": "MLB19876543",
                                                        "titulo": "Asad Elixir", "preco": 1249.9, "full": True},
                                                       {"anuncio": "MLB9990009999", "titulo": "Prova antiga", "preco": 99}])
    meli.gravar_hash_lojas(r, seg, meli.SEGUIDOS)
    pend = w.rota_posicoes(r, "GET", "ml_vitrine_pendente", {}, b"")["lojas"]
    assert {x["vendedor"]: x["seller_id"] for x in pend} == {"SIENO P13": "222222222", "ICARBONXX P3": "2540338692", "VANVIC P4": "999"}
    corpo = {"vendedor": "SIENO P13", "seller_id": "222222222", "pagina": 0, "cards": [CARD_CAT, CARD_NORMAL, CARD_PAD], "scripts": [SCRIPT]}
    out = w.rota_posicoes(r, "POST", "ml_vitrine_salvar", {}, json.dumps(corpo).encode())
    assert out["anuncios"] == 4 and "MLB9990009999" not in out["mlbs"]
    assert set(r.anuncios_ml) == {"MLB4440002222", "MLB3330003333", "MLB7770007777", "MLB5550005555", "MLB9990009999"}
    a = r.anuncios_ml["MLB4440002222"]
    assert (a["vendedor"], a["seller_id"], a["fonte"], a["produto_catalogo"], a["preco"], a["full"]) == \
        ("SIENO P13", "222222222", "vitrine", "MLB19876543", 1249.9, True)
    assert a["foto"].endswith("-O.webp") and a["visto_em"]
    assert r.anuncios_ml["MLB9990009999"]["fonte"] == "prova"          # anúncio de prova de meli|seguidos entra primeiro
    w.rota_posicoes(r, "POST", "ml_vitrine_salvar", {}, json.dumps(corpo).encode())   # de novo: 1 linha por MLB (upsert)
    assert len(r.anuncios_ml) == 5
    try:                                                                # seller_id de outra loja: recusa
        w.rota_posicoes(r, "POST", "ml_vitrine_salvar", {}, json.dumps(dict(corpo, seller_id="123")).encode())
        raise AssertionError("devia recusar")
    except w.ErroNuvem:
        pass
    lido = w.rota_meli(r, "GET", "meli_seguido_anuncios", {"vendedor": "SIENO P13"}, b"")
    assert lido["loja"]["id"] == "222222222" and lido["anuncios"][0]["mlb"] == "MLB4440002222"   # mais vendido primeiro
    assert len(lido["anuncios"]) == 5
    assert w.rota_meli(r, "GET", "meli_seguido_anuncios", {"vendedor": "OUTRO"}, b"")["anuncios"] == []
    sql = (Path(__file__).resolve().parents[1] / "supabase" / "vend_anuncios_ml.sql").read_text(encoding="utf-8")
    for col in ("mlb text not null unique", "vendedor", "seller_id", "link", "titulo", "foto", "preco", "vendidos", "full",
                "produto_catalogo", "vend_anuncio_id", "visto_em"):
        assert col in sql, col


def test_coletor_passa_as_paginas_da_vitrine_ate_acabar():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
    import coletor
    assert "vitrine_seguidos" in w.COMANDOS_MAC and coletor.comando_mac("vitrine_seguidos")[-1] == "vitrine-seguidos"
    assert "vitrine_seguidos" in coletor.SERVIDOR_PODE
    assert coletor.vitrine_url("222222222", 2) == meli.vitrine_url("222222222", 2)
    paginas = {coletor.vitrine_url("222222222", 0): [CARD_CAT] * 48, coletor.vitrine_url("222222222", 1): [CARD_NORMAL, CARD_PAD]}
    pedidos = []

    class Pg:
        url, mouse = "", type("M", (), {"wheel": lambda *a: None})()

        def add_init_script(self, s):
            assert "printed_result" in s

        def goto(self, u, **k):
            self.url = u
            pedidos.append(u)

        def evaluate(self, js):
            return {"cards": paginas.get(self.url, []), "scripts": [SCRIPT]}

    class Ctx:
        pages = [Pg()]

        def close(self):
            pass
    enviados = []

    def api(token, rota, params=None, corpo=None, **k):
        if rota == "ml_vitrine_pendente":
            return {"lojas": [{"vendedor": "SIENO P13", "seller_id": "222222222", "nome": "SIENO."},
                              {"vendedor": "X", "seller_id": "abc"}]}          # seller_id estranho: pula
        enviados.append(corpo)
        return {"mlbs": [a["mlb"] for a in meli.vitrine_cartoes(corpo["cards"], corpo["scripts"])]}
    velhos = coletor.api, coletor._ml_navegador, coletor._ml_bloqueado, coletor.devagar
    coletor.api, coletor._ml_navegador, coletor._ml_bloqueado, coletor.devagar = api, lambda p, c: Ctx(), lambda pg: False, lambda s=0: None
    try:
        feitos, total, erros, msg = coletor.coletar_vitrine_seguidos(None, {}, "t")
    finally:
        coletor.api, coletor._ml_navegador, coletor._ml_bloqueado, coletor.devagar = velhos
    assert pedidos == [coletor.vitrine_url("222222222", 0), coletor.vitrine_url("222222222", 1)]   # 2ª página curta: para
    assert (feitos, total, erros) == (1, 4, 0), msg                     # 3 da 1ª (1 card + 2 da lista) + 1 novo (patrocinado)
    assert [e["pagina"] for e in enviados] == [0, 1] and enviados[0]["seller_id"] == "222222222"


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
