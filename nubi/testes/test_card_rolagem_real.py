"""Rolagem do card no nubi DE VERDADE (26/09: o Bruno testou e o fim do card não aparecia). Sobe o servidor de teste, abre
Central → Desenvolvimento, abre um card longo (relatório + 25 passos) no computador e no celular e rola até o fim."""
import json, os, subprocess, sys, time, urllib.request
from playwright.sync_api import sync_playwright
AQUI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servidor_teste")
PORTA = os.environ.get("PORTA_ROLAGEM", "8791")
env = dict(os.environ, IA_FALSA="1", OLLAMA_API_KEY="x", ANTHROPIC_API_KEY="x", PORTA=PORTA)
srv = subprocess.Popen([sys.executable, "-W", "ignore", os.path.join(AQUI, "servidor.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
STUB = """window.supabase = { createClient: () => { const sess = {access_token: "TOKEN", user: {id: "u1", email: "brmilani@gmail.com"}};
  return { auth: { getSession: async () => ({data: {session: sess}}), signOut: async () => {}, updateUser: async () => ({}),
    onAuthStateChange: cb => setTimeout(() => cb("INITIAL_SESSION", sess), 0) }, storage: {from: () => ({createSignedUrls: async () => ({data: []})})} }; } };"""
longo = "\n".join(f"- Linha {i} do relatório final com bastante texto para ocupar espaço na tela e testar a rolagem." for i in range(60))
evs = [{"id": i, "tarefa_id": 94, "autor": ["claude_mac", "claude_code", "revisor"][i % 3], "tipo": "passo",
        "texto": f"Passo {i}: " + "texto do passo " * 25, "criado_em": "2026-09-26T16:00:00+00:00"} for i in range(25)]
card = {"tarefa": {"id": 94, "titulo": "🩺 Corrigir rolagem", "status": "feita", "responsavel": "claude_mac", "descricao": "Escopo: x\nArquivo/função: y\nTeste: z\nCritério de aceite: w",
                   "relatorio": longo, "prioridade": "alta"}, "eventos": evs}
for _ in range(40):
    try: urllib.request.urlopen(f"http://127.0.0.1:{PORTA}/", timeout=2); break
    except OSError: time.sleep(0.5)
try:
    with sync_playwright() as p:
        exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
        b = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch(channel="chrome")
        for w, h, nome in ((1440, 820, "pc"), (390, 760, "cel")):
            pg = b.new_page(viewport={"width": w, "height": h})
            erros = []; pg.on("pageerror", lambda e: erros.append(str(e)))
            pg.route("https://cdn.jsdelivr.net/**", lambda r: r.fulfill(content_type="application/javascript", body=STUB))
            pg.route("https://fonts.**", lambda r: r.abort())
            pg.route("**/api/app?r=tarefa_eventos*", lambda r: r.fulfill(content_type="application/json", body=json.dumps(card)))
            pg.goto(f"http://127.0.0.1:{PORTA}/#/reuniao/dev"); pg.wait_for_timeout(2500)
            pg.evaluate("abrirTarefa(94)"); pg.wait_for_timeout(1500)
            info = pg.evaluate("""() => { const m = document.querySelector('.modal-bg.tarefa .modal'), tf = m, bg = document.querySelector('.modal-bg.tarefa');
              const r = e => { const b = e.getBoundingClientRect(); return [Math.round(b.top), Math.round(b.bottom), Math.round(b.height)]; };
              return {bg: r(bg), modal: r(m), tf: r(tf), tfScroll: [tf.scrollHeight, tf.clientHeight], inner: innerHeight,
                      cssModal: getComputedStyle(m).height + ' / ' + getComputedStyle(m).maxHeight + ' / pad ' + getComputedStyle(bg).padding,
                      tfOverflow: getComputedStyle(tf).overflowY}; }""")
            assert not erros, erros
            pg.mouse.move(w - 200, h // 2)
            for _ in range(40): pg.mouse.wheel(0, 800); pg.wait_for_timeout(30)
            pg.wait_for_timeout(500)
            fim = pg.evaluate("""() => { const s = document.getElementById('tf-status'), tf = document.querySelector('.modal-bg.tarefa .modal'); const b = s.getBoundingClientRect();
              return {statusBottom: Math.round(b.bottom), inner: innerHeight, tfTop: tf.scrollTop, max: tf.scrollHeight - tf.clientHeight}; }""")
            assert fim["tfTop"] >= fim["max"] - 2, (nome, fim)             # rolou até o fim
            assert fim["statusBottom"] <= fim["inner"], (nome, fim)        # o seletor de status aparece inteiro
        b.close()
finally:
    srv.terminate()
