"""Avisos no WhatsApp do Bruno pelo CallMeBot (03/10): só com as chaves da Vercel; a chave nunca aparece no texto."""
import os
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SUPABASE_URL", "http://x")
os.environ.setdefault("SUPABASE_KEY", "x")
import nubi_web as w  # noqa: E402

pedidos = []


class Resp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def abrir(req, timeout=20):
    pedidos.append(req.full_url)
    return Resp()


class Repo:
    def __init__(self, texto):
        self.d = {w.WHATSAPP_PEDIDO: texto}

    def _eq(self, v):
        return v

    def _req(self, metodo, tabela, params=None, corpo=None, prefer=None):
        if metodo == "GET":
            t = self.d.get(params["chave"])
            return [{"texto": t}] if t else []
        if metodo == "DELETE":
            self.d.pop(params["chave"], None)


def test_aviso():
    w.urllib.request.urlopen = abrir
    os.environ.pop("NUBI_WHATSAPP_FONE", None)
    assert w.whatsapp_aviso("oi") is False and not pedidos          # sem as chaves: não manda
    os.environ["NUBI_WHATSAPP_FONE"] = "+55 (11) 99999-0000"
    os.environ["NUBI_WHATSAPP_CHAVE"] = "123456"
    assert w.whatsapp_aviso("Histórico terminou") is True
    q = urllib.parse.parse_qs(urllib.parse.urlparse(pedidos[-1]).query)
    assert q["phone"] == ["+5511999990000"] and q["apikey"] == ["123456"] and q["text"][0].startswith("🤖 nubi: Histórico")
    t = w._aviso_fim_comando("historico_vendas", "ok", "a\nb\nOK: 290 dias\n")
    assert t.startswith("✅ terminou: Mac: vendas por dia") and "OK: 290 dias" in t and "123456" not in t
    r = Repo("teste do nubi")
    assert w.whatsapp_pedidos(r) is True and not r.d and pedidos[-1].count("teste") == 1
    assert w.whatsapp_pedidos(r) is None                             # já apagado: não repete


if __name__ == "__main__":
    test_aviso()
    print("ok whatsapp")
