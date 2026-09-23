# -*- coding: utf-8 -*-
"""
Ranking mensal de marcas: o relatório "MARCAS" do Nubimetrics (fechamento do mês,
sem produtos). Uma linha por marca: posição, variação no ranking, vendas em $,
quantidade vendida, tendência, % catálogo, vendedores, saturação e ranking de demanda.

Nome do arquivo no padrão do Nubimetrics:  MARCAS-MLB1246-MLB6284-2026-08-01_1.xlsx
  -> categoria "MLB1246-MLB6284" (Beleza e Cuidado Pessoal > Perfumes), mês 2026-08.
"""

import hashlib
import io
import math
import re
import statistics

import nubi

PADRAO_ARQUIVO = re.compile(r"MARCAS[-_]+(?P<cat>(?:MLB\d+[-_]?)+?)[-_]+(?P<mes>\d{4}-\d{2})(?:-\d{2})?", re.I)

# Nomes das categorias do Mercado Livre que aparecem nos códigos (os que não estão aqui
# aparecem pelo código mesmo).
NOMES_CATEGORIA = {
    "MLB1246": "Beleza e Cuidado Pessoal",
    "MLB6284": "Perfumes",
    "MLB1248": "Maquiagem",
    "MLB1263": "Cuidados com a Pele",
    "MLB199407": "Cuidados com o Cabelo",
}

COLUNAS = ["#", "Variação", "Marca", "Vendas em $", "Quantidade vendas", "Tendencia ranking",
           "Catálogo", "Vendedores", "Saturação", "Ranking de demanda"]

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]


class ErroRanking(Exception):
    pass


def nome_categoria(cat):
    partes = [p for p in re.split(r"[-_]", cat or "") if p]
    return " > ".join(NOMES_CATEGORIA.get(p.upper(), p.upper()) for p in partes)


def nome_mes(mes):
    """'2026-08-01' -> 'agosto de 2026'."""
    a, m = str(mes)[:7].split("-")
    return f"{MESES[int(m) - 1]} de {a}"


