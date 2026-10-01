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
_CABECALHO_ORIGINAL = c._conversa_aberta_e_de

CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
PAGINA = Path(tempfile.mkdtemp()) / "chat.html"
PAGINA.write_text("""<html><head><meta charset="utf-8"><title>Bate-papo da loja</title></head><body>
<div>Não respondidos</div><div class="item" style="cursor:pointer" onclick="document.body.dataset.aberta=1"><b>leidianearaujo182</b> · Vocês vendem perfumes tester?</div>
<textarea placeholder="Insira / para respostas salvas"></textarea>
<button onclick="const t=document.querySelector('textarea'); localStorage.enviado=t.value; const p=document.createElement('p'); p.textContent=t.value; document.body.appendChild(p); t.value=''">Enviar</button>
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
        if rota == "atendimento_navegar_ia":   # 27/09: navegação só com IA grátis; o roteiro vem pelo gpt-oss do nubi
            return claude(None, corpo["mensagens"], corpo.get("sistema"))
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
    def pago(*a, **k):
        chamadas["pago"] = chamadas.get("pago", 0) + 1
        raise AssertionError("a navegação não pode usar IA paga")
    c._claude_ferramentas = pago
    c._modelos_locais = lambda: []            # sem Ollama local no teste
    c._conversa_aberta_e_de = lambda pg, cli: True   # a página falsa não tem cabeçalho; a trava tem teste próprio
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
    assert ENVIADO["texto"].strip() == aprovado                            # o texto aprovado, digitado pelo coletor
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


def test_gratis_parou_sem_registrar_recebe_o_empurrao_e_continua_gratis():
    # 27/09 (Shopee): o gpt-oss grátis leu a lista com "Sem resposta (3)" e terminou com "{}" sem registrar nada; agora ele
    # recebe o empurrão ("Você parou sem registrar") e continua — sem IA paga
    import shutil
    shutil.rmtree(c.PASTA / "perfil", ignore_errors=True)
    PAGINA.with_name("shopee.html").write_text(PAGINA.read_text(encoding="utf-8").replace(
        "<div>Não respondidos</div>", "<div>Sem resposta (3)</div>"), encoding="utf-8")
    ch = _preparar([], canais=["shopee"])
    url = URL.replace("chat.html", "shopee.html")
    c.PLATAFORMAS["shopee"] = ("Shopee", url, "127.0.0.1", "Atendente Shopee")
    gratis = iter([{"content": [{"type": "tool_use", "id": "g1", "name": "ler", "input": {}}]},
                   {"content": [{"type": "text", "text": "{}"}]},
                   {"content": [{"type": "tool_use", "id": "g2", "name": "registrar", "input": {"cliente": "leidianearaujo182",
                     "historico": [{"de": "cliente", "texto": "oi"}, {"de": "cliente", "texto": "tem tester?"}]}}]},
                   {"content": [{"type": "tool_use", "id": "g3", "name": "terminar", "input": {"resumo": "1 registrada"}}]}])
    vistas = []
    api_antes = c.api

    def api(token, rota, params=None, corpo=None, metodo=None, timeout=300):
        if rota == "atendimento_navegar_ia":
            vistas.append(corpo["mensagens"])
            return next(gratis)
        return api_antes(token, rota, params, corpo, metodo, timeout)
    c.api = api
    c.cmd_atender_tiktok(None, c.ler_config())
    assert not ch.get("pago")
    assert any(r == "atendimento_receber" for r, _ in ch["api"])
    assert "Você parou sem registrar" in json.dumps(vistas[-1], ensure_ascii=False)


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


def test_ias_gratis_fora_do_ar_encerra_sem_pagar():
    # 27/09 (Bruno): navegação nunca usa IA paga; com as grátis fora do ar, a rodada para e tenta de novo na próxima
    import shutil
    shutil.rmtree(c.PASTA / "perfil", ignore_errors=True)
    ch = _preparar([])
    api_antes = c.api
    tentativas = []

    def api(token, rota, params=None, corpo=None, metodo=None, timeout=300):
        if rota == "atendimento_navegar_ia":
            tentativas.append(1)
            raise RuntimeError("grátis fora do ar")
        return api_antes(token, rota, params, corpo, metodo, timeout)
    c.api = api
    c.cmd_atender_tiktok(None, c.ler_config())
    assert not ch.get("pago") and len(tentativas) >= 1 and c._gasto_atendente(c.ler_config()) == 0


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


def test_shopee_recomecar_com_confirmacao_e_campo_que_demora():
    # 28/09 (joana, falhou 2x): depois do "Recomeçar Conversa" a Shopee pede confirmação e o campo demora a aparecer
    from playwright.sync_api import sync_playwright
    html = """<html><head><meta charset="utf-8"></head><body><div class="lista"><div class="linha"><span>joanaabranches</span></div></div>
<div id="chat"><b>joanaabranches</b><p>Boa tarde! Acabei de comprar</p><div id="rodape">A conversa foi fechada automaticamente
<div class="btn-rec" style="cursor:pointer">Recomeçar Conversa</div></div></div><div id="m"></div>
<script>
document.querySelector('.btn-rec').onclick = () => { document.getElementById('m').innerHTML =
  '<div role="dialog">Deseja recomeçar a conversa? <span>Cancelar</span> <span id="ok">Confirmar</span></div>';
  document.getElementById('ok').onclick = () => { document.getElementById('m').innerHTML = '';
    setTimeout(() => { document.getElementById('rodape').innerHTML = '<div contenteditable="true" id="t" style="width:300px;height:30px"></div>';
      const t = document.getElementById('t');
      t.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); const p = document.createElement('p');
        p.className = 'loja'; p.textContent = t.innerText; document.getElementById('chat').insertBefore(p, document.getElementById('rodape'));
        t.innerText = ''; } }); }, 2500); }; };
