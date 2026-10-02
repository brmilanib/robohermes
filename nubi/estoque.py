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


ABC_COLUNAS = {"Produtos": "produto", "Loja": "loja", "SKU Principal": "sku", "ID do Anúncios": "anuncio", "ID do Anúncio": "anuncio",
               "Classificação ABC": "classe", "Valor de Vendas Válidas": "valor", "Volume de vendas válido": "unidades",
               "Preço Médio": "preco_medio"}


def eh_abc(conteudo):
    """True se o .xlsx é a Análise ABC do UpSeller (coluna "Classificação ABC")."""
    import openpyxl
    import warnings
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            wb = openpyxl.load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
        cab = [_cab(c) for c in next(wb.worksheets[0].iter_rows(values_only=True))]
        wb.close()
        return _cab("Classificação ABC") in cab
    except Exception:  # noqa: BLE001
        return False


def ler_abc(conteudo):
    """01/10 (Bruno: "o próprio UpSeller gera o relatório da curva ABC"): Análise ABC → Exportar ("Product_Sales_…xlsx"):
    uma linha por anúncio com a classe A/B/C do UpSeller. -> [{anuncio, loja, sku, produto, classe, valor, unidades}]"""
    import openpyxl
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            wb = openpyxl.load_workbook(io.BytesIO(conteudo), data_only=True)
        except Exception as e:  # noqa: BLE001
            raise ErroEstoque(f"não é uma planilha .xlsx válida ({e.__class__.__name__})")
    linhas = wb.worksheets[0].iter_rows(values_only=True)
    cab = [_cab(c) for c in next(linhas)]
    colunas = {_cab(k): v for k, v in ABC_COLUNAS.items()}
    mapa = {i: colunas[c] for i, c in enumerate(cab) if c in colunas}
    if not {"classe", "anuncio"} <= set(mapa.values()):
        raise ErroEstoque("não parece a Análise ABC do UpSeller (falta Classificação ABC)")
    out = []
    for row in linhas:
        it = {campo: row[i] if i < len(row) else None for i, campo in mapa.items()}
        classe = str(it.get("classe") or "").strip().upper()[:1]
        if classe not in ("A", "B", "C"):
            continue
        out.append({"anuncio": str(it.get("anuncio") or "").strip(), "loja": str(it.get("loja") or "").strip(),
                    "sku": str(it.get("sku") or "").strip(), "produto": str(it.get("produto") or "").strip()[:300],
                    "classe": classe, "valor": _num(it.get("valor")) or 0.0, "unidades": _num(it.get("unidades")) or 0.0,
                    "preco_medio": _num(it.get("preco_medio"))})
    wb.close()
    if not out:
        raise ErroEstoque("nenhum anúncio com classe A/B/C na planilha")
    return out


def periodo_abc(nome):
    """'Product_Sales_20260901_20260930_…' -> ('2026-09-01', '2026-09-30') ou (None, None)."""
    m = re.search(r"(20\d{6})_(20\d{6})", str(nome or ""))
    if not m:
        return None, None
    return tuple(f"{x[:4]}-{x[4:6]}-{x[6:]}" for x in m.groups())


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
        # 01/10 (arquivo do Bruno: 49 de 320 anúncios sem SKU, R$ 34,7 mil): anúncio sem SKU Principal também é venda —
        # entra nos totais e na lista por anúncio (sem_sku), mas não nas listas por SKU (não liga ao estoque)
        if not sku and not str(it.get("anuncio") or "").strip():
            continue
        it["sku"] = sku
        it["sem_sku"] = not sku
        for c in VENDAS_NUMEROS:
            it[c] = _num(it.get(c)) or 0.0
        for c in ("produto", "loja", "anuncio"):
            it[c] = str(it.get(c) or "").strip()[:300]
        out.append(it)
    wb.close()
    if not out:
        raise ErroEstoque("nenhuma venda na planilha")
    return out


