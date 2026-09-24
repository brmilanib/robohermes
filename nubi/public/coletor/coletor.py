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
  python coletor.py diario          o que o agendamento roda todo dia: baixa o que falta desde 'desde'
                                    (meses fechados + mês atual até o último dia liberado)
  python coletor.py agendar 7 0     muda o horário da coleta diária (7h00)
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
import random
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
PAUSA = float(os.environ.get("NUBI_COLETOR_PAUSA", "10"))          # segundos entre um download e outro
CALMA = float(os.environ.get("NUBI_COLETOR_CALMA", "1"))           # multiplica as esperas entre cliques

PADRAO_CONFIG = {
    "nubi_email": "",
    "grupo": "460388",                       # grupo "perfumes" no Nubimetrics
    "categoria": "MLB1246-MLB6284",          # Beleza e Cuidado Pessoal > Perfumes
    "categoria_nomes": ["Beleza e Cuidado Pessoal", "Perfumes"],
    "mes_atual": True,                       # manter o mês em andamento atualizado (parcial), todo dia
    "desde": "2026-01",                      # primeiro mês do histórico de vendedores
    "atraso_dias": 2,                        # o Nubimetrics libera os dados com 2 dias de atraso
    "dias_atras": 7,                         # venda isolada: baixa os últimos 7 dias liberados que faltarem
    "mostrar_navegador": False,
    "hashes": {},                            # hash do vendedor -> {nome, primeiro, ultimo} (conferir estabilidade)
    "hash_por_nome": {},                     # apelido -> hash (se mudar, o hash não é estável)
    "config_versao": 2,
}
MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
         "Setembro", "Outubro", "Novembro", "Dezembro"]
OFUSCADO = re.compile(r"^[A-Z]+[.\-][A-Z]+[.\-][A-Z]+$")                   # BANTENG.PRETO.DEMONSTRATIVO
ESCONDER = "#intercom-container, .intercom-lightweight-app, .intercom-launcher {display: none !important}"


class Falha(Exception):
    pass


class SessaoExpirada(Falha):
    pass


# ---------------------------------------------------------------------------
# Configuração, registro e avisos
# ---------------------------------------------------------------------------

LOG = []
# andamento mostrado ao vivo no nubi (Vendedores → Coletor)
AO_VIVO = {"token": None, "id": None, "feito": 0, "total": 0, "atual": "", "enviado": 0.0}


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
    ao_vivo()


def ao_vivo(forcar=False, **mudou):
    """Manda o andamento e o fim do log para o nubi, no máximo a cada 3 s."""
    AO_VIVO.update(mudou)
    if not AO_VIVO["token"] or not AO_VIVO["id"] or (not forcar and time.time() - AO_VIVO["enviado"] < 3):
        return
    AO_VIVO["enviado"] = time.time()
    try:
        api(AO_VIVO["token"], "coletor_registrar", corpo={
            "id": AO_VIVO["id"], "em_andamento": True, "feito": AO_VIVO["feito"], "total": AO_VIVO["total"],
            "atual": AO_VIVO["atual"], "log": "\n".join(LOG[-400:])}, timeout=15)
    except Exception:  # noqa: BLE001
        pass                                          # o site fica sem o ao vivo; a coleta segue


def devagar(seg=2.0):
    """Espera um pouco entre os cliques: o Nubimetrics fecha o Chrome quando é rápido demais."""
    time.sleep(seg * CALMA * random.uniform(0.8, 1.3))


def ler_config():
    cfg = dict(PADRAO_CONFIG)
    if CONFIG.exists():
        salvo = json.loads(CONFIG.read_text(encoding="utf-8"))
        cfg.update(salvo)
        cfg["config_versao"] = salvo.get("config_versao", 1)
    if not str(cfg.get("grupo") or "").isdigit():      # ex.: alguém respondeu "sim" na pergunta do grupo
        cfg["grupo"] = PADRAO_CONFIG["grupo"]
    if int(cfg.get("config_versao") or 1) < 2:
        # a 1ª versão gravava mes_atual=False no config; agora o mês em andamento é baixado todo dia
        cfg["mes_atual"] = True
        cfg["config_versao"] = 2
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