</script></body></html>"""
    PAGINA.with_name("shopee_confirma.html").write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        ctx = _abrir(p, {})
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto(URL.replace("chat.html", "shopee_confirma.html"))
        assert "Recomeçar visível: sim" in c._testar_envio(pg, "joanaabranches")       # o teste não digita nem recomeça
        assert pg.evaluate("document.querySelectorAll('p.loja').length") == 0 and not pg.evaluate("!!document.getElementById('t')")
        assert c._enviar_direto(pg, {"id": 81, "cliente": "joanaabranches", "texto": "Pode deixar que vamos conferir a válvula!"}) is None
        assert pg.evaluate("document.querySelectorAll('p.loja').length") == 1
        ctx.close()


def test_falha_de_envio_conta_o_que_havia_na_tela():
    from playwright.sync_api import sync_playwright
    html = """<html><head><meta charset="utf-8"></head><body style="margin:0;width:1200px;height:800px">
<div style="position:absolute;left:0;top:0">joanaabranches</div>
<div style="position:absolute;left:500px;top:700px"><span>Conversa encerrada pela plataforma</span></div></body></html>"""
    PAGINA.with_name("shopee_sem_campo.html").write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        ctx = _abrir(p, {})
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.set_viewport_size({"width": 1200, "height": 800})
        pg.goto(URL.replace("chat.html", "shopee_sem_campo.html"))
        erro = c._enviar_direto(pg, {"id": 1, "cliente": "joanaabranches", "texto": "Oi"})
        assert erro.startswith("não achei o campo") and "Conversa encerrada pela plataforma" in erro, erro
        ctx.close()


def test_rola_ate_3_vezes_e_recusa_conversa_antiga():
    # 28/09 (Bruno): sem rolar, chats novos do TikTok abaixo do topo não vinham; e o chat de agosto da joana veio como novo
    ch = _preparar([("ler", {}), ("rolar", {}), ("rolar", {}), ("rolar", {}), ("rolar", {}),
                    ("registrar", {"cliente": "joanaabranches", "data_ultima": "21/08", "historico": [
                        {"de": "cliente", "texto": "Boa tarde! Acabei de comprar"}, {"de": "loja", "texto": "Olá"}]}),
                    ("terminar", {"resumo": "nada"})])
    assert c.cmd_atender_tiktok(None, c.ler_config()) == 0
    txt = json.dumps(ch["ultima"], ensure_ascii=False)
    assert txt.count("Rolei") == 3 and "Já rolou 3 vezes" in txt and "conversa antiga (21/08" in txt
    assert not any(r == "atendimento_receber" for r, _ in ch["api"])


def test_data_da_tela():
    from datetime import date
    h = date(2026, 9, 28)
    assert [c._data_antiga(t, h) for t in ("14:05", "Ontem", "segunda", "27/09", "21/08", "21 de ago", "")] == \
        [False, False, False, False, True, True, False]


def test_so_marca_enviado_quando_aparece_no_chat():
    # 28/09 (Bruno): "✓ enviado" só quando a mensagem chegou de verdade no chat
    from playwright.sync_api import sync_playwright
    html = """<html><head><meta charset="utf-8"></head><body><b>mrcia.amorim24</b><textarea data-nubi-n="0"></textarea>
