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


def test_mesmo_fone_sem_o_9():
    assert c.wa_mesmo_fone("554498812871", "5544998812871") and c.wa_mesmo_fone("+55 44 9881-2871", "44998812871")
    assert not c.wa_mesmo_fone("5547988881111", "5544998812871") and not c.wa_mesmo_fone("", "5544998812871")
    assert "entrar_auto_gestor" not in c.SERVIDOR_PODE                       # a senha do Gestor só está no Mac


def test_le_pelos_baloes_sem_data_id():
    from playwright.sync_api import sync_playwright
    html = """<div id="main"><header><span title="+55 44 9881-2871">+55 44 9881-2871</span></header>
      <div role="row"><div class="message-out"><div data-pre-plain-text="[14:40, 03/10/2026] Loja: "><span class="selectable-text">Oi</span></div></div></div>
      <div role="row"><div class="message-in"><div data-pre-plain-text="[15:04, 03/10/2026] Bruno: "><span class="selectable-text">Ferreiro, oi! Está me ouvindo?</span></div></div></div>
      <footer><div contenteditable="true"></div></footer></div>"""
    with sync_playwright() as p:
        b = p.chromium.launch(**({"executable_path": "/opt/pw-browsers/chromium"} if Path("/opt/pw-browsers/chromium").is_file() else {}))
        pg = b.new_page()
        pg.set_content(html)
        conv = pg.evaluate(c.JS_WA_CONVERSA)
        assert [(m["de"], m["texto"]) for m in conv["msgs"]] == [("loja", "Oi"), ("cliente", "Ferreiro, oi! Está me ouvindo?")]
        assert c._wa_fone(conv) == "554498812871" and c.wa_mesmo_fone(c._wa_fone(conv), "5544998812871")
        assert [m["texto"] for m in c.wa_novas(conv, set())] == ["Ferreiro, oi! Está me ouvindo?"]
        assert pg.evaluate(c.JS_WA_DIAG_CONVERSA)["msg_in"] == 1
        b.close()


def test_le_pela_posicao_do_balao():
    # 03/10: formato real (data-id sem true_/false_, sem .message-in): o do chip fica à direita, o do cliente à esquerda
    from playwright.sync_api import sync_playwright
    html = """<div id="main" style="width:800px"><header><span title="+55 44 9881-2871">+55 44 9881-2871</span></header>
      <div role="row"><div data-id="AC72FB4C"><div style="margin-left:600px;width:150px"><span class="selectable-text">Oi</span></div></div></div>
      <div role="row"><div data-id="3EB09110"><div style="margin-left:10px;width:200px"><span class="selectable-text">Ferreiro, teste 2.</span></div></div></div>
      <footer><div contenteditable="true"></div></footer></div>"""
    with sync_playwright() as p:
        b = p.chromium.launch(**({"executable_path": "/opt/pw-browsers/chromium"} if Path("/opt/pw-browsers/chromium").is_file() else {}))
        pg = b.new_page()
        pg.set_content(html)
        conv = pg.evaluate(c.JS_WA_CONVERSA)
        assert [(m["de"], m["texto"]) for m in conv["msgs"]] == [("loja", "Oi"), ("cliente", "Ferreiro, teste 2.")], conv
        assert [m["texto"] for m in c.wa_novas(conv, set())] == ["Ferreiro, teste 2."] and c._wa_fone(conv) == "554498812871"
        b.close()


def test_le_pelo_remetente():
    # 03/10 (estrutura real): sem classes de direção; o data-pre-plain-text diz quem mandou
    from playwright.sync_api import sync_playwright
    html = """<div id="main"><header><span title="+55 44 9881-2871">+55 44 9881-2871</span></header>
      <div role="row"><div data-id="AC019F5E"><div data-pre-plain-text="[14:40, 03/10/2026] Pure Perfumaria: "><span class="selectable-text">Oi</span></div></div></div>
      <div role="row"><div data-id="3B93E144"><div data-pre-plain-text="[15:53, 03/10/2026] +55 44 9881-2871: "><span class="selectable-text">Ferreiro, teste 2.</span></div></div></div>
      <footer><div contenteditable="true"></div></footer></div>"""
    with sync_playwright() as p:
        b = p.chromium.launch(**({"executable_path": "/opt/pw-browsers/chromium"} if Path("/opt/pw-browsers/chromium").is_file() else {}))
        pg = b.new_page()
        pg.set_content(html)
        conv = pg.evaluate(c.JS_WA_CONVERSA)
        assert [(m["de"], m["texto"]) for m in conv["msgs"]] == [("loja", "Oi"), ("cliente", "Ferreiro, teste 2.")], conv
        b.close()


def test_comandos():
    assert c.comando_mac("whatsapp_instalar")[-1] == "whatsapp-instalar"
    assert c._wa_fone({"titulo": "Maria Cliente", "msgs": [{"chat": "123@lid"}]}) == ""


if __name__ == "__main__":
    test_comandos()
    test_mesmo_fone_sem_o_9()
    test_le_pelos_baloes_sem_data_id()
    test_le_pela_posicao_do_balao()
    test_le_pelo_remetente()
    test_ler_e_digitar()
    print("ok whatsapp coletor")
