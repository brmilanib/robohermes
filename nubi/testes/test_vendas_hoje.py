# -*- coding: utf-8 -*-
"""01/10 (Bruno, print de UpSeller → Análises → Visão geral): o coletor lê "Vendas de Hoje" a cada 10 min, o nubi guarda
a cada meia hora e a tela ⚡ Vendas de hoje compara dois dias hora a hora (ex.: 10/10 × 09/09) e mostra os picos.
Rodar: python3 testes/test_vendas_hoje.py, na pasta nubi."""
import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import vendas_hoje as vh  # noqa: E402

spec = importlib.util.spec_from_file_location("coletor", RAIZ / "public" / "coletor" / "coletor.py")
coletor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coletor)
BR = timezone(timedelta(hours=-3))

# a tela do print do Bruno (mesmos textos e números), no formato de cartões e tabelas do UpSeller
PAGINA = """<html><body><div class="tabs"><button>Vendas de Hoje</button><button>Últimos 7 dias</button></div>
<div>Horário do Brasil: 2026-10-01 18:18:09 Moeda: BRL</div>
<div class="row">
 <div class="card"><div class="head"><span>Valor de Vendas Válidas</span></div><div class="v">14.995,73</div>
   <div class="cmp"><div><span>Ontem</span><span>31.678,53 <i>↓-52.7%</i></span></div>
   <div><span>Mesmo período de Ontem</span><span>21.784,16 <i>↓-31.2%</i></span></div></div>
   <div class="pie">100,00% <span>Self Fulfillment 14.725,84</span></div></div>
 <div class="card"><div class="head"><span>Pedidos Válidos</span></div><div class="v">64</div>
   <div class="cmp"><div><span>Ontem</span><span>113 <i>↓-43.4%</i></span></div>
   <div><span>Mesmo período de Ontem</span><span>78 <i>↓-17.9%</i></span></div></div>
   <div class="pie">100,00% <span>Self Fulfillment 63</span></div></div>
</div>
<div class="card"><div class="head"><span>Ranking de Anúncio</span></div><table><thead><tr><th>#</th><th>Produtos</th><th>Unidades Vendidas</th><th>Valor de Vendas</th></tr></thead>
 <tbody><tr><td>1</td><td><img src="https://http2.mlstatic.com/D_Q_NP_ferrari-O.webp"><div>Perfume Ferrari Black 125ml Eau De Toilette</div><div>ESSENCE PRIME [Mercado Libre BR]</div></td><td>10</td><td>2.088,90</td></tr>
 <tr><td>2</td><td><div>Perfume Sabah Al Ward Al Wataniah</div><div>PURE PERFUMARIA [TikTok Shop BR]</div></td><td>6</td><td>608,33</td></tr></tbody></table></div>
<div class="card"><div class="head"><span>Ranking de Loja</span></div><table><thead><tr><th>#</th><th>Loja</th><th>Pedidos</th><th>Valor de Vendas</th></tr></thead>
 <tbody><tr><td>1</td><td><div>ESSENCE PRIME</div><div>[Mercado Libre BR]</div></td><td>43</td><td>6.793,12</td></tr>
 <tr><td>2</td><td><div>PURE PERFUMARIA</div><div>[TikTok Shop BR]</div></td><td>8</td><td>1.118,04</td></tr></tbody></table></div>
</body></html>"""


class Repo:
    def __init__(self):
        self.res = {}

    def _req(self, metodo, tabela, params=None, corpo=None, prefer=None):
        assert tabela == "ia_resumos"
        if metodo == "GET":
            ch = (params or {}).get("chave", "")
            if ch.startswith("like."):
                pre = ch[5:].rstrip("*")
                return [{"chave": k} for k in sorted(self.res, reverse=True) if k.startswith(pre)]
            ch = ch.replace("eq.", "")
            return [{"texto": self.res[ch]}] if ch in self.res else []
        for r in corpo:
            self.res[r["chave"]] = r["texto"]
        return []


def leitura_da_pagina():
    from playwright.sync_api import sync_playwright
    exe = os.environ.get("NUBI_CHROMIUM") or "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe) if os.path.exists(exe) else p.chromium.launch()
        pg = b.new_page()
        pg.set_content(PAGINA)
        x = pg.evaluate(coletor.JS_UPSELLER_HOJE)
        b.close()
    return x


