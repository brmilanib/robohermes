# -*- coding: utf-8 -*-
"""
Categoria de cada marca (Designer, Nicho, Árabe, Nacional, Outros) para o relatório de categorias do ranking.

A classificação automática vem da lista abaixo (marcas conhecidas do mercado de perfumes no Brasil).
O que você escolher na tela (tabela marca_categorias) vence a lista. Marca que não está em nenhum
dos dois fica "Sem categoria" até alguém escolher.
"""

import nubi

CATEGORIAS = ["Alta perfumaria", "Designer", "Nicho", "Árabe", "Importados low ticket", "Nacional", "Outros"]
SEM = "Sem categoria"

SEMENTE = {
    # vem antes de Designer: as casas de luxo ficam aqui mesmo aparecendo também na lista de grifes
    "Alta perfumaria": """
        DIOR, CHRISTIAN DIOR, CHANEL, GUERLAIN, BVLGARI, BULGARI, LANCOME, HERMES, CARTIER, TOM FORD, GIVENCHY,
        LOUIS VUITTON, CHOPARD, VAN CLEEF & ARPELS, BOUCHERON, LALIQUE, ESTEE LAUDER, LOEWE, BOTTEGA VENETA
    """,
    "Designer": """
        CAROLINA HERRERA, RABANNE, PACO RABANNE, LANCOME, JEAN PAUL GAULTIER, AZZARO, CALVIN KLEIN, ARMANI BEAUTY,
        GIORGIO ARMANI, YVES SAINT LAURENT, YSL, DIOR, CHRISTIAN DIOR, DOLCE & GABBANA, RALPH LAUREN, NAUTICA, VERSACE,
        HUGO BOSS, BOSS, BANDERAS, ANTONIO BANDERAS, PRADA, CHANEL, VICTORIA'S SECRET, ISSEY MIYAKE, ISSEI MIAKE,
        MONTBLANC, GIVENCHY, JACQUES BOGART, BVLGARI, BULGARI, CHLOE, BURBERRY, JOOP!, CACHAREL, MERCEDES-BENZ, MUGLER,
        THIERRY MUGLER, FERRARI, SCUDERIA FERRARI, GUCCI, MOSCHINO, DAVIDOFF, GABRIELA SABATINI, BENETTON,
        NARCISO RODRIGUEZ, BRITNEY SPEARS, KENZO, TOMMY HILFIGER, TOMMY, HERMES, NINA RICCI, GUERLAIN, VALENTINO,
        VIKTOR & ROLF, VICTOR & ROLF, MARC JACOBS, MICHAEL KORS, COACH, LACOSTE, DIESEL, ARIANA GRANDE, SHAKIRA,
        TOM FORD, JIMMY CHOO, ZARA, MONTBLANC, BENTLEY, JAGUAR, POLICE, ADIDAS, PARIS HILTON, KATY PERRY, CAROLINA HERRERA NEW YORK,
        ELIZABETH ARDEN, CLINIQUE, ESTEE LAUDER, LOEWE, CARTIER, CHOPARD, SALVATORE FERRAGAMO, FERRAGAMO, EMPORIO ARMANI,
        DKNY, DONNA KARAN, ESCADA, ELIE SAAB, ZADIG & VOLTAIRE, BOUCHERON, VAN CLEEF & ARPELS, LALIQUE, TED LAPIDUS,
        ADOLFO DOMINGUEZ, JEANNE ARTHES, KARL LAGERFELD, LANVIN, ROCHAS, SALVADOR DALI, JESUS DEL POZO, HALLOWEEN,
        ANGEL SCHLESSER, AGATHA RUIZ DE LA PRADA, BOTTEGA VENETA, MAISON MARGIELA, ACQUA DI PARMA, SHISEIDO, KENNETH COLE,
        PERRY ELLIS, JOHN VARVATOS, AMOR AMOR, AIRE LOEWE, DOLCE GABBANA
    """,
    "Nicho": """
        XERJOFF, PARFUMS DE MARLY, PARFUM DE MARLY, CREED, NISHANE, SOSPIRO, MAISON FRANCIS KURKDJIAN, MFK, INITIO,
        AMOUAGE, KILIAN, BY KILIAN, LE LABO, BYREDO, MANCERA, MONTALE, ROJA, ROJA PARFUMS, FREDERIC MALLE, DIPTYQUE,
        MEMO PARIS, CLIVE CHRISTIAN, PENHALIGON'S, JULIETTE HAS A GUN, BDK PARFUMS, EX NIHILO, TIZIANA TERENZI,
        ORTO PARISI, NASOMATTO, ZOOLOGIST, VILHELM PARFUMERIE, BOND NO 9, ATELIER COLOGNE, JO MALONE, MAISON CRIVELLI,
        PROFUMUM, LORENZO VILLORESI, ORMONDE JAYNE, HISTOIRES DE PARFUMS, SERGE LUTENS, L'ARTISAN PARFUMEUR,
        ETAT LIBRE D'ORANGE, KAJAL, BOADICEA THE VICTORIOUS, ELECTIMUSS, GOLDFIELD & BANKS, MARC-ANTOINE BARROIS,
        STEPHANE HUMBERT LUCAS, NASOMATTO, ESCENTRIC MOLECULES, MOLECULE, JUSBOX, SIMONE ANDREOLI, ARGOS,
        LOUIS VUITTON, MAISON TAHITE, THOMAS KOSMALA, HFC, HAUTE FRAGRANCE COMPANY, CASAMORATI, BOIS 1920,
        ACQUA DI PARMA BLU MEDITERRANEO, FUGAZZI, MIND GAMES, ALEXANDRE.J, ALEXANDRE J, FRANCK BOCLET, ATKINSONS
    """,
    "Árabe": """
        LATTAFA, LATAFFA, LATTAFA PRIDE, BELARA - LATTAFA, AL WATANIAH, ARMAF, MAISON ALHAMBRA, FRENCH AVENUE, AFNAN,
        RASASI, RAYHAAN, PARIS CORNER, KHADLAJ, FRAGRANCE WORLD, MAISON ASRAR, ORIENTICA, MANASIK, RIIFFS, AL HARAMAIN,
        PERFUMES ARABES, MAWWAL, BIDAYA, EMPER, ARD AL ZAAFARAN, AL NUAIM, ZIMAYA, SWISS ARABIAN, AJMAL, ASDAAF, NABEEL,
        AL REHAB, GRANDEUR, GRANDEUR ELITE, DUMONT, ANFAR, AL FARES, GULF ORCHID, SURRATI, ABDUL SAMAD AL QURASHI,
        IBRAHEEM AL QURASHI, ARABIYAT, ARABIYAT PRESTIGE, MY PERFUMES, OTOORI, KHALIS, NUSUK, AL MUSBAH, FA PARIS,
        MILESTONE, AHMED AL MAGHRIBI, OUD ELITE, AL MAJED, ARD AL KHALEEJ, HAMIDI, BADEE AL OUD, ASAD, AL ATTAAR,
        OUD AL ANBAR, JO MILANO, ALHAMBRA, WATANIAH, AL AMBRA, PENDORA SCENTS, ARABIAN OUD, MAISON AL HAMBRA,
        AFNAN PERFUMES, RAWAEH, MOHRA, AMEER AL OUDH, BARAKKAT, LE FALCONE,
    """,
    "Nacional": """
        NATURA, O BOTICARIO, BOTICARIO, EUDORA, JEQUITI, HINODE, WEPINK, AVON, CICLO, CICLO COSMETICOS, EZ COSMETICOS,
        MAHOGANY, AMAKHA PARIS, L'ACQUA DI FIORI, LACQUA DI FIORI, ANIMALE, GRANADO, HANNITY COSMETICOS, NUANCIELO,
        SOUL COSMETICOS, QUASAR, FLORATTA, L'OCCITANE AU BRESIL, THERA COSMETICOS, BOTICOLLECTION, ZAAD, PHEBO,
        GOTA BRASIL, MALBEC, BELLO CHARME, GIOVANNA BABY, BOTICA 214, AGUA DE CHEIRO, POLO WEAR, ISABELLE LA BELLE,
        EGEO, LILY, ARBO, KAIAK, DEO PARFUM, PHYTODERM, FENZZA, COSCENTRA,
        DELLA E DELLE, FIORUCCI, EUDORA PULSE, BEAUTY BOX, QUEM DISSE BERENICE, VULT, RICHARDS, RESERVA, OSKLEN,
        HERING, CHILLI BEANS, TRUSSARDI BRASIL, LA PERLA BRASIL, BRAND COLLECTION BRASIL, GIRAFFE, NINA SECRETS,
        FARMASI BRASIL, MARY KAY, MARIA POMPOSA, LAKMA, DIVAMOR, AROEIRA, APINIL, BELLA DOLCE, BELA DOLCE
    """,
    # importadas que SÓ fazem perfume (não são grife de moda), com ticket mais baixo
    "Importados low ticket": """
        LA RIVE, PARIS ELYSEES, CUBA PARIS, ULRIC DE VARENS, BRAND COLLECTION, JEAN MISS, FRAGLUXE, SAPIL,
        PANTHERA, JEANNE ARTHES, CHATLER, ASPEN, NOVAE PLUS, FRAGRANCE COUTURE, AVIVA, PENDORA
    """,
    # não é marca de perfume (cosmético, maquiagem, cuidados)
    "Outros": """
        TREE HUT, NESTI DANTE, MILANI, NARS, BESSENCIALS
    """,
}