# ---------------------------------------------------------------------------
# Relatório de Vendas do Gestor Seller (card #124, 29/09): uma linha por pedido/SKU com faturamento, custo, imposto, taxas, frete e
# lucro. Os nomes das colunas variam: cada campo casa pela 1ª coluna cujo cabeçalho bate (frete/imposto/taxa antes de custo/valor).
# ---------------------------------------------------------------------------
GESTOR_VENDAS_CAMPOS = (("frete", r"frete|envio"), ("imposto", r"imposto|tribut|\bnf\b"), ("taxa", r"taxa|comiss|tarifa"),
                        ("margem", r"margem"), ("lucro", r"lucro|resultado"), ("custo", r"custo"),
                        ("valor", r"faturamento|valor|receita|total|pre[çc]o"), ("unidades", r"quantidade|qtd|unidades"),
                        ("sku", r"\bsku\b"), ("pedido", r"pedido|order"), ("conta", r"conta|marketplace|loja|canal"),
                        ("produto", r"produto|t[íi]tulo|an[úu]ncio|descri"))
GESTOR_VENDAS_NUMEROS = ("unidades", "valor", "custo", "imposto", "taxa", "frete", "lucro", "margem", "recebido")
# 01/10 (CSV "reports_sales" do Gestor mandado pelo Bruno): nomes exatos das colunas vencem as regras por palavra (antes o
# "Preço Unitário" virava o valor, o "SKU Externo" o SKU e o "Marketplace" a conta). Custo e imposto são do pedido inteiro.
GESTOR_VENDAS_EXATOS = {"id do pedido": "pedido", "marketplace": "marketplace", "status": "status", "data de compra": "data",
                        "nome da conta": "conta", "sku interno": "sku", "título": "produto", "quantidade": "unidades",
                        "preço total": "valor", "comissão": "taxa", "taxa de envio": "frete", "recebido do marketplace": "recebido",
                        "preço de custo": "custo", "imposto": "imposto", "lucro": "lucro", "margem(%)": "margem",
                        "estado do comprador": "estado", "logística": "logistica"}


def _linhas_planilha(conteudo):
    """Linhas de um .xlsx (ou .csv) como listas de valores."""
    if conteudo[:2] != b"PK":
        import csv
        txt = conteudo.decode("utf-8-sig", errors="replace")
        return list(csv.reader(io.StringIO(txt), delimiter=";" if txt[:2000].count(";") > txt[:2000].count(",") else ","))
    import openpyxl
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            wb = openpyxl.load_workbook(io.BytesIO(conteudo), data_only=True, read_only=True)
        except Exception as e:  # noqa: BLE001
            raise ErroEstoque(f"não é uma planilha .xlsx válida ({e.__class__.__name__})")
    out = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    wb.close()
    return out


def ler_gestor_vendas(conteudo):
    """Bytes do 'Relatório de Vendas' do Gestor Seller -> lista de linhas (pedido/SKU) com os números do Gestor."""
    rows = _linhas_planilha(conteudo)
    for n, row in enumerate(rows[:15]):                    # o cabeçalho pode vir depois de um título/período
        cab = [_cab(c) for c in row]
        mapa = {i: GESTOR_VENDAS_EXATOS[c] for i, c in enumerate(cab) if c in GESTOR_VENDAS_EXATOS}
        if len(mapa) < 6:
            mapa = {}
        for i, c in enumerate(cab):
            if i in mapa:
                continue
            campo = next((campo for campo, rx in GESTOR_VENDAS_CAMPOS if c and re.search(rx, c)), None)
            if campo and campo not in mapa.values():
                mapa[i] = campo
        if "sku" in mapa.values() and {"lucro", "margem"} & set(mapa.values()):
            break
    else:
        raise ErroEstoque("não parece o Relatório de Vendas do Gestor Seller (faltam as colunas SKU e Lucro/Margem)")
    out = []
    for row in rows[n + 1:]:
        it = {campo: row[i] if i < len(row) else None for i, campo in mapa.items()}
        sku = str(it.get("sku") or "").strip()
        if not sku or re.match(r"(?i)^total", sku):
            continue
        it["sku"] = sku
        for c in GESTOR_VENDAS_NUMEROS:
            if c in it:
                it[c] = _num(str(it[c]).replace("%", "")) if isinstance(it[c], str) else _num(it[c])
        for c in ("pedido", "conta", "produto", "marketplace", "status", "estado", "logistica"):
            if c in it or c in ("pedido", "conta", "produto"):
                it[c] = str(it.get(c) or "").strip()[:300]
        if it.get("data") not in (None, ""):
            d = it["data"]
            it["data"] = d.strftime("%Y-%m-%d %H:%M:%S") if hasattr(d, "strftime") else str(d).strip()[:19]
        out.append(it)
    if not out:
        raise ErroEstoque("nenhuma venda na planilha")
    return out


