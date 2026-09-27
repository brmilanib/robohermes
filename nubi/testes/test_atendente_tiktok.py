"""Atendente da TikTok Shop no Mac (26/09): página de chat falsa, Claude falso e nubi falso. Ele traz a mensagem para o
nubi, envia SÓ o texto aprovado (nunca o do modelo), confere o cliente e o botão, e não gasta nada sem mensagem nova."""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
PAGINA = Path(tempfile.mkdtemp()) / "chat.html"
PAGINA.write_text("""<html><head><meta charset="utf-8"><title>Bate-papo da loja</title></head><body>
<div>Não respondidos</div><div class="item" style="cursor:pointer" onclick="document.body.dataset.aberta=1"><b>leidianearaujo182</b> · Vocês vendem perfumes tester?</div>
<textarea placeholder="Insira / para respostas salvas"></textarea>
<button onclick="localStorage.enviado=document.querySelector('textarea').value">Enviar</button>
<button>Reembolsar</button></body></html>""", encoding="utf-8")


def _servidor():
    import functools
    import http.server
    import threading
    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(PAGINA.parent))
    h.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}/chat.html"


URL = _servidor()
ENVIADO = {}


def _abrir(p, cfg, visivel=None):
    extra = {"executable_path": CHROME} if Path(CHROME).exists() else {"channel": "chrome"}
    ctx = p.chromium.launch_persistent_context(str(c.PASTA / "perfil"), headless=True, **extra)
    fechar = ctx.close

    def close():
        try:
            ENVIADO["texto"] = ctx.pages[0].evaluate("localStorage.enviado || ''")
        except Exception:  # noqa: BLE001
            pass
        fechar()
    ctx.close = close
    return ctx


def _preparar(roteiro, aprovadas=(), receber=None, canais=("tiktok_shop",)):
    chamadas = {"api": [], "claude": 0}
    c.abrir_navegador = _abrir
    c.guardar_sessao = lambda ctx: None
    c._credencial = lambda site, cfg=None: ("bruno", "sk-ant-falsa") if site == "anthropic" else ("", "")
    c.token_nubi = lambda cfg: "T"
    c.ATENDENTE_URL = URL
    c.PLATAFORMAS["tiktok_shop"] = ("TikTok Shop", URL, "127.0.0.1", "Atendente TikTok")
    c.PLATAFORMAS["shopee"] = ("Shopee", URL, "127.0.0.1", "Atendente Shopee")
    c.salvar_config({})

    def api(token, rota, params=None, corpo=None, metodo=None, timeout=300):
        chamadas["api"].append((rota, corpo))
        if rota == "atendimento_para_enviar":
            return {"itens": list(aprovadas), "canais": list(canais)}
        if rota == "atendimento_receber":
            return {"rascunho": receber or {"id": 7, "status": "precisa_info"}}
        return {}
    c.api = api
    it = iter(roteiro)

    def claude(chave, mensagens, sistema, ferramentas=None, modelo=None):
        chamadas["claude"] += 1
        chamadas["ultima"] = json.loads(json.dumps(mensagens))
        nome, ent = next(it)
        return {"content": [{"type": "tool_use", "id": f"t{chamadas['claude']}", "name": nome, "input": ent}],
                "usage": {"input_tokens": 3000, "output_tokens": 200}}
    c._claude_ferramentas = claude
    return chamadas


def _ultimo_resultado(ch):
    return ch["ultima"][-1]["content"][0]["content"]


