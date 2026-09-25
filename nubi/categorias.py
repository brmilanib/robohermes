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
    for tam in (3, 2):
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
