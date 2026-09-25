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
  python coletor.py hermes          o Hermes (Ollama, no Mac) lê a Sala de reunião e dá a opinião dele
  python coletor.py qwen            o Qwen (Ollama, no Mac) confere a Sala e posta a revisão dele
  python coletor.py entrar-upseller abre o navegador para você fazer login no UpSeller (uma vez)
  python coletor.py entrar-gestor   abre o navegador para você fazer login no Gestor Seller (uma vez)
  python coletor.py gestor          baixa do nubi a planilha do Gestor Seller e importa em Produtos internos
  python coletor.py estoque         exporta a Lista de Estoque do UpSeller e manda para Minhas Lojas → Estoque
                                    (o vigia roda sozinho de madrugada, no horário da rotina 'estoque')
  (qualquer coleta aceita --ver para mostrar a janela do navegador e acompanhar)

Os caminhos, botões e endereços do Nubimetrics seguem o mapeamento feito com o Claude do
navegador (URLs diretas, ids e aria-labels estáveis; os ids gerados pelo MUI mudam a cada
carga e não são usados).
"""

import argparse
import calendar
import getpass
import hashlib
import json
import os
import random
import re
import signal
import shutil
import subprocess
import sys
import time
import traceback
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = os.environ.get("NUBIMETRICS_URL", "https://app.nubimetrics.com")
UPSELLER = os.environ.get("UPSELLER_URL", "https://app.upseller.com")
GESTOR = os.environ.get("GESTOR_URL", "https://app.gestorseller.com.br")
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


TOKEN = {"cfg": None, "troca": {}}   # o login do nubi vale 1 h: nas coletas longas, api() entra de novo sozinho


def token_nubi(cfg):
    if os.environ.get("NUBI_TOKEN"):                   # testes
        return os.environ["NUBI_TOKEN"]
    TOKEN["cfg"] = cfg
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


def api(token, rota, params=None, corpo=None, metodo=None, timeout=300, _de_novo=True):
    token = TOKEN["troca"].get(token, token)
    q = urllib.parse.urlencode(dict(params or {}, r=rota))
    dados = corpo if isinstance(corpo, (bytes, type(None))) else json.dumps(corpo).encode()
    req = urllib.request.Request(f"{NUBI}/api/app?{q}", data=dados, method=metodo or ("POST" if dados else "GET"),
                                 headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        if e.code == 401 and _de_novo and TOKEN["cfg"] is not None:
            # login vencido no meio da coleta: entra de novo e repete o envio (antes, tudo depois de 1 h dava erro)
            novo = token_nubi(TOKEN["cfg"])
            for velho in [k for k, v in TOKEN["troca"].items() if v == token] + [token]:
                TOKEN["troca"][velho] = novo
            return api(novo, rota, params, corpo, metodo, timeout, _de_novo=False)
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
            # nome aleatório do Nubimetrics é normal: o vendedor é reconhecido pelo hash (e o dono renomeia quando souber)
            log(f"  · {nome}: nome aleatório, identificado pelo hash {h[:10]}…")
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
        anotar_falha(tarefa, msg)
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


# ---------------------------------------------------------------------------
# Estoque do UpSeller (Minhas Lojas → Estoque): Estoque → Lista de Estoque → aba My Warehouse →
# Importar & Exportar → Exportar Páginas (1 até o total) → Exportar → 100% → Baixar
# ---------------------------------------------------------------------------

def _upseller_lista(pg):
    """Abre a Lista de Estoque; sem o botão 'Importar & Exportar' em 60 s = login vencido ou tela mudou."""
    pg.goto(f"{UPSELLER}/pt/inventory/list", wait_until="domcontentloaded", timeout=90000)
    botao = pg.get_by_text("Importar & Exportar").first
    try:
        botao.wait_for(state="visible", timeout=60000)
    except Exception:  # noqa: BLE001
        u = urllib.parse.urlparse(pg.url)
        senha = pg.locator("input[type=password]:visible").count() > 0
        if senha or "login" in (u.path + u.fragment).lower() or "/inventory" not in u.path:
            raise SessaoExpirada("O UpSeller pediu login de novo. No Mac mini, rode: ~/.nubi-coletor/coletor entrar-upseller "
                                 + diagnostico(pg))
        raise Falha("a Lista de Estoque do UpSeller não carregou (sem o botão 'Importar & Exportar') " + diagnostico(pg))
    devagar(3)
    return botao


def _numero(txt, rotulo):
    m = re.search(rotulo + r"\s*[:\n]?\s*([\d.]+)", txt)
    return int(m.group(1).replace(".", "")) if m else None


def baixar_estoque(pg, p=None):
    """Faz o export na tela e devolve (arquivo baixado, SKUs esperados)."""
    botao = _upseller_lista(pg)
    aba = pg.get_by_text(re.compile(r"^\s*My Warehouse\s*\d*\s*$")).first
    esperado = None
    if aba.count():
        aba.click()
        devagar(3)
        esperado = _numero(aba.inner_text(), "My Warehouse")
    log(f"  UpSeller: Lista de Estoque aberta (My Warehouse: {esperado if esperado is not None else '?'} SKUs)")
    botao.click()
    devagar(1.5)
    pg.get_by_text("Exportar Páginas", exact=True).first.click()
    janela = pg.locator(".ant-modal-content, [role=dialog]").filter(has_text=re.compile("Total de P[aá]ginas")).last
    janela.wait_for(state="visible", timeout=30000)
    devagar(1.5)
    paginas = _numero(janela.inner_text(), "Total de P[aá]ginas")
    campos = janela.locator("input:visible")
    if paginas and campos.count() >= 2:
        campos.nth(0).fill("1")
        campos.nth(1).fill(str(paginas))
    log(f"  exportando as páginas 1 a {paginas or '?'}")
    janela.get_by_role("button", name=re.compile(r"^\s*Exportar\s*$")).click()
    baixar = pg.get_by_role("button", name=re.compile(r"^\s*Baixar\s*$")).last
    baixar.wait_for(state="visible", timeout=15 * 60 * 1000)
    devagar(2)
    fim = pg.locator(".ant-modal-content, [role=dialog]").filter(has=baixar).last.inner_text()
    total, sucesso, falhou = _numero(fim, "Total"), _numero(fim, "Sucesso"), _numero(fim, "Falhou")
    log(f"  export pronto: total {total}, sucesso {sucesso}, falhou {falhou}")
    if falhou:
        raise Falha(f"o UpSeller exportou com {falhou} SKU(s) com falha; não importei (tento de novo depois)")
    destino = PASTA / "estoque"
    destino.mkdir(parents=True, exist_ok=True)
    # 25/09: o Chrome fechava inteiro no instante do download (TargetClosedError, até com o navegador visível). Então:
    # (1) uma aba extra fica aberta para o Chrome não sair se a aba do download fechar; (2) guardo o login e o link do
    # arquivo antes; (3) se o navegador cair, baixo pelo link com um cliente HTTP à parte (não depende do Chrome).
    ctx = pg.context
    estado = ctx.storage_state()
    links = []
    ctx.on("request", lambda r: links.append(r.url) if re.search(r"\.xlsx(\?|$)|download|export", r.url, re.I) else None)
    ctx.on("page", lambda nova: log(f"  (o UpSeller abriu uma aba nova: {nova.url[:80]})"))
    ctx.on("close", lambda _: log("  (o navegador fechou)"))
    try:
        ctx.new_page().goto("about:blank")
    except Exception:  # noqa: BLE001
        pass
    try:
        href = pg.locator(".ant-modal-content a[href], [role=dialog] a[href]").last.get_attribute("href", timeout=3000)
        if href and href.startswith("http"):
            links.append(href)
    except Exception:  # noqa: BLE001
        pass
    d = None
    try:
        try:
            with pg.expect_download(timeout=120000) as dl:
                baixar.click()
        except Exception:  # noqa: BLE001
            with pg.expect_download(timeout=120000) as dl:     # plano B: o nome do arquivo na janela também baixa
                pg.get_by_text(re.compile(r"\.xlsx\s*$")).last.click()
        d = dl.value
        arq = destino / d.suggested_filename              # nome do UpSeller, sem renomear
        _salvar_download(pg, d, arq)
        return arq, sucesso or esperado
    except Exception as e:  # noqa: BLE001
        url = (getattr(d, "url", "") or "") if d else ""
        candidatos = [u for u in [url] + links[::-1] if u.startswith("http")]
        if p is None or not candidatos:
            raise
        log(f"  o navegador falhou no download ({e.__class__.__name__}); baixando pelo link com um cliente à parte")
        nome = (d.suggested_filename if d else "") or ""
        return _baixar_link(p, estado, candidatos, destino, nome), sucesso or esperado


def _salvar_download(pg, d, arq):
    """Salva o download. Na madrugada de 25/09 o UpSeller exportou os 640 SKUs mas o arquivo se perdeu (TargetClosedError:
    a aba que baixa fecha sozinha): aí baixa de novo direto pelo link, com os cookies do navegador. O nome não muda."""
    try:
        d.save_as(str(arq))
        return
    except Exception as e:  # noqa: BLE001
        url = d.url or ""
        if not url.startswith("http"):
            raise
        log(f"  o download se perdeu ({e.__class__.__name__}); baixando direto pelo link")
    r = pg.context.request.get(url, timeout=120000)
    if not r.ok:
        raise Falha(f"não consegui baixar a planilha do estoque pelo link (HTTP {r.status})")
    corpo = r.body()
    if corpo[:2] != b"PK":
        raise Falha("o link do estoque não devolveu uma planilha .xlsx")
    arq.write_bytes(corpo)


def _baixar_link(p, estado, candidatos, destino, nome):
    """Baixa a planilha pelo link com um cliente HTTP do Playwright (sem Chrome), usando os cookies guardados."""
    req = p.request.new_context(storage_state=estado)
    try:
        for url in dict.fromkeys(candidatos):
            try:
                r = req.get(url, timeout=120000)
            except Exception:  # noqa: BLE001
                continue
            corpo = r.body() if r.ok else b""
            if corpo[:2] != b"PK":
                continue
            if not nome:
                m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+\.xlsx)', r.headers.get("content-disposition", ""), re.I)
                nome = urllib.parse.unquote(m.group(1)) if m else urllib.parse.unquote(url.split("?")[0].rsplit("/", 1)[-1])
            arq = destino / Path(nome).name
            arq.write_bytes(corpo)
            return arq
    finally:
        req.dispose()
    raise Falha("o Chrome fechou no download do estoque e o link do arquivo não devolveu a planilha")


def coletar_estoque(p, cfg, token, enviar=True):
    ctx = abrir_navegador(p, cfg, visivel=True if cfg.get("upseller_ver") else None)
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        arq, esperado = baixar_estoque(pg, p)
        guardar_sessao(ctx)
    except SessaoExpirada:
        enviar_foto(pg, "estoque: login do UpSeller vencido", resumo_tela(pg))
        raise
    except Exception as e:  # noqa: BLE001
        enviar_foto(pg, f"estoque: {str(e)[:150]}", resumo_tela(pg))
        raise
    finally:
        ctx.close()
    log(f"  baixado: {arq.name} ({arq.stat().st_size // 1024} KB)")
    if not enviar:
        return 1, 0, 0, f"estoque baixado em {arq} (sem enviar)"
    r = api(token, "estoque_importar", {"arquivo": arq.name, **({"esperado": esperado} if esperado else {})}, arq.read_bytes())
    for linha in r.get("log") or []:
        log("  " + linha)
    linhas = r.get("log") or ["estoque importado"]
    return 1, 1, 0, (linhas[1] if len(linhas) > 1 else linhas[0])[:200]


def cmd_entrar_upseller(args, cfg):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = abrir_navegador(p, cfg, visivel=True)
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto(f"{UPSELLER}/pt/inventory/list")
        print("Faça login no UpSeller na janela que abriu (a senha fica só no navegador do coletor, nunca no nubi).")
        print("Quando a Lista de Estoque aparecer, o login fica salvo e a janela fecha sozinha.")
        fim, ok = time.time() + 600, False
        while time.time() < fim:
            try:
                if pg.get_by_text("Importar & Exportar").count():
                    ok = True
                    break
            except Exception:  # noqa: BLE001
                pass
            time.sleep(2)
        if ok:
            time.sleep(3)
            guardar_sessao(ctx)
        ctx.close()
        if not ok:
            print("Tempo esgotado (10 min) sem ver a Lista de Estoque.")
            return 1
        print("OK: login do UpSeller feito. Testando se o coletor entra sozinho, sem janela…")
        for visivel in (False, True):
            ctx = abrir_navegador(p, cfg, visivel=visivel)
            try:
                _upseller_lista(ctx.pages[0] if ctx.pages else ctx.new_page())
                guardar_sessao(ctx)
                cfg["upseller_ver"] = visivel
                salvar_config(cfg)
                print("OK: " + ("funciona com a janela aberta (ela aparece e some sozinha)." if visivel
                                else "funciona sem janela. O estoque vai atualizar sozinho de madrugada."))
                return 0
            except Falha as e:
                print(f"  {'Com' if visivel else 'Sem'} janela não entrou: {str(e)[:160]}")
            finally:
                ctx.close()
        print("Me mande esta mensagem e a foto ~/.nubi-coletor/ultimo-erro.png.")
        return 1


# ---------------------------------------------------------------------------
# Gestor Seller: Gerenciamento → Produtos internos → Importar por planilha → Selecionar planilha →
# Período de atualização (deixa o padrão: custos só nas novas vendas a partir de hoje) → Salvar
# ---------------------------------------------------------------------------

def baixar_do_nubi(token, rota, params=None):
    """Arquivo (bytes, nome) de uma rota do nubi que devolve download."""
    token = TOKEN["troca"].get(token, token)
    q = urllib.parse.urlencode(dict(params or {}, r=rota))
    req = urllib.request.Request(f"{NUBI}/api/app?{q}", headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            nome = re.search(r'filename="([^"]+)"', r.headers.get("Content-Disposition") or "")
            return r.read(), (nome.group(1) if nome else "import_gestor_seller.xlsx")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode()).get("erro")
        except Exception:  # noqa: BLE001
            msg = None
        raise Falha(msg or f"nubi respondeu {e.code}")


def _gestor_produtos(pg):
    pg.goto(f"{GESTOR}/management/products", wait_until="domcontentloaded", timeout=90000)
    botao = pg.get_by_text("Importar por planilha").first
    try:
        botao.wait_for(state="visible", timeout=60000)
    except Exception:  # noqa: BLE001
        u = urllib.parse.urlparse(pg.url)
        if "/auth" in u.path or pg.locator("input[type=password]:visible").count():
            raise SessaoExpirada("O Gestor Seller pediu login de novo. No Mac mini, rode: ~/.nubi-coletor/coletor entrar-gestor "
                                 + diagnostico(pg))
        raise Falha("a tela Produtos internos do Gestor Seller não carregou (sem 'Importar por planilha') " + diagnostico(pg))
    devagar(3)
    return botao


def importar_gestor(pg, arq):
    """Importa a planilha em Produtos internos; devolve o que a tela disse depois do Salvar."""
    _gestor_produtos(pg).click()
    janela = pg.locator("[role=dialog], .modal-content, .ant-modal-content").filter(has_text="Importar por planilha").last
    janela.wait_for(state="visible", timeout=30000)
    devagar(1.5)
    arquivo = janela.locator("input[type=file]")
    if arquivo.count():
        arquivo.first.set_input_files(str(arq))
    else:
        with pg.expect_file_chooser(timeout=30000) as fc:
            janela.get_by_text("Selecionar planilha").first.click()
        fc.value.set_files(str(arq))
    devagar(2)
    texto = janela.inner_text()
    if "padrão" not in texto and "padrao" not in texto.lower():
        raise Falha("o Período de atualização não está no padrão (custos só nas novas vendas); não importei " + diagnostico(pg))
    log(f"  planilha {arq.name} selecionada; período de atualização: padrão (custos nas novas vendas a partir de hoje)")
    salvar = janela.get_by_role("button", name=re.compile(r"^\s*Salvar\s*$"))
    fim = time.time() + 30
    while not salvar.is_enabled() and time.time() < fim:
        time.sleep(1)
    salvar.click()
    log("  Salvar clicado; esperando o Gestor Seller processar…")
    fim = time.time() + 300
    while time.time() < fim:
        time.sleep(3)
        if not janela.is_visible():
            break
    time.sleep(3)
    avisos = pg.evaluate("""() => [...document.querySelectorAll('[role=alert],[role=status],.toast,.Toastify__toast,.swal2-popup,.notification,.alert')]
        .map(e => (e.innerText || '').trim()).filter(Boolean).join(' | ')""")[:500]
    ainda_aberta = janela.is_visible()
    enviar_foto(pg, "gestor: depois do Salvar", resumo_tela(pg))            # para conferir o resultado de fora do Mac
    if ainda_aberta:
        raise Falha("a janela de importação do Gestor Seller não fechou em 5 min: " + (avisos or janela.inner_text()[:300]))
    if re.search(r"erro|falh|inv[aá]lid", avisos, re.I):
        raise Falha("o Gestor Seller recusou a planilha: " + avisos)
    return avisos or "janela fechou sem mensagem de erro"


def _normalizar_sku(sku):
    """trim + upper + sem caracteres invisíveis (categoria Unicode "Cf", ex.: espaço de largura zero)."""
    if not sku:
        return ""
    limpo = "".join(ch for ch in str(sku) if unicodedata.category(ch) != "Cf").replace("\xa0", " ")
    return limpo.strip().upper()


def _diagnostico_sku_nao_bate(sku_original, custo, achou, etapa, existe_em_estoque):
    """Card #57: o texto do erro traz os 4 campos (sku_original, sku_normalizado, etapa da busca, se existe
    na última foto de estoque_itens) para diagnosticar sem adivinhar — sem bloquear nem mudar custo."""
    existe_txt = {True: "sim", False: "não"}.get(existe_em_estoque, "sem_dados")
    tela = str(achou or "SKU não encontrado")[:160]
    return (f"conferência: no Gestor Seller o custo de {sku_original} não bateu com a planilha ({custo:.2f}); "
            f"a tela mostra: {tela}. "
            f"[sku_original={sku_original} sku_normalizado={_normalizar_sku(sku_original)} etapa={etapa} "
            f"existe_em_estoque={existe_txt}]")


def _linha_do_sku(pg, sku):
    """Texto da "linha" do produto na lista do Gestor. A lista não é uma tabela (tr): é feita de blocos (div), por isso a
    conferência nunca achava o SKU (25/09). Acha o elemento com o SKU exato e sobe até o bloco que também tem o preço."""
    try:
        return pg.evaluate("""sku => {
          const alvo = sku.trim().toUpperCase();
          const preco = /\\d[\\d.]*[.,]\\d{2}\\b/;
          for (const el of document.querySelectorAll('body *')) {
            if (el.children.length || (el.textContent || '').trim().toUpperCase() !== alvo) continue;
            if (!el.getClientRects().length) continue;               // escondido não conta
            let p = el.parentElement;
            for (let i = 0; p && i < 8; i++, p = p.parentElement) {
              const t = p.innerText || '';
              if (t.length > 800) break;
              if (preco.test(t.replace(alvo, ''))) return t;
            }
          }
          return '';
        }""", sku) or ""
    except Exception:  # noqa: BLE001
        return ""


def conferir_gestor(pg, amostra, token=None):
    """Pesquisa alguns SKUs em Produtos internos e confere o Preço de Custo com a planilha. Devolve o resumo."""
    busca = pg.get_by_placeholder(re.compile("Pesquisar")).first
    ok = []
    for a in amostra:
        achou, etapa = None, "campo de busca (Enter)"
        for tentativa in range(3):                   # o Gestor pode levar alguns segundos para gravar
            if tentativa == 0:
                etapa = "campo de busca (Enter)"
                busca.fill("")
                busca.fill(a["sku"])
                busca.press("Enter")                 # 25/09: só preencher não disparava a busca ("SKU não encontrado")
            else:                                    # plano B: busca pelo endereço (?search=); plano C: pelo título
                termo = a["sku"] if tentativa == 1 or not a.get("titulo") else a["titulo"][:60]
                etapa = "busca por link (?search=)" if tentativa == 1 or not a.get("titulo") else "busca pelo título"
                pg.goto(f"{GESTOR}/management/products?search={urllib.parse.quote(termo)}",
                        wait_until="domcontentloaded", timeout=90000)
                busca = pg.get_by_placeholder(re.compile("Pesquisar")).first
            time.sleep(4)
            txt = _linha_do_sku(pg, a["sku"])
            nums = [float(x.replace(".", "").replace(",", ".")) if "," in x else float(x) for x in re.findall(r"\d[\d.]*[.,]\d{2}\b", txt)]
            if any(abs(n - a["custo"]) < 0.011 for n in nums):
                achou = True
                break
            achou = txt or None
            time.sleep(6)
        if achou is not True:
            existe = None
            try:
                existe = api(token, "estoque_sku_existe", {"sku": _normalizar_sku(a["sku"])}, timeout=20).get("existe")
            except Exception:  # noqa: BLE001
                pass                                  # sem token/nubi fora do ar: fica "sem_dados", não bloqueia o erro original
            raise Falha(_diagnostico_sku_nao_bate(a["sku"], a["custo"], achou, etapa, existe))
        ok.append(f"{a['sku']} {a['custo']:.2f}")
    busca.fill("")
    return "custo conferido no Gestor: " + ", ".join(ok) if ok else ""


def coletar_gestor(p, cfg, token):
    dados, nome = baixar_do_nubi(token, "estoque_gestor")
    destino = PASTA / "gestor"
    destino.mkdir(parents=True, exist_ok=True)
    arq = destino / nome
    arq.write_bytes(dados)
    log(f"  planilha do Gestor Seller baixada do nubi: {nome} ({len(dados) // 1024} KB)")
    ctx = abrir_navegador(p, cfg, visivel=True if cfg.get("gestor_ver") else None)
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        msg = importar_gestor(pg, arq)
        try:
            amostra = api(token, "gestor_amostra", timeout=30).get("skus") or []
        except Exception:  # noqa: BLE001
            amostra = []
        if amostra:
            conf = conferir_gestor(pg, amostra, token)
            log(f"  {conf}")
            msg = conf
        guardar_sessao(ctx)
    except SessaoExpirada:
        enviar_foto(pg, "gestor: login vencido", resumo_tela(pg))
        raise
    except Exception as e:  # noqa: BLE001
        enviar_foto(pg, f"gestor: {str(e)[:150]}", resumo_tela(pg))
        raise
    finally:
        ctx.close()
    log(f"  Gestor Seller: {msg}")
    return 1, 1, 0, f"planilha {nome} importada no Gestor Seller ({msg[:120]})"


def cmd_entrar_gestor(args, cfg):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = abrir_navegador(p, cfg, visivel=True)
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto(f"{GESTOR}/management/products")
        print("Faça login no Gestor Seller na janela que abriu (a senha fica só no navegador do coletor, nunca no nubi).")
        print("Quando a tela Produtos aparecer, o login fica salvo e a janela fecha sozinha.")
        fim, ok = time.time() + 600, False
        while time.time() < fim:
            try:
                if pg.get_by_text("Importar por planilha").count():
                    ok = True
                    break
                if "/management/products" not in pg.url and "/auth" not in pg.url:
                    pg.goto(f"{GESTOR}/management/products")      # depois do login ele cai em Vendas: volta para Produtos
            except Exception:  # noqa: BLE001
                pass
            time.sleep(3)
        if ok:
            time.sleep(3)
            guardar_sessao(ctx)
        ctx.close()
        if not ok:
            print("Tempo esgotado (10 min) sem ver a tela Produtos do Gestor Seller.")
            return 1
        print("OK: login do Gestor Seller feito. Testando se o coletor entra sozinho, sem janela…")
        for visivel in (False, True):
            ctx = abrir_navegador(p, cfg, visivel=visivel)
            try:
                _gestor_produtos(ctx.pages[0] if ctx.pages else ctx.new_page())
                guardar_sessao(ctx)
                cfg["gestor_ver"] = visivel
                salvar_config(cfg)
                print("OK: " + ("funciona com a janela aberta." if visivel else "funciona sem janela."))
                return 0
            except Falha as e:
                print(f"  {'Com' if visivel else 'Sem'} janela não entrou: {str(e)[:160]}")
            finally:
                ctx.close()
        return 1


VIGIA_PLIST = Path.home() / "Library" / "LaunchAgents" / "com.nubi.coletor.vigia.plist"


def instalar_vigia():
    """
    Vigia de 15 em 15 minutos (launchd): pergunta ao nubi se há versão nova do coletor ou um pedido de coleta
    ("Rodar coleta agora" no site) e, se houver, atualiza e roda a coleta na hora, sem esperar as 7h.
    """
    if sys.platform != "darwin":
        return
    wrapper = PASTA / "coletor"
    if not wrapper.exists():
        return
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.nubi.coletor.vigia</string>
  <key>ProgramArguments</key>
  <array><string>{wrapper}</string><string>vigiar</string></array>
  <key>StartInterval</key><integer>60</integer>
  <key>EnvironmentVariables</key><dict><key>NUBI_VIGIA</key><string>1</string>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
  <key>StandardOutPath</key><string>{PASTA}/vigia.log</string>
  <key>StandardErrorPath</key><string>{PASTA}/vigia.log</string>
</dict>
</plist>
"""
    if os.environ.get("NUBI_VIGIA") or os.environ.get("XPC_SERVICE_NAME") == "com.nubi.coletor.vigia":
        return                                          # dentro do próprio vigia: recarregar o launchd o mataria
    try:
        ativo = subprocess.run(["launchctl", "list", "com.nubi.coletor.vigia"], check=False, capture_output=True).returncode == 0
        if ativo and VIGIA_PLIST.exists() and VIGIA_PLIST.read_text(encoding="utf-8") == xml:
            return
        VIGIA_PLIST.parent.mkdir(parents=True, exist_ok=True)
        VIGIA_PLIST.write_text(xml, encoding="utf-8")
        subprocess.run(["launchctl", "unload", str(VIGIA_PLIST)], check=False, capture_output=True)
        r = subprocess.run(["launchctl", "load", "-w", str(VIGIA_PLIST)], check=False, capture_output=True, text=True)
        ok = subprocess.run(["launchctl", "list", "com.nubi.coletor.vigia"], check=False, capture_output=True).returncode == 0
        if ok:
            print("Vigia instalado e ativo: confere a cada 15 min se há versão nova ou pedido de coleta.", flush=True)
        else:
            print(f"(o vigia não ficou ativo: {(r.stderr or r.stdout or '').strip()[:300]}. "
                  f"Rode: launchctl load -w {VIGIA_PLIST})", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"(não consegui instalar o vigia: {e})", flush=True)