def test_traz_a_mensagem_e_envia_so_o_texto_aprovado():
    ENVIADO.clear()
    aprovado = "Oi! Sim, vendemos tester! Qual perfume você quer? Qualquer coisa, é só chamar!"
    ch = _preparar([("ler", {}),
                    ("registrar", {"cliente": "leidianearaujo182", "historico": [{"de": "cliente", "texto": "Vocês vendem perfumes tester?"}]}),
                    ("registrar", {"cliente": "leidianearaujo182", "historico": [                   # 1ª foi recusada: prévia
                        {"de": "cliente", "texto": "Oi, boa tarde"}, {"de": "cliente", "texto": "Vocês vendem perfumes tester?"}]}),
                    ("enviar_aprovada", {"id": 9, "n_campo": 0, "n_botao": 2}),       # botão errado (Reembolsar): recusa
                    ("enviar_aprovada", {"id": 9, "n_campo": 0, "n_botao": 1}),
                    ("terminar", {"resumo": "1 registrada, 1 enviada"})],
                   receber={"id": 9, "status": "aprovado", "pelo_mac": True, "texto": aprovado})
    assert c.cmd_atender_tiktok(None, c.ler_config()) == 0
    rotas = [r for r, _ in ch["api"]]
    assert ("atendimento_receber", ) == tuple(r for r in rotas if r == "atendimento_receber")
    corpo = next(cp for r, cp in ch["api"] if r == "atendimento_receber")
    assert corpo["cliente"] == "leidianearaujo182" and corpo["canal"] == "tiktok_shop" and len(corpo["historico"]) == 2
    assert ENVIADO["texto"] == aprovado                                    # o texto aprovado, digitado pelo coletor
    assert ("atendimento_enviado", {"id": 9, "ok": True}) in ch["api"]
    assert any("Atendente TikTok" in json.dumps(cp, ensure_ascii=False) for r, cp in ch["api"] if r == "reuniao_postar")


def test_cliente_errado_nao_envia():
    ENVIADO.clear()
    import shutil
    shutil.rmtree(c.PASTA / "perfil", ignore_errors=True)
    ch = _preparar([("ler", {}), ("enviar_aprovada", {"id": 3, "n_campo": 0, "n_botao": 1}), ("terminar", {"resumo": "x"})],
                   aprovadas=[{"id": 3, "cliente": "outra_pessoa", "texto": "Oi!"}])
    c.cmd_atender_tiktok(None, c.ler_config())
    assert "não é do cliente outra_pessoa" in _ultimo_resultado(ch) and not ENVIADO.get("texto")
    assert not any(r == "atendimento_enviado" and cp.get("ok") for r, cp in ch["api"])     # só avisa a falha


def test_sem_novidade_nao_chama_a_ia():
    ch = _preparar([("terminar", {"resumo": "nada"})])
    c.cmd_atender_tiktok(None, c.ler_config())                            # 1ª rodada guarda a marca da caixa de entrada
    antes, marca = ch["claude"], c.ler_config().get("tiktok_marca_v4")
    assert marca
    ch2 = _preparar([], aprovadas=())
    c.salvar_config({"tiktok_marca_v4": marca})
    c.cmd_atender_tiktok(None, c.ler_config())
    assert ch2["claude"] == 0 and antes == 1                               # nada novo: zero gasto


def test_navega_com_a_ia_gratis_sem_gastar():
    ENVIADO.clear()
    import shutil
    shutil.rmtree(c.PASTA / "perfil", ignore_errors=True)
    roteiro = iter([("ler", {}), ("terminar", {"resumo": "nada a fazer"})])
    ch = _preparar([])
    api_antes = c.api

    def api(token, rota, params=None, corpo=None, metodo=None, timeout=300):
        if rota == "atendimento_navegar_ia":
            nome, ent = next(roteiro)
            return {"content": [{"type": "tool_use", "id": "g1", "name": nome, "input": ent}], "usage": {"input_tokens": 999}}
        return api_antes(token, rota, params, corpo, metodo, timeout)
    c.api = api
    c.cmd_atender_tiktok(None, c.ler_config())
    assert ch["claude"] == 0 and c._gasto_atendente(c.ler_config()) == 0      # tudo com a grátis: US$ 0


def test_shopee_usa_o_mesmo_atendente_com_o_canal_certo():
    import shutil
    shutil.rmtree(c.PASTA / "perfil", ignore_errors=True)
    ch = _preparar([("ler", {}), ("abrir", {"url": "https://seller-br.tiktok.com/x"}),
                    ("registrar", {"cliente": "joao", "historico": [{"de": "cliente", "texto": "oi"}, {"de": "cliente", "texto": "tem tester?"}]}),
                    ("terminar", {"resumo": "ok"})], canais=["shopee"])
    c.cmd_atender_tiktok(None, c.ler_config())
    corpo = next(cp for r, cp in ch["api"] if r == "atendimento_receber")
    assert corpo["canal"] == "shopee"
    assert "Shopee" in json.dumps(ch["ultima"][0], ensure_ascii=False)
    assert any("Atendente Shopee" in json.dumps(cp, ensure_ascii=False) for r, cp in ch["api"] if r == "reuniao_postar")