GESTOR_ABC_EXATOS = {"sku interno": "sku", "título": "produto", "curva": "curva", "unidades vendidas": "unidades",
                     "faturamento total": "valor", "lucro bruto": "lucro_bruto", "lucro pós ads": "lucro_pos_ads"}


def eh_abc_gestor(conteudo):
    """True se é a Curva ABC do Gestor Seller (colunas Curva e Lucro Pós Ads)."""
    try:
        cab = [_cab(c) for c in (_linhas_planilha(conteudo)[:1] or [[]])[0]]
    except Exception:  # noqa: BLE001
        return False
    return "curva" in cab and "lucro pós ads" in cab


def ler_abc_gestor(conteudo):
    """01/10 (Bruno: "o Gestor traz o custo de ADS e a margem de lucro líquido de cada produto"): Curva ABC do Gestor (1ª aba,
    "Todas"). Por SKU: curva A/B/C/Z (Z = sem venda no período, só gasto), unidades, faturamento, lucro bruto, lucro pós ADS.
    ADS = lucro bruto − lucro pós ADS; MPA = lucro pós ADS ÷ faturamento (conferido: Ferrari 13.989,78 ÷ 86.427,04 = 16,19%).
    A coluna "Margem (%)" do arquivo vem dividida por 100 duas vezes: não é usada."""
    rows = _linhas_planilha(conteudo)
    cab = [_cab(c) for c in rows[0]]
    mapa = {i: GESTOR_ABC_EXATOS[c] for i, c in enumerate(cab) if c in GESTOR_ABC_EXATOS}
    if not {"sku", "curva", "lucro_pos_ads"} <= set(mapa.values()):
        raise ErroEstoque("não parece a Curva ABC do Gestor Seller (faltam SKU Interno, Curva e Lucro Pós Ads)")
    out = []
    for row in rows[1:]:
        it = {campo: row[i] if i < len(row) else None for i, campo in mapa.items()}
        sku = str(it.get("sku") or "").strip()
        curva = str(it.get("curva") or "").strip().upper()[:1]
        if not sku or curva not in ("A", "B", "C", "Z"):
            continue
        n = {c: _num(it.get(c)) for c in ("unidades", "valor", "lucro_bruto", "lucro_pos_ads")}
        bruto, pos, val = n["lucro_bruto"] or 0.0, n["lucro_pos_ads"] or 0.0, n["valor"] or 0.0
        out.append({"sku": sku, "produto": str(it.get("produto") or "").strip()[:300], "curva": curva,
                    "unidades": n["unidades"] or 0.0, "valor": round(val, 2), "lucro_bruto": round(bruto, 2),
                    "lucro_pos_ads": round(pos, 2), "ads": round(bruto - pos, 2),
                    "margem_pct": round(bruto / val * 100, 2) if val else None,
                    "mpa_pct": round(pos / val * 100, 2) if val else None,
                    "ads_pct": round((bruto - pos) / val * 100, 2) if val else None})
    if not out:
        raise ErroEstoque("nenhum produto com curva na planilha")
    return out


def resumo_abc_gestor(linhas):
    """Totais por curva (como os 4 quadros da tela do Gestor)."""
    out = []
    for k in ("A", "B", "C", "Z"):
        xs = [x for x in linhas if x["curva"] == k]
        val = sum(x["valor"] for x in xs)
        bruto = sum(x["lucro_bruto"] for x in xs)
        pos = sum(x["lucro_pos_ads"] for x in xs)
        out.append({"curva": k, "produtos": len(xs), "unidades": round(sum(x["unidades"] for x in xs)), "valor": round(val, 2),
                    "lucro_bruto": round(bruto, 2), "lucro_pos_ads": round(pos, 2), "ads": round(bruto - pos, 2),
                    "margem_pct": round(bruto / val * 100, 2) if val else None, "mpa_pct": round(pos / val * 100, 2) if val else None})
    return out


