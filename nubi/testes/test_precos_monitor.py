"""30/09 (Bruno, VANVIC): foto do Nubimetrics vira link do anúncio no ML (pela foto da vitrine), "Monitorar preço" põe o
anúncio no monitor, o coletor lê a página de madrugada e a tela mostra o histórico."""
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import precos  # noqa: E402
import nubi_web as w  # noqa: E402


class Repo:
    def __init__(self):
        self.res = {}
        self.vitrine = [{"mlb": "MLB4350649763", "link": "https://produto.mercadolivre.com.br/MLB-4350649763", "titulo": "Perfume Hugo Boss Bottled Night",
                         "foto": "https://http2.mlstatic.com/D_836103-MLA84833570173_052025-O.jpg", "preco": 329.9, "seller_id": "123"}]

    def _eq(self, v):
        return f"eq.{v}"

    def _req(self, metodo, tabela, params=None, corpo=None, prefer=None):
        if tabela == "ia_resumos":
            if metodo == "GET":
                ch = (params or {}).get("chave", "").replace("eq.", "")
                return [{"texto": self.res[ch]}] if ch in self.res else []
            for r in corpo:
                self.res[r["chave"]] = r["texto"]
            return []
        if tabela == "rotinas":
            return [{"id": "precos", "ativo": True, "horario": "04:10", "dias_semana": ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]}]
        return []

    def _todos(self, tabela, params=None):
        return self.vitrine if tabela == "vend_anuncios_ml" else []


def test_seguir_gravar_e_painel():
    r = Repo()
    it = precos.seguir(r, {"mlb": "MLB-4350649763", "titulo": "Hugo Boss", "loja": "VANVICWEB", "seller_id": "123", "preco": "329.9"})
    assert it["mlb"] == "MLB4350649763" and it["link"].endswith("/MLB-4350649763") and it["preco_inicial"] == 329.9
    precos.seguir(r, {"mlb": "MLB4350649763", "foto": "x.jpg"})               # de novo = atualiza, não duplica
    assert len(precos.lista(r)) == 1 and precos.lista(r)[0]["foto"] == "x.jpg"
    try:
        precos.seguir(r, {"mlb": "abc"})
        assert False
    except precos.ErroPrecos:
        pass
    n = precos.gravar_leitura(r, [{"mlb": "MLB4350649763", "preco": 329.9, "status": "ativo", "estoque": 96}], dia="2026-09-29")
    n += precos.gravar_leitura(r, [{"mlb": "MLB4350649763", "preco": 299.9, "preco_original": 599.9, "status": "ativo", "estoque": 90}], dia="2026-09-30")
    # 01/10: mudou no mesmo dia = ponto novo com a hora (antes substituía e a mudança se perdia)
    precos.gravar_leitura(r, [{"mlb": "MLB4350649763", "preco": 309.9, "status": "ativo"}], dia="2026-09-30")
    assert n == 2 and [p["preco"] for p in precos.historico(r, "MLB4350649763")] == [329.9, 299.9, 309.9]
    p = precos.painel(r)[0]
    assert p["atual"] == 309.9 and p["anterior"] == 299.9 and round(p["var"], 4) == round(309.9 / 299.9 - 1, 4)
    assert p["minimo"] == 299.9 and p["maximo"] == 329.9 and p["ultimo_dia"] == "2026-09-30" and p["estoque"] is None
    # 01/10: rodadas ao meio-dia e às 19 h; lido nesta rodada (e com título bom) não roda; na próxima rodada roda (20 min depois)
    precos.seguir(r, {"mlb": "MLB4350649763", "titulo": "Perfume Hugo Boss Bottled Night 100ml"})
    precos.gravar_leitura(r, [{"mlb": "MLB4350649763", "preco": 309.9, "status": "ativo"}])
    from datetime import timedelta as _td
    ini = precos.rodada_atual()
    assert precos.pendente(r, {"ativo": True}, ini + _td(minutes=25))["rodar"] is False
    prox = precos.rodada_atual(ini + _td(hours=12))
    pd_ = precos.pendente(r, {"ativo": True}, prox + _td(minutes=25))
    assert pd_["rodar"] is True and pd_["itens"][0]["mlb"] == "MLB4350649763"
    assert precos.pendente(r, {"ativo": True}, prox + _td(minutes=5))["rodar"] is False      # a API lê primeiro
    assert precos.parar(r, "MLB4350649763") and precos.lista(r) == [] and precos.historico(r, "MLB4350649763")   # histórico fica
    print("ok test_seguir_gravar_e_painel")


