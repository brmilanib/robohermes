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
import os
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
    "Importados low ticket": [r"low ?cost", r"\bbaratos?\b", r"acessive", r"affordable", r"budget", r"dupes?\b",
                              r"alternativ", r"polones", r"polish", r"polonia", r"poland"],
    "Outros": [r"maquiagem", r"makeup", r"skin ?care", r"body (butter|scrub)", r"esfoliante"],
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
                if nubi.compacta(marca) not in nubi.compacta(r.get("title", "") + " " + _limpa(r.get("snippet", ""))):
                    continue                      # resultado que não fala da marca (ex.: "Paris Elysees" -> Champs-Élysées)
                achados.append({"fonte": f"wikipedia {lang}", "titulo": r["title"], "texto": _limpa(r.get("snippet")),
                                "link": f"https://{lang}.wikipedia.org/wiki/" + urllib.parse.quote(r["title"].replace(" ", "_"))})
        except Exception:  # noqa: BLE001
            pass
    return achados


CATS_IA = {
    "Alta perfumaria": "casas de luxo clássicas, maisons de alta joalheria/alta costura (Dior, Chanel, Guerlain, Bvlgari, Lancôme, Hermès, Tom Ford)",
    "Designer": "grifes de MODA importadas: empresas que vendem principalmente roupas, bolsas, calçados e acessórios, e o "
                "perfume é um produto licenciado (Carolina Herrera, Rabanne, Azzaro, Calvin Klein, Hugo Boss, Zara); "
                "inclui marcas de celebridade (Britney Spears, Shakira)",
    "Nicho": "perfumaria de nicho/artística, independente, ticket alto (Xerjoff, Creed, Parfums de Marly, Nishane, Initio)",
    "Árabe": "marcas dos Emirados, Arábia Saudita e Oriente Médio (Lattafa, Armaf, Al Wataniah, Afnan, Maison Alhambra)",
    "Importados low ticket": "marcas IMPORTADAS (de fora do Brasil e do Oriente Médio) que SÓ fazem perfume, não são grife de "
                             "moda, e têm preço mais em conta (La Rive da Polônia, Paris Elysees e Ulric de Varens da França, "
                             "Cuba Paris, Brand Collection)",
    "Nacional": "perfumaria nacional: marcas BRASILEIRAS de perfume, inclusive as de inspirações/contratipos e as de "
                "cosméticos (Natura, O Boticário, Eudora, WePink, Lescent, Attracione, Barbour's Beauty)",
    "Outros": "não é marca de perfume (maquiagem, cuidados com o corpo, cosméticos em geral)",
}


def ia_disponivel():
    return "claude" if os.environ.get("ANTHROPIC_API_KEY") else "chatgpt" if os.environ.get("OPENAI_API_KEY") else None


