"""🧪 Decants (01/10): custo por ml do estoque, 15/10/5 ml + frasco/adesivo/caixa × markup 2,3, ml digitado, kit fora,
levar ao Bazar (aba Decants) com post e catálogo dos preços por tamanho; tela no PC e no celular."""
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "testes"))
import bazar  # noqa: E402
import decants  # noqa: E402
from test_bazar import Repo, STUB  # noqa: E402

ITENS = [{"sku": "YARA100", "titulo": "Perfume Lattafa Yara EDP 100ml Feminino", "marca": "Lattafa", "tipo": "Perfume", "disponivel": 4, "custo": 150.0},
         {"sku": "ASAD", "titulo": "Perfume Asad Lattafa EDP", "marca": "Lattafa", "tipo": "Perfume", "disponivel": 2, "custo": 120.0},
         {"sku": "KIT", "titulo": "Kit Perfume 2x 30ml", "marca": "", "tipo": "Perfume", "disponivel": 1, "custo": 90.0},
         {"sku": "SPLASH", "titulo": "Body Splash 250ml", "marca": "", "tipo": "Body splash", "disponivel": 9, "custo": 20.0},
         {"sku": "MINI", "titulo": "Perfume Miniatura 7ml", "marca": "", "tipo": "Perfume", "disponivel": 3, "custo": 30.0},
         {"sku": "SEMCUSTO", "titulo": "Perfume X 50ml", "marca": "", "tipo": "Perfume", "disponivel": 1, "custo": None}]


def test_conta_dos_decants():
    r = Repo()
    p = decants.planilha(ITENS, decants.config(r), decants.itens_extra(r))
    assert [x["sku"] for x in p["itens"]] == ["YARA100"]
    y = p["itens"][0]
    assert y["custo_ml"] == 1.5 and y["markup_usado"] == 2.3
    # 15 ml: 22,50 + frasco 5 + embalagem 1 + adesivo 0,50 = 29,00 × 2,3 = 66,70 · 10 ml: 21,50 → 49,45 · 5 ml: 14,00 → 32,20
    assert [(d["ml"], d["custo"], d["preco"]) for d in y["decants"]] == [(15, 29.0, 66.7), (10, 21.5, 49.45), (5, 14.0, 32.2)]
    assert y["insumos"] == {"frasco": 5.0, "caixa": 1.0, "adesivo": 0.5} and y["insumos_total"] == 6.5
    assert {x["sku"] for x in p["sem_volume"]} == {"ASAD", "KIT", "MINI"}          # sem ml, kit e miniatura
    assert [x["sku"] for x in p["sem_custo"]] == ["SEMCUSTO"]
    # padrão editável e ml/markup por perfume
    decants.salvar_config(r, {"frasco": "4,50", "markup": 2})
    decants.salvar_item(r, {"sku": "ASAD", "volume_ml": 100})
    decants.salvar_item(r, {"sku": "YARA100", "markup": 3})
    p = decants.planilha(ITENS, decants.config(r), decants.itens_extra(r))
    d = {x["sku"]: x for x in p["itens"]}
    assert d["YARA100"]["decants"][2] == {"ml": 5, "custo": 13.5, "preco": 40.5, "lucro": 27.0}   # 7,50 + 4,50 + 1 + 0,50
    assert d["ASAD"]["volume_manual"] and d["ASAD"]["decants"][1]["preco"] == round((12 + 6.0) * 2, 2)
    # custo próprio de um perfume (frasco mais caro, sem adesivo); vazio volta ao padrão
    decants.salvar_item(r, {"sku": "YARA100", "frasco": "8", "adesivo": 0})
    y = {x["sku"]: x for x in decants.planilha(ITENS, decants.config(r), decants.itens_extra(r))["itens"]}["YARA100"]
    assert y["insumos"] == {"frasco": 8.0, "caixa": 1.0, "adesivo": 0.0} and y["decants"][2]["custo"] == 16.5
    decants.salvar_item(r, {"sku": "YARA100", "frasco": None, "adesivo": None})
    y = {x["sku"]: x for x in decants.planilha(ITENS, decants.config(r), decants.itens_extra(r))["itens"]}["YARA100"]
    assert y["insumos"] == {"frasco": 4.5, "caixa": 1.0, "adesivo": 0.5}


