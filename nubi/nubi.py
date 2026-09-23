#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nubi — explorador de anúncios: monitoramento de mercado a partir dos exports CSV do Nubimetrics.

Uso:
    python nubi.py
    python nubi.py --marca MONTBLANC --inicio 2026-08-01 --fim 2026-09-16
      (marca/período para os CSVs cujo nome não segue MARCA__AAAA-MM-DD_AAAA-MM-DD.csv)

Lê os CSVs de entrada/, guarda o histórico em dados/base.db e gera uma
planilha por marca em saida/, mais o painel-geral.xlsx.
Dependências: pandas e openpyxl.
"""

import argparse
import hashlib
import io
import os
import json
import re
import sqlite3
import sys
import time
import traceback
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

try:
    import pandas as pd
    from openpyxl import Workbook
    from openpyxl.formatting.rule import ColorScaleRule, FormulaRule
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    print("Faltam bibliotecas. Instale com:  pip install pandas openpyxl")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Pastas e constantes
# ---------------------------------------------------------------------------

BASE = Path(__file__).resolve().parent
ENTRADA = BASE / "entrada"
SAIDA = BASE / "saida"
DADOS = BASE / "dados"
BANCO = DADOS / "base.db"
CONFIG = BASE / "marcas.json"
ARQ_GTINS = BASE / "gtins.json"
ARQ_TOKEN_COSMOS = BASE / "cosmos-token.txt"
LOG_ERRO = DADOS / "erro.log"

PADRAO_NOME = re.compile(r"^(.+?)__(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})$", re.IGNORECASE)
COLUNAS_OBRIGATORIAS = ["Título", "Vendedor", "Unidades vendidas"]
# Colunas do export do Nubimetrics, na ordem do arquivo. A linha original de cada anúncio
# é guardada inteira (campo "bruto") e mostrada assim na aba Anúncios da página.
COLUNAS_NUBIMETRICS = [
    "Título", "Vendedor", "Categoria L1", "Categoria final", "Código Completo da Categoria",
    "Código da Categoria L1", "Código da Categoria Final", "Categoria completa", "Vendas em $ históricas",
    "Vendas em $", "Unidades vendidas históricas", "Unidades vendidas", "Último preço", "Data de criação",
    "Dias publicados", "Exposição", "Parcelas", "Catálogo", "FLEX", "FULL", "Compra Internacional", "Marca",
    "Modelo", "Loja oficial", "Frete grátis", "ID do anúncio", "ID do vendedor", "Sku", "Gtin", "N° Peça", "Oem",
]
COLUNAS_OPCIONAIS = [
    "Vendas em $ históricas", "Vendas em $", "Unidades vendidas históricas",
    "Último preço", "Dias publicados", "Exposição", "Catálogo", "FLEX", "FULL",
    "Compra Internacional", "Marca", "Loja oficial", "Frete grátis",
    "ID do vendedor", "Sku", "Gtin", "Categoria L1", "Categoria final",
]

# O export da marca inteira traz também o que não é perfume (canetas, cintos...).
# Esses anúncios continuam contando no total, mas viram uma referência por categoria.
CATEGORIA_PERFUMARIA = "beleza e cuidado pessoal"
TIPO_FORA = "Não perfume"
TIPO_OUTRA = "Outra marca"   # anúncio de outra marca (contratipo, erro de cadastro)
TIPO_PADRAO = "EDT?"   # título sem tipo escrito: EDT por padrão, mas não vota na etapa 2

# Grau de confiança do agrupamento de cada anúncio (coluna "Confiança").
CONF_PESQ = "Pesquisado (GTIN)"
CONF_GTIN = "Confirmado por GTIN"
CONF_TITULO = "Só título"
DUV_DIVERG = "Dúvida: títulos divergentes"
DUV_LINHA = "Dúvida: linha não identificada"

# Especificações pesquisadas por GTIN (gtins.json). Carregado no main().
INFO_GTIN = {}

# Prefixos GS1 plausíveis para achar um GTIN dentro de uma string de dígitos colados.
PREFIXOS_GS1 = ("789", "332", "542", "629", "608", "500", "871", "400", "301", "760", "335")

NEUTROS = {"-", "Outros", "EDT?"}   # valores que não votam na etapa 2 da consolidação

NOTA_FAT = ("Faturamento (Vendas em $) vem arredondado em faixas pela plataforma de origem: "
            "preços médios calculados por faturamento ÷ unidades são aproximados.")

# Palavras que nunca são nome de linha de produto (usadas na detecção automática).
PALAVRAS_VAZIAS = set("""
perfume perfumes original originais importado importada importados masculino masculina masc fem homens mulheres
feminino feminina unissex eau toilette parfum cologne edt edp edc ml spray amadeirado
amadeirada amadeirados fragrancia fragrancias colonia deo desodorante body splash kit
kits estojo lacrado lacrada novo nova homem mulher para com sem lancamento promocao
oferta envio imediato pronta entrega frete gratis brinde caixa selo nacional nota fiscal
adipec garantia autentico autentica verdadeiro produto unidade unidades frasco tester
contratipo inspiracao essencia intensa oriental floral frutado aromatico citrico
presente vaporizador tradicional fixacao alta longa duracao cheiroso cheirosa melhor mais
de da do das dos di du la le the and em por
""".split())


# Mensagens ao usuário: no terminal vão para o print; na versão web, para uma lista
# que volta como resposta da página.
_SAIDA = [print]


def avisar(msg=""):
    _SAIDA[0](msg)


# ---------------------------------------------------------------------------
# Utilidades de texto e números
# ---------------------------------------------------------------------------

def sem_acento(txt):
    txt = unicodedata.normalize("NFKD", str(txt))
    return "".join(c for c in txt if not unicodedata.combining(c))


def normalizar(txt):
    """Minúsculo, sem acento, só letras/números/espaço, espaços simples."""
    txt = sem_acento(txt).lower()
    txt = re.sub(r"[^a-z0-9 ]+", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


def chave_marca(marca):
    return re.sub(r"\s+", " ", sem_acento(marca).upper()).strip()


def palavras_da_marca(marca):
    """
    Palavras que são só o nome da marca, em qualquer grafia: "MONT BLANC" dá
    {"mont", "blanc", "montblanc"} e "MONTBLANC" dá {"montblanc"} — o título pode
    trazer "Mont Blanc" ou "Montblanc" e nenhum dos dois é linha de produto.
    """
    p = set(normalizar(marca).split())
    if p:
        p.add("".join(normalizar(marca).split()))
    return p


def nome_bonito(txt):
    """ARMAF -> Armaf; ULRIC DE VARENS -> Ulric de Varens."""
    minusculas = {"de", "da", "do", "das", "dos", "di", "du", "del", "e"}
    palavras = str(txt).lower().split()
    return " ".join(p if (i > 0 and p in minusculas) else p[:1].upper() + p[1:]
                     for i, p in enumerate(palavras))


def slug(marca):
    return re.sub(r"[^a-z0-9]+", "-", sem_acento(marca).lower()).strip("-")


def fmt_int(n):
    return f"{int(round(n)):,}".replace(",", ".")


def fmt_data(d):
    return datetime.strptime(d, "%Y-%m-%d").strftime("%d/%m/%Y")


def limpar_celula(v):
    """Tira o lixo de fórmula do Excel: =\"\"\"3355...\"\"\"  ->  3355..."""
    v = "" if v is None else str(v)
    return re.sub(r'^\s*=|"', "", v).strip()


def para_numero(v):
    """'$ 147.000,00' -> 147000.0  (ponto = milhar, vírgula = decimal)."""
    v = re.sub(r"[^0-9,.\-]", "", limpar_celula(v))
    if not v:
        return 0.0
    v = v.replace(".", "").replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return 0.0


def para_inteiro(v):
    return int(round(para_numero(v)))


def sim_nao(v):
    return 1 if normalizar(limpar_celula(v)) in ("sim", "si", "yes", "s", "1", "true") else 0


def digito_gtin_ok(g):
    """Confere o dígito verificador GS1 (módulo 10)."""
    corpo, dv = g[:-1], int(g[-1])
    soma = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(corpo)))
    return (10 - soma % 10) % 10 == dv


def normalizar_gtin(v, conhecidos=None):
    """
    Devolve um GTIN de 12 ou 13 dígitos, ou "" quando não há GTIN aproveitável.
      =\"\"\"3355991003019\"\"\"   -> 3355991003019
      78949141202503355991002319    -> um dos dois GTINs colados (ver abaixo)
      03355991005174 (14 dígitos)   -> 3355991005174
      ES2601MK25 / SILVERSCENT      -> ""
    """
    dig = re.sub(r"\D", "", limpar_celula(v))
    if len(dig) == 14 and dig.startswith("0"):
        dig = dig[1:]
    elif len(dig) > 13:
        # Dois GTINs colados: procurar janelas de 13 dígitos com prefixo GS1.
        # Os dois costumam ter dígito verificador válido, então desempata o contexto
        # do próprio arquivo (`conhecidos`: prefixo de empresa -> unidades): ganha o
        # candidato cujo prefixo de 7 dígitos é o da marca. Depois, dígito válido.
        conhecidos = conhecidos or {}
        candidatos = [dig[i:i + 13] for i in range(len(dig) - 12)
                      if dig[i:i + 13].startswith(PREFIXOS_GS1)]
        candidatos.sort(key=lambda c: (-conhecidos.get(c[:7], 0), not digito_gtin_ok(c)))
        dig = (candidatos or [""])[0]
    return dig if len(dig) in (12, 13) else ""


# ---------------------------------------------------------------------------
# Leitura do CSV
# ---------------------------------------------------------------------------

class ErroArquivo(Exception):
    """Erro de leitura que vira uma linha amigável no terminal."""


def ler_csv(fonte):
    """`fonte`: caminho do arquivo ou o conteúdo em bytes (upload pela web)."""
    df = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            entrada = io.BytesIO(fonte) if isinstance(fonte, (bytes, bytearray)) else fonte
            df = pd.read_csv(entrada, sep=";", encoding=enc, dtype=str,
                             keep_default_na=False, on_bad_lines="skip")
            break
        except UnicodeDecodeError:
            continue
        except pd.errors.EmptyDataError:
            raise ErroArquivo("arquivo vazio")
        except Exception as e:  # noqa: BLE001 — qualquer falha vira aviso, não trava
            raise ErroArquivo(f"não consegui ler o arquivo ({e.__class__.__name__})")
    if df is None:
        raise ErroArquivo("codificação de texto não reconhecida")

    # Alguns nomes de coluna vêm com aspas e espaço sobrando.
    df.columns = [str(c).strip().strip('"').strip() for c in df.columns]
    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in df.columns]
    if faltando:
        raise ErroArquivo("não parece um export do Nubimetrics (faltam as colunas: "
                          + ", ".join(faltando) + ")")
    originais = list(df.columns)
    for c in COLUNAS_OPCIONAIS:
        if c not in df.columns:
            df[c] = ""
    df = df[df["Título"].str.strip() != ""]
    if df.empty:
        raise ErroArquivo("o arquivo não tem nenhum anúncio")

    out = pd.DataFrame({
        "titulo": df["Título"].str.strip(),
        "vendedor": df["Vendedor"].str.strip(),
        "vendedor_id": df["ID do vendedor"].map(limpar_celula),
        "sku": df["Sku"].map(limpar_celula),
        "un": df["Unidades vendidas"].map(para_inteiro),
        "fat": df["Vendas em $"].map(para_numero),
        "preco": df["Último preço"].map(para_numero),
        "un_hist": df["Unidades vendidas históricas"].map(para_inteiro),
        "fat_hist": df["Vendas em $ históricas"].map(para_numero),
        "dias_pub": df["Dias publicados"].map(para_inteiro),
        "exposicao": df["Exposição"].str.strip(),
        "catalogo": df["Catálogo"].map(sim_nao),
        "full": df["FULL"].map(sim_nao),
        "flex": df["FLEX"].map(sim_nao),
        "internacional": df["Compra Internacional"].map(sim_nao),
        "loja_oficial": df["Loja oficial"].map(lambda v: 1 if limpar_celula(v) else 0),
        "frete_gratis": df["Frete grátis"].map(sim_nao),
        # Linha original do arquivo, coluna por coluna (só tira o ="..." do Excel).
        "bruto": [{c: re.sub(r'^="*(.*?)"*$', r"\1", str(v)).strip() for c, v in zip(originais, lin)}
                  for lin in df[originais].itertuples(index=False, name=None)],
        # "" = perfumaria; senão, o nome da categoria final (ex.: "Canetas").
        "marca_anuncio": df["Marca"].str.strip(),
        "categoria": [
            "" if (not l1.strip() or normalizar(l1) == CATEGORIA_PERFUMARIA)
            else (fin.strip() or l1.strip())
            for l1, fin in zip(df["Categoria L1"], df["Categoria final"])],
    })
    # O ID do vendedor é a chave; se vier vazio, o nome faz o papel.
    out.loc[out["vendedor_id"] == "", "vendedor_id"] = out["vendedor"]
    # GTIN: coluna Gtin; se não der nada, tenta a coluna Sku (às vezes o GTIN está lá).
    # 1ª passada só com GTINs limpos, para saber qual prefixo de empresa é o da marca.
    unidades = out["un"].values
    conhecidos = {}
    for bruto, un in zip(df["Gtin"], unidades):
        g = re.sub(r"\D", "", limpar_celula(bruto))
        if len(g) == 13:
            conhecidos[g[:7]] = conhecidos.get(g[:7], 0) + int(un) + 1
    gt = df["Gtin"].map(lambda v: normalizar_gtin(v, conhecidos))
    gt_sku = df["Sku"].map(lambda v: normalizar_gtin(v, conhecidos))
    out["gtin"] = gt.where(gt != "", gt_sku).values
    marcas = df["Marca"].str.strip()
    marcas = marcas[marcas != ""]
    sugestao = marcas.value_counts().index[0] if not marcas.empty else ""
    return out.reset_index(drop=True), sugestao


