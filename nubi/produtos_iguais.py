# -*- coding: utf-8 -*-
"""
Mesmo produto com títulos diferentes (anúncios sem GTIN).

Cada vendedor escreve o título do seu jeito ("Perfume Árabe Vulcan Feu 100ml Lattafa" x "Vulcan Feu Edp 100 Ml
Lattafa Original"); sem GTIN, o nubi tratava cada título como um produto. Aqui a IA (embeddings) mede o quanto os
títulos querem dizer a mesma coisa, e regras fixas barram as confusões comuns em perfumes: marca diferente, tamanho
diferente (100 ml x 200 ml), concentração diferente (EDT x EDP x Elixir) e masculino x feminino.

agrupar(itens, vetores) -> {chave: (grupo, similaridade)} só para as chaves que mudam de grupo.
  itens: [{"chave", "titulo", "marca", "v"}]  (chave "T:..." = sem GTIN; as outras são GTIN, âncoras dos grupos)
"""

import re
import unicodedata

import numpy as np

LIMIAR = 0.82            # similaridade mínima (cosseno); as regras de nome, tamanho e concentração seguram o resto
CONCENTRACOES = [("elixir", r"elixir"), ("extrait", r"extrait|extrato"), ("parfum", r"(?<!de )\bparfum\b"),
                 ("edp", r"\bedp\b|eau de parfum"), ("edt", r"\bedt\b|eau de toilette"), ("edc", r"\bedc\b|eau de cologne|col[oô]nia"),
                 ("intense", r"intens[eo]"), ("body", r"body splash|hidratante|desodorante|lo[cç][aã]o")]


