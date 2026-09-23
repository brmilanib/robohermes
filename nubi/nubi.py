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
import json
import re
import sqlite3
import sys
import traceback
import unicodedata
from datetime import datetime
from pathlib import Path

try:
    import pandas as pd
    from openpyxl import Workbook
    from openpyxl.formatting.rule import FormulaRule
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
LOG_ERRO = DADOS / "erro.log"

PADRAO_NOME = re.compile(r"^(.+?)__(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})$", re.IGNORECASE)
COLUNAS_OBRIGATORIAS = ["Título", "Vendedor", "Unidades vendidas"]
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


def ler_csv(caminho):
    df = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(caminho, sep=";", encoding=enc, dtype=str,
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
    palavras_marca = set(normalizar(marca).split())
    if "categoria" in df.columns:
        df = df[(df["categoria"].fillna("") == "") & (dono_do_anuncio(df, marca) == "")]
    util = lambda p: (p not in PALAVRAS_VAZIAS and p not in palavras_marca
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


def garantir_config(cfg, marca, df):
    """Se a marca não está no marcas.json, detecta as linhas, grava e avisa."""
    chave = chave_marca(marca)
    if chave in cfg:
        return
    linhas = detectar_linhas(df, marca)
    cfg[chave] = {"linhas": linhas}
    salvar_config(cfg)
    print(f"    Marca nova: {chave}. Linhas detectadas e gravadas em marcas.json:")
    if linhas:
        for _, rotulo in linhas:
            print(f"      - {rotulo}")
    else:
        print("      (nenhuma — todos os anúncios vão para \"Outros\")")
    print("    Você pode ajustar essa lista à mão no marcas.json e rodar de novo.")


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


def dono_do_anuncio(df, marca):
    """
    Confirma, anúncio por anúncio, se ele é mesmo da marca do export — cruzando a
    coluna Marca com o GTIN. Devolve uma Série: "" = é da marca; senão o nome da
    outra marca (ex.: "J. SERRANO" num export da Montblanc = contratipo).
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
    for _, g in df[df["gtin"] != ""].groupby("gtin"):
        if bate[g.index].any():
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


def consolidar(df, marca, cfg):
    """Devolve df com linha, volume, tipo e produto preenchidos."""
    df = df.copy()
    linhas = cfg.get(chave_marca(marca), {}).get("linhas", [])
    palavras_marca = set(normalizar(marca).split())
    tn = df["titulo"].map(normalizar)

    # Etapa 1 — ler o título.
    df["linha"] = tn.map(lambda t: achar_linha(t, linhas, palavras_marca))
    df["volume"] = tn.map(achar_volume)
    df["tipo"] = tn.map(achar_tipo)
    # Antes de tudo, separar o que não é da marca nem é perfume: esses anúncios
    # continuam no total, mas viram referências próprias e não votam nas etapas 2 e 3.
    dono = dono_do_anuncio(df, marca)
    outra = dono != ""
    df.loc[outra, "linha"] = dono[outra].map(nome_bonito)
    df.loc[outra, "tipo"] = TIPO_OUTRA
    nao_perf = (df["categoria"].fillna("") != "") & ~outra
    df.loc[nao_perf, "linha"] = df.loc[nao_perf, "categoria"]
    df.loc[nao_perf, "tipo"] = TIPO_FORA
    fora = outra | nao_perf
    df.loc[fora, "volume"] = "-"

    # Etapa 2 — o GTIN corrige o título.
    # Todos os anúncios do mesmo GTIN são o mesmo produto físico. Para linha, volume
    # e tipo, vale o que o anúncio que MAIS VENDEU UNIDADES diz (não o valor mais
    # frequente): um título com 1.200 unidades pesa mais que cinco com 2 cada.
    # É isso que junta "Club De Nuit Intense Da Armaf Ed" (título cortado, campeão
    # de vendas) com "...Club De Nuit Intense Man Eau De Toilette 105ml".
    # "-" e "Outros" não votam, mas o vencedor é aplicado ao grupo inteiro.
    com_gtin = df[(df["gtin"] != "") & ~fora]
    for _, grupo in com_gtin.groupby("gtin"):
        for coluna in ("linha", "volume", "tipo"):
            vencedor = _mais_vendido(grupo, coluna)
            if vencedor is not None:
                df.loc[grupo.index, coluna] = vencedor

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
            volume TEXT, tipo TEXT, gtin TEXT, sku TEXT, un INTEGER, fat REAL, preco REAL,
            un_hist INTEGER, fat_hist REAL, dias_pub INTEGER, exposicao TEXT,
            catalogo INTEGER, full INTEGER, flex INTEGER, internacional INTEGER,
            loja_oficial INTEGER, frete_gratis INTEGER);
        CREATE INDEX IF NOT EXISTS ix_anuncios_snap ON anuncios(snapshot_id);
    """)
    return con


def gravar_snapshot(con, marca, inicio, fim, dias, arquivo, hash_, df):
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
    linhas = [(sid, *r) for r in df[CAMPOS_ANUNCIO].itertuples(index=False, name=None)]
    con.executemany(f"INSERT INTO anuncios(snapshot_id, {', '.join(CAMPOS_ANUNCIO)}) "
                    f"VALUES ({', '.join('?' * (len(CAMPOS_ANUNCIO) + 1))})", linhas)
    con.commit()
    return len(antigos) > 0


def reconsolidar(con, cfg):
    """
    Refaz a consolidação de todo o histórico com o marcas.json atual — assim uma
    correção feita à mão no arquivo vale também para os períodos já importados.
    """
    for marca, sid in con.execute("SELECT marca, id FROM snapshots").fetchall():
        df = pd.read_sql("SELECT rowid AS rid, * FROM anuncios WHERE snapshot_id=?", con, params=(sid,))
        if df.empty:
            continue
        garantir_config(cfg, marca, df)
        novo = consolidar(df, marca, cfg)
        con.executemany("UPDATE anuncios SET produto=?, linha=?, volume=?, tipo=? WHERE rowid=?",
                        list(novo[["produto", "linha", "volume", "tipo", "rid"]]
                             .itertuples(index=False, name=None)))
    con.commit()


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
            return chave_marca(m.group(1).replace("_", " ")), ini, fim
    if informado and informado[1] and informado[2]:
        marca = chave_marca(informado[0] or sugestao)
        if marca:
            return marca, informado[1], informado[2]
    print("    O nome do arquivo não traz marca e período "
          "(padrão MARCA__AAAA-MM-DD_AAAA-MM-DD.csv).")
    try:
        marca = ""
        for _ in range(3):
            marca = chave_marca(perguntar("Marca", chave_marca(sugestao)))
            if marca:
                break
        if not marca:
            print("    Marca não informada. Arquivo pulado.")
            return None
        ini = fim = None
        for _ in range(3):
            ini = data_valida(perguntar("Data inicial (AAAA-MM-DD)"))
            if ini:
                break
            print("    Data inválida. Use o formato AAAA-MM-DD, ex.: 2026-08-01")
        for _ in range(3):
            if not ini:
                break
            fim = data_valida(perguntar("Data final (AAAA-MM-DD)"))
            if fim and fim >= ini:
                break
            print("    Data inválida ou anterior à inicial. Use AAAA-MM-DD.")
            fim = None
        if not (ini and fim):
            print("    Datas não informadas corretamente. Arquivo pulado.")
            return None
        return marca, ini, fim
    except SemTerminal:
        print("    Sem terminal para perguntar. Renomeie o arquivo no padrão "
              "MARCA__AAAA-MM-DD_AAAA-MM-DD.csv. Arquivo pulado.")
        return None


def importar(con, cfg, caminho, informado=None):
    print(f"\n  {caminho.name}")
    hash_ = hashlib.sha256(caminho.read_bytes()).hexdigest()
    ja = con.execute("SELECT importado_em, marca, inicio, fim FROM snapshots WHERE hash=?",
                     (hash_,)).fetchone()
    if ja:
        quando = datetime.fromisoformat(ja[0]).strftime("%d/%m/%Y %H:%M")
        print(f"    Já importado em {quando} ({ja[1]}, {fmt_data(ja[2])} a {fmt_data(ja[3])}). Pulado.")
        return None
    try:
        df, sugestao = ler_csv(caminho)
    except ErroArquivo as e:
        print(f"    Não importado: {e}.")
        return None
    print(f"    {fmt_int(len(df))} anúncios · {fmt_int(df['un'].sum())} unidades")
    mp = marca_e_periodo(caminho, sugestao, informado)
    if not mp:
        return None
    marca, ini, fim = mp
    dias = (fim - ini).days + 1          # inclusive nas pontas: 01/08 a 16/09 = 47 dias
    garantir_config(cfg, marca, df)
    df = consolidar(df, marca, cfg)
    substituiu = gravar_snapshot(con, marca, ini.isoformat(), fim.isoformat(), dias,
                                 caminho.name, hash_, df)
    if substituiu:
        print("    (substituiu uma importação anterior do mesmo período)")
    print(f"    OK: {marca} · {ini:%d/%m/%Y} a {fim:%d/%m/%Y} ({dias} dias) · "
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
    ("linha", "Linha", TXT, 24),
    ("tipo", "Tipo", TXT, 11),
    ("volume", "Volume", TXT, 9),
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


def aba_resumo(ws, marca, snap, n_vend, n_prod, n_gtin):
    ws.title = "Resumo"
    ws.column_dimensions["A"].width = 36
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 58
    cel(ws, 1, 1, f"Explorador de anúncios — {nome_bonito(marca)}", fonte=FONTE_TIT, borda=False)
    cel(ws, 2, 1, "Números do mercado inteiro (todos os vendedores), não da sua loja.",
        fonte=FONTE_ALERTA, borda=False)
    cel(ws, 3, 1, f"Período: {fmt_data(snap['inicio'])} a {fmt_data(snap['fim'])} "
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
    rn = r0 + len(faixas) + 2
    nota(ws, rn, NOTA_FAT)
    nota(ws, rn + 1, "Giro/dia e projeções usam os dias reais do período, nunca 30 fixo.")


def aba_produtos(ws, dfp, df):
    ws.title = "Produtos"
    cols = [("Produto", TXT, 46), ("Anúncios", INT, 10), ("Vendedores", INT, 11),
            ("Un. vendidas", INT, 12), ("Faturamento", MOEDA, 15), ("Preço médio", MOEDA2, 12),
            ("Giro/dia", DEC, 10), ("Projeção 30d", INT, 12), ("% do volume", PCT, 10),
            ("% acumulado", PCT, 11), ("Curva ABC", TXT, 8), ("Un. por anúncio", DEC, 11),
            ("% catálogo", PCT, 10), ("% FULL", PCT, 9)]
    n = len(dfp)
    tr = n + 2   # linha do TOTAL
    P, U, F = AN("produto"), AN("un"), AN("fat")

    def fazer(nome, vend):
        def f(r):
            return [nome, f"=COUNTIFS({P},$A{r})", vend,
                    f"=SUMIFS({U},{P},$A{r})", f"=SUMIFS({F},{P},$A{r})",
                    f"=IFERROR(E{r}/D{r},0)", f"=IFERROR(D{r}/{R_DIAS},0)", f"=G{r}*30",
                    f"=IFERROR(D{r}/$D${tr},0)", f"=IFERROR(SUM($D$2:D{r})/$D${tr},0)",
                    f'=IF(J{r}-I{r}<0.8,"A",IF(J{r}-I{r}<0.95,"B","C"))', f"=IFERROR(D{r}/B{r},0)",
                    f"=IFERROR(COUNTIFS({P},$A{r},{AN('catalogo')},1)/B{r},0)",
                    f"=IFERROR(COUNTIFS({P},$A{r},{AN('full')},1)/B{r},0)"]
        return f

    def total(r):
        u = f"$D$2:$D${r - 1}" if n else "$D$2:$D$2"
        rng = lambda L: f"{L}2:{L}{max(r - 1, 2)}"
        return ["TOTAL", f"=SUM({rng('B')})", df["vendedor_id"].nunique(), f"=SUM({u})",
                f"=SUM({rng('E')})", f"=IFERROR(E{r}/D{r},0)", f"=IFERROR(D{r}/{R_DIAS},0)",
                f"=G{r}*30", f"=SUM({rng('I')})", None, None, f"=IFERROR(D{r}/B{r},0)",
                f"=IFERROR(SUM({AN('catalogo')})/B{r},0)", f"=IFERROR(SUM({AN('full')})/B{r},0)"]

    r = tabela(ws, 1, cols, [fazer(p, v) for p, v in zip(dfp.index, dfp["vendedores"])], total)
    nota(ws, r + 2, NOTA_FAT)
    nota(ws, r + 3, "Curva ABC pelo % acumulado: até 80% = A, até 95% = B, resto = C (o produto que "
                    "cruza a linha dos 80% ainda é A). "
                    "Un. por anúncio alto = poucos anúncios levando muito volume.")


def aba_gtins(ws, df):
    ws.title = "GTINs"
    cols = [("GTIN", TXT, 16), ("Produto", TXT, 46), ("Anúncios", INT, 10), ("Vendedores", INT, 11),
            ("Un. vendidas", INT, 12), ("Faturamento", MOEDA, 15), ("Preço médio", MOEDA2, 12),
            ("% do volume", PCT, 10)]
    g = df[df["gtin"] != ""]
    agg = g.groupby("gtin").agg(produto=("produto", lambda s: s.value_counts().index[0]),
                                vend=("vendedor_id", "nunique"), un=("un", "sum"), fat=("fat", "sum"))
    agg = agg.sort_values(["un", "fat"], ascending=False, kind="mergesort")
    G, U, F = AN("gtin"), AN("un"), AN("fat")

    def fazer(gtin, prod, vend):
        return lambda r: [gtin, prod, f"=COUNTIFS({G},$A{r})", vend, f"=SUMIFS({U},{G},$A{r})",
                          f"=SUMIFS({F},{G},$A{r})", f"=IFERROR(F{r}/E{r},0)",
                          f"=IFERROR(E{r}/{R_UN},0)"]

    r = tabela(ws, 1, cols, [fazer(i, p, v) for i, p, v in zip(agg.index, agg["produto"], agg["vend"])])
    fim = max(r, 2)
    r += 2
    cel(ws, r, 1, "Unidades sem GTIN válido", fonte=FONTE_B)
    cel(ws, r, 2, None)
    cel(ws, r, 5, f"={R_UN}-SUM(E2:E{fim})", fmt=INT, fonte=FONTE_B)
    cel(ws, r, 8, f"=IFERROR(E{r}/{R_UN},0)", fmt=PCT, fonte=FONTE_B)
    nota(ws, r + 1, "Essas unidades não aparecem nesta aba, mas estão na aba Produtos. "
                    "Quanto maior esse número, mais sujo está o cadastro da marca no marketplace.")
    nota(ws, r + 2, NOTA_FAT)


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


def aba_precos(ws, df):
    ws.title = "Preços"
    cols = [("Produto", TXT, 46), ("Vendedores", INT, 11), ("Un. vendidas", INT, 12),
            ("Mínimo", MOEDA2, 11), ("1º quartil", MOEDA2, 11), ("Mediana", MOEDA2, 11),
            ("3º quartil", MOEDA2, 11), ("Máximo", MOEDA2, 11), ("Amplitude (máx ÷ mín)", VEZES, 12),
            ("Preço médio ponderado", MOEDA2, 13), ("Un. vendidas abaixo de 80% da mediana", INT, 16)]
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
        return lambda r: [prod, nv, f"=SUMIFS({U},{filtro(r)})", *[round(x, 2) for x in q],
                          f"=IFERROR(H{r}/D{r},0)", f"=IFERROR(SUMIFS({RC},{filtro(r)})/C{r},0)",
                          f'=SUMIFS({U},{filtro(r)},{PR},"<"&(0.8*F{r}))']

    r = tabela(ws, 1, cols, [fazer(p, nv, q) for _, p, nv, q in grupos])
    nota(ws, r + 2, "Só anúncios com venda no período e preço > 0; referências com menos de 2 "
                    "anúncios ficam de fora. Quartis e extremos usam o último preço de cada anúncio.")
    nota(ws, r + 3, "Amplitude alta = a marca não tem faixa de preço definida. A última coluna mostra "
                    "se há volume real vendido muito barato ou só anúncio de vitrine que não gira.")


def aba_evolucao(ws, ant, atu, snap_ant, snap_atu):
    ws.title = "Evolução"
    cel(ws, 1, 1, "Evolução por referência — tudo por dia, porque os períodos podem ter durações diferentes",
        fonte=FONTE_B, borda=False)
    for r, rot, s in ((2, "Período anterior", snap_ant), (3, "Período atual", snap_atu)):
        cel(ws, r, 1, rot, fonte=FONTE_B)
        cel(ws, r, 2, f"{fmt_data(s['inicio'])} a {fmt_data(s['fim'])}")
        cel(ws, r, 3, "Dias", fonte=FONTE_B)
        cel(ws, r, 4, int(s["dias"]), fmt=INT)
    cols = [("Produto", TXT, 46), ("Giro/dia anterior", DEC, 12), ("Giro/dia atual", DEC, 12),
            ("Variação do giro", PCT, 11), ("Preço médio anterior", MOEDA2, 13),
            ("Preço médio atual", MOEDA2, 13), ("Variação do preço", PCT, 11),
            ("Vendedores antes", INT, 11), ("Vendedores agora", INT, 11), ("Movimento", TXT, 16),
            ("Un. anterior (base)", INT, 12), ("Un. atual (base)", INT, 12),
            ("Faturamento anterior (base)", MOEDA, 15), ("Faturamento atual (base)", MOEDA, 15)]
    agg = lambda d: d.groupby("produto").agg(un=("un", "sum"), fat=("fat", "sum"),
                                             vend=("vendedor_id", "nunique"))
    j = agg(ant).join(agg(atu), how="outer", lsuffix="_a", rsuffix="_b").fillna(0)
    j["giro"] = j["un_b"] / snap_atu["dias"]
    j = j.sort_values(["giro", "un_a"], ascending=False, kind="mergesort")

    def fazer(prod, x):
        return lambda r: [
            prod, f"=IFERROR(K{r}/$D$2,0)", f"=IFERROR(L{r}/$D$3,0)",
            f"=IF(B{r}=0,0,IFERROR(C{r}/B{r}-1,0))",
            f"=IFERROR(M{r}/K{r},0)", f"=IFERROR(N{r}/L{r},0)",
            f"=IF(OR(E{r}=0,F{r}=0),0,IFERROR(F{r}/E{r}-1,0))",
            int(x["vend_a"]), int(x["vend_b"]),
            f'=IF(AND(B{r}=0,C{r}=0),"sem venda",IF(B{r}=0,"novo no período",IF(C{r}=0,"sumiu",'
            f'IF(D{r}>0.2,"acelerando",IF(D{r}<-0.2,"perdendo giro","estável")))))',
            int(x["un_a"]), int(x["un_b"]), float(x["fat_a"]), float(x["fat_b"])]

    r = tabela(ws, 5, cols, [fazer(p, x) for p, x in j.iterrows()])
    nota(ws, r + 2, "Movimento: sem giro antes = novo no período; sem giro agora = sumiu; "
                    "variação acima de +20% = acelerando; abaixo de −20% = perdendo giro; senão estável.")
    nota(ws, r + 3, NOTA_FAT)


def aba_anuncios(ws, df, vend):
    ws.title = "Anúncios"
    cols = [(t, f, l) for _, t, f, l in COLS_ANUNCIOS]
    d = df.sort_values(["produto", "un"], ascending=[True, False], kind="mergesort").copy()
    d["cod"] = d["vendedor_id"].map(vend["cod"])
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


def gerar_planilha_marca(con, marca):
    snaps = pd.read_sql("SELECT * FROM snapshots WHERE marca=? ORDER BY fim, inicio, id",
                        con, params=(marca,))
    if snaps.empty:
        return None
    atual = snaps.iloc[-1]
    df = pd.read_sql("SELECT * FROM anuncios WHERE snapshot_id=?", con, params=(int(atual["id"]),))
    df["gtin"] = df["gtin"].fillna("")
    vend = codigos_vendedor(df)
    dfp = df.groupby("produto").agg(un=("un", "sum"), fat=("fat", "sum"),
                                    vendedores=("vendedor_id", "nunique"))
    dfp = dfp.sort_values(["un", "fat"], ascending=False, kind="mergesort")
    n_gtin = df.loc[df["gtin"] != "", "gtin"].nunique()

    wb = Workbook()
    aba_resumo(wb.active, marca, atual, len(vend), len(dfp), n_gtin)
    if len(snaps) >= 2:
        anterior = snaps.iloc[-2]
        df_ant = pd.read_sql("SELECT * FROM anuncios WHERE snapshot_id=?", con,
                             params=(int(anterior["id"]),))
        aba_evolucao(wb.create_sheet(), df_ant, df, anterior, atual)
    aba_produtos(wb.create_sheet(), dfp, df)
    aba_gtins(wb.create_sheet(), df)
    aba_vendedores(wb.create_sheet(), df, vend)
    aba_precos(wb.create_sheet(), df)
    aba_anuncios(wb.create_sheet(), df, vend)

    destino = SAIDA / f"{slug(marca)}-explorador-de-anuncios.xlsx"
    salvar(wb, destino)
    return destino


def gerar_painel(con):
    snaps = pd.read_sql("SELECT * FROM snapshots ORDER BY marca, fim, inicio, id", con)
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
        d = pd.read_sql("SELECT vendedor_id, produto, un, fat, catalogo FROM anuncios "
                        "WHERE snapshot_id=?", con, params=(int(s["id"]),))
        todos_vend |= set(d["vendedor_id"])
        linhas.append((d["un"].sum(), nome_bonito(s["marca"]),
                       f"{fmt_data(s['inicio'])} a {fmt_data(s['fim'])}", int(s["dias"]), len(d),
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
    a = ap.parse_args()
    ini = data_valida(a.inicio) if a.inicio else None
    fim = data_valida(a.fim) if a.fim else None
    if (a.inicio and not ini) or (a.fim and not fim):
        ap.error("datas no formato AAAA-MM-DD, ex.: --inicio 2026-08-01 --fim 2026-09-16")
    if bool(ini) != bool(fim) or (ini and fim < ini):
        ap.error("informe --inicio e --fim juntos, com o fim depois do início")
    return (a.marca, ini, fim)


def main():
    informado = ler_argumentos()
    for p in (ENTRADA, SAIDA, DADOS):
        p.mkdir(parents=True, exist_ok=True)
    print("nubi — explorador de anúncios")

    arquivos = sorted(p for p in ENTRADA.iterdir() if p.is_file() and p.suffix.lower() == ".csv")
    if not arquivos:
        print(f"\n  Nenhum CSV na pasta entrada/. Coloque os exports lá e rode de novo.")
        return 0

    try:
        cfg = carregar_config()
    except ErroArquivo as e:
        print(f"\n  {e}")
        return 1

    con = abrir_banco()
    try:
        print(f"\nImportando {len(arquivos)} arquivo(s):")
        for arq in arquivos:
            try:
                importar(con, cfg, arq, informado)
            except ErroArquivo as e:
                print(f"    Não importado: {e}.")

        marcas = [m for (m,) in con.execute("SELECT DISTINCT marca FROM snapshots ORDER BY marca")]
        if not marcas:
            print("\n  Nada no histórico ainda — nenhuma planilha gerada.")
            return 0

        reconsolidar(con, cfg)
        print("\nPlanilhas geradas:")
        for marca in marcas + [None]:
            try:
                destino = gerar_planilha_marca(con, marca) if marca else gerar_painel(con)
                if destino:
                    print(f"  saida/{destino.name}")
            except ErroArquivo as e:
                print(f"  {e}.")
    finally:
        con.close()
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