def test_conversa_da_lista_feita_de_div_aparece_para_clicar():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = _abrir(p, {})
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto(URL)
        texto = c._nav_ler(pg, {})
        ctx.close()
    assert "leidianearaujo182" in texto.split("ELEMENTOS:")[1]


def test_gratis_parou_sem_registrar_com_conversa_sem_resposta_a_paga_assume():
    # 27/09 (Shopee): o gpt-oss grátis leu a lista com "Sem resposta (3)" e terminou com "{}" sem registrar nada
    import shutil
    shutil.rmtree(c.PASTA / "perfil", ignore_errors=True)
    PAGINA.with_name("shopee.html").write_text(PAGINA.read_text(encoding="utf-8").replace(
        "<div>Não respondidos</div>", "<div>Sem resposta (3)</div>"), encoding="utf-8")
    ch = _preparar([("registrar", {"cliente": "leidianearaujo182", "historico": [
                        {"de": "cliente", "texto": "oi"}, {"de": "cliente", "texto": "tem tester?"}]}),
                    ("terminar", {"resumo": "1 registrada"})], canais=["shopee"])
    url = URL.replace("chat.html", "shopee.html")
    c.PLATAFORMAS["shopee"] = ("Shopee", url, "127.0.0.1", "Atendente Shopee")
    gratis = iter([{"content": [{"type": "tool_use", "id": "g1", "name": "ler", "input": {}}]},
                   {"content": [{"type": "text", "text": "{}"}]}])
    api_antes = c.api

    def api(token, rota, params=None, corpo=None, metodo=None, timeout=300):
        if rota == "atendimento_navegar_ia":
            return next(gratis)
        return api_antes(token, rota, params, corpo, metodo, timeout)
    c.api = api
    c.cmd_atender_tiktok(None, c.ler_config())
    assert ch["claude"] == 2                                                   # a reserva assumiu depois do "{}"
    assert any(r == "atendimento_receber" for r, _ in ch["api"])
    assert "Você parou sem registrar" in json.dumps(ch["ultima"], ensure_ascii=False)


def test_abre_a_conversa_pelo_nome_quando_a_lista_nao_vira_elemento():
    # 27/09 (Shopee): a linha da conversa não aparecia nos ELEMENTOS; abrir_conversa clica no nome
    import shutil
    shutil.rmtree(c.PASTA / "perfil", ignore_errors=True)
    PAGINA.with_name("shopee2.html").write_text(
        '<html><body><div>Sem resposta (1)</div><section onclick="document.title=\'aberta\'"><p>fernandacristiane11</p>'
        '<p>Comprador precisa de assistência</p></section></body></html>', encoding="utf-8")
    ch = _preparar([("terminar", {"resumo": "a lista não é clicável"}),       # cutucado: não pode terminar assim
                    ("abrir_conversa", {"cliente": "fernandacristiane11"}),
                    ("registrar", {"cliente": "fernandacristiane11", "historico": [
                        {"de": "cliente", "texto": "oi"}, {"de": "cliente", "texto": "cadê meu pedido?"}]}),
                    ("terminar", {"resumo": "1 registrada"})], canais=["shopee"])
    c.PLATAFORMAS["shopee"] = ("Shopee", URL.replace("chat.html", "shopee2.html"), "127.0.0.1", "Atendente Shopee")
    c.cmd_atender_tiktok(None, c.ler_config())
    txt = json.dumps(ch["ultima"], ensure_ascii=False)
    assert "AINDA NÃO" in txt and "Abri a conversa de fernandacristiane11" in txt and "TÍTULO: aberta" in txt
    assert any(r == "atendimento_receber" for r, _ in ch["api"])