# Quando a mesma marca está na lista de mais de uma categoria (ex.: BOTTEGA VENETA em Alta
# perfumaria e em Designer), quem decide é esta prioridade explícita — não a ordem em que a
# categoria foi definida no dict SEMENTE acima. Precisa conter toda categoria de SEMENTE (senão
# _indice() recusa montar o índice). As casas de luxo (Alta perfumaria) vêm antes de Designer e
# Nicho de propósito, mesmo aparecendo nas duas listas; Designer vem antes de Importados low
# ticket pela mesma razão (ex.: JEANNE ARTHES).
PRIORIDADE_CATEGORIA = ["Alta perfumaria", "Designer", "Nicho", "Árabe", "Nacional", "Importados low ticket", "Outros"]


def _pertence():
    """chave (marca compactada) -> conjunto das categorias que citam essa marca em SEMENTE."""
    pertence = {}
    for cat, texto in SEMENTE.items():
        for m in texto.split(","):
            m = m.strip()
            if m:
                pertence.setdefault(nubi.compacta(m), set()).add(cat)
    return pertence


def _indice(sementes=None):
    """chave -> categoria vencedora pela PRIORIDADE_CATEGORIA, nunca pela ordem de SEMENTE:
    reordenar o dict SEMENTE não muda nenhum resultado de classificar()."""
    faltando = set(SEMENTE) - set(PRIORIDADE_CATEGORIA)
    if faltando:
        raise ValueError(f"Categoria sem prioridade definida em PRIORIDADE_CATEGORIA: {faltando}")
    pertence = sementes if sementes is not None else _pertence()
    return {chave: min(cats, key=PRIORIDADE_CATEGORIA.index) for chave, cats in pertence.items()}


