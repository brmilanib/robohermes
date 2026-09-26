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
<div>Não respondidos</div><div>leidianearaujo182 · Vocês vendem perfumes tester?</div>
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


def _preparar(roteiro, aprovadas=(), receber=None):
    chamadas = {"api": [], "claude": 0}
    c.abrir_navegador = _abrir
    c.guardar_sessao = lambda ctx: None
    c._credencial = lambda site, cfg=None: ("bruno", "sk-ant-falsa") if site == "anthropic" else ("", "")
    c.token_nubi = lambda cfg: "T"
    c.ATENDENTE_URL = URL
    c.salvar_config({})

    def api(token, rota, params=None, corpo=None, metodo=None, timeout=300):
        chamadas["api"].append((rota, corpo))
        if rota == "atendimento_para_enviar":
            return {"itens": list(aprovadas)}
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
                    ("registrar", {"cliente": "leidianearaujo182", "mensagem": "Vocês vendem perfumes tester?"}),
                    ("enviar_aprovada", {"id": 9, "n_campo": 0, "n_botao": 2}),       # botão errado (Reembolsar): recusa
                    ("enviar_aprovada", {"id": 9, "n_campo": 0, "n_botao": 1}),
                    ("terminar", {"resumo": "1 registrada, 1 enviada"})],
                   receber={"id": 9, "status": "aprovado", "pelo_mac": True, "texto": aprovado})
    assert c.cmd_atender_tiktok(None, c.ler_config()) == 0
    rotas = [r for r, _ in ch["api"]]
    assert ("atendimento_receber", ) == tuple(r for r in rotas if r == "atendimento_receber")
    corpo = next(cp for r, cp in ch["api"] if r == "atendimento_receber")
    assert corpo["cliente"] == "leidianearaujo182" and corpo["canal"] == "tiktok_shop"
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
    assert not any(r == "atendimento_enviado" for r, _ in ch["api"])


def test_sem_novidade_nao_chama_a_ia():
    ch = _preparar([("terminar", {"resumo": "nada"})])
    c.cmd_atender_tiktok(None, c.ler_config())                            # 1ª rodada guarda a marca da caixa de entrada
    antes, marca = ch["claude"], c.ler_config().get("tiktok_marca_v2")
    assert marca
    ch2 = _preparar([], aprovadas=())
    c.salvar_config({"tiktok_marca_v2": marca})
    c.cmd_atender_tiktok(None, c.ler_config())
    assert ch2["claude"] == 0 and antes == 1                               # nada novo: zero gasto


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
