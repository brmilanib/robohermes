"""🛍️ Bazar (card #137): cadastro igual à planilha, colunas automáticas, vendas com baixa, post no formato do grupo,
catálogo do WhatsApp, importação da planilha real do Bruno e "levar ao Bazar" da lista Para promoção."""
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
import bazar  # noqa: E402


class Repo:
    def __init__(self):
        self.db = {}

    def _req(self, metodo, tabela, params=None, corpo=None, prefer=None):
        assert tabela == "ia_resumos"
        if metodo == "GET":
            chave = params["chave"][3:]
            return [{"texto": self.db[chave]}] if chave in self.db else []
        for linha in corpo:
            self.db[linha["chave"]] = linha["texto"]


def test_cadastro_calcula_como_a_planilha():
    r = Repo()
    p = bazar.salvar_produto(r, {"produto": "Yara Elixir", "marca": "Lattafa", "qtd_inicial": 3, "preco_original": "230,00",
                                 "desconto": 40, "condicao": "SEM CAIXA"})
    assert p["codigo"] == "BZ001" and p["preco_promo"] == 138.0 and p["economia"] == 92.0
    assert p["estoque"] == 3 and p["status"] == "DISPONÍVEL"
    bazar.salvar_venda(r, {"produto_id": p["id"], "qtd": 2, "cliente": "Ana", "pagamento": "Pix"})
    pn = bazar.painel(r)
    it = pn["produtos"][0]
    assert it["qtd_vendida"] == 2 and it["estoque"] == 1 and it["status"] == "ÚLTIMAS UNIDADES"
    assert pn["kpis"] == {"produtos": 1, "unidades": 1, "valor_potencial": 138.0, "esgotados": 0}
    assert pn["kpis_vendas"]["total"] == 276.0
    try:
        bazar.salvar_venda(r, {"produto_id": p["id"], "qtd": 2})
        raise AssertionError("vendeu mais do que tem")
    except bazar.ErroBazar as e:
        assert "só tem 1" in str(e)
    v = bazar.vendas(r)[0]
    bazar.salvar_venda(r, {"id": v["id"], "status": "Cancelado"})           # cancelada devolve ao estoque
    assert bazar.painel(r)["produtos"][0]["estoque"] == 3
    # desconto editado recalcula
    bazar.salvar_produto(r, {"id": p["id"], "desconto": 0.5})
    assert bazar.painel(r)["produtos"][0]["preco_promo"] == 115.0


def test_post_no_formato_do_grupo():
    r = Repo()
    p = bazar.salvar_produto(r, {"produto": "Yara Elixir", "marca": "Lattafa", "qtd_inicial": 1, "preco_original": 230,
                                 "desconto": 0.4, "descricao": "Uma fragrância feminina marcante, elegante e sofisticada!",
                                 "cor": "💜", "aba": "promocao"})
    t = bazar.post(p)
    assert t.splitlines()[0] == "🔥 OFERTA IMPERDÍVEL NA PURE PERFUMARIA! 🔥"
    assert "💜 Yara Elixir – Lattafa" in t
    assert "De R$ 230,00 por apenas R$ 138,00 😱🔥" in t and "💰 Economize R$ 92,00!" in t
    assert t.endswith("👜 Corre aproveitar essa oferta! ❤️✨")
    assert "📦" not in t and "🏷️ OUTLET PURE" in t                          # outlet não fala de caixa
    av = bazar.salvar_produto(r, {"produto": "Club de Nuit", "marca": "Armaf", "qtd_inicial": 1, "preco_original": 275.99,
                                  "desconto": 0.4, "condicao": "CAIXA COM PEQUENAS AVARIAS"})
    assert "📦 Produto original e novo · vai na caixa (caixa com pequenas avarias)" in bazar.post(av)
    sc = bazar.salvar_produto(r, {"produto": "Yara", "marca": "Lattafa", "qtd_inicial": 1, "preco_original": 249,
                                  "desconto": 0.4, "aba": "sem_caixa", "condicao": "SEM CAIXA"})
    assert "📦 Produto original e novo · sem caixa" in bazar.post(sc)


def test_frase_da_ia_sem_numeros():
    assert bazar.ler_frase("💜 | Uma fragrância doce e envolvente!") == ("💜", "Uma fragrância doce e envolvente!")
    cor, frase = bazar.ler_frase("🟥 | Por apenas 99 reais, irresistível!")
    assert cor == "❤️" and not any(c.isdigit() for c in frase)