def api(token, rota, params=None, corpo=None, metodo=None, timeout=300):
    q = urllib.parse.urlencode(dict(params or {}, r=rota))
    dados = corpo if isinstance(corpo, (bytes, type(None))) else json.dumps(corpo).encode()
    req = urllib.request.Request(f"{NUBI}/api/app?{q}", data=dados, method=metodo or ("POST" if dados else "GET"),
                                 headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
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


FOTOS_ENVIADAS = [0]


def resumo_tela(pg):
    """Os botões, opções e campos visíveis (texto curto), para entender uma tela que mudou sem ver o Mac."""
    try:
        return pg.evaluate("""() => {
          const vis = e => e.offsetParent !== null && getComputedStyle(e).visibility !== 'hidden';
          const t = [...document.querySelectorAll('button,[role=button],[role=option],[role=menuitem],[role=tab],li,label,input,select')]
            .filter(vis).map(e => e.tagName === 'INPUT' ? `[input ${e.type} ph="${e.placeholder || ''}" v="${e.value || ''}"]`
              : (e.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 40)).filter(Boolean);
          return [...new Set(t)].slice(0, 80).join(' | ');
        }""")[:1500]
    except Exception as e:  # noqa: BLE001
        return f"(sem resumo: {e})"


def enviar_foto(pg, rotulo, tela=""):
    """Manda a foto da tela e o resumo ao nubi (no máximo 6 por coleta), para o erro ser visto de fora do Mac."""
    if FOTOS_ENVIADAS[0] >= 6 or not AO_VIVO.get("token"):
        return
    FOTOS_ENVIADAS[0] += 1
    try:
        import base64
        img = pg.screenshot(type="jpeg", quality=55)
        api(AO_VIVO["token"], "coletor_foto", corpo={"execucao_id": AO_VIVO.get("id"), "rotulo": rotulo[:200],
                                                     "tela": tela[:3000], "foto": base64.b64encode(img).decode()}, timeout=30)
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
    devagar(3)


# ---------------------------------------------------------------------------
# Períodos
# ---------------------------------------------------------------------------

def mes_anterior(hoje=None):
    hoje = hoje or date.today()
    d = hoje.replace(day=1) - timedelta(days=1)
    return f"{d.year}-{d.month:02d}"


def ultimo_dia_liberado(cfg, hoje=None):
    return (hoje or date.today()) - timedelta(days=int(cfg.get("atraso_dias", 2)))


def periodo_fechado(mes, hoje=None):
    ini, fim = limites(mes)
    return {"mes": mes, "ini": ini, "fim": fim, "ate": None,
            "rng": "PREVMONTH" if mes == mes_anterior(hoje) else "CUSTOM"}


def periodos(cfg, hoje=None):
    """Do mês 'desde' até o mês do último dia liberado: meses fechados + o mês atual parcial."""
    d = ultimo_dia_liberado(cfg, hoje)
    a, m = map(int, (cfg.get("desde") or "2026-01").split("-"))
    saida = []
    while (a, m) <= (d.year, d.month):
        mes = f"{a}-{m:02d}"
        ini, fim = limites(mes)
        if (a, m) < (d.year, d.month) or d.isoformat() == fim:
            saida.append(periodo_fechado(mes, hoje))
        elif cfg.get("mes_atual", True):
            saida.append({"mes": mes, "ini": ini, "fim": d.isoformat(), "ate": d.isoformat(), "rng": "CUSTOM"})
        m += 1
        if m == 13:
            a, m = a + 1, 1
    return saida


def periodo_comparativo(cfg, hoje=None):
    """Do dia 1 ao mesmo dia do mês anterior (01/08–22/08 quando os dados vão até 22/09). None no fim do mês."""
    d = ultimo_dia_liberado(cfg, hoje)
    if d.day == calendar.monthrange(d.year, d.month)[1]:
        return None                               # mês atual fechado: compara mês cheio com mês cheio
    ant = date(d.year, d.month, 1) - timedelta(days=1)
    mes = f"{ant.year}-{ant.month:02d}"
    fim = f"{mes}-{min(d.day, ant.day):02d}"
    return {"mes": mes, "ini": f"{mes}-01", "fim": fim, "ate": fim, "rng": "CUSTOM"}


def periodos_dia(cfg, hoje=None):
    """Os últimos dias liberados, um de cada vez (21/09 a 21/09): a venda isolada do dia com os itens de cada vendedor."""
    d = ultimo_dia_liberado(cfg, hoje)
    saida = []
    for n in range(int(cfg.get("dias_atras", 7))):
        x = (d - timedelta(days=n)).isoformat()
        saida.append({"mes": x[:7], "ini": x, "fim": x, "ate": x, "rng": "CUSTOM"})
    return saida


def periodos_intervalo(desde, ate):
    """Um período de 1 dia para cada dia de 'ate' até 'desde' (mais recentes primeiro)."""
    d, fim, saida = date.fromisoformat(ate), date.fromisoformat(desde), []
    while d >= fim:
        x = d.isoformat()
        saida.append({"mes": x[:7], "ini": x, "fim": x, "ate": x, "rng": "CUSTOM"})
        d -= timedelta(days=1)
    return saida


def dias_comparacao(pers):
    """O mesmo dia do mês anterior de cada dia (22/09 -> 22/08), para comparar dia com dia."""
    saida = []
    for per in pers:
        d = date.fromisoformat(per["ate"])
        ant = date(d.year, d.month, 1) - timedelta(days=1)
        if d.day <= ant.day:
            x = ant.replace(day=d.day).isoformat()
            saida.append({"mes": x[:7], "ini": x, "fim": x, "ate": x, "rng": "CUSTOM"})
    return saida


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


def mostrar_mais_linhas(pg):
    """Paginação MUI: tenta 100/50/25 linhas por página para caber o grupo inteiro numa página só."""
    try:
        sel = pg.locator('.MuiTablePagination-select, .MuiTablePagination-root [role="combobox"], '
                         '.MuiTablePagination-root [aria-haspopup="listbox"]').first
        if not sel.count():
            return
        antes = pg.locator('td a[aria-label="Analise um concorrente"]').count()
        sel.click()
        for n in ("100", "50", "25"):
            op = pg.locator(f'li[role="option"][data-value="{n}"]')
            if op.count():
                op.first.click()
                pg.wait_for_function("n => document.querySelectorAll('td a[aria-label=\"Analise um concorrente\"]')"
                                     ".length > n", arg=antes, timeout=15000)
                log(f"  lista de vendedores com {n} por página")
                return
        pg.keyboard.press("Escape")
    except Exception:  # noqa: BLE001
        try:
            pg.keyboard.press("Escape")
        except Exception:  # noqa: BLE001
            pass


def listar_vendedores(pg, cfg):
    """Nome e hash de cada vendedor do grupo (tabela paginada, 10 por página)."""
    ir(pg, f"{BASE}/competition/dashboardbycompetitor?group={cfg['grupo']}&range=PREVMONTH",
       'td a[aria-label="Analise um concorrente"]')
    vistos, pagina = {}, 1
    mostrar_mais_linhas(pg)
    js_nomes = ("() => Array.from(document.querySelectorAll('td a[aria-label=\"Analise um concorrente\"]'))"
                ".map(a => (a.closest('td') || a).innerText.trim()).join('|')")
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
        if prox.count() == 0 or prox.first.is_disabled() or pagina >= 20:
            break
        antes = pg.evaluate(js_nomes)
        prox.first.scroll_into_view_if_needed()
        prox.first.click()
        try:                                         # a página trocou quando a lista de nomes muda
            pg.wait_for_function(f"t => ({js_nomes})() !== t", arg=antes, timeout=30000)
        except Exception:  # noqa: BLE001
            log(f"  ⚠ não consegui passar para a página {pagina + 1} da lista de vendedores; "
                f"sigo com os {len(vistos)} já encontrados " + diagnostico(pg))
            break
        pagina += 1
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


def baixar_grupo(pg, cfg, dia, destino):
    """
    Tabela do grupo no dia (a tela 'Comparar concorrentes' do Nubimetrics): vendas, unidades, visitas, conversão e share
    de TODOS os vendedores num arquivo só. Devolve o arquivo exportado.
    """
    alvo = ((int(dia[8:10]), int(dia[5:7])), (int(dia[8:10]), int(dia[5:7])))
    url = f"{BASE}/competition/dashboardbycompetitor?group={cfg['grupo']}&range=CUSTOM&from={dia}&to={dia}"
    ir(pg, url, 'td a[aria-label="Analise um concorrente"]')
    fim_t = time.time() + 40
    while periodo_na_tela(pg) != alvo and time.time() < fim_t:
        pg.wait_for_timeout(700)
    if periodo_na_tela(pg) != alvo:
        aplicar_periodo(pg, dia, dia)
        fim_t = time.time() + 40
        while periodo_na_tela(pg) != alvo and time.time() < fim_t:
            pg.wait_for_timeout(700)
        if periodo_na_tela(pg) != alvo:
            tela = resumo_tela(pg)
            enviar_foto(pg, f"grupo {dia}: período não mudou", tela)
            raise Falha(f"a tabela do grupo não mudou para {dia} (na tela: {periodo_na_tela(pg)}) " + diagnostico(pg))
    devagar(4)                                          # a tabela recarrega com o período novo
    botao = pg.locator("button, [role=button]", has_text=re.compile(r"^\s*EXPORTAR\s*$", re.I))
    if not botao.count():
        tela = resumo_tela(pg)
        enviar_foto(pg, f"grupo {dia}: sem botão EXPORTAR", tela)
        raise Falha("não achei o botão EXPORTAR da tabela do grupo " + diagnostico(pg))
    with pg.expect_download(timeout=120000) as d:
        botao.last.click()
    arq = destino / d.value.suggested_filename
    d.value.save_as(str(arq))
    devagar(2)
    return arq


def coletar_grupo(p, cfg, token, dias, prazo=None):
    """Baixa a tabela do grupo de cada dia (1 arquivo por dia, todos os vendedores) e manda ao nubi."""
    feitos = cfg.setdefault("grupo_dias", [])
    fila = [d for d in dias if d not in feitos]
    if not fila:
        return 0, 0, 0
    log(f"Tabela do grupo (visitas, conversão, todos os vendedores): {len(fila)} dia(s)")
    ctx = abrir_navegador(p, cfg)
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    a = i = e = 0
    try:
        for dia in fila:
            if prazo and time.time() > prazo:
                break
            destino = PASTA / "arquivos" / "grupo" / dia
            destino.mkdir(parents=True, exist_ok=True)
            try:
                arq = baixar_grupo(pg, cfg, dia, destino)
                a += 1
                r = api(token, "vend_grupo", {"arquivo": arq.name, "ate": dia}, arq.read_bytes())
                i += 1
                feitos.append(dia)
                del feitos[:-400]
                log(f"  grupo {dia[8:10]}/{dia[5:7]}: " + " ".join(r.get("log", [])))
            except SessaoExpirada:
                raise
            except Exception as ex:  # noqa: BLE001
                e += 1
                log(f"  grupo {dia[8:10]}/{dia[5:7]}: ERRO {str(ex)[:200]}")
                if e >= 3 and not i:
                    log("  (a tabela do grupo falhou 3 vezes: paro por hoje; a foto da tela foi para o nubi)")
                    break
            time.sleep(PAUSA * random.uniform(0.8, 1.4))
        guardar_sessao(ctx)
    finally:
        salvar_config(cfg)
        try:
            ctx.close()
        except BaseException:  # noqa: BLE001
            pass
    return a, i, e


def reenviar_dias(cfg, token):
    """Uma vez: reenvia os arquivos de 1 dia já baixados, para o nubi guardar o preço do Nubimetrics e cada anúncio."""
    if cfg.get("reenvio_dias") == 1:
        return 0
    n = 0
    for man in sorted((PASTA / "arquivos" / "dias").glob("*/manifest.json")):
        try:
            itens = json.loads(man.read_text(encoding="utf-8"))
        except ValueError:
            continue
        for m in itens:
            arq = man.parent / m["arquivo"]
            if not arq.exists() or not m.get("ate"):
                continue
            try:
                api(token, "vend_dia", {"arquivo": arq.name, "mes": m["mes"], "ate": m["ate"], "seller_hash": m["seller_hash"]},
                    arq.read_bytes())
                n += 1
            except Exception as ex:  # noqa: BLE001
                log(f"  reenvio {arq.parent.name}/{arq.name}: {str(ex)[:120]}")
    cfg["reenvio_dias"] = 1
    salvar_config(cfg)
    log(f"Reenviados {n} arquivo(s) de dia (preço do Nubimetrics e anúncios)")
    return n


def aplicar_periodo(pg, ini, fim):
    """
    Plano B: escolher o período no calendário da tela. Abre o seletor de período; se aparecerem só os atalhos
    (últimos 7 dias, mês passado…), escolhe a faixa personalizada; preenche início e fim e aplica.
    """
    br = lambda d: f"{d[8:10]}/{d[5:7]}/{d[:4]}"
    botao = pg.locator("button, [role=button]").filter(
        has_text=re.compile(r"\d{1,2}\s+[A-ZÇ]{3}\.?\s*-\s*\d{1,2}\s+[A-ZÇ]{3}", re.I)).first
    if not botao.count():
        raise Falha("não achei o botão do período (ex.: '15 SET - 21 SET') " + diagnostico(pg))
    botao.click()
    devagar(1.5)
    campos_js = """() => [...document.querySelectorAll('input')].map((i, n) => [n, i]).filter(([n, i]) => i.offsetParent &&
        (/^\\d{2}\\/\\d{2}\\/\\d{4}$/.test(i.value) || i.type === 'date' ||
         /dd|aaaa|yyyy|data|date|in[ií]cio|fim|desde|até/i.test([i.placeholder, i.name, i.id,
           i.getAttribute('aria-label')].join(' ')))).map(([n, i]) => [n, i.type])"""

    def esperar_campos(seg):
        fim_t = time.time() + seg
        while time.time() < fim_t:
            c = pg.evaluate(campos_js)
            if len(c) >= 2:
                return c
            pg.wait_for_timeout(600)
        return pg.evaluate(campos_js)

    campos = esperar_campos(4)
    if len(campos) < 2:
        op = pg.get_by_text(re.compile(r"faixa personalizada|per[ií]odo personalizado|personalizad[oa]|customizad[oa]|custom", re.I))
        try:
            if op.count():
                op.last.click(timeout=3000)
                devagar(1.5)
        except Exception:  # noqa: BLE001 — é só um rótulo, não um botão
            pass
        campos = esperar_campos(8)
    if len(campos) < 2:
        tela = resumo_tela(pg)
        enviar_foto(pg, f"calendário sem campos ({ini} a {fim})", tela)
        raise Falha(f"o calendário não mostrou os campos de data. Na tela: {tela[:400]} " + diagnostico(pg))
    for (n, tipo), valor in zip(campos[:2], (ini, fim)):
        campo = pg.locator("input").nth(n)
        campo.click(click_count=3)
        campo.fill(valor if tipo == "date" else br(valor))
        campo.press("Tab")
        devagar(1)
    aplicar = pg.locator("button, [role=button]", has_text=re.compile(r"^\s*(APLICAR|OK|CONFIRMAR|FILTRAR)\s*$", re.I))
    if not aplicar.count():
        tela = resumo_tela(pg)
        enviar_foto(pg, f"calendário sem botão aplicar ({ini} a {fim})", tela)
        raise Falha(f"não achei o botão APLICAR. Na tela: {tela[:400]} " + diagnostico(pg))
    aplicar.last.click()


MES_ABREV = {"JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10,
             "NOV": 11, "DEZ": 12, "FEB": 2, "APR": 4, "MAY": 5, "AUG": 8, "SEP": 9, "OCT": 10, "DEC": 12, "ENE": 1, "DIC": 12}
VAZIO = re.compile(r"sem (dados|resultados|informa|vendas|an[uú]ncios)|nenhum (resultado|dado|an[uú]ncio)|n[aã]o h[aá] (dados|resultados)|"
                   r"no hay|no (data|results)|sin (datos|resultados)", re.I)


class SemDados(Exception):
    """O vendedor não teve venda no período (a tela e a API vêm vazias)."""


def periodo_na_tela(pg):
    """Lê o botão do período (ex.: '01 SET - 21 SET') -> ((dia, mês), (dia, mês)) ou None."""
    try:
        txt = pg.evaluate("() => [...document.querySelectorAll('button,[role=button]')].map(b => b.innerText)"
                          ".find(t => /\\d{1,2}\\s+[A-ZÇa-zç]{3}\\.?\\s*-\\s*\\d{1,2}\\s+[A-ZÇa-zç]{3}/.test(t)) || ''")
    except Exception:  # noqa: BLE001
        return None
    m = re.search(r"(\d{1,2})\s+([A-ZÇa-zç]{3})\.?\s*-\s*(\d{1,2})\s+([A-ZÇa-zç]{3})", txt or "")
    if not m:
        return None
    m1, m2 = MES_ABREV.get(m.group(2).upper()), MES_ABREV.get(m.group(4).upper())
    return ((int(m.group(1)), m1), (int(m.group(3)), m2)) if m1 and m2 else None


def _vazio_json(r):
    """True se a resposta da lista de anúncios veio sem nenhum anúncio (None = não sei dizer)."""
    try:
        j = r.json()
    except Exception:  # noqa: BLE001
        return None
    if isinstance(j, list):
        return len(j) == 0
    if isinstance(j, dict):
        for k in ("items", "data", "results", "rows", "list", "content"):
            if isinstance(j.get(k), list):
                return len(j[k]) == 0
        for k in ("total", "totalItems", "count"):
            if isinstance(j.get(k), (int, float)):
                return j[k] == 0
    return None


def baixar_vendedor(pg, h, ini, fim, rng, destino, nome=None):
    """
    Abre a análise do vendedor no período, confere o período (pela API ou pelo botão da tela) e exporta.
    Escuta as respostas da página desde o início: às vezes a lista carrega antes do clique na aba.
    """
    alvo = ((int(ini[8:10]), int(ini[5:7])), (int(fim[8:10]), int(fim[5:7])))
    vistos = []

    chegou = {}

    def ouvir(r):
        if "analysisitems" in r.url:
            vistos.append(r)
            chegou[id(r)] = time.time()
    certo = lambda r: f"from={ini}" in r.url and f"to={fim}" in r.url
    linhas = lambda: pg.evaluate("() => document.querySelectorAll('table tbody tr').length")
    vazio_tela = lambda: bool(VAZIO.search(pg.evaluate("() => (document.querySelector('main') || document.body).innerText")))

    def pronto(depois=0):
        """Período certo na tela/API e a tabela já decidiu (tem linhas ou está vazia).
        depois: quantas respostas já tinham chegado antes de trocar o período (a tabela antiga ainda pode estar na tela)."""
        bons = [r for r in vistos if certo(r)]
        if bons:
            if _vazio_json(bons[-1]):
                return True                                   # a API respondeu o período certo e sem anúncios
            if time.time() - chegou[id(bons[-1])] < 2:
                return False                                  # a tabela ainda está redesenhando
            return linhas() > 0 or vazio_tela()
        ok_tela = periodo_na_tela(pg) == alvo and len(vistos) > depois
        return ok_tela and (linhas() > 0 or vazio_tela())

    def esperar(cond, seg):
        fim_t = time.time() + seg
        while time.time() < fim_t:
            if cond():
                return True
            pg.wait_for_timeout(700)
        return False

    pg.on("response", ouvir)
    try:
        url = (f"{BASE}/competition/analysisbycompetitor?seller={h}&range={rng}&category="
               f"&from={ini}&to={fim}")
        ir(pg, url, "button#tab-1")
        if f"from={ini}" not in pg.url:              # redirecionou e perdeu o período do endereço: abre de novo
            ir(pg, url, "button#tab-1")
        pg.click("button#tab-1")
        devagar(2)
        # a página já mostrou outro período (ignorou a URL): vai direto para o calendário
        outro = lambda: bool(vistos) and not any(certo(r) for r in vistos) and time.time() - chegou[id(vistos[-1])] > 3 \
            and periodo_na_tela(pg) not in (None, alvo)
        estado = {"assin": None, "desde": 0.0}

        def vendedor_certo():
            if not nome:
                return True
            return bool(pg.evaluate("n => [...document.querySelectorAll('input')].some(i => (i.value || '').trim().toUpperCase()"
                                    " === n)", nome.strip().upper()))

        def estavel():
            """Período e vendedor certos na tela e a tabela parada há 4 s (vendedor grande: a lista demora e às vezes a
            resposta da API não é reconhecida). Tabela vazia com aviso de 'sem dados' também vale (não vendeu)."""
            if periodo_na_tela(pg) != alvo or not vendedor_certo():
                estado["assin"] = None
                return False
            if linhas() == 0:
                return vazio_tela()
            assin = pg.evaluate("() => { const r = document.querySelectorAll('table tbody tr');"
                                " return r.length + '|' + (r[0] ? r[0].innerText.slice(0, 80) : ''); }")
            if assin != estado["assin"]:
                estado["assin"], estado["desde"] = assin, time.time()
                return False
            return time.time() - estado["desde"] >= 4
        esperar(lambda: pronto() or outro(), 45)
        if not pronto() and not outro() and periodo_na_tela(pg) == alvo:
            # período certo na tela: só está demorando; espera mais em vez de mexer no calendário
            if not esperar(lambda: pronto() or estavel(), 150):
                raise Falha(f"a lista de anúncios de {ini} a {fim} não terminou de carregar " + diagnostico(pg))
        elif not pronto():
            # a tela ignorou o período da URL (ou a lista não veio): escolhe no calendário
            n0 = len(vistos)
            aplicar_periodo(pg, ini, fim)
            if not esperar(lambda: pronto(n0), 60):
                faixas = sorted({re.sub(r".*from=([\d-]+).*to=([\d-]+).*", r"\1 a \2", r.url) for r in vistos}) or ["nenhuma"]
                raise Falha(f"a lista de anúncios não carregou para {ini} a {fim} (a página pediu: {', '.join(faixas)[:120]}; "
                            f"período na tela: {periodo_na_tela(pg)}) " + diagnostico(pg))
        resp = [r for r in vistos if certo(r)]
        if (resp and _vazio_json(resp[-1])) or (linhas() == 0 and vazio_tela() and periodo_na_tela(pg) == alvo):
            raise SemDados()
        if linhas() == 0:
            if not esperar(lambda: linhas() > 0, 30):
                raise Falha("a tabela de anúncios ficou vazia " + diagnostico(pg))
        pg.wait_for_selector("#dashboardByCompetitor_exportBtn_table", timeout=60000)
        devagar(3)                                       # a tabela termina de desenhar
        with pg.expect_download(timeout=120000) as d:
            pg.click("#dashboardByCompetitor_exportBtn_table")
        dl = d.value
        arq = destino / dl.suggested_filename           # nome = vendedor na tela; não renomear
        dl.save_as(str(arq))
        devagar(2)                                       # deixa o Chrome terminar o download antes de seguir
        if arq.stat().st_size < 3000:
            raise Falha(f"arquivo vazio ou incompleto ({arq.name})")
        return arq
    finally:
        try:
            pg.remove_listener("response", ouvir)
        except Exception:  # noqa: BLE001
            pass


FALTARAM = [0]          # quantos arquivos ficaram para depois quando a coleta parou pelo prazo


def feito(cfg, rota, h, ate):
    """Guarda as fotos/dias já enviados (só os últimos 400 de cada vendedor)."""
    if rota in ("vend_foto", "vend_dia"):
        lista = cfg.setdefault("fotos" if rota == "vend_foto" else "dias", {}).setdefault(h, [])
        lista.append(ate)
        del lista[:-400]


def coletar_vendedores(p, cfg, token, lista_periodos, so=None, enviar=True, pular=None, avisos=None, rota="vend_importar",
                       por_dia=False, prazo=None):
    """Para cada vendedor do grupo, baixa cada período (mês fechado ou mês atual parcial) e envia ao nubi.
    pular(hash, nome, periodo) -> True quando o nubi já tem exatamente esse período.
    por_dia: percorre período por período (todos os vendedores de um dia, depois o dia anterior).
    prazo: hora (time.time) em que para de baixar; o que faltar fica para a próxima vez."""
    estado = {"ctx": abrir_navegador(p, cfg)}
    estado["pg"] = estado["ctx"].pages[0] if estado["ctx"].pages else estado["ctx"].new_page()

    def reabrir(motivo):
        """A aba ou o navegador fechou no meio: abre de novo e segue."""
        log(f"    (o navegador fechou: {motivo[:80]}; abrindo de novo)")
        try:
            estado["ctx"].close()
        except Exception:  # noqa: BLE001
            pass
        time.sleep(10)
        estado["ctx"] = abrir_navegador(p, cfg)
        estado["pg"] = estado["ctx"].new_page()

    def pagina():
        pg = estado["pg"]
        if pg.is_closed():
            try:
                estado["pg"] = estado["ctx"].new_page()
            except Exception as e:  # noqa: BLE001
                reabrir(str(e))
        return estado["pg"]

    arquivos = importados = erros = 0
    try:
        lista, av = listar_vendedores(pagina(), cfg)
        if avisos is not None:
            avisos.extend(av)
        salvar_config(cfg)
        lista = [(h, nome) for h, nome in lista if not so or so.upper() == nome.upper()]
        fila = ([(h, nome, per) for per in lista_periodos for h, nome in lista] if por_dia else
                [(h, nome, per) for h, nome in lista for per in lista_periodos])
        fila = [x for x in fila if not (pular and pular(*x))]
        log(f"Vendedores: {len(fila)} arquivo(s) para baixar")
        ao_vivo(True, total=AO_VIVO["total"] + len(fila))
        anterior = None
        FALTARAM[0] = 0
        seguidos = 0
        for n, (h, nome, per) in enumerate(fila):
            if seguidos >= 6:
                FALTARAM[0] = len(fila) - n
                log(f"  PAROU: {seguidos} erros seguidos (a tela do Nubimetrics deve ter mudado). A foto e o resumo da tela "
                    f"foram para o nubi; faltam {FALTARAM[0]} arquivo(s).")
                break
            if prazo and time.time() > prazo:
                FALTARAM[0] = len(fila) - n
                log(f"  (hora de parar: faltam {FALTARAM[0]} arquivo(s), ficam para a próxima rodada)")
                break
            if anterior and anterior != h and not por_dia:
                guardar_sessao(estado["ctx"])
            anterior = h
            mes, ate = per["mes"], per["ate"]
            rotulo = (f"dia {ate[8:10]}/{ate[5:7]}" if rota == "vend_dia" else
                      mes + (f" até {ate[8:10]}/{ate[5:7]}" if ate else ""))
            if pular and pular(h, nome, per):
                continue
            ao_vivo(True, atual=f"{nome} · {rotulo}")
            destino = PASTA / "arquivos" / (f"dias/{ate}" if rota == "vend_dia" else
                                            mes + ("-comparativo" if rota == "vend_foto" else "-parcial" if ate else ""))
            destino.mkdir(parents=True, exist_ok=True)
            for tentativa in (1, 2):
                try:
                    arq = baixar_vendedor(pagina(), h, per["ini"], per["fim"], per["rng"], destino, nome)
                    arquivos += 1
                    log(f"  {nome} {rotulo}: baixado {arq.name} ({arq.stat().st_size // 1024} KB)")
                    manifesto_arq = destino / "manifest.json"
                    manifesto = (json.loads(manifesto_arq.read_text(encoding="utf-8"))
                                 if manifesto_arq.exists() else [])
                    manifesto = [m for m in manifesto if m["arquivo"] != arq.name] + [{
                        "arquivo": arq.name, "nome_exibido": nome, "seller_hash": h, "mes": mes, "ate": ate,
                        "baixado_em": datetime.now(timezone.utc).isoformat()}]
                    manifesto_arq.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
                    if enviar:
                        # nome do arquivo = nome exibido; o hash é a identidade do vendedor no nubi
                        params = {"arquivo": arq.name, "mes": mes, "seller_hash": h}
                        if ate:
                            params["ate"] = ate
                        try:
                            r = api(token, rota, params, arq.read_bytes())
                        except Falha as e:
                            if "nenhum anúncio" in str(e):
                                raise SemDados()      # o Nubimetrics exportou a planilha vazia: não vendeu no período
                            raise
                        importados += 1
                        seguidos = 0
                        log("    " + " ".join(r.get("log", [])))
                        feito(cfg, rota, h, ate)
                    break
                except SessaoExpirada:
                    raise
                except SemDados:
                    seguidos = 0
                    log(f"  {nome} {rotulo}: sem vendas nesse período (nada para importar)")
                    if rota == "vend_dia" and enviar:
                        try:                       # guarda o dia zerado: "não vendeu" é diferente de "não coletado"
                            api(token, "vend_dia_vazio", {"ate": ate, "seller_hash": h, "nome": nome}, metodo="POST")
                        except Exception:  # noqa: BLE001
                            pass
                    if rota in ("vend_foto", "vend_dia"):
                        feito(cfg, rota, h, ate)
                    elif not ate:     # mês fechado vazio não muda mais: não tenta de novo
                        cfg.setdefault("vazios", {}).setdefault(h, []).append(mes)
                    break
                except Exception as e:  # noqa: BLE001
                    fechou = "has been closed" in str(e) or "Target closed" in str(e)
                    if fechou and tentativa == 1:
                        reabrir(str(e))
                        continue
                    erros += 1
                    seguidos += 1
                    if not fechou:
                        enviar_foto(pagina(), f"{nome} {rotulo}: {str(e)[:150]}", resumo_tela(pagina()))
                    extra = "" if fechou else " " + diagnostico(pagina())
                    log(f"  {nome} {rotulo}: ERRO {str(e)[:200]}{extra}")
                    break
            AO_VIVO["feito"] += 1
            ao_vivo(True)
            time.sleep(PAUSA * random.uniform(0.8, 1.4))
        guardar_sessao(estado["ctx"])
    finally:
        salvar_config(cfg)
        try:
            estado["ctx"].close()
        except BaseException:  # noqa: BLE001 — inclusive um 2º Ctrl+C enquanto fecha
            pass
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
        devagar(3)
        with pg.expect_download(timeout=120000) as d:
            pg.locator("button", has_text="EXPORTAR").last.click()
        dl = d.value
        nome = dl.suggested_filename
        if not re.search(r"MARCAS.*\d{4}-\d{2}", nome, re.I):
            nome = f"MARCAS-{cat}-{mes}-01.xlsx"
        arq = destino / nome
        dl.save_as(str(arq))
        devagar(2)
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
            "id": AO_VIVO["id"], "em_andamento": False, "atual": None, "feito": AO_VIVO["feito"],
            "total": AO_VIVO["total"], "iniciado_em": inicio.isoformat(), "terminado_em": datetime.now(timezone.utc).isoformat(),
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


def _outra_rodando():
    """PID de outra coleta rodando agora (o Chrome do coletor não abre duas vezes), ou None."""
    trava = PASTA / "rodando.pid"
    try:
        pid = int(trava.read_text().strip())
        if pid != os.getpid():
            os.kill(pid, 0)
            return pid
    except (OSError, ValueError):
        pass
    return None


def executar(tarefa, func):
    """Roda uma coleta com registro no nubi e aviso no Mac em caso de erro."""
    if _outra_rodando():
        if tarefa != "diario":
            log("Já tem uma coleta rodando neste Mac. Espere ela terminar e rode de novo.")
            return 1
        log("Outra coleta está rodando (histórico de vendas diárias?): esperando ela terminar…")
        fim = time.time() + 4 * 3600
        while _outra_rodando() and time.time() < fim:
            time.sleep(60)
    trava = PASTA / "rodando.pid"
    try:
        trava.write_text(str(os.getpid()))
    except OSError:
        pass
    try:
        return _executar(tarefa, func)
    finally:
        try:
            if trava.read_text().strip() == str(os.getpid()):
                trava.unlink()
        except OSError:
            pass


def _executar(tarefa, func):
    cfg = ler_config()
    inicio = datetime.now(timezone.utc)
    token = None
    AO_VIVO.update(id=None, feito=0, total=0, atual="")      # 2ª tarefa na mesma rodada começa do zero
    LOG.clear()
    try:
        token = token_nubi(cfg)
        try:
            r = api(token, "coletor_registrar", corpo={"iniciado_em": inicio.isoformat(), "tarefa": tarefa,
                                                       "em_andamento": True, "mensagem": "rodando…"}, timeout=30)
            AO_VIVO.update(token=token, id=r.get("id"))
        except Exception as e:  # noqa: BLE001
            log(f"(sem acompanhamento ao vivo no nubi: {e})")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            arquivos, importados, erros, msg = func(p, cfg, token)
        ok = erros == 0
        log(("OK: " if ok else "Terminou com erros: ") + msg)
        registrar(token, tarefa, inicio, ok, arquivos, importados, erros, msg)
        if not ok:
            aviso_mac("Coletor nubi", msg)
        return 0 if ok else 1
    except KeyboardInterrupt:
        log("Interrompido (Ctrl+C). O que já foi importado fica no nubi; rode de novo que ele continua de onde parou.")
        registrar(token, tarefa, inicio, False, 0, 0, 0, "interrompido à mão (Ctrl+C)")
        return 130
    except Exception as e:  # noqa: BLE001
        msg = str(e) if isinstance(e, Falha) else f"{e.__class__.__name__}: {e}"
        log("FALHOU: " + msg)
        if not isinstance(e, Falha):
            log(traceback.format_exc()[-2000:])
        registrar(token, tarefa, inicio, False, 0, 0, 1, msg)
        aviso_mac("Coletor nubi — falhou", msg)
        return 2


def cmd_dias(args, segundos=None):
    """
    Histórico de vendas diárias: baixa o export de UM dia de cada vendedor, de ontem-1 até --desde (mais recentes
    primeiro). Continua de onde parou; o que faltar a coleta diária completa aos poucos (até 1h30 por dia).
    Rodado à mão antes das 6h40, para às 6h40 para não atrapalhar a coleta das 7h.
    """
    cfg = ler_config()
    if args is not None and args.desde:
        cfg["dias_desde"] = args.desde
        salvar_config(cfg)
    desde = cfg.get("dias_desde")
    if not desde:
        print("Informe o primeiro dia: coletor dias --desde 2026-08-01")
        return 1
    ate = (args.ate if args is not None and args.ate else None) or ultimo_dia_liberado(cfg).isoformat()
    agora = datetime.now()
    limite = agora.replace(hour=6, minute=40, second=0)
    prazo = time.time() + segundos if segundos else (limite.timestamp() if agora < limite else None)

    def f(p, cfg, token):
        dias_ok = cfg.setdefault("dias", {})
        pers = periodos_intervalo(desde, ate)
        reenviar_dias(cfg, token)
        a, i, e = coletar_vendedores(p, cfg, token, pers, rota="vend_dia", por_dia=True, prazo=prazo,
                                     pular=lambda h, nome, per: per["ate"] in dias_ok.get(h, []))
        try:
            a2, i2, _ = coletar_grupo(p, cfg, token, [x["ate"] for x in pers], prazo=prazo)
            a, i = a + a2, i + i2
        except SessaoExpirada:
            raise
        except Exception as ex:  # noqa: BLE001
            log(f"  tabela do grupo: ERRO {str(ex)[:200]}")
        # terminou tudo (sem parar pelo prazo e sem erro)? -> não precisa mais continuar na coleta diária
        falta = FALTARAM[0] + e
        if not falta:
            cfg.pop("dias_desde", None)
            salvar_config(cfg)
        return a, i, e, f"vendas diárias de {desde[8:10]}/{desde[5:7]} a {ate[8:10]}/{ate[5:7]}: {i} dia(s) importado(s)" + \
            (f"; faltam {falta} (continua na próxima coleta)" if falta else "; histórico completo")
    return executar("dias", f)


def auto_atualizar():
    """Antes de cada coleta: se o nubi tem uma versão nova do coletor, troca e roda a nova (sem ninguém no Terminal)."""
    try:
        novo = urllib.request.urlopen(f"{NUBI}/coletor/coletor.py", timeout=20).read()
        atual = Path(__file__).read_bytes()
        if not novo or novo == atual:
            return
        compile(novo, "coletor.py", "exec")               # só troca se o arquivo novo estiver íntegro
        Path(__file__).write_bytes(novo)
    except Exception as e:  # noqa: BLE001
        print(f"(não consegui verificar versão nova do coletor: {e}; seguindo com a atual)", flush=True)
        return
    print("Coletor atualizado para a versão nova; reiniciando…", flush=True)
    os.environ["NUBI_ATUALIZADO"] = "1"
    os.execv(sys.executable, [sys.executable, str(Path(__file__).resolve())] + sys.argv[1:])


def main():
    ap = argparse.ArgumentParser(description="Coletor do Nubimetrics para o nubi")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("configurar")
    sub.add_parser("entrar")
    sub.add_parser("status")
    sub.add_parser("atualizar", help="baixa a versão mais nova do coletor")
    ag = sub.add_parser("agendar", help="muda o horário da coleta diária")
    ag.add_argument("hora", type=int)
    ag.add_argument("minuto", type=int, nargs="?", default=0)
    d = sub.add_parser("diario")
    d.add_argument("--ver", action="store_true", help="mostrar a janela do navegador")
    v = sub.add_parser("vendedores")
    v.add_argument("--mes")
    v.add_argument("--parcial", action="store_true", help="mês atual até ontem")
    v.add_argument("--so", help="só este vendedor")
    v.add_argument("--sem-enviar", action="store_true")
    v.add_argument("--ver", action="store_true", help="mostrar a janela do navegador")
    ds = sub.add_parser("dias", help="histórico de vendas diárias (export de 1 dia de cada vendedor)")
    ds.add_argument("--desde", help="primeiro dia, ex.: 2026-08-01")
    ds.add_argument("--ate", help="último dia (padrão: o último liberado)")
    ds.add_argument("--ver", action="store_true", help="mostrar a janela do navegador")
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
    if args.cmd == "agendar":
        plist = Path.home() / "Library" / "LaunchAgents" / "com.nubi.coletor.plist"
        if not plist.exists():
            print("Agendamento não encontrado; rode o instalador.")
            return 1
        txt = plist.read_text(encoding="utf-8")
        txt = re.sub(r"(<key>Hour</key><integer>)\d+", rf"\g<1>{args.hora}", txt)
        txt = re.sub(r"(<key>Minute</key><integer>)\d+", rf"\g<1>{args.minuto}", txt)
        plist.write_text(txt, encoding="utf-8")
        subprocess.run(["launchctl", "unload", str(plist)], check=False, capture_output=True)
        subprocess.run(["launchctl", "load", str(plist)], check=False)
        print(f"OK: coleta diária agendada para {args.hora}h{args.minuto:02d}.")
        return 0
    if args.cmd in ("diario", "vendedores", "marcas", "dias") and not os.environ.get("NUBI_ATUALIZADO"):
        auto_atualizar()
    if args.cmd == "atualizar":
        novo = urllib.request.urlopen(f"{NUBI}/coletor/coletor.py", timeout=60).read()
        compile(novo, "coletor.py", "exec")               # só troca se o arquivo novo estiver íntegro
        Path(__file__).write_bytes(novo)
        print("OK: coletor atualizado.")
        return 0
    if args.cmd == "vendedores":
        def f(p, cfg, token):
            if args.parcial:
                d = ultimo_dia_liberado(cfg)
                mes = f"{d.year}-{d.month:02d}"
                pers = [{"mes": mes, "ini": f"{mes}-01", "fim": d.isoformat(), "ate": d.isoformat(), "rng": "CUSTOM"}]
            else:
                pers = [periodo_fechado(args.mes or mes_anterior())]
            a, i, e = coletar_vendedores(p, cfg, token, pers, args.so, not args.sem_enviar)
            return a, i, e, f"vendedores: {a} baixado(s), {i} importado(s), {e} erro(s)"
        return executar("vendedores", f)
    if args.cmd == "marcas":
        def f(p, cfg, token):
            a, i, e = coletar_marcas(p, cfg, token, args.mes, not args.sem_enviar)
            return a, i, e, f"MARCAS {args.mes or mes_anterior()}: baixado"
        return executar("marcas", f)
    if args.cmd == "diario":
        def f(p, cfg, token):
            pend = api(token, "coletor_pendencias")
            rot = pend.get("rotina") or {}
            hoje = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"][date.today().weekday()]
            if rot and (not rot.get("ativo", True) or (hoje not in (rot.get("dias_semana") or [])
                                                       and rot.get("dia_mes") != date.today().day)):
                log("Coleta diária desligada para hoje em Tarefas de rotina (site): nada a fazer.")
                return 0, 0, 0, "desligada hoje em Tarefas de rotina"
            d = ultimo_dia_liberado(cfg)
            pers = periodos(cfg)
            A = I = E = 0
            partes = [f"dados até {d:%d/%m}"]
            # MARCAS: todo mês fechado (último dia já liberado) que ainda não está no nubi
            ja_rk = set(pend["ranking"].get(cfg["categoria"], []))
            faltam = [per for per in pers if not per["ate"] and per["mes"] not in ja_rk]
            ao_vivo(True, total=len(faltam))
            for per in pers:
                if per["ate"] or per["mes"] in ja_rk:
                    continue
                ao_vivo(True, atual=f"MARCAS · {per['mes']}")
                try:
                    a, i, e = coletar_marcas(p, cfg, token, per["mes"])
                    partes.append(f"MARCAS {per['mes']} importado")
                except SessaoExpirada:
                    raise
                except Exception as ex:  # noqa: BLE001
                    a, i, e = 0, 0, 1
                    log(f"  MARCAS {per['mes']}: ERRO {ex}")
                    partes.append(f"MARCAS {per['mes']} falhou")
                A, I, E = A + a, I + i, E + e
                AO_VIVO["feito"] += 1
                devagar(5)
            # vendedores: cada mês que falta, o mês que ainda estava parcial e fechou, e o mês atual
            ja, ja_h = pend["vendedores"], pend.get("hashes", {})

            vazios = cfg.get("vazios", {})

            def pular(h, nome, per):
                if not per["ate"] and per["mes"] in vazios.get(h, []):
                    return True                      # mês fechado sem venda desse vendedor
                reg = ja_h.get(h) if h in ja_h else ja.get(nome, {})
                return per["mes"] in reg and (reg[per["mes"]] or None) == per["ate"]
            avisos = []
            a, i, e = coletar_vendedores(p, cfg, token, pers, pular=pular, avisos=avisos)
            A, I, E = A + a, I + i, E + e
            partes.append(f"vendedores: {i} arquivo(s) importado(s)")
            # mesmo período do mês anterior (ex.: 01/08 a 22/08), para comparar com 01/09 a 22/09
            comp = periodo_comparativo(cfg)
            if comp:
                feitas = cfg.get("fotos", {})
                a, i, e = coletar_vendedores(p, cfg, token, [comp], rota="vend_foto",
                                             pular=lambda h, nome, per: per["ate"] in feitas.get(h, []))
                A, I, E = A + a, I + i, E + e
                partes.append(f"mesmo período de {comp['mes']} (até {comp['ate'][8:10]}/{comp['ate'][5:7]}): {i} vendedor(es)")
            # venda isolada de cada um dos últimos dias (21/09 a 21/09), com todos os itens vendidos de cada vendedor
            # e o mesmo dia do mês anterior (22/09 -> 22/08), para comparar dia com dia
            dias_ok = cfg.get("dias", {})
            pdias = periodos_dia(cfg)
            a, i, e = coletar_vendedores(p, cfg, token, pdias + dias_comparacao(pdias[:1]), rota="vend_dia", por_dia=True,
                                         pular=lambda h, nome, per: per["ate"] in dias_ok.get(h, []))
            A, I, E = A + a, I + i, E + e
            partes.append(f"vendas do dia: {i} arquivo(s)")
            reenviar_dias(cfg, token)
            # tabela do grupo (visitas, conversão e o total de todos os vendedores) dos mesmos dias
            try:
                a, i, e = coletar_grupo(p, cfg, token, [x["ate"] for x in pdias + dias_comparacao(pdias[:1])])
                A, I, E = A + a, I + i, E + e
                if a or e:
                    partes.append(f"tabela do grupo: {i} dia(s)" + (f", {e} erro(s)" if e else ""))
            except SessaoExpirada:
                raise
            except Exception as ex:  # noqa: BLE001
                log(f"  tabela do grupo: ERRO {str(ex)[:200]}")
            if avisos:
                partes.append(f"{len(avisos)} aviso(s): " + "; ".join(avisos)[:300])
                aviso_mac("Coletor nubi — conferir", avisos[0])
            return A, I, E, "; ".join(partes) + (f"; {E} erro(s)" if E else "")
        rc = executar("diario", f)
        if ler_config().get("dias_desde"):
            # histórico de vendas diárias ainda incompleto: continua por até 1h30, depois do resumo do dia já sair
            rc2 = cmd_dias(None, 90 * 60)
            return rc or rc2
        return rc
    if args.cmd == "dias":
        return cmd_dias(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