def _parar_coleta_velha():
    """
    Coleta rodando com o código antigo (o coletor foi atualizado depois que ela começou): ela não recebe as correções
    (ex.: login do nubi que vencia em 1 h e fazia todo envio falhar). Para ela; a próxima continua de onde parou.
    """
    pid = _outra_rodando()
    if not pid:
        return False
    try:
        comecou = (PASTA / "rodando.pid").stat().st_mtime
        if Path(__file__).stat().st_mtime <= comecou + 60:
            return False                                   # está rodando com o código atual: deixa terminar
        try:
            pg = os.getpgid(pid)
            # o Chrome da coleta é filho dela: para o grupo todo (se não for o do próprio vigia)
            os.killpg(pg, signal.SIGTERM) if pg != os.getpgid(0) else os.kill(pid, signal.SIGTERM)
        except OSError:
            os.kill(pid, signal.SIGTERM)
        for _ in range(30):
            time.sleep(2)
            if not _outra_rodando():
                break
        print(f"{datetime.now():%d/%m %H:%M} vigia: coleta {pid} rodava com o coletor antigo; parei para rodar a versão nova",
              flush=True)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Despachante: a cada minuto executa os comandos pedidos na Central (lista fechada), manda a saída ao vivo,
# faz o Hermes/Qwen responderem na Sala quando chamados e informa o estado do Mac.
# ---------------------------------------------------------------------------