def test_leva_ao_bazar_com_os_precos():
    r = Repo()
    y = decants.planilha(ITENS, decants.config(r), {})["itens"][0]
    p = bazar.decant_ao_bazar(r, dict(y, foto="bazar/decant/YARA100/foto-1.jpg"))
    assert p["produto"] == "Lattafa Yara EDP Feminino"
    assert p["aba"] == "decant" and p["status"] == "DECANT" and p["foto"] == "bazar/decant/YARA100/foto-1.jpg"
    t = bazar.post(p)
    assert t.startswith("✨ DECANT NA PURE PERFUMARIA! ✨") and "❤️ Lattafa Yara EDP Feminino\n" in t   # marca não repete
    assert "🧪 5 ml por R$ 32,20" in t and "🧪 15 ml por R$ 66,70" in t
    # de novo = atualiza o mesmo (não duplica)
    p2 = bazar.decant_ao_bazar(r, dict(y, decants=[{"ml": 5, "preco": 30.0}]))
    assert p2["id"] == p["id"] and len(bazar.produtos(r)) == 1 and p2["decant"] == [{"ml": 5, "preco": 30.0}]
    assert "🧪 *DECANTS*" in bazar.painel(r)["catalogo"] and "5 ml R$ 30,00" in bazar.painel(r)["catalogo"]


def test_notas_e_legenda():
    d = decants.notas_do_texto('Achei: {"perfume": "Yara Lattafa", "familia": "Âmbar Floral", "notas_topo": "Orquídea, Heliotrópio",'
                               ' "notas_coracao": "Acordes gourmand", "notas_fundo": "Baunilha, Almíscar",'
                               ' "link": "https://www.fragrantica.com.br/perfume/Lattafa-Perfumes/Yara-76880.html"}')
    assert d["notas_fundo"] == "Baunilha, Almíscar" and d["link"].startswith("https://www.fragrantica.com.br/")
    assert decants.notas_do_texto('{"perfume": "X", "link": "https://golpe.com"}') == {}           # sem notas não vale
    assert decants.notas_do_texto('{"notas_topo": "a", "link": "https://golpe.com/x"}')["link"] == ""
    leg = decants.legenda_limpa("Sinta a baunilha 🍦\nLeve por R$ 29,90 no tamanho 5ml!\nExperimente antes de comprar o frasco.")
    assert not any(c.isdigit() for c in leg) and "Experimente antes" in leg
    # post do decant com legenda e notas, preço do sistema
    r = Repo()
    y = decants.planilha(ITENS, decants.config(r), {})["itens"][0]
    y.update(legenda="Uma baunilha cremosa que abraça 🤍", notas={"notas_topo": "Orquídea", "notas_coracao": "Gourmand", "notas_fundo": "Baunilha"},
             fotos=["bazar/decant/Y/foto-1.jpg", "bazar/decant/Y/foto-2.jpg"], videos=["bazar/decant/Y/video-1.mp4"])
    p = bazar.decant_ao_bazar(r, y)
    t = bazar.post(p)
    assert "Uma baunilha cremosa que abraça 🤍" in t and "🌳 Fundo: Baunilha" in t and "🧪 5 ml por R$ 32,20" in t
    assert p["foto"] == "bazar/decant/Y/foto-1.jpg" and p["video"] == "bazar/decant/Y/video-1.mp4" and len(p["fotos"]) == 2
    # até 3 fotos guardadas no cadastro do decant; caminho de fora é recusado
    decants.salvar_item(r, {"sku": "YARA100", "fotos": [f"bazar/decant/Y/f{i}.jpg" for i in range(5)]})
    assert len(decants.itens_extra(r)["YARA100"]["fotos"]) == 3 and decants.itens_extra(r)["YARA100"]["foto"] == "bazar/decant/Y/f0.jpg"
    try:
        decants.salvar_item(r, {"sku": "YARA100", "videos": ["sala/../x.mp4"]})
        raise AssertionError("aceitou caminho de fora")
    except decants.ErroDecant:
        pass