def test_ler_pagina_do_anuncio():
    x = precos.ler_pagina({"fracao": "1.299", "centavos": "90", "original": "R$ 1.599,90", "titulo": "T", "vendedor": "LOJA",
                           "texto": "Comprar agora\n(96 disponíveis)\nVendido por LOJA"})
    assert x["preco"] == 1299.9 and x["preco_original"] == 1599.9 and x["status"] == "ativo" and x["estoque"] == 96
    y = precos.ler_pagina({"fracao": None, "texto": "Publicação pausada"})
    assert y["status"] == "pausado" and y["preco"] is None
    z = precos.ler_pagina({"fracao": "72", "centavos": None, "texto": "Último disponível!"})
    assert z["preco"] == 72.0 and z["estoque"] == 1 and z["preco_original"] is None
    print("ok test_ler_pagina_do_anuncio")


def test_rotas_e_foto_com_link():
    r = Repo()
    r.res["vend_fotos|VANVIC P4"] = json.dumps({"vendedor": "VANVIC P4", "itens": [
        {"foto": "http://http2.mlstatic.com/D_836103-MLA84833570173_052025-I.jpg", "Title": "Hugo Boss", "Price": 329.9},
        {"foto": "http://http2.mlstatic.com/D_999999-MLA1_052025-I.jpg", "Title": "Outro"}]})
    r.res["meli|seguidos"] = json.dumps({"VANVIC P4": {"id": "123", "nome": "VANVICWEB", "link": "https://x", "confianca": "provável", "prova": ["a"]}})
    out = w.rota_meli(r, "GET", "meli_fotos_seguido", {"vendedor": "VANVIC P4"}, b"")
    assert out["com_link"] == 1 and out["itens"][0]["mlb"] == "MLB4350649763" and out["itens"][0]["monitorando"] is False
    assert "mlb" not in out["itens"][1] and out["loja"]["nome"] == "VANVICWEB"
    corpo = json.dumps({"mlb": "MLB4350649763", "titulo": "Hugo Boss", "loja": "VANVICWEB", "seller_id": "123", "vendedor": "VANVIC P4", "preco": 329.9}).encode()
    s = w.rota_posicoes(r, "POST", "ml_precos_seguir", {}, corpo)
    assert s["ok"] and s["total"] == 1
    out = w.rota_meli(r, "GET", "meli_fotos_seguido", {"vendedor": "VANVIC P4"}, b"")
    assert out["itens"][0]["monitorando"] is True
    g = w.rota_posicoes(r, "POST", "ml_precos_gravar", {}, json.dumps({"itens": [
        {"mlb": "MLB4350649763", "fracao": "329", "centavos": "90", "texto": "(12 disponíveis)", "titulo": "Hugo Boss", "vendedor": "VANVICWEB"}]}).encode())
    assert g["gravados"] == 1
    lst = w.rota_posicoes(r, "GET", "ml_precos_lista", {}, b"")
    assert lst["itens"][0]["atual"] == 329.9 and lst["itens"][0]["estoque"] == 12 and lst["itens"][0]["loja"] == "VANVICWEB"
    h = w.rota_posicoes(r, "GET", "ml_precos_hist", {"mlb": "MLB-4350649763"}, b"")
    assert len(h["historico"]) == 1
    p = w.rota_posicoes(r, "GET", "ml_precos_pendente", {}, b"")
    assert p["total"] == 1 and "rodar" in p
    assert w.rota_posicoes(r, "POST", "ml_precos_parar", {}, b'{"mlb":"MLB4350649763"}')["tirou"] is True
    print("ok test_rotas_e_foto_com_link")


if __name__ == "__main__":
    test_seguir_gravar_e_painel()
    test_ler_pagina_do_anuncio()
    test_rotas_e_foto_com_link()