<button data-nubi-n="1">Enviar</button></body></html>"""
    PAGINA.with_name("nao_envia.html").write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        ctx = _abrir(p, {})
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto(URL.replace("chat.html", "nao_envia.html"))
        estado = {"els": {0: {"n": 0, "tag": "textarea", "tipo": "", "texto": "", "nome": ""},
                          1: {"n": 1, "tag": "button", "tipo": "", "texto": "Enviar", "nome": ""}}}
        erro = c._atendente_digitar(pg, {"n_campo": 0, "n_botao": 1}, estado, {"id": 1, "cliente": "mrcia.amorim24",
                                                                                "texto": "Oi, Márcia! Sentimos muito pelo ocorrido."})
        assert erro and "não apareceu no chat" in erro
        ctx.close()


def test_traz_as_fotos_que_a_cliente_mandou():
    # 28/09 (Márcia): as fotos do perfume quebrado mandadas no chat do TikTok não chegavam ao nubi
    import base64
    from playwright.sync_api import sync_playwright
    PAGINA.with_name("foto.png").write_bytes(base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAADIAAAAyCAIAAACRXR/mAAAAK0lEQVR42u3NMQEAAAgDoK1/aM3hIYJpzW1vQ0JCQkJCQkJCQkJCQkJCQkLiA0yHAWG2m/mQAAAAAElFTkSuQmCC"))
    html = """<html><head><meta charset="utf-8"></head><body style="margin:0;width:1400px">
<div style="position:absolute;left:0;top:0;width:330px"><img class="avatar" src="foto.png?a" width="120" height="120"></div>
<div style="position:absolute;left:500px;top:200px"><div class="msg"><img src="foto.png?quebrado" width="200" height="200"></div></div>
<div style="position:absolute;left:1150px;top:100px"><img src="foto.png?painel" width="120" height="120"></div></body></html>"""
    PAGINA.with_name("fotos.html").write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        ctx = _abrir(p, {})
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.set_viewport_size({"width": 1400, "height": 900})
        pg.goto(URL.replace("chat.html", "fotos.html"))
        fotos = c._fotos_da_cliente(pg)
        assert len(fotos) == 1 and fotos[0].endswith("foto.png?quebrado"), fotos
        assert c._atendente_painel({"cliente": "x"}, pg)["fotos_cliente"] == fotos
        ctx.close()


def test_le_a_analise_de_servico_do_tiktok_sem_ia():
    # 28/09 (print do Bruno): TikTok → Análise de serviço → Visão geral
    txt = """Visão geral dos chats\nAtividades ao vivo\nSessões de hoje\n3 sessão(ões)\nAgentes online\n1 Agentes