def test_le_a_tela_do_upseller_e_guarda():
    x = leitura_da_pagina()
    r = Repo()
    out = vh.salvar(r, x, agora=datetime(2026, 10, 1, 18, 18, tzinfo=BR))
    assert out["ok"], out
    ag = json.loads(r.res[vh.AGORA])
    assert (ag["valor"], ag["valor_ontem"], ag["valor_ontem_mesmo"]) == (14995.73, 31678.53, 21784.16), ag
    assert (ag["pedidos"], ag["pedidos_ontem"], ag["pedidos_ontem_mesmo"]) == (64, 113, 78), ag
    assert ag["lojas"][0] == {"loja": "ESSENCE PRIME", "plataforma": "Mercado Libre BR", "pedidos": 43.0, "valor": 6793.12}, ag["lojas"]
    assert ag["anuncios"][1]["loja"] == "PURE PERFUMARIA" and ag["anuncios"][1]["plataforma"] == "TikTok Shop BR"
    assert ag["anuncios"][0]["unidades"] == 10 and ag["anuncios"][0]["valor"] == 2088.9
    assert ag["anuncios"][0]["foto"] == "https://http2.mlstatic.com/D_Q_NP_ferrari-O.webp" and ag["anuncios"][1]["foto"] is None   # foto da linha
    assert ag["hora_upseller"].startswith("2026-10-01 18:18")
    d = json.loads(r.res["vendas_hoje|2026-10-01"])
    assert d["pontos"]["18:00"]["valor"] == 14995.73
    # erro (login vencido) fica guardado sem apagar a última leitura boa
    vh.salvar(r, {"erro": "O UpSeller pediu login de novo", "login": True}, agora=datetime(2026, 10, 1, 18, 30, tzinfo=BR))
    ag = json.loads(r.res[vh.AGORA])
    assert ag["valor"] == 14995.73 and ag["login"] and "login" in ag["erro"]
    try:
        vh.salvar(r, {"valor": None, "pedidos": None})
        assert False
    except vh.ErroVendasHoje:
        pass


