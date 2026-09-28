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
        casos = ((1440, 820, "pc", "Vocês vendem tester do Asad?", "Não vendemos tester, só perfumes lacrados."),
                 (390, 760, "cel", "Vocês fazem embrulho para presente?", "Não fazemos embrulho, só a caixa lacrada."))
        for w, h, nome, pergunta, resposta in casos:
            pg = b.new_page(viewport={"width": w, "height": h})
            erros = []; pg.on("pageerror", lambda e: erros.append(str(e)))
            pg.route("https://cdn.jsdelivr.net/**", lambda r: r.fulfill(content_type="application/javascript", body=STUB))
            pg.route("https://fonts.**", lambda r: r.abort())
            pg.goto(f"http://127.0.0.1:{PORTA}/#/estoque/tiktok"); pg.wait_for_selector(".atx", timeout=15000)   # endereço antigo leva ao SAC
            assert "#/sac/tiktok" in pg.url
            if nome == "cel":                                               # tudo passa pela aprovação
                pg.uncheck("#at-auto"); pg.wait_for_timeout(1500)
            pg.click("#atx-colar"); pg.fill("#at-cli", f"Ana {nome}"); pg.fill("#at-txt", pergunta)
            pg.click("#at-nova button"); pg.wait_for_selector(".atx-alerta", timeout=10000)
            assert "Preciso de você" in pg.inner_text(".atx-alerta"), nome          # abriu a conversa com a dúvida
            if nome == "pc":        # 🌐 sugestão da internet (só para o Bruno) e 🤖 conversa com a IA antes de responder
                pg.wait_for_selector("#atx-sug-usar", timeout=15000); pg.click("#atx-sug-usar")
                assert pg.input_value("#atx-txt").strip()
                pg.click("#atx-ia summary"); pg.fill("#atx-ia-txt", "o que você indicaria?"); pg.click("#atx-ia-env")
                pg.wait_for_selector("[data-ia-usar]", timeout=15000); pg.click("[data-ia-usar]")
                assert pg.input_value("#atx-txt").startswith("Oi! Temos opções florais") and "exemplo.com" in pg.inner_html("#atx-ia-msgs")
                pg.fill("#atx-txt", resposta)
            pg.fill("#atx-txt", resposta); pg.click("#atx-env"); pg.wait_for_timeout(1800)
            if nome == "pc":        # respondeu embaixo: a mensagem já vai para o cliente pelo atendente
                assert "⏳ enviando" in pg.inner_text("#atx-msgs") and "🤖 automático" in pg.inner_text("#atx-msgs")
                assert "Informação do pedido" in pg.inner_text(".atx-info")
                pg.click("#at-ligar"); pg.wait_for_timeout(1500)
                assert "ligado no Mac" in pg.inner_text(".at-num")
            else:                   # sem responder sozinho: vira rascunho no campo de baixo, o Bruno envia
                assert pg.input_value("#atx-txt").startswith("Oi!") and "Rascunho para aprovar" in pg.inner_text(".atx-alerta")
                larg = pg.evaluate("() => [document.documentElement.scrollWidth, innerWidth]")
                assert larg[0] <= larg[1] + 1, (nome, larg)                     # sem rolagem de lado no celular
                assert not pg.is_visible(".atx-lista")                          # no celular: só o chat aberto
                pg.click("#atx-env"); pg.wait_for_timeout(1800)
                assert "⏳ enviando" in pg.inner_text("#atx-msgs")
                pg.fill("#atx-txt", "Qualquer dúvida estou aqui!"); pg.click("#atx-env"); pg.wait_for_timeout(1800)
                assert "Qualquer dúvida estou aqui!" in pg.inner_text("#atx-msgs")      # mensagem livre do Bruno
                pg.click("#atx-voltar"); pg.wait_for_timeout(1200)
                assert pg.is_visible(".atx-lista") and f"Ana {nome}" in pg.inner_text(".atx-lista")
            pg.click("[data-at-aba=kb]"); pg.wait_for_selector(".at-kb-item", timeout=10000)
            assert pergunta in pg.inner_text(".at-kb"), nome
            assert "#/sac/base" in pg.url and "🎵 TikTok Shop" in pg.inner_text(".at-kb")      # base SAC com a origem (a dúvida veio do chat da TikTok)
            pg.click("[data-kb-vista=fichas]"); pg.wait_for_selector("#fi-prox", timeout=10000)
            assert "Fichas dos perfumes" in pg.inner_text("h1")
            pg.click("[data-kb-vista=base]"); pg.wait_for_selector("#kb-sac", timeout=10000)
            assert not erros, erros
            if nome == "pc":        # 🛍️ Shopee: mesma tela, conversas só da Shopee
                pg.goto(f"http://127.0.0.1:{PORTA}/#/sac/shopee"); pg.wait_for_selector("[data-at-aba=tudo]", timeout=15000)
                pg.click("[data-at-aba=tudo]"); pg.wait_for_selector(".atx", timeout=15000)
                assert "Shopee · Atendimento" in pg.inner_text("h1") and "Ana pc" not in pg.inner_text(".atx-lista")
                pg.click("#atx-colar"); pg.fill("#at-cli", "joao shopee"); pg.fill("#at-txt", "vocês têm loja física?")
                pg.click("#at-nova button"); pg.wait_for_selector(".atx-alerta", timeout=10000)
                assert "joao shopee" in pg.inner_text(".atx-lista")
                pg.goto(f"http://127.0.0.1:{PORTA}/#/sac/tiktok"); pg.wait_for_selector("h1", timeout=15000); pg.wait_for_timeout(1500)
                assert "TikTok Shop · Atendimento" in pg.inner_text("h1")
                assert "joao shopee" not in pg.inner_text(".atx-lista")
                pg.goto(f"http://127.0.0.1:{PORTA}/#/sac/ml"); pg.wait_for_selector("h1", timeout=15000); pg.wait_for_timeout(1200)
                assert "Mercado Livre · Atendimento" in pg.inner_text("h1") and not pg.is_visible("#at-ligar")
                assert "Base de conhecimento SAC" in pg.inner_text("#side")          # menu SAC com as lojas e a base
                pg.evaluate("""async () => { const p = (c) => api('atendimento_taxa', {}, {method: 'POST', body: JSON.stringify(c)});
                  await p({canal: 'shopee', taxa_resposta: 55.56, tempo_resposta: '03:14:11', csat: 50, respondidos: 5, nao_respondidos: 4, periodo: 'Últimos 7 Dias'});
                  await p({canal: 'tiktok_shop', taxa_resposta: 89.23, tempo_resposta: '844.1 min', csat: 85.7, periodo: 'Últimos 28 dias',
                           extras: {total_chats: 65, chats_ia: 31, chats_equipe: 13, chats_ia_para_equipe: 21, conversao: 11.76, receita_pos: '$ 493', pedidos_pos: 2, taxa_risco: 2.94}}); }""")
                pg.goto(f"http://127.0.0.1:{PORTA}/#/sac/painel"); pg.wait_for_selector(".sp-kpis", timeout=15000)
                pg.wait_for_selector(".sp-chip", timeout=15000)
                pg.set_viewport_size({"width": 1760, "height": 1250})
                pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), "painel_sac.png"), full_page=True)
                assert "IA → equipe" in pg.inner_text(".sp-root") and "89,23%" in pg.inner_text(".sp-root")
                assert "precisam de resposta agora" in pg.inner_text(".sp-kpis") and "Últimos 7 dias" in pg.inner_text(".sp-root")
                pg.click("#sp-tv"); pg.wait_for_selector(".sp-root.tv", timeout=5000)             # modo TV
                pg.screenshot(path=os.path.join(os.environ.get("TMPDIR", "/tmp"), "painel_sac_tv.png"))
                pg.click("#sp-tv"); pg.wait_for_selector(".sp-root:not(.tv)", timeout=5000)
                # 27/09 (Bruno): o que pisca no painel é clicável e abre o chat; as linhas abrem a lista filtrada
                assert "Na plataforma" in pg.inner_text(".sp-root") and "Respondidas pelo nubi" in pg.inner_text(".sp-root")
                pg.locator(".sp-agora .sp-link", has_text="joao shopee").first.click()
                pg.wait_for_selector(".atx-cab", timeout=15000)
                assert "#/sac/shopee" in pg.url and "joao shopee" in pg.inner_text(".atx-cab")
                assert "on" in (pg.get_attribute("[data-at-aba=precisa]", "class") or "")
                pg.goto(f"http://127.0.0.1:{PORTA}/#/sac/painel"); pg.wait_for_selector(".sp-kpis", timeout=15000)
                pg.locator(".sp-card .sp-linha", has_text="Respondidas hoje").first.click()
                pg.wait_for_selector(".atx", timeout=15000)
                assert "on" in (pg.get_attribute("[data-at-aba=respondidas]", "class") or "")
                pg.goto(f"http://127.0.0.1:{PORTA}/#/sac/tiktok"); pg.wait_for_selector(".atx-item", timeout=15000)
                assert pg.locator(".atx-item .atx-ok").count() >= 1                              # respondida: ✓✓
                assert not erros, erros
        b.close()
finally:
    srv.terminate()
print("ok atendimento real")
