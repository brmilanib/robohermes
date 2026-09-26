"""Atendimento no nubi DE VERDADE (26/09): Minhas Lojas → 🎵 TikTok Shop. Cola a mensagem do cliente, sem dado vira
"Precisa de você", a resposta do lojista vai para a base e gera o rascunho, o operador aprova. Computador e celular."""
import os, subprocess, sys, time, urllib.request
from playwright.sync_api import sync_playwright
AQUI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servidor_teste")
PORTA = os.environ.get("PORTA_ATENDIMENTO", "8793")
env = dict(os.environ, IA_FALSA="1", OLLAMA_API_KEY="x", ANTHROPIC_API_KEY="x", PORTA=PORTA)
srv = subprocess.Popen([sys.executable, "-W", "ignore", os.path.join(AQUI, "servidor.py")], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
STUB = """window.supabase = { createClient: () => { const sess = {access_token: "TOKEN", user: {id: "u1", email: "brmilani@gmail.com"}};
  return { auth: { getSession: async () => ({data: {session: sess}}), signOut: async () => {}, updateUser: async () => ({}),
    onAuthStateChange: cb => setTimeout(() => cb("INITIAL_SESSION", sess), 0) }, storage: {from: () => ({createSignedUrls: async () => ({data: []})})} }; } };"""
for _ in range(40):
    try: urllib.request.urlopen(f"http://127.0.0.1:{PORTA}/", timeout=2); break
    except OSError: time.sleep(0.5)
try:
    with sync_playwright() as p:
        exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
        b = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        casos = ((1440, 820, "pc", "Vocês vendem tester do Asad?", "Vendemos perfumes tester?", "Não vendemos tester, só perfumes lacrados."),
                 (390, 760, "cel", "Vocês fazem embrulho para presente?", "Fazem embrulho para presente?", "Não fazemos embrulho, só a caixa lacrada."))
        for w, h, nome, pergunta, tipo, resposta in casos:
            pg = b.new_page(viewport={"width": w, "height": h})
            erros = []; pg.on("pageerror", lambda e: erros.append(str(e)))
            pg.route("https://cdn.jsdelivr.net/**", lambda r: r.fulfill(content_type="application/javascript", body=STUB))
            pg.route("https://fonts.**", lambda r: r.abort())
            pg.goto(f"http://127.0.0.1:{PORTA}/#/estoque/tiktok"); pg.wait_for_selector("#at-nova", timeout=15000)
            pg.fill("#at-cli", "Ana"); pg.fill("#at-txt", pergunta)
            pg.click("#at-nova button"); pg.wait_for_timeout(1500)
            pg.click("[data-at-aba=info]"); pg.wait_for_selector(".at-conv.info", timeout=10000)
            assert "não tenho essa informação" in pg.inner_text(".at-conv.info"), nome
            pg.fill(".at-conv.info textarea", resposta)
            pg.fill(".at-conv.info [data-at-tipo]", tipo)
            pg.click("[data-at-responder]"); pg.wait_for_timeout(1500)
            pg.click("[data-at-aba=fila]"); pg.wait_for_selector("[data-at-txt]", timeout=10000)
            assert pg.input_value("[data-at-txt]").startswith("Oi!"), nome
            assert "Dados usados" in pg.inner_text(".at-conv")                 # o operador audita o que foi usado
            larg = pg.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")
            assert larg[0] <= larg[1] + 1, (nome, larg)                         # sem rolagem de lado no celular
            pg.click("[data-at-ok]"); pg.wait_for_timeout(1500)
            pg.click("[data-at-aba=feitas]"); pg.wait_for_timeout(1200)
            assert "aprovado como estava" in pg.inner_text("#main"), nome
            pg.click("[data-at-aba=kb]"); pg.wait_for_selector(".at-kb-item", timeout=10000)
            assert tipo in pg.inner_text(".at-kb"), nome
            assert not erros, erros
        b.close()
finally:
    srv.terminate()
print("ok atendimento real")
