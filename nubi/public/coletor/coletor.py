# -*- coding: utf-8 -*-
"""
Coletor do Nubimetrics — roda no Mac mini, abre o Nubimetrics com o seu login já feito,
baixa os relatórios e manda para o nubi (https://nubi-explorador.vercel.app).

  Vendedores seguidos (grupo "perfumes"): o export de anúncios de cada vendedor, mês fechado.
  Relatório MARCAS: o ranking de marcas do mês fechado da categoria (Perfumes).

Instalação no Mac: curl -fsSL https://nubi-explorador.vercel.app/coletor/instalar.sh | bash
Depois, os comandos ficam em ~/.nubi-coletor/coletor (ex.: ~/.nubi-coletor/coletor status):
  python coletor.py configurar      e-mail e senha do NUBI (guardados no Chaveiro do Mac)
  python coletor.py entrar          abre o navegador para você fazer login no Nubimetrics
  python coletor.py diario          o que o agendamento roda todo dia (só baixa o que falta)
  python coletor.py vendedores [--mes AAAA-MM] [--parcial] [--so NOME] [--sem-enviar]
  python coletor.py marcas [--mes AAAA-MM] [--sem-enviar]
  python coletor.py status          última coleta e o que já está no nubi
  python coletor.py atualizar       baixa a versão mais nova do coletor
  (qualquer coleta aceita --ver para mostrar a janela do navegador e acompanhar)

Os caminhos, botões e endereços do Nubimetrics seguem o mapeamento feito com o Claude do
navegador (URLs diretas, ids e aria-labels estáveis; os ids gerados pelo MUI mudam a cada
carga e não são usados).
"""

import argparse
import calendar
import getpass
import json
import os
import re
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = os.environ.get("NUBIMETRICS_URL", "https://app.nubimetrics.com")
NUBI = os.environ.get("NUBI_URL", "https://nubi-explorador.vercel.app")
SUPABASE_URL = "https://ivsmadbyzbmugwfadwtg.supabase.co"
SUPABASE_KEY = "sb_publishable_hlLuzIP8GMxjwTfY-otJQQ_LbMPm7Yt"     # chave pública (a mesma da página)
PASTA = Path(os.environ.get("NUBI_COLETOR_DIR", Path.home() / ".nubi-coletor"))
CONFIG = PASTA / "config.json"
SESSAO = PASTA / "sessao.json"          # cookies do Nubimetrics (inclusive os "de sessão", que o Chrome apaga ao fechar)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/140.0.0.0 Safari/537.36")
SERVICO_CHAVEIRO = "nubi-coletor"
PAUSA = float(os.environ.get("NUBI_COLETOR_PAUSA", "4"))           # segundos entre vendedores

PADRAO_CONFIG = {
    "nubi_email": "",
    "grupo": "460388",                       # grupo "perfumes" no Nubimetrics
    "categoria": "MLB1246-MLB6284",          # Beleza e Cuidado Pessoal > Perfumes
    "categoria_nomes": ["Beleza e Cuidado Pessoal", "Perfumes"],
    "mes_atual": False,                      # baixar também o mês em andamento (parcial), todo dia
    "mostrar_navegador": False,
    "hashes": {},                            # hash do vendedor -> {nome, primeiro, ultimo} (conferir estabilidade)
    "hash_por_nome": {},                     # apelido -> hash (se mudar, o hash não é estável)
}
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
         "Setembro", "Outubro", "Novembro", "Dezembro"]
OFUSCADO = re.compile(r"^[A-Z]+\.[A-Z]+\.[A-Z]+$")                   # BANTENG.PRETO.DEMONSTRATIVO
ESCONDER = "#intercom-container, .intercom-lightweight-app, .intercom-launcher {display: none !important}"


class Falha(Exception):
    pass


class SessaoExpirada(Falha):
    pass


# ---------------------------------------------------------------------------
# Configuração, registro e avisos
# ---------------------------------------------------------------------------