def gestor_por_sku(linhas):
    """Soma do Gestor por SKU (sem maiúsculas): unidades, faturamento e lucro -> margem real % (depois de taxas e frete)."""
    por = {}
    for x in linhas or []:
        s = por.setdefault(_chave(x["sku"]), {"unidades": 0.0, "valor": 0.0, "lucro": 0.0, "com_lucro": False, "margens": []})
        s["unidades"] += x.get("unidades") or 0
        s["valor"] += x.get("valor") or 0
        if x.get("lucro") is not None:
            s["lucro"] += x["lucro"]
            s["com_lucro"] = True
        elif x.get("margem") is not None:
            s["margens"].append(x["margem"])
    out = {}
    for k, s in por.items():
        if s["com_lucro"] and s["valor"]:
            pct = s["lucro"] / s["valor"] * 100
        elif s["margens"]:
            pct = sum(s["margens"]) / len(s["margens"])
            pct = pct * 100 if abs(pct) <= 1 else pct      # 0,23 (célula em %) ou 23
        else:
            continue
        out[k] = {"margem_pct": round(pct, 1), "lucro_un": round(s["lucro"] / s["unidades"], 2) if s["com_lucro"] and s["unidades"] else None}
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


def listas(itens, vendas, dias=30, alerta=ALERTA_DIAS, alvo=ALVO_DIAS, gestor=None):
    """Zerados, mais vendidos e preciso comprar, calculados em código (números exatos; a IA só interpreta).
    Venda por dia = unidades vendidas no período / dias. Cobertura = (disponível + em trânsito da compra) / venda por dia."""
    import math
    por = {}
    todas, vendas = vendas, [v for v in vendas or [] if v.get("sku")]      # sem SKU: só na lista por anúncio
    for v in vendas:
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
    anuncios = por_anuncio(itens, todas, dias, gestor)
    return {"dias": dias, "alerta_dias": alerta, "alvo_dias": alvo, "zerados": zerados, "mais_vendidos": vendidos,
            "comprar": comprar, "zerados_com_venda": sum(1 for r in zerados if r["vendidos"] > 0),
            "vendas_sem_estoque": sum(1 for r in vendidos if not r["no_estoque"]),
            "anuncios": anuncios, "precos": precos_diferentes(anuncios), "encalhados": encalhados(itens, vendas, dias)}


# ---------------------------------------------------------------------------
# 29/09 (Bruno: "DeepSeek focado no meu estoque: listas, preços, custo, frequência de venda, análise de vendas por anúncio,
# reposição"). Tudo calculado aqui; a IA só lê e organiza.
# ---------------------------------------------------------------------------
MARGEM_BAIXA = 0.25       # (preço médio − custo médio) ÷ preço abaixo disso = margem baixa (antes das taxas do canal)
ENCALHE_DIAS = 90         # estoque que dura mais que isso (ou sem venda no período) = encalhado
PRECO_DIFERENTE = 0.15    # mesmo SKU com preço médio 15%+ diferente entre anúncios/lojas


def _loja_curta(loja):
    m = re.match(r"\s*(.*?)\s*\[(.*?)\]", loja or "")
    return f"{m.group(1).strip().upper()} ({m.group(2).strip()})" if m else (loja or "").strip().upper()


def _frequencia(pedidos, dias):
    if not pedidos:
        return "sem venda"
    por_dia = pedidos / dias
    return f"{por_dia:.1f} pedidos/dia".replace(".", ",") if por_dia >= 1 else f"1 pedido a cada {dias / pedidos:.0f} dias"


def por_anuncio(itens, vendas, dias=30, gestor=None):
    """Uma linha por anúncio: preço médio, custo médio do SKU, margem antes das taxas, frequência (pedidos/dia) e o estoque do
    SKU. Ordem: o que mais fatura primeiro. card #124: com as linhas do Gestor Seller, `margem_real_pct`/`lucro_un` do SKU
    (depois de taxas, imposto e frete) quando o SKU casa."""
    est = {_chave(it["sku"]): it for it in itens or []}
    real = gestor_por_sku(gestor)
    out = []
    for v in vendas or []:
        it = (est.get(_chave(v["sku"])) or {}) if v.get("sku") else {}
        un, ped, val = v.get("unidades") or 0, v.get("pedidos") or 0, v.get("valor") or 0
        preco = v.get("preco_medio") or (val / un if un else 0)
        custo = it.get("custo_medio")
        custo = float(custo) if custo not in (None, "") and float(custo) > 0 else None
        margem = round(preco - custo, 2) if custo and preco else None
        out.append({"anuncio": v.get("anuncio") or "", "sku": v["sku"], "produto": v.get("produto") or it.get("titulo") or "",
                    "loja": _loja_curta(v.get("loja")), "pedidos": round(ped), "unidades": round(un), "valor": round(val, 2),
                    "preco": round(preco, 2) if preco else None, "custo": custo, "margem": margem,
                    "margem_pct": round(margem / preco * 100, 1) if margem is not None and preco else None,
                    "pedidos_dia": round(ped / dias, 2), "frequencia": _frequencia(ped, dias),
                    "estoque": (it.get("disponivel") or 0) if it else None,
                    "margem_real_pct": (real.get(_chave(v["sku"])) or {}).get("margem_pct"),
                    "lucro_un": (real.get(_chave(v["sku"])) or {}).get("lucro_un"), "sem_sku": not v.get("sku")})
    out.sort(key=lambda r: (-r["valor"], -r["unidades"]))
    return out