def valor_abreviado(v):
    """'+$20.9M' -> 20900000.0 ; '+161.6k' -> 161600.0 ; '61,3%' -> 0.613 ; 549 -> 549."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace("R$", "").replace("$", "").replace("+", "").replace(" ", "")
    pct = t.endswith("%")
    t = t.rstrip("%")
    m = re.fullmatch(r"(-?[\d.,]+)([kKmMbB]?)", t)
    if not m:
        return None
    num, suf = m.groups()
    if suf:                                   # abreviado: ponto é decimal (20.9M)
        num = num.replace(",", ".")
    elif "," in num:                          # pt-BR: 1.234,5
        num = num.replace(".", "").replace(",", ".")
    try:
        x = float(num)
    except ValueError:
        return None
    x *= {"k": 1e3, "m": 1e6, "b": 1e9}.get(suf.lower(), 1) if suf else 1
    return x / 100 if pct else x


def _inteiro(v):
    x = valor_abreviado(v)
    return None if x is None else int(round(x))


def ler_relatorio(dados, nome_arquivo=""):
    """Lê o .xlsx (ou .csv) do relatório de marcas. Devolve (linhas, categoria, mes)."""
    linhas_brutas = []
    if nome_arquivo.lower().endswith(".csv"):
        import pandas as pd
        texto = None
        for enc in ("utf-8-sig", "latin-1"):
            try:
                texto = dados.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        sep = ";" if texto and texto.count(";") > texto.count(",") else ","
        df = pd.read_csv(io.StringIO(texto or ""), sep=sep, dtype=str, keep_default_na=False)
        linhas_brutas = [list(df.columns)] + df.values.tolist()
    else:
        from openpyxl import load_workbook
        try:
            wb = load_workbook(io.BytesIO(dados), read_only=True, data_only=True)
        except Exception:  # noqa: BLE001
            raise ErroRanking("não consegui abrir o arquivo como planilha (.xlsx)")
        ws = wb.worksheets[0]
        linhas_brutas = [list(r) for r in ws.iter_rows(values_only=True)]

    # Cabeçalho: a primeira linha que tem "Marca" e "Vendas".
    ini = next((i for i, r in enumerate(linhas_brutas[:20])
                if any(str(c or "").strip().lower() == "marca" for c in r)
                and any("venda" in str(c or "").lower() for c in r)), None)
    if ini is None:
        raise ErroRanking("não parece o relatório de marcas do Nubimetrics (faltam as colunas Marca e Vendas)")
    cab = [str(c or "").strip() for c in linhas_brutas[ini]]
    idx = {c.lower(): i for i, c in enumerate(cab)}

    def col(r, *nomes):
        for n in nomes:
            i = idx.get(n.lower())
            if i is not None and i < len(r):
                return r[i]
        return None

    linhas = []
    for r in linhas_brutas[ini + 1:]:
        marca = str(col(r, "Marca") or "").strip()
        if not marca:
            continue
        linhas.append({
            "posicao": _inteiro(col(r, "#", "Posição", "Posicao")),
            "variacao": _inteiro(col(r, "Variação", "Variacao")),
            "marca": marca,
            "marca_chave": nubi.compacta(marca),
            "vendas": valor_abreviado(col(r, "Vendas em $", "Vendas")),
            "unidades": valor_abreviado(col(r, "Quantidade vendas", "Unidades vendidas", "Quantidade")),
            "tendencia": str(col(r, "Tendencia ranking", "Tendência ranking", "Tendencia") or "").strip(),
            "catalogo": valor_abreviado(col(r, "Catálogo", "Catalogo")),
            "vendedores": _inteiro(col(r, "Vendedores")),
            "saturacao": str(col(r, "Saturação", "Saturacao") or "").strip(),
            "ranking_demanda": _inteiro(col(r, "Ranking de demanda")),
            "bruto": {c: ("" if v is None else str(v)) for c, v in zip(cab, r) if c},
        })
    if not linhas:
        raise ErroRanking("o arquivo não tem nenhuma marca")
    for i, l in enumerate(linhas, 1):
        if l["posicao"] is None:
            l["posicao"] = i

    m = PADRAO_ARQUIVO.search(nome_arquivo or "")
    categoria = m.group("cat").strip("-_").upper().replace("_", "-") if m else ""
    mes = f"{m.group('mes')}-01" if m else ""
    return linhas, categoria, mes


def hash_de(dados):
    return hashlib.sha256(dados).hexdigest()


# ---------------------------------------------------------------------------
# Análise do mês (valores calculados para a página)
# ---------------------------------------------------------------------------

def _div(a, b):
    return float(a) / float(b) if a is not None and b else 0.0


SAT_LIVRE = {"baixa": 1.0, "média": 0.5, "media": 0.5, "alta": 0.0}
TEND = {"crescendo": 1.0, "estável": 0.5, "estavel": 0.5, "diminuindo": 0.0}


def analisar(linhas, anteriores=None, marcas_explorador=()):
    """
    Enriquece as linhas do mês:
      ticket médio (vendas ÷ unidades), vendas por vendedor, share do top listado,
      comparação com o mês anterior (se houver) e nota/sinais de oportunidade.
    Nota de oportunidade (0–100), pensada para achar marca para entrar, não a maior:
      100 × √(tamanho, com teto nas 25% maiores) × (0,10 + 0,30 × saturação livre
      + 0,30 × tendência + 0,15 × vendas por vendedor [3× a mediana = 1]
      + 0,15 × subida no ranking [+5 posições = 1]).
    Acima do percentil 75 de vendas o tamanho não soma mais: a partir daí pesam
    crescimento, saturação e concorrência.
    """
    tot_v = sum(l["vendas"] or 0 for l in linhas)
    tot_u = sum(l["unidades"] or 0 for l in linhas)
    vendas_ord = sorted(l["vendas"] or 0 for l in linhas)
    p75 = vendas_ord[int(len(vendas_ord) * 0.75)] if vendas_ord else 1
    vpv = [_div(l["vendas"], l["vendedores"]) for l in linhas if l["vendedores"]]
    med_vpv = statistics.median(vpv) if vpv else 0
    ant = {l["marca_chave"]: l for l in (anteriores or [])}
    explorador = {nubi.compacta(m): m for m in marcas_explorador}
    saida, acum = [], 0.0
    for l in sorted(linhas, key=lambda x: x["posicao"] or 9999):
        x = {k: v for k, v in l.items() if k != "bruto"}
        x["ticket"] = _div(l["vendas"], l["unidades"])
        x["vendas_por_vendedor"] = _div(l["vendas"], l["vendedores"])
        x["share"] = _div(l["vendas"], tot_v)
        acum += x["share"]
        x["share_acum"] = acum
        a = ant.get(l["marca_chave"])
        if anteriores is not None:
            x["posicao_ant"] = a["posicao"] if a else None
            x["vendas_ant"] = a["vendas"] if a else None
            x["unidades_ant"] = a["unidades"] if a else None
            x["var_vendas"] = (_div(l["vendas"], a["vendas"]) - 1) if a and a["vendas"] else None
            x["var_unidades"] = (_div(l["unidades"], a["unidades"]) - 1) if a and a["unidades"] else None
            x["novo"] = a is None
        sat = SAT_LIVRE.get((l["saturacao"] or "").lower(), 0.5)
        ten = TEND.get((l["tendencia"] or "").lower(), 0.5)
        rel = min(1.0, _div(x["vendas_por_vendedor"], 3 * med_vpv)) if med_vpv else 0
        sub = min(1.0, max(0, l["variacao"] or 0) / 5)
        tam = math.sqrt(min(1.0, _div(l["vendas"] or 0, p75)))
        x["nota"] = round(100 * tam * (0.1 + 0.3 * sat + 0.3 * ten + 0.15 * rel + 0.15 * sub))
        s = []
        if (l["saturacao"] or "").lower() == "baixa":
            s.append("Pouca saturação")
        if (l["tendencia"] or "").lower() == "crescendo":
            s.append("Crescendo")
        if med_vpv and x["vendas_por_vendedor"] >= 3 * med_vpv:
            s.append("Poucos vendedores p/ o volume")
        if (l["variacao"] or 0) >= 3:
            s.append("Subiu no ranking")
        if l["catalogo"] is not None and l["catalogo"] < 0.5:
            s.append("Catálogo pouco disputado")
        if (l["tendencia"] or "").lower() == "diminuindo":
            s.append("Diminuindo")
        if (l["variacao"] or 0) <= -3:
            s.append("Caiu no ranking")
        if (l["saturacao"] or "").lower() == "alta":
            s.append("Saturada")
        if anteriores is not None and x.get("novo"):
            s.append("Nova no ranking")
        x["sinais"] = " · ".join(s)
        x["explorador"] = explorador.get(l["marca_chave"])
        saida.append(x)
    saiu = []
    if anteriores is not None:
        atuais = {l["marca_chave"] for l in linhas}
        saiu = [{"marca": a["marca"], "posicao_ant": a["posicao"], "vendas_ant": a["vendas"]}
                for a in anteriores if a["marca_chave"] not in atuais]
    conc = {}
    for n in (1, 3, 5, 10, 20):
        conc[f"top{n}"] = sum(x["share"] for x in saida[:n])
    resumo = {
        "marcas": len(saida), "vendas": tot_v, "unidades": tot_u, "ticket": _div(tot_v, tot_u),
        "vendedores_mediana": statistics.median([l["vendedores"] for l in linhas if l["vendedores"]] or [0]),
        "crescendo": sum(1 for l in linhas if (l["tendencia"] or "").lower() == "crescendo"),
        "diminuindo": sum(1 for l in linhas if (l["tendencia"] or "").lower() == "diminuindo"),
        "estavel": sum(1 for l in linhas if (l["tendencia"] or "").lower() in ("estável", "estavel")),
        "sat_baixa": sum(1 for l in linhas if (l["saturacao"] or "").lower() == "baixa"),
        "sat_media": sum(1 for l in linhas if (l["saturacao"] or "").lower() in ("média", "media")),
        "sat_alta": sum(1 for l in linhas if (l["saturacao"] or "").lower() == "alta"),
        "concentracao": conc,
    }
    if anteriores is not None:
        tv_a = sum(a["vendas"] or 0 for a in anteriores)
        tu_a = sum(a["unidades"] or 0 for a in anteriores)
        resumo.update({"vendas_ant": tv_a, "unidades_ant": tu_a,
                       "var_vendas": (_div(tot_v, tv_a) - 1) if tv_a else None,
                       "var_unidades": (_div(tot_u, tu_a) - 1) if tu_a else None,
                       "novas": sum(1 for x in saida if x.get("novo")), "sairam": len(saiu)})
    return saida, saiu, resumo