def test_tela():
    import subprocess
    import time
    import urllib.parse
    import urllib.request
    from playwright.sync_api import sync_playwright
    r = Repo()

    def planilha():
        p = decants.planilha(ITENS, decants.config(r), decants.itens_extra(r))
        nb = {x.get("sku"): x["codigo"] for x in bazar.produtos(r) if x.get("aba") == "decant"}
        for x in p["itens"]:
            x["bazar"] = nb.get(x["sku"])
        return p

    def api(rota):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(rota.request.url).query)
        nome = qs["r"][0]
        d = json.loads(rota.request.post_data_buffer or b"{}") if rota.request.method == "POST" else {}
        if nome == "decants":
            out = planilha()
            for x in out["itens"]:
                x.setdefault("notas", None)
        elif nome == "decants_config":
            out = {"ok": True, "config": decants.salvar_config(r, d)}
        elif nome == "decants_item":
            out = {"ok": True, "item": decants.salvar_item(r, d)}
        elif nome == "decants_bazar":
            linha = next(x for x in planilha()["itens"] if x["sku"] == d["sku"])
            decants.salvar_item(r, {"sku": d["sku"], "tamanhos_bazar": d["tamanhos"]})
            linha = dict(linha, decants=[x for x in linha["decants"] if x["ml"] in d["tamanhos"]])
            out = {"ok": True, "produto": bazar.decant_ao_bazar(r, linha)}
        elif nome == "bazar":
            out = bazar.painel(r)
        elif nome == "bazar_post":
            out = {"texto": bazar.post(next(x for x in bazar.painel(r)["produtos"] if x["id"] == int(qs["id"][0])))}
        else:
            return rota.fulfill(status=404, content_type="application/json", body=json.dumps({"erro": nome}))
        rota.fulfill(content_type="application/json", body=json.dumps(out))

    aqui = RAIZ / "testes" / "servidor_teste"
    porta = os.environ.get("PORTA_DC", "8832")
    srv = subprocess.Popen([sys.executable, "-W", "ignore", str(aqui / "servidor.py")],
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
                pg.route("**/api/app?r=decants*", api)
                pg.route("**/api/app?r=bazar*", api)
                pg.goto(f"http://127.0.0.1:{porta}/#/decants")
                pg.wait_for_selector(".dc-tab tbody tr", timeout=15000)
                txt = pg.inner_text("#main")
                assert ("R$ 66,70" in txt and "R$ 32,20" in txt) if nome == "pc" else "R$ 57,00" in txt, txt[:600]
                if nome == "pc":
                    pg.fill("#dc-markup", "2")
                    pg.click("#dc-salvar")
                    pg.wait_for_function("document.querySelector('.dc-tab').innerText.includes('R$ 58,00')", timeout=8000)   # 29,00 × 2
                    i = pg.locator("[data-dcins='adesivo'][data-sku='YARA100']")
                    i.fill("0")
                    i.dispatch_event("change")
                    pg.wait_for_function("document.querySelector('.dc-tab').innerText.includes('R$ 57,00')", timeout=8000)   # 28,50 × 2
                    assert decants.itens_extra(r)["YARA100"]["adesivo"] == 0
                    pg.wait_for_timeout(800)                                  # a tabela termina de redesenhar
                    pg.locator("[data-dcvol='ASAD']").fill("100")
                    pg.locator("[data-dcvol='ASAD']").dispatch_event("change")
                    pg.wait_for_function("document.querySelector('.dc-tab').innerText.includes('Asad')", timeout=8000)
                    pg.screenshot(path=str(RAIZ / "testes" / "saida_decants_pc.png"))
                    pg.locator("[data-dccad='YARA100']").first.click()
                    pg.wait_for_selector("#dcc-fotos .dc-slot", timeout=5000)
                    assert pg.locator("#dcc-fotos .dc-slot.vazio").count() == 3 and pg.locator("#dcc-videos .dc-slot.vazio").count() == 3
                    pg.fill("#dcc-leg", "Uma baunilha que abraça")
                    pg.click("#dcc-salvar")
                    pg.wait_for_function("document.querySelector('.dc-tab') && document.querySelector('.dc-tab').innerText.includes('legenda')", timeout=8000)
                    assert decants.itens_extra(r)["YARA100"]["legenda"] == "Uma baunilha que abraça"
                    pg.locator("[data-dcbz='YARA100']").click()
                    pg.wait_for_selector(".dc-tam", timeout=5000)
                    assert pg.locator(".dc-tam").count() == 3
                    pg.locator(".dc-tam input[value='5']").uncheck()
                    pg.locator(".dc-tam input[value='10']").uncheck()
                    pg.screenshot(path=str(RAIZ / "testes" / "saida_decants_tamanhos.png"))
                    pg.click("#dct-ok")
                    pg.wait_for_selector(".bz-tab tbody tr", timeout=8000)
                    assert "#/bazar/decant" in pg.url and "🧪 DECANT" in pg.inner_text("#main")
                    pg.locator("[data-bzsh]").first.click()
                    pg.wait_for_selector("#bzc-txt", timeout=5000)
                    t = pg.input_value("#bzc-txt")
                    assert t.startswith("✨ DECANT NA PURE PERFUMARIA! ✨") and "15 ml" in t and "5 ml" not in t.replace("15 ml", ""), t
                    assert decants.itens_extra(r)["YARA100"]["tamanhos_bazar"] == [15]
                    pg.wait_for_timeout(400)
                    pg.screenshot(path=str(RAIZ / "testes" / "saida_decants_arte.png"))
                    pg.click(".modal [data-fechar]")
                    pg.goto(f"http://127.0.0.1:{porta}/#/decants")
                    pg.wait_for_selector(".dc-tab tbody tr", timeout=8000)
                larg = pg.evaluate("document.documentElement.scrollWidth")
                assert larg <= wd + 2, f"{nome}: rolagem lateral ({larg}px)"
                pg.screenshot(path=str(RAIZ / "testes" / f"saida_decants_{nome}.png"))
                assert not erros, erros
            b.close()
    finally:
        srv.terminate()


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)


