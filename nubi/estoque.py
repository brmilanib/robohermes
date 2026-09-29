# -*- coding: utf-8 -*-
"""
Estoque das lojas do dono (UpSeller): lê o export "Lista de Estoque", compara com a atualização anterior e
monta a análise (o que entrou, o que saiu, o que zerou, o que voltou, SKUs novos e removidos).

A comparação é feita aqui, em código (números exatos); o agente de estoque só escreve a leitura curta em cima
desses números, e nunca inventa um número que não esteja na comparação.
"""

import io
import json
import re
import unicodedata

import ia

# coluna do export -> campo gravado em estoque_itens
COLUNAS = {
    "SKU": "sku", "Título": "titulo", "Armazém": "armazem", "Estante": "estante", "Estoque Baixo": "estoque_min",
    "Em Trânsito(Compra)": "transito_compra", "Em Trânsito(Transferência)": "transito_transf", "Ocupado": "ocupado",
    "Disponível": "disponivel", "Estoque Atual": "atual", "Custo Médio": "custo_medio", "Subtotal": "subtotal",
    "Criado": "criado",
}
NUMEROS = ("estoque_min", "transito_compra", "transito_transf", "ocupado", "disponivel", "atual", "custo_medio", "subtotal")
OBRIGATORIAS = ("sku", "disponivel", "atual")


class ErroEstoque(Exception):
    pass


def _cab(txt):
    """Cabeçalho normalizado (o UpSeller mistura parênteses chineses e espaços)."""
    t = unicodedata.normalize("NFC", str(txt or "")).replace("（", "(").replace("）", ")")
    return re.sub(r"\s*\(\s*", "(", re.sub(r"\s+", " ", t)).strip().lower()