def _post_json(url, corpo, cab, timeout=90):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **cab})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def pesquisar_ia(marca, pistas=""):
    """
    Pergunta a uma IA com pesquisa na web (Claude ou ChatGPT, a que tiver chave) qual é a categoria da marca.
    Devolve {categoria, confianca, motivo, fontes, ia} ou None (sem chave ou erro).
    """
    ia = ia_disponivel()
    if not ia:
        return None
    lista = "\n".join(f"- {c}: {d}" for c, d in CATS_IA.items())
    pergunta = (
        f'Pesquise na web a marca de perfumes "{marca}", vendida no Mercado Livre Brasil. Descubra a origem da empresa '
        f"(país), se ela é uma grife de moda (vende roupas/acessórios) ou só faz perfume, e a faixa de preço. "
        f"Classifique em UMA destas categorias:\n{lista}\n"
        "Regras: grife de moda importada = Designer; importada que só faz perfume e é barata = Importados low ticket; "
        "brasileira = Nacional (mesmo com nome em francês ou inglês, ex.: Amakha Paris, Lescent); "
        "do Oriente Médio = Árabe; casa de luxo clássica = Alta perfumaria.\n"
        f"Pistas que já temos: {pistas or 'nenhuma'}.\n"
        'Responda SOMENTE com um JSON: {"categoria": "<uma das categorias acima>", "confianca": "alta|média|baixa", '
        '"motivo": "<1 ou 2 frases em português: país de origem e o que a marca é>", "fontes": ["<url>", ...]}. '
        "Se não achar nada confiável sobre a marca, use confianca baixa e diga isso no motivo.")
    try:
        if ia == "claude":
            r = _post_json("https://api.anthropic.com/v1/messages", {
                "model": os.environ.get("NUBI_IA_MODELO", "claude-sonnet-5"), "max_tokens": 1200,
                "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}],
                "messages": [{"role": "user", "content": pergunta}]},
                {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
            texto = " ".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text")
            links = [c.get("url") for b in r.get("content", []) for c in (b.get("citations") or []) if c.get("url")]
        else:
            r = _post_json("https://api.openai.com/v1/responses", {
                "model": os.environ.get("NUBI_IA_MODELO", "gpt-4.1"), "tools": [{"type": "web_search_preview"}],
                "input": pergunta}, {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
            partes = [c for o in r.get("output", []) if o.get("type") == "message" for c in o.get("content", [])]
            texto = " ".join(c.get("text", "") for c in partes)
            links = [a.get("url") for c in partes for a in (c.get("annotations") or []) if a.get("url")]
        m = re.search(r"\{.*\}", texto, re.S)
        j = json.loads(m.group(0)) if m else {}
        cat = j.get("categoria")
        if cat not in CATS_IA:
            return {"categoria": None, "confianca": "baixa", "motivo": texto[:300], "fontes": links[:3], "ia": ia}
        fontes = [f for f in (j.get("fontes") or []) if isinstance(f, str) and f.startswith("http")] or links
        return {"categoria": cat, "confianca": (j.get("confianca") or "média").replace("media", "média"),
                "motivo": j.get("motivo") or "", "fontes": list(dict.fromkeys(fontes))[:3], "ia": ia}
    except Exception as e:  # noqa: BLE001
        return {"categoria": None, "confianca": "baixa", "motivo": f"a IA não respondeu ({str(e)[:120]})",
                "fontes": [], "ia": ia}


def sugerir(marca, gtins=(), preco_medio=None, web=None, usar_ia=True):
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
            for c in ("Designer", "Nicho", "Importados low ticket", "Alta perfumaria"):
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
            pontos["Importados low ticket"] += 0.5
        ev.append({"fonte": "preço", "texto": f"Preço médio no ranking: R$ {preco_medio:,.0f}".replace(",", "."), "link": ""})
    # 4) IA com pesquisa na web (Claude ou ChatGPT): pesa mais que as outras pistas
    ia = None
    if usar_ia and ia_disponivel():
        resumo = "; ".join(e["texto"] for e in ev if e["fonte"] in ("código de barras", "preço"))
        ia = pesquisar_ia(marca, resumo)
        if ia:
            if ia["categoria"]:
                pontos[ia["categoria"]] += {"alta": 7, "média": 5}.get(ia["confianca"], 2.5)
            nome_ia = "IA (Claude)" if ia["ia"] == "claude" else "IA (ChatGPT)"
            ev.insert(0, {"fonte": nome_ia, "texto": (f"{ia['categoria']} — " if ia["categoria"] else "") + ia["motivo"],
                          "link": ia["fontes"][0] if ia["fontes"] else ""})
            for f in ia["fontes"][1:]:
                ev.insert(1, {"fonte": "fonte da IA", "texto": f, "link": f})
    melhor = max(pontos.items(), key=lambda kv: kv[1])
    segundo = sorted(pontos.values(), reverse=True)[1]
    conf = "alta" if melhor[1] >= 4 and melhor[1] - segundo >= 2 else "média" if melhor[1] >= 2.5 else "baixa"
    if ia and ia["categoria"] and melhor[0] == ia["categoria"]:
        conf = ia["confianca"] if ia["confianca"] in ("alta", "média") else conf
    return {"marca": marca, "sugestao": melhor[0] if melhor[1] > 0.5 else None, "confianca": conf, "ia": ia_disponivel(),
            "pontos": {k: round(v, 1) for k, v in pontos.items()}, "evidencias": ev,
            "google": "https://www.google.com/search?" + urllib.parse.urlencode({"q": f"{marca} perfume marca origem"})}