def test_ficha_pelo_gemini_vai_para_perfume_fichas():
    import nubi_web
    import ia

    class R:
        def __init__(self):
            self.fichas = []

        def _req(self, metodo, tabela, params=None, corpo=None, prefer=None):
            assert tabela == "perfume_fichas"
            if metodo == "GET":
                return [f for f in self.fichas if f["chave"] == params["chave"][3:]]
            if metodo == "POST":
                self.fichas.append(dict(corpo[0], id=1))
                return [self.fichas[-1]]
    pedidos = []
    antes = ia.gemini_texto
    ia.gemini_texto = lambda pergunta, **k: (pedidos.append(pergunta) or (
        '{"perfume": "Yara", "familia": "Âmbar", "notas_topo": "Orquídea", "notas_coracao": "Gourmand", "notas_fundo": "Baunilha",'
        ' "link": "https://www.fragrantica.com/perfume/Lattafa/Yara.html"}', ["https://www.fragrantica.com/perfume/Lattafa/Yara.html"]))
    try:
        r = R()
        f = nubi_web._ficha_decant(r, "Perfume Lattafa Yara EDP 100ml Feminino")
        assert f["notas_fundo"] == "Baunilha" and f["fontes"][0]["url"].startswith("https://www.fragrantica.com/")
        assert "Fragrantica" in pedidos[0] and "Lattafa Yara EDP Feminino" in pedidos[0]
        nubi_web._ficha_decant(r, "Perfume Lattafa Yara EDP 100ml Feminino")      # já tem: não pesquisa de novo
        assert len(pedidos) == 1 and len(r.fichas) == 1
    finally:
        ia.gemini_texto = antes


if __name__ == "__main__":
    test_ficha_pelo_gemini_vai_para_perfume_fichas()
    print("ok test_ficha_pelo_gemini_vai_para_perfume_fichas")