def _ollama_bin():
    for c in ("/usr/local/bin/ollama", "/opt/homebrew/bin/ollama", "/Applications/Ollama.app/Contents/Resources/ollama"):
        if Path(c).exists():
            return c
    return "ollama"


MODELOS_OK = ("hermes3:8b", "qwen3:8b", "nomic-embed-text")


def comando_mac(chave, arg=""):
    """Lista FECHADA: cada chave vira um comando fixo; nada vindo de fora vira comando livre."""
    c = str(PASTA / "coletor")
    ol = _ollama_bin()
    tabela = {
        "status": [c, "status"], "diario": [c, "diario"], "atualizar": [c, "atualizar"],
        "parar_coleta": [c, "parar"], "vigia_reativar": [c, "vigia-reativar"],
        "hermes": [c, "hermes"], "qwen": [c, "qwen"], "estoque": [c, "estoque"], "gestor": [c, "gestor"],
        "entrar": [c, "entrar"], "entrar_upseller": [c, "entrar-upseller"], "entrar_gestor": [c, "entrar-gestor"],
        "entrar_auto_nubimetrics": [c, "entrar-auto", "nubimetrics"], "entrar_auto_upseller": [c, "entrar-auto", "upseller"],
        "entrar_auto_gestor": [c, "entrar-auto", "gestor"],
        "ferreiro_status": [c, "programar", "0"],
        "vigia_status": ["/bin/launchctl", "list"],
        "log_vigia": ["/usr/bin/tail", "-n", "80", str(PASTA / "vigia.log")],
        "log_coleta": ["/usr/bin/tail", "-n", "120", str(PASTA / "coletor.log")],
        "ollama_modelos": [ol, "list"], "ollama_rodando": [ol, "ps"],
        "espaco": ["/bin/df", "-h", str(Path.home())],
    }
    if chave == "baixar_modelo":
        return [ol, "pull", arg] if arg in MODELOS_OK else None
    if chave == "hermes_card":
        return [c, "hermes-card", arg] if str(arg).isdigit() else None
    if chave == "programar_card":
        return [c, "programar", arg] if str(arg).isdigit() else None
    return tabela.get(chave)


def _estado_desp():
    try:
        return json.loads((PASTA / "despachante.json").read_text())
    except (OSError, ValueError):
        return {"rodando": {}, "sala_ult": 0}


def _salvar_desp(e):
    try:
        (PASTA / "despachante.json").write_text(json.dumps(e))
    except OSError:
        pass


def _info_mac():
    import shutil
    info = {"coleta_rodando": bool(_outra_rodando()), "disco_livre_gb": round(shutil.disk_usage(str(Path.home())).free / 1e9, 1)}
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=4) as r:
            info["ollama"] = True
            info["modelos"] = [m.get("name") for m in json.loads(r.read().decode()).get("models", [])]
    except Exception:  # noqa: BLE001
        info["ollama"] = False
    try:
        info["vigia_ativo"] = subprocess.run(["/bin/launchctl", "list", "com.nubi.coletor.vigia"], capture_output=True).returncode == 0
    except OSError:
        pass
    info["versao"] = hashlib.sha1(Path(__file__).read_bytes()).hexdigest()[:10]
    return info


def despachar(cfg):
    """Um ciclo do despachante (roda dentro do vigia, a cada minuto)."""
    est = _estado_desp()
    saidas = []
    for cid, r in list(est["rodando"].items()):          # comandos em andamento: manda a saída; terminou = status
        logf, rcf = Path(r["log"]), Path(r["log"] + ".rc")
        txt = logf.read_text(errors="replace")[-12000:] if logf.exists() else ""
        fim = rcf.exists()
        rc = int((rcf.read_text().strip() or "1")) if fim else None
        if not fim and time.time() - r["inicio"] > 3 * 3600:
            fim, rc, txt = True, 124, txt + "\n(parado: passou de 3 horas)"
        saidas.append({"id": int(cid), "saida": txt, "status": ("ok" if rc == 0 else "erro") if fim else "rodando"})
        if fim:
            est["rodando"].pop(cid, None)
    token = token_nubi(cfg)
    r = api(token, "mac_tick", corpo={"info": _info_mac(), "saidas": saidas, "sala_ult": est.get("sala_ult", 0)}, timeout=40)
    for p in r.get("pendentes", []):
        argv = comando_mac(p.get("comando"), p.get("arg") or "")
        if not argv:
            api(token, "mac_tick", corpo={"saidas": [{"id": p["id"], "status": "recusado",
                                                     "saida": "Comando fora da lista permitida: recusado."}]}, timeout=30)
            continue
        logf = PASTA / "comandos" / f"{p['id']}.log"
        logf.parent.mkdir(parents=True, exist_ok=True)
        import shlex
        linha = " ".join(shlex.quote(a) for a in argv)
        subprocess.Popen(["/bin/sh", "-c", f"{linha} > {shlex.quote(str(logf))} 2>&1; echo $? > {shlex.quote(str(logf))}.rc"],
                         start_new_session=True)
        est["rodando"][str(p["id"])] = {"log": str(logf), "inicio": time.time()}
    # Sala: o Hermes/Qwen respondem quando alguém chama (@hermes, @qwen) e na reunião diária. Rodam em SEGUNDO PLANO
    # (o modelo local leva minutos e travava o vigia, que ficava sem pegar pedidos); mensagem com mais de 30 min é ignorada.
    info = _info_mac() if r.get("sala") else {}
    chamar = []
    for m in r.get("sala", []):
        est["sala_ult"] = max(est.get("sala_ult", 0), m["id"])
        try:
            velha = (datetime.now(timezone.utc) - datetime.fromisoformat(str(m.get("criado_em")).replace("Z", "+00:00"))).total_seconds() > 1800
        except ValueError:
            velha = False
        t = (m.get("texto") or "").lower()
        for chave in ("hermes", "qwen"):
            if not velha and (f"@{chave}" in t or t.startswith("reunião diária")) and chave not in chamar:
                chamar.append(chave)
    for chave in chamar:
        modelo = LOCAIS[chave][1]
        pid = (est.get("sala_pid") or {}).get(chave)
        try:
            if pid:
                os.kill(int(pid), 0)
                continue                                 # ainda respondendo a chamada anterior
        except (OSError, ValueError):
            pass
        if info.get("ollama") and any(str(x).startswith(modelo.split(":")[0]) for x in (info.get("modelos") or [])):
            with open(PASTA / f"{chave}.log", "a") as saida:
                pr = subprocess.Popen([str(PASTA / "coletor"), chave], stdout=saida, stderr=subprocess.STDOUT, start_new_session=True)
            est.setdefault("sala_pid", {})[chave] = pr.pid
    _salvar_desp(est)
    return 0


def _soltar(cmd, env=None):
    """Roda a tarefa (coleta, estoque, Gestor) SEPARADA do vigia: antes o vigia virava a coleta (execv) e, enquanto ela
    durava (horas), o launchd não chamava o vigia de novo — o despachante (Central, cards, Hermes) ficava parado."""
    with open(PASTA / "vigia.log", "a") as saida:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), *([cmd] if isinstance(cmd, str) else cmd)],
                         stdout=saida, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, start_new_session=True, cwd=str(PASTA),
                         env={**os.environ, **env} if env else None)
    return 0


def cmd_vigiar():
    """Chamado pelo launchd a cada minuto: despachante; a cada 15 min, versão nova do coletor ou pedido de coleta."""
    cfg0 = ler_config()
    try:
        despachar(cfg0)
    except Exception as e:  # noqa: BLE001
        print(f"{datetime.now():%d/%m %H:%M} despachante: {e}", flush=True)
    try:
        if _falhas_pendentes() and not _pid_vivo(PASTA / "hermes-vigia.pid"):
            print(f"{datetime.now():%d/%m %H:%M} vigia: falha nova -> chamando o Hermes (vigia de erros)", flush=True)
            _soltar("hermes-vigia")
    except Exception as e:  # noqa: BLE001
        print(f"{datetime.now():%d/%m %H:%M} vigia de erros: {e}", flush=True)
    marca = PASTA / "vigia.ultimo"
    try:
        if time.time() - marca.stat().st_mtime < 4 * 60:      # a cada ~5 min: versão nova, pedidos e horários das rotinas
            return 0
    except OSError:
        pass
    try:
        marca.touch()
    except OSError:
        pass
    _parar_coleta_velha()
    if _outra_rodando():
        return 0
    motivo = None
    try:
        novo = urllib.request.urlopen(f"{NUBI}/coletor/coletor.py", timeout=20).read()
        if novo and novo != Path(__file__).read_bytes():
            compile(novo, "coletor.py", "exec")
            motivo = "versão nova do coletor"
            _soltar("repetir-falhas")    # a correção pode ser para o que falhou hoje: o Hermes roda de novo (estoque/Gestor)
    except Exception:  # noqa: BLE001
        pass
    cfg = ler_config()
    pedido = None
    try:
        token = token_nubi(cfg)
        pedido = api(token, "coletor_pedido", timeout=30).get("pedido")
        if pedido and pedido.get("tarefa") == "gestor":
            api(token, "coletor_pedido_ok", corpo={"id": pedido["id"], "tarefa": "gestor", "resultado": "importação iniciada"}, timeout=30)
            print(f"{datetime.now():%d/%m %H:%M} vigia: pedido no site -> importando a planilha no Gestor Seller", flush=True)
            return _soltar("gestor")
        if pedido and pedido.get("tarefa") == "estoque":
            api(token, "coletor_pedido_ok", corpo={"id": pedido["id"], "tarefa": "estoque", "resultado": "estoque iniciado"}, timeout=30)
            print(f"{datetime.now():%d/%m %H:%M} vigia: pedido no site -> atualizando o estoque do UpSeller", flush=True)
            return _soltar("estoque")
        if pedido:
            api(token, "coletor_pedido_ok", corpo={"id": pedido["id"], "tarefa": pedido.get("tarefa") or "diario",
                                                   "resultado": "coleta iniciada"}, timeout=30)
            motivo = motivo or f"pedido no site: {pedido.get('motivo') or 'rodar coleta agora'}"
        if not motivo:
            motivo = _coleta_na_hora(cfg, token)
        if not motivo and _estoque_na_hora(cfg, token):
            print(f"{datetime.now():%d/%m %H:%M} vigia: hora do estoque do UpSeller -> atualizando", flush=True)
            return _soltar("estoque")
        if not motivo and _na_hora(cfg, token, "gestor_pendente", "gestor_tentativas"):
            print(f"{datetime.now():%d/%m %H:%M} vigia: hora do Gestor Seller -> importando a planilha", flush=True)
            return _soltar("gestor")
        if (not motivo and _fora_da_janela_coleta() and not _outra_rodando()
                and _na_hora(cfg, token, "memoria_pendente", "memoria_tentativas")):
            print(f"{datetime.now():%d/%m %H:%M} vigia: hora da memória (Hermes documenta, Qwen revisa)", flush=True)
            return _soltar("hermes-memoria")
    except Exception as e:  # noqa: BLE001
        print(f"{datetime.now():%d/%m %H:%M} vigia: sem contato com o nubi ({e})", flush=True)
    if not motivo:
        return 0
    print(f"{datetime.now():%d/%m %H:%M} vigia: {motivo} -> rodando a coleta", flush=True)
    return _soltar("diario")


def _sincronizar_agenda(horario):
    """O agendamento do launchd (com.nubi.coletor) segue o horário da rotina 'coleta' do nubi."""
    plist = Path.home() / "Library" / "LaunchAgents" / "com.nubi.coletor.plist"
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(horario or ""))
    if sys.platform != "darwin" or not plist.exists() or not m:
        return
    txt = plist.read_text(encoding="utf-8")
    novo = re.sub(r"(<key>Hour</key>\s*<integer>)\d+", rf"\g<1>{int(m.group(1))}", txt)
    novo = re.sub(r"(<key>Minute</key>\s*<integer>)\d+", rf"\g<1>{int(m.group(2))}", novo)
    if novo != txt:
        plist.write_text(novo, encoding="utf-8")
        subprocess.run(["launchctl", "unload", str(plist)], check=False, capture_output=True)
        subprocess.run(["launchctl", "load", str(plist)], check=False, capture_output=True)
        print(f"{datetime.now():%d/%m %H:%M} vigia: coleta diária agendada para {horario} (rotina do nubi)", flush=True)


def _coleta_na_hora(cfg, token):
    """Rotina 'coleta' no horário do nubi (ex.: 01:00): a coleta diária ainda não rodou hoje -> motivo para rodar."""
    try:
        r = api(token, "coleta_pendente", timeout=30)
    except Exception:  # noqa: BLE001
        return None                                    # nubi antigo sem a rota: fica o agendamento do launchd
    _sincronizar_agenda(r.get("horario"))
    if not r.get("rodar"):
        return None
    hoje = date.today().isoformat()
    tent = {k: v for k, v in (cfg.get("coleta_tentativas") or {}).items() if k == hoje}
    if tent.get(hoje, 0) >= 2:
        return None
    tent[hoje] = tent.get(hoje, 0) + 1
    cfg["coleta_tentativas"] = tent
    salvar_config(cfg)
    return f"horário da coleta ({r.get('horario')})"


def _estoque_na_hora(cfg, token):
    """Rotina 'estoque' (madrugada): o nubi diz se está na hora e ainda não rodou hoje; no máximo 3 tentativas por dia."""
    return _na_hora(cfg, token, "estoque_pendente", "estoque_tentativas")


