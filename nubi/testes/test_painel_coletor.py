"""03/10 (Bruno: "ver o coletor funcionando, bonito, em tempo real, e conversar com o Hermes aqui no Mac"): Painel do coletor
(localhost): estado, tela ao vivo, chat com o Hermes (Ollama falso), ações confirmadas (comando da lista → Central; card)."""
import json
import os
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
os.environ["NUBI_TOKEN"] = "t"
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "public" / "coletor"))
import coletor  # noqa: E402

P = coletor.PASTA
(P / "comandos").mkdir(parents=True)
(P / "comandos" / "600.log").write_text("09:00 começou\n09:01 vendas: dia 2026-01-05 ok\n")
(P / "comandos" / "599.log").write_text("OK: coletor atualizado.\n")
(P / "comandos" / "599.log.rc").write_text("0")
(P / "despachante.json").write_text(json.dumps({"rodando": {"600": {"log": str(P / "comandos" / "600.log"), "inicio": time.time() - 90,
                                                                    "cmd": "historico_vendas"}}, "nomes": {"599": "atualizar"}}))
(P / "coletor.log").write_text("2026-10-03 09:00:00 linha do coletor\n")
coletor.TELA_AO_VIVO.write_bytes(b"\xff\xd8jpg")
coletor._outra_rodando = lambda: True

# Ollama falso (stream no formato OpenAI)
pedidos_ollama = []


class Ol(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(json.dumps({"models": [{"name": "hermes3:8b"}]}).encode())

    def do_POST(self):
        pedidos_ollama.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200)
        self.end_headers()
        for p in ["Rodando o histórico. ", "Quer atualizar o estoque?\n", "[[comando:estoque]]"]:
            self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": p}}]}) + "\n\n").encode())
        self.wfile.write(b"data: [DONE]\n\n")


ol = ThreadingHTTPServer(("127.0.0.1", 0), Ol)
threading.Thread(target=ol.serve_forever, daemon=True).start()
coletor.OLLAMA = f"http://127.0.0.1:{ol.server_port}/v1/chat/completions"
coletor._modelos_locais = lambda: ["hermes3:8b"]
coletor.contexto_hermes = lambda token: ("SISTEMA", "CTX")
chamadas = []


def api_falsa(token, rota, params=None, corpo=None, **k):
    chamadas.append((rota, corpo))
    if rota == "mac_painel":
        return {"lista": [{"k": "estoque", "nome": "Atualizar o estoque"}, {"k": "diario", "nome": "Rodar a coleta"}]}
    if rota == "mac_pedir":
        return {"ok": True, "id": 777}
    if rota == "reuniao_tarefa_salvar":
        return {"ok": True, "id": 160}
    return {}


coletor.api = api_falsa


class A:
    porta = 0
    sem_abrir = True


# sobe o painel numa porta livre
import socket  # noqa: E402
s = socket.socket()
s.bind(("127.0.0.1", 0))
A.porta = s.getsockname()[1]
s.close()
threading.Thread(target=coletor.cmd_painel, args=(A, {}), daemon=True).start()
time.sleep(0.6)
URL = f"http://localhost:{A.porta}"


def get(c, **h):
    return urllib.request.urlopen(urllib.request.Request(URL + c, headers=h), timeout=10)


html = get("/").read().decode()
assert "Painel do coletor" in html and "Conversar com o coletor" in html and "Codex" in html
e = json.loads(get("/estado").read())
assert e["rodando"][0]["comando"] == "historico_vendas" and "dia 2026-01-05" in e["rodando"][0]["log"][-1]
assert e["recentes"][0]["nomes"] == "atualizar" and e["recentes"][0]["ok"] and e["coleta_rodando"]
assert e["ollama"] is None or isinstance(e["ollama"], list)
assert coletor.PAINEL_ABERTO.exists()                        # a coleta sabe que o painel está aberto
assert get("/tela").read() == b"\xff\xd8jpg"
# outro site (Origin de fora) não consegue usar o painel
try:
    get("/estado", Origin="https://site-mal.com")
    raise AssertionError("devia recusar")
except urllib.error.HTTPError as er:
    assert er.code == 403