def test_catalogo_e_arquivo_invalido():
    r = Repo()
    p = bazar.salvar_produto(r, {"produto": "Florata", "marca": "O Boticário", "qtd_inicial": 1, "preco_original": 115.8,
                                 "desconto": 0.5, "condicao": "SEM CAIXA"})
    cat = bazar.painel(r)["catalogo"]
    assert "✨ *Florata* | O Boticário" in cat and "*Por: R$ 57,90* (50% OFF)" in cat and "Código: BZ001" in cat
    try:
        bazar.salvar_produto(r, {"id": p["id"], "foto": "sala/../segredo.png"})
        raise AssertionError("aceitou caminho fora do Bazar")
    except bazar.ErroBazar:
        pass


def test_importa_a_planilha_do_bruno():
    r = Repo()
    dados = (RAIZ / "docs" / "bazar" / "BAZAR_PURE_PERFUMARIA.xlsx").read_bytes()
    n = bazar.importar_planilha(r, dados)
    assert n == 23
    assert bazar.importar_planilha(r, dados) == 0                          # não duplica
    ps = {p["produto"]: p for p in bazar.painel(r)["produtos"]}
    cdn = ps["CLUB DE NUIT INTENSE MEN"]
    assert cdn["marca"] == "ARMAF" and cdn["qtd_inicial"] == 15 and cdn["preco_original"] == 275.99
    assert cdn["desconto"] == 0.4 and cdn["preco_promo"] == 165.59 and cdn["data_cadastro"] == "2026-09-23"
    # 3 modelos: "SEM CAIXA…" vai para Sem caixa, o resto com avaria para Caixa avariada
    assert ps["YARA ELIXIR"]["aba"] == "sem_caixa" and ps["CK ONE"]["aba"] == "sem_caixa" and ps["FERRARI BLACK"]["aba"] == "avariada"
    assert sum(p["aba"] == "sem_caixa" for p in ps.values()) == 11 and sum(p["aba"] == "avariada" for p in ps.values()) == 12


def test_levar_ao_bazar_nao_duplica():
    r = Repo()
    itens = [{"sku": "ABC1", "titulo": "Perfume X", "disponivel": 4, "preco": 199.9, "sem_venda_dias": 90}]
    assert len(bazar.levar_ao_bazar(r, itens)) == 1
    assert bazar.levar_ao_bazar(r, itens) == []
    p = bazar.painel(r)["produtos"][0]
    assert p["aba"] == "promocao" and p["qtd_inicial"] == 4 and p["preco_promo"] == 159.92


STUB = """window.supabase = { createClient: () => { const sess = {access_token: "TOKEN", user: {id: "u1", email: "brmilani@gmail.com"}};
  return { auth: { getSession: async () => ({data: {session: sess}}), signOut: async () => {}, updateUser: async () => ({}),
    onAuthStateChange: cb => setTimeout(() => cb("INITIAL_SESSION", sess), 0) }, storage: {from: () => ({createSignedUrls: async () => ({data: []})})} }; } };"""