def conflitos():
    """Marcas citadas em mais de uma categoria de SEMENTE: (marca, categoria vencedora, todas as categorias)."""
    saida = []
    for chave, cats in sorted(_pertence().items()):
        if len(cats) > 1:
            vencedora = min(cats, key=PRIORIDADE_CATEGORIA.index)
            saida.append((chave, vencedora, sorted(cats, key=PRIORIDADE_CATEGORIA.index)))
    return saida


INDICE = _indice()


def classificar(marca, manuais=None):
    """(categoria, fonte): fonte 'manual' (escolhida na tela), 'auto' (lista conhecida) ou 'sem'.
    Categoria manual fora de CATEGORIAS (dado velho/corrompido em marca_categorias) vira 'sem' em vez
    de propagar um valor que quebraria serie[cat] em relatorio(); quem lê marca_categorias direto
    (auditoria.conferencias) é quem avisa o Bruno do dado inválido."""
    k = nubi.compacta(marca or "")
    if manuais and k in manuais:
        if manuais[k] in CATEGORIAS:
            return manuais[k], "manual"
        return SEM, "sem"
    if k in INDICE:
        return INDICE[k], "auto"
    # linhas/sub-marcas: "LATTAFA PRIDE", "ISABELLE LA BELLE ASAD..." -> começa com uma marca conhecida
    # 30/09 (estoque: "Lattafa Yara" ficava Sem categoria): a 1ª palavra também, se for marca conhecida de 5+ letras
    for tam in (3, 2, 1):
        pref = " ".join(nubi.sem_acento(marca or "").upper().split()[:tam])
        if nubi.compacta(pref) in INDICE and len(nubi.compacta(pref)) >= 5:
            return INDICE[nubi.compacta(pref)], "auto"
    return SEM, "sem"