ABC_A, ABC_B = 0.80, 0.95      # igual ao UpSeller (conferido em 01/10: 59/95/166 anúncios = 79,71% / 15,23% / 5,06%)


def curva_abc(vendas, por="valor", classes_upseller=None):
    """01/10 (Bruno: "coloque também as vendas ABC do UpSeller"): curva ABC por anúncio, como a Análise ABC do UpSeller
    ("Anúncio & Valor de Vendas" / "Anúncio & Volume de Vendas"): ordena pelo valor (ou unidades), acumula; A até 80% do
    acumulado, B até 95%, C o resto. Mesmo relatório Vendas por Anúncio, sem baixar outro."""
    campo = "valor" if por == "valor" else "unidades"
    # todos os anúncios do relatório, até os de valor 0 (o UpSeller conta esses em C: 166 e não 156 no arquivo de 09/2026)
    xs = sorted((v for v in vendas or []), key=lambda v: -(v.get(campo) or 0))
    tot = sum(v.get(campo) or 0 for v in xs)
    out, ac = [], 0.0
    res = {k: {"classe": k, "anuncios": 0, "total": 0.0} for k in "ABC"}
    for v in xs:
        ac += v.get(campo) or 0
        acum = ac / tot if tot else 0
        k = "A" if acum <= ABC_A + 1e-9 else "B" if acum <= ABC_B + 1e-9 else "C"
        if classes_upseller:                    # a letra do próprio UpSeller (Análise ABC) vence a conta, se o anúncio está lá
            k = classes_upseller.get((str(v.get("anuncio") or ""), _loja_curta(v.get("loja")))) or k
        res[k]["anuncios"] += 1
        res[k]["total"] += v.get(campo) or 0
        out.append({"anuncio": v.get("anuncio") or "", "sku": v.get("sku") or "", "produto": v.get("produto") or "",
                    "loja": _loja_curta(v.get("loja")), "valor": round(v.get("valor") or 0, 2), "unidades": round(v.get("unidades") or 0),
                    "preco": v.get("preco_medio"), "pct": round((v.get(campo) or 0) / tot * 100, 2) if tot else 0,
                    "acum": round(acum * 100, 2), "classe": k})
    n = len(xs)
    for r in res.values():
        r["pct"] = round(r["total"] / tot * 100, 2) if tot else 0
        r["pct_anuncios"] = round(r["anuncios"] / n * 100, 2) if n else 0
        r["total"] = round(r["total"], 2)
    return {"por": campo, "total": round(tot, 2), "anuncios": n, "classes": [res[k] for k in "ABC"], "itens": out}


def precos_diferentes(anuncios, limite=PRECO_DIFERENTE):
    """SKUs vendidos em mais de um anúncio com preço médio muito diferente (o mais barato pode estar deixando dinheiro)."""
    por = {}
    for a in anuncios:
        if a["preco"] and a["sku"]:
            por.setdefault(_chave(a["sku"]), []).append(a)
    out = []
    for xs in por.values():
        if len(xs) < 2:
            continue
        lo, hi = min(xs, key=lambda a: a["preco"]), max(xs, key=lambda a: a["preco"])
        if hi["preco"] >= lo["preco"] * (1 + limite):
            out.append({"sku": lo["sku"], "produto": lo["produto"], "menor": lo["preco"], "loja_menor": lo["loja"],
                        "anuncio_menor": lo["anuncio"], "maior": hi["preco"], "loja_maior": hi["loja"], "anuncio_maior": hi["anuncio"],
                        "diferenca_pct": round((hi["preco"] / lo["preco"] - 1) * 100, 1), "anuncios": len(xs),
                        "unidades": sum(a["unidades"] for a in xs)})
    out.sort(key=lambda r: -r["unidades"])
    return out