def _fora_da_janela_coleta():
    """Fora do horário de coleta (00:30-06:40 em Brasília): a rotina 'memoria' (Hermes/Qwen) nunca roda durante a
    coleta, mesmo se chamada fora do vigia (ex.: na mão, ou pelo cron do launchd um pouco atrasado)."""
    hhmm = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime("%H:%M")
    return not ("00:30" <= hhmm < "06:40")


def _na_hora(cfg, token, rota, chave):
    """Rotina do Mac com horário no nubi (estoque, gestor): está na hora e ainda não deu certo hoje? Máx. 3 tentativas/dia."""
    try:
        r = api(token, rota, timeout=30)
    except Exception:  # noqa: BLE001
        return False
    if not r.get("rodar"):
        return False
    hoje = date.today().isoformat()
    tent = {k: v for k, v in (cfg.get(chave) or {}).items() if k == hoje}
    if tent.get(hoje, 0) >= 3:
        return False
    tent[hoje] = tent.get(hoje, 0) + 1
    cfg[chave] = tent
    salvar_config(cfg)
    return True


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


OLLAMA = "http://localhost:11434/v1/chat/completions"
PAPEL_HERMES = ("Você é o Hermes, agente de IA do nubi que roda de graça no Mac mini do dono (Ollama). Seu forte: trabalho de "
                "volume e rotina 24h (vigiar erros, ler logs, criar testes, documentar, organizar a memória do projeto). "
                "Está no grupo com o dono, ChatGPT (Codex), DeepSeek e Claude (que coordena e decide). Responda à última "
                "mensagem ou pauta do grupo: somente em português do Brasil, direto, no máximo 6 linhas, sem elogios genéricos, "
                "sem repetir o que os outros disseram e sem perguntar no final. Traga a sua opinião, um risco e no máximo 2 "
                "sugestões concretas que VOCÊ pode executar no Mac (vigiar, ler logs, testes, documentação, memória). "
                "Não invente números.")


PAPEL_QWEN = ("Você é o Qwen, revisor do nubi que roda de graça no Mac mini (Ollama). Seu papel: conferir o trabalho do Hermes "
              "e do time (memória, caixa de conhecimento, pacotes), apontando contradições, dados velhos, duplicados e riscos. "
              "Está no grupo com o dono, Hermes, ChatGPT (Codex), DeepSeek, gpt-oss e Claude (que coordena e decide). Responda "
              "à última mensagem ou pauta: somente em português do Brasil, no máximo 6 linhas, sem elogios genéricos e sem "
              "perguntar no final. Traga o que você conferiu, um risco e no máximo 2 sugestões concretas. Não invente números.")
LOCAIS = {"hermes": ("Hermes", "hermes3:8b", PAPEL_HERMES), "qwen": ("Qwen (revisor)", "qwen3:8b", PAPEL_QWEN)}

PAPEL_HERMES_MEMORIA = (
    "Você é o Hermes, agente de IA do nubi (Ollama, grátis, no Mac mini). Tarefa: ler mensagens da Sala de reunião e "
    "cards concluídos do quadro de Desenvolvimento (a seguir) e registrar na caixa de conhecimento o que for de "
    "verdade uma decisão, um aprendizado ou um procedimento novo, para os outros agentes lerem depois. Ignore "
    "conversa sem substância (saudação, combinação de horário, repetição do que já foi dito). Não invente números "
    "nem fatos que não estejam no texto. Responda SOMENTE um JSON, sem markdown e sem comentário, no formato "
    '[{"tipo": "decisao|aprendizado|procedimento", "titulo": "...", "texto": "...", "fonte": "..."}] — use a "fonte" '
    "exatamente como veio no item de origem (ex.: reuniao_mensagens:123). Português do Brasil. Nada relevante: [].")

PAPEL_QWEN_MEMORIA = (
    "Você é o Qwen, revisor do nubi (Ollama, grátis, no Mac mini). Confira os registros que o Hermes propôs para a "
    "caixa de conhecimento: aponte contradição com o que já existe, duplicidade entre os próprios registros ou erro "
    "óbvio. Responda SOMENTE um JSON (lista, na MESMA ORDEM e quantidade dos registros recebidos), no formato "
    '[{"nota": "..."}], uma frase curta por registro (ex.: "Aprovado, sem contradição." ou "Duplicado com o '
    'registro 2 — mesmo assunto."). Português do Brasil.')


def cmd_hermes(args, cfg):
    """Um agente local (Ollama, no Mac) lê a Sala de reunião do nubi e posta a opinião dele (Hermes ou Qwen)."""
    autor, padrao, papel = LOCAIS[getattr(args, "agente", "hermes")]
    args.modelo = args.modelo or padrao
    token = token_nubi(cfg)
    sala = api(token, "reuniao", {"sistema": "1"})
    msgs = sala.get("mensagens") or []
    hist = "\n".join(f"[{m['autor']}] {m['texto'][:2500]}" for m in msgs[-args.ultimas:])
    pedido = papel + (f"\nPERGUNTA DO DONO PARA VOCÊ: {args.pergunta}" if args.pergunta else "") + f"\n\nCONVERSA:\n{hist}"
    corpo = {"model": args.modelo, "stream": False,
             "messages": [{"role": "system", "content": sala.get("sistema") or ""}, {"role": "user", "content": pedido}]}
    print(f"{autor} ({args.modelo}) lendo as últimas {min(len(msgs), args.ultimas)} mensagens da Sala…", flush=True)
    inicio = datetime.now(timezone.utc).isoformat()

    def chamar(c):
        req = urllib.request.Request(OLLAMA, data=json.dumps(c).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=900) as r:
            j = json.loads(r.read().decode())
        u = j.get("usage") or {}
        return j["choices"][0]["message"]["content"].strip(), int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
    apelido = ""
    try:
        texto, t_in, t_out = chamar(corpo)
        if not (sala.get("apelidos") or {}).get(autor):
            # primeira vez: o agente escolhe o próprio apelido no time
            ap, _, _ = chamar({"model": args.modelo, "stream": False, "messages": [{"role": "user", "content":
                              f"Você é o {autor}, agente de IA do nubi que roda no Mac mini. "
                              "Escolha um apelido curto para você no time (1 ou 2 palavras, em português). "
                              "Responda SOMENTE o apelido."}]})
            apelido = re.sub(r"[\"'*_`.]", "", (ap.splitlines() or [""])[0]).strip()[:30]
    except urllib.error.URLError as e:
        print(f"Não consegui falar com o Ollama ({e}). Abra o app Ollama (lhama na barra de cima) e confira: "
              f"ollama list  (o modelo {args.modelo} precisa aparecer).")
        return 1
    if not texto:
        print(f"O {autor} devolveu resposta vazia; nada foi postado.")
        return 1
    print("\n" + texto + "\n", flush=True)
    api(token, "reuniao_postar", corpo={"autor": autor, "texto": texto, "modelo": args.modelo, "inicio": inicio,
                                         "tokens_in": t_in, "tokens_out": t_out, "apelido": apelido}, metodo="POST")
    print(f"OK: resposta do {autor} postada na Sala de reunião." + (f" Apelido escolhido: {apelido}" if apelido else ""))
    return 0


def cmd_hermes_card(args, cfg):
    """O Hermes (Ollama no Mac, grátis) faz um card do quadro do qual é responsável e entrega no nubi (o coordenador testa)."""
    token = token_nubi(cfg)
    x = api(token, "tarefa_eventos", {"id": args.id})
    t, evs = x["tarefa"], x.get("eventos") or []
    sala = api(token, "reuniao", {"sistema": "1"})
    conversa = "\n".join(f"[{e['autor']}] {e['texto'][:1200]}" for e in evs[-15:])
    pedido = (PAPEL_HERMES.split(" Responda à última")[0] + "\n\nVocê é o RESPONSÁVEL por este card e vai entregá-lo agora.\n"
              f"CARD #{t['id']}: {t['titulo']}\n{t.get('descricao') or ''}\n\nHISTÓRICO (corrija o que foi reprovado):\n{conversa}\n\n"
              "Entregue o RESULTADO COMPLETO em markdown, em português do Brasil. Você não edita código nem roda comandos: se o card "
              "só puder ser concluído com código, entregue o plano e termine com uma linha exatamente assim: PRECISA_CODIGO. "
              "Não invente números nem fatos.")
    corpo = {"model": args.modelo or "hermes3:8b", "stream": False,
             "messages": [{"role": "system", "content": sala.get("sistema") or ""}, {"role": "user", "content": pedido}]}
    print(f"Hermes fazendo o card #{t['id']}…", flush=True)
    req = urllib.request.Request(OLLAMA, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            texto = json.loads(r.read().decode())["choices"][0]["message"]["content"].strip()
    except urllib.error.URLError as e:
        print(f"Não consegui falar com o Ollama ({e}).")
        return 1
    if not texto:
        print("O Hermes devolveu resposta vazia.")
        return 1
    r = api(token, "tarefa_agente_entregar", corpo={"id": t["id"], "autor": "hermes", "texto": texto}, metodo="POST")
    print(f"Entregue. Teste do coordenador: {r.get('resultado')}")
    return 0


def _chamar_ollama(modelo, sistema, pedido, timeout=300):
    corpo = {"model": modelo, "stream": False,
             "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": pedido}]}
    req = urllib.request.Request(OLLAMA, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())["choices"][0]["message"]["content"].strip()


def _json_lista(bruto):
    """Extrai a primeira lista JSON de dentro do texto (o modelo às vezes cerca a resposta de comentário/markdown)."""
    m = re.search(r"\[.*\]", bruto or "", re.S)
    if not m:
        return []
    try:
        j = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    return j if isinstance(j, list) else []


def cmd_hermes_memoria(args, cfg):
    """Card #39 (pedido do Bruno, aprovado 25/09): rotina 'memoria' (1x/dia). O Hermes (Ollama no Mac) lê a Sala e os
    cards concluídos desde a última rodada e propõe registros para a caixa de conhecimento; o Qwen revisa cada um
    (contradição, duplicidade); grava-se por cima de um registro existente do mesmo tipo/título (nunca duplica).
    Nunca roda durante a coleta (00:30-06:40) nem com outra coleta em andamento neste Mac."""
    token = token_nubi(cfg)

    def terminar(rid, ok, mensagem):
        if rid:
            try:
                api(token, "coletor_registrar", corpo={"id": rid, "em_andamento": False, "ok": ok, "mensagem": mensagem,
                                                        "terminado_em": datetime.now(timezone.utc).isoformat()}, metodo="POST")
            except Exception as e:  # noqa: BLE001
                print(f"memória: não consegui registrar o fim ({e})", flush=True)
        print(("OK: " if ok else "ERRO: ") + mensagem, flush=True)
        return 0 if ok else 1

    if not _fora_da_janela_coleta():
        print(f"{datetime.now():%d/%m %H:%M} memória: dentro do horário da coleta (00:30-06:40); não roda agora.", flush=True)
        return 0
    if _outra_rodando():
        print(f"{datetime.now():%d/%m %H:%M} memória: outra coleta rodando neste Mac; espero a próxima chamada.", flush=True)
        return 0

    rid = None
    try:
        rid = api(token, "coletor_registrar", corpo={"tarefa": "memoria", "iniciado_em": datetime.now(timezone.utc).isoformat(),
                                                       "em_andamento": True}, metodo="POST").get("id")
    except Exception as e:  # noqa: BLE001
        print(f"memória: não consegui registrar o início ({e}); sigo sem registrar.", flush=True)

    try:
        pendente = api(token, "conhecimento_pendente")
    except Exception as e:  # noqa: BLE001
        return terminar(rid, False, f"não consegui ler o que está pendente ({e})")
    itens = pendente.get("itens") or []
    if not itens:
        return terminar(rid, True, "nada novo na Sala nem em cards concluídos desde a última rodada")

    resumo = "\n\n".join(f"[{it['fonte']}] {it.get('autor', '')}: {it['texto']}" for it in itens[:60])
    print(f"Hermes lendo {len(itens)} item(ns) novo(s) para a caixa de conhecimento…", flush=True)
    try:
        registros = _json_lista(_chamar_ollama("hermes3:8b", PAPEL_HERMES_MEMORIA, resumo))
    except urllib.error.URLError as e:
        return terminar(rid, False, f"não consegui falar com o Ollama (Hermes): {e}")
    registros = [r for r in registros if isinstance(r, dict) and str(r.get("titulo") or "").strip() and str(r.get("texto") or "").strip()][:20]
    if not registros:
        return terminar(rid, True, "Hermes não achou nada relevante para registrar")

    try:
        revisoes = _json_lista(_chamar_ollama("qwen3:8b", PAPEL_QWEN_MEMORIA, json.dumps(registros, ensure_ascii=False)))
    except urllib.error.URLError as e:
        print(f"memória: Qwen não respondeu ({e}); grava sem revisão.", flush=True)
        revisoes = []

    gravados = 0
    for i, reg in enumerate(registros):
        nota = ""
        if i < len(revisoes) and isinstance(revisoes[i], dict):
            nota = str(revisoes[i].get("nota") or "").strip()
        nota = nota or "Sem revisão registrada."
        titulo = str(reg["titulo"]).strip()[:200]
        tipo = reg.get("tipo") if reg.get("tipo") in ("decisao", "aprendizado", "procedimento") else "aprendizado"
        texto = f"{str(reg['texto']).strip()}\n\n---\nRevisão (Qwen): {nota}"
        try:
            existentes = api(token, "conhecimento", {"q": titulo}).get("itens") or []
        except Exception:  # noqa: BLE001
            existentes = []
        igual = next((e for e in existentes if e.get("tipo") == tipo and str(e.get("titulo") or "").strip().lower() == titulo.lower()), None)
        corpo = {"titulo": titulo, "texto": texto, "tipo": tipo, "fonte": str(reg.get("fonte") or "")[:200], "autor": "Hermes"}
        if igual:
            corpo["id"] = igual["id"]
        try:
            api(token, "conhecimento_salvar", corpo=corpo, metodo="POST")
            gravados += 1
        except Exception as e:  # noqa: BLE001
            print(f"memória: não gravei '{titulo}' ({e})", flush=True)
    return terminar(rid, True, f"{gravados} de {len(registros)} registro(s) memorizado(s) na caixa de conhecimento")


