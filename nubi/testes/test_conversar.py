"""Chat com o Hermes no Terminal: contexto do projeto, resposta ao vivo (Ollama falso) e resumo na caixa de conhecimento."""
import builtins
import http.server
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402

PEDIDOS = []


class OllamaFalso(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        PEDIDOS.append(corpo)
        self.send_response(200)
        self.end_headers()
        if corpo.get("stream"):
            for p in ("A coleta ", "de hoje ", "falhou no login."):
                self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': p}}]})}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
        else:
            self.wfile.write(json.dumps({"choices": [{"message": {"content": "Bruno perguntou da coleta."}}]}).encode())

    def log_message(self, *a):
        pass


def test_conversa_com_contexto_e_resumo():
    srv = http.server.HTTPServer(("127.0.0.1", 0), OllamaFalso)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    c.OLLAMA = f"http://127.0.0.1:{srv.server_port}/v1/chat/completions"
    salvos = []

    def api(token, rota, params=None, corpo=None, metodo=None, timeout=300):
        if rota == "reuniao":
            return {"sistema": "BRIEFING DO NUBI", "mensagens": [{"autor": "Claude", "texto": "estoque ok", "criado_em": "2026-09-25T13:25:00+00:00"}]}
        if rota == "coletor_status":
            return {"execucoes": [{"iniciado_em": "2026-09-25T16:00:00+00:00", "tarefa": "diario", "ok": False,
                                   "mensagem": "O Nubimetrics pediu login de novo"}]}
        if rota == "reuniao_tarefas":
            return {"tarefas": [{"id": 9, "status": "aprovada", "responsavel": "claude_code", "titulo": "Gate de publicação"}]}
        if rota == "conhecimento":
            return {"itens": [{"fixo": True, "titulo": "Hermes vigia", "texto": "conserta o coletor"}]}
        if rota == "conhecimento_salvar":
            salvos.append(corpo)
        return {}
    c.api, c.token_nubi = api, lambda cfg: "T"
    falas = iter(["por que a coleta falhou?", "/sair"])
    original = builtins.input
    builtins.input = lambda prompt="": next(falas)
    try:
        assert c.cmd_conversar(type("A", (), {"modelo": None})(), {}) == 0
    finally:
        builtins.input = original
    sistema = PEDIDOS[0]["messages"][0]["content"]
    assert "BRIEFING DO NUBI" in sistema and "25/09 13:00 diario: ERRO" in sistema      # horário em Brasília
    assert "#9 [aprovada/claude_code]" in sistema and "Hermes vigia" in sistema
    assert PEDIDOS[0]["messages"][-1]["content"] == "por que a coleta falhou?"
    assert salvos and salvos[0]["tipo"] == "conversa" and "Bruno perguntou" in salvos[0]["texto"]


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
