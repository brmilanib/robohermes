"""02/10 (Bruno: "ícones das lojas em alta resolução"): coletor icones pega o maior ícone que a página declara
(apple-touch-icon) e manda ao nubi como data:; sem página, o favicon do Google em 256 px."""
import io
import os
import sys
import tempfile
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 5000
pedidos, enviado = [], {}


class Resp(io.BytesIO):
    def __init__(self, dado, tipo):
        super().__init__(dado)
        self.headers = {"content-type": tipo}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def abrir(req, timeout=30):
    url = req.full_url
    pedidos.append(url)
    if url == "https://shopee.com.br":
        raise OSError("bloqueado")
    if "google.com/s2" in url or url.endswith(".png"):
        return Resp(PNG, "image/png")
    return Resp(b'<html><link rel="icon" href="/f.ico" sizes="16x16"><link rel="apple-touch-icon" sizes="180x180" href="/apple.png"></html>', "text/html")


coletor.urllib.request.urlopen = abrir
coletor.token_nubi = lambda cfg: "t"
coletor.api = lambda token, rota, corpo=None, **k: enviado.update(corpo or {}) or {"ok": len((corpo or {}).get("icones") or {})}
coletor.ICONES_SITES = {"Mercado Libre": "https://www.mercadolivre.com.br", "Shopee": "https://shopee.com.br"}
assert coletor.cmd_icones(None, {}) == 0
ic = enviado["icones"]
assert set(ic) == {"Mercado Libre", "Shopee"} and all(v.startswith("data:image/png;base64,") for v in ic.values()), ic.keys()
assert "https://www.mercadolivre.com.br/apple.png" in pedidos                       # o maior que a página declara
assert any("google.com/s2/favicons?domain=shopee.com.br&sz=256" in u for u in pedidos)  # página não abriu: favicon do Google
print("ok icones")
