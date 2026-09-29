# -*- coding: utf-8 -*-
"""Card #121 (fase 1): a extensão manda ao nubi o que leu da página do anúncio que o Bruno abriu (rota pública ext_coleta,
com limite): 1 registro por anúncio com a data, nada inventado (o que falta fica None = "sem dados"). E o preço de agora
dos GTINs das marcas pelo catálogo (/products/{id}/items, todas as páginas), 1 vez por dia e sob demanda, sem /items nem
/sites/MLB/search de outras lojas. Página falsa + dublê da API do ML (test_meli). Rodar: python3 testes/test_ext_coleta.py"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import meli  # noqa: E402
import nubi_web as w  # noqa: E402
from test_meli import Repo, _preparar  # noqa: E402

EXT = Path(__file__).resolve().parents[1] / "public" / "extensao" / "nubi-ml"

# trecho da página /up/ salva na inspeção de 29/09 (Claude no Chrome) + a foto do anúncio do caso Cowork
PAGINA = ('<script id="__NORDIC_RENDERING_CTX__">_n.ctx.r={"components":{"header":{"reviews":{"rating":4.7,"amount":124}}},'
          '"melidata_event":{"event_data":{"item_id":"MLB4430562169","seller_id":2162683356,"seller_name":"Essence Prime",'
          '"listing_type_id":"gold_special","category_id":"MLB6284","logistic_type":"fulfillment","quantity":98,"sold_quantity":500}}}</script>'
          '<img src="https://http2.mlstatic.com/D_NQ_NP_951134-MLB91143087125_082025-O.webp">')


class RepoMarcas(Repo):
    def __init__(self, gtins=()):
        super().__init__()
        self.gtins = list(gtins)

    def carregar_config(self):
        return {"LATTAFA": {"linhas": []}, "AL WATANIAH": {"linhas": []}}

    def _todos(self, tabela, q=None):
        assert tabela == "gtin_info", tabela
        return self.gtins


def _coleta_da_pagina(html, url):
    """O que o conteudo.js manda ao nubi: lerAnuncio (fundo.js) + os mesmos campos."""
    js = """global.chrome={runtime:{onMessage:{addListener(){}}}};const {lerAnuncio}=require(process.argv[1]);
const A=lerAnuncio(process.argv[2],process.argv[3]);
const c={mlb:A.item,vendedor:A.vendedor,loja:A.nome_loja||A.apelido,preco:A.preco,vendidos:A.vendidos,
 full:A.full==null?null:A.full?1:0,fotos:(A.fotos||[]).slice(0,12).join(",")};