def encalhados(itens, vendas, dias=30, limite=ENCALHE_DIAS):
    """Estoque parado: disponível > 0 que dura mais de `limite` dias no ritmo atual (ou não vendeu nada). Valor parado =
    disponível × custo médio; o que mais prende dinheiro primeiro."""
    vend = {}
    for v in vendas or []:
        k = _chave(v["sku"])
        vend[k] = vend.get(k, 0) + (v.get("unidades") or 0)
    out = []
    for it in itens or []:
        disp = it.get("disponivel") or 0
        if disp <= 0:
            continue
        vd = vend.get(_chave(it["sku"]), 0) / dias
        dura = round(disp / vd) if vd else None
        if dura is not None and dura <= limite:
            continue
        custo = it.get("custo_medio")
        custo = float(custo) if custo not in (None, "") and float(custo) > 0 else None
        out.append({"sku": it["sku"], "titulo": it.get("titulo") or "", "disponivel": disp, "vendidos": round(vd * dias),
                    "dura": dura, "custo": custo, "parado": round(disp * custo, 2) if custo else None})
    out.sort(key=lambda r: -(r["parado"] or 0))
    return out


def painel(itens, ls, tem_vendas=True):
    """Card #122: quadro "Estoque total" do topo do Estoque, só com números de `listas`/`encalhados` (nunca IA). None = sem
    dados: sem estoque, sem custo ou (dinheiro parado, zerados que vendem e cobertura) sem o relatório de vendas."""
    com_custo = [it for it in itens or [] if (it.get("custo_medio") or 0) > 0 and (it.get("atual") or 0) > 0]
    cob = [r["cobertura_dias"] for r in ls.get("mais_vendidos") or [] if r["no_estoque"] and r["cobertura_dias"] is not None]
    en = [x["parado"] for x in ls.get("encalhados") or [] if x["parado"] is not None]
    return {"unidades": round(sum(it.get("atual") or 0 for it in itens), 2) if itens else None,
            "valor_custo": round(sum(it["atual"] * it["custo_medio"] for it in com_custo), 2) if com_custo else None,
            "parado": round(sum(en), 2) if tem_vendas and itens and (en or not ls.get("encalhados")) else None,
            "encalhados": len(ls.get("encalhados") or []) if tem_vendas and itens else None,
            "zerados_vendem": ls.get("zerados_com_venda") if tem_vendas and itens else None,
            "cobertura_media": round(sum(cob) / len(cob), 1) if tem_vendas and cob else None, "cobertura_skus": len(cob)}


PAPEL_ANALISE = ("Você é o DeepSeek, analista do ESTOQUE do Bruno no nubi (seu foco é só o estoque dele). Abaixo, o estoque do "
                 "UpSeller cruzado com as vendas por anúncio dos últimos {dias} dias, já calculado pelo sistema: NÃO recalcule e "
                 "NÃO invente nenhum número. Margem = preço médio − custo médio, ANTES das taxas do canal e do frete. Escreva em "
                 "português do Brasil, direto, em markdown curto, com estas seções:\n"
                 "## Comprar já\nos 5 a 8 mais urgentes (acabam primeiro e vendem bem), com a quantidade e o porquê.\n"
                 "## Zerados que vendem\no que está vendendo zero por falta de estoque.\n"
                 "## Campeões\nos que mais vendem, a frequência de venda e como está o estoque deles.\n"
                 "## Anúncios\nos anúncios que mais faturam e os que vendem pouco para o estoque que têm; por loja quando fizer diferença.\n"
                 "## Preços e margem\nmargem baixa ou negativa, e o mesmo SKU com preço diferente entre anúncios/lojas "
                 "(qual subir ou baixar).\n"
                 "## Encalhados\no que prende mais dinheiro parado e uma ideia para girar (promoção, kit, outra loja).\n"
                 "## Atenção\n1 ou 2 riscos (SKU vendido que não está no estoque, custo faltando).")


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
            + f"\n\nSKUs vendidos que não estão no estoque do UpSeller: {ls['vendas_sem_estoque']}."
            + tabelas_extra(ls))