def test_tela():
    """Tela no PC e no celular: importa a planilha, edita o desconto na tabela, registra venda, abre o Compartilhar."""
    import os
    import subprocess
    import time
    import urllib.parse
    import urllib.request
    from playwright.sync_api import sync_playwright
    r = Repo()
    bazar.importar_planilha(r, (RAIZ / "docs" / "bazar" / "BAZAR_PURE_PERFUMARIA.xlsx").read_bytes())

    def api(rota):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(rota.request.url).query)
        nome, corpo = qs["r"][0], rota.request.post_data_buffer
        d = json.loads(corpo) if corpo and nome != "bazar_importar" else {}
        try:
            if nome == "bazar":
                out = bazar.painel(r)
            elif nome == "bazar_salvar":
                out = {"ok": True, "produto": bazar.salvar_produto(r, d)}
            elif nome == "bazar_venda":
                out = {"ok": True, "venda": bazar.salvar_venda(r, d)}
            elif nome == "bazar_post":
                p = next(x for x in bazar.painel(r)["produtos"] if x["id"] == int(qs["id"][0]))
                out = {"texto": bazar.post(p)}
            else:
                return rota.fulfill(status=404, content_type="application/json", body=json.dumps({"erro": "x"}))
        except bazar.ErroBazar as e:
            return rota.fulfill(status=400, content_type="application/json", body=json.dumps({"erro": str(e)}))
        rota.fulfill(content_type="application/json", body=json.dumps(out))

    aqui = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servidor_teste")
    porta = os.environ.get("PORTA_BZ", "8831")
    srv = subprocess.Popen([sys.executable, "-W", "ignore", os.path.join(aqui, "servidor.py")],
                           env=dict(os.environ, IA_FALSA="1", OPENAI_API_KEY="x", PORTA=porta), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{porta}/", timeout=2)
            break
        except OSError:
            time.sleep(0.5)
    try:
        with sync_playwright() as p:
            exe = os.environ.get("NUBI_CHROMIUM") or "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
            b = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
            for wd, ht, nome in ((1440, 900, "pc"), (390, 800, "cel")):
                pg = b.new_page(viewport={"width": wd, "height": ht})
                erros = []
                pg.on("pageerror", lambda e: erros.append(str(e)))
                pg.route("https://cdn.jsdelivr.net/**", lambda rt: rt.fulfill(content_type="application/javascript", body=STUB))
                pg.route("https://fonts.**", lambda rt: rt.abort())
                pg.route("**/api/app?r=bazar*", api)
                pg.goto(f"http://127.0.0.1:{porta}/#/bazar/avariada")
                pg.wait_for_selector(".bz-tab tbody tr", timeout=15000)
                txt = pg.inner_text("#main")
                assert "CLUB DE NUIT INTENSE MEN" in txt and "Valor potencial" in txt, txt[:500]
                if nome == "pc":
                    i = pg.locator(".bz-desc").first
                    i.fill("50")
                    i.dispatch_event("change")
                    pg.wait_for_function("document.querySelector('[id^=bz-pp-]').textContent.includes('138,00')", timeout=5000)
                    pg.locator("[data-bzv]").first.click()
                    pg.fill("#bzv-cliente", "Ana")
                    pg.click("#bzv-ok")
                    pg.wait_for_timeout(800)
                    assert bazar.vendas(r)[0]["cliente"] == "Ana"
                    pg.locator("[data-bzsh]").first.click()
                    pg.wait_for_selector("#bzc-cv", timeout=5000)
                    assert pg.evaluate("[document.querySelector('#bzc-cv').width, document.querySelector('#bzc-cv').height]") == [1080, 1920]
                    pg.click("[data-fmt=quadrado]")
                    pg.wait_for_function("document.querySelector('#bzc-cv') && document.querySelector('#bzc-cv').height === 1080", timeout=5000)
                    pg.click("[data-est=legendas]")
                    pg.wait_for_selector("#leg-grupo", timeout=5000)
                    t = pg.input_value("#leg-grupo")
                    assert t.startswith("🔥 OFERTA IMPERDÍVEL NA PURE PERFUMARIA! 🔥") and "R$ 138,00" in t, t
                    pg.screenshot(path=str(RAIZ / "testes" / "saida_bazar_compartilhar.png"))
                    pg.click(".modal [data-fechar]")
                    pg.click("#bz-novo")
                    pg.wait_for_selector(".bz-mod", timeout=5000)
                    assert pg.locator(".bz-mod").count() == 3
                    pg.locator("[name=bze-mod][value=sem_caixa]").check()
                    assert pg.input_value("#bze-condicao") == "SEM CAIXA"
                    pg.locator("[name=bze-mod][value=promocao]").check()
                    assert pg.input_value("#bze-condicao") == "OUTLET (SEM AVARIA)"
                    pg.screenshot(path=str(RAIZ / "testes" / "saida_bazar_novo.png"))
                    pg.click(".modal [data-fechar]")
                    pg.goto(f"http://127.0.0.1:{porta}/#/bazar/whatsapp")
                    pg.wait_for_selector("#bzw-cat", timeout=8000)
                    assert "BAZAR PURE PROMOÇÕES" in pg.input_value("#bzw-cat")
                    pg.goto(f"http://127.0.0.1:{porta}/#/bazar/vendas")
                    pg.wait_for_selector("[data-bzst]", timeout=8000)
                    pg.goto(f"http://127.0.0.1:{porta}/#/bazar/avariada")
                    pg.wait_for_selector(".bz-tab tbody tr", timeout=8000)
                larg = pg.evaluate("document.documentElement.scrollWidth")
                assert larg <= wd + 2, f"{nome}: rolagem lateral ({larg}px)"
                pg.screenshot(path=str(RAIZ / "testes" / f"saida_bazar_{nome}.png"), full_page=False)
                assert not erros, erros
            b.close()
    finally:
        srv.terminate()


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