Relatório de operações\nÚltimos 28 dias: 2026-08-31—2026-09-27\nVolume de chats\nDesempenho do serviço\nConversão de vendas\nRiscos do chat
Total de chats\n65\n66.67%\nChats apenas de IA\n31\nChats apenas de agentes\n13\nChats de IA para agente\n21
Taxa de satisfação\n85.7%\n71.43%\nTop 30% (75.9%)\nTaxa de resposta em 24 horas\n89.23%\n16%\nTempo médio de resposta\n844.1 min\n-50.98%
Receita pós-atendimento\n$ 493\nPedidos pós-atendimento\n2\nConversão de vendas\n11.76%\nRiscos do chat\n1 sessão(ões)\nTaxa de risco\n2.94%"""
    d = c._taxa_tiktok_do_texto(txt)
    assert d["taxa_resposta"] == 89.23 and d["csat"] == 85.7 and d["tempo_resposta"] == "844.1 min"
    assert d["periodo"] == "Últimos 28 dias"
    assert d["extras"] == {"total_chats": 65, "chats_ia": 31, "chats_equipe": 13, "chats_ia_para_equipe": 21, "receita_pos": "$ 493",
                           "pedidos_pos": 2, "conversao": 11.76, "taxa_risco": 2.94, "sessoes_hoje": 3}, d["extras"]
    assert c._taxa_tiktok_do_texto("Bate-papo da loja") == {}


def test_fecha_a_janelinha_do_upseller_que_tampa_o_clique():
    # 28/09 (Mac): um aviso do UpSeller (.ant-modal) na frente fez o clique em 'My Warehouse' falhar 2x
    from playwright.sync_api import sync_playwright
    html = """<html><head><meta charset="utf-8"></head><body><span id="mw" onclick="document.body.dataset.ok=1">My Warehouse</span>
<div class="ant-modal-wrap" style="position:fixed;inset:0;background:rgba(0,0,0,.4)"><div class="ant-modal" role="dialog">
<div class="ant-modal-body">Novidades do UpSeller!</div><button class="ant-modal-close" aria-label="Close"
onclick="document.querySelector('.ant-modal-wrap').remove()">x</button></div></div></body></html>"""
    PAGINA.with_name("upseller_aviso.html").write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        ctx = _abrir(p, {})
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto(URL.replace("chat.html", "upseller_aviso.html"))
        assert c._fechar_popups(pg) == 1
        pg.click("#mw", timeout=3000)
        assert pg.evaluate("document.body.dataset.ok") == "1"
        ctx.close()


def test_so_registra_com_o_chat_da_propria_cliente_aberto():
    # 28/09 (print do Bruno): andrezaaasouza recebeu foto, produto, pedido e mensagens da amordemaelb
    from playwright.sync_api import sync_playwright
    html = """<html><head><meta charset="utf-8"></head><body style="margin:0;width:1400px">