def relatorio(meses, linhas_por_mes, manuais=None):
    """
    meses: ['AAAA-MM-01', ...] em ordem; linhas_por_mes: linhas do ranking (já com nomes unificados).
    Devolve a série de cada categoria por mês e a lista de marcas com a categoria.
    """
    cats = CATEGORIAS + [SEM]
    n = len(meses)
    serie = {c: {"vendas": [0.0] * n, "unidades": [0] * n, "marcas": [0] * n} for c in cats}
    marcas = {}
    total = [0.0] * n
    for i, linhas in enumerate(linhas_por_mes):
        for l in linhas:
            nome = l.get("marca") or ""
            cat, fonte = classificar(nome, manuais)
            v = float(l.get("vendas") or 0)
            un = int(l.get("unidades") or 0)
            pos = l.get("posicao")
            serie[cat]["vendas"][i] += v
            serie[cat]["unidades"][i] += un
            total[i] += v
            m = marcas.setdefault(nubi.compacta(nome), {"marca": nome, "categoria": cat, "fonte": fonte,
                                                         "vendas": [None] * n, "posicao": [None] * n, "un": [None] * n})
            if m["vendas"][i] is None:
                # 1ª linha da marca no mês
                m["vendas"][i] = v
                m["un"][i] = un
                m["posicao"][i] = pos
            else:
                # a mesma marca (já unificada) aparece de novo no mesmo mês: soma vendas/unidades,
                # fica com a melhor (menor) posição em vez de sobrescrever com a última linha lida
                m["vendas"][i] += v
                m["un"][i] += un
                if pos is not None and (m["posicao"][i] is None or pos < m["posicao"][i]):
                    m["posicao"][i] = pos
    for m in marcas.values():
        for i in range(n):
            if m["vendas"][i] is not None:
                serie[m["categoria"]]["marcas"][i] += 1
    for c in cats:
        s = serie[c]
        s["share"] = [s["vendas"][i] / total[i] if total[i] else 0 for i in range(n)]
        u, a = s["vendas"][-1], (s["vendas"][-2] if n > 1 else None)
        s["var_mes"] = (u / a - 1) if a else None
        s["var_share"] = (s["share"][-1] - s["share"][-2]) if n > 1 else None
    lista = sorted(marcas.values(), key=lambda m: -(m["vendas"][-1] or 0))
    for m in lista:
        u, a = m["vendas"][-1], (m["vendas"][-2] if n > 1 else None)
        m["ultimo"] = u
        uu = m["un"][-1]
        m["preco_medio"] = (u / uu) if u and uu else None
        m["var_mes"] = (u / a - 1) if u is not None and a else None
        m["share_cat"] = (u or 0) / serie[m["categoria"]]["vendas"][-1] if serie[m["categoria"]]["vendas"][-1] else 0
    return {"meses": [m[:7] for m in meses], "categorias": cats, "serie": serie, "total": total, "marcas": lista,
            "sem_categoria": [m for m in lista if m["categoria"] == SEM]}


# ---------------------------------------------------------------------------
# 30/09 (Bruno: "no meu estoque, uma aba com o estoque por categoria, igual ao ranking de marcas"): a marca de cada item do
# estoque sai do título (o UpSeller não tem coluna de marca) e a categoria é a mesma do ranking (classificar).
TIPOS_PRODUTO = [
    # 01/10 (Bruno: "produto de outra categoria tem que ter a categoria certa, mesmo sendo da mesma marca"): tipos fora
    # de perfumaria viram categoria própria do item (Eletrônicos, Maquiagem, Cabelo, Skincare…), não a categoria da marca.
    # Ordem importa: "tábua de corte com cabo" é Utilidades domésticas, não Eletrônicos; "difusor elétrico" é Casa.
    ("Utilidades domésticas", ("tabua", "faca", "facas", "caneca", "copo", "taca", "jogo americano", "sousplat", "tapete", "capacho",
                               "petisqueira", "panela", "frigideira", "talher", "talheres", "prato", "garrafa", "lixeira", "escorredor",
                               "pote", "jarra", "bandeja", "porta", "organizador", "churrasco", "cozinha", "toalha", "lencol", "almofada")),
    ("Casa", ("home spray", "difusor", "interiores", "aromatizador", "vela aromatica", "vela", "sache", "agua perfumada para tecidos",
              "abajur", "luminaria", "cortina", "quadro", "vaso")),
    ("Eletrônicos", ("escova secadora", "escova modeladora", "escova alisadora", "secador", "chapinha", "prancha", "modelador",
                     "babyliss", "barbeador", "depilador", "massageador", "pen drive", "fire tv", "stick", "drone", "camera", "smartwatch",
                     "relogio", "controle remoto", "caixa de som", "fone", "carregador", "alexa", "wi-fi", "wifi", "bluetooth", "tela",
                     "monitor", "notebook", "celular", "tablet", "echo", "lampada inteligente", "roteador")),
    # 01/10 (Bruno, "tudo errado ainda"): "Good Girl BLUSH Eau de Parfum", "Noble BLUSH by Lattafa 100ml" e "Shampoo a seco
    # Batiste BLUSH" iam para Maquiagem por causa da palavra "blush". Perfume e body splash (e cabelo/skincare explícitos)
    # vêm ANTES de maquiagem; "blush" só decide quando não há sinal de perfume.
    ("Body splash", ("body splash", "perfume mist", "body mist", "hair mist", "desodorante colonia", "splash")),
    ("Perfume", ("perfume", "perfumes", "eau de parfum", "eau de toilette", "parfum", "extrait", "edp", "edt", "colonia", "decant", "fragrancia")),
    ("Cabelo", ("shampoo", "condicionador", "mascara capilar", "leave in", "leave-in", "oleo capilar", "finalizador", "tonico capilar",
                "cabelo", "cabelos", "capilar")),
    ("Skincare", ("serum", "protetor solar", "vitamina c", "skincare", "retinal", "retinol", "acido", "esfoliante", "demaquilante",
                  "limpeza de pele", "anti sinais", "antissinais", "anti idade", "antiidade", "gel creme", "sabonete")),
    ("Maquiagem", ("batom", "base liquida", "rimel", "mascara de cilios", "paleta", "blush", "corretivo", "po compacto", "delineador",
                   "gloss", "primer", "iluminador", "sombra", "lapis de olho", "maquiagem", "esmalte")),
    ("Skincare", ("facial", "hidratante", "creme", "tonico", "bronzeador", "lenco", "lip balm", "locao", "pore")),
]
# tipos que seguem a categoria da MARCA (Árabe, Designer, Nicho…); os outros são categoria por si (o próprio tipo)
TIPOS_DA_MARCA = ("Perfume", "Body splash", "Outros")
# categorias de PRODUTO (01/10): as do tipo + as que o Astra ou o Bruno criarem na tela (lista aberta)
CATEGORIAS_PRODUTO = ["Skincare", "Maquiagem", "Cabelo", "Eletrônicos", "Casa", "Utilidades domésticas", "Acessórios",
                      "Alimentos e bebidas", "Infantil", "Pet", "Papelaria", "Moda", "Saúde"]