def _ler(r, quando, valor, pedidos, ontem=None):
    x = {"valor": {"nums": [f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")] + ([ontem] if ontem else [])},
         "pedidos": {"nums": [str(pedidos)]}}
    return vh.salvar(r, x, agora=quando)


def test_meia_hora_comparacao_e_picos():
    r = Repo()
    d1, d2 = datetime(2026, 9, 9, tzinfo=BR), datetime(2026, 10, 10, tzinfo=BR)
    # 09/09: pico às 10h e às 20h
    for h, m, v, p in ((0, 10, 100, 1), (9, 40, 900, 9), (10, 50, 3900, 30), (11, 40, 4500, 35), (19, 45, 6000, 45),
                       (20, 55, 11000, 80), (23, 50, 12000, 90)):
        _ler(r, d1.replace(hour=h, minute=m), v, p)
    # 10/10 até 11h: 10h forte; a 2ª leitura da mesma meia hora troca a 1ª
    for h, m, v, p in ((0, 5, 200, 2), (9, 35, 1000, 10), (10, 5, 2500, 20), (10, 40, 4800, 38), (10, 55, 5200, 40), (11, 2, 5600, 44)):
        _ler(r, d2.replace(hour=h, minute=m), v, p)
    dia = json.loads(r.res["vendas_hoje|2026-10-10"])
    assert dia["pontos"]["10:30"]["valor"] == 5200 and len(dia["pontos"]) == 5
    p = vh.painel(r, "2026-10-10", "2026-09-09", agora=datetime(2026, 10, 10, 11, 5, tzinfo=BR))
    assert p["hora"] == "11:00" and p["ate_agora"]["valor"] == 5600 and p["ate_agora_comparar"]["valor"] == 3900
    ph = {x["hora"]: x for x in p["por_hora"]}
    assert ph[10]["valor"] == 4200 and ph[10]["pedidos"] == 30 and ph[11]["valor"] == 400      # 11h em andamento (parcial)
    assert ph[12]["valor"] is None
    assert p["picos"][0]["hora"] == "10h" and p["picos_comparar"][0]["hora"] == "20h" and p["picos_comparar"][1]["hora"] == "10h"
    # a curva acumulada não inventa nada depois da última leitura
    assert [x["valor"] for x in p["curva"] if x["hora"] in ("09:30", "10:00", "11:00", "11:30")] == [1000, 2500, 5600, None]
    assert p["dias"][:2] == ["2026-10-10", "2026-09-09"]
    # 11/10: o "Ontem" do UpSeller fecha 10/10
    _ler(r, datetime(2026, 10, 11, 0, 3, tzinfo=BR), 50, 1, ontem="18.765,43")
    f = json.loads(r.res["vendas_hoje|2026-10-10"])["total_final"]
    assert f["valor"] == 18765.43
    p = vh.painel(r, "2026-10-10", "2026-09-09", agora=datetime(2026, 10, 11, 0, 5, tzinfo=BR))
    assert p["hora"] == "23:30" and p["curva"][-1]["valor"] == 18765.43 and p["total"]["valor"] == 18765.43
    try:
        vh.painel(r, "10/10/2026")
        assert False
    except vh.ErroVendasHoje:
        pass


def test_pendente():
    r = Repo()
    t = datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)
    assert vh.pendente(r, t)["rodar"]
    _ler(r, t, 10, 1)
    assert not vh.pendente(r, t + timedelta(minutes=5))["rodar"]
    assert vh.pendente(r, t + timedelta(minutes=9))["rodar"]
    assert not vh.pendente(r, t + timedelta(hours=1), ativo=False)["rodar"]


STUB = """window.supabase = { createClient: () => { const sess = {access_token: "TOKEN", user: {id: "u1", email: "brmilani@gmail.com"}};
  return { auth: { getSession: async () => ({data: {session: sess}}), signOut: async () => {}, updateUser: async () => ({}),
    onAuthStateChange: cb => setTimeout(() => cb("INITIAL_SESSION", sess), 0) }, storage: {from: () => ({createSignedUrls: async () => ({data: []})})} }; } };"""


def test_tela():
    from playwright.sync_api import sync_playwright
    r = Repo()
    x = leitura_da_pagina()
    hoje = datetime.now(BR).replace(hour=18, minute=18, second=0, microsecond=0)
    for h, v, p in ((9, 2000, 10), (12, 7000, 30), (15, 11000, 48)):
        _ler(r, (hoje - timedelta(days=1)).replace(hour=h, minute=40), v, p)
    for h, v, p in ((8, 1500, 8), (11, 6000, 26)):
        _ler(r, hoje.replace(hour=h, minute=40), v, p)
    vh.salvar(r, x, agora=hoje)
    painel = vh.painel(r, agora=hoje)
    painel["agora"]["lido_em"] = datetime.now(timezone.utc).isoformat()
    aqui = RAIZ / "testes" / "servidor_teste"
    porta = os.environ.get("PORTA_VH", "8823")
    srv = subprocess.Popen([sys.executable, "-W", "ignore", str(aqui / "servidor.py")],
                           env=dict(os.environ, IA_FALSA="1", OLLAMA_API_KEY="x", OPENAI_API_KEY="x", PORTA=porta),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
                pg.route("**/api/app?r=vendas_hoje*", lambda rt: rt.fulfill(content_type="application/json", body=json.dumps(painel)))
                pg.goto(f"http://127.0.0.1:{porta}/#/analises-vendas/hoje")
                try:
                    pg.wait_for_selector(".vh-kpi", timeout=15000)
                except Exception:
                    raise AssertionError((erros, pg.inner_text("body")[:1500]))
                txt = pg.inner_text("#main")
                assert "Vendas de hoje" in txt and "14.995,73" in txt and "ESSENCE PRIME" in txt and "Picos" in txt, txt[:900]
                assert "Data dupla" not in txt or hoje.day == hoje.month
                assert pg.query_selector("#vh-acum svg path") is not None and pg.locator(".vh-h").count() == 24
                assert "⚡ Vendas de hoje" in pg.inner_text("body")
                larg = pg.evaluate("document.documentElement.scrollWidth")
                assert larg <= wd + 2, f"{nome}: rolagem lateral ({larg}px)"
                pg.screenshot(path=str(RAIZ / "testes" / f"saida_vendas_hoje_{nome}.png"), full_page=True)
                assert not erros, erros
            b.close()
    finally:
        srv.terminate()


def _ler_rk(r, quando, valor, pedidos, anuncios, lojas, ontem=None):
    x = {"valor": {"nums": [f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")] + ([ontem] if ontem else [])},
         "pedidos": {"nums": [str(pedidos)]},
         "anuncios": [["", f"{t}\n{l} [Mercado Libre BR]", str(u), f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")] for t, l, u, v in anuncios],
         "lojas": [["", f"{l}\n[{p}]", str(n), f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")] for l, p, n, v in lojas]}
    return vh.salvar(r, x, agora=quando)


def dados_tv(hoje):
    r = Repo()
    ontem, semana = hoje - timedelta(days=1), hoje - timedelta(days=7)
    _ler(r, semana.replace(hour=14, minute=10), 8000, 40)
    _ler(r, semana.replace(hour=23, minute=50), 18000, 90)
    _ler_rk(r, ontem.replace(hour=10, minute=40), 4000, 20, [("Yara", "PURE", 4, 800), ("Asad", "ESSENCE", 3, 600), ("Club", "AURA", 2, 300)],
            [("ESSENCE PRIME", "Mercado Libre BR", 10, 2000), ("PURE PERFUMARIA", "TikTok Shop BR", 4, 600)])
    _ler(r, ontem.replace(hour=13, minute=40), 9000, 45)
    _ler(r, ontem.replace(hour=14, minute=40), 10000, 50)
    _ler(r, ontem.replace(hour=23, minute=55), 20000, 100)
    _ler(r, hoje.replace(hour=12, minute=40), 5000, 22)
    _ler(r, hoje.replace(hour=13, minute=40), 7000, 30)
    _ler_rk(r, hoje.replace(hour=14, minute=40), 12000, 55, [("Asad", "ESSENCE", 9, 1800), ("Yara", "PURE", 6, 1200), ("Sabah", "PURE", 3, 500)],
            [("ESSENCE PRIME", "Mercado Libre BR", 30, 7000), ("PURE PERFUMARIA", "TikTok Shop BR", 3, 400)], ontem="20.000,00")
    return r


def test_tv_numeros():
    hoje = datetime(2026, 10, 10, tzinfo=BR)
    r = dados_tv(hoje)
    t = vh.tv(r, agora=hoje.replace(hour=14, minute=45))
    assert t["ate_agora"]["valor"] == 12000 and t["ate_ontem"]["valor"] == 10000 and t["ate_semana"]["valor"] == 8000
    assert t["projecao"] == {"valor": 24000.0, "base": "ontem"}                      # 12 mil × (20 mil ÷ 10 mil)
    assert t["ultima_hora"]["hora"] == 13 and t["ultima_hora"]["hoje"] is not None
    c = {x["titulo"]: x for x in t["campeoes"]}
    assert (c["Asad"]["pos"], c["Asad"]["pos_ontem"]) == (1, 2) and (c["Yara"]["pos"], c["Yara"]["pos_ontem"]) == (2, 1)
    assert c["Sabah"]["pos_ontem"] is None                                            # novo no ranking
    l = {x["loja"]: x for x in t["lojas"]}
    assert l["ESSENCE PRIME"]["valor_ontem"] == 2000 and l["PURE PERFUMARIA"]["valor_ontem"] == 600


def test_picos_por_loja_no_banco_e_melhores_horarios():
    """01/10 (Bruno: "gravar todos os picos no banco para identificar os melhores picos de venda de cada loja"): hora sem
    leitura antes não vira pico (o 1º dia começou às 18h e marcava 18h = R$ 15 mil); cada dia vai para vendas_hoje|picos."""
    r = Repo()
    d1 = datetime(2026, 10, 1, tzinfo=BR)
    lj = lambda e, p: [("ESSENCE PRIME", "Mercado Libre BR", 10, e), ("PURE PERFUMARIA", "TikTok Shop BR", 3, p)]
    an = [("Asad", "ESSENCE", 1, 100)]
    _ler_rk(r, d1.replace(hour=18, minute=10), 15000, 66, an, lj(6000, 500))
    _ler_rk(r, d1.replace(hour=18, minute=50), 15100, 66, an, lj(6050, 500))
    _ler_rk(r, d1.replace(hour=19, minute=50), 18650, 70, an, lj(7150, 1100))
    t = vh.painel(r, "2026-10-01", agora=d1.replace(hour=20, minute=0))
    ph = {x["hora"]: x for x in t["por_hora"]}
    assert ph[18]["valor"] is None and ph[18]["acumulado"] == 15100 and ph[19]["valor"] == 3550
    assert [p["hora"] for p in t["picos"]] == ["19h"]
    hist = json.loads(r.res[vh.PICOS])
    lojas = hist["2026-10-01"]["lojas"]
    assert lojas["ESSENCE PRIME · Mercado Libre BR"][19] == 1100 and lojas["ESSENCE PRIME · Mercado Libre BR"][18] is None
    assert lojas["PURE PERFUMARIA · TikTok Shop BR"][19] == 600
    # 2º dia: o melhor horário de cada loja sai da média dos dias guardados
    d2 = d1 + timedelta(days=1)
    _ler_rk(r, d2.replace(hour=18, minute=50), 3000, 10, an, lj(1000, 100))
    _ler_rk(r, d2.replace(hour=19, minute=50), 5000, 15, an, lj(1500, 900))
    m = vh.melhores_horarios(r, 30, "2026-10-03")
    assert m["dias"] == 2 and m["melhores"][0]["hora"] == "19h"
    pure = next(x for x in m["lojas"] if x["loja"] == "PURE PERFUMARIA")
    assert pure["plataforma"] == "TikTok Shop BR" and pure["melhores"][0] == {"hora": "19h", "valor": 700.0}   # (600 + 800) ÷ 2


def test_tv_tela():
    from playwright.sync_api import sync_playwright
    hoje = datetime.now(BR).replace(second=0, microsecond=0)
    hoje = hoje.replace(hour=max(hoje.hour, 15))
    r = dados_tv(hoje)
    t = vh.tv(r, agora=hoje.replace(hour=14, minute=50))
    t["agora"]["lido_em"] = datetime.now(timezone.utc).isoformat()
    sac = {"total": {"precisa_voce": 2, "aprovar": 1, "respondidas_hoje": 40, "sozinho_hoje": 12, "clientes_hoje": 77},
           "tempo_mediano_min": 6, "por_canal": {"shopee": {"precisa_voce": 2}, "tiktok_shop": {"aprovar": 1}},
           "agora": [{"cliente": "Márcia", "desde": datetime.now(timezone.utc).isoformat(), "canal": "shopee"}]}
    aqui = RAIZ / "testes" / "servidor_teste"
    porta = os.environ.get("PORTA_TV", "8824")
    srv = subprocess.Popen([sys.executable, "-W", "ignore", str(aqui / "servidor.py")],
                           env=dict(os.environ, IA_FALSA="1", OLLAMA_API_KEY="x", OPENAI_API_KEY="x", PORTA=porta),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
            for wd, ht, nome in ((1920, 1080, "tv"), (1280, 720, "tv720")):
                pg = b.new_page(viewport={"width": wd, "height": ht})
                erros = []
                pg.on("pageerror", lambda e: erros.append(str(e)))
                pg.route("https://cdn.jsdelivr.net/**", lambda rt: rt.fulfill(content_type="application/javascript", body=STUB))
                pg.route("https://fonts.**", lambda rt: rt.abort())
                pg.route("**/api/app?r=vendas_tv*", lambda rt: rt.fulfill(content_type="application/json", body=json.dumps(t)))
                pg.route("**/api/app?r=atendimento_painel*", lambda rt: rt.fulfill(content_type="application/json", body=json.dumps(sac)))
                pg.goto(f"http://127.0.0.1:{porta}/#/analises-vendas/tv")
                try:
                    pg.wait_for_selector(".tv-k", timeout=15000)
                except Exception:
                    raise AssertionError((erros, pg.inner_text("body")[:1500]))
                pg.wait_for_timeout(1900)                                            # números sobem até o valor (animação)
                txt = pg.inner_text(".tv-tela")
                assert pg.locator(".tv-loja svg.pl-ico[aria-label*=Mercado]").count() >= 1 and pg.locator(".tv-loja svg.pl-ico[aria-label*=TikTok]").count() >= 1   # ícone da plataforma
                assert "AO VIVO" in txt and "12.000,00" in txt and "24.000,00" in txt and "Campeões" in txt and "Márcia" in txt, txt[:900]
                assert pg.locator(".tv-pos.sobe").count() >= 1 and pg.locator(".tv-pos.novo").count() == 1
                assert pg.query_selector("#tv-acum svg path") is not None and pg.locator(".tv-k.sac.alerta").count() == 1
                pg.screenshot(path=str(RAIZ / "testes" / f"saida_vendas_{nome}.png"))
                pg.keyboard.press("Escape")
                pg.wait_for_function("!document.querySelector('.tv-tela')", timeout=5000)
                assert "#/analises-vendas/hoje" in pg.url
                assert not erros, erros
            b.close()
    finally:
        srv.terminate()


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