def test_importa_o_sac_do_upseller_so_como_historico():
    # 27/09 (pedido do Bruno): o SAC do UpSeller tem um ano de respostas da equipe; vira histórico (nunca resposta)
    import shutil
    shutil.rmtree(c.PASTA / "perfil", ignore_errors=True)
    ch = _preparar([("ler", {}), ("rolar", {}),
                    ("registrar", {"cliente": "comprador_ml", "plataforma": "mercado_livre", "respondido": False, "historico": [
                        {"de": "cliente", "texto": "Sobre Sauvage 100ml: é original?"}, {"de": "loja", "texto": "Sim, 100% original!"}],
                        "pedido_id": "UP5377046774", "pedido": {"loja": "AURA SCENT", "numero_plataforma": "2000018852964378",
                        "itens": [{"nome": "Perfume Club De Nuit Iconic 105ml", "quantidade": 1}]}}),
                    ("enviar_aprovada", {"id": 1, "n_campo": 0, "n_botao": 1}),
                    ("fechados_concluido", {}), ("terminar", {"resumo": "1 importada"})])
    import base64
    PAGINA.with_name("foto.png").write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAADIAAAAyCAIAAACRXR/mAAAAK0lEQVR42u3NMQEAAAgDoK1/aM3hIYJpzW1vQ0JCQkJCQkJCQkJCQkJCQkLiA0yHAWG2m/mQAAAAAElFTkSuQmCC"))
    PAGINA.with_name("sac.html").write_text(PAGINA.read_text(encoding="utf-8").replace(
        "</body>", '<div class="it"><img src="foto.png" width="50" height="50"><span>Perfume Club De Nuit Iconic 105ml</span></div></body>'),
        encoding="utf-8")
    c.PLATAFORMAS["upseller_sac"] = ("UpSeller SAC", URL.replace("chat.html", "sac.html"), "127.0.0.1", "Importador SAC")
    assert c.cmd_importar_sac(None, c.ler_config()) == 0
    corpo = next(cp for r, cp in ch["api"] if r == "atendimento_receber")
    assert corpo["canal"] == "mercado_livre" and corpo["respondido"] and corpo["fechado"]
    pd = corpo["pedido_dados"]
    assert pd["fonte"] == "upseller_sac" and pd["loja"] == "AURA SCENT" and pd["itens"][0]["foto"].endswith("/foto.png")
    assert ("atendimento_sac", {"importar": False}) not in ch["api"]      # trouxe conversa nesta rodada: ainda não acabou
    assert "Ainda não" in json.dumps(ch["ultima"], ensure_ascii=False) and c.ler_config().get("sac_vazias") == 0
    txt = json.dumps(ch["ultima"], ensure_ascii=False)
    assert "Rolei" in txt and "nunca envia" in txt and not any(r == "atendimento_enviado" for r, _ in ch["api"])


def test_tela_de_login_nao_chama_a_ia():
    import shutil
    shutil.rmtree(c.PASTA / "perfil", ignore_errors=True)
    ch = _preparar([], canais=["shopee"])
    base = URL.rsplit("/", 1)[0]
    import os as _os
    _os.makedirs(PAGINA.parent / "seller" / "login", exist_ok=True)
    (PAGINA.parent / "seller" / "login" / "index.html").write_text("<html><body>Entrar</body></html>", encoding="utf-8")
    c.PLATAFORMAS["shopee"] = ("Shopee", base + "/seller/login/", "127.0.0.1", "Atendente Shopee")
    c.cmd_atender_tiktok(None, c.ler_config())
    assert ch["claude"] == 0 and not any(r == "atendimento_navegar_ia" for r, _ in ch["api"])