# chat
req = urllib.request.Request(URL + "/chat", data=json.dumps({"mensagens": [{"role": "user", "content": "o que está rodando?"}], "agente": "hermes"}).encode(),
                             headers={"Content-Type": "application/json"}, method="POST")
txt = urllib.request.urlopen(req, timeout=20).read().decode()
assert "Rodando o histórico" in txt and "[[comando:estoque]]" in txt, txt
sis = pedidos_ollama[-1]["messages"][0]["content"]
assert "estoque: Atualizar o estoque" in sis and "historico_vendas" in sis and "[[card:" in sis

# Claude Code e Codex (CLI do Mac, só leitura): flags de leitura e teto do Ferreiro
import subprocess as _sp  # noqa: E402
rodadas = []


class R:
    def __init__(self, out="", err="", rc=0):
        self.stdout, self.stderr, self.returncode = out, err, rc


def run_falso(argv, **k):
    rodadas.append(argv)
    if argv[0] == "codex":
        Path(argv[argv.index("--output-last-message") + 1]).write_text("Codex: o log mostra o dia 05/01.\n[[comando:diario]]")
        return R()
    return R(json.dumps({"result": "Claude: está no histórico de vendas.\n[[card:Gestor por mês|usar o Personalizado]]", "total_cost_usd": 0.12}))