def categoria_produto_nome(txt):
    """Nome limpo de uma categoria de produto (a do Astra ou a digitada): grafia conhecida ganha; senão 'Primeira maiúscula'."""
    t = " ".join(str(txt or "").split())[:40]
    if not t:
        return ""
    for c in CATEGORIAS + CATEGORIAS_PRODUTO + [t for t, _ in TIPOS_PRODUTO]:
        if nubi.compacta(c) == nubi.compacta(t):
            return c
    return t[:1].upper() + t[1:]
# 01/10 (Sospiro Vibrato em Árabe): "Perfume" virou marca porque existe uma marca "PERFUME" no Explorador; palavra de
# anúncio nunca é marca
GENERICAS = {"perfume", "perfumes", "perfumaria", "kit", "kits", "importado", "importados", "original", "originais", "eau",
             "parfum", "edp", "edt", "edc", "decant", "body", "splash", "mist", "spray", "masculino", "feminino", "unissex",
             "novo", "nova", "promocao", "oferta", "lacrado", "colonia", "desodorante", "creme", "serum", "nicho",
             # 01/10: "Shampoo" virou marca do Batiste Blush; palavra de produto nunca é marca
             "shampoo", "condicionador", "blush", "batom", "gel", "sabonete", "hidratante", "locao", "mist", "home", "sache",
             "difusor", "aromatizador", "vela", "tapete", "caneca", "faca", "facas", "drone", "stick", "fire", "smartwatch",
             # 02/10 (Bruno: "não tem nada a ver essa marca Perfume Árabe"): "Perfume Árabe" virou a 3ª marca do estoque
             "arabe", "arabes", "arabia", "masculina", "feminina", "unisex", "fragrancia", "oriental", "alta", "fixacao",
             "original", "lancamento", "contratipo", "inspiracao", "inspirado"}


def tipo_produto(titulo):
    t = " " + " ".join(nubi.normalizar(titulo or "").split()) + " "
    for tipo, palavras in TIPOS_PRODUTO:
        if any(f" {p} " in t for p in palavras):
            return tipo
    return "Outros"


def marca_do_titulo(titulo, conhecidas):
    """A marca conhecida mais longa que aparece no título (1 a 4 palavras seguidas, comparando sem espaço/acento):
    "Perfume Asad Elixir Lattafa" -> LATTAFA (ganha de ASAD, que é mais curto). conhecidas: {chave compacta: nome}.
    Palavra de anúncio (perfume, kit, importado…) nunca é marca, mesmo que exista como "marca" no Explorador."""
    pal = nubi.normalizar(titulo or "").split()
    melhor = None
    for n in (5, 4, 3, 2, 1):
        for i in range(len(pal) - n + 1):
            jan = pal[i:i + n]
            if all(w in GENERICAS for w in jan):
                continue
            # "Dolce and Gabbana" = "DOLCE & GABBANA": o conectivo não conta (nem na 1ª/última palavra)
            sem_con = [w for w in jan if w not in ("and", "e", "y", "et")] if jan[0] not in ("and", "e") and jan[-1] not in ("and", "e") else jan
            for k in {nubi.compacta(" ".join(jan)), nubi.compacta(" ".join(sem_con))}:
                if len(k) >= 4 and k in conhecidas and (melhor is None or len(k) > len(melhor)):
                    melhor = k
    return conhecidas[melhor] if melhor else None


CRESCIMENTO_PADRAO = 0.20
MARKUP_PADRAO = 1.85     # 02/10 (Bruno): "coloca 1,85, que é a média anual a última vez que eu vi"; editável na tela


