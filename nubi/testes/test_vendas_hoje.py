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
 <tbody><tr><td>1</td><td><div>Perfume Ferrari Black 125ml Eau De Toilette</div><div>ESSENCE PRIME [Mercado Libre BR]</div></td><td>10</td><td>2.088,90</td></tr>
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


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