# ---------------------------------------------------------------------------
# Ferreiro: Claude Code no Mac mini, pela API da Anthropic (pedido do Bruno, 25/09). Programador de plantão: o Hermes
# chama na hora quando abre um card 🩺 urgente. Trabalha num clone do projeto no Mac, roda os testes e envia num branch
# próprio (ferreiro/card-N); o Chefe (Claude Code do plano) revisa, junta e publica. Teto de US$ 10 por dia.
# A chave da API fica só no Chaveiro do Mac (coletor guardar-senha anthropic), digitada pelo Bruno.
# ---------------------------------------------------------------------------

REPO_GIT = "https://github.com/brmilanib/robohermes.git"
BRANCH_NUBI = "claude/wizardly-ritchie-5fig5i"
FERREIRO_TETO_DIA = float(os.environ.get("NUBI_FERREIRO_TETO", "10"))
FERREIRO_MODELO = os.environ.get("NUBI_FERREIRO_MODELO", "claude-opus-5-5")
FERREIRO_AUTOR = "Ferreiro (Claude no Mac)"


def _claude_bin():
    for c in (shutil.which("claude"), str(Path.home() / ".claude" / "local" / "claude"), "/opt/homebrew/bin/claude",
              "/usr/local/bin/claude", str(Path.home() / ".local" / "bin" / "claude")):
        if c and Path(c).exists():
            return c
    return None


def ferreiro_pronto(cfg=None):
    """(pronto, motivo): tem o Claude Code instalado, a chave no Chaveiro e o git?"""
    if not _claude_bin():
        return False, "Claude Code não instalado no Mac (npm install -g @anthropic-ai/claude-code)"
    if not _credencial("anthropic", cfg)[1]:
        return False, "chave da API não guardada (coletor guardar-senha anthropic)"
    if not shutil.which("git"):
        return False, "git não instalado"
    return True, ""


def _gasto_ferreiro(cfg, somar=0.0):
    hoje = date.today().isoformat()
    g = {k: v for k, v in (cfg.get("ferreiro_gasto") or {}).items() if k == hoje}
    if somar:
        g[hoje] = round(g.get(hoje, 0.0) + somar, 4)
        cfg["ferreiro_gasto"] = g
        salvar_config(cfg)
    return g.get(hoje, 0.0)


def _git(pasta, *args, timeout=300):
    return subprocess.run(["git", *args], cwd=str(pasta), capture_output=True, text=True, timeout=timeout)


def _passo_card(token, tid, texto, status=None, tipo="passo"):
    try:
        api(token, "tarefa_mac_passo", corpo={"id": tid, "texto": texto, "tipo": tipo, **({"status": status} if status else {})},
            metodo="POST", timeout=60)
    except Exception as e:  # noqa: BLE001
        print(f"ferreiro: não escrevi no card ({e})", flush=True)


def cmd_programar(args, cfg):
    """O Ferreiro pega o card N, corrige no clone do projeto, testa e envia num branch para o Chefe revisar e publicar."""
    trava = PASTA / "ferreiro.pid"
    if _pid_vivo(trava):
        print("O Ferreiro já está trabalhando em outro card.")
        return 1
    ok, motivo = ferreiro_pronto(cfg)
    gasto = _gasto_ferreiro(cfg)
    if str(args.id) == "0":                               # só conferir (comando "Ferreiro: conferir" da Central)
        print(("✅ Ferreiro pronto" if ok else f"❌ Ferreiro indisponível: {motivo}")
              + f" · gasto hoje US$ {gasto:.2f} de {FERREIRO_TETO_DIA:.0f} · modelo {FERREIRO_MODELO}")
        return 0 if ok else 1
    if not ok:
        print(f"Ferreiro indisponível: {motivo}")
        return 1
    if gasto >= FERREIRO_TETO_DIA:
        print(f"Teto do dia atingido (US$ {gasto:.2f} de {FERREIRO_TETO_DIA:.0f}); o card fica para o Chefe.")
        return 1
    trava.write_text(str(os.getpid()))
    token = token_nubi(cfg)
    tid = int(args.id)
    try:
        x = api(token, "tarefa_eventos", {"id": tid}, timeout=60)
        t, evs = x["tarefa"], x.get("eventos") or []
        repo = PASTA / "projeto"
        if not (repo / ".git").exists():
            r = subprocess.run(["git", "clone", "--branch", BRANCH_NUBI, REPO_GIT, str(repo)], capture_output=True, text=True, timeout=900)
            if r.returncode:
                raise Falha("não consegui clonar o projeto: " + (r.stderr or r.stdout)[-300:])
        _git(repo, "fetch", "origin", BRANCH_NUBI)
        _git(repo, "checkout", "-B", f"ferreiro/card-{tid}", f"origin/{BRANCH_NUBI}")
        _passo_card(token, tid, f"🔨 Ferreiro (Claude Code no Mac) pegou o card na hora. Trabalhando no branch ferreiro/card-{tid}.",
                    "em_desenvolvimento")
        historico = "\n".join(f"[{e['autor']}] {e['texto'][:1500]}" for e in evs[-12:])
        pedido = (
            f"Você é o Ferreiro, programador de plantão do nubi rodando no Mac mini. Leia nubi/CLAUDE.md antes. Corrija o card "
            f"#{tid} abaixo com a MENOR mudança possível, no estilo do código em volta.\n\nCARD #{tid}: {t['titulo']}\n"
            f"{t.get('descricao') or ''}\n\nHISTÓRICO DO CARD:\n{historico}\n\n"
            "Regras: reproduza o problema com um teste em nubi/testes/ (página falsa, como os testes do coletor; nunca os sites "
            "reais), corrija, rode TODOS os nubi/testes/test_*.py e python3 nubi/testes/fumaca.py até passar. Faça UM commit em "
            "português explicando a causa e a solução. NÃO faça push, NÃO publique, NÃO mexa em senhas, chaves, no banco nem no "
            "Branch Tracking. No fim, responda com um relatório curto em markdown com as seções ## Causa, ## Solução e ## Testes.")
        env = {**os.environ, "ANTHROPIC_API_KEY": _credencial("anthropic", cfg)[1]}
        print(f"Ferreiro trabalhando no card #{tid}…", flush=True)
        r = subprocess.run([_claude_bin(), "-p", pedido, "--output-format", "json", "--model", FERREIRO_MODELO,
                            "--max-turns", "60", "--permission-mode", "acceptEdits",
                            "--allowedTools", "Read,Edit,Write,Glob,Grep,Bash(python3:*),Bash(git status:*),Bash(git diff:*),"
                                              "Bash(git add:*),Bash(git commit:*),Bash(git log:*),Bash(ls:*),Bash(node:*)"],
                           cwd=str(repo), env=env, capture_output=True, text=True, timeout=3600)
        try:
            saida = json.loads(r.stdout or "{}")
        except ValueError:
            saida = {"result": (r.stdout or r.stderr or "")[-3000:]}
        custo = float(saida.get("total_cost_usd") or saida.get("cost_usd") or 0)
        _gasto_ferreiro(cfg, custo)
        relatorio = str(saida.get("result") or "").strip()
        novos = _git(repo, "rev-list", "--count", f"origin/{BRANCH_NUBI}..HEAD").stdout.strip()
        testes = subprocess.run(["/bin/sh", "-c", "set -e; for f in nubi/testes/test_*.py; do python3 \"$f\" >/dev/null; done; "
                                 "python3 nubi/testes/fumaca.py >/dev/null"], cwd=str(repo), capture_output=True, text=True,
                                timeout=1800)
        if r.returncode or novos in ("", "0") or testes.returncode:
            motivo = ("o Claude Code parou com erro" if r.returncode else "nenhum commit" if novos in ("", "0")
                      else "os testes não passaram no Mac")
            _passo_card(token, tid, f"⚠️ Ferreiro não conseguiu fechar ({motivo}; custo US$ {custo:.2f}). Volta para o Chefe.\n\n"
                        + (relatorio[:4000] or (testes.stdout + testes.stderr)[-1500:]), "aprovada", tipo="erro_teste")
            _postar_hermes_como(token, FERREIRO_AUTOR, f"⚠️ Card #{tid}: não consegui fechar ({motivo}). Devolvi para o Chefe.", custo)
            return 1
        env_push = _git(repo, "push", "-f", "origin", f"ferreiro/card-{tid}")
        if env_push.returncode:
            _passo_card(token, tid, "⚠️ Ferreiro corrigiu, mas não conseguiu enviar o branch para o GitHub (login do GitHub no Mac: "
                        "gh auth login). Volta para o Chefe.\n\n" + relatorio[:4000], "aprovada", tipo="erro_teste")
            return 1
        _passo_card(token, tid, f"📦 **Entrega do Ferreiro** (branch `ferreiro/card-{tid}`, {novos} commit(s), testes do Mac ✅, "
                    f"custo US$ {custo:.2f}). O Chefe revisa, junta e publica.\n\n{relatorio[:6000]}", "em_teste")
        _postar_hermes_como(token, FERREIRO_AUTOR, f"🔨 Card #{tid} corrigido no branch ferreiro/card-{tid} (testes ✅, US$ {custo:.2f}). "
                                                    "Chefe: revisar, juntar e publicar.", custo)
        return 0
    except Exception as e:  # noqa: BLE001
        _passo_card(token, tid, f"⚠️ Ferreiro parou: {str(e)[:300]}. Volta para o Chefe.", "aprovada", tipo="erro_teste")
        return 1
    finally:
        try:
            trava.unlink()
        except OSError:
            pass


def _postar_hermes_como(token, autor, texto, custo=0.0):
    try:
        api(token, "reuniao_postar", corpo={"autor": autor, "texto": texto, "modelo": FERREIRO_MODELO, "tokens_in": 0,
                                             "tokens_out": 0, "custo_usd": custo}, metodo="POST", timeout=60)
    except Exception as e:  # noqa: BLE001
        print(f"não postei na Sala ({e})", flush=True)


# ---------------------------------------------------------------------------
# Conversar com o Hermes no Terminal do Mac (pedido do Bruno, 25/09): chat ao vivo com o modelo local, com o contexto do
# projeto (briefing, Sala, coletas, quadro, caixa de conhecimento, log do vigia). No fim, o resumo vai para a caixa.
# ---------------------------------------------------------------------------

def _br(iso):
    """'2026-09-25T15:04:00+00:00' (UTC) -> '25/09 12:04' (Brasília)."""
    try:
        return (datetime.fromisoformat(str(iso).replace("Z", "+00:00")) - timedelta(hours=3)).strftime("%d/%m %H:%M")
    except ValueError:
        return str(iso)[:16]


def contexto_hermes(token):
    """O que o Hermes precisa saber do projeto agora (só leitura). Cada parte que falhar fica de fora, sem travar o chat."""
    partes, sistema = [], ""
    try:
        sala = api(token, "reuniao", {"sistema": "1"}, timeout=60)
        sistema = sala.get("sistema") or ""
        partes.append("SALA DE REUNIÃO (últimas mensagens):\n" + "\n".join(
            f"[{_br(m.get('criado_em'))}] {m['autor']}: {m['texto'][:600]}" for m in (sala.get("mensagens") or [])[-20:]))
    except Exception:  # noqa: BLE001
        pass
    try:
        st = api(token, "coletor_status", timeout=60)
        partes.append("COLETAS DO MAC (mais recentes primeiro):\n" + "\n".join(
            f"{_br(e['iniciado_em'])} {e['tarefa']}: {'ok' if e['ok'] else 'ERRO'} — {(e.get('mensagem') or '')[:200]}"
            for e in (st.get("execucoes") or [])[:10]))
    except Exception:  # noqa: BLE001
        pass
    try:
        ts = api(token, "reuniao_tarefas", timeout=60).get("tarefas") or []
        abertas = [t for t in ts if t.get("status") in ("proposta", "aprovada", "em_desenvolvimento", "em_teste")]
        partes.append("QUADRO DE DESENVOLVIMENTO (cards abertos):\n" + "\n".join(
            f"#{t['id']} [{t['status']}/{t.get('responsavel') or '-'}] {t['titulo']}" for t in abertas[:30]))
    except Exception:  # noqa: BLE001
        pass
    try:
        itens = [c for c in (api(token, "conhecimento", timeout=60).get("itens") or []) if c.get("fixo")][:12]
        partes.append("CAIXA DE CONHECIMENTO (fixos):\n" + "\n".join(f"- {c['titulo']}: {c['texto'][:500]}" for c in itens))
    except Exception:  # noqa: BLE001
        pass
    try:
        partes.append("LOG DO VIGIA NESTE MAC (fim):\n" + "\n".join((PASTA / "vigia.log").read_text(errors="replace").splitlines()[-30:]))
    except OSError:
        pass
    return sistema, "\n\n".join(partes)