<div style="position:absolute;left:0;top:0;width:330px"><div>andrezaaasouza</div><div>amordemaelb</div></div>
<div style="position:absolute;left:420px;top:60px"><b>amordemaelb</b></div>
<div style="position:absolute;left:420px;top:300px">Bom dia! Vi que você está de olho no Sabah Al Ward</div></body></html>"""
    PAGINA.with_name("cabecalho.html").write_text(html, encoding="utf-8")
    with sync_playwright() as p:
        ctx = _abrir(p, {})
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.set_viewport_size({"width": 1400, "height": 900})
        pg.goto(URL.replace("chat.html", "cabecalho.html"))
        assert _CABECALHO_ORIGINAL(pg, "amordemaelb") is True
        assert _CABECALHO_ORIGINAL(pg, "andrezaaasouza") is False      # só na lista, não no cabeçalho
        ctx.close()


def test_registrar_recusa_chat_de_outra_cliente_e_nome_vazio():
    # 29/09 (card #118): com o chat de outra cliente aberto, ou sem nome, nada vai para o nubi
    hist = [{"de": "cliente", "texto": "Oi"}, {"de": "cliente", "texto": "Tem tester?"}]
    ch = _preparar([("ler", {}), ("registrar", {"cliente": "", "historico": hist}),
                    ("registrar", {"cliente": "simonefa22", "historico": hist}), ("terminar", {"resumo": "x"})])
    c._conversa_aberta_e_de = lambda pg, cli: False        # o chat aberto é de outra pessoa
    try:
        c.cmd_atender_tiktok(None, c.ler_config())
    finally:
        c._conversa_aberta_e_de = lambda pg, cli: True
    assert not any(r == "atendimento_receber" for r, _ in ch["api"])
    ch2 = _preparar([("ler", {}), ("registrar", {"cliente": "simonefa22", "historico": hist}), ("terminar", {"resumo": "x"})])
    c.cmd_atender_tiktok(None, c.ler_config())              # cliente certa: grava normal
    assert any(r == "atendimento_receber" for r, _ in ch2["api"])


def test_nao_achada_2_rodadas_vai_para_precisa_de_voce_e_sai_da_fila():
    # card #119: conversa não achada em 2 rodadas seguidas para de repetir a cada hora e avisa o Bruno
    c.salvar_config({})
    for _ in range(2):
        antes = c.ler_config().get("nao_achadas", {})          # _preparar zera a config: guarda a contagem entre as rodadas
        ch = _preparar([("ler", {}), ("abrir_conversa", {"cliente": "fulana_que_nao_existe"}), ("terminar", {"resumo": "x"})])
        c.salvar_config({"nao_achadas": antes})
        c.cmd_atender_tiktok(None, c.ler_config())
    n = c.ler_config()["nao_achadas"]["tiktok_shop"]["fulana_que_nao_existe"]["n"]
    assert n == 2
    assert any("precisa de você" in json.dumps(cp, ensure_ascii=False) for r, cp in ch["api"] if r == "reuniao_postar")
    antes = c.ler_config().get("nao_achadas", {})
    ch = _preparar([("ler", {}), ("abrir_conversa", {"cliente": "fulana_que_nao_existe"}), ("terminar", {"resumo": "x"})])
    c.salvar_config({"nao_achadas": antes})
    c.cmd_atender_tiktok(None, c.ler_config())            # 3ª rodada: fora da fila, a IA nem tenta abrir
    assert "NÃO ABRA" in json.dumps(ch["ultima"], ensure_ascii=False) or "saiu da fila automática" in _ultimo_resultado(ch)
    assert c.ler_config()["nao_achadas"]["tiktok_shop"]["fulana_que_nao_existe"]["n"] == 2   # não conta de novo


def test_1_nao_achada_usa_busca_primeiro_e_achar_zera_a_contagem():
    c.salvar_config({"nao_achadas": {"tiktok_shop": {"leidianearaujo182": {"n": 1, "em": c.datetime.now().isoformat(), "nome": "leidianearaujo182"}}}})
    chamou = []
    orig = c._atendente_buscar
    c._atendente_buscar = lambda pg, cli, estado: chamou.append(cli) or "busca"
    try:
        _preparar([("ler", {}), ("abrir_conversa", {"cliente": "leidianearaujo182"}), ("terminar", {"resumo": "x"})])
        c.salvar_config({"nao_achadas": {"tiktok_shop": {"leidianearaujo182": {"n": 1, "em": c.datetime.now().isoformat(), "nome": "leidianearaujo182"}}}})
        c.cmd_atender_tiktok(None, c.ler_config())
    finally:
        c._atendente_buscar = orig
    assert chamou == ["leidianearaujo182"]                  # buscou por nome ANTES de procurar na lista
    assert "leidianearaujo182" not in c.ler_config().get("nao_achadas", {}).get("tiktok_shop", {})


def test_sem_envio_falso_corta_registrei_com_contador_zero():
    fim = "Registrei 3 conversas. Nada mais a fazer."
    assert c._sem_envio_falso(fim, 0, 0) == "Nada mais a fazer."
    assert c._sem_envio_falso(fim, 0, 3) == fim
    assert c._sem_envio_falso("Enviei tudo.", 0) == ""


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)


def test_captcha_conta_como_login_e_espera_sem_recarregar():
    """01/10 (Bruno: 'já deu captcha duas vezes'): tela de verificação = login (a rodada não recarrega o chat) e, depois do
    aviso, o atendente deixa a aba quieta por 30 min."""
    import coletor as c
    from datetime import datetime, timedelta

    class Pg:
        def __init__(self, url):
            self.url = url
    assert c._na_tela_login(Pg("https://seller.shopee.com.br/verification/captcha?x=1"))
    assert c._na_tela_login(Pg("https://accounts.shopee.com.br/seller/login"))
    assert not c._na_tela_login(Pg("https://seller.shopee.com.br/new-webchat/conversations"))
    assert c._esperando_login({"shopee_login_avisado": datetime.now().isoformat()}, "shopee")
    assert not c._esperando_login({"shopee_login_avisado": (datetime.now() - timedelta(hours=1)).isoformat()}, "shopee")
    assert not c._esperando_login({}, "shopee")
    assert not c._esperando_login({"shopee_login_avisado": "lixo"}, "shopee")