LOG = []


def log(msg):
    linha = f"{datetime.now():%H:%M:%S} {msg}"
    LOG.append(linha)
    print(linha, flush=True)
    try:
        PASTA.mkdir(parents=True, exist_ok=True)
        with open(PASTA / "coletor.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d} {linha}\n")
    except OSError:
        pass


def ler_config():
    cfg = dict(PADRAO_CONFIG)
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    if not str(cfg.get("grupo") or "").isdigit():      # ex.: alguém respondeu "sim" na pergunta do grupo
        cfg["grupo"] = PADRAO_CONFIG["grupo"]
    return cfg


def salvar_config(cfg):
    PASTA.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def aviso_mac(titulo, texto):
    """Notificação na tela do Mac (só avisa; não faz nada em outros sistemas)."""
    if sys.platform != "darwin":
        return
    t = texto.replace('"', "'")[:200]
    subprocess.run(["osascript", "-e", f'display notification "{t}" with title "{titulo}"'], check=False)


# ---------------------------------------------------------------------------
# Login no nubi (para enviar os arquivos)
# ---------------------------------------------------------------------------

def senha_chaveiro(email):
    if os.environ.get("NUBI_SENHA"):
        return os.environ["NUBI_SENHA"]
    if sys.platform != "darwin":
        return ""
    r = subprocess.run(["security", "find-generic-password", "-s", SERVICO_CHAVEIRO, "-a", email, "-w"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def token_nubi(cfg):
    if os.environ.get("NUBI_TOKEN"):                   # testes
        return os.environ["NUBI_TOKEN"]
    email = cfg.get("nubi_email") or ""
    senha = senha_chaveiro(email)
    if not email or not senha:
        raise Falha("Login do nubi não configurado. Rode: python coletor.py configurar")
    req = urllib.request.Request(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        data=json.dumps({"email": email, "password": senha}).encode(),
        headers={"apikey": SUPABASE_KEY, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())["access_token"]
    except urllib.error.HTTPError as e:
        raise Falha(f"Login no nubi recusado ({e.code}). Rode de novo: python coletor.py configurar")


def api(token, rota, params=None, corpo=None, metodo=None):
    q = urllib.parse.urlencode(dict(params or {}, r=rota))
    dados = corpo if isinstance(corpo, (bytes, type(None))) else json.dumps(corpo).encode()
    req = urllib.request.Request(f"{NUBI}/api/app?{q}", data=dados, method=metodo or ("POST" if dados else "GET"),
                                 headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode()).get("erro")
        except Exception:  # noqa: BLE001
            msg = None
        raise Falha(msg or f"nubi respondeu {e.code}")


# ---------------------------------------------------------------------------
# Navegador
# ---------------------------------------------------------------------------

def abrir_navegador(p, cfg, visivel=None):
    """Chrome com perfil próprio e persistente: o login do Nubimetrics fica salvo nele."""
    if visivel is None:
        visivel = bool(cfg.get("mostrar_navegador") or os.environ.get("NUBI_VER"))
    opcoes = dict(user_data_dir=str(PASTA / "perfil"), headless=not visivel, accept_downloads=True,
                  viewport={"width": 1500, "height": 950}, locale="pt-BR", user_agent=UA,
                  args=["--disable-blink-features=AutomationControlled"],
                  ignore_default_args=["--enable-automation"])
    exe = os.environ.get("NUBI_CHROMIUM")
    ctx = None
    if exe:
        opcoes["executable_path"] = exe
    else:
        try:                                        # prefere o Google Chrome instalado no Mac
            ctx = p.chromium.launch_persistent_context(channel="chrome", **opcoes)
        except Exception:  # noqa: BLE001
            ctx = None
    ctx = ctx or p.chromium.launch_persistent_context(**opcoes)
    if SESSAO.exists():                             # devolve os cookies de sessão do último login
        try:
            ctx.add_cookies(json.loads(SESSAO.read_text(encoding="utf-8")).get("cookies", []))
        except Exception as e:  # noqa: BLE001
            log(f"(não consegui restaurar a sessão salva: {e})")
    return ctx


def guardar_sessao(ctx):
    try:
        ctx.storage_state(path=str(SESSAO))
        os.chmod(SESSAO, 0o600)
    except Exception:  # noqa: BLE001
        pass


def diagnostico(pg):
    """Onde a página parou (sem a parte da URL com parâmetros) + foto da tela."""
    foto = PASTA / "ultimo-erro.png"
    try:
        pg.screenshot(path=str(foto), full_page=True)
    except Exception:  # noqa: BLE001
        foto = None
    try:
        titulo = pg.title()
    except Exception:  # noqa: BLE001
        titulo = ""
    u = urllib.parse.urlparse(pg.url)
    return f"[parou em {u.netloc}{u.path} · título '{titulo[:60]}'" + (f" · foto: {foto}]" if foto else "]")


def conferir_sessao(pg):
    """Sessão expirada: o Nubimetrics manda para a tela de login."""
    caminho = urllib.parse.urlparse(pg.url).path          # só o caminho: a tela de login leva o destino na query
    if not caminho.startswith(("/competition", "/market")):
        raise SessaoExpirada("O Nubimetrics pediu login de novo. No Mac mini, rode: "
                             "~/.nubi-coletor/coletor entrar " + diagnostico(pg))


def ir(pg, url, esperar):
    pg.goto(url, wait_until="domcontentloaded", timeout=90000)
    try:
        pg.wait_for_selector(esperar, timeout=60000)
    except Exception:  # noqa: BLE001
        conferir_sessao(pg)
        raise Falha(f"a página não carregou o esperado ({esperar}) " + diagnostico(pg))
    conferir_sessao(pg)
    try:
        pg.add_style_tag(content=ESCONDER)          # chat do Intercom pode cobrir botões
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Períodos
# ---------------------------------------------------------------------------

def mes_anterior(hoje=None):
    hoje = hoje or date.today()
    d = hoje.replace(day=1) - timedelta(days=1)
    return f"{d.year}-{d.month:02d}"


def limites(mes):
    a, m = map(int, mes.split("-"))
    return f"{mes}-01", f"{mes}-{calendar.monthrange(a, m)[1]:02d}"


# ---------------------------------------------------------------------------
# Fluxo 1 — vendedores seguidos
# ---------------------------------------------------------------------------

def limpar_nome(txt):
    """Nome do vendedor na tabela, sem ícones (lápis, lupa) e espaços sobrando."""
    linhas = [l.strip() for l in (txt or "").splitlines() if l.strip()]
    nome = linhas[0] if linhas else ""
    nome = re.sub(r"^[^\w]+|[^\w)]+$", "", nome)
    return re.sub(r"\s+", " ", nome).upper()


def listar_vendedores(pg, cfg):
    """Nome e hash de cada vendedor do grupo (tabela paginada, 10 por página)."""
    ir(pg, f"{BASE}/competition/dashboardbycompetitor?group={cfg['grupo']}&range=PREVMONTH",
       'td a[aria-label="Analise um concorrente"]')
    vistos, pagina = {}, 1
    while True:
        pg.wait_for_selector('td a[aria-label="Analise um concorrente"]', timeout=60000)
        for a in pg.locator('td a[aria-label="Analise um concorrente"]').all():
            nome = limpar_nome(a.evaluate("a => { const td = a.closest('td'); const c = td.cloneNode(true);"
                                          " c.querySelectorAll('a, svg, button, img').forEach(x => x.remove());"
                                          " return c.innerText; }"))
            href = a.get_attribute("href") or ""
            if "seller=" not in href:               # link sem href: abre nova aba ao clicar
                with pg.context.expect_page() as nova:
                    a.click()
                aba = nova.value
                aba.wait_for_load_state("domcontentloaded")
                href = aba.url
                aba.close()
            h = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("seller", [""])[0]
            if h:
                vistos[h] = nome
        prox = pg.locator('button[aria-label="Go to next page"]')
        if prox.count() == 0 or prox.first.is_disabled():
            break
        antes = pg.locator("td").first.inner_text()
        prox.first.click()
        pagina += 1
        pg.wait_for_function("t => document.querySelector('td') && document.querySelector('td').innerText !== t",
                             arg=antes, timeout=30000)
    log(f"Vendedores no grupo: {len(vistos)} ({pagina} página(s))")
    avisos = []
    hoje = date.today().isoformat()
    hs, por_nome = cfg.setdefault("hashes", {}), cfg.setdefault("hash_por_nome", {})
    for h, nome in vistos.items():
        x = hs.setdefault(h, {"nome": nome, "primeiro": hoje})
        x.update(nome=nome, ultimo=hoje)
        if OFUSCADO.match(nome):
            avisos.append(f"{nome} está com nome aleatório: dê um apelido a ele no Nubimetrics (ícone de lápis)")
        elif por_nome.get(nome) and por_nome[nome] != h:
            avisos.append(f"o hash de {nome} mudou desde {hs.get(por_nome[nome], {}).get('ultimo', '?')}: "
                          "o nubi vai reconhecê-lo pelos anúncios")
        if not OFUSCADO.match(nome):
            por_nome[nome] = h
    for a in avisos:
        log("  ⚠ " + a)
    return list(vistos.items()), avisos


def baixar_vendedor(pg, h, ini, fim, rng, destino):
    url = (f"{BASE}/competition/analysisbycompetitor?seller={h}&range={rng}&category="
           f"&from={ini}&to={fim}")
    ir(pg, url, "button#tab-1")
    with pg.expect_response(lambda r: "analysisitems" in r.url and f"from={ini}" in r.url, timeout=120000) as resp:
        pg.click("button#tab-1")
    if not resp.value.ok:
        raise Falha(f"a lista de anúncios não carregou ({resp.value.status})")
    pg.wait_for_selector("#dashboardByCompetitor_exportBtn_table", timeout=60000)
    pg.wait_for_function("() => document.querySelectorAll('table tbody tr').length > 0", timeout=60000)
    time.sleep(1.5)                                  # a tabela termina de desenhar
    with pg.expect_download(timeout=120000) as d:
        pg.click("#dashboardByCompetitor_exportBtn_table")
    dl = d.value
    arq = destino / dl.suggested_filename           # nome = vendedor na tela; não renomear
    dl.save_as(str(arq))
    if arq.stat().st_size < 3000:
        raise Falha(f"arquivo vazio ou incompleto ({arq.name})")
    return arq


def coletar_vendedores(p, cfg, token, mes=None, parcial=False, so=None, enviar=True, pular=None, avisos=None):
    hoje = date.today()
    if parcial:
        mes = f"{hoje.year}-{hoje.month:02d}"
        ontem = hoje - timedelta(days=1)
        if ontem.month != hoje.month:
            log("Dia 1º: ainda não há mês atual para baixar.")
            return 0, 0, 0
        ini, fim, rng, ate = f"{mes}-01", ontem.isoformat(), "CUSTOM", ontem.isoformat()
    else:
        mes = mes or mes_anterior()
        ini, fim = limites(mes)
        rng = "PREVMONTH" if mes == mes_anterior() else "CUSTOM"
        ate = None
    destino = PASTA / "arquivos" / (mes + ("-parcial" if parcial else ""))
    destino.mkdir(parents=True, exist_ok=True)
    ctx = abrir_navegador(p, cfg)
    arquivos = importados = erros = 0
    try:
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        lista, av = listar_vendedores(pg, cfg)
        if avisos is not None:
            avisos.extend(av)
        salvar_config(cfg)
        manifesto_arq = destino / "manifest.json"
        manifesto = json.loads(manifesto_arq.read_text(encoding="utf-8")) if manifesto_arq.exists() else []
        for h, nome in lista:
            if so and so.upper() != nome.upper():
                continue
            if pular and pular(h, nome):
                log(f"  {nome}: {mes} já está no nubi")
                continue
            try:
                arq = baixar_vendedor(pg, h, ini, fim, rng, destino)
                arquivos += 1
                log(f"  {nome}: baixado {arq.name} ({arq.stat().st_size // 1024} KB)")
                manifesto = [m for m in manifesto if m["arquivo"] != arq.name] + [{
                    "arquivo": arq.name, "nome_exibido": nome, "seller_hash": h, "mes": mes, "ate": ate,
                    "baixado_em": datetime.now(timezone.utc).isoformat()}]
                manifesto_arq.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
                if enviar:
                    # nome do arquivo = nome exibido; o hash é a identidade do vendedor no nubi
                    params = {"arquivo": arq.name, "mes": mes, "seller_hash": h}
                    if ate:
                        params["ate"] = ate
                    r = api(token, "vend_importar", params, arq.read_bytes())
                    importados += 1
                    log("    " + " ".join(r.get("log", [])))
            except SessaoExpirada:
                raise
            except Exception as e:  # noqa: BLE001
                erros += 1
                log(f"  {nome}: ERRO {e}")
            time.sleep(PAUSA)
        guardar_sessao(ctx)
    finally:
        salvar_config(cfg)
        ctx.close()
    return arquivos, importados, erros


# ---------------------------------------------------------------------------
# Fluxo 2 — relatório MARCAS mensal
# ---------------------------------------------------------------------------

def coletar_marcas(p, cfg, token, mes=None, enviar=True):
    mes = mes or mes_anterior()
    a, m = map(int, mes.split("-"))
    rotulo_mes = f"{MESES[m - 1]} {a}"
    cat = cfg["categoria"]
    nivel1, nivel2 = cat.split("-")[:2]
    destino = PASTA / "arquivos" / mes
    destino.mkdir(parents=True, exist_ok=True)
    ctx = abrir_navegador(p, cfg)
    try:
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        ir(pg, f"{BASE}/market/sellerranking#?range={mes}-01", "button#simple-tab-3")
        # mês: o botão do calendário tem que mostrar o mês certo
        cal = pg.locator("button.calendar-btn").first
        if rotulo_mes.lower() not in cal.inner_text().lower():
            cal.click()
            pg.locator("ul.dropdown-menu li a", has_text=rotulo_mes).first.click()
            pg.wait_for_function("t => document.querySelector('button.calendar-btn').innerText.toLowerCase()"
                                 ".includes(t)", arg=rotulo_mes.lower(), timeout=30000)
        # categoria: os botões têm que mostrar Beleza e Cuidado Pessoal / Perfumes
        botoes = pg.locator("div.dropdown-category button.dropdown-toggle")
        textos = " | ".join(botoes.all_inner_texts())
        if not all(n.lower() in textos.lower() for n in cfg["categoria_nomes"]):
            log(f"  Categoria na tela: {textos!r}; escolhendo {cat}")
            botoes.nth(0).click()
            pg.locator(f'a[data-id="{nivel1}"]').first.click()
            time.sleep(2)
            botoes.nth(1).click()
            pg.locator(f'a[data-id="{nivel2}"][data-parent="{nivel1}"]').first.click()
            time.sleep(2)
            textos = " | ".join(botoes.all_inner_texts())
            if not all(n.lower() in textos.lower() for n in cfg["categoria_nomes"]):
                raise Falha(f"não consegui escolher a categoria (tela mostra: {textos})")
        # aba MARCAS
        def e_ranking(r, limite=None):
            u = urllib.parse.unquote(r.url)
            return ("ranking/tree" in u and "Topic=brands" in u and f"Date={mes}-01" in u
                    and f"CategoryPath={cat}" in u and (limite is None or f"Limit={limite}" in u))
        with pg.expect_response(lambda r: e_ranking(r), timeout=120000):
            pg.click("button#simple-tab-3")
        # 100 linhas por página (o export sai da tabela carregada)
        seletor = pg.locator('[role="combobox"], [aria-haspopup="listbox"]').filter(has_text=re.compile(r"^\s*10\s*$")).first
        if seletor.count():
            with pg.expect_response(lambda r: e_ranking(r, 100), timeout=120000):
                seletor.click()
                pg.locator('li[role="option"][data-value="100"]').click()
        pg.wait_for_function("() => document.querySelectorAll('table tbody tr').length > 0", timeout=60000)
        time.sleep(1.5)
        with pg.expect_download(timeout=120000) as d:
            pg.locator("button", has_text="EXPORTAR").last.click()
        dl = d.value
        nome = dl.suggested_filename
        if not re.search(r"MARCAS.*\d{4}-\d{2}", nome, re.I):
            nome = f"MARCAS-{cat}-{mes}-01.xlsx"
        arq = destino / nome
        dl.save_as(str(arq))
        log(f"  MARCAS {mes}: baixado {arq.name} ({arq.stat().st_size // 1024} KB)")
        guardar_sessao(ctx)
        if enviar:
            r = api(token, "ranking_importar", {"arquivo": arq.name, "categoria": cat, "mes": mes}, arq.read_bytes())
            log("    " + " ".join(r.get("log", [])))
            return 1, 1, 0
        return 1, 0, 0
    finally:
        ctx.close()


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

def registrar(token, tarefa, inicio, ok, arquivos, importados, erros, mensagem):
    if not token:
        return
    try:
        api(token, "coletor_registrar", corpo={
            "iniciado_em": inicio.isoformat(), "terminado_em": datetime.now(timezone.utc).isoformat(),
            "tarefa": tarefa, "ok": ok, "arquivos": arquivos, "importados": importados, "erros": erros,
            "mensagem": mensagem, "log": "\n".join(LOG)})
    except Exception as e:  # noqa: BLE001
        log(f"(não consegui registrar a coleta no nubi: {e})")


def cmd_configurar(args, cfg):
    print("Login do NUBI: o MESMO e-mail e senha que você usa em nubi-explorador.vercel.app")
    print("(não é o login do Nubimetrics; esse vem no próximo passo).")
    for tentativa in range(3):
        padrao = cfg.get("nubi_email") or ""
        email = (input(f"E-mail do nubi{f' [{padrao}]' if padrao else ''}: ").strip() or padrao).lower()
        senha = getpass.getpass("Senha do nubi: ")
        if sys.platform == "darwin":
            subprocess.run(["security", "add-generic-password", "-U", "-s", SERVICO_CHAVEIRO, "-a", email,
                            "-w", senha], check=True)
        else:
            os.environ["NUBI_SENHA"] = senha
        cfg["nubi_email"] = email
        salvar_config(cfg)
        try:
            token_nubi(cfg)
            break
        except Falha:
            print("  E-mail ou senha do nubi não conferem. Use o login da página nubi-explorador.vercel.app"
                  " (se esqueceu a senha, peça uma nova).")
    else:
        print("Não consegui entrar no nubi. Rode de novo depois: ~/.nubi-coletor/coletor configurar")
        return 1
    grupo = input(f"Número do grupo de vendedores no Nubimetrics (Enter para manter {cfg['grupo']}): ").strip()
    if grupo.isdigit():
        cfg["grupo"] = grupo
    elif grupo:
        print(f"  '{grupo}' não é um número; mantive o grupo {cfg['grupo']}.")
    salvar_config(cfg)
    print("OK: login do nubi conferido e guardado no Chaveiro do Mac.")


def testar_sessao(p, cfg, visivel):
    ctx = abrir_navegador(p, cfg, visivel=visivel)
    try:
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        ir(pg, f"{BASE}/competition/dashboardbycompetitor?group={cfg['grupo']}&range=PREVMONTH",
           'td a[aria-label="Analise um concorrente"]')
        guardar_sessao(ctx)
        return True, ""
    except Falha as e:
        return False, str(e)
    finally:
        ctx.close()


def cmd_entrar(args, cfg):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = abrir_navegador(p, cfg, visivel=True)
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto(f"{BASE}/competition/dashboardbycompetitor?group={cfg['grupo']}&range=PREVMONTH")
        print("Faça login no Nubimetrics na janela que abriu (marque 'lembrar', se houver).")
        print("Quando a tela de Grupo de vendedores aparecer, o login fica salvo e a janela fecha.")
        fim, ok = time.time() + 600, False
        while time.time() < fim:
            if pg.locator('td a[aria-label="Analise um concorrente"]').count():
                ok = True
                break
            time.sleep(2)
        if ok:
            time.sleep(3)
            guardar_sessao(ctx)
        ctx.close()
        if not ok:
            print("Tempo esgotado (10 min) sem ver a tela de vendedores.")
            return 1
        print("OK: login feito. Testando se o coletor consegue entrar sozinho, sem janela…")
        ok, erro = testar_sessao(p, cfg, visivel=False)
        if ok:
            cfg["mostrar_navegador"] = False
            print("OK: funciona sem janela. As coletas vão rodar em segundo plano.")
        else:
            print(f"  Sem janela o Nubimetrics não aceitou ({erro[:160]}).")
            print("  Testando com a janela do navegador aberta (ela aparece e some sozinha durante a coleta)…")
            ok, erro = testar_sessao(p, cfg, visivel=True)
            if ok:
                cfg["mostrar_navegador"] = True
                print("OK: com janela funciona. As coletas vão abrir o navegador por alguns minutos e fechar sozinhas.")
            else:
                print(f"  Também não entrou com janela: {erro}")
                print("  Me mande esta mensagem e a foto ~/.nubi-coletor/ultimo-erro.png.")
        salvar_config(cfg)
        return 0 if ok else 1


def cmd_status(args, cfg):
    token = token_nubi(cfg)
    st = api(token, "coletor_status")
    for e in st["execucoes"][:5]:
        print(f"{e['iniciado_em'][:16]}  {e['tarefa']:<10} {'ok ' if e['ok'] else 'ERRO'}  "
              f"{e['importados'] or 0}/{e['arquivos'] or 0} importados  {e['mensagem'] or ''}")


def executar(tarefa, func):
    """Roda uma coleta com registro no nubi e aviso no Mac em caso de erro."""
    cfg = ler_config()
    inicio = datetime.now(timezone.utc)
    token = None
    try:
        token = token_nubi(cfg)
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            arquivos, importados, erros, msg = func(p, cfg, token)
        ok = erros == 0
        log(("OK: " if ok else "Terminou com erros: ") + msg)
        registrar(token, tarefa, inicio, ok, arquivos, importados, erros, msg)
        if not ok:
            aviso_mac("Coletor nubi", msg)
        return 0 if ok else 1
    except Exception as e:  # noqa: BLE001
        msg = str(e) if isinstance(e, Falha) else f"{e.__class__.__name__}: {e}"
        log("FALHOU: " + msg)
        if not isinstance(e, Falha):
            log(traceback.format_exc()[-2000:])
        registrar(token, tarefa, inicio, False, 0, 0, 1, msg)
        aviso_mac("Coletor nubi — falhou", msg)
        return 2


def main():
    ap = argparse.ArgumentParser(description="Coletor do Nubimetrics para o nubi")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("configurar")
    sub.add_parser("entrar")
    sub.add_parser("status")
    sub.add_parser("atualizar", help="baixa a versão mais nova do coletor")
    d = sub.add_parser("diario")
    d.add_argument("--ver", action="store_true", help="mostrar a janela do navegador")
    v = sub.add_parser("vendedores")
    v.add_argument("--mes")
    v.add_argument("--parcial", action="store_true", help="mês atual até ontem")
    v.add_argument("--so", help="só este vendedor")
    v.add_argument("--sem-enviar", action="store_true")
    v.add_argument("--ver", action="store_true", help="mostrar a janela do navegador")
    mk = sub.add_parser("marcas")
    mk.add_argument("--mes")
    mk.add_argument("--sem-enviar", action="store_true")
    mk.add_argument("--ver", action="store_true", help="mostrar a janela do navegador")
    args = ap.parse_args()
    cfg = ler_config()
    if getattr(args, "ver", False):
        os.environ["NUBI_VER"] = "1"

    if args.cmd == "configurar":
        return cmd_configurar(args, cfg)
    if args.cmd == "entrar":
        return cmd_entrar(args, cfg)
    if args.cmd == "status":
        return cmd_status(args, cfg)
    if args.cmd == "atualizar":
        novo = urllib.request.urlopen(f"{NUBI}/coletor/coletor.py", timeout=60).read()
        compile(novo, "coletor.py", "exec")               # só troca se o arquivo novo estiver íntegro
        Path(__file__).write_bytes(novo)
        print("OK: coletor atualizado.")
        return 0
    if args.cmd == "vendedores":
        def f(p, cfg, token):
            a, i, e = coletar_vendedores(p, cfg, token, args.mes, args.parcial, args.so, not args.sem_enviar)
            return a, i, e, f"vendedores: {a} baixado(s), {i} importado(s), {e} erro(s)"
        return executar("vendedores", f)
    if args.cmd == "marcas":
        def f(p, cfg, token):
            a, i, e = coletar_marcas(p, cfg, token, args.mes, not args.sem_enviar)
            return a, i, e, f"MARCAS {args.mes or mes_anterior()}: baixado"
        return executar("marcas", f)
    if args.cmd == "diario":
        def f(p, cfg, token):
            mes = mes_anterior()
            pend = api(token, "coletor_pendencias")
            A = I = E = 0
            partes = []
            if mes not in pend["ranking"].get(cfg["categoria"], []):
                try:
                    a, i, e = coletar_marcas(p, cfg, token, mes)
                    partes.append(f"MARCAS {mes} importado")
                except SessaoExpirada:
                    raise
                except Exception as ex:  # noqa: BLE001
                    a, i, e = 0, 0, 1
                    log(f"  MARCAS {mes}: ERRO {ex}")
                    partes.append(f"MARCAS {mes} falhou")
                A, I, E = A + a, I + i, E + e
            # vendedores: mês fechado que falta (ou que ainda está como parcial)
            ja, ja_h = pend["vendedores"], pend.get("hashes", {})

            def pular(h, nome):          # já importado (e não parcial) neste mês
                reg = ja_h.get(h) if h in ja_h else ja.get(nome, {})
                return mes in reg and not reg[mes]
            avisos = []
            a, i, e = coletar_vendedores(p, cfg, token, mes, pular=pular, avisos=avisos)
            A, I, E = A + a, I + i, E + e
            partes.append(f"vendedores {mes}: {i} importado(s)")
            if avisos:
                partes.append(f"{len(avisos)} aviso(s): " + "; ".join(avisos)[:300])
                aviso_mac("Coletor nubi — conferir", avisos[0])
            if cfg.get("mes_atual"):
                a, i, e = coletar_vendedores(p, cfg, token, parcial=True)
                A, I, E = A + a, I + i, E + e
                partes.append(f"mês atual: {i} importado(s)")
            return A, I, E, "; ".join(partes) + (f"; {E} erro(s)" if E else "")
        return executar("diario", f)


if __name__ == "__main__":
    sys.exit(main() or 0)
