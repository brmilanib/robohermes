"""01/10 (Bruno): legenda e arte davam erro (Gemini 404/429) -> troca de modelo; link do site encurtado na legenda;
"Monitorar" de anúncio de catálogo pelo GTIN (SIENO: Cuba e Silver Scent sem link na vitrine)."""
import io
import json
import os
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ["GEMINI_API_KEY"] = "teste"
import ia  # noqa: E402
import bazar  # noqa: E402
import marketing  # noqa: E402
import meli  # noqa: E402
import precos  # noqa: E402
import nubi_web as w  # noqa: E402
from test_precos_monitor import Repo  # noqa: E402


def _http(code):
    return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(b""))


def test_gemini_troca_de_modelo():
    ia._GEMINI_LISTA.update(t=10 ** 12, nomes=["gemini-2.5-flash-image", "gemini-3-pro-image-preview", "gemini-3-flash-preview",
                                               "gemini-embedding-001", "gemini-3-flash-preview-tts"])
    os.environ.pop("NUBI_IA_MODELO_GEMINI_TEXTO", None)
    os.environ.pop("NUBI_IA_MODELO_GEMINI", None)
    assert ia.gemini_candidatos("texto")[0] == "gemini-3-flash-preview"
    assert "gemini-embedding-001" not in ia.gemini_candidatos("texto")
    assert ia.gemini_candidatos("imagem")[:2] == ["gemini-3-pro-image-preview", "gemini-2.5-flash-image"]
    vistos = []
    antes = ia._post_json

    def falso(url, corpo, cab, timeout=90):
        vistos.append(corpo["model"])
        if corpo["model"] == "gemini-3-pro-image-preview":
            raise _http(429)
        return {"candidates": [{"content": {"parts": [{"inlineData": {"data": "QUJD"}}]}}]}
    ia._post_json = falso
    try:
        img, _, m = ia.gemini_gerar_imagem("faz a arte")
        assert img == "QUJD" and m == "gemini-2.5-flash-image" and vistos == ["gemini-3-pro-image-preview", "gemini-2.5-flash-image"]
        ia._post_json = lambda *a, **k: (_ for _ in ()).throw(_http(404))
        try:
            ia.gemini_texto("oi", web=False)
            assert False
        except ia.SemIA as e:
            assert "HTTP 404" in str(e)
        ia._post_json = lambda *a, **k: (_ for _ in ()).throw(_http(500))   # erro de verdade não é engolido
        try:
            ia.gemini_texto("oi", web=False)
            assert False
        except urllib.error.HTTPError:
            pass
    finally:
        ia._post_json = antes


def test_link_curto_na_legenda():
    assert marketing.encurtar("https://pure.com.br/yara", get=lambda u: "https://is.gd/abc12") == "https://is.gd/abc12"
    assert marketing.encurtar("https://pure.com.br/yara", get=lambda u: "<html>erro</html>") == "https://pure.com.br/yara"
    r = Repo()
    p = bazar.salvar_produto(r, {"produto": "Yara", "preco_original": 230, "desconto": 0.4, "aba": "sem_caixa", "link": "https://pure.com.br/yara"})
    try:
        bazar.salvar_produto(r, {"id": p["id"], "link": "javascript:alert(1)"})
        assert False
    except bazar.ErroBazar:
        pass
    ps = bazar.produtos(r)
    ps[0]["link_curto"] = "https://is.gd/abc12"
    bazar._gravar(r, bazar.PRODUTOS, ps)
    assert bazar.post(bazar.calcular(bazar.produtos(r), []) [0]).endswith("🛒 Compre pelo site: https://is.gd/abc12")
    bazar.salvar_produto(r, {"id": p["id"], "link": "https://pure.com.br/outro"})
    assert "link_curto" not in bazar.produtos(r)[0]                  # link novo: encurta de novo


def test_monitorar_pelo_gtin():
    r = Repo()
    r.vitrine = []
    meli.gravar_hash_lojas(r, {"SIENO P13": {"id": "1142362911", "nome": "SIENO.", "confianca": "manual"}}, meli.SEGUIDOS)
    item = {"Title": "Perfume Cuba Gold Masculino 100ml", "Gtin": "5425017732389", "Price": 59.99, "IsFull": True,
            "ListingTypeId": "gold_special", "foto": "http://http2.mlstatic.com/D_645456-MLU54957895113_042023-I.jpg"}
    out = w.fotos_com_anuncio(r, "SIENO P13", {"itens": [dict(item)]})
    assert out["itens"][0]["gtin_mon"] == "5425017732389" and not out["itens"][0].get("mlb")
    antes = meli.ofertas_por_gtin
    meli.ofertas_por_gtin = lambda gs, **k: [
        {"anuncio": "MLB4000000111", "link": "https://x/MLB-4000000111", "vendedor_id": 999, "preco": 55.0, "tipo_id": "gold_special", "full": True},
        {"anuncio": "MLB4000000222", "link": "https://x/MLB-4000000222", "vendedor_id": 1142362911, "preco": 61.0, "tipo_id": "gold_pro", "full": True},
        {"anuncio": "MLB4000000333", "link": "https://x/MLB-4000000333", "vendedor_id": 1142362911, "preco": 59.99, "tipo_id": "gold_special", "full": True}]
    try:
        x = w._seguir_pelo_gtin(r, {"vendedor": "SIENO P13", "gtin": "5425017732389", "preco": 59.99, "full": True, "tipo_id": "gold_special"})
        assert x["mlb"] == "MLB4000000333" and x["outras"] == 1
        m = precos.lista(r)[0]
        assert m["gtin"] == "5425017732389" and m["seller_id"] == "1142362911" and m["vendedor"] == "SIENO P13"
        out = w.fotos_com_anuncio(r, "SIENO P13", {"itens": [dict(item)]})
        assert out["itens"][0]["monitorando"] and out["itens"][0]["mlb"] == "MLB4000000333" and out["com_link"] == 1
        meli.ofertas_por_gtin = lambda gs, **k: [{"anuncio": "MLB4000000111", "vendedor_id": 999, "preco": 55.0}]
        try:
            w._seguir_pelo_gtin(r, {"vendedor": "SIENO P13", "gtin": "5425017736363"})
            assert False
        except w.ErroNuvem as e:
            assert "não tem oferta ativa" in str(e)
    finally:
        meli.ofertas_por_gtin = antes


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
