# -*- coding: utf-8 -*-
"""
Estoque das lojas do dono (UpSeller): lê o export "Lista de Estoque", compara com a atualização anterior e
monta a análise (o que entrou, o que saiu, o que zerou, o que voltou, SKUs novos e removidos).

A comparação é feita aqui, em código (números exatos); o agente de estoque só escreve a leitura curta em cima
desses números, e nunca inventa um número que não esteja na comparação.
"""

import io
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


# agente de estoque: primeiro o grátis (gpt-oss na cota do Ollama), depois os baratos
ORDEM_IA = (("ollama", None, "Estoquista (gpt-oss)"), ("deepseek", None, "Estoquista (DeepSeek)"),
            ("claude", None, "Estoquista (Claude)"))


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