def ranking_marcas(lista, crescimento=CRESCIMENTO_PADRAO, markup=MARKUP_PADRAO):
    """02/10 (Bruno: "ranking de marcas dentro do meu estoque: SKUs, unidades, custo total, potencial de vendas; ao clicar,
    os produtos com custo, estoque, trânsito e sugestão de compra pela venda com crescimento de 20%"). Entra a `lista` de
    `estoque_por_categoria` (1 linha por SKU). Por SKU: potencial = custo em estoque × markup médio (Bruno: "tem que pegar
    o custo vezes 1,85", não o preço de venda do SKU, que às vezes está baixo porque estou rankeando); sugestão = venda 30d
    × (1 + crescimento) − disponível − trânsito, nunca negativa, arredondada para cima; custo da sugestão = sugestão × custo
    médio. Devolve {marcas: [...], itens: {marca: [...]}}."""
    import math
    markup = float(markup or MARKUP_PADRAO)
    por = {}
    itens = {}
    reservado = [0.0, 0.0]
    for x in lista:
        m = x.get("marca") or "(marca não identificada)"
        disp = float(x.get("disponivel") if x.get("disponivel") is not None else x.get("atual") or 0)
        trans = float(x.get("transito") or 0)
        vu = float(x.get("vend_un") or 0)
        pv = x.get("preco_venda")
        custo = x.get("custo")
        potencial = round(max(disp, 0) * float(custo) * markup, 2) if custo is not None else None
        sug = max(0, math.ceil(vu * (1 + crescimento) - disp - trans)) if vu > 0 else 0
        it = {"sku": x.get("sku"), "titulo": x.get("titulo"), "marca_manual": bool(x.get("marca_manual")), "custo": custo, "disponivel": disp, "transito": trans,
              "valor": round(disp * float(custo), 2) if custo is not None else 0.0, "vend_un": vu, "vend_valor": float(x.get("vend_valor") or 0),
              "preco_venda": pv, "potencial": potencial, "cobertura_dias": x.get("cobertura_dias"),
              "sugestao": sug, "sugestao_custo": round(sug * float(custo), 2) if custo is not None and sug else 0.0}
        itens.setdefault(m, []).append(it)
        if custo is not None and x.get("atual") is not None:   # vendido esperando envio: está no galpão, mas não é disponível
            res = max(float(x.get("atual") or 0) - max(disp, 0), 0)
            reservado[0] += res
            reservado[1] += res * float(custo)
        g = por.setdefault(m, {"marca": m, "categoria": x.get("categoria"), "skus": 0, "com_estoque": 0, "unidades": 0.0, "transito": 0.0,
                               "custo": 0.0, "potencial": 0.0, "skus_sem_custo": 0, "vend_un": 0.0, "vend_valor": 0.0,
                               "sugestao": 0, "sugestao_custo": 0.0})
        g["skus"] += 1
        g["com_estoque"] += 1 if disp > 0 else 0
        g["unidades"] += disp
        g["transito"] += trans
        g["custo"] += it["valor"]
        if potencial is not None:
            g["potencial"] += potencial
        elif disp > 0:
            g["skus_sem_custo"] += 1
        g["vend_un"] += vu
        g["vend_valor"] += it["vend_valor"]
        g["sugestao"] += sug
        g["sugestao_custo"] += it["sugestao_custo"]
    total_custo = sum(g["custo"] for g in por.values()) or 1.0
    total_vend = sum(g["vend_valor"] for g in por.values()) or 1.0
    marcas = []
    for g in por.values():
        g = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in g.items()}
        g["pct_custo"] = round(g["custo"] / total_custo, 4)
        g["pct_vendas"] = round(g["vend_valor"] / total_vend, 4)
        g["cobertura_dias"] = round(g["unidades"] / (g["vend_un"] / 30), 1) if g["vend_un"] else None
        g["margem_potencial"] = round(g["potencial"] - g["custo"], 2)
        marcas.append(g)
    marcas.sort(key=lambda g: (-g["custo"], -g["unidades"]))
    for i, g in enumerate(marcas, 1):
        g["posicao"] = i
    for xs in itens.values():
        xs.sort(key=lambda it: (-it["sugestao"], -it["valor"]))
    return {"marcas": marcas, "itens": itens, "crescimento": crescimento, "markup_usado": markup,
            "total": {"reservado_un": round(reservado[0], 2), "reservado_custo": round(reservado[1], 2),
                      "skus": sum(g["skus"] for g in marcas), "unidades": round(sum(g["unidades"] for g in marcas), 2),
                      "custo": round(sum(g["custo"] for g in marcas), 2), "potencial": round(sum(g["potencial"] for g in marcas), 2),
                      "sugestao": sum(g["sugestao"] for g in marcas), "sugestao_custo": round(sum(g["sugestao_custo"] for g in marcas), 2)}}