def test_duas_falhas_no_envio_devolvem_a_resposta_ao_bruno_sem_3a_tentativa():
    # card #108: a resposta 25 de fernandacristiane11 falhava no envio e o atendente tentava de novo a cada rodada
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import atendimento as at
    from test_atendimento import Repo
    import shutil
    shutil.rmtree(c.PASTA / "perfil", ignore_errors=True)
    r = Repo()
    r.t["atendimento_conversas"] = [{"id": 1, "cliente": "fernandacristiane11", "canal": "shopee", "status": "respondida"}]
    r.t["atendimento_rascunhos"] = [{"id": 25, "conversa_id": 1, "status": "aprovado", "texto_final": "Oi! Já foi enviado.",
                                     "enviar_pelo_mac": True, "enviado_em": None}]
    tentar = ("enviar_aprovada", {"id": 25, "n_campo": 0, "n_botao": 1})       # a conversa aberta é de outra cliente
    ch = _preparar([("ler", {}), tentar, tentar, tentar, ("terminar", {"resumo": "x"})],
                   aprovadas=at.para_enviar(r), canais=["shopee"])
    c.PLATAFORMAS["shopee"] = ("Shopee", URL, "127.0.0.1", "Atendente Shopee")
    api_antes = c.api

    def api(token, rota, params=None, corpo=None, metodo=None, timeout=300):
        if rota == "atendimento_enviado":
            ch["api"].append((rota, corpo))
            return at.marcar_enviado(r, corpo["id"], corpo.get("ok", True), corpo.get("erro"))
        return api_antes(token, rota, params, corpo, metodo, timeout)
    c.api = api
    c.cmd_atender_tiktok(None, c.ler_config())
    falhas = [cp for rt, cp in ch["api"] if rt == "atendimento_enviado"]
    assert len(falhas) == 2 and not any(f["ok"] for f in falhas)              # a 3ª tentativa não acontece
    rasc = r.t["atendimento_rascunhos"][0]
    assert rasc["status"] == "precisa_info" and not rasc["enviar_pelo_mac"] and "2 vezes" in rasc["motivo"]
    assert "não é do cliente fernandacristiane11" in rasc["motivo"] and rasc["pergunta_operador"]
    assert r.t["atendimento_conversas"][0]["status"] == "precisa_info" and at.para_enviar(r) == []
    assert "não está aprovada" in _ultimo_resultado(ch) and not ENVIADO.get("texto")


def test_teto_de_passos_pagos_encerra_a_rodada():
    import shutil
    shutil.rmtree(c.PASTA / "perfil", ignore_errors=True)
    ch = _preparar([("ler", {})] * 20 + [("terminar", {"resumo": "x"})])
    api_antes = c.api

    def api(token, rota, params=None, corpo=None, metodo=None, timeout=300):
        if rota == "atendimento_navegar_ia":
            raise RuntimeError("grátis fora do ar")                           # tudo vai para a IA paga
        return api_antes(token, rota, params, corpo, metodo, timeout)
    c.api = api
    c.cmd_atender_tiktok(None, c.ler_config())
    assert ch["claude"] == c.ATENDENTE_PAGOS_RODADA == 5


def test_login_encerra_na_hora_e_avisa_a_sala_uma_vez():
    import shutil
    shutil.rmtree(c.PASTA / "perfil", ignore_errors=True)
    ch = _preparar([], canais=["shopee"])
    base = URL.rsplit("/", 1)[0]
    os.makedirs(PAGINA.parent / "seller" / "login", exist_ok=True)
    (PAGINA.parent / "seller" / "login" / "index.html").write_text("<html><body>Entrar</body></html>", encoding="utf-8")
    c.PLATAFORMAS["shopee"] = ("Shopee", base + "/seller/login/", "127.0.0.1", "Atendente Shopee")
    c.cmd_atender_tiktok(None, c.ler_config())
    c.cmd_atender_tiktok(None, c.ler_config())                                 # 2ª rodada seguida, ainda no login
    avisos = [cp for rt, cp in ch["api"] if rt == "reuniao_postar"]
    assert len(avisos) == 1 and "login" in avisos[0]["texto"] and ch["claude"] == 0
    c.PLATAFORMAS["shopee"] = ("Shopee", URL, "127.0.0.1", "Atendente Shopee")    # entrou: o próximo login avisa de novo
    cfg = c.ler_config()
    _preparar([("terminar", {"resumo": "ok"})], canais=["shopee"])
    c.salvar_config(cfg)
    assert cfg.get("shopee_login_avisado")
    c.cmd_atender_tiktok(None, c.ler_config())
    assert not c.ler_config().get("shopee_login_avisado")