console.log(JSON.stringify(Object.fromEntries(Object.entries(c).filter(([,v])=>v!=null&&v!==""))));"""
    return json.loads(subprocess.run(["node", "-e", js, str(EXT / "fundo.js"), html, url], capture_output=True, text=True,
                                     check=True).stdout)


def test_ext_coleta_grava_um_registro_por_anuncio_sem_inventar():
    r = Repo()
    w.RepoSupabase, w.login_agente = (lambda token: r), (lambda: "agente")
    meli._EXT_COLETA.update(min=0, n=0)
    q = {k: str(v) for k, v in _coleta_da_pagina(PAGINA, "https://www.mercadolivre.com.br/x/up/MLBU3736729421").items()}
    assert "preco" not in q                                   # o trecho não traz o preço: não vai nada (nem zero)
    st, _, corpo, cab = w.atender("GET", "ext_coleta", q, b"", "")
    assert st == 200 and cab.get("Access-Control-Allow-Origin") == "*", corpo
    assert json.loads(corpo) == {"ok": True, "mlb": "MLB4430562169", "sem_dados": ["preco"]}, corpo
    assert list(r.resumos) == ["ext_coleta|MLB4430562169"]
    reg = json.loads(r.resumos["ext_coleta|MLB4430562169"])
    assert {k: reg[k] for k in ("mlb", "vendedor", "loja", "preco", "vendidos", "vendidos_faixa", "full", "fotos")} == {
        "mlb": "MLB4430562169", "vendedor": "2162683356", "loja": "Essence Prime", "preco": None, "vendidos": 500,
        "vendidos_faixa": True, "full": True, "fotos": ["https://http2.mlstatic.com/D_NQ_NP_2X_951134-MLB91143087125_082025-O.webp"]}, reg
    assert reg["em"].endswith("+00:00") and reg["dia"] == w._hoje_br().isoformat()
    # a mesma página de novo (agora com o preço): continua 1 registro do anúncio, atualizado
    st, _, corpo, _ = w.atender("GET", "ext_coleta", dict(q, preco="167.90", fotos=q["fotos"] + ",https://outro.site/x.jpg"), b"", "")
    assert st == 200 and list(r.resumos) == ["ext_coleta|MLB4430562169"]
    reg = json.loads(r.resumos["ext_coleta|MLB4430562169"])
    assert reg["preco"] == 167.9 and reg["sem_dados"] == [] and len(reg["fotos"]) == 1       # foto fora do mlstatic não entra
    # sem anúncio ou vendedor válido: recusa e não grava
    st, _, corpo, _ = w.atender("GET", "ext_coleta", {"mlb": "MLB1&x=1", "vendedor": "abc"}, b"", "")
    assert st == 400 and len(r.resumos) == 1
    # campos que não vieram ficam None ("sem dados"), nunca zero
    st, _, corpo, _ = w.atender("GET", "ext_coleta", {"mlb": "MLB5000000001", "vendedor": "123456"}, b"", "")
    assert json.loads(corpo)["sem_dados"] == ["loja", "preco", "fotos", "vendidos", "vendidos_faixa", "full"], corpo
    # passou do limite por minuto: recusado e nada gravado
    meli._EXT_COLETA.update(min=int(__import__("time").time() // 60), n=meli.EXT_COLETA_POR_MINUTO)
    st, _, corpo, _ = w.atender("GET", "ext_coleta", dict(q, mlb="MLB4430562170"), b"", "")
    assert st == 400 and "muitos pedidos" in json.loads(corpo)["erro"].lower() and "ext_coleta|MLB4430562170" not in r.resumos
    meli._EXT_COLETA.update(n=0)
    texto = json.dumps(r.resumos).lower()
    assert "token" not in texto and "cookie" not in texto and "senha" not in texto


def test_preco_de_agora_pelo_catalogo_todas_as_paginas_1_vez_por_dia():
    d = _preparar()
    r = RepoMarcas([{"gtin": "7899463112978", "marca": "Al Wataniah"}, {"gtin": "6290362346548", "marca": "Lattafa"},
                    {"gtin": "1234567890123", "marca": "Outra"}, {"gtin": "abc", "marca": "Lattafa"}])
    assert w._gtins_das_marcas(r) == ["6290362346548", "7899463112978"]
    out = w.precos_catalogo(r)
    assert out["lidos"] == 2 and out["faltam"] == 0 and out["erros"] == 0, out
    f = json.loads(r.resumos["meli|preco|7899463112978"])
    assert f["total"] == 122 and f["menor"] == 120.0 and f["dia"] == w._hoje_br().isoformat(), (f["total"], f["menor"])   # 3 páginas
    kaidox = [o for o in f["ofertas"] if o["vendedor_id"] == 2540338692]
    assert kaidox == [{"anuncio": "MLB5000002", "vendedor_id": 2540338692, "preco": 142.9, "preco_cheio": None, "full": True,
                       "tipo_id": "gold_special", "produto_catalogo": "MLB8880888"}], kaidox       # a loja certa, depois das 50 primeiras
    # nenhuma chamada a /items nem à busca de outras lojas (dão 403)
    assert d.pedidos and all(p in ("/products/search",) or (p.startswith("/products/") and p.endswith("/items")) for p in d.pedidos), d.pedidos
    # 1 vez por dia: a 2ª rodada do cron não pede nada
    n = len(d.pedidos)
    assert w.precos_catalogo(r)["lidos"] == 2 and len(d.pedidos) == n
    # sob demanda: POST {gtin} lê agora (sem o cache de 20 min) e GET devolve o gravado
    meli._CACHE.clear()
    x = w.rota_meli(r, "POST", "meli_preco_catalogo", {}, json.dumps({"gtin": "6290362346548"}).encode())
    assert x["menor"] == 265.28 and x["total"] == 2 and len(d.pedidos) > n
    assert w.rota_meli(r, "GET", "meli_preco_catalogo", {"gtin": "6290362346548"}, b"")["menor"] == 265.28
    assert w.rota_meli(r, "GET", "meli_preco_catalogo", {"gtin": "0000000000000"}, b"") == {"gtin": "0000000000000", "ofertas": []}
    try:
        w.rota_meli(r, "GET", "meli_preco_catalogo", {"gtin": "12"}, b"")
        assert False, "devia recusar"
    except w.ErroNuvem:
        pass
    # botão "ler todos agora" (forçar): lê de novo mesmo já feito hoje
    meli._CACHE.clear()
    n = len(d.pedidos)
    assert w.rota_meli(r, "POST", "meli_preco_catalogo", {}, json.dumps({"todos": True}).encode())["lidos"] == 2 and len(d.pedidos) > n


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