def estoque_por_categoria(itens, conhecidas, manuais=None, vendas_sku=None, marca_sku=None, marca_ia=None,
                          categoria_sku=None, categoria_ia=None):
    """itens do estoque (sku, titulo, atual, custo_medio) -> totais por categoria, por tipo de produto e por marca.
    vendas_sku: {sku compactado: {"unidades", "valor"}} dos últimos 30 dias (relatório do UpSeller).
    marca_sku: {sku compactado: marca} escolhida pelo Bruno na tela (vence a marca achada no título).
    categoria_sku / categoria_ia (01/10): categoria do PRODUTO escolhida pelo Bruno / lida pelo Astra (título + GTIN); a do
    Bruno vence tudo; a do Astra vence o tipo e a marca."""
    vendas_sku, marca_sku, marca_ia = vendas_sku or {}, marca_sku or {}, marca_ia or {}
    categoria_sku, categoria_ia = categoria_sku or {}, categoria_ia or {}
    lista = []
    cats, tipos, marcas = {}, {}, {}
    total = {"skus": 0, "unidades": 0.0, "valor": 0.0, "vend_un": 0.0, "vend_valor": 0.0}
    sem = []
    for it in itens:
        atual = float(it.get("atual") or 0)
        custo = it.get("custo_medio")
        valor = atual * float(custo) if custo not in (None, "") else 0.0
        manual = marca_sku.get(nubi.compacta(it.get("sku") or ""))
        # ordem: a que o Bruno escolheu > a achada no título > a que o Astra leu no título (30/09)
        marca = manual or marca_do_titulo(it.get("titulo"), conhecidas) or marca_ia.get(nubi.compacta(it.get("sku") or ""))
        tipo = tipo_produto(it.get("titulo"))
        ks = nubi.compacta(it.get("sku") or "")
        if categoria_sku.get(ks):
            cat, fonte_cat = categoria_sku[ks], "manual_sku"
        elif categoria_ia.get(ks):
            cat, fonte_cat = categoria_ia[ks], "astra"
        elif tipo in TIPOS_DA_MARCA:
            cat, fonte_cat = classificar(marca, manuais) if marca else (SEM, "sem")
        else:                                   # 01/10: escova da Revlon é Eletrônicos, não Designer
            cat, fonte_cat = tipo, "tipo"
        v = vendas_sku.get(nubi.compacta(it.get("sku") or ""), {})
        vu, vv = float(v.get("unidades") or 0), float(v.get("valor") or 0)
        for grupo, chave in ((cats, cat), (tipos, tipo), (marcas, marca or "(marca não identificada)")):
            g = grupo.setdefault(chave, {"skus": 0, "com_estoque": 0, "zerados": 0, "unidades": 0.0, "valor": 0.0,
                                         "vend_un": 0.0, "vend_valor": 0.0})
            g["skus"] += 1
            g["com_estoque" if atual > 0 else "zerados"] += 1
            g["unidades"] += atual
            g["valor"] += valor
            g["vend_un"] += vu
            g["vend_valor"] += vv
        m = marcas[marca or "(marca não identificada)"]
        m.setdefault("categoria", cat)
        m.setdefault("tipos", {})
        m["tipos"][tipo] = m["tipos"].get(tipo, 0) + 1
        # 01/10 (Bruno: "no UpSeller tenho 13 Naxos disponíveis e a tela mostrava 15"): o "atual" conta o que já está
        # reservado em pedido (ocupado); o que dá para vender é o DISPONÍVEL — é ele que vai na lista e na cobertura
        disp = float(it.get("disponivel")) if it.get("disponivel") not in (None, "") else atual
        lista.append({"sku": it.get("sku"), "titulo": it.get("titulo"), "marca": marca or "", "marca_manual": bool(manual),
                      "categoria": cat, "categoria_fonte": fonte_cat, "tipo": tipo, "atual": atual, "disponivel": disp,
                      "ocupado": float(it.get("ocupado") or 0), "transito": float(it.get("transito_compra") or 0) + float(it.get("transito_transf") or 0),
                      "custo": float(custo) if custo not in (None, "") else None,
                      "valor": round(valor, 2), "vend_un": vu, "vend_valor": round(vv, 2), "media_dia": round(vu / 30, 2) if vu else 0,
                      # 01/10 (Bruno): preço de venda atual = preço médio das vendas dos últimos 30 dias (UpSeller)
                      "preco_venda": round(vv / vu, 2) if vu and vv else None,
                      "cobertura_dias": round(disp / (vu / 30), 1) if vu else None})
        if not marca and atual > 0:
            sem.append({"sku": it.get("sku"), "titulo": it.get("titulo"), "atual": atual, "valor": round(valor, 2)})
        total["skus"] += 1
        total["unidades"] += atual
        total["valor"] += valor
        total["vend_un"] += vu
        total["vend_valor"] += vv

    def fechar(d, nome):
        out = []
        for k, g in d.items():
            x = {nome: k, **{c: (round(v, 2) if isinstance(v, float) else v) for c, v in g.items() if c != "tipos"}}
            x["pct_valor"] = round(g["valor"] / total["valor"], 4) if total["valor"] else 0
            x["pct_vendas"] = round(g["vend_valor"] / total["vend_valor"], 4) if total["vend_valor"] else 0
            x["cobertura_dias"] = round(g["unidades"] / (g["vend_un"] / 30), 1) if g["vend_un"] else None
            if "tipos" in g:
                x["tipo"] = max(g["tipos"], key=g["tipos"].get)
            out.append(x)
        return sorted(out, key=lambda x: -x["valor"])
    sem.sort(key=lambda x: -x["valor"])
    extras = sorted({c for c in cats if c not in CATEGORIAS and c not in CATEGORIAS_PRODUTO and c != SEM})
    return {"total": {k: round(v, 2) if isinstance(v, float) else v for k, v in total.items()},
            "categorias": fechar(cats, "categoria"), "tipos": fechar(tipos, "tipo"), "marcas": fechar(marcas, "marca"),
            "sem_marca": sem[:60], "ordem": CATEGORIAS + CATEGORIAS_PRODUTO + extras + [SEM],
            "opcoes": CATEGORIAS, "opcoes_produto": CATEGORIAS_PRODUTO + extras,
            "itens": sorted(lista, key=lambda x: (-x["valor"], -x["atual"]))}