def test_comando_do_nubi_no_pc_so_da_lista():
    ch = _preparar([])
    class Pg:
        url = "https://seller.shopee.com.br/webchat"
        def goto(self, u, timeout=0): self.url = u
        def bring_to_front(self): pass
    c.salvar_config({"shopee_marca": "x"})
    assert c._pc_comando({"id": 1, "comando": "limpar_marca", "status": "pendente"}, Pg(), "T") == "limpar_marca"
    assert "shopee_marca" not in c.ler_config()
    assert c._pc_comando({"id": 1, "comando": "limpar_marca", "status": "pendente"}, Pg(), "T") is None      # não repete
    c._pc_comando({"id": 2, "comando": "rm -rf /", "status": "pendente"}, Pg(), "T")
    assert "recusado" in [cp for r, cp in ch["api"] if r == "atendimento_pc_resultado"][-1]["saida"]
    assert c._pc_comando({"id": 3, "comando": "reiniciar", "status": "pendente"}, Pg(), "T") == "reiniciar"


def test_busca_o_cliente_pela_caixa_de_busca():
    from playwright.sync_api import sync_playwright
    PAGINA.with_name("busca.html").write_text('<html><body><input placeholder="Buscar cliente" '
        'onkeydown="if(event.key==\'Enter\')document.body.insertAdjacentHTML(\'beforeend\',\'<div>achei \'+this.value+\'</div>\')">'
        '</body></html>', encoding="utf-8")
    with sync_playwright() as p:
        ctx = _abrir(p, {})
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto(URL.replace("chat.html", "busca.html"))
        txt = c._atendente_buscar(pg, "naiaraandradeabreu", {})
        ctx.close()
    assert "achei naiaraandradeabreu" in txt


SHOPEE_FALSA = """<html><head><meta charset="utf-8"></head><body style="margin:0">
<div style="display:flex">
 <div id="lista" style="width:300px">
  <input placeholder="Buscar nome do usuário" oninput="filtrar(this.value)">
  <div id="itens"></div>
 </div>
 <div id="chat" style="flex:1;min-height:500px">
  <div id="cab"></div><div id="msgs"></div>
  <div style="position:fixed;bottom:10px;left:320px;width:500px;display:flex">
   <div id="campo" contenteditable="true" style="flex:1;min-height:30px;border:1px solid #999"></div>
   <i class="icon-send-chat" style="display:inline-block;width:24px;height:24px;background:#ee4d2d;cursor:pointer" onclick="enviar()"></i>
  </div>
 </div>
</div>
<script>
const clientes = ["fulano1","beltrano2","naiaraandradeabreu","outra_pessoa"];
let aberta = null;
function filtrar(q){ const it = document.getElementById("itens"); it.innerHTML = "";
  clientes.filter(c => q ? c.includes(q) : c !== "naiaraandradeabreu").forEach(c => {   // naiara só aparece pela busca
    const d = document.createElement("div"); d.style.cursor = "pointer"; d.style.padding = "8px";
    d.innerHTML = "<div><span>" + c + "</span></div><div>Atrasado</div>";
    d.addEventListener("click", () => { aberta = c; document.getElementById("cab").innerText = c; document.getElementById("msgs").innerHTML = "<p>Qual a validade?</p>"; });
    it.appendChild(d); }); }
function enviar(){ const t = document.getElementById("campo").innerText.trim(); if (!t || !aberta) return;
  document.getElementById("msgs").insertAdjacentHTML("beforeend", "<p class=loja>" + t + "</p>"); document.getElementById("campo").innerText = "";
  localStorage.enviado = aberta + "|" + t; }
filtrar("");
</script></body></html>"""