coletor.subprocess.run = run_falso
coletor.ferreiro_pronto = lambda cfg=None: (True, "")
coletor.astra_pronto = lambda cfg=None: (True, "")
coletor._claude_bin = lambda: "claude"
coletor._codex_bin = lambda: "codex"
coletor._credencial = lambda site, cfg=None: ("u", "chave-" + site)
coletor._teto_ferreiro = lambda cfg: 10.0
gastos = []
coletor._gasto_ferreiro = lambda cfg, somar=0.0: gastos.append(somar) or 0.0
for ag, esperado in (("claude", "Claude: está no histórico"), ("codex", "Codex: o log")):
    req = urllib.request.Request(URL + "/chat", data=json.dumps({"mensagens": [{"role": "user", "content": "o que houve?"}], "agente": ag}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    assert esperado in urllib.request.urlopen(req, timeout=20).read().decode()
cl, cx = rodadas[0], rodadas[1]
ferr = cl[cl.index("--allowedTools") + 1]
assert "WebSearch" in ferr and "Edit" not in ferr and "Write" not in ferr and "commit" not in ferr and "--permission-mode" not in cl
assert cx[cx.index("--sandbox") + 1] == "read-only"
assert 0.12 in gastos                                            # o Claude conta no teto do Ferreiro
coletor._gasto_ferreiro = lambda cfg, somar=0.0: 10.0
assert "teto de hoje" in coletor._painel_cli({}, "claude", "S", [{"role": "user", "content": "oi"}])
# memória: a 2ª mensagem continua a sessão do Claude (--resume) e manda só a fala nova; anexo vai junto
coletor._gasto_ferreiro = lambda cfg, somar=0.0: 0.0
rodadas.clear()
_run_ant = coletor.subprocess.run
coletor.subprocess.run = lambda argv, **k: rodadas.append(argv) or R(json.dumps({"result": "ok", "session_id": "S1", "total_cost_usd": 0}))
coletor._painel_cli({}, "claude", "S", [{"role": "user", "content": "primeira"}], nova=True)
anexo = str(coletor.PASTA / "painel_anexos" / "a.png")
coletor._painel_cli({}, "claude", "S", [{"role": "user", "content": "primeira"}, {"role": "assistant", "content": "ok"},
                                        {"role": "user", "content": "e agora?"}], [anexo])
assert "--resume" not in rodadas[0] and rodadas[1][rodadas[1].index("--resume") + 1] == "S1"
assert rodadas[1][2].startswith("Bruno: e agora?") and anexo in rodadas[1][2]
coletor._painel_cli({}, "codex", "S", [{"role": "user", "content": "olha o print"}], [anexo])
assert rodadas[-1][rodadas[-1].index("-i") + 1] == anexo
coletor.subprocess.run = _run_ant

# ações (o Bruno confirma no botão)
def acao(d):
    r = urllib.request.Request(URL + "/acao", data=json.dumps(d).encode(), headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(r, timeout=10).read())


a = acao({"tipo": "comando", "chave": "estoque"})
assert a["ok"] and "#777" in a["texto"] and ("mac_pedir", {"comando": "estoque", "arg": ""}) in chamadas
c = acao({"tipo": "card", "titulo": "Gestor: período por mês", "descricao": "usar o seletor"})
assert c["ok"] and "#160" in c["texto"]
cc = [x for x in chamadas if x[0] == "reuniao_tarefa_salvar"][0][1]
assert cc["status"] == "proposta" and cc["area"] == "coletor" and cc["autor"] == "hermes"
assert not acao({"tipo": "rm -rf"})["ok"]
p_ = acao({"tipo": "programar", "titulo": "Gestor: período por mês", "descricao": "usar a caixa única", "agente": "claude", "anexos": ["/x.png"]})
assert p_["ok"] and "#160" in p_["texto"] and "Ferreiro" in p_["texto"]
cc = [x for x in chamadas if x[0] == "reuniao_tarefa_salvar"][-1][1]
assert cc["status"] == "aprovada" and cc["responsavel"] == "claude_mac" and "/x.png" in cc["descricao"]
acao({"tipo": "programar", "titulo": "x", "agente": "codex"})
assert [x for x in chamadas if x[0] == "reuniao_tarefa_salvar"][-1][1]["responsavel"] == "astra"
# anexo (print) vai para a pasta do coletor; outro tipo é recusado
r_ = urllib.request.Request(URL + "/anexo", data=b"\x89PNG...", headers={"Content-Type": "image/png"}, method="POST")
cam = json.loads(urllib.request.urlopen(r_, timeout=10).read())["caminho"]
assert cam.startswith(str(coletor.PASTA / "painel_anexos")) and Path(cam).read_bytes() == b"\x89PNG..."
try:
    urllib.request.urlopen(urllib.request.Request(URL + "/anexo", data=b"x", headers={"Content-Type": "text/html"}, method="POST"), timeout=10)
    raise AssertionError("devia recusar")
except urllib.error.HTTPError as er:
    assert er.code == 400

# foto ao vivo: só com o painel aberto, a cada ~4 s
class Pg:
    n = 0

    def is_closed(self):
        return False

    def screenshot(self, **k):
        Pg.n += 1
        return b"\xff\xd8novo"


class Ctx:
    pages = [Pg()]


coletor.CTX_VIVO[:] = [Ctx(), 0.0]
coletor.foto_ao_vivo()
coletor.foto_ao_vivo()
assert Pg.n == 1 and coletor.TELA_AO_VIVO.read_bytes() == b"\xff\xd8novo"
os.utime(coletor.PAINEL_ABERTO, (time.time() - 60, time.time() - 60))
coletor.CTX_VIVO[1] = 0
coletor.foto_ao_vivo()
assert Pg.n == 1                                               # painel fechado: não fotografa
assert coletor.comando_mac("painel_instalar")[-1] == "painel-instalar"

# a página no navegador: chat com botão de ação
if os.environ.get("NUBI_CHROMIUM"):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=os.environ["NUBI_CHROMIUM"])
        pg = b.new_page(viewport={"width": 1300, "height": 900})
        erros = []
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(URL)
        pg.wait_for_selector("#jobs .job")
        assert "historico_vendas" in pg.inner_text("#jobs")
        pg.click(".ag button[data-a=hermes]")
        pg.fill("#q", "o que está rodando?")
        pg.keyboard.press("Enter")
        pg.wait_for_selector("button.acao")
        assert "Rodar no Mac: estoque" in pg.inner_text("button.acao")
        assert pg.locator("#mic").count() == 1 and pg.locator("#arq").count() == 1 and pg.locator("#nova").count() == 1
        assert "[[" not in pg.inner_text("#msgs")
        pg.screenshot(path=str(RAIZ / "testes" / "saida_painel_coletor.png"))
        pg.set_viewport_size({"width": 390, "height": 800})
        assert pg.evaluate("document.documentElement.scrollWidth") <= 392
        assert not erros, erros
        b.close()
print("ok painel do coletor")
