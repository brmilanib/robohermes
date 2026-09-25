# -*- coding: utf-8 -*-
"""
Teste de fumaça do nubi: sobe o servidor de teste (sem Supabase e sem IA de verdade) e confere que as rotas principais
respondem sem erro. Roda no GitHub a cada envio e localmente: python3 nubi/testes/fumaca.py
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
PORTA = os.environ.get("PORTA", "8799")
ROTAS = ["rotinas", "reuniao_tarefas", "reuniao", "estoque", "conhecimento", "conhecimento_pendente", "memoria_pendente",
         "ops_execucoes", "ops_erros", "agentes", "mac_painel", "inicio", "coletor_status"]

env = dict(os.environ, IA_FALSA="1", OLLAMA_API_KEY="x", ANTHROPIC_API_KEY="x", PORTA=PORTA)
srv = subprocess.Popen([sys.executable, "-W", "ignore", os.path.join(AQUI, "servidor_teste", "servidor.py")], env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
falhas = []
try:
    for _ in range(40):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORTA}/", timeout=2)
            break
        except OSError:
            time.sleep(0.5)
    for r in ROTAS:
        req = urllib.request.Request(f"http://127.0.0.1:{PORTA}/api/app?r={r}", headers={"Authorization": "Bearer TOKEN"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                corpo = json.loads(resp.read().decode() or "{}")
            if isinstance(corpo, dict) and corpo.get("erro"):
                falhas.append(f"{r}: {corpo['erro']}")
            else:
                print(f"ok   {r}")
        except Exception as e:  # noqa: BLE001
            falhas.append(f"{r}: {e}")
finally:
    srv.terminate()
if falhas:
    print("FALHOU:\n  " + "\n  ".join(falhas))
    sys.exit(1)
print("fumaça ok")