def test_shopee_envia_a_aprovada_sem_ia_buscando_a_cliente():
    # 27/09 (relatório do PC): lista de divs sem botão, cliente fora do topo, campo contenteditable e envio só por ícone
    from playwright.sync_api import sync_playwright
    PAGINA.with_name("shopee_chat.html").write_text(SHOPEE_FALSA, encoding="utf-8")
    texto = "Oi! Tudo bem? Pode ficar tranquila! Depois de aberto, o perfume dura em média 2 anos."
    with sync_playwright() as p:
        ctx = _abrir(p, {})
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto(URL.replace("chat.html", "shopee_chat.html"))
        assert c._enviar_direto(pg, {"id": 34, "cliente": "naiaraandradeabreu", "texto": texto}) is None
        assert pg.evaluate("localStorage.enviado") == "naiaraandradeabreu|" + texto
        assert c._enviar_direto(pg, {"id": 34, "cliente": "naiaraandradeabreu", "texto": texto}) is None   # já está lá: não repete
        assert pg.evaluate("document.querySelectorAll('p.loja').length") == 1
        assert "não achei" in c._enviar_direto(pg, {"id": 9, "cliente": "ninguem_aqui", "texto": "x"})
        ctx.close()


def test_ia_que_pede_licenca_recebe_sim_e_segue():
    import shutil
    shutil.rmtree(c.PASTA / "perfil", ignore_errors=True)
    ch = _preparar([("terminar", {"resumo": "ok"})])
    gratis = iter([{"content": [{"type": "text", "text": "Preciso abrir a conversa de mavignierferro. Posso prosseguir com esse clique?"}]},
                   {"content": [{"type": "tool_use", "id": "g2", "name": "terminar", "input": {"resumo": "feito"}}]}])
    api_antes = c.api
    def api(token, rota, params=None, corpo=None, metodo=None, timeout=300):
        if rota == "atendimento_navegar_ia":
            return next(gratis)
        return api_antes(token, rota, params, corpo, metodo, timeout)
    c.api = api
    c.cmd_atender_tiktok(None, c.ler_config())
    assert ch["claude"] == 0                                             # não caiu na paga: seguiu com o "sim"


def test_chat_ja_aberto_nao_recarrega():
    # 27/09 (Bruno): recarregar o chat a cada rodada fazia a Shopee/TikTok pedir captcha; o chat se atualiza sozinho
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = _abrir(p, {})
        abas = {}
        pg = c._aba_do_canal(ctx, abas, "shopee")
        assert c._no_chat(pg, URL) is True                                  # 1ª vez: abre
        pg.evaluate("window.marca_nubi = 1")
        assert c._no_chat(pg, URL) is False and pg.evaluate("window.marca_nubi") == 1     # já está no chat: não recarrega
        assert c._aba_do_canal(ctx, abas, "shopee") is pg and c._aba_do_canal(ctx, abas, "tiktok_shop") is not pg
        ctx.close()


def test_shopee_conversa_fechada_recomeca_e_envia():
    # 27/09 (print do Bruno): conversa fechada pela Shopee não tem campo; só o botão "Recomeçar Conversa" devolve o campo
    from playwright.sync_api import sync_playwright
    html = """<html><head><meta charset="utf-8"></head><body><div class="lista"><div class="linha"><span>naiaraandradeabreu</span></div></div>
<div id="chat"><b>naiaraandradeabreu</b><p>Qual a validade ?</p><div id="rodape">A conversa foi fechada automaticamente
<button id="rec">Recomeçar Conversa</button></div></div>
<script>
document.getElementById('rec').onclick = () => { document.getElementById('rodape').innerHTML =
  '<textarea id="t" placeholder="Digite"></textarea>';
  const t = document.getElementById('t');
  t.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); const p = document.createElement('p');
    p.className = 'loja'; p.textContent = t.value; document.getElementById('chat').insertBefore(p, document.getElementById('rodape'));
    t.value = ''; } }); };
</script></body></html>"""
    PAGINA.with_name("shopee_fechada.html").write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        ctx = _abrir(p, {})
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto(URL.replace("chat.html", "shopee_fechada.html"))
        assert c._enviar_direto(pg, {"id": 1, "cliente": "naiaraandradeabreu", "texto": "Após aberto, dura cerca de 2 anos."}) is None
        assert pg.evaluate("document.querySelectorAll('p.loja').length") == 1
        ctx.close()


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