# Card #128 (desafio #126): liga um anúncio real do ML (formato meli.normalizar_item: titulo, gtin, full, tipo) à linha do
# Nubimetrics (vend_anuncios: titulo, gtin, marca_chave, fulfillment, tipo_pub, unidades). Só regras, sem IA.
# Ordem: ligação manual (intocável) > GTIN > título forte > título fraco (a conferir). A foto fica para o embedding.
def _gtins(v):
    import meli
    return {g.lstrip("0") for g in meli.gtins_do_texto(v)}


def _desempate(anuncio, cands):
    """Mesmo produto em 2 linhas (Full e não Full, Clássico e Premium): fica a de Full e tipo iguais, depois a que mais
    vende. -> (linha, empate); empate = ainda sobrou mais de uma com Full e tipo iguais."""
    tipo = str(anuncio.get("tipo") or "").lower()
    nota = lambda l: ((bool(l.get("fulfillment")) == bool(anuncio.get("full")))
                      + bool(tipo and str(l.get("tipo_pub") or "").lower().startswith(tipo)))
    melhor = max(nota(l) for l in cands)
    cands = [l for l in cands if nota(l) == melhor]
    return max(cands, key=lambda l: int(l.get("unidades") or 0)), len(cands) > 1


def casar_anuncio_nubimetrics(anuncio, linhas, conhecidas=None, ligacao=None):
    """-> {"linha", "metodo" (manual/gtin/titulo_forte/titulo_fraco/None), "a_conferir"}.
    ligacao: a já gravada para este anúncio ({"metodo", "linha"}); "manual" nunca é desfeita.
    conhecidas: {chave compacta: marca} para marca_do_titulo (marca do título diferente da marca_chave = outro produto)."""
    import produtos_iguais as pi
    if ligacao and ligacao.get("metodo") == "manual":
        return {"linha": ligacao.get("linha"), "metodo": "manual", "a_conferir": False}
    g = _gtins(anuncio.get("gtin"))
    if g:
        cands = [l for l in linhas if g & _gtins(l.get("gtin"))]
        if cands:
            linha, empate = _desempate(anuncio, cands)
            return {"linha": linha, "metodo": "gtin", "a_conferir": empate}
    marca = marca_do_titulo(anuncio.get("titulo"), conhecidas or {})
    a = {"titulo": anuncio.get("titulo") or "", "marca": marca or ""}
    fortes, fracos = [], []
    for l in linhas:
        if g and _gtins(l.get("gtin")):
            continue                    # os dois têm GTIN e são diferentes: outro produto, o título não passa por cima
        if marca and l.get("marca_chave") and nubi.compacta(marca) != nubi.compacta(l["marca_chave"]):
            continue
        b = {"titulo": l.get("titulo") or "", "marca": l.get("marca_chave") or ""}
        if pi.pode_juntar_sozinho(a, b):
            fortes.append(l)
        elif pi.motivo_conferencia(a, b) and pi.palavras_nome(a["titulo"], a["marca"]) & pi.palavras_nome(b["titulo"], b["marca"]):
            fracos.append(l)            # volume de um lado só, ou nome parecido ("Asad" x "Asad Bourbon"): o Bruno confere
    if fortes:
        linha, empate = _desempate(anuncio, fortes)
        return {"linha": linha, "metodo": "titulo_forte", "a_conferir": empate}
    if fracos:
        return {"linha": _desempate(anuncio, fracos)[0], "metodo": "titulo_fraco", "a_conferir": True}
    return {"linha": None, "metodo": None, "a_conferir": False}
