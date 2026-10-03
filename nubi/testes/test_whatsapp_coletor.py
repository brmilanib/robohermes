"""WhatsApp do chip no Mac (03/10): lê a lista e a conversa do WhatsApp Web, acha o número, pega só o que é novo e digita
devagar (página falsa com a mesma estrutura do web.whatsapp.com)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
os.environ["NUBI_TOKEN"] = "t"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402

PAGINA = """<html><body>
<div id="side"><div id="pane-side">
 <div role="listitem"><span title="+55 47 98888-1111">+55 47 98888-1111</span><span>Olá! Gostaria de saber mais</span>
   <span aria-label="2 mensagens não lidas">2</span></div>
 <div role="listitem"><span title="Maria Cliente">Maria Cliente</span><span>obrigada</span></div>
</div></div>
<div id="main"><header><span dir="auto" title="+55 47 98888-1111">+55 47 98888-1111</span></header>
 <div id="msgs">
  <div role="row"><div data-id="true_5547988881111@c.us_A1"><div class="message-out"><span class="selectable-text">Oi, tudo bem?</span></div></div></div>
  <div role="row"><div data-id="false_5547988881111@c.us_A2"><div class="message-in"><span class="selectable-text">Olá! Gostaria de saber mais sobre a Via Brazil Global.</span></div></div></div>
  <div role="row"><div data-id="false_5547988881111@c.us_A3"><div class="message-in"><button aria-label="Reproduzir mensagem de voz"></button><audio></audio></div></div></div>
 </div>
 <footer><div contenteditable="true" id="campo"></div></footer>
</div>
<script>
 let n = 10;
 document.getElementById('campo').addEventListener('keydown', e => {
   if (e.key === 'Enter' && !e.shiftKey) {
     e.preventDefault();
     const t = document.getElementById('campo').innerText;
     const d = document.createElement('div'); d.setAttribute('role', 'row');
     d.innerHTML = '<div data-id="true_5547988881111@c.us_B' + (n++) + '"><div class="message-out"><span class="selectable-text"></span></div></div>';
     d.querySelector('span').innerText = t;
     document.getElementById('msgs').appendChild(d);
     document.getElementById('campo').innerText = '';
   }
 });
</script></body></html>"""


def test_ler_e_digitar():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(**({"executable_path": "/opt/pw-browsers/chromium"} if Path("/opt/pw-browsers/chromium").is_file() else {}))
        pg = b.new_page()
        pg.set_content(PAGINA)
        assert pg.evaluate(c.JS_WA_ESTADO) == {"qr": False, "pronto": True, "aberto": True}
        lista = pg.evaluate(c.JS_WA_LISTA)
        assert [x["titulo"] for x in lista] == ["+55 47 98888-1111", "Maria Cliente"] and lista[0]["nao_lida"] and not lista[1]["nao_lida"]
        previas = {}
        assert c.wa_para_abrir(lista, previas) == ["+55 47 98888-1111"]
        lista[1]["previa"] = "Maria Cliente vocês têm o Asad?"            # leram pelo celular: sem bolinha, mas a prévia mudou
        lista[0]["nao_lida"] = False
        assert c.wa_para_abrir(lista, previas) == ["Maria Cliente"]
        conv = pg.evaluate(c.JS_WA_CONVERSA)
        assert c._wa_fone(conv) == "5547988881111"
        novas = c.wa_novas(conv, set())
        assert [m["texto"] for m in novas] == ["Olá! Gostaria de saber mais sobre a Via Brazil Global.", "[áudio]"]
        assert c.wa_novas(conv, {m["id"] for m in novas}) == []           # já tratadas: não manda de novo
        c._wa_digitar(pg, "Oi! Aqui é da Via Brazil 😊\nMe conta o volume?")
        conv = pg.evaluate(c.JS_WA_CONVERSA)
        assert conv["msgs"][-1]["de"] == "loja" and conv["msgs"][-1]["texto"].startswith("Oi! Aqui é da Via Brazil")
        assert "volume" in conv["msgs"][-1]["texto"] and c.wa_novas(conv, set()) == []
        b.close()


def test_comandos():
    assert c.comando_mac("whatsapp_instalar")[-1] == "whatsapp-instalar"
    assert c._wa_fone({"titulo": "Maria Cliente", "msgs": [{"chat": "123@lid"}]}) == ""


if __name__ == "__main__":
    test_comandos()
    test_ler_e_digitar()
    print("ok whatsapp coletor")