# ---------------------------------------------------------------------------
# Configuração de linhas por marca (marcas.json)
# ---------------------------------------------------------------------------

def carregar_config():
    if not CONFIG.exists():
        return {}
    try:
        bruto = json.loads(CONFIG.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ErroArquivo(f"marcas.json está com erro de digitação (linha {e.lineno}, "
                          f"coluna {e.colno}). Corrija e rode de novo.")
    return {chave_marca(k): v for k, v in bruto.items()}


def salvar_config(cfg):
    """Grava uma linha por par [chave, rótulo], fácil de editar à mão."""
    blocos = []
    for marca, dados in cfg.items():
        pares = ",\n".join("    " + json.dumps(p, ensure_ascii=False) for p in dados.get("linhas", []))
        blocos.append(f'  {json.dumps(marca, ensure_ascii=False)}: {{"linhas": [\n{pares}]}}')
    CONFIG.write_text("{\n" + ",\n\n".join(blocos) + "\n}\n", encoding="utf-8")


def detectar_linhas(df, marca):
    """
    Marca nova: descobre as linhas de produto pelos títulos, ponderando por unidades.
    Termos candidatos = palavras úteis (4+ letras) e pares de palavras consecutivas.
    Pares pesam o dobro na ordenação, senão "nuit" e "intense" soltos ganham de
    "nuit intense" e a linha real se perde.
    """
    palavras_marca = palavras_da_marca(marca)
    if "categoria" in df.columns:
        df = df[(df["categoria"].fillna("") == "") & (dono_do_anuncio(df, marca) == "")]
    # Nome de outra marca declarado na coluna Marca (loja, contratipo) também não é linha.
    alvo = compacta(marca)
    outras = {compacta(v).lower() for v in df.get("marca_anuncio", pd.Series(dtype=str)).fillna("")
              if v and not marca_bate(v, alvo)}
    util = lambda p: (p not in PALAVRAS_VAZIAS and p not in palavras_marca and p not in outras
                      and not any(ch.isdigit() for ch in p))
    volume = {}
    for titulo, un in zip(df["titulo"], df["un"]):
        toks = normalizar(titulo).split()
        # "Mont Blanc" escrito separado ainda é o nome da marca "MONTBLANC".
        for i in range(len(toks) - 1):
            if toks[i] + toks[i + 1] in palavras_marca:
                toks[i] = toks[i + 1] = toks[i] + toks[i + 1]
        termos = {t for t in toks if len(t) >= 4 and util(t)}
        termos |= {f"{a} {b}" for a, b in zip(toks, toks[1:])
                   if util(a) and util(b) and len(a) >= 3 and len(b) >= 3}
        for t in termos:
            volume[t] = volume.get(t, 0) + int(un)
    total = int(df["un"].sum())
    if total <= 0:
        return []
    cands = [(t, v) for t, v in volume.items() if v >= 0.015 * total]
    cands.sort(key=lambda tv: (-(tv[1] * (2 if " " in tv[0] else 1)), -len(tv[0])))
    escolhidos = []
    for termo, _ in cands:
        # Termo já contido num par escolhido é redundante ("nuit" dentro de "nuit intense").
        if any(f" {termo} " in f" {e} " for e in escolhidos):
            continue
        escolhidos.append(termo)
        if len(escolhidos) == 20:
            break
    escolhidos.sort(key=lambda t: -len(t))   # compostos antes dos curtos
    return [[t, nome_bonito(t)] for t in escolhidos]


def garantir_config(cfg, marca, df, repo=None):
    """Se a marca não está na configuração, detecta as linhas, grava e avisa."""
    chave = chave_marca(marca)
    if chave in cfg:
        return
    linhas = detectar_linhas(df, marca)
    cfg[chave] = {"linhas": linhas}
    if repo is not None:
        repo.salvar_config(cfg, chave)
    else:
        salvar_config(cfg)
    avisar(f"    Marca nova: {chave}. Linhas de produto detectadas e gravadas na configuração:")
    if linhas:
        for _, rotulo in linhas:
            avisar(f"      - {rotulo}")
    else:
        avisar("      (nenhuma — todos os anúncios vão para \"Outros\")")
    avisar("    Você pode ajustar essa lista (marcas.json ou tela Configuração) e reprocessar.")


# ---------------------------------------------------------------------------
# Consolidação: anúncios -> referências reais
# ---------------------------------------------------------------------------

def achar_linha(titulo_norm, linhas, palavras_marca):
    """
    Procura as chaves do marcas.json no título normalizado.
    - Chave contida numa chave maior que também casou é descartada
      ("club de nuit" some quando "club de nuit intense man" casa no mesmo lugar).
    - Entre as que sobram, ganha a que aparece mais cedo; empate, a mais longa.
    - Chave feita só de palavras do nome da marca (ex.: "bogart") é reserva:
      só vale se nada mais casar, porque o nome da marca está em quase todo título.
    """
    alvo = f" {titulo_norm} "
    achados = []
    for ordem, (chave, rotulo) in enumerate(linhas):
        k = normalizar(chave)
        if not k:
            continue
        pos = alvo.find(f" {k} ")
        if pos >= 0:
            reserva = set(k.split()) <= palavras_marca
            achados.append((pos, pos + len(k), ordem, rotulo, reserva))
    if not achados:
        return "Outros"
    principais = [a for a in achados if not a[4]] or achados
    principais = [a for a in principais
                  if not any(b is not a and b[0] <= a[0] and a[1] <= b[1]
                             and (b[1] - b[0]) > (a[1] - a[0]) for b in principais)]
    principais.sort(key=lambda a: (a[0], -(a[1] - a[0]), a[2]))
    return principais[0][3]


RE_VOLUME = re.compile(r"(?<!\d)(\d{2,3})\s?ml\b")


def achar_volume(t):
    m = RE_VOLUME.search(t)
    return f"{int(m.group(1))} ml" if m else "-"


def achar_tipo(t):
    """Ordem de precedência importa: um kit de body splash é Body Splash."""
    if "body" in t or "splash" in t:
        return "Body Splash"
    if "desodorante" in t or re.search(r"\bdeo\b", t):
        return "Deo"
    if "gel de banho" in t or "shower" in t or "sabonete" in t:
        return "Banho"
    if re.search(r"\bkits?\b", t) or "estojo" in t or re.search(r"\d\s*perfumes", t):
        return "Kit"
    if re.search(r"\bedp\b", t) or "eau de parfum" in t:
        return "EDP"
    if re.search(r"\bedc\b", t) or "cologne" in t:
        return "EDC"
    if re.search(r"\bedt\b", t) or "toilette" in t:
        return "EDT"
    # Nada escrito: EDT é o palpite, mas marcado como "EDT?" para não vencer, na
    # etapa 2, um título do mesmo GTIN que diz explicitamente "Eau de Parfum".
    return TIPO_PADRAO


RE_FEM = re.compile(r"\b(feminino|feminina|fem|woman|women|femme|her|mulher|lady|donna)\b")
RE_MASC = re.compile(r"\b(masculino|masculina|masc|men|man|homme|him|homem|uomo)\b")
RE_UNI = re.compile(r"\b(unissex|unisex|unisexo)\b")


def achar_genero(t):
    if RE_UNI.search(t):
        return "Unissex"
    f, m = bool(RE_FEM.search(t)), bool(RE_MASC.search(t))
    if f and m:
        return "Unissex"
    return "Feminino" if f else "Masculino" if m else "-"


def categoria_de(tipo):
    """Categoria para filtro, a partir do tipo."""
    return {"EDT": "Perfume", "EDP": "Perfume", "EDC": "Perfume", "Body Splash": "Body Splash",
            "Deo": "Desodorante", "Banho": "Banho", "Kit": "Kit", TIPO_OUTRA: "Outra marca",
            TIPO_FORA: "Não perfume"}.get(tipo, "Perfume")



def campos_do_arquivo(df, marca):
    """
    O que vem direto do arquivo tem prioridade: Categoria = coluna "Categoria final"
    (e "Categoria L1"); Marca = a marca do export (grafia oficial) ou, para anúncios
    de outra marca, o nome dela. Sem a linha original guardada, usa o tipo lido do título.
    """
    b = [x if isinstance(x, dict) else {} for x in (df["bruto"] if "bruto" in df.columns else [None] * len(df))]
    df["cat"] = [x.get("Categoria final") or categoria_de(t) for x, t in zip(b, df["tipo"])]
    df["cat_l1"] = [x.get("Categoria L1") or "-" for x in b]
    df["marca_prod"] = [l if t == TIPO_OUTRA else nome_bonito(marca) for l, t in zip(df["linha"], df["tipo"])]
    return df

def ler_texto(t, linhas, palavras_marca):
    """Lê linha, volume, tipo e gênero de um texto já normalizado."""
    return {"linha": achar_linha(t, linhas, palavras_marca), "volume": achar_volume(t),
            "tipo": achar_tipo(t), "genero": achar_genero(t)}


def _mais_vendido(sub, coluna):
    """Valor de `coluna` que somou mais unidades (neutros não votam). None se só há neutros."""
    s = sub[~sub[coluna].isin(NEUTROS)]
    if s.empty:
        return None
    agg = s.groupby(coluna)["un"].agg(["sum", "size"])
    agg = agg.sort_values(["sum", "size"], ascending=False, kind="mergesort")
    return agg.index[0]


def compacta(txt):
    """'Mont Blanc' e 'MONTBLANC' viram a mesma coisa: MONTBLANC."""
    return re.sub(r"[^A-Z0-9]", "", sem_acento(txt).upper())


def marca_bate(valor, alvo):
    v = compacta(valor)
    return bool(v) and (v == alvo or (len(v) >= 4 and (v in alvo or alvo in v)))


def dono_do_anuncio(df, marca, pesquisados=None):
    """
    Confirma, anúncio por anúncio, se ele é mesmo da marca do export — cruzando a
    coluna Marca com o GTIN. Devolve uma Série: "" = é da marca; senão o nome da
    outra marca (ex.: "J. SERRANO" num export da Montblanc = contratipo).
    - GTIN pesquisado (gtins.json) com marca preenchida manda: é a fonte mais confiável.
    - GTIN que aparece em pelo menos um anúncio com a Marca certa é da marca: os
      outros anúncios desse GTIN também são, mesmo que o vendedor tenha posto a
      marca da loja dele na coluna Marca (ex.: "ERIAN" vendendo Montblanc Explorer).
    - GTIN que só aparece com outra marca declarada é daquela outra marca, inclusive
      nos anúncios desse GTIN com a coluna Marca vazia.
    - Sem GTIN: vale a coluna Marca; vazia conta como da marca.
    """
    alvo = compacta(marca)
    declarada = df["marca_anuncio"].fillna("").str.strip()
    bate = declarada.map(lambda v: marca_bate(v, alvo))
    dono = declarada.where(~bate & (declarada != ""), "")
    for gtin, g in df[df["gtin"] != ""].groupby("gtin"):
        marca_pesq = (pesquisados or {}).get(gtin, {}).get("marca", "")
        if marca_pesq:
            dono[g.index] = "" if marca_bate(marca_pesq, alvo) else marca_pesq
        elif bate[g.index].any():
            dono[g.index] = ""
        else:
            outras = g[declarada[g.index] != ""]
            if not outras.empty:
                dono[g.index] = outras.groupby("marca_anuncio")["un"].sum().idxmax()
    # "J. SERRANO" e "J SERRANO", "LEN" e "L.E.N": mesma marca, grafia mais comum.
    preenchido = dono[dono != ""]
    if not preenchido.empty:
        grafia = preenchido.groupby(preenchido.map(compacta)).agg(lambda x: x.value_counts().index[0])
        dono = dono.map(lambda v: grafia[compacta(v)] if v else "")
    return dono


def identificar_marca(df, existentes=(), consultar=True, max_gtins=3):
    """
    Descobre de qual marca é o export, sem ninguém digitar:
    1. A marca dominante da coluna Marca, pesando por unidades vendidas (grafias como
       "MONT BLANC" e "MONTBLANC" contam juntas).
    2. A grafia oficial: pesquisa os GTINs mais vendidos dessa marca nas bases de
       produtos (gtin_info / Cosmos / Open Beauty Facts / UPCitemdb) e usa a marca
       como está escrita lá. Sem resposta, fica a grafia mais comum no arquivo.
    3. Se já existe marca cadastrada com a mesma grafia compacta, aponta qual é
       (para renomear para a oficial, se for diferente).
    As demais marcas da coluna Marca são listadas em `outras` — na consolidação elas
    viram "Outra marca: ...".
    Devolve dict com marca, grafia_arquivo, oficial, fonte, gtin, existente, outras,
    e `pesquisados` (GTINs consultados agora, para gravar).
    """
    d = df.assign(m=df["marca_anuncio"].fillna("").str.strip())
    d = d[d["m"] != ""].assign(c=lambda x: x["m"].map(compacta), p=lambda x: x["un"] + 1)
    if d.empty:
        return None
    pesos = d.groupby("c")["p"].sum().sort_values(ascending=False)
    dom = pesos.index[0]
    grafia = d[d["c"] == dom]["m"].value_counts().index[0]
    oficial = fonte = gtin_ok = None
    pesquisados = []
    gtins = (d[(d["c"] == dom) & (d["gtin"] != "")].groupby("gtin")["un"].sum()
             .sort_values(ascending=False).index[:max_gtins])
    token = os.environ.get("NUBI_COSMOS_TOKEN", "")
    for g in gtins:
        info = INFO_GTIN.get(g)
        if info is None and consultar:
            r, falhas, _ = consultar_gtin(g, token)
            if r:
                info = INFO_GTIN[g] = {"nome": r["nome"], "marca": r["marca"], "fonte": r["fonte"],
                                       "consultado_em": datetime.now().isoformat(timespec="seconds")}
                pesquisados.append(g)
        m = (info or {}).get("marca", "").split(",")[0].strip()
        if m and compacta(m) == dom:
            oficial, fonte, gtin_ok = m, (info or {}).get("fonte", ""), g
            break
    nome_final = oficial or grafia
    existente = next((e for e in existentes if compacta(e) == dom), None)
    # "Outras marcas" com a mesma regra da consolidação: GTIN + coluna Marca. Uma loja que
    # escreve o próprio nome na coluna Marca, mas usa o GTIN da marca, não entra aqui.
    dono = dono_do_anuncio(df, nome_final)
    fora = df.assign(dono=dono)[dono != ""]
    outras = [{"marca": nome_bonito(m), "un": int(g["un"].sum()), "anuncios": len(g)}
              for m, g in fora.groupby("dono")]
    outras.sort(key=lambda x: (-x["un"], -x["anuncios"]))
    return {"marca": chave_marca(nome_final), "grafia_arquivo": grafia, "oficial": oficial,
            "fonte": fonte, "gtin": gtin_ok, "existente": existente, "outras": outras,
            "pesquisados": pesquisados}


def consolidar(df, marca, cfg, info=None):
    """Devolve df com linha, volume, tipo, gênero, produto e confiança preenchidos."""
    df = df.copy()
    info = INFO_GTIN if info is None else info
    linhas = cfg.get(chave_marca(marca), {}).get("linhas", [])
    palavras_marca = palavras_da_marca(marca)
    tn = df["titulo"].map(normalizar)

    # Etapa 1 — ler o título.
    lido = pd.DataFrame([ler_texto(t, linhas, palavras_marca) for t in tn], index=df.index)
    for c in ("linha", "volume", "tipo", "genero"):
        df[c] = lido[c]

    # Especificação pesquisada do GTIN (gtins.json, preenchido por --pesquisar-gtin
    # ou à mão). É lida com as mesmas regras do título, mas vale mais que qualquer
    # anúncio: é o nome oficial do produto, não o que o vendedor digitou.
    pesquisados = {}
    for g in df.loc[df["gtin"] != "", "gtin"].unique():
        d = info.get(g) or {}
        if d.get("nome") or d.get("marca"):
            p = ler_texto(normalizar(d.get("nome", "")), linhas, palavras_marca)
            p["marca"] = d.get("marca", "")
            pesquisados[g] = p

    # Antes de tudo, separar o que não é da marca nem é perfume: esses anúncios
    # continuam no total, mas viram referências próprias e não votam nas etapas 2 e 3.
    dono = dono_do_anuncio(df, marca, pesquisados)
    outra = dono != ""
    df.loc[outra, "linha"] = dono[outra].map(nome_bonito)
    df.loc[outra, "tipo"] = TIPO_OUTRA
    nao_perf = (df["categoria"].fillna("") != "") & ~outra
    df.loc[nao_perf, "linha"] = df.loc[nao_perf, "categoria"]
    df.loc[nao_perf, "tipo"] = TIPO_FORA
    fora = outra | nao_perf
    df.loc[fora, ["volume", "genero"]] = "-"
    df["confianca"] = CONF_TITULO
    df.loc[fora, "confianca"] = "-"

    # Etapa 2 — o GTIN corrige o título.
    # Todos os anúncios do mesmo GTIN são o mesmo produto físico. Para linha, volume,
    # tipo e gênero, vale o que o anúncio que MAIS VENDEU UNIDADES diz (não o valor
    # mais frequente): um título com 1.200 unidades pesa mais que cinco com 2 cada.
    # É isso que junta "Club De Nuit Intense Da Armaf Ed" (título cortado, campeão
    # de vendas) com "...Club De Nuit Intense Man Eau De Toilette 105ml".
    # "-" e "Outros" não votam, mas o vencedor é aplicado ao grupo inteiro.
    # Se o GTIN foi pesquisado, a especificação pesquisada vence a votação.
    # Quando os títulos do mesmo GTIN discordam entre si, o grupo fica marcado como
    # dúvida — é a lista que o --pesquisar-gtin vai conferir.
    com_gtin = df[(df["gtin"] != "") & ~fora]
    for gtin, grupo in com_gtin.groupby("gtin"):
        p = pesquisados.get(gtin, {})
        divergente = any(grupo[c][~grupo[c].isin(NEUTROS)].nunique() > 1
                         for c in ("linha", "volume", "tipo"))
        for coluna in ("linha", "volume", "tipo", "genero"):
            vencedor = p.get(coluna) if p.get(coluna) not in NEUTROS | {None} else None
            if vencedor is None:
                vencedor = _mais_vendido(grupo, coluna)
            if vencedor is not None:
                df.loc[grupo.index, coluna] = vencedor
        if df.at[grupo.index[0], "linha"] == "Outros":
            conf = DUV_LINHA
        elif p.get("linha") not in NEUTROS | {None}:
            conf = CONF_PESQ
        elif divergente:
            conf = DUV_DIVERG
        else:
            conf = CONF_GTIN
        df.loc[grupo.index, "confianca"] = conf

    # Etapa 3 — preencher o que sobrou vazio.
    # 3a. Tipo não escrito no título e sem GTIN que resolva ("EDT?"): recebe o tipo
    #     de perfume (EDT/EDP/EDC) que mais vendeu na mesma linha e volume. Assim um
    #     "Montblanc Explorer 100ml" solto vira EDP, como os anúncios que dizem o tipo.
    #     Sem referência para copiar, fica EDT.
    for _, grupo in df[~fora & (df["volume"] != "-")].groupby(["linha", "volume"]):
        faltando = grupo.index[grupo["tipo"] == TIPO_PADRAO]
        if len(faltando):
            vencedor = _mais_vendido(grupo[grupo["tipo"].isin(["EDT", "EDP", "EDC"])], "tipo")
            if vencedor is not None:
                df.loc[faltando, "tipo"] = vencedor
    df.loc[df["tipo"] == TIPO_PADRAO, "tipo"] = "EDT"
    # 3b. Volume: anúncio sem "ml" no título e sem GTIN que resolva recebe o volume
    #     que mais vendeu entre os anúncios da mesma linha e tipo.
    for _, grupo in df[~fora].groupby(["linha", "tipo"]):
        faltando = grupo.index[grupo["volume"] == "-"]
        if len(faltando):
            vencedor = _mais_vendido(grupo, "volume")
            if vencedor is not None:
                df.loc[faltando, "volume"] = vencedor
    # 3c. Gênero não escrito: o que mais vendeu na mesma linha.
    for _, grupo in df[~fora].groupby("linha"):
        faltando = grupo.index[grupo["genero"] == "-"]
        if len(faltando):
            vencedor = _mais_vendido(grupo, "genero")
            if vencedor is not None:
                df.loc[faltando, "genero"] = vencedor

    marca_txt = nome_bonito(marca)
    df["produto"] = [
        f"{marca_txt} {l} (não perfume)" if t == TIPO_FORA else
        f"Outra marca: {l}" if t == TIPO_OUTRA else
        re.sub(r"\s+", " ", f"{marca_txt} {l} {t} {v if v != '-' else ''}").strip()
        for l, t, v in zip(df["linha"], df["tipo"], df["volume"])
    ]
    return df


# ---------------------------------------------------------------------------
# Banco de dados
# ---------------------------------------------------------------------------

CAMPOS_ANUNCIO = ["titulo", "vendedor", "vendedor_id", "marca_anuncio", "categoria", "produto", "linha", "volume", "tipo",
                  "genero", "confianca", "bruto",
                  "gtin", "sku", "un", "fat", "preco", "un_hist", "fat_hist", "dias_pub",
                  "exposicao", "catalogo", "full", "flex", "internacional", "loja_oficial",
                  "frete_gratis"]


def abrir_banco():
    DADOS.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(BANCO)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            marca TEXT NOT NULL, inicio TEXT NOT NULL, fim TEXT NOT NULL,
            dias INTEGER NOT NULL, arquivo TEXT, hash TEXT UNIQUE, importado_em TEXT);
        CREATE TABLE IF NOT EXISTS anuncios(
            snapshot_id INTEGER NOT NULL REFERENCES snapshots(id),
            titulo TEXT, vendedor TEXT, vendedor_id TEXT, marca_anuncio TEXT, categoria TEXT, produto TEXT, linha TEXT,
            volume TEXT, tipo TEXT, genero TEXT, confianca TEXT, bruto TEXT, gtin TEXT, sku TEXT, un INTEGER, fat REAL, preco REAL,
            un_hist INTEGER, fat_hist REAL, dias_pub INTEGER, exposicao TEXT,
            catalogo INTEGER, full INTEGER, flex INTEGER, internacional INTEGER,
            loja_oficial INTEGER, frete_gratis INTEGER);
        CREATE INDEX IF NOT EXISTS ix_anuncios_snap ON anuncios(snapshot_id);
    """)
    # Banco criado por uma versão anterior: acrescenta as colunas que faltam.
    existentes = {r[1] for r in con.execute("PRAGMA table_info(anuncios)")}
    for c in ("marca_anuncio", "categoria", "genero", "confianca", "bruto"):
        if c not in existentes:
            con.execute(f"ALTER TABLE anuncios ADD COLUMN {c} TEXT")
    con.commit()
    return con


class RepoLocal:
    """
    Onde os dados moram no uso local: SQLite em dados/base.db e os arquivos
    marcas.json / gtins.json. A versão web (nubi_web.py) tem uma classe com os
    mesmos métodos que fala com o Supabase.
    """

    def __init__(self):
        self.con = abrir_banco()

    def fechar(self):
        self.con.close()

    def marcas(self):
        return [m for (m,) in self.con.execute("SELECT DISTINCT marca FROM snapshots ORDER BY marca")]

    def snapshot_por_hash(self, hash_):
        r = self.con.execute("SELECT importado_em, marca, inicio, fim FROM snapshots WHERE hash=?",
                             (hash_,)).fetchone()
        return dict(zip(("importado_em", "marca", "inicio", "fim"), r)) if r else None

    def snapshots(self, marca=None):
        sql = "SELECT * FROM snapshots" + (" WHERE marca=?" if marca else "") + \
              " ORDER BY marca, fim, inicio, id"
        return pd.read_sql(sql, self.con, params=(marca,) if marca else ())

    def gravar_snapshot(self, marca, inicio, fim, dias, arquivo, hash_, df):
        con = self.con
        # Mesmo marca+período vindo num arquivo diferente (novo export): substitui o antigo.
        antigos = con.execute("SELECT id FROM snapshots WHERE marca=? AND inicio=? AND fim=?",
                              (marca, inicio, fim)).fetchall()
        for (sid,) in antigos:
            con.execute("DELETE FROM anuncios WHERE snapshot_id=?", (sid,))
            con.execute("DELETE FROM snapshots WHERE id=?", (sid,))
        cur = con.execute(
            "INSERT INTO snapshots(marca, inicio, fim, dias, arquivo, hash, importado_em) "
            "VALUES (?,?,?,?,?,?,?)",
            (marca, inicio, fim, dias, arquivo, hash_, datetime.now().isoformat(timespec="seconds")))
        sid = cur.lastrowid
        d = df[CAMPOS_ANUNCIO].copy()
        d["bruto"] = d["bruto"].map(lambda x: json.dumps(x, ensure_ascii=False) if isinstance(x, dict) else x)
        linhas = [(sid, *r) for r in d.itertuples(index=False, name=None)]
        con.executemany(f"INSERT INTO anuncios(snapshot_id, {', '.join(CAMPOS_ANUNCIO)}) "
                        f"VALUES ({', '.join('?' * (len(CAMPOS_ANUNCIO) + 1))})", linhas)
        con.commit()
        return len(antigos) > 0

    def anuncios(self, sid):
        """Anúncios de um período, com `rid` (identificador da linha para atualizar)."""
        df = pd.read_sql("SELECT rowid AS rid, * FROM anuncios WHERE snapshot_id=?",
                         self.con, params=(int(sid),))
        df["bruto"] = df["bruto"].map(lambda x: json.loads(x) if isinstance(x, str) and x else {})
        return df

    def atualizar_consolidacao(self, df):
        self.con.executemany(
            "UPDATE anuncios SET produto=?, linha=?, volume=?, tipo=?, genero=?, confianca=? WHERE rowid=?",
            list(df[CAMPOS_CONSOLIDACAO + ["rid"]].itertuples(index=False, name=None)))
        self.con.commit()

    def un_por_produto(self, sids):
        """Unidades por produto em cada período (para a aba Histórico)."""
        ph = ",".join("?" * len(sids))
        return pd.read_sql(f"SELECT snapshot_id, produto, SUM(un) AS un FROM anuncios "
                           f"WHERE snapshot_id IN ({ph}) GROUP BY snapshot_id, produto",
                           self.con, params=[int(x) for x in sids])

    def renomear_marca(self, antiga, nova):
        self.con.execute("UPDATE snapshots SET marca=? WHERE marca=?", (nova, antiga))
        self.con.commit()

    def carregar_config(self):
        return carregar_config()

    def salvar_config(self, cfg, marca=None, apagar=None):
        salvar_config(cfg)

    def carregar_gtins(self):
        return carregar_gtins()

    def salvar_gtins(self, info, alterados=None):
        salvar_gtins(info)


CAMPOS_CONSOLIDACAO = ["produto", "linha", "volume", "tipo", "genero", "confianca"]


def preparar(df):
    """Anúncios lidos do banco: troca vazios (None) pelos valores que a consolidação espera."""
    for c in ("gtin", "marca_anuncio", "categoria", "confianca", "titulo", "vendedor"):
        if c in df.columns:
            df[c] = df[c].fillna("")
    if "genero" in df.columns:
        df["genero"] = df["genero"].fillna("-")
    return df


def reconsolidar(repo, cfg, marcas=None):
    """
    Refaz a consolidação do histórico com a configuração atual — assim uma correção
    nas linhas (marcas.json) ou num GTIN vale também para os períodos já importados.
    `marcas`: só estas marcas (padrão: todas).
    """
    snaps = repo.snapshots()
    for _, s in snaps.iterrows():
        if marcas and s["marca"] not in marcas:
            continue
        df = preparar(repo.anuncios(s["id"]))
        if df.empty:
            continue
        garantir_config(cfg, s["marca"], df, repo)
        novo = consolidar(df, s["marca"], cfg)
        mudou = (novo[CAMPOS_CONSOLIDACAO].astype(str) != df[CAMPOS_CONSOLIDACAO].astype(str)).any(axis=1)
        if mudou.any():
            repo.atualizar_consolidacao(novo[mudou])


# ---------------------------------------------------------------------------
# Pesquisa de GTIN: buscar a especificação oficial quando o agrupamento está em dúvida
# ---------------------------------------------------------------------------

COMANDO_PESQUISA = "python nubi.py --pesquisar-gtin"


def link_pesquisa(gtin):
    return "https://www.google.com/search?q=" + urllib.parse.quote(f"{gtin} perfume")


def carregar_gtins():
    if not ARQ_GTINS.exists():
        return {}
    try:
        bruto = json.loads(ARQ_GTINS.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ErroArquivo(f"gtins.json está com erro de digitação (linha {e.lineno}, "
                          f"coluna {e.colno}). Corrija e rode de novo.")
    return {re.sub(r"\D", "", k): v for k, v in bruto.items() if isinstance(v, dict)}


def salvar_gtins(info):
    """Um GTIN por linha, para dar para corrigir à mão."""
    linhas = [f"  {json.dumps(g)}: {json.dumps(info[g], ensure_ascii=False)}" for g in sorted(info)]
    ARQ_GTINS.write_text("{\n" + ",\n".join(linhas) + "\n}\n", encoding="utf-8")


class SemConexao(Exception):
    pass


class LimiteAtingido(Exception):
    pass


def _get_json(url, cabecalhos=None):
    req = urllib.request.Request(url, headers={
        "User-Agent": "nubi/1.0 (explorador de anuncios)", "Accept": "application/json",
        **(cabecalhos or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        if e.code == 429:
            raise LimiteAtingido()
        raise SemConexao(f"erro {e.code}")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        raise SemConexao(e.__class__.__name__)


def fonte_cosmos(gtin, token):
    """Cosmos (Bluesoft): melhor base para produtos vendidos no Brasil. Precisa de token."""
    d = _get_json(f"https://api.cosmos.bluesoft.com.br/gtins/{gtin}.json", {"X-Cosmos-Token": token})
    if not d or not d.get("description"):
        return None
    return {"nome": d["description"], "marca": (d.get("brand") or {}).get("name", "")}


def fonte_open_beauty(gtin):
    """Open Beauty Facts: base aberta de cosméticos e perfumes, sem cadastro."""
    d = _get_json(f"https://world.openbeautyfacts.org/api/v2/product/{gtin}.json"
                  "?fields=product_name,generic_name,brands,quantity")
    if not d or d.get("status") != 1:
        return None
    p = d.get("product") or {}
    nome = " ".join(str(p.get(k) or "").strip()
                    for k in ("brands", "product_name", "generic_name", "quantity")).strip()
    if not nome:
        return None
    return {"nome": re.sub(r"\s+", " ", nome), "marca": str(p.get("brands") or "").split(",")[0].strip()}


def fonte_upcitemdb(gtin):
    """UPCitemdb: base internacional, grátis até ~100 consultas por dia."""
    d = _get_json(f"https://api.upcitemdb.com/prod/trial/lookup?upc={gtin}")
    itens = (d or {}).get("items") or []
    if not itens:
        return None
    it = itens[0]
    nome = " ".join(str(it.get(k) or "").strip() for k in ("title", "size")).strip()
    return {"nome": nome, "marca": str(it.get("brand") or "")} if nome else None


def consultar_gtin(gtin, token=""):
    """Tenta as bases em ordem. Devolve (resultado ou None, lista de falhas de conexão)."""
    fontes = [("Cosmos", lambda g: fonte_cosmos(g, token))] if token else []
    fontes += [("Open Beauty Facts", fonte_open_beauty), ("UPCitemdb", fonte_upcitemdb)]
    falhas = []
    for nome, f in fontes:
        try:
            r = f(gtin)
        except LimiteAtingido:
            falhas.append(f"{nome}: limite de consultas do dia")
            continue
        except SemConexao as e:
            falhas.append(f"{nome}: sem resposta ({e})")
            continue
        if r:
            r["fonte"] = nome
            return r, falhas, len(fontes)
    # Se alguma base não respondeu, "não encontrado" ainda não é definitivo.
    return None, falhas, len(fontes)


def gtins_em_duvida(repo, marca=None):
    """GTINs cujo agrupamento está em dúvida, no período mais recente de cada marca."""
    snaps = repo.snapshots(marca)
    saida = []
    for m, grupo in snaps.groupby("marca"):
        df = preparar(repo.anuncios(grupo.iloc[-1]["id"]))
        d = df[(df["gtin"] != "") & df["confianca"].str.startswith("Dúvida")]
        for gtin, un in d.groupby("gtin")["un"].sum().items():
            saida.append((gtin, m, int(un)))
    return sorted(saida, key=lambda x: -x[2])


REPESQUISAR_DIAS = 30


def precisa_pesquisar(gtin):
    """Nunca pesquisado, ou "não encontrado" há mais de 30 dias (as bases crescem)."""
    d = INFO_GTIN.get(gtin)
    if d is None:
        return True
    if d.get("fonte") != "não encontrado":
        return False
    try:
        quando = datetime.fromisoformat(str(d.get("consultado_em", ""))[:19])
    except ValueError:
        return True
    return (datetime.now() - quando).days >= REPESQUISAR_DIAS


def pesquisar_gtins(repo, limite, lista=None, marca=None, prazo=None):
    """
    Pesquisa os GTINs (em dúvida, ou os da lista) e grava o resultado.
    prazo: time.monotonic() limite para parar (a função da nuvem tem tempo máximo).
    Devolve um resumo: pendentes, pesquisados, encontrados, nao_encontrados, sem_resposta, marcas.
    """
    res = {"pendentes": 0, "pesquisados": 0, "encontrados": 0, "nao_encontrados": 0, "sem_resposta": 0,
           "marcas": set()}
    if lista:
        alvos = [(normalizar_gtin(g) or re.sub(r"\D", "", g), "", 0) for g in lista]
    else:
        alvos = [a for a in gtins_em_duvida(repo, marca) if precisa_pesquisar(a[0])]
    res["pendentes"] = len(alvos)
    if not alvos:
        avisar("\n  Nenhum GTIN em dúvida esperando pesquisa.")
        return res
    token = (ARQ_TOKEN_COSMOS.read_text(encoding="utf-8").strip() if ARQ_TOKEN_COSMOS.exists()
             else os.environ.get("NUBI_COSMOS_TOKEN", ""))
    alterados = []
    lote = alvos[:limite]
    if lista:
        avisar(f"Pesquisando {len(lote)} GTIN(s):")
    else:
        avisar(f"Pesquisando {len(lote)} GTIN(s) em dúvida (de {len(alvos)}), "
              f"dos que mais vendem para os que menos vendem:")
    sem_rede = 0
    for gtin, m_gtin, _ in lote:
        if prazo and time.monotonic() > prazo:
            avisar("    Tempo desta rodada acabou; o resto fica para a próxima.")
            break
        res["pesquisados"] += 1
        r, falhas, n_fontes = consultar_gtin(gtin, token)
        agora = datetime.now().isoformat(timespec="seconds")
        if r:
            INFO_GTIN[gtin] = {"nome": r["nome"], "marca": r["marca"], "fonte": r["fonte"],
                               "consultado_em": agora}
            alterados.append(gtin)
            res["encontrados"] += 1
            if m_gtin:
                res["marcas"].add(m_gtin)
            avisar(f"    {gtin}  {r['nome']}  ({r['fonte']})")
            sem_rede = 0
        elif len(falhas) == n_fontes:
            avisar(f"    {gtin}  sem resposta das bases ({'; '.join(falhas)})")
            res["sem_resposta"] += 1
            sem_rede += 1
            if sem_rede >= 3:
                avisar("    Sem conexão com as bases de GTIN agora. Tente de novo mais tarde.")
                break
        elif falhas:
            res["sem_resposta"] += 1
            avisar(f"    {gtin}  não encontrado, mas nem todas as bases responderam "
                  f"({'; '.join(falhas)}). Fica para a próxima pesquisa.")
            sem_rede = 0
        else:
            INFO_GTIN[gtin] = {"nome": "", "marca": "", "fonte": "não encontrado", "consultado_em": agora}
            alterados.append(gtin)
            res["nao_encontrados"] += 1
            avisar(f"    {gtin}  não encontrado nas bases — confira: {link_pesquisa(gtin)}")
            sem_rede = 0
        time.sleep(0.5)
    repo.salvar_gtins(INFO_GTIN, alterados)
    if len(alvos) > res["pesquisados"]:
        avisar(f"    Faltam {len(alvos) - res['pesquisados']}. Pesquise de novo para continuar.")
    avisar("    Resultados gravados (gtins.json no computador; aba Dúvidas na web). Se algum nome "
           "estiver errado, ou não foi encontrado, corrija à mão e reprocesse.")
    return res


# ---------------------------------------------------------------------------
# Marca e período: pelo nome do arquivo ou perguntando
# ---------------------------------------------------------------------------

class SemTerminal(Exception):
    pass


def data_valida(txt):
    try:
        return datetime.strptime(txt.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def perguntar(msg, padrao=""):
    try:
        resp = input(f"    {msg}" + (f" [{padrao}]" if padrao else "") + ": ").strip()
    except EOFError:
        raise SemTerminal()
    return resp or padrao


def marca_e_periodo(caminho, sugestao, informado=None):
    """
    Devolve (marca, inicio, fim) como (str, date, date), ou None para pular o arquivo.
    Ordem: nome do arquivo -> --marca/--inicio/--fim da linha de comando -> perguntar.
    """
    m = PADRAO_NOME.match(caminho.stem)
    if m:
        ini, fim = data_valida(m.group(2)), data_valida(m.group(3))
        if ini and fim and ini <= fim:
            # A marca do conteúdo (coluna Marca + GTIN) vale mais que a do nome do arquivo.
            return chave_marca(sugestao or m.group(1).replace("_", " ")), ini, fim
    if informado and informado[1] and informado[2]:
        marca = chave_marca(sugestao or informado[0] or "")
        if marca:
            return marca, informado[1], informado[2]
    avisar("    O nome do arquivo não traz marca e período "
          "(padrão MARCA__AAAA-MM-DD_AAAA-MM-DD.csv).")
    try:
        marca = ""
        for _ in range(3):
            marca = chave_marca(perguntar("Marca", chave_marca(sugestao)))
            if marca:
                break
        if not marca:
            avisar("    Marca não informada. Arquivo pulado.")
            return None
        ini = fim = None
        for _ in range(3):
            ini = data_valida(perguntar("Data inicial (AAAA-MM-DD)"))
            if ini:
                break
            avisar("    Data inválida. Use o formato AAAA-MM-DD, ex.: 2026-08-01")
        for _ in range(3):
            if not ini:
                break
            fim = data_valida(perguntar("Data final (AAAA-MM-DD)"))
            if fim and fim >= ini:
                break
            avisar("    Data inválida ou anterior à inicial. Use AAAA-MM-DD.")
            fim = None
        if not (ini and fim):
            avisar("    Datas não informadas corretamente. Arquivo pulado.")
            return None
        return marca, ini, fim
    except SemTerminal:
        avisar("    Sem terminal para perguntar. Renomeie o arquivo no padrão "
              "MARCA__AAAA-MM-DD_AAAA-MM-DD.csv. Arquivo pulado.")
        return None


def importar(repo, cfg, caminho, informado=None):
    avisar(f"\n  {caminho.name}")
    return importar_dados(repo, cfg, caminho.name, caminho.read_bytes(),
                          lambda sugestao: marca_e_periodo(caminho, sugestao, informado))


def importar_dados(repo, cfg, nome, dados, obter_marca_periodo):
    """
    Importa um CSV (conteúdo em bytes). `obter_marca_periodo(sugestao)` devolve
    (marca, inicio, fim) ou None — pelo nome do arquivo, pela linha de comando,
    perguntando no terminal ou pelo formulário da página.
    """
    hash_ = hashlib.sha256(dados).hexdigest()
    ja = repo.snapshot_por_hash(hash_)
    if ja:
        quando = datetime.fromisoformat(str(ja["importado_em"])[:19]).strftime("%d/%m/%Y %H:%M")
        avisar(f"    Já importado em {quando} ({ja['marca']}, {fmt_data(str(ja['inicio']))} a "
               f"{fmt_data(str(ja['fim']))}). Pulado.")
        return None
    try:
        df, sugestao = ler_csv(dados)
    except ErroArquivo as e:
        avisar(f"    Não importado: {e}.")
        return None
    avisar(f"    {fmt_int(len(df))} anúncios · {fmt_int(df['un'].sum())} unidades")
    # A marca vem do próprio arquivo (coluna Marca + grafia oficial pelo GTIN).
    existentes = sorted(set(cfg) | set(repo.marcas()))
    ident = identificar_marca(df, existentes)
    if ident:
        sugestao = ident["marca"]
        if ident["pesquisados"]:
            repo.salvar_gtins(INFO_GTIN, ident["pesquisados"])
    mp = obter_marca_periodo(sugestao)
    if not mp:
        return None
    marca, ini, fim = mp
    if ident and ident["oficial"] and compacta(marca) == compacta(ident["marca"]):
        marca = ident["marca"]    # grafia oficial vence a digitada/do nome do arquivo
    # Mesma marca já cadastrada com outra grafia ("MONT BLANC" x "MONTBLANC"): renomeia.
    for antiga in existentes:
        if antiga != marca and compacta(antiga) == compacta(marca):
            repo.renomear_marca(antiga, marca)
            if antiga in cfg:
                cfg[marca] = cfg.pop(antiga)
                repo.salvar_config(cfg, marca, apagar=antiga)
            avisar(f"    Marca {antiga} renomeada para {marca} (grafia oficial).")
            reconsolidar(repo, cfg, [marca])
    dias = (fim - ini).days + 1          # inclusive nas pontas: 01/08 a 16/09 = 47 dias
    garantir_config(cfg, marca, df, repo)
    df = consolidar(df, marca, cfg)
    substituiu = repo.gravar_snapshot(marca, ini.isoformat(), fim.isoformat(), dias, nome, hash_, df)
    if substituiu:
        avisar("    (substituiu uma importação anterior do mesmo período)")
    avisar(f"    OK: {marca} · {ini:%d/%m/%Y} a {fim:%d/%m/%Y} ({dias} dias) · "
           f"{df['produto'].nunique()} referências")
    return marca


# ---------------------------------------------------------------------------
# Excel: estilos e ajudantes
# ---------------------------------------------------------------------------

AZUL = "1F3864"
FONTE = Font(name="Arial", size=10)
FONTE_B = Font(name="Arial", size=10, bold=True)
FONTE_CAB = Font(name="Arial", size=10, bold=True, color="FFFFFF")
FONTE_TIT = Font(name="Arial", size=14, bold=True, color=AZUL)
FONTE_ALERTA = Font(name="Arial", size=11, bold=True, color="C00000")
FONTE_NOTA = Font(name="Arial", size=9, italic=True, color="595959")
FILL_CAB = PatternFill("solid", fgColor=AZUL)
FILL_TOTAL = PatternFill("solid", fgColor="F2F2F2")
FILL_VERDE = PatternFill("solid", fgColor="C6EFCE")
_LADO = Side(style="thin", color="BFBFBF")
BORDA = Border(left=_LADO, right=_LADO, top=_LADO, bottom=_LADO)

MOEDA = '"R$ "#,##0'
MOEDA2 = '"R$ "#,##0.00'
PCT = "0.0%"
DEC = "#,##0.0"
INT = "#,##0"
TXT = "@"
VEZES = '0.0"x"'


def cel(ws, r, c, v, fmt=None, fonte=FONTE, borda=True, fill=None, alinhar=None):
    x = ws.cell(row=r, column=c, value=v)
    x.font = fonte
    if fmt:
        x.number_format = fmt
    if borda:
        x.border = BORDA
    if fill:
        x.fill = fill
    if alinhar:
        x.alignment = alinhar
    return x


def cabecalho(ws, r, colunas):
    """colunas: lista de (título, formato, largura)."""
    for c, (tit, _, larg) in enumerate(colunas, 1):
        cel(ws, r, c, tit, fonte=FONTE_CAB, fill=FILL_CAB,
            alinhar=Alignment(horizontal="center", vertical="center", wrap_text=True))
        if larg:
            ws.column_dimensions[get_column_letter(c)].width = larg
    ws.row_dimensions[r].height = 42


def linha_dados(ws, r, colunas, valores, total=False):
    for c, ((_, fmt, _), v) in enumerate(zip(colunas, valores), 1):
        cel(ws, r, c, v, fmt=fmt, fonte=FONTE_B if total else FONTE,
            fill=FILL_TOTAL if total else None)


def tabela(ws, r0, colunas, linhas, total=None):
    """Escreve cabeçalho + dados (+ TOTAL). `linhas` = lista de funções r -> valores."""
    cabecalho(ws, r0, colunas)
    r = r0
    for fazer in linhas:
        r += 1
        linha_dados(ws, r, colunas, fazer(r))
    ult = max(r, r0 + 1)
    ws.freeze_panes = ws.cell(row=r0 + 1, column=2)
    ws.auto_filter.ref = f"A{r0}:{get_column_letter(len(colunas))}{ult}"
    if total:
        r += 1
        linha_dados(ws, r, colunas, total(r), total=True)
    return r


def nota(ws, r, texto, fonte=FONTE_NOTA):
    cel(ws, r, 1, texto, fonte=fonte, borda=False)


def col(i):
    return get_column_letter(i)


# Aba Anúncios: é a base de onde as outras abas puxam por fórmula.
COLS_ANUNCIOS = [
    ("produto", "Produto (consolidado)", TXT, 46),
    ("cat", "Categoria", TXT, 13),
    ("linha", "Linha", TXT, 24),
    ("tipo", "Tipo", TXT, 11),
    ("volume", "Volume", TXT, 9),
    ("cat_l1", "Categoria L1", TXT, 18),
    ("confianca", "Confiança do agrupamento", TXT, 26),
    ("titulo", "Título do anúncio", TXT, 60),
    ("cod", "Cód. vendedor", TXT, 10),
    ("vendedor", "Vendedor", TXT, 26),
    ("marca_anuncio", "Marca no anúncio", TXT, 16),
    ("gtin", "GTIN", TXT, 16),
    ("sku", "SKU", TXT, 16),
    ("un", "Un. vendidas", INT, 11),
    ("fat", "Faturamento", MOEDA, 14),
    ("preco", "Último preço", MOEDA2, 12),
    ("receita", "Preço × un.", MOEDA, 14),
    ("un_hist", "Un. históricas", INT, 11),
    ("fat_hist", "Faturamento histórico", MOEDA, 15),
    ("dias_pub", "Dias publicado", INT, 10),
    ("exposicao", "Exposição", TXT, 12),
    ("catalogo", "Catálogo", INT, 9),
    ("full", "FULL", INT, 7),
    ("flex", "FLEX", INT, 7),
    ("internacional", "Internacional", INT, 12),
    ("loja_oficial", "Loja oficial", INT, 9),
    ("frete_gratis", "Frete grátis", INT, 9),
    ("vendedor_id", "ID do vendedor", TXT, 20),
]
IDX_AN = {k: i + 1 for i, (k, *_) in enumerate(COLS_ANUNCIOS)}


def AN(chave):
    """Referência de coluna inteira na aba Anúncios."""
    L = col(IDX_AN[chave])
    return f"'Anúncios'!${L}:${L}"


R_DIAS = "'Resumo'!$B$6"
R_UN = "'Resumo'!$B$8"
FONTE_LINK = Font(name="Arial", size=10, color="0563C1", underline="single")


def faixa_preco(ref):
    """Fórmula que classifica um preço em faixas fixas (para filtrar)."""
    return (f'=IF({ref}<=0,"-",IF({ref}<100,"até R$ 99",IF({ref}<200,"R$ 100–199",'
            f'IF({ref}<300,"R$ 200–299",IF({ref}<500,"R$ 300–499","R$ 500+")))))')


def link_google(gtin):
    return f'=HYPERLINK("{link_pesquisa(gtin)}","pesquisar")'


# ---------------------------------------------------------------------------
# Excel: planilha da marca
# ---------------------------------------------------------------------------

def codigos_vendedor(df):
    """V01, V02… por ordem de volume. Nome exibido = o mais frequente para aquele ID."""
    g = df.groupby("vendedor_id").agg(un=("un", "sum"), fat=("fat", "sum"),
                                      nome=("vendedor", lambda s: s.value_counts().index[0]))
    g = g.sort_values(["un", "fat", "nome"], ascending=[False, False, True], kind="mergesort")
    larg = max(2, len(str(len(g))))
    g["cod"] = [f"V{i:0{larg}d}" for i in range(1, len(g) + 1)]
    return g


def atributos_produto(df):
    """Uma linha por produto com os campos de filtro (categoria, gênero, volume, GTINs…)."""
    out = df.groupby("produto").agg(linha=("linha", "first"), tipo=("tipo", "first"),
                                    volume=("volume", "first"), un=("un", "sum"), fat=("fat", "sum"),
                                    vendedores=("vendedor_id", "nunique"))
    def moda(coluna):
        """Valor da coluna que mais vendeu dentro de cada produto."""
        v = df.assign(p=df["un"] + 0.001).groupby(["produto", coluna])["p"].sum()
        return v.groupby(level=0).idxmax().map(lambda x: x[1])
    out["cat"] = moda("cat") if "cat" in df.columns else out["tipo"].map(categoria_de)
    out["cat_l1"] = moda("cat_l1") if "cat_l1" in df.columns else "-"
    out["marca"] = moda("marca_prod") if "marca_prod" in df.columns else "-"
    peso = df.assign(p=df["un"] + 1).groupby(["produto", "confianca"])["p"].sum()
    out["confianca"] = peso.groupby(level=0).idxmax().map(lambda x: x[1])
    # Cada GTIN é um produto físico de um tamanho só; a referência junta os GTINs dele.
    out["gtins"] = df[df["gtin"] != ""].groupby("produto")["gtin"].nunique().reindex(out.index).fillna(0).astype(int)
    return out.sort_values(["un", "fat"], ascending=False, kind="mergesort")


def aba_resumo(ws, marca, snap, n_vend, n_prod, n_gtin, n_duvida, n_oport):
    ws.title = "Resumo"
    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 58
    cel(ws, 1, 1, f"Explorador de anúncios — {nome_bonito(marca)}", fonte=FONTE_TIT, borda=False)
    cel(ws, 2, 1, "Números do mercado inteiro (todos os vendedores), não da sua loja.",
        fonte=FONTE_ALERTA, borda=False)
    cel(ws, 3, 1, f"Período: {fmt_data(str(snap['inicio']))} a {fmt_data(str(snap['fim']))} "
                  f"({snap['dias']} dias) · arquivo {snap['arquivo']}", borda=False)

    v_fim, p_fim, g_fim = n_vend + 1, n_prod + 1, n_gtin + 1
    vend = lambda L: f"'Vendedores'!${L}$2:${L}${max(v_fim, 2)}"
    A = "'Anúncios'!$A:$A"
    indicadores = [
        ("Dias no período", snap["dias"], INT, "Ritmos por dia usam este número."),
        ("Anúncios ativos", f"=COUNTA({A})-1", INT, ""),
        ("Unidades no período", f"=SUM({AN('un')})", INT, ""),
        ("Faturamento", f"=SUM({AN('fat')})", MOEDA, "Aproximado: a plataforma arredonda em faixas."),
        ("Preço médio", "=IFERROR(B9/B8,0)", MOEDA2, "Faturamento ÷ unidades (aproximado)."),
        ("Giro/dia (unidades)", "=IFERROR(B8/B6,0)", DEC, ""),
        ("Projeção 30 dias (unidades)", "=B11*30", INT, "No ritmo atual."),
        ("Projeção anual (unidades)", "=B11*365", INT, "No ritmo atual."),
        ("Projeção anual (R$)", "=IFERROR(B9/B6,0)*365", MOEDA, "No ritmo atual."),
        ("Vendedores distintos", f"=COUNTA({vend('A')})", INT, ""),
        ("Referências", f"=COUNTA('Produtos'!$A$2:$A${max(p_fim, 2)})", INT,
         "Produtos reais depois de consolidar os anúncios."),
        ("GTINs distintos", f"=COUNTA('GTINs'!$A$2:$A${max(g_fim, 2)})", INT, ""),
        ("Vendedores com loja oficial", f'=COUNTIFS({vend("M")},">0")', INT, ""),
        ("% de anúncios em catálogo", f"=IFERROR(SUM({AN('catalogo')})/B7,0)", PCT, ""),
        ("% de anúncios FULL", f"=IFERROR(SUM({AN('full')})/B7,0)", PCT, ""),
        ("Unidades de outras marcas", f'=SUMIFS({AN("un")},{AN("tipo")},"{TIPO_OUTRA}")', INT,
         "Coluna Marca e GTIN apontam outra marca (contratipo ou cadastro errado)."),
        ("Unidades fora de perfumaria", f'=SUMIFS({AN("un")},{AN("tipo")},"{TIPO_FORA}")', INT,
         "Canetas, acessórios etc. que vieram no export da marca."),
        ("GTINs em dúvida", n_duvida, INT,
         f"Títulos do mesmo GTIN não batem (aba Dúvidas). Para pesquisar: {COMANDO_PESQUISA}"
         if n_duvida else "Nenhum: todos os GTINs agruparam sem conflito."),
    ]
    cols = [("Indicador", None, None), ("Valor", None, None), ("Observação", None, None)]
    cabecalho(ws, 5, cols)
    ws.merge_cells("C5:D5")
    for i, (rot, val, fmt, obs) in enumerate(indicadores):
        r = 6 + i
        cel(ws, r, 1, rot, fonte=FONTE_B)
        cel(ws, r, 2, val, fmt=fmt)
        cel(ws, r, 3, obs, fonte=FONTE_NOTA)
        cel(ws, r, 4, None)
        ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)

    r0 = 6 + len(indicadores) + 2
    cel(ws, r0 - 1, 1, "Concentração entre vendedores", fonte=FONTE_B, borda=False)
    cols = [("Faixa", None, None), ("Vendedores", INT, None), ("Unidades", INT, None),
            ("Share do volume", PCT, None)]
    cabecalho(ws, r0, cols)
    faixas = [("Top 1", 1), ("Top 3", 3), ("Top 5", 5), ("Top 10", 10), ("Top 20", 20), ("Todos", None)]
    for i, (rot, n) in enumerate(faixas):
        r = r0 + 1 + i
        if n:
            fim = n + 1
            vals = [rot, f"=MIN({n},$B$15)", f"=SUM('Vendedores'!$C$2:$C${fim})", f"=IFERROR(C{r}/$B$8,0)"]
        else:
            vals = [rot, "=$B$15", f"=SUM({vend('C')})", f"=IFERROR(C{r}/$B$8,0)"]
        linha_dados(ws, r, cols, vals, total=(n is None))

    # As 5 melhores notas da aba Oportunidades (que já vem ordenada pela nota).
    r0 = r0 + len(faixas) + 3
    if n_oport:
        cel(ws, r0 - 1, 1, "Melhores oportunidades (detalhes na aba Oportunidades)", fonte=FONTE_B, borda=False)
        cols = [("Produto", None, None), ("Nota (0–100)", INT, None), ("Giro/dia", DEC, None),
                ("Sinais", None, None)]
        cabecalho(ws, r0, cols)
        for i in range(min(5, n_oport)):
            r, o = r0 + 1 + i, i + 2
            linha_dados(ws, r, cols, [f"='Oportunidades'!A{o}", f"='Oportunidades'!Q{o}",
                                      f"='Oportunidades'!E{o}", f"='Oportunidades'!R{o}"])
        r0 += min(5, n_oport) + 2
    nota(ws, r0, NOTA_FAT)
    nota(ws, r0 + 1, "Giro/dia e projeções usam os dias reais do período, nunca 30 fixo.")


def calcular_oportunidades(df, attrs, df_ant, dias_ant):
    """
    Métricas de oportunidade por produto da marca com venda, ordenadas pela nota.
    A mesma conta aparece como fórmula na aba Oportunidades e como valor na web.
    """
    alvo = attrs[~attrs["tipo"].isin([TIPO_OUTRA, TIPO_FORA]) & (attrs["un"] > 0)]
    dias = float(df.attrs["dias"])
    un_ant = df_ant.groupby("produto")["un"].sum() if df_ant is not None else None
    dados = []
    for prod, a in alvo.iterrows():
        g = df[df["produto"] == prod]
        com_venda = g[g["un"] > 0]
        por_vend = com_venda.groupby("vendedor_id")["un"].sum()
        precos = com_venda.loc[com_venda["preco"] > 0, "preco"]
        giro = a["un"] / dias
        giro_ant = (float(un_ant.get(prod, 0)) / dias_ant) if un_ant is not None else None
        x = {"prod": prod, "a": a, "giro": giro, "giro_ant": giro_ant, "vend": len(por_vend),
             "lider": por_vend.max() / a["un"] if a["un"] else 0,
             "full": g["full"].mean(), "catalogo": g["catalogo"].mean(), "anuncios": len(g),
             "mediana": round(float(precos.median()), 2) if len(precos) else 0,
             "amp": round(float(precos.max() / precos.min()), 2) if len(precos) >= 2 else 0}
        dados.append(x)
    # Mesma conta da fórmula da coluna Nota, só para ordenar a aba.
    gmax = max([x["giro"] for x in dados] or [1]) or 1
    for x in dados:
        var = (x["giro"] / x["giro_ant"] - 1) if x["giro_ant"] else 0
        x["nota"] = 100 * (x["giro"] / gmax) ** 0.5 * (
            0.4 + 0.25 / max(x["vend"], 1) + 0.15 * (1 - x["full"])
            + 0.1 * (1 - x["lider"]) + 0.1 * max(0, min(var, 1)))
    dados.sort(key=lambda x: -x["nota"])
    media = sum(x["giro"] for x in dados) / len(dados) if dados else 0
    for x in dados:
        x["var"] = (x["giro"] / x["giro_ant"] - 1) if x["giro_ant"] else None
        s = []
        if x["vend"] <= 3 and x["giro"] >= media:
            s.append("Pouca concorrência")
        if x["full"] < 0.2 and x["giro"] >= media:
            s.append("FULL livre")
        if x["catalogo"] < 0.3:
            s.append("Catálogo pouco disputado")
        if x["lider"] >= 0.6:
            s.append("Líder domina")
        if x["var"] is not None and x["var"] > 0.2:
            s.append("Acelerando")
        if x["var"] is not None and x["var"] < -0.2:
            s.append("Perdendo giro")
        if x["giro_ant"] is not None and x["giro_ant"] == 0:
            s.append("Novo no período")
        if x["amp"] >= 2:
            s.append("Preço disperso")
        x["sinais"] = " · ".join(s)
    return dados


def aba_oportunidades(ws, df, attrs, df_ant, dias_ant):
    """
    Onde entrar: produtos da marca com venda, com uma nota de 0 a 100 e sinais.
    A demanda MULTIPLICA a nota (produto sem venda não é oportunidade, por mais
    livre que esteja):  nota = 100 × √(giro ÷ maior giro) × (0,40 + 0,25 × pouca
    concorrência + 0,15 × FULL livre + 0,10 × líder fraco + 0,10 × aceleração).
    """
    ws.title = "Oportunidades"
    cols = [("Produto", TXT, 44), ("Categoria", TXT, 12), ("Marca", TXT, 14), ("Volume", TXT, 9),
            ("Giro/dia", DEC, 9), ("Giro/dia anterior", DEC, 10), ("Variação do giro", PCT, 10),
            ("Vendedores com venda", INT, 10), ("Giro por vendedor", DEC, 10), ("Anúncios", INT, 9),
            ("Líder: share do maior vendedor", PCT, 12), ("% FULL", PCT, 8), ("% catálogo", PCT, 9),
            ("Preço mediano", MOEDA2, 11), ("Faixa de preço", TXT, 12), ("Amplitude de preço", VEZES, 10),
            ("Nota (0–100)", INT, 9), ("Sinais", TXT, 60)]
    dados = calcular_oportunidades(df, attrs, df_ant, dias_ant)
    n = len(dados) + 1
    P = AN("produto")
    E = f"E$2:E${max(n, 2)}"

    def fazer(x):
        a = x["a"]

        def f(r):
            sinais = (f'IF(AND(H{r}<=3,E{r}>=AVERAGE({E}))," · Pouca concorrência","")'
                      f'&IF(AND(L{r}<0.2,E{r}>=AVERAGE({E}))," · FULL livre","")'
                      f'&IF(M{r}<0.3," · Catálogo pouco disputado","")'
                      f'&IF(K{r}>=0.6," · Líder domina","")'
                      f'&IF(AND(ISNUMBER(G{r}),G{r}>0.2)," · Acelerando","")'
                      f'&IF(AND(ISNUMBER(G{r}),G{r}<-0.2)," · Perdendo giro","")'
                      f'&IF(AND(ISNUMBER(F{r}),F{r}=0)," · Novo no período","")'
                      f'&IF(P{r}>=2," · Preço disperso","")')
            return [x["prod"], a["cat"], a["marca"], a["volume"],
                    f"=IFERROR(SUMIFS({AN('un')},{P},$A{r})/{R_DIAS},0)",
                    None if x["giro_ant"] is None else round(x["giro_ant"], 4),
                    f'=IF(AND(ISNUMBER(F{r}),F{r}>0),E{r}/F{r}-1,"")',
                    x["vend"], f"=IFERROR(E{r}/H{r},0)", f"=COUNTIFS({P},$A{r})",
                    round(float(x["lider"]), 4),
                    f"=IFERROR(COUNTIFS({P},$A{r},{AN('full')},1)/J{r},0)",
                    f"=IFERROR(COUNTIFS({P},$A{r},{AN('catalogo')},1)/J{r},0)",
                    x["mediana"], faixa_preco(f"N{r}"), x["amp"],
                    f"=ROUND(100*SQRT(IFERROR(E{r}/MAX({E}),0))*(0.4+0.25*IFERROR(1/H{r},0)"
                    f"+0.15*(1-L{r})+0.1*(1-K{r})+0.1*IF(ISNUMBER(G{r}),MAX(0,MIN(G{r},1)),0)),0)",
                    f"=MID({sinais},4,300)"]
        return f

    r = tabela(ws, 1, cols, [fazer(x) for x in dados])
    if r >= 2:
        ws.conditional_formatting.add(f"Q2:Q{r}", ColorScaleRule(
            start_type="num", start_value=0, start_color="FFFFFF",
            end_type="num", end_value=100, end_color="63BE7B"))
    notas = [
        "Como ler: nota alta = muita demanda, pouca gente vendendo, FULL livre, mercado sem dono e giro subindo.",
        "Nota = 100 × √(giro ÷ maior giro) × (0,40 + 0,25 × pouca concorrência [1 ÷ vendedores com venda] "
        "+ 0,15 × FULL livre + 0,10 × líder fraco + 0,10 × aceleração). A demanda multiplica: sem venda, sem nota.",
        "Pouca concorrência: até 3 vendedores com venda e giro acima da média. "
        "FULL livre: menos de 20% dos anúncios em FULL e giro acima da média.",
        "Catálogo pouco disputado: menos de 30% dos anúncios no catálogo. Líder domina: um vendedor com 60%+ "
        "das unidades (difícil entrar). Preço disperso: máximo 2x ou mais o mínimo (há espaço de margem).",
        "Acelerando / perdendo giro: variação acima de +20% / abaixo de −20% contra o período anterior. "
        "Rodando todo dia, isso vira o seu radar diário.",
        "Só produtos da própria marca com venda no período (sem outras marcas nem itens fora de perfumaria).",
    ]
    for i, t in enumerate(notas):
        nota(ws, r + 2 + i, t)
    return len(dados)


def aba_produtos(ws, attrs, df):
    ws.title = "Produtos"
    cols = [("Produto", TXT, 44), ("Categoria", TXT, 12), ("Linha", TXT, 22), ("Tipo", TXT, 10),
            ("Volume", TXT, 8), ("GTINs", INT, 7), ("Marca", TXT, 14),
            ("Anúncios", INT, 9), ("Vendedores", INT, 10),
            ("Un. vendidas", INT, 11), ("Faturamento", MOEDA, 14), ("Preço médio", MOEDA2, 11),
            ("Faixa de preço", TXT, 12), ("Giro/dia", DEC, 9), ("Projeção 30d", INT, 11),
            ("% do volume", PCT, 9), ("% acumulado", PCT, 10), ("Curva ABC", TXT, 7),
            ("Un. por anúncio", DEC, 10), ("% catálogo", PCT, 9), ("% FULL", PCT, 8),
            ("Confiança do agrupamento", TXT, 26)]
    n = len(attrs)
    tr = n + 2   # linha do TOTAL
    P, U, F = AN("produto"), AN("un"), AN("fat")

    def fazer(prod, a):
        def f(r):
            return [prod, a["cat"], a["linha"], a["tipo"], a["volume"], int(a["gtins"]), a["marca"],
                    f"=COUNTIFS({P},$A{r})", int(a["vendedores"]),
                    f"=SUMIFS({U},{P},$A{r})", f"=SUMIFS({F},{P},$A{r})",
                    f"=IFERROR(K{r}/J{r},0)", faixa_preco(f"L{r}"),
                    f"=IFERROR(J{r}/{R_DIAS},0)", f"=N{r}*30",
                    f"=IFERROR(J{r}/$J${tr},0)", f"=IFERROR(SUM($J$2:J{r})/$J${tr},0)",
                    f'=IF(Q{r}-P{r}<0.8,"A",IF(Q{r}-P{r}<0.95,"B","C"))', f"=IFERROR(J{r}/H{r},0)",
                    f"=IFERROR(COUNTIFS({P},$A{r},{AN('catalogo')},1)/H{r},0)",
                    f"=IFERROR(COUNTIFS({P},$A{r},{AN('full')},1)/H{r},0)", a["confianca"]]
        return f

    def total(r):
        rng = lambda L: f"{L}2:{L}{max(r - 1, 2)}"
        return ["TOTAL", None, None, None, None, None, None, f"=SUM({rng('H')})",
                df["vendedor_id"].nunique(), f"=SUM({rng('J')})", f"=SUM({rng('K')})",
                f"=IFERROR(K{r}/J{r},0)", None, f"=IFERROR(J{r}/{R_DIAS},0)", f"=N{r}*30",
                f"=SUM({rng('P')})", None, None, f"=IFERROR(J{r}/H{r},0)",
                f"=IFERROR(SUM({AN('catalogo')})/H{r},0)", f"=IFERROR(SUM({AN('full')})/H{r},0)", None]

    r = tabela(ws, 1, cols, [fazer(p, a) for p, a in attrs.iterrows()], total)
    nota(ws, r + 2, NOTA_FAT)
    nota(ws, r + 3, "Curva ABC pelo % acumulado: até 80% = A, até 95% = B, resto = C (o produto que "
                    "cruza a linha dos 80% ainda é A). "
                    "Un. por anúncio alto = poucos anúncios levando muito volume.")
    nota(ws, r + 4, "Use os filtros do cabeçalho (Categoria, Marca, Volume, Faixa de preço, Curva ABC) "
                    "para recortar o mercado.")


def aba_gtins(ws, df, attrs):
    ws.title = "GTINs"
    cols = [("GTIN", TXT, 16), ("Produto", TXT, 44), ("Anúncios", INT, 10), ("Vendedores", INT, 11),
            ("Un. vendidas", INT, 12), ("Faturamento", MOEDA, 15), ("Preço médio", MOEDA2, 12),
            ("% do volume", PCT, 10), ("Categoria", TXT, 12), ("Confiança do agrupamento", TXT, 26),
            ("Especificação pesquisada", TXT, 44), ("Pesquisar", TXT, 11)]
    g = df[df["gtin"] != ""]
    agg = g.groupby("gtin").agg(produto=("produto", lambda s: s.value_counts().index[0]),
                                vend=("vendedor_id", "nunique"), un=("un", "sum"), fat=("fat", "sum"),
                                conf=("confianca", lambda s: s.value_counts().index[0]))
    agg = agg.sort_values(["un", "fat"], ascending=False, kind="mergesort")
    G, U, F = AN("gtin"), AN("un"), AN("fat")

    def fazer(gtin, x):
        cat = attrs["cat"].get(x["produto"], "")
        spec = (INFO_GTIN.get(gtin) or {}).get("nome", "")
        return lambda r: [gtin, x["produto"], f"=COUNTIFS({G},$A{r})", x["vend"],
                          f"=SUMIFS({U},{G},$A{r})", f"=SUMIFS({F},{G},$A{r})",
                          f"=IFERROR(F{r}/E{r},0)", f"=IFERROR(E{r}/{R_UN},0)",
                          cat, x["conf"], spec, link_google(gtin)]

    r = tabela(ws, 1, cols, [fazer(i, x) for i, x in agg.iterrows()])
    for rr in range(2, r + 1):
        ws.cell(row=rr, column=12).font = FONTE_LINK
    fim = max(r, 2)
    r += 2
    cel(ws, r, 1, "Unidades sem GTIN válido", fonte=FONTE_B)
    cel(ws, r, 2, None)
    cel(ws, r, 5, f"={R_UN}-SUM(E2:E{fim})", fmt=INT, fonte=FONTE_B)
    cel(ws, r, 8, f"=IFERROR(E{r}/{R_UN},0)", fmt=PCT, fonte=FONTE_B)
    nota(ws, r + 1, "Essas unidades não aparecem nesta aba, mas estão na aba Produtos. "
                    "Quanto maior esse número, mais sujo está o cadastro da marca no marketplace.")
    nota(ws, r + 2, NOTA_FAT)


def aba_duvidas(ws, df):
    """GTINs cujos anúncios discordam sobre o produto — o que vale conferir/pesquisar."""
    ws.title = "Dúvidas"
    duv = df[(df["gtin"] != "") & df["confianca"].fillna("").str.startswith("Dúvida")]
    cel(ws, 1, 1, "GTINs em dúvida: os títulos dos anúncios não batem entre si (ou a linha não foi "
                  "reconhecida). O produto atribuído foi escolhido pelo anúncio que mais vende.",
        fonte=FONTE_B, borda=False)
    cel(ws, 2, 1, f"Para pesquisar as especificações automaticamente:  {COMANDO_PESQUISA}     "
                  f"(um GTIN específico:  python nubi.py --gtin 3386460101035)", fonte=FONTE_ALERTA, borda=False)
    cel(ws, 3, 1, "Para corrigir à mão: abra gtins.json e escreva o nome certo do produto no GTIN, "
                  'ex.: "3386460101035": {"nome": "Montblanc Explorer Eau de Parfum 100 ml", "marca": "Montblanc"}',
        fonte=FONTE_NOTA, borda=False)
    cols = [("GTIN", TXT, 16), ("Produto atribuído", TXT, 44), ("Motivo", TXT, 28),
            ("Anúncios", INT, 9), ("Un. vendidas", INT, 11), ("Títulos diferentes", INT, 10),
            ("Principais títulos (dos que mais vendem)", TXT, 80), ("Pesquisa automática", TXT, 40),
            ("Pesquisar", TXT, 11)]
    grupos = []
    for gtin, g in duv.groupby("gtin"):
        g = g.sort_values("un", ascending=False)
        titulos = list(dict.fromkeys(g["titulo"]))
        info = INFO_GTIN.get(gtin)
        if not info:
            status = "não pesquisado"
        elif info.get("nome"):
            status = f"{info.get('fonte', '')}: {info['nome']}"
        else:
            status = "não encontrado nas bases — confira no Google"
        grupos.append((int(g["un"].sum()), gtin, g["produto"].value_counts().index[0],
                       g["confianca"].iloc[0], g["titulo"].map(normalizar).nunique(),
                       " | ".join(titulos[:3]), status))
    grupos.sort(key=lambda x: -x[0])
    G = AN("gtin")

    def fazer(x):
        _, gtin, prod, motivo, n_tit, tits, status = x
        return lambda r: [gtin, prod, motivo, f"=COUNTIFS({G},$A{r})", f"=SUMIFS({AN('un')},{G},$A{r})",
                          n_tit, tits, status, link_google(gtin)]

    r = tabela(ws, 5, cols, [fazer(x) for x in grupos])
    for rr in range(6, r + 1):
        ws.cell(row=rr, column=9).font = FONTE_LINK
    return len(grupos)


def aba_vendedores(ws, df, vend):
    ws.title = "Vendedores"
    cols = [("Código", TXT, 9), ("Vendedor", TXT, 30), ("Un. vendidas", INT, 12),
            ("Faturamento", MOEDA, 15), ("Share", PCT, 9), ("Share acumulado", PCT, 11),
            ("Anúncios", INT, 10), ("Referências", INT, 11), ("Preço médio", MOEDA2, 12),
            ("Un. por anúncio", DEC, 11), ("% catálogo", PCT, 10), ("% FULL", PCT, 9),
            ("Anúncios loja oficial", INT, 12), ("Internacional", INT, 12)]
    refs = df.groupby("vendedor_id")["produto"].nunique()
    C, U, F = AN("cod"), AN("un"), AN("fat")

    def fazer(vid, row):
        return lambda r: [row["cod"], row["nome"], f"=SUMIFS({U},{C},$A{r})", f"=SUMIFS({F},{C},$A{r})",
                          f"=IFERROR(C{r}/{R_UN},0)", f"=IFERROR(SUM($C$2:C{r})/{R_UN},0)",
                          f"=COUNTIFS({C},$A{r})", int(refs.get(vid, 0)), f"=IFERROR(D{r}/C{r},0)",
                          f"=IFERROR(C{r}/G{r},0)",
                          f"=IFERROR(COUNTIFS({C},$A{r},{AN('catalogo')},1)/G{r},0)",
                          f"=IFERROR(COUNTIFS({C},$A{r},{AN('full')},1)/G{r},0)",
                          f"=COUNTIFS({C},$A{r},{AN('loja_oficial')},1)",
                          f"=COUNTIFS({C},$A{r},{AN('internacional')},1)"]

    r = tabela(ws, 1, cols, [fazer(vid, row) for vid, row in vend.iterrows()])
    if r >= 2:
        ws.conditional_formatting.add(f"A2:N{r}", FormulaRule(formula=["$E2>=0.05"], fill=FILL_VERDE))
    nota(ws, r + 2, "Em verde: vendedores com 5% ou mais do volume do mercado. "
                    "O código V01, V02… permite gerar versão anonimizada do relatório.")
    nota(ws, r + 3, NOTA_FAT)


def aba_precos(ws, df, attrs):
    ws.title = "Preços"
    cols = [("Produto", TXT, 44), ("Vendedores", INT, 11), ("Un. vendidas", INT, 12),
            ("Mínimo", MOEDA2, 11), ("1º quartil", MOEDA2, 11), ("Mediana", MOEDA2, 11),
            ("3º quartil", MOEDA2, 11), ("Máximo", MOEDA2, 11), ("Amplitude (máx ÷ mín)", VEZES, 12),
            ("Preço médio ponderado", MOEDA2, 13), ("Un. vendidas abaixo de 80% da mediana", INT, 16),
            ("Categoria", TXT, 12), ("Marca", TXT, 14), ("Faixa de preço", TXT, 12)]
    v = df[(df["un"] > 0) & (df["preco"] > 0)]
    grupos = []
    for prod, g in v.groupby("produto"):
        if len(g) < 2:      # quartil de um ponto só não diz nada
            continue
        q = g["preco"].quantile([0, .25, .5, .75, 1]).tolist()   # mesmo método do QUARTIL do Excel
        grupos.append((int(g["un"].sum()), prod, g["vendedor_id"].nunique(), q))
    grupos.sort(key=lambda x: (-x[0], x[1]))
    P, U, PR, RC = AN("produto"), AN("un"), AN("preco"), AN("receita")
    filtro = lambda r: f'{P},$A{r},{U},">0",{PR},">0"'

    def fazer(prod, nv, q):
        a = attrs.loc[prod]
        return lambda r: [prod, nv, f"=SUMIFS({U},{filtro(r)})", *[round(x, 2) for x in q],
                          f"=IFERROR(H{r}/D{r},0)", f"=IFERROR(SUMIFS({RC},{filtro(r)})/C{r},0)",
                          f'=SUMIFS({U},{filtro(r)},{PR},"<"&(0.8*F{r}))',
                          a["cat"], a["marca"], faixa_preco(f"F{r}")]

    r = tabela(ws, 1, cols, [fazer(p, nv, q) for _, p, nv, q in grupos])
    nota(ws, r + 2, "Só anúncios com venda no período e preço > 0; referências com menos de 2 "
                    "anúncios ficam de fora. Quartis e extremos usam o último preço de cada anúncio.")
    nota(ws, r + 3, "Amplitude alta = a marca não tem faixa de preço definida. A última coluna mostra "
                    "se há volume real vendido muito barato ou só anúncio de vitrine que não gira.")


def aba_evolucao(ws, ant, atu, snap_ant, snap_atu, attrs):
    ws.title = "Evolução"
    cel(ws, 1, 1, "Evolução por referência — tudo por dia, porque os períodos podem ter durações diferentes",
        fonte=FONTE_B, borda=False)
    for r, rot, s in ((2, "Período anterior", snap_ant), (3, "Período atual", snap_atu)):
        cel(ws, r, 1, rot, fonte=FONTE_B)
        cel(ws, r, 2, f"{fmt_data(str(s['inicio']))} a {fmt_data(str(s['fim']))}")
        cel(ws, r, 3, "Dias", fonte=FONTE_B)
        cel(ws, r, 4, int(s["dias"]), fmt=INT)
    cols = [("Produto", TXT, 44), ("Giro/dia anterior", DEC, 12), ("Giro/dia atual", DEC, 12),
            ("Variação do giro", PCT, 11), ("Preço médio anterior", MOEDA2, 13),
            ("Preço médio atual", MOEDA2, 13), ("Variação do preço", PCT, 11),
            ("Vendedores antes", INT, 11), ("Vendedores agora", INT, 11), ("Movimento", TXT, 16),
            ("Un. anterior (base)", INT, 12), ("Un. atual (base)", INT, 12),
            ("Faturamento anterior (base)", MOEDA, 15), ("Faturamento atual (base)", MOEDA, 15),
            ("Categoria", TXT, 12), ("Marca", TXT, 14)]
    agg = lambda d: d.groupby("produto").agg(un=("un", "sum"), fat=("fat", "sum"),
                                             vend=("vendedor_id", "nunique"))
    j = agg(ant).join(agg(atu), how="outer", lsuffix="_a", rsuffix="_b").fillna(0)
    j["giro"] = j["un_b"] / snap_atu["dias"]
    j = j.sort_values(["giro", "un_a"], ascending=False, kind="mergesort")
    extra = ant.drop_duplicates("produto").set_index("produto")

    def fazer(prod, x):
        if prod in attrs.index:
            cat, gen = attrs.at[prod, "cat"], attrs.at[prod, "marca"]
        else:
            cat, gen = extra.at[prod, "cat"], extra.at[prod, "marca_prod"]
        return lambda r: [
            prod, f"=IFERROR(K{r}/$D$2,0)", f"=IFERROR(L{r}/$D$3,0)",
            f"=IF(B{r}=0,0,IFERROR(C{r}/B{r}-1,0))",
            f"=IFERROR(M{r}/K{r},0)", f"=IFERROR(N{r}/L{r},0)",
            f"=IF(OR(E{r}=0,F{r}=0),0,IFERROR(F{r}/E{r}-1,0))",
            int(x["vend_a"]), int(x["vend_b"]),
            f'=IF(AND(B{r}=0,C{r}=0),"sem venda",IF(B{r}=0,"novo no período",IF(C{r}=0,"sumiu",'
            f'IF(D{r}>0.2,"acelerando",IF(D{r}<-0.2,"perdendo giro","estável")))))',
            int(x["un_a"]), int(x["un_b"]), float(x["fat_a"]), float(x["fat_b"]), cat, gen]

    r = tabela(ws, 5, cols, [fazer(p, x) for p, x in j.iterrows()])
    nota(ws, r + 2, "Movimento: sem giro antes = novo no período; sem giro agora = sumiu; "
                    "variação acima de +20% = acelerando; abaixo de −20% = perdendo giro; senão estável.")
    nota(ws, r + 3, "Produto que sumiu com giro alto antes = possível ruptura de estoque dos concorrentes: "
                    "oportunidade de entrar.")
    nota(ws, r + 4, NOTA_FAT)


def aba_historico(ws, repo, snaps, attrs):
    """Giro/dia de cada referência em cada período importado (até os 30 últimos)."""
    ws.title = "Histórico"
    snaps = snaps.tail(30)
    series, rotulos = [], []
    un = repo.un_por_produto(list(snaps["id"]))
    for _, s in snaps.iterrows():
        d = un[un["snapshot_id"] == s["id"]]
        series.append(d.groupby("produto")["un"].sum() / float(s["dias"]))
        ini, fim = fmt_data(str(s["inicio"]))[:5], fmt_data(str(s["fim"]))[:5]
        rotulos.append(f"Giro/dia {fim}" if ini == fim else f"Giro/dia {ini} a {fim}")
    tab = pd.concat(series, axis=1).fillna(0)
    tab = tab.iloc[(-tab.iloc[:, -1].values).argsort(kind="mergesort")]   # maior giro atual primeiro
    k = len(series)
    L0, Lp, Lu = col(3), col(2 + k - 1), col(2 + k)   # primeira, penúltima e última coluna de giro
    cols = ([("Produto", TXT, 44), ("Categoria", TXT, 12)] + [(t, DEC, 11) for t in rotulos]
            + [("Média dos períodos anteriores", DEC, 12), ("Último vs média", PCT, 10),
               ("Períodos com venda", INT, 10)])

    def fazer(prod, valores):
        cat = attrs.at[prod, "cat"] if prod in attrs.index else "-"
        return lambda r: ([prod, cat] + [round(float(v), 4) for v in valores]
                          + [f"=AVERAGE({L0}{r}:{Lp}{r})",
                             f'=IF({col(3 + k)}{r}>0,{Lu}{r}/{col(3 + k)}{r}-1,"")',
                             f'=COUNTIFS({L0}{r}:{Lu}{r},">0")'])

    r = tabela(ws, 1, cols, [fazer(p, v.values) for p, v in tab.iterrows()])
    nota(ws, r + 2, "Cada coluna é um período importado. Importando um CSV por dia, esta aba vira a série "
                    "diária de cada produto. Último vs média: +20% ou mais = ganhando tração.")


def aba_anuncios(ws, df, vend):
    ws.title = "Anúncios"
    cols = [(t, f, l) for _, t, f, l in COLS_ANUNCIOS]
    d = df.sort_values(["produto", "un"], ascending=[True, False], kind="mergesort").copy()
    d["cod"] = d["vendedor_id"].map(vend["cod"])
    d["confianca"] = d["confianca"].fillna("")
    chaves = [k for k, *_ in COLS_ANUNCIOS]
    iL, iJ = col(IDX_AN["preco"]), col(IDX_AN["un"])
    registros = d.to_dict("records")

    def fazer(reg):
        def f(r):
            vals = []
            for k in chaves:
                if k == "receita":
                    vals.append(f"={iL}{r}*{iJ}{r}")
                elif k == "gtin":
                    vals.append(reg["gtin"] or None)   # vazio de verdade, não texto ""
                else:
                    v = reg[k]
                    vals.append(v.item() if hasattr(v, "item") else v)
            return vals
        return f

    tabela(ws, 1, cols, [fazer(reg) for reg in registros])


def ler_snapshot(repo, sid, marca=""):
    return campos_do_arquivo(preparar(repo.anuncios(sid)), marca)


def montar_planilha_marca(repo, marca):
    """Monta o Excel da marca e devolve (workbook, nome do arquivo)."""
    snaps = repo.snapshots(marca)
    if snaps.empty:
        return None, None
    atual = snaps.iloc[-1]
    df = ler_snapshot(repo, atual["id"], marca)
    df.attrs["dias"] = int(atual["dias"])
    vend = codigos_vendedor(df)
    attrs = atributos_produto(df)
    n_gtin = df.loc[df["gtin"] != "", "gtin"].nunique()
    df_ant, anterior = None, None
    if len(snaps) >= 2:
        anterior = snaps.iloc[-2]
        df_ant = ler_snapshot(repo, anterior["id"], marca)

    wb = Workbook()
    resumo = wb.active
    n_oport = aba_oportunidades(wb.create_sheet(), df, attrs, df_ant,
                                float(anterior["dias"]) if anterior is not None else None)
    if df_ant is not None:
        aba_evolucao(wb.create_sheet(), df_ant, df, anterior, atual, attrs)
        aba_historico(wb.create_sheet(), repo, snaps, attrs)
    aba_produtos(wb.create_sheet(), attrs, df)
    aba_precos(wb.create_sheet(), df, attrs)
    aba_vendedores(wb.create_sheet(), df, vend)
    aba_gtins(wb.create_sheet(), df, attrs)
    ws_duv = wb.create_sheet()
    n_duvida = aba_duvidas(ws_duv, df)
    if not n_duvida:
        wb.remove(ws_duv)
    aba_anuncios(wb.create_sheet(), df, vend)
    aba_resumo(resumo, marca, atual, len(vend), len(attrs), n_gtin, n_duvida, n_oport)
    return wb, f"{slug(marca)}-explorador-de-anuncios.xlsx"


def gerar_planilha_marca(repo, marca):
    wb, nome = montar_planilha_marca(repo, marca)
    if wb is None:
        return None
    destino = SAIDA / nome
    salvar(wb, destino)
    return destino


def montar_painel(repo):
    snaps = repo.snapshots()
    if snaps.empty:
        return None
    ultimos = snaps.groupby("marca").tail(1)
    wb = Workbook()
    ws = wb.active
    ws.title = "Painel"
    cols = [("Marca", TXT, 22), ("Período", TXT, 24), ("Dias", INT, 7), ("Anúncios", INT, 10),
            ("Vendedores", INT, 11), ("Referências", INT, 11), ("Un. vendidas", INT, 12),
            ("Faturamento", MOEDA, 15), ("Preço médio", MOEDA2, 12), ("Giro/dia", DEC, 10),
            ("Projeção anual (un.)", INT, 13), ("% em catálogo", PCT, 11),
            ("Anúncios em catálogo (base)", INT, 13)]
    linhas, todos_vend = [], set()
    for _, s in ultimos.iterrows():
        d = repo.anuncios(s["id"])
        todos_vend |= set(d["vendedor_id"])
        linhas.append((d["un"].sum(), nome_bonito(s["marca"]),
                       f"{fmt_data(str(s['inicio']))} a {fmt_data(str(s['fim']))}", int(s["dias"]), len(d),
                       d["vendedor_id"].nunique(), d["produto"].nunique(), int(d["un"].sum()),
                       float(d["fat"].sum()), int(d["catalogo"].sum())))
    linhas.sort(key=lambda x: -x[0])

    def fazer(x):
        _, m, per, dias, na, nv, nr, un, fat, cat = x
        return lambda r: [m, per, dias, na, nv, nr, un, fat, f"=IFERROR(H{r}/G{r},0)",
                          f"=IFERROR(G{r}/C{r},0)", f"=J{r}*365", f"=IFERROR(M{r}/D{r},0)", cat]

    def total(r):
        s = lambda L: f"=SUM({L}2:{L}{r - 1})"
        return ["TOTAL", None, None, s("D"), len(todos_vend), s("F"), s("G"), s("H"),
                f"=IFERROR(H{r}/G{r},0)", s("J"), f"=J{r}*365", f"=IFERROR(M{r}/D{r},0)", s("M")]

    r = tabela(ws, 1, cols, [fazer(x) for x in linhas], total)
    nota(ws, r + 2, "Sempre o período mais recente de cada marca. Vendedores no TOTAL = vendedores "
                    "distintos somando todas as marcas (quem vende duas marcas conta uma vez).")
    nota(ws, r + 3, "Números do mercado inteiro (todos os vendedores), não da sua loja.", FONTE_ALERTA)
    nota(ws, r + 4, NOTA_FAT)
    return wb


def gerar_painel(repo):
    wb = montar_painel(repo)
    if wb is None:
        return None
    destino = SAIDA / "painel-geral.xlsx"
    salvar(wb, destino)
    return destino


def salvar(wb, destino):
    try:
        wb.save(destino)
    except PermissionError:
        raise ErroArquivo(f"não consegui gravar {destino.name} — feche o arquivo no Excel "
                          f"e rode de novo")


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------

def ler_argumentos():
    ap = argparse.ArgumentParser(
        description="Explorador de anúncios: transforma os CSVs de entrada/ em planilhas.")
    ap.add_argument("--marca", help="marca dos CSVs cujo nome não segue o padrão")
    ap.add_argument("--inicio", help="data inicial do período, AAAA-MM-DD")
    ap.add_argument("--fim", help="data final do período, AAAA-MM-DD")
    ap.add_argument("--pesquisar-gtin", action="store_true",
                    help="pesquisa na internet os GTINs cujo agrupamento está em dúvida")
    ap.add_argument("--gtin", nargs="+", metavar="GTIN",
                    help="pesquisa estes GTINs específicos (mesmo que já pesquisados)")
    ap.add_argument("--limite", type=int, default=40,
                    help="máximo de GTINs pesquisados por vez (padrão 40)")
    a = ap.parse_args()
    ini = data_valida(a.inicio) if a.inicio else None
    fim = data_valida(a.fim) if a.fim else None
    if (a.inicio and not ini) or (a.fim and not fim):
        ap.error("datas no formato AAAA-MM-DD, ex.: --inicio 2026-08-01 --fim 2026-09-16")
    if bool(ini) != bool(fim) or (ini and fim < ini):
        ap.error("informe --inicio e --fim juntos, com o fim depois do início")
    a.informado = (a.marca, ini, fim)
    a.pesquisar = a.pesquisar_gtin or bool(a.gtin)
    return a


def main():
    args = ler_argumentos()
    for p in (ENTRADA, SAIDA, DADOS):
        p.mkdir(parents=True, exist_ok=True)
    print("nubi — explorador de anúncios")

    arquivos = sorted(p for p in ENTRADA.iterdir() if p.is_file() and p.suffix.lower() == ".csv")
    if not arquivos and not args.pesquisar:
        print(f"\n  Nenhum CSV na pasta entrada/. Coloque os exports lá e rode de novo.")
        return 0

    repo = RepoLocal()
    try:
        cfg = repo.carregar_config()
        INFO_GTIN.update(repo.carregar_gtins())
    except ErroArquivo as e:
        print(f"\n  {e}")
        return 1

    try:
        if arquivos:
            print(f"\nImportando {len(arquivos)} arquivo(s):")
        for arq in arquivos:
            try:
                importar(repo, cfg, arq, args.informado)
            except ErroArquivo as e:
                print(f"    Não importado: {e}.")

        marcas = repo.marcas()
        if not marcas:
            print("\n  Nada no histórico ainda — nenhuma planilha gerada.")
            return 0

        reconsolidar(repo, cfg)
        if args.pesquisar:
            pesquisar_gtins(repo, max(1, args.limite), args.gtin)
            reconsolidar(repo, cfg)
        print("\nPlanilhas geradas:")
        for marca in marcas + [None]:
            try:
                destino = gerar_planilha_marca(repo, marca) if marca else gerar_painel(repo)
                if destino:
                    print(f"  saida/{destino.name}")
            except ErroArquivo as e:
                print(f"  {e}.")

        # Sempre que houver agrupamento em dúvida, mostrar o comando que resolve.
        pendentes = [g for g in gtins_em_duvida(repo) if precisa_pesquisar(g[0])]
        if pendentes:
            un = sum(g[2] for g in pendentes)
            print(f"\n  Em dúvida: {len(pendentes)} GTIN(s) com títulos que não batem entre si "
                  f"({fmt_int(un)} unidades). Veja a aba Dúvidas.")
            print(f"  Para pesquisar as especificações e agrupar certo:  {COMANDO_PESQUISA}")
    finally:
        repo.fechar()
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(errors="replace")
    except AttributeError:
        pass
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrompido.")
        sys.exit(1)
    except Exception:  # noqa: BLE001 — o operador vê uma frase; o detalhe vai para o log
        DADOS.mkdir(parents=True, exist_ok=True)
        LOG_ERRO.write_text(f"{datetime.now():%d/%m/%Y %H:%M}\n{traceback.format_exc()}",
                            encoding="utf-8")
        print("\nAlgo deu errado e o programa parou. O detalhe técnico foi salvo em "
              "dados/erro.log — mande esse arquivo para quem dá suporte.")
        sys.exit(1)