def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("R$", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def ler_planilha(conteudo):
    """Bytes do .xlsx da Lista de Estoque -> lista de itens (um por SKU)."""
    import openpyxl
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")                  # o arquivo do UpSeller vem sem estilo padrão
        try:
            wb = openpyxl.load_workbook(io.BytesIO(conteudo), data_only=True)   # read_only corta as linhas: o arquivo do UpSeller vem sem "dimension"
        except Exception as e:  # noqa: BLE001
            raise ErroEstoque(f"não é uma planilha .xlsx válida ({e.__class__.__name__})")
    ws = wb.worksheets[0]
    linhas = ws.iter_rows(values_only=True)
    try:
        cab = [_cab(c) for c in next(linhas)]
    except StopIteration:
        raise ErroEstoque("planilha vazia")
    colunas = {_cab(k): v for k, v in COLUNAS.items()}
    mapa = {i: colunas[c] for i, c in enumerate(cab) if c in colunas}
    faltam = [c for c in OBRIGATORIAS if c not in mapa.values()]
    if faltam:
        raise ErroEstoque("não parece a Lista de Estoque do UpSeller (faltam as colunas "
                          + ", ".join(k for k, v in COLUNAS.items() if v in faltam) + ")")
    itens, vistos = [], set()
    for row in linhas:
        it = {campo: row[i] if i < len(row) else None for i, campo in mapa.items()}
        sku = str(it.get("sku") or "").strip()
        if not sku:
            continue
        if sku in vistos:
            raise ErroEstoque(f"SKU repetido na planilha: {sku}")
        vistos.add(sku)
        it["sku"] = sku
        for c in NUMEROS:
            if c in it:
                it[c] = _num(it[c])
        for c in ("titulo", "armazem", "estante", "criado"):
            if c in it:
                it[c] = None if it[c] is None else str(it[c]).strip()[:500]
        itens.append(it)
    wb.close()
    if not itens:
        raise ErroEstoque("nenhum SKU na planilha")
    return itens


def totais(itens):
    q = lambda it: it.get("atual") or 0  # noqa: E731
    return {
        "skus": len(itens),
        "unidades": round(sum(q(it) for it in itens), 2),
        "disponivel": round(sum(it.get("disponivel") or 0 for it in itens), 2),
        "valor": round(sum(it.get("subtotal") or 0 for it in itens), 2),
        "zerados": sum(1 for it in itens if q(it) <= 0),
        "baixo": sum(1 for it in itens if q(it) > 0 and it.get("estoque_min") and q(it) <= it["estoque_min"]),
        "sem_custo": sum(1 for it in itens if q(it) > 0 and not it.get("custo_medio")),
        "transito": round(sum(it.get("transito_compra") or 0 for it in itens), 2),   # compras já feitas, chegando
        "chegando": sum(1 for it in itens if (it.get("transito_compra") or 0) > 0),
    }


def comparar(anterior, atual, limite=60):
    """
    Diferença entre duas fotos do estoque (listas de itens). Quantidade = Estoque Atual.
    entradas/saídas: SKUs cuja quantidade subiu/desceu; zeraram: tinham e agora 0; voltaram: estavam em 0 e agora têm.
    """
    a = {it["sku"]: it for it in anterior or []}
    b = {it["sku"]: it for it in atual}
    q = lambda it: (it or {}).get("atual") or 0  # noqa: E731
    lin = lambda sku, ant, nov: {"sku": sku, "titulo": ((b.get(sku) or a.get(sku)) or {}).get("titulo") or "",  # noqa: E731
                                 "antes": ant, "agora": nov, "dif": round(nov - ant, 2)}
    entradas, saidas, zeraram, voltaram = [], [], [], []
    for sku, it in b.items():
        if sku not in a:
            continue
        x, y = q(a[sku]), q(it)
        if y > x:
            entradas.append(lin(sku, x, y))
        elif y < x:
            saidas.append(lin(sku, x, y))
        if x > 0 and y <= 0:
            zeraram.append(lin(sku, x, y))
        elif x <= 0 and y > 0:
            voltaram.append(lin(sku, x, y))
    novos = [lin(s, 0, q(it)) for s, it in b.items() if s not in a]
    removidos = [lin(s, q(it), 0) for s, it in a.items() if s not in b]
    entradas.sort(key=lambda x: -x["dif"])
    saidas.sort(key=lambda x: x["dif"])
    zeraram.sort(key=lambda x: -x["antes"])
    ta, tb = totais(anterior or []), totais(atual)
    return {
        "tem_anterior": bool(anterior),
        "totais": tb, "totais_antes": ta if anterior else None,
        "n": {"entradas": len(entradas), "saidas": len(saidas), "zeraram": len(zeraram), "voltaram": len(voltaram),
              "novos": len(novos), "removidos": len(removidos)},
        "unidades_entraram": round(sum(x["dif"] for x in entradas), 2),
        "unidades_sairam": round(-sum(x["dif"] for x in saidas), 2),
        "entradas": entradas[:limite], "saidas": saidas[:limite], "zeraram": zeraram[:limite],
        "voltaram": voltaram[:limite], "novos": novos[:limite], "removidos": removidos[:limite],
    }


def _br(v, casas=0):
    s = f"{v:,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def resumo_texto(d):
    """Linhas curtas e exatas (sem IA): o log de cada atualização."""
    t, n = d["totais"], d["n"]
    out = [f"{_br(t['skus'])} SKUs · {_br(t['unidades'])} unidades · R$ {_br(t['valor'], 2)} em estoque "
           f"· {_br(t['zerados'])} zerados"]
    if t["transito"]:
        out.append(f"Em trânsito (compra): {_br(t['transito'])} un. em {t['chegando']} SKU(s) já comprados e chegando.")
    if not d["tem_anterior"]:
        out.append("Primeira foto do estoque: a comparação (o que entrou, saiu e zerou) começa na próxima atualização.")
        return out
    ta = d["totais_antes"]
    out.append(f"Desde a atualização anterior: +{_br(d['unidades_entraram'])} un. em {n['entradas']} SKU(s), "
               f"−{_br(d['unidades_sairam'])} un. em {n['saidas']} SKU(s); saldo "
               f"{'+' if t['unidades'] >= ta['unidades'] else '−'}{_br(abs(t['unidades'] - ta['unidades']))} un.")
    if n["zeraram"] or n["voltaram"]:
        out.append(f"{n['zeraram']} SKU(s) zeraram e {n['voltaram']} voltaram a ter estoque.")
    if n["novos"] or n["removidos"]:
        out.append(f"{n['novos']} SKU(s) novo(s) e {n['removidos']} removido(s) do UpSeller.")
    return out


PAPEL = ("Você é o Estoquista, agente do nubi que acompanha o estoque das lojas do dono (export do UpSeller, "
         "armazém My Warehouse). Recebe a comparação EXATA entre a atualização anterior e a atual, já calculada em "
         "código. Escreva uma análise curta em português do Brasil, em até 8 tópicos com '- ': o que mais saiu (provável "
         "venda), o que entrou (compra/reposição), o que zerou e precisa de reposição (priorize os que tinham mais "
         "unidades), SKUs novos/removidos, estoque baixo e itens sem custo médio (prejudica o valor do estoque). "
         "Use SOMENTE os números da comparação; se algo não dá para saber, diga o que conferir. Sem introdução e sem "
         "pergunta no final.")


def _lista(xs, n=15):
    return "\n".join(f"  {x['sku']} | {x['titulo'][:70]} | {_br(x['antes'])} -> {_br(x['agora'])}" for x in xs[:n]) or "  (nenhum)"


def pedido_ia(d, baixos):
    t, n = d["totais"], d["n"]
    partes = ["RESUMO: " + " ".join(resumo_texto(d)),
              f"Estoque baixo (≤ mínimo): {t['baixo']} SKU(s); com estoque e sem custo médio: {t['sem_custo']}."]
    if d["tem_anterior"]:
        partes += [f"SAÍRAM ({n['saidas']}):\n{_lista(d['saidas'])}", f"ENTRARAM ({n['entradas']}):\n{_lista(d['entradas'])}",
                   f"ZERARAM ({n['zeraram']}):\n{_lista(d['zeraram'])}", f"VOLTARAM ({n['voltaram']}):\n{_lista(d['voltaram'])}",
                   f"NOVOS ({n['novos']}):\n{_lista(d['novos'])}", f"REMOVIDOS ({n['removidos']}):\n{_lista(d['removidos'])}"]
    if baixos:
        partes.append("ABAIXO DO MÍNIMO:\n" + "\n".join(f"  {b['sku']} | {(b.get('titulo') or '')[:70]} | "
                                                          f"{_br(b.get('atual') or 0)} (mín. {_br(b.get('estoque_min') or 0)})"
                                                          for b in baixos[:15]))
    return "\n\n".join(partes)


# agente de estoque na importação: SÓ o grátis (gpt-oss). 28/09 (Bruno): IA paga no estoque só na análise diária do DeepSeek
ORDEM_IA = (("ollama", None, "Estoquista (gpt-oss)"),)


def analisar_ia(d, itens, sistema=""):
    """(texto, quem) — análise curta do agente; ('', motivo) se nenhuma IA respondeu."""
    baixos = sorted([it for it in itens if (it.get("atual") or 0) > 0 and it.get("estoque_min")
                     and (it.get("atual") or 0) <= it["estoque_min"]], key=lambda it: (it.get("atual") or 0))
    pedido = PAPEL + "\n\n" + pedido_ia(d, baixos)
    ultimo = "nenhuma IA configurada"
    for qual, modelo, quem in ORDEM_IA:
        if not ia.tem(qual):
            continue
        try:
            t, _, _ = ia.perguntar(pedido, web=False, max_tokens=1500, qual=qual, modelo=modelo, sistema=sistema or None)
            if t and t.strip():
                return t.strip(), quem
        except Exception as e:  # noqa: BLE001
            ultimo = f"{quem}: {str(e)[:120]}"
    return "", ultimo


# ---------------------------------------------------------------------------
# Vendas por anúncio do UpSeller (28/09, pedido do Bruno): Análises → Vendas por Anúncio, últimos 30 dias, 1 vez por dia.
# Arquivo "Vendas_por_Produtos_AAAAMMDD-AAAAMMDD_….xlsx": Produtos, Loja, SKU Principal, ID do Anúncios, Pedidos Válidos,
# Unidades Vendidas, Valor de Vendas, Preço Médio (uma linha por anúncio; o mesmo SKU pode ter vários anúncios/lojas).
# ---------------------------------------------------------------------------
VENDAS_COLUNAS = {"Produtos": "produto", "Loja": "loja", "SKU Principal": "sku", "ID do Anúncios": "anuncio",
                  "ID do Anúncio": "anuncio", "Pedidos Válidos": "pedidos", "Unidades Vendidas": "unidades",
                  "Valor de Vendas": "valor", "Preço Médio": "preco_medio"}
VENDAS_NUMEROS = ("pedidos", "unidades", "valor", "preco_medio")
ALERTA_DIAS = 15        # estoque (disponível + em trânsito) que dura menos que isso = preciso comprar
ALVO_DIAS = 30          # a sugestão de compra cobre 30 dias de venda


def ler_vendas(conteudo):
    """Bytes do .xlsx "Vendas por Produtos" do UpSeller -> lista de linhas (uma por anúncio)."""
    import openpyxl
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            wb = openpyxl.load_workbook(io.BytesIO(conteudo), data_only=True)
        except Exception as e:  # noqa: BLE001
            raise ErroEstoque(f"não é uma planilha .xlsx válida ({e.__class__.__name__})")
    linhas = wb.worksheets[0].iter_rows(values_only=True)
    try:
        cab = [_cab(c) for c in next(linhas)]
    except StopIteration:
        raise ErroEstoque("planilha vazia")
    colunas = {_cab(k): v for k, v in VENDAS_COLUNAS.items()}
    mapa = {i: colunas[c] for i, c in enumerate(cab) if c in colunas}
    if not {"sku", "unidades"} <= set(mapa.values()):
        raise ErroEstoque("não parece o relatório 'Vendas por Anúncio' do UpSeller (faltam SKU Principal e Unidades Vendidas)")
    out = []
    for row in linhas:
        it = {campo: row[i] if i < len(row) else None for i, campo in mapa.items()}
        sku = str(it.get("sku") or "").strip()
        if not sku:
            continue
        it["sku"] = sku
        for c in VENDAS_NUMEROS:
            it[c] = _num(it.get(c)) or 0.0
        for c in ("produto", "loja", "anuncio"):
            it[c] = str(it.get(c) or "").strip()[:300]
        out.append(it)
    wb.close()
    if not out:
        raise ErroEstoque("nenhuma venda na planilha")
    return out


def periodo_vendas(nome):
    """'Vendas_por_Produtos_20260829-20260927_…' -> ('2026-08-29', '2026-09-27', 30 dias) ou (None, None, 30)."""
    m = re.search(r"(20\d{6})\s*-\s*(20\d{6})", str(nome or ""))
    if not m:
        return None, None, 30
    from datetime import date
    a, b = (date(int(x[:4]), int(x[4:6]), int(x[6:])) for x in m.groups())
    return a.isoformat(), b.isoformat(), max(1, (b - a).days + 1)


def _chave(sku):
    return str(sku or "").strip().upper()


def listas(itens, vendas, dias=30, alerta=ALERTA_DIAS, alvo=ALVO_DIAS):
    """Zerados, mais vendidos e preciso comprar, calculados em código (números exatos; a IA só interpreta).
    Venda por dia = unidades vendidas no período / dias. Cobertura = (disponível + em trânsito da compra) / venda por dia."""
    import math
    por = {}
    for v in vendas or []:
        k = _chave(v["sku"])
        x = por.setdefault(k, {"sku": v["sku"], "produto": v.get("produto") or "", "unidades": 0.0, "pedidos": 0.0,
                               "valor": 0.0, "anuncios": 0, "lojas": set()})
        x["unidades"] += v.get("unidades") or 0
        x["pedidos"] += v.get("pedidos") or 0
        x["valor"] += v.get("valor") or 0
        x["anuncios"] += 1
        if v.get("loja"):
            x["lojas"].add(re.sub(r"\s*\[.*$", "", v["loja"]).strip().upper())
    est = {_chave(it["sku"]): it for it in itens or []}

    def linha(k):
        it, x = est.get(k) or {}, por.get(k) or {}
        vd = (x.get("unidades") or 0) / dias
        disp, trans = it.get("disponivel") or 0, it.get("transito_compra") or 0
        cob = round((disp + trans) / vd, 1) if vd else None
        return {"sku": it.get("sku") or x.get("sku") or k, "titulo": it.get("titulo") or x.get("produto") or "",
                "disponivel": disp, "atual": it.get("atual") or 0, "transito": trans, "minimo": it.get("estoque_min") or 0,
                "custo": it.get("custo_medio"), "vendidos": round(x.get("unidades") or 0), "pedidos": round(x.get("pedidos") or 0),
                "valor": round(x.get("valor") or 0, 2), "venda_dia": round(vd, 2), "cobertura_dias": cob,
                "lojas": sorted(x.get("lojas") or []), "no_estoque": bool(it)}
    zerados = sorted((linha(k) for k, it in est.items() if not ((it.get("atual") or 0) > 0)),
                     key=lambda r: (-r["vendidos"], r["sku"]))
    vendidos = sorted((linha(k) for k in por if por[k]["unidades"] > 0), key=lambda r: (-r["vendidos"], -r["valor"]))
    comprar = []
    for k in set(por) | set(est):
        r = linha(k)
        abaixo_min = r["minimo"] > 0 and r["disponivel"] + r["transito"] <= r["minimo"] and r["vendidos"] > 0
        if r["venda_dia"] and (r["cobertura_dias"] is not None and r["cobertura_dias"] < alerta or abaixo_min):
            r["sugerido"] = max(0, math.ceil(r["venda_dia"] * alvo - r["disponivel"] - r["transito"]))
            r["motivo"] = (f"dura {r['cobertura_dias']:g} dia(s)" if r["cobertura_dias"] is not None and r["cobertura_dias"] < alerta
                           else "abaixo do mínimo do UpSeller")
            if r["sugerido"] > 0:
                comprar.append(r)
    comprar.sort(key=lambda r: (r["cobertura_dias"] if r["cobertura_dias"] is not None else 9e9, -r["vendidos"]))
    return {"dias": dias, "alerta_dias": alerta, "alvo_dias": alvo, "zerados": zerados, "mais_vendidos": vendidos,
            "comprar": comprar, "zerados_com_venda": sum(1 for r in zerados if r["vendidos"] > 0),
            "vendas_sem_estoque": sum(1 for r in vendidos if not r["no_estoque"])}


PAPEL_ANALISE = ("Você é o DeepSeek, analista de estoque do nubi. Abaixo, as listas do estoque do Bruno (UpSeller) cruzadas com "
                 "as vendas por anúncio dos últimos {dias} dias, já calculadas pelo sistema: NÃO recalcule e NÃO invente nenhum "
                 "número. Escreva em português do Brasil, direto, em markdown curto, com estas seções:\n"
                 "## Comprar já\nos 5 a 8 mais urgentes (acabam primeiro e vendem bem), com a quantidade sugerida e o porquê.\n"
                 "## Zerados que vendem\no que está parado vendendo zero por falta de estoque.\n"
                 "## Campeões\nos que mais vendem e como está o estoque deles.\n"
                 "## Atenção\n1 ou 2 riscos (estoque encalhado, SKU vendido que não está no estoque, custo faltando).")


def pedido_analise(ls):
    return PAPEL_ANALISE.replace("{dias}", str(ls["dias"])) + "\n\n" + tabelas(ls)


def tabelas(ls):
    """As listas do estoque × vendas em texto, para a IA (sem o papel)."""
    def tab(xs, n, extra=lambda r: ""):
        return "\n".join(f"  {r['sku']} | {r['titulo'][:60]} | vendeu {r['vendidos']} | disp. {r['disponivel']:g} | trânsito "
                         f"{r['transito']:g} | dura {r['cobertura_dias'] if r['cobertura_dias'] is not None else '—'} dias{extra(r)}"
                         for r in xs[:n]) or "  (nenhum)"
    return (f"PRECISO COMPRAR (dura menos de {ls['alerta_dias']} dias; sugestão cobre {ls['alvo_dias']} dias):\n"
            + tab(ls["comprar"], 25, lambda r: f" | sugerido {r['sugerido']} | {r['motivo']}")
            + f"\n\nZERADOS COM VENDA NO PERÍODO ({ls['zerados_com_venda']}):\n" + tab([r for r in ls["zerados"] if r["vendidos"]], 20)
            + "\n\nMAIS VENDIDOS:\n" + tab(ls["mais_vendidos"], 20)
            + f"\n\nSKUs vendidos que não estão no estoque do UpSeller: {ls['vendas_sem_estoque']}.")


# ---------------------------------------------------------------------------
# Reposição semanal e lista de compra (29/09, pedido do Bruno: "o DeepSeek analisa minhas vendas e acha o melhor equilíbrio
# de reposição semanal; lista de compra com nome, quantidade e último preço pago de custo"). Os números saem daqui (código);
# o DeepSeek só ajusta a quantidade de cada SKU e explica.
# ---------------------------------------------------------------------------
REPOR_SEMANA = 7          # o pedido é semanal: compra para cobrir a semana…
SEGURANCA_DIAS = 7        # …mais uma semana de folga (atraso do fornecedor, pico de venda)


def ultimo_custo_pago(fotos):
    """Último preço pago por SKU, tirado do histórico do estoque (o UpSeller só dá o custo MÉDIO). fotos = lista em ordem de
    data de {chave_sku: {"atual", "custo_medio", "quando"}}. Numa entrada (o atual subiu e o custo médio mudou):
    preço = (custo novo × qtd nova − custo velho × qtd velha) ÷ quantidade que entrou. Vinha zerado: preço = custo novo.
    Devolve {chave: {"preco", "quando"}} com a entrada mais recente de cada SKU."""
    out = {}
    for a, b in zip(fotos, fotos[1:]):
        for k, y in b.items():
            x = a.get(k)
            if not x:
                continue
            qa, qb = float(x.get("atual") or 0), float(y.get("atual") or 0)
            ca, cb = float(x.get("custo_medio") or 0), float(y.get("custo_medio") or 0)
            if qb <= qa or cb <= 0:
                continue
            if qa <= 0:
                preco = cb
            elif ca > 0 and abs(cb - ca) > 0.005:
                preco = (cb * qb - ca * qa) / (qb - qa)
                if not (0.3 * min(ca, cb) <= preco <= 3 * max(ca, cb)):
                    continue                 # vendeu no meio e a conta não fecha: não chuta
            else:
                preco = cb                   # entrou pelo mesmo custo
            out[k] = {"preco": round(preco, 2), "quando": y.get("quando")}
    return out


def plano_semanal(ls, custos=None, semana=REPOR_SEMANA, seguranca=SEGURANCA_DIAS):
    """Quanto comprar AGORA para a semana: venda/dia × (semana + folga) − disponível − em trânsito, só de quem vende.
    Custo = último preço pago (histórico) ou o custo médio do UpSeller."""
    import math
    custos = custos or {}
    vistos, out = set(), []
    for r in (ls.get("comprar") or []) + (ls.get("mais_vendidos") or []):
        k = _chave(r["sku"])
        if k in vistos or not r.get("venda_dia"):
            continue
        vistos.add(k)
        qtd = math.ceil(r["venda_dia"] * (semana + seguranca) - (r.get("disponivel") or 0) - (r.get("transito") or 0))
        if qtd <= 0:
            continue
        c = custos.get(k)
        preco = c["preco"] if c else (float(r["custo"]) if r.get("custo") not in (None, "") and float(r["custo"]) > 0 else None)
        out.append({"sku": r["sku"], "produto": r.get("titulo") or "", "quantidade": qtd, "venda_semana": round(r["venda_dia"] * 7, 1),
                    "disponivel": r.get("disponivel") or 0, "transito": r.get("transito") or 0, "dura": r.get("cobertura_dias"),
                    "ultimo_custo": preco, "fonte_custo": ("última compra" + (f" {c['quando']}" if c.get("quando") else "")) if c
                    else ("custo médio" if preco else "sem custo"),
                    "subtotal": round(preco * qtd, 2) if preco else None, "motivo": ""})
    out.sort(key=lambda x: (x["dura"] if x["dura"] is not None else 9e9, -x["venda_semana"]))
    return out


PAPEL_PLANO = ("\n\n## Reposição da semana\nAbaixo, o PLANO BASE calculado pelo sistema (venda/dia × {dias} dias − disponível − "
               "trânsito). Ache o melhor equilíbrio: ajuste a quantidade de cada SKU quando fizer sentido (venda irregular, produto "
               "caro parado, campeão que não pode faltar) e explique em 1 frase curta. Use SÓ os SKUs do plano; não invente preço. "
               "Na ÚLTIMA linha da resposta, escreva exatamente:\nLISTA_JSON: [{\"sku\": \"…\", \"quantidade\": N, \"motivo\": \"…\"}, …]")


def pedido_plano(plano, n=60):
    return PAPEL_PLANO.replace("{dias}", str(REPOR_SEMANA + SEGURANCA_DIAS)) + "\n\nPLANO BASE:\n" + linhas_plano(plano, n)


def linhas_plano(plano, n=60):
    return "\n".join(f"  {x['sku']} | {x['produto'][:55]} | vende {x['venda_semana']:g}/semana | disp. {x['disponivel']:g} | trânsito "
                        f"{x['transito']:g} | base {x['quantidade']} un | custo {x['ultimo_custo'] if x['ultimo_custo'] else '—'}"
                        for x in plano[:n]) or "  (nada a repor)"


def lista_da_resposta(txt, plano):
    """Separa o texto da linha LISTA_JSON e monta a lista final: só SKUs do plano, quantidade inteira ≥ 0; nome, custo e
    subtotal SEMPRE do sistema (a IA só muda a quantidade e o motivo). Sem a linha (ou inválida): o plano base."""
    base = {_chave(x["sku"]): x for x in plano}
    m = re.search(r"LISTA_JSON:\s*(\[.*\])\s*$", txt or "", re.S)
    texto = (txt[:m.start()] if m else txt or "").strip()
    if not m:
        return texto, [dict(x) for x in plano], False
    try:
        itens = json.loads(m.group(1))
    except ValueError:
        return texto, [dict(x) for x in plano], False
    out = []
    for it in itens if isinstance(itens, list) else []:
        k = _chave(str((it or {}).get("sku") or ""))
        if k not in base:
            continue
        try:
            q = max(0, int(round(float(it.get("quantidade")))))
        except (TypeError, ValueError):
            continue
        x = dict(base[k], quantidade=q, motivo=str(it.get("motivo") or "")[:160])
        x["subtotal"] = round(x["ultimo_custo"] * q, 2) if x.get("ultimo_custo") else None
        if q > 0:
            out.append(x)
    return texto, out, True


# ---------------------------------------------------------------------------
# Planilha de importação do Gestor Seller (cadastro de produtos), feita a partir do estoque do UpSeller.
# Mesmo formato do modelo do Gestor: aba "Planilha1", 7 colunas, custo com 2 casas, SKU como texto.
# ---------------------------------------------------------------------------
GESTOR_COLUNAS = ["SKU Interno", "SKU externo (opcional)", "Link da Imagem (opcional)", "Título", "Preço de Custo",
                  "Custo Extra (opcional)", "EAN (opcional)"]


def linhas_gestor(itens):
    """Uma linha por SKU, na ordem do export do UpSeller: SKU interno = externo = SKU; custo = Custo Médio (2 casas)."""
    out = []
    for it in itens:
        custo = it.get("custo_medio")
        custo = round(float(custo), 2) if custo not in (None, "") and float(custo) > 0 else None
        if custo is not None and custo == int(custo):
            custo = int(custo)
        sku = str(it["sku"])
        out.append([sku, sku, None, it.get("titulo") or "", custo, None, None])
    return out


def gerar_gestor(itens):
    """Bytes do .xlsx pronto para importar no Gestor Seller."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Planilha1"
    ws.append(GESTOR_COLUNAS)
    for lin in linhas_gestor(itens):
        ws.append(lin)
    for c in ws["A"][1:] + ws["B"][1:]:
        c.number_format = "@"                          # SKU só de números (ex.: 1050009143) continua texto
    for c in ws["E"][1:]:
        c.number_format = "0.00"
    for col, larg in zip("ABCDEFG", (20.8, 20.8, 18, 40, 14, 14, 16)):
        ws.column_dimensions[col].width = larg
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
