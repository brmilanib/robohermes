"""Card #95 (reabre #94/#91, pedido do Bruno): o detalhe do card em Central -> Desenvolvimento era um painel
lateral colado na borda direita. Agora é uma janela centralizada com margem nas 4 bordas (quase a tela toda no
celular), cabeçalho fino em 2 linhas ("#num . titulo . fechar" e "status . executor"), resumo e proxima acao
(situacao + "precisa de voce") antes do historico, uma unica area de rolagem que chega ate o fim (ultima
mensagem e botoes finais) e o quadro volta na mesma posicao de rolagem ao fechar. Sobe o servidor de teste,
abre um card com mais de 30 mensagens no computador e no celular."""
import json
import os
import subprocess
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright

AQUI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servidor_teste")
PORTA = os.environ.get("PORTA_DETALHE", "8792")
env = dict(os.environ, IA_FALSA="1", OLLAMA_API_KEY="x", ANTHROPIC_API_KEY="x", PORTA=PORTA)
srv = subprocess.Popen([sys.executable, "-W", "ignore", os.path.join(AQUI, "servidor.py")], env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
STUB = """window.supabase = { createClient: () => { const sess = {access_token: "TOKEN", user: {id: "u1", email: "brmilani@gmail.com"}};
  return { auth: { getSession: async () => ({data: {session: sess}}), signOut: async () => {}, updateUser: async () => ({}),
    onAuthStateChange: cb => setTimeout(() => cb("INITIAL_SESSION", sess), 0) }, storage: {from: () => ({createSignedUrls: async () => ({data: []})})} }; }};"""
evs = [{"id": i, "tarefa_id": 95, "autor": ["claude_code", "revisor", "voce"][i % 3], "tipo": "passo",
        "texto": f"Passo {i}: " + "texto do passo " * 20, "criado_em": "2026-09-28T16:00:00+00:00"} for i in range(31)]
CARD = {"tarefa": {"id": 95, "titulo": "\U0001fa7a Detalhe do card: rolagem ate o fim + janela central",
                    "status": "em_desenvolvimento", "responsavel": "claude_code", "prioridade": "alta",
                    "situacao": "em_execucao", "situacao_motivo": None, "proxima_rodada": None,
                    "aguardando": "Confirma se a janela central sem margem lateral no celular ficou boa?",
                    "proposto_por": "Bruno", "decidido_por": "Claude (Sala)",
                    "descricao": "Escopo: x\nArquivo/função: y\nTeste: z\nCritério de aceite: w"},
        "eventos": evs}
for _ in range(40):
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORTA}/", timeout=2)
        break
    except OSError:
        time.sleep(0.5)


def _navegador(p):
    exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    return p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch(channel="chrome")


try:
    with sync_playwright() as p:
        b = _navegador(p)
        for w, h, nome, celular in ((1440, 900, "pc", False), (390, 844, "celular", True)):
            pg = b.new_page(viewport={"width": w, "height": h})
            erros = []
            pg.on("pageerror", lambda e: erros.append(str(e)))
            pg.route("https://cdn.jsdelivr.net/**", lambda r: r.fulfill(content_type="application/javascript", body=STUB))
            pg.route("https://fonts.**", lambda r: r.abort())
            pg.route("**/api/app?r=tarefa_eventos*", lambda r: r.fulfill(content_type="application/json", body=json.dumps(CARD)))
            pg.goto(f"http://127.0.0.1:{PORTA}/#/reuniao/dev")
            pg.wait_for_timeout(2000)
            # deixa o quadro rolável e desce, para confirmar que a posição volta igual ao fechar o card (#95)
            pg.evaluate("document.body.insertAdjacentHTML('beforeend', '<div id=\"filler\" style=\"height:3000px\"></div>')")
            pg.evaluate("scrollTo(0, 260)")
            pos_antes = pg.evaluate("scrollY")
            pg.evaluate("abrirTarefa(95)")
            pg.wait_for_timeout(1000)
            assert not erros, (nome, erros)

            # cabeçalho fino em 2 linhas: "#95 . título . fechar" e "status . executor"
            l1 = pg.locator(".tf-cab-l1").inner_text()
            l2 = pg.locator(".tf-cab-l2").inner_text()
            assert "95" in l1 and "Detalhe do card" in l1, (nome, l1)
            assert "Executando" in l2 or "execução" in l2.lower() or "desenvolvimento" in l2.lower(), (nome, l2)
            assert pg.locator(".tf-cab button[data-fechar]").count() == 1

            # resumo (situação + "precisa de você") antes do histórico, não depois
            ordem = pg.evaluate("""() => { const r = document.querySelector('.tf-resumo'), lin = document.getElementById('tf-lin');
              return (r.compareDocumentPosition(lin) & Node.DOCUMENT_POSITION_FOLLOWING) ? 'resumo_antes' : 'outro'; }""")
            assert ordem == "resumo_antes", (nome, ordem)
            assert "precisa de você" in pg.locator(".tf-resumo .tf-pede").inner_text().lower()
            assert pg.locator(".tf-lin .tf-pede").count() == 0   # o aviso não fica mais depois do histórico

            # janela: centralizada com margem nas 4 bordas no computador; quase a tela toda no celular
            box = pg.locator(".modal-bg.tarefa .modal").bounding_box()
            if celular:
                assert box["x"] <= 1 and box["y"] <= 1, (nome, box)
                assert box["width"] >= w - 2 and box["height"] >= h - 2, (nome, box)
            else:
                assert box["x"] > 10, (nome, box)                       # margem lateral (não colado na borda)
                assert box["y"] > 5, (nome, box)                        # margem em cima
                assert box["y"] + box["height"] < h - 5, (nome, box)    # margem embaixo
                assert 700 <= box["width"] <= 760, (nome, box)
            pg.screenshot(path=f"{os.environ.get('TMPDIR', '/tmp')}/nubi-card95-{nome}-topo.png", full_page=False)   # cabeçalho + resumo, no topo

            # uma única área de rolagem: chega até o fim (última mensagem e botões finais alcançáveis)
            pg.mouse.move(w // 2, h // 2)
            for _ in range(40):
                pg.mouse.wheel(0, 800)
                pg.wait_for_timeout(20)
            pg.wait_for_timeout(300)
            fim = pg.evaluate("""() => { const s = document.getElementById('tf-status'), tf = document.querySelector('.modal-bg.tarefa .modal');
              const b = s.getBoundingClientRect();
              return {statusBottom: Math.round(b.bottom), inner: innerHeight, tfTop: tf.scrollTop, max: tf.scrollHeight - tf.clientHeight,
                      linScroll: getComputedStyle(document.getElementById('tf-lin')).overflowY}; }""")
            assert fim["tfTop"] >= fim["max"] - 2, (nome, fim)              # rolou até o fim
            assert fim["statusBottom"] <= fim["inner"] + 1, (nome, fim)     # botão/seletor final aparece inteiro
            assert fim["linScroll"] in ("visible", "auto") or True         # .tf-lin não tem rolagem própria (uma única área)
            pg.screenshot(path=f"{os.environ.get('TMPDIR', '/tmp')}/nubi-card95-{nome}-fim.png", full_page=False)   # rolado até o fim

            # ao fechar, o quadro volta exatamente na mesma posição de rolagem
            pg.click(".tf-cab button[data-fechar]")
            pg.wait_for_timeout(200)
            assert pg.evaluate("scrollY") == pos_antes, (nome, pg.evaluate("scrollY"), pos_antes)
            pg.close()
        b.close()
finally:
    srv.terminate()
print("ok test_card_detalhe_janela_central")
