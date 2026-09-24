# -*- coding: utf-8 -*-
"""
Sugere a categoria de uma marca (Alta perfumaria, Designer, Nicho, Árabe, Nacional, Outros) juntando pistas:

1. País do código de barras (prefixo GS1 do GTIN) dos produtos da marca que já estão no nubi
   (vendedores monitorados e Explorador): 789/790 = Brasil, 628 = Arábia Saudita, 629 = Emirados…
   É onde a empresa registrou o código — boa pista da origem da marca.
2. O que a internet diz: resultados de busca (DuckDuckGo) e Wikipédia (pt/en), procurando palavras
   como "árabe", "Dubai", "brasileira", "nicho", "grife", "contratipo"…
3. Preço médio no ranking (muito caro puxa para nicho/alta perfumaria; muito barato, para nacional/outros).

Devolve a categoria com mais pontos, a confiança e as evidências (com link) para você conferir.
"""

import html
import json
import re
import urllib.parse
import urllib.request

import nubi

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36", "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"}

ARABES = {"Bahrein", "Síria", "Egito", "Jordânia", "Kuwait", "Arábia Saudita", "Emirados Árabes", "Líbano",
          "Marrocos", "Argélia", "Tunísia", "Omã", "Catar"}

FAIXAS = [
    (0, 19, "EUA/Canadá"), (30, 39, "EUA/Canadá"), (60, 139, "EUA/Canadá"), (300, 379, "França"),
    (400, 440, "Alemanha"), (450, 459, "Japão"), (490, 499, "Japão"), (460, 469, "Rússia"), (500, 509, "Reino Unido"),
    (520, 521, "Grécia"), (528, 528, "Líbano"), (540, 549, "Bélgica"), (560, 560, "Portugal"), (590, 590, "Polônia"),
    (608, 608, "Bahrein"), (611, 611, "Marrocos"), (613, 613, "Argélia"), (619, 619, "Tunísia"), (621, 621, "Síria"),
    (622, 622, "Egito"), (625, 625, "Jordânia"), (626, 626, "Irã"), (627, 627, "Kuwait"), (628, 628, "Arábia Saudita"),
    (629, 629, "Emirados Árabes"), (640, 649, "Finlândia"), (690, 699, "China"), (700, 709, "Noruega"),
    (729, 729, "Israel"), (730, 739, "Suécia"), (750, 750, "México"), (754, 755, "Canadá"), (760, 769, "Suíça"),
    (770, 771, "Colômbia"), (773, 773, "Uruguai"), (775, 775, "Peru"), (778, 779, "Argentina"), (780, 780, "Chile"),
    (789, 790, "Brasil"), (800, 839, "Itália"), (840, 849, "Espanha"), (868, 869, "Turquia"), (870, 879, "Holanda"),
    (880, 880, "Coreia do Sul"), (885, 885, "Tailândia"), (888, 888, "Singapura"), (890, 890, "Índia"),
    (899, 899, "Indonésia"), (900, 919, "Áustria"), (930, 939, "Austrália"), (940, 949, "Nova Zelândia"),
    (955, 955, "Malásia"),
]

PALAVRAS = {
    "Árabe": [r"\barabe", r"\barabic", r"\barab\b", r"\bdubai", r"emirados", r"\buae\b", r"emirates", r"\boud\b",
              r"arabia", r"sharjah", r"saudi", r"oriente medio", r"middle east", r"orientais?\b"],
    "Nacional": [r"brasileir", r"brazilian", r"made in brazil", r"\bbrasil\b", r"contratipo", r"inspirad",
                 r"inspiracao", r"cosmeticos ltda", r"sao paulo", r"minas gerais", r"parana", r"rio grande"],
    "Nicho": [r"\bnicho\b", r"\bniche\b", r"artisan", r"haute parfumerie", r"perfumaria de nicho", r"independent perfum",
              r"maison de parfum"],
    "Alta perfumaria": [r"maison de luxe", r"luxury (fashion )?house", r"haute couture", r"alta perfumaria",
                        r"casa de luxo", r"joalheri", r"jewel"],
    "Designer": [r"\bgrife\b", r"fashion (house|brand|designer)", r"\bdesigner\b", r"estilista", r"marca de moda",
                 r"celebrit", r"celebridade", r"cantora", r"singer", r"atriz", r"actress", r"\bmoda\b"],
    "Outros": [r"low ?cost", r"\bbaratos?\b", r"acessive", r"affordable", r"budget", r"dupes?\b", r"alternativ"],
}


def pais_gtin(g):
    g = re.sub(r"\D", "", str(g or ""))
    if len(g) == 12:
        return "EUA/Canadá"
    if len(g) != 13:
        return None
    p = int(g[:3])
    for a, b, nome in FAIXAS:
        if a <= p <= b:
            return nome
    return None