def _rs(v):
    return "—" if v is None else f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tabelas_extra(ls, n=30):
    """Anúncios, preços diferentes e encalhados, em texto para a IA."""
    an = ls.get("anuncios") or []
    t = "\n\nANÚNCIOS (mais faturamento primeiro; margem antes das taxas):\n" + ("\n".join(
        f"  {a['anuncio'] or '—'} | {a['loja']} | {a['sku']} | {a['produto'][:45]} | {a['unidades']} un | {_rs(a['valor'])} | "
        f"preço {_rs(a['preco'])} | custo {_rs(a['custo'])} | margem {a['margem_pct'] if a['margem_pct'] is not None else '—'}% | "
        f"{a['frequencia']} | estoque do SKU {a['estoque'] if a['estoque'] is not None else 'fora do estoque'}" for a in an[:n])
        or "  (nenhum)")
    baixa = [a for a in an if a["margem_pct"] is not None and a["margem_pct"] < MARGEM_BAIXA * 100]
    t += f"\n\nMARGEM ABAIXO DE {MARGEM_BAIXA * 100:.0f}% ({len(baixa)} anúncios):\n" + ("\n".join(
        f"  {a['anuncio'] or '—'} | {a['loja']} | {a['sku']} | preço {_rs(a['preco'])} | custo {_rs(a['custo'])} | "
        f"margem {a['margem_pct']}% | {a['unidades']} un" for a in sorted(baixa, key=lambda a: a["margem_pct"])[:15]) or "  (nenhum)")
    pr = ls.get("precos") or []
    t += f"\n\nMESMO SKU COM PREÇO DIFERENTE ({len(pr)}):\n" + ("\n".join(
        f"  {x['sku']} | {x['produto'][:45]} | {_rs(x['menor'])} em {x['loja_menor']} x {_rs(x['maior'])} em {x['loja_maior']} "
        f"(+{x['diferenca_pct']}%) | {x['unidades']} un" for x in pr[:15]) or "  (nenhum)")
    en = ls.get("encalhados") or []
    t += f"\n\nENCALHADOS (dura mais de {ENCALHE_DIAS} dias ou sem venda; {len(en)} SKUs, "
    t += f"{_rs(sum(x['parado'] or 0 for x in en))} parados):\n" + ("\n".join(
        f"  {x['sku']} | {x['titulo'][:45]} | disp. {x['disponivel']:g} | vendeu {x['vendidos']} | "
        f"dura {x['dura'] if x['dura'] is not None else 'sem venda'} | parado {_rs(x['parado'])}" for x in en[:15]) or "  (nenhum)")
    return t


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


def ler_cadastro_produtos(conteudo):
    """02/10 (Bruno: "consegui exportar isso do UpSeller, tem o código de barras dos meus produtos"): Produtos → Exportar
    (export_warehouse_products_*.xlsx) -> {chave do SKU: {sku, gtin, custo_compra, categoria, marca, titulo}}. O GTIN liga o
    meu SKU ao mercado do Explorador; o custo de compra cobre SKU sem custo médio no estoque."""
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
    pos = {n: i for i, n in enumerate(cab)}
    if _cab("SKU") not in pos or _cab("Código de Barras") not in pos:
        raise ErroEstoque("não parece o cadastro de produtos do UpSeller (faltam as colunas SKU e Código de Barras)")
    col = lambda r, n: r[pos[_cab(n)]] if _cab(n) in pos and pos[_cab(n)] < len(r) else None
    out = {}
    for r in linhas:
        sku = str(col(r, "SKU") or "").strip()
        if not sku:
            continue
        g = re.sub(r"\D", "", str(col(r, "Código de Barras") or ""))
        try:
            c = float(str(col(r, "Custo de Compra")).replace(",", ".")) if col(r, "Custo de Compra") not in (None, "") else None
        except ValueError:
            c = None
        out[_chave(sku)] = {"sku": sku, "gtin": g if len(g) >= 8 else None, "custo_compra": c if c and c > 0 else None,
                            "categoria": col(r, "Categorias"), "marca": col(r, "Marca"), "titulo": col(r, "Título")}
    if not out:
        raise ErroEstoque("nenhum SKU na planilha")
    return out