def _ollama_stream(mensagens, modelo):
    """Resposta do Ollama aparecendo na tela enquanto é escrita; devolve o texto todo."""
    corpo = {"model": modelo, "stream": True, "messages": mensagens}
    req = urllib.request.Request(OLLAMA, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
    texto = []
    with urllib.request.urlopen(req, timeout=900) as r:
        for linha in r:
            linha = linha.decode("utf-8", "replace").strip()
            if not linha.startswith("data:") or linha == "data: [DONE]":
                continue
            try:
                pedaco = json.loads(linha[5:])["choices"][0]["delta"].get("content") or ""
            except (ValueError, KeyError, IndexError):
                continue
            texto.append(pedaco)
            print(pedaco, end="", flush=True)
    print(flush=True)
    return "".join(texto).strip()


def cmd_conversar(args, cfg):
    modelo = args.modelo or "hermes3:8b"
    token = token_nubi(cfg)
    print("Carregando o projeto (Sala, coletas, quadro, caixa de conhecimento, log do vigia)…", flush=True)
    sistema, ctx = contexto_hermes(token)
    papel = (PAPEL_HERMES.split(" Responda à última")[0] + " Agora você está conversando direto com o Bruno (dono) no "
             "Terminal do Mac mini. Responda em português do Brasil, direto e curto. Use o CONTEXTO abaixo; se algo não está "
             "nele, diga que não sabe (não invente números). Horários em Brasília. Você não executa comandos aqui: se precisar "
             "de uma ação, diga qual comando o Bruno pode rodar ou pedir na Central.")
    base = [{"role": "system", "content": f"{sistema}\n\n{papel}\n\nCONTEXTO DO PROJETO AGORA:\n{ctx}"}]
    hist = []
    print(f"\n🪽 Hermes ({modelo}) pronto. Escreva e aperte Enter. /atualizar recarrega o projeto; /sair termina "
          "(o resumo vai para a caixa de conhecimento).\n", flush=True)
    while True:
        try:
            pergunta = input("você › ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not pergunta:
            continue
        if pergunta in ("/sair", "sair", "/exit"):
            break
        if pergunta == "/atualizar":
            sistema, ctx = contexto_hermes(token)
            base[0]["content"] = f"{sistema}\n\n{papel}\n\nCONTEXTO DO PROJETO AGORA:\n{ctx}"
            print("(projeto recarregado)\n", flush=True)
            continue
        hist.append({"role": "user", "content": pergunta})
        print("hermes › ", end="", flush=True)
        try:
            resposta = _ollama_stream(base + hist[-20:], modelo)
        except urllib.error.URLError as e:
            print(f"\nNão consegui falar com o Ollama ({e}). Abra o app Ollama e confira: ollama list")
            hist.pop()
            continue
        hist.append({"role": "assistant", "content": resposta})
        print()
    if len(hist) >= 2:
        print("Guardando o resumo da conversa na caixa de conhecimento…", flush=True)
        try:
            conversa = "\n".join(f"{'Bruno' if m['role'] == 'user' else 'Hermes'}: {m['content'][:1500]}" for m in hist)
            corpo = {"model": modelo, "stream": False, "messages": [{"role": "user", "content":
                     "Resuma esta conversa entre o Bruno e o Hermes em até 6 linhas, em português: o que foi perguntado, o que "
                     "foi decidido e o que ficou pendente. Não invente.\n\n" + conversa[-12000:]}]}
            req = urllib.request.Request(OLLAMA, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=600) as r:
                resumo = json.loads(r.read().decode())["choices"][0]["message"]["content"].strip()
            api(token, "conhecimento_salvar", corpo={"titulo": f"Conversa do Bruno com o Hermes ({datetime.now():%d/%m %H:%M})",
                                                     "texto": resumo, "tipo": "conversa", "fonte": "Terminal do Mac mini",
                                                     "autor": "Hermes"}, metodo="POST", timeout=60)
            print("OK: resumo guardado.", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"(não guardei o resumo: {e})", flush=True)
    return 0


# ---------------------------------------------------------------------------
# Login automático (autorizado pelo Bruno no plano aprovado em 25/09): quando um site pede login, o coletor entra
# sozinho. A senha fica SÓ no navegador do coletor (preenchimento automático do Chrome) ou no Chaveiro do Mac (o Bruno
# guarda com `coletor guardar-senha <site>`); nunca em arquivo, no nubi, no banco ou no log. Código do e-mail
# (UpSeller): lido no Gmail por IMAP, só leitura, com a "senha de app" do Google, também no Chaveiro; só e-mails do
# próprio site, dos últimos minutos. Nunca troca senha, cria conta ou clica em "esqueci a senha".
# ---------------------------------------------------------------------------

LOGIN_SITES = {   # site: (nome, tela depois do login, sinal de que entrou)
    "nubimetrics": ("Nubimetrics",
                    lambda cfg: f"{BASE}/competition/dashboardbycompetitor?group={cfg.get('grupo')}&range=PREVMONTH",
                    lambda pg: pg.locator('td a[aria-label="Analise um concorrente"]').first.is_visible()),
    "upseller": ("UpSeller", lambda cfg: f"{UPSELLER}/pt/inventory/list",
                 lambda pg: pg.get_by_text("Importar & Exportar").first.is_visible()),
    "gestor": ("Gestor Seller", lambda cfg: f"{GESTOR}/management/products",
               lambda pg: pg.get_by_text("Importar por planilha").first.is_visible()),
}
MESES_IMAP = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
PROIBIDO_CLICAR = re.compile(r"esquec|forgot|recuper|redefin|reset|cadastr|criar conta|sign up|registr", re.I)


def _credencial(site, cfg=None):
    """(usuário, senha) do Chaveiro do Mac; senha "" se o Bruno não guardou (aí vale o preenchimento do Chrome)."""
    cfg = cfg or ler_config()
    usuario = (cfg.get("logins") or {}).get(site, "")
    if not usuario or sys.platform != "darwin":
        return usuario, ""
    r = subprocess.run(["security", "find-generic-password", "-s", f"{SERVICO_CHAVEIRO}-{site}", "-a", usuario, "-w"],
                       capture_output=True, text=True)
    return usuario, (r.stdout.strip() if r.returncode == 0 else "")


def cmd_guardar_senha(args, cfg):
    """O Bruno guarda (uma vez, no próprio Mac) o login de um site no Chaveiro, para o coletor entrar sozinho."""
    site = args.site
    nome = {"gmail": "Gmail (código do UpSeller)", "anthropic": "Anthropic (chave da API do Ferreiro)"}.get(site) or LOGIN_SITES[site][0]
    if sys.platform != "darwin":
        print("Só funciona no Mac (Chaveiro).")
        return 1
    usuario = input(f"E-mail/usuário do {nome}: ").strip()
    if site == "anthropic":
        senha = getpass.getpass("Chave da API (Console → Chaves de API → criar 'Ferreiro Mac'; começa com sk-ant-): ").strip()
    elif site == "gmail":
        senha = getpass.getpass("Senha de APP do Google (myaccount.google.com → Segurança → Senhas de app; "
                                "16 letras, NÃO é a senha normal): ").replace(" ", "")
    else:
        senha = getpass.getpass(f"Senha do {nome} (fica só no Chaveiro deste Mac): ")
    if not usuario or not senha:
        print("Nada guardado.")
        return 1
    subprocess.run(["security", "add-generic-password", "-U", "-s", f"{SERVICO_CHAVEIRO}-{site}", "-a", usuario,
                    "-w", senha], check=True)
    cfg.setdefault("logins", {})[site] = usuario
    salvar_config(cfg)
    print(f"OK: login do {nome} guardado no Chaveiro do Mac. O coletor entra sozinho quando o site pedir.")
    return 0


def _botao_enviar(pg):
    b = pg.locator("button[type=submit]:visible, input[type=submit]:visible")
    if not b.count():
        b = pg.get_by_role("button", name=re.compile(r"entrar|ingressar|login|log in|acessar|sign in|continuar|confirmar|verificar", re.I))
    for i in range(b.count()):
        if not PROIBIDO_CLICAR.search(b.nth(i).inner_text() or ""):
            return b.nth(i)
    return None


def _preencher_login(pg, site, cfg):
    """Tela de login: preenche do Chaveiro ou usa o que o Chrome preencheu sozinho, e envia. False = não deu."""
    senha_campo = pg.locator("input[type=password]:visible").first
    if not senha_campo.count():
        return False
    usuario_campo = pg.locator("input[type=email]:visible, input[name*=mail i]:visible, input[id*=mail i]:visible, "
                               "input[name*=user i]:visible, input[name*=login i]:visible, input[type=text]:visible").first
    usuario, senha = _credencial(site, cfg)
    if senha:
        if usuario and usuario_campo.count():
            usuario_campo.fill(usuario)
        senha_campo.fill(senha)
    else:
        try:                                   # o Chrome só libera a senha salva depois de um clique na página
            (usuario_campo if usuario_campo.count() else senha_campo).click()
        except Exception:  # noqa: BLE001
            pass
        devagar(1.5)
        if not senha_campo.evaluate("e => e.value.length"):
            return False
    b = _botao_enviar(pg)
    if b:
        b.click()
    else:
        senha_campo.press("Enter")
    return True


def _campos_codigo(pg):
    return pg.locator("input[autocomplete=one-time-code]:visible, input[name*=code i]:visible, "
                      "input[name*=codigo i]:visible, input[id*=code i]:visible, input[placeholder*=código i]:visible, "
                      "input[placeholder*=code i]:visible, input[maxlength='6']:visible, input[maxlength='1']:visible")


def _texto_email(msg):
    partes = msg.walk() if msg.is_multipart() else [msg]
    txt = []
    for parte in partes:
        if parte.get_content_type() in ("text/plain", "text/html"):
            try:
                txt.append(parte.get_payload(decode=True).decode(parte.get_content_charset() or "utf-8", "replace"))
            except Exception:  # noqa: BLE001
                pass
    return re.sub(r"<[^>]+>", " ", " ".join(txt))


def achar_codigo(texto):
    """Código de verificação no e-mail (perto de 'código'/'code'; senão, o primeiro número de 6 dígitos)."""
    m = re.search(r"(?:c[óo]digo|code|verifica\w*)\D{0,80}?(?<!\d)(\d{4,8})(?!\d)", texto, re.I)
    m = m or re.search(r"(?<!\d)(\d{6})(?!\d)", texto)
    return m.group(1) if m else ""


def codigo_email(site, desde, espera=150, imap=None):
    """Lê no Gmail (IMAP, só leitura) o código que o site mandou depois de `desde`. "" se não achar."""
    usuario, senha = _credencial("gmail")
    if not senha:
        log("  (o site pediu código por e-mail, mas a senha de app do Gmail não está no Chaveiro: "
            "~/.nubi-coletor/coletor guardar-senha gmail)")
        return ""
    import email
    import email.utils
    import imaplib
    ontem = date.today() - timedelta(days=1)
    desde_imap = f"{ontem.day:02d}-{MESES_IMAP[ontem.month - 1]}-{ontem.year}"
    fim = time.time() + espera
    while time.time() < fim:
        try:
            with (imap or imaplib.IMAP4_SSL)("imap.gmail.com") as caixa:
                caixa.login(usuario, senha)
                caixa.select("INBOX", readonly=True)
                _, ids = caixa.search(None, f'(FROM "{site}" SINCE "{desde_imap}")')
                for i in reversed(ids[0].split()[-5:]):
                    _, dados = caixa.fetch(i, "(RFC822)")
                    msg = email.message_from_bytes(dados[0][1])
                    quando = email.utils.parsedate_to_datetime(msg["Date"])
                    if quando.tzinfo is None:
                        quando = quando.replace(tzinfo=timezone.utc)
                    if quando < desde - timedelta(minutes=2):
                        break                          # e-mail velho: o código novo ainda não chegou
                    codigo = achar_codigo(f"{msg.get('Subject', '')} {_texto_email(msg)}")
                    if codigo:
                        log("  código de verificação lido no e-mail")   # o código em si nunca vai para o log
                        return codigo
        except Exception as e:  # noqa: BLE001
            log(f"  (não consegui ler o Gmail: {e.__class__.__name__})")
            return ""
        time.sleep(10)
    return ""


def _preencher_codigo(pg, site, desde):
    campos = _campos_codigo(pg)
    if not campos.count():
        return None
    pedir = pg.get_by_role("button", name=re.compile(r"(enviar|obter|send|get)\s*(o\s*)?(c[óo]digo|code)", re.I))
    if pedir.count():
        try:
            pedir.first.click()
            desde = datetime.now(timezone.utc)
        except Exception:  # noqa: BLE001
            pass
    codigo = codigo_email(site, desde)
    if not codigo:
        return False
    if campos.count() > 1:                     # caixinhas de 1 dígito
        campos.first.click()
        pg.keyboard.type(codigo, delay=80)
    else:
        campos.first.fill(codigo)
    devagar(1)
    b = _botao_enviar(pg)
    if b:
        b.click()
    return True


def entrar_sozinho(p, cfg, site, visivel=True, prazo=180):
    """Abre o site, faz o login (e o código do e-mail, se pedir) e guarda a sessão. True = entrou. Máx. 2 tentativas."""
    nome, url, pronto = LOGIN_SITES[site]
    ctx = abrir_navegador(p, cfg, visivel=visivel)
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    inicio, logins, codigos = datetime.now(timezone.utc), 0, 0
    try:
        pg.goto(url(cfg), wait_until="domcontentloaded", timeout=90000)
        fim = time.time() + prazo
        while time.time() < fim:
            devagar(2)
            try:
                if pronto(pg):
                    devagar(2)
                    guardar_sessao(ctx)
                    log(f"  {nome}: login feito sozinho")
                    return True
                if _campos_codigo(pg).count() and not pg.locator("input[type=password]:visible").count():
                    if codigos >= 2:
                        break
                    codigos += 1
                    if _preencher_codigo(pg, site, inicio) is False:
                        break
                    continue
                if pg.locator("input[type=password]:visible").count():
                    if logins >= 2:
                        log(f"  {nome}: o site recusou o login 2 vezes (senha, captcha ou tela nova)")
                        break
                    logins += 1
                    if not _preencher_login(pg, site, cfg):
                        log(f"  {nome}: sem senha salva no navegador do coletor nem no Chaveiro")
                        break
                    inicio = datetime.now(timezone.utc)
                    continue
                if site == "gestor" and "/management/products" not in pg.url and "/auth" not in pg.url:
                    pg.goto(url(cfg), wait_until="domcontentloaded", timeout=90000)
            except Exception as e:  # noqa: BLE001
                log(f"  {nome}: {e.__class__.__name__} no login")
        try:
            enviar_foto(pg, f"login automático do {nome} não entrou", resumo_tela(pg))
        except Exception:  # noqa: BLE001
            pass
        return False
    finally:
        ctx.close()


def cmd_entrar_auto(args, cfg):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ok = entrar_sozinho(p, cfg, args.site)
    print(("OK: entrou sozinho no " if ok else "Não entrou sozinho no ") + LOGIN_SITES[args.site][0], flush=True)
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# Hermes, vigia de erros 24 h (pedido do Bruno, 25/09): tarefa do Mac falhou -> ele diagnostica e conserta na hora o que é
# simples (navegador, perfil travado, pasta de downloads, rede), tenta de novo e conta na Sala. Só ações da lista fechada
# abaixo; login/senha nunca (isso é do Bruno). No máximo 2 consertos por tarefa por dia; depois abre card para o programador.
# ---------------------------------------------------------------------------

FALHAS = PASTA / "falhas.json"
MEDICO_MAX = 2
MEDICO_TAREFAS = ("estoque", "gestor", "diario")        # as que ele pode rodar de novo sozinho
RECEITAS = [   # (padrão no erro, ação, diagnóstico em português)
    (r"pediu login|SessaoExpirada|login .{0,30}vencid", "janela_login", "o login do site venceu (a senha é só do Bruno)"),
    (r"SingletonLock|ProcessSingleton|already in use|profile .{0,20}in use", "destravar", "o perfil do Chrome ficou travado por um Chrome que não fechou"),
    (r"No space left|ENOSPC", "limpar", "a pasta de downloads/disco encheu"),
    (r"[Dd]ownload|save_as", "visivel", "o download se perdeu com o navegador invisível"),
    (r"TargetClosed|browser has been closed|[Cc]rash", "visivel", "o navegador fechou no meio da tarefa"),
    (r"Timeout|timed out|net::ERR|ECONNRESET|Connection|sem contato", "repetir", "a página demorou ou a rede oscilou"),
]
ACOES_MEDICO = {"repetir": "rodei de novo", "visivel": "rodei de novo com o navegador visível",
                "destravar": "fechei o Chrome travado, destravei o perfil e rodei de novo",
                "limpar": "limpei arquivos velhos da pasta de downloads e rodei de novo",
                "janela_login": "abri a janela de login no Mac mini", "avisar": "avisei o Bruno"}
JANELA_LOGIN = {"nubimetrics": "entrar", "upseller": "entrar-upseller", "gestor seller": "entrar-gestor"}
ALERTAS_DEDUP = PASTA / "alertas_dedup.json"


def _chave_dedup_gestor(tarefa, erro):
    """Card #57: mesmo SKU e mesmo erro na conferência do gestor no mesmo dia -> uma só mensagem na Sala."""
    if tarefa != "gestor":
        return None
    m_sku = re.search(r"sku_normalizado=(\S+)", erro)
    if not m_sku:
        return None
    m_tela = re.search(r"a tela mostra: (.+?)\.\s*\[", erro)
    return f"gestor_sku|{m_sku.group(1)}|{(m_tela.group(1) if m_tela else '')[:60]}"


def _alerta_repetido_hoje(chave):
    """Verdadeiro só da 2ª vez em diante que essa chave aparece no mesmo dia; guarda só o dia de hoje (não cresce à toa)."""
    hoje = date.today().isoformat()
    try:
        estado = json.loads(ALERTAS_DEDUP.read_text()) if ALERTAS_DEDUP.exists() else {}
    except (OSError, ValueError):
        estado = {}
    vistas = estado.get(hoje, [])
    repetido = chave in vistas
    if not repetido:
        try:
            ALERTAS_DEDUP.write_text(json.dumps({hoje: vistas + [chave]}, ensure_ascii=False))
        except OSError:
            pass
    return repetido


def anotar_falha(tarefa, msg):
    try:
        lista = json.loads(FALHAS.read_text()) if FALHAS.exists() else []
    except (OSError, ValueError):
        lista = []
    lista.append({"tarefa": tarefa, "erro": str(msg)[:600], "quando": datetime.now().isoformat(timespec="seconds"),
                  "log": "\n".join(LOG[-15:])[-2500:]})
    try:
        FALHAS.write_text(json.dumps(lista[-30:], ensure_ascii=False))
    except OSError:
        pass


def _falhas_pendentes():
    try:
        lista = json.loads(FALHAS.read_text()) if FALHAS.exists() else []
    except (OSError, ValueError):
        return []
    limite = (datetime.now() - timedelta(hours=6)).isoformat()
    return [f for f in lista if not f.get("tratada") and f.get("quando", "") > limite]


def _pid_vivo(arq):
    try:
        os.kill(int(arq.read_text().strip()), 0)
        return True
    except (OSError, ValueError):
        return False


def diagnosticar(erro, log_txt=""):
    """Receita conhecida para o erro -> (ação, diagnóstico), ou (None, None)."""
    texto = f"{erro}\n{log_txt}"
    for padrao, acao, diag in RECEITAS:
        if re.search(padrao, texto):
            return acao, diag
    return None, None


def _hermes_escolhe(f):
    """Erro sem receita: o Hermes (Ollama, grátis) escolhe UMA ação da lista fechada; qualquer outra resposta = avisar."""
    pedido = ("Você é o Hermes, vigia de erros do coletor do nubi no Mac mini. Uma tarefa falhou. Escolha UMA ação da lista "
              "e explique a causa provável em 1 frase, em português do Brasil. Ações: repetir (rede/página lenta), visivel "
              "(problema do navegador invisível), destravar (Chrome/perfil travado), limpar (pasta de downloads cheia), "
              "avisar (precisa do Bruno: login, senha, site mudou). Responda SOMENTE JSON: "
              '{"acao": "...", "diagnostico": "..."}\n\n'
              f"TAREFA: {f['tarefa']}\nERRO: {f['erro']}\nFIM DO LOG:\n{f.get('log', '')[-1500:]}")
    corpo = {"model": "hermes3:8b", "stream": False, "messages": [{"role": "user", "content": pedido}]}
    try:
        req = urllib.request.Request(OLLAMA, data=json.dumps(corpo).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            txt = json.loads(r.read().decode())["choices"][0]["message"]["content"]
        j = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
        acao = str(j.get("acao") or "").strip().lower()
        if acao in ACOES_MEDICO:
            return acao, str(j.get("diagnostico") or "")[:200] or "causa não identificada"
    except Exception:  # noqa: BLE001
        pass
    return "avisar", "erro que eu não conheço (o Ollama não respondeu ou não soube classificar)"


def _destravar_perfil():
    perfil = PASTA / "perfil"
    subprocess.run(["pkill", "-f", f"user-data-dir={perfil}"], check=False, capture_output=True)
    time.sleep(3)
    for nome in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        try:
            (perfil / nome).unlink()
        except OSError:
            pass


def _limpar_downloads(dias=3):
    """Apaga só planilhas baixadas pelo coletor com mais de N dias (o nubi já tem os dados); nunca o perfil nem a config."""
    limite = time.time() - dias * 86400
    n = 0
    for pasta in (PASTA / "estoque", PASTA / "gestor", PASTA / "downloads", PASTA / "comandos"):
        for arq in (pasta.glob("*") if pasta.is_dir() else []):
            try:
                if arq.is_file() and arq.stat().st_mtime < limite:
                    arq.unlink()
                    n += 1
            except OSError:
                pass
    return n


def cmd_hermes_vigia(args, cfg):
    """(automático) O Hermes trata as falhas novas das tarefas do Mac: diagnostica, conserta o simples e tenta de novo."""
    trava = PASTA / "hermes-vigia.pid"
    if _pid_vivo(trava):
        return 0
    trava.write_text(str(os.getpid()))
    try:
        return _hermes_vigia(cfg)
    finally:
        try:
            trava.unlink()
        except OSError:
            pass


def _hermes_vigia(cfg):
    pend = _falhas_pendentes()
    if not pend:
        return 0
    try:
        lista = json.loads(FALHAS.read_text())
    except (OSError, ValueError):
        return 0
    for f in lista:                                        # trata só a mais recente de cada tarefa
        if not f.get("tratada"):
            f["tratada"] = True
    FALHAS.write_text(json.dumps(lista, ensure_ascii=False))
    ultimas = {}
    for f in pend:
        ultimas[f["tarefa"]] = f
    hoje = date.today().isoformat()
    conta = {k: v for k, v in (cfg.get("hermes_consertos") or {}).items() if k == hoje}.get(hoje, {})
    token = token_nubi(cfg)
    for tarefa, f in ultimas.items():
        n = conta.get(tarefa, 0)
        acao, diag = diagnosticar(f["erro"], f.get("log", ""))
        if not acao:
            acao, diag = _hermes_escolhe(f)
        if tarefa not in MEDICO_TAREFAS and acao != "avisar":
            acao, diag = "avisar", diag + " (esta tarefa eu não rodo de novo sozinho)"
        desistiu = acao != "avisar" and n >= MEDICO_MAX
        if desistiu:
            acao = "avisar"
        hora = f["quando"][11:16]
        conhecida = _solucao_conhecida(token, tarefa, f["erro"])
        texto = (f"🩺 **Vigia de erros**: a tarefa **{tarefa}** falhou às {hora} ({f['erro'][:180]}).\n"
                 f"Diagnóstico: {diag}.\n" + (f"📚 Já vimos esse erro antes — {conhecida[:300]}\n" if conhecida else ""))
        login = bool(re.search(RECEITAS[0][0], f["erro"]))
        if desistiu or (acao == "avisar" and not login):
            # pedido do Bruno (25/09): o que o Hermes não resolve vira card URGENTE na hora, e o time de programação
            # (Claude Code/Copilot/Codex, plantão de urgências) resolve sem esperar o Bruno
            motivo = (f"O Hermes consertou {n} vez(es) hoje e a tarefa voltou a falhar." if desistiu
                      else "O Hermes não tem conserto automático para este erro.")
            cid, novo = _abrir_card_erro(token, tarefa, f, diag, motivo, conhecida)
            ref = f"#{cid}" if cid else ""
            if novo and cid and ferreiro_pronto(cfg)[0]:
                _soltar(["programar", str(cid)])            # o Ferreiro (Claude Code no Mac) começa na hora
                texto += f"🔨 Chamei o Ferreiro (Claude Code no Mac) para atacar o card {ref} agora. "
            texto += (f"🚨 **URGENTE**: {motivo} Abri o card urgente {ref} para o time de programação (Claude Code, Copilot, "
                      "Codex) resolver agora; o plantão pega na próxima hora. Quando sair a correção, eu rodo a tarefa de novo "
                      "e guardo a solução na caixa de conhecimento." if novo else
                      f"O card urgente {ref} deste erro já está aberto com o time de programação.")
            aviso_mac("Hermes: card urgente aberto", f"{tarefa}: {diag[:120]}")
        elif acao == "janela_login":
            site = next((k for k in JANELA_LOGIN if k in f["erro"].lower()), "")
            ja = (cfg.get("hermes_login") or {}).get(hoje, [])
            if not site or ja.count(site) >= 2:
                texto += "Ação: o login é só com você — rode no Mac: ~/.nubi-coletor/coletor " + JANELA_LOGIN.get(site, "entrar")
                aviso_mac("Hermes: login vencido", f"{tarefa}: entre de novo no site")
            else:
                cfg.setdefault("hermes_login", {})[hoje] = ja + [site]
                salvar_config(cfg)
                # 25/09: logo depois da coleta falhar, o histórico diário abria o mesmo Chrome; o login não conseguia abrir
                # (perfil em uso) e "fechava" em 1 min. Espera o navegador do coletor ficar livre.
                fim_espera = time.time() + 1800
                while _outra_rodando() and time.time() < fim_espera:
                    time.sleep(20)
                chave = {"gestor seller": "gestor"}.get(site, site)
                auto = subprocess.run([sys.executable, str(Path(__file__).resolve()), "entrar-auto", chave],
                                      stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=600)
                if auto.returncode == 0:
                    if tarefa in MEDICO_TAREFAS:
                        _soltar(tarefa)
                    _postar_hermes(token, texto + f"Ação: entrei sozinho no {site.title()} (senha salva, sem ninguém) e "
                                   + (f"rodei a tarefa **{tarefa}** de novo." if tarefa in MEDICO_TAREFAS
                                      else "a próxima coleta já entra normal."))
                    texto = ""
                    continue
                motivo = " / ".join(x.strip() for x in (auto.stdout or "").splitlines()[-3:] if x.strip())[:300]
                texto += f"Tentei entrar sozinho e não deu ({motivo or 'sem detalhe'}). "
                texto += (f"Ação: abri a janela de login do {site.title()} no Mac mini. Com a senha salva no navegador é só clicar "
                          "em Entrar (10 min). Assim que entrar, eu rodo a tarefa de novo sozinho.")
                aviso_mac("Hermes: clique em Entrar", f"Janela de login do {site.title()} aberta no Mac mini")
                _postar_hermes(token, texto)
                texto = ""
                r = subprocess.run([sys.executable, str(Path(__file__).resolve()), JANELA_LOGIN[site]],
                                   stdin=subprocess.DEVNULL, capture_output=True, timeout=900)
                if r.returncode == 0 and tarefa in MEDICO_TAREFAS:
                    _soltar(tarefa)
                    texto = f"🩺 Login do {site.title()} feito. Rodei a tarefa **{tarefa}** de novo."
                elif r.returncode == 0:
                    texto = f"🩺 Login do {site.title()} feito. A próxima coleta já entra normal."
                else:
                    texto = f"🩺 A janela de login do {site.title()} fechou sem login (10 min). Rode no Mac: ~/.nubi-coletor/coletor {JANELA_LOGIN[site]}"
        elif acao == "avisar":                              # só login: a senha/o clique é do Bruno
            texto += "Ação: isso eu não consigo resolver sozinho — precisa do Bruno (login)."
            aviso_mac("Hermes: precisa de você", f"{tarefa}: {diag}")
        else:
            if acao == "destravar":
                _destravar_perfil()
            elif acao == "limpar":
                texto += f"(apaguei {_limpar_downloads()} arquivo(s) velho(s)) "
            elif acao == "repetir":
                time.sleep(120)
            fim = time.time() + 1800
            while _outra_rodando() and time.time() < fim:   # espera a coleta que estiver rodando terminar
                time.sleep(30)
            _soltar(tarefa, {"NUBI_VER": "1"} if acao == "visivel" else None)
            conta[tarefa] = n + 1
            texto += f"Ação: {ACOES_MEDICO[acao]} (conserto {n + 1} de {MEDICO_MAX} hoje)."
        print(f"{datetime.now():%d/%m %H:%M} hermes-vigia: {tarefa} -> {acao}", flush=True)
        if texto:
            chave = _chave_dedup_gestor(tarefa, f["erro"])
            if chave and _alerta_repetido_hoje(chave):
                print(f"{datetime.now():%d/%m %H:%M} hermes-vigia: {tarefa} -> mesmo SKU/erro já alertado hoje, não repito na Sala", flush=True)
            else:
                _postar_hermes(token, texto)
    cfg = ler_config()
    cfg["hermes_consertos"] = {hoje: conta}
    salvar_config(cfg)
    return 0


def cmd_repetir_falhas(args, cfg):
    """(automático, a cada versão nova do coletor) "Corrigiu, já roda": estoque/Gestor cuja última execução de hoje falhou
    rodam de novo com o código novo — antes ficavam esperando o dia seguinte (limite de 3 tentativas por dia)."""
    trava = PASTA / "repetir-falhas.pid"
    if _pid_vivo(trava):
        return 0
    trava.write_text(str(os.getpid()))
    try:
        time.sleep(90)                                   # a coleta da versão nova começa primeiro
        token = token_nubi(cfg)
        hoje = (datetime.now(timezone.utc) - timedelta(hours=3)).date().isoformat()
        ultima = {}
        for e in api(token, "coletor_status", timeout=60).get("execucoes") or []:   # mais recente primeiro
            ultima.setdefault(e["tarefa"], e)
        alvo = [t for t in ("estoque", "gestor") if t in ultima and not ultima[t]["ok"]
                and _br(ultima[t]["iniciado_em"])[:5] == f"{hoje[8:10]}/{hoje[5:7]}"]
        for tarefa in alvo:
            fim = time.time() + 4 * 3600
            while _outra_rodando() and time.time() < fim:   # espera a coleta terminar (o Chrome é um só)
                time.sleep(30)
            print(f"{datetime.now():%d/%m %H:%M} repetir-falhas: {tarefa} falhou hoje -> rodando com a versão nova", flush=True)
            subprocess.run([sys.executable, str(Path(__file__).resolve()), tarefa], stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=3600)
            depois = next((e for e in api(token, "coletor_status", timeout=60).get("execucoes") or [] if e["tarefa"] == tarefa), {})
            _postar_hermes(token, f"🩺 Saiu versão nova do coletor: rodei de novo a tarefa **{tarefa}**, que tinha falhado hoje "
                                  f"({(ultima[tarefa].get('mensagem') or '')[:120]}). Agora: "
                                  + ("✅ " if depois.get("ok") else "⚠️ ") + (depois.get("mensagem") or "sem resultado")[:200])
        return 0
    finally:
        try:
            trava.unlink()
        except OSError:
            pass


def _postar_hermes(token, texto):
    try:
        api(token, "reuniao_postar", corpo={"autor": "Hermes", "texto": texto, "modelo": "vigia", "tokens_in": 0,
                                             "tokens_out": 0}, metodo="POST", timeout=60)
    except Exception as e:  # noqa: BLE001
        print(f"hermes-vigia: não postei na Sala ({e})", flush=True)


def assinatura_erro(erro):
    """O 'jeito' do erro, sem números, horários e detalhes entre colchetes: serve para achar o mesmo erro de novo."""
    t = re.sub(r"\[.*?\]|\(.*?\)|\d+[\d.,:]*", " ", str(erro))
    return re.sub(r"[,*%]|\s+", " ", t).strip()[:60].strip()


def _solucao_conhecida(token, tarefa, erro):
    """A caixa de conhecimento já tem a solução deste erro (de um card 🩺 fechado antes)? Devolve o texto ou ""."""
    try:
        itens = api(token, "conhecimento", {"q": assinatura_erro(erro)[:40]}, timeout=30).get("itens") or []
    except Exception:  # noqa: BLE001
        return ""
    sol = next((c for c in itens if str(c.get("titulo", "")).startswith("Solução") and tarefa in c.get("titulo", "")), None)
    return f"{sol['titulo']}: {sol['texto'][:600]}" if sol else ""


def _abrir_card_erro(token, tarefa, f, diag, motivo="", conhecida=""):
    """Card URGENTE para o time de programação (Claude Code, Copilot, Codex): o sistema não pode ficar parado esperando o
    Bruno. Não duplica: se já tem card aberto do mesmo erro, devolve ele. Devolve (id, novo)."""
    titulo = f"🩺 Coletor: {tarefa} falhando — {assinatura_erro(f['erro'])}"
    try:
        abertos = [t for t in (api(token, "reuniao_tarefas", timeout=60).get("tarefas") or [])
                   if t.get("titulo") == titulo and t.get("status") not in ("feita", "recusada")]
        if abertos:
            return abertos[0]["id"], False
    except Exception:  # noqa: BLE001
        pass
    desc = (f"{motivo or 'O Hermes (vigia de erros) não conseguiu resolver sozinho.'}\n"
            f"Último erro ({f['quando']}, horário do Mac): {f['erro'][:400]}\nDiagnóstico do Hermes: {diag}\n"
            + (f"Solução que já funcionou antes (caixa de conhecimento): {conhecida}\n" if conhecida else "")
            + f"Fim do log:\n{f.get('log', '')[-1200:]}\n\n"
            f"Escopo: descobrir e corrigir a causa da falha da tarefa {tarefa} do coletor, sem mexer no login nem em senhas.\n"
            f"Arquivo/função: nubi/public/coletor/coletor.py (tarefa {tarefa}; ver o log no Coletor da Central).\n"
            f"Teste: reproduzir contra página falsa (como os testes do UpSeller/Gestor) e rodar os testes do repositório.\n"
            f"Critério de aceite: a tarefa {tarefa} roda sem erro na próxima execução do Mac (o Hermes roda de novo sozinho "
            f"quando sai a versão nova). No relatório, escreva ## Causa e ## Solução: o Hermes guarda na caixa de conhecimento.")
    try:
        r = api(token, "reuniao_tarefa_salvar", corpo={"titulo": titulo, "descricao": desc, "status": "aprovada",
                                                       "prioridade": "urgente", "area": "coletor", "responsavel": "claude_code",
                                                       "risco": "medio", "autor": "hermes"}, metodo="POST", timeout=60)
        return (r or {}).get("id"), True
    except Exception as e:  # noqa: BLE001
        print(f"hermes-vigia: não abri o card ({e})", flush=True)
        return None, False


def main():
    ap = argparse.ArgumentParser(description="Coletor do Nubimetrics para o nubi")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("configurar")
    sub.add_parser("entrar")
    sub.add_parser("status")
    sub.add_parser("atualizar", help="baixa a versão mais nova do coletor")
    sub.add_parser("vigiar", help="(automático) roda a coleta se houver versão nova ou pedido no site")
    sub.add_parser("despachar", help="(automático) executa os comandos pedidos na Central")
    sub.add_parser("parar", help="para a coleta que estiver rodando neste Mac")
    sub.add_parser("vigia-reativar", help="instala/ativa de novo o vigia (launchd)")
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
    hm = sub.add_parser("hermes", help="o Hermes (Ollama, no Mac) lê a Sala de reunião e posta a opinião dele")
    hm.add_argument("pergunta", nargs="?", default="", help="pergunta para o Hermes (opcional)")
    hm.add_argument("--modelo", default=None)
    hm.set_defaults(agente="hermes")
    qw = sub.add_parser("qwen", help="o Qwen (Ollama, no Mac) confere a Sala de reunião e posta a revisão dele")
    qw.add_argument("pergunta", nargs="?", default="")
    qw.add_argument("--modelo", default=None)
    qw.add_argument("--ultimas", type=int, default=20)
    qw.set_defaults(agente="qwen")
    hm.add_argument("--ultimas", type=int, default=20, help="quantas mensagens da Sala ele lê")
    sub.add_parser("entrar-upseller", help="login no UpSeller (uma vez), para o estoque atualizar sozinho")
    hc = sub.add_parser("hermes-card", help="o Hermes faz um card do quadro de Desenvolvimento e entrega no nubi")
    hc.add_argument("id")
    hc.add_argument("--modelo", default=None)
    sub.add_parser("entrar-gestor", help="login no Gestor Seller (uma vez), para importar a planilha sozinho")
    sub.add_parser("hermes-vigia", help="(automático) o Hermes trata as falhas novas: diagnostica, conserta e tenta de novo")
    sub.add_parser("hermes-memoria", help="(automático) o Hermes documenta a Sala e os cards na caixa de conhecimento; o Qwen revisa")
    sub.add_parser("repetir-falhas", help="(automático) roda de novo o estoque/Gestor que falhou hoje, com a versão nova")
    cv = sub.add_parser("conversar", help="conversa com o Hermes no Terminal, com o contexto do projeto")
    cv.add_argument("--modelo", default=None)
    gsn = sub.add_parser("guardar-senha", help="guarda no Chaveiro do Mac o login de um site (para o coletor entrar sozinho)")
    gsn.add_argument("site", choices=["nubimetrics", "upseller", "gestor", "gmail", "anthropic"])
    pgr = sub.add_parser("programar", help="o Ferreiro (Claude Code no Mac, pela API) corrige o card N e envia num branch")
    pgr.add_argument("id")
    ea = sub.add_parser("entrar-auto", help="entra sozinho no site (senha do navegador/Chaveiro, código do e-mail)")
    ea.add_argument("site", choices=["nubimetrics", "upseller", "gestor"])
    gs = sub.add_parser("gestor", help="importa no Gestor Seller a planilha feita pelo nubi")
    gs.add_argument("--ver", action="store_true", help="mostrar a janela do navegador")
    es = sub.add_parser("estoque", help="exporta a Lista de Estoque do UpSeller e manda para o nubi")
    es.add_argument("--sem-enviar", action="store_true")
    es.add_argument("--ver", action="store_true", help="mostrar a janela do navegador")
    mk = sub.add_parser("marcas")
    mk.add_argument("--mes")
    mk.add_argument("--sem-enviar", action="store_true")
    mk.add_argument("--ver", action="store_true", help="mostrar a janela do navegador")
    comandos = set(sub.choices)
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-") and sys.argv[1] not in comandos and not os.environ.get("NUBI_ATUALIZADO"):
        auto_atualizar()                               # comando novo que esta versão ainda não conhece: atualiza antes
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
    if args.cmd == "entrar-upseller":
        return cmd_entrar_upseller(args, cfg)
    if args.cmd == "hermes-card":
        return cmd_hermes_card(args, cfg)
    if args.cmd == "entrar-gestor":
        return cmd_entrar_gestor(args, cfg)
    if args.cmd == "hermes-vigia":
        return cmd_hermes_vigia(args, cfg)
    if args.cmd == "hermes-memoria":
        return cmd_hermes_memoria(args, cfg)
    if args.cmd == "guardar-senha":
        return cmd_guardar_senha(args, cfg)
    if args.cmd == "conversar":
        return cmd_conversar(args, cfg)
    if args.cmd == "programar":
        return cmd_programar(args, cfg)
    if args.cmd == "repetir-falhas":
        return cmd_repetir_falhas(args, cfg)
    if args.cmd == "entrar-auto":
        return cmd_entrar_auto(args, cfg)
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
    if args.cmd == "vigiar":
        return cmd_vigiar()
    if args.cmd == "despachar":
        return despachar(cfg)
    if args.cmd == "parar":
        pid = _outra_rodando()
        if not pid:
            print("Nenhuma coleta rodando.")
            return 0
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except OSError:
            os.kill(pid, signal.SIGTERM)
        print(f"Coleta {pid} parada. A próxima continua de onde parou.")
        return 0
    if args.cmd == "vigia-reativar":
        os.environ.pop("NUBI_VIGIA", None)
        instalar_vigia()
        return 0
    if args.cmd in ("diario", "vendedores", "marcas", "dias", "hermes", "qwen", "estoque", "gestor", "conversar") and not os.environ.get("NUBI_ATUALIZADO"):
        auto_atualizar()
    if args.cmd in ("hermes", "qwen"):
        return cmd_hermes(args, cfg)
    if args.cmd in ("diario", "vendedores", "marcas", "dias", "estoque"):
        instalar_vigia()
    if args.cmd == "estoque":
        return executar("estoque", lambda p, cfg, token: coletar_estoque(p, cfg, token, not args.sem_enviar))
    if args.cmd == "gestor":
        return executar("gestor", coletar_gestor)
    if args.cmd == "atualizar":
        novo = urllib.request.urlopen(f"{NUBI}/coletor/coletor.py", timeout=60).read()
        compile(novo, "coletor.py", "exec")               # só troca se o arquivo novo estiver íntegro
        Path(__file__).write_bytes(novo)
        print("OK: coletor atualizado.")
        if not os.environ.get("NUBI_VIGIA"):
            subprocess.run([str(PASTA / "coletor"), "vigia-reativar"], check=False)   # já com a versão nova
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
            # histórico de vendas diárias ainda incompleto: continua por até 1h30 (de madrugada, até as 06:40),
            # depois do resumo do dia já sair
            agora = datetime.now()
            limite = agora.replace(hour=6, minute=40, second=0)
            rc2 = cmd_dias(None, max(90 * 60, (limite - agora).total_seconds()) if agora < limite else 90 * 60)
            return rc or rc2
        return rc
    if args.cmd == "dias":
        return cmd_dias(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