def _norm(t):
    t = unicodedata.normalize("NFKD", (t or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def volumes(t):
    """Tamanhos citados no título, em ml (100ml, 100 ml; '100m' no fim de um título cortado também conta)."""
    n = _norm(t)
    return {int(x) for x in re.findall(r"(\d{2,4})\s*ml\b", n)} | {int(x) for x in re.findall(r"(\d{2,4})\s*m$", n.strip())}


def quantidade(t):
    """Kit ou vários perfumes no mesmo anúncio: 'Kit com 5', 'Kit C/ 4', '2 Perfumes' -> 5, 4, 2; kit sem número -> 'kit'."""
    n = _norm(t)
    m = re.search(r"\bkit\s*(?:com|c/)?\s*(\d+)|\b(\d+)\s*(?:perfumes|unidades|frascos)\b", n)
    if m:
        return int(m.group(1) or m.group(2))
    return "kit" if re.search(r"\bkit\b", n) else 1


def numeros(t):
    """Outros números do título (modelos, códigos: C3000 x 4000), fora os tamanhos em ml e a quantidade do kit.
    O número no fim de um título cortado (40 caracteres) pode estar pela metade: vira prefixo ('12' de '125')."""
    n = _norm(t).strip()
    n2 = re.sub(r"\d{2,4}\s*ml\b|\d{2,4}\s*m$|\bkit\s*(?:com|c/)?\s*\d+|\b\d+\s*(?:perfumes|unidades|frascos)\b", " ", n)
    achados = re.findall(r"\d+", n2)
    cortado = len(t or "") >= 39 and re.search(r"\d+$", n2.strip()) is not None
    return set(achados), (achados[-1] if cortado and achados else None)


def _numeros_batem(a, b):
    (na, pa), (nb, pb) = numeros(a), numeros(b)
    if not na or not nb:
        return True
    if na & nb:
        return True
    parcial = lambda p, outros: p is not None and any(x.startswith(p) for x in outros)
    return parcial(pa, nb) or parcial(pb, na)


def concentracoes(t):
    n = _norm(t)
    return {nome for nome, rx in CONCENTRACOES if re.search(rx, n)}


def genero(t):
    n = _norm(t)
    m = bool(re.search(r"\bmasc|\bmen\b|\bhomme\b|\bpour homme\b|\bhombre\b", n))
    f = bool(re.search(r"\bfem|\bwomen\b|\bfemme\b|\bpour femme\b|\bmujer\b", n))
    return "m" if m and not f else "f" if f and not m else ""


# palavras de anúncio que não mudam o produto (o resto do título é o nome do perfume)
COMUNS = set("""perfume perfumes eau de du des parfum toilette cologne colonia edp edt edc ml original originais lacrado
importado importada masculino masculina feminino feminina unissex unisex arabe arabes spray vaporizador fragrancia
fragrance deo pour homme femme for men women man woman com para the and selo adipec nota fiscal pronta entrega envio
imediato lancamento amadeirado amadeirada citrico citrica frutado frutada floral florais oriental doce fresco fresca
aromatico aromatica especiado especiada ambarado ambarada presente novo nova kit caixa tester contratipo inspirado
100ml 200ml 50ml 30ml 80ml 90ml 60ml 75ml 125ml 150ml sensual marcante classico classica fixacao duradouro longa
alta size tamanho grande""".split())


MARCAS_PALAVRAS = set()   # palavras dos nomes de marca vistas nos dados (um título pode citar a marca-mãe)


def palavras_nome(t, marca=""):
    """As palavras que dão nome ao perfume (sem marcas, tamanhos e palavras de anúncio)."""
    fora = COMUNS | MARCAS_PALAVRAS | set(_norm(marca).split())
    return {w for w in re.findall(r"[a-z]{3,}", _norm(t)) if w not in fora}


def compativeis(a, b):
    """Regras que a IA não pode passar por cima."""
    va, vb = volumes(a["titulo"]), volumes(b["titulo"])
    if va and vb and not (va & vb):
        return False
    if quantidade(a["titulo"]) != quantidade(b["titulo"]):
        return False                               # kit x unidade, kit de 3 x kit de 5
    if not _numeros_batem(a["titulo"], b["titulo"]):
        return False
    ca, cb = concentracoes(a["titulo"]), concentracoes(b["titulo"])
    if ca and cb and ca != cb:
        return False
    ga, gb = genero(a["titulo"]), genero(b["titulo"])
    if ga and gb and ga != gb:
        return False
    # o nome tem de ser o mesmo: "Good Girl" x "Good Girl Blush" e "Asad" x "Asad Bourbon" são perfumes diferentes
    na, nb = palavras_nome(a["titulo"], a.get("marca")), palavras_nome(b["titulo"], b.get("marca"))
    return bool(na) and na == nb


def texto_embedding(it):
    return f"{it.get('marca') or ''} | {it.get('titulo') or ''}"[:300]


def agrupar(itens, vetores, bloqueados=(), limiar=LIMIAR):
    """
    Junta os títulos sem GTIN ao produto (GTIN) mais parecido da mesma marca; os que não acharem GTIN se juntam
    entre si (o de maior venda dá o nome ao grupo). bloqueados: chaves que a pessoa separou à mão (ficam sozinhas).
    """
    if not itens:
        return {}
    MARCAS_PALAVRAS.clear()
    MARCAS_PALAVRAS.update(w for it in itens for w in re.findall(r"[a-z]{3,}", _norm(it.get("marca"))))
    V = np.asarray(vetores, dtype=np.float32)
    V /= np.linalg.norm(V, axis=1, keepdims=True) + 1e-9
    por_marca = {}
    for i, it in enumerate(itens):
        por_marca.setdefault((it.get("marca") or "").strip().upper(), []).append(i)
    saida = {}
    for marca, idx in por_marca.items():
        if not marca or len(idx) < 2:
            continue
        S = V[idx] @ V[idx].T
        sem = [j for j, i in enumerate(idx) if itens[i]["chave"].startswith("T:") and itens[i]["chave"] not in bloqueados]
        ancoras = [j for j, i in enumerate(idx) if not itens[i]["chave"].startswith("T:")]
        pai = {j: j for j in sem}

        def raiz(j):
            while pai[j] != j:
                pai[j] = pai[pai[j]]
                j = pai[j]
            return j
        melhor_ancora = {}
        for j in sem:
            cand = sorted(((S[j, a], a) for a in ancoras if S[j, a] >= limiar
                           and compativeis(itens[idx[j]], itens[idx[a]])), reverse=True)
            if cand:
                melhor_ancora[j] = cand[0]
        livres = [j for j in sem if j not in melhor_ancora]
        for x in range(len(livres)):
            for y in range(x + 1, len(livres)):
                a, b = livres[x], livres[y]
                if S[a, b] >= limiar + 0.02 and compativeis(itens[idx[a]], itens[idx[b]]):
                    pai[raiz(a)] = raiz(b)
        for j, (sim, a) in melhor_ancora.items():
            saida[itens[idx[j]]["chave"]] = (itens[idx[a]]["chave"], float(sim))
        grupos = {}
        for j in livres:
            grupos.setdefault(raiz(j), []).append(j)
        for membros in grupos.values():
            if len(membros) < 2:
                continue
            lider = max(membros, key=lambda j: itens[idx[j]].get("v") or 0)
            for j in membros:
                if j != lider:
                    saida[itens[idx[j]]["chave"]] = (itens[idx[lider]]["chave"], float(S[j, lider]))
    return saida