def _baixar(url, timeout=8):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _limpa(t):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t or ""))).strip()


def buscar_web(marca):
    """Resultados de busca: [{fonte, titulo, texto, link}] (DuckDuckGo + Wikipédia pt/en). Falhas são ignoradas."""
    achados = []
    q = f'"{marca}" perfume marca'
    try:
        pg = _baixar("https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": q, "kl": "br-pt"}))
        blocos = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?class="result__snippet"[^>]*>(.*?)</a>',
                            pg, re.S)
        for link, tit, trecho in blocos[:6]:
            m = re.search(r"uddg=([^&]+)", link)
            link = urllib.parse.unquote(m.group(1)) if m else link
            achados.append({"fonte": "busca", "titulo": _limpa(tit), "texto": _limpa(trecho), "link": link})
    except Exception:  # noqa: BLE001
        pass
    for lang in ("pt", "en"):
        try:
            j = json.loads(_baixar(f"https://{lang}.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
                {"action": "query", "list": "search", "srsearch": f"{marca} perfume", "format": "json", "srlimit": 2})))
            for r in j.get("query", {}).get("search", []):
                if nubi.compacta(marca)[:5] not in nubi.compacta(r.get("title", "") + r.get("snippet", "")):
                    continue                      # resultado que não fala da marca
                achados.append({"fonte": f"wikipedia {lang}", "titulo": r["title"], "texto": _limpa(r.get("snippet")),
                                "link": f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(r["title"].replace(" ", "_"))})
        except Exception:  # noqa: BLE001
            pass
    return achados


def sugerir(marca, gtins=(), preco_medio=None, web=None):
    """
    marca: nome; gtins: códigos de barras dos produtos da marca no nubi; preco_medio: R$ por unidade no ranking;
    web: resultados de buscar_web (None = busca agora). Devolve {sugestao, confianca, pontos, evidencias, google}.
    """
    pontos = {c: 0.0 for c in PALAVRAS}
    ev = []
    # 1) país do código de barras
    paises = {}
    for g in gtins:
        p = pais_gtin(g)
        if p:
            paises[p] = paises.get(p, 0) + 1
    if paises:
        tot = sum(paises.values())
        pais, n = max(paises.items(), key=lambda kv: kv[1])
        frac = n / tot
        txt = ", ".join(f"{p} ({q})" for p, q in sorted(paises.items(), key=lambda kv: -kv[1])[:3])
        if pais == "Brasil" and frac >= 0.6:
            pontos["Nacional"] += 4
        elif pais in ARABES and frac >= 0.5:
            pontos["Árabe"] += 4
        elif frac >= 0.5:
            for c in ("Designer", "Nicho", "Outros", "Alta perfumaria"):
                pontos[c] += 0.5                   # importada; o resto decide qual
            pontos["Nacional"] -= 1
        ev.append({"fonte": "código de barras", "texto": f"País do código de barras de {tot} produto(s): {txt}", "link": ""})
    # 2) internet
    web = buscar_web(marca) if web is None else web
    texto = nubi.sem_acento(" ".join((w.get("titulo") or "") + " " + (w.get("texto") or "") for w in web)).lower()
    for cat, pads in PALAVRAS.items():
        achou = [p for p in pads if re.search(p, texto)]
        if achou:
            pontos[cat] += min(4, 1.5 * len(achou))
    for w in web[:5]:
        ev.append({"fonte": w["fonte"], "texto": (w.get("titulo") or "") + " — " + (w.get("texto") or "")[:220], "link": w.get("link", "")})
    # 3) preço médio
    if preco_medio:
        if preco_medio >= 800:
            pontos["Nicho"] += 1
            pontos["Alta perfumaria"] += 1
        elif preco_medio <= 130:
            pontos["Nacional"] += 0.5
            pontos["Outros"] += 0.5
        ev.append({"fonte": "preço", "texto": f"Preço médio no ranking: R$ {preco_medio:,.0f}".replace(",", "."), "link": ""})
    melhor = max(pontos.items(), key=lambda kv: kv[1])
    segundo = sorted(pontos.values(), reverse=True)[1]
    conf = "alta" if melhor[1] >= 4 and melhor[1] - segundo >= 2 else "média" if melhor[1] >= 2.5 else "baixa"
    return {"marca": marca, "sugestao": melhor[0] if melhor[1] > 0.5 else None, "confianca": conf,
            "pontos": {k: round(v, 1) for k, v in pontos.items()}, "evidencias": ev,
            "google": "https://www.google.com/search?" + urllib.parse.urlencode({"q": f"{marca} perfume marca origem"})}
