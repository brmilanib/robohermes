# -*- coding: utf-8 -*-
"""
Mini-benchmark interno (card #15): nenhum modelo novo entra em produção sem passar por aqui.

Roda o conjunto FIXO e versionado de casos (VERSAO + CASOS, com entrada determinística e gabarito) num modelo candidato,
com as MESMAS funções de produção (pedido e formato do resumo do dia, produtos_iguais.agrupar, custo por ia_precos), e
grava 1 linha por caso e modelo em ia_benchmark_execucoes (os casos da versão ficam em ia_benchmark_casos). Não muda
nenhum modelo em produção: o modelo vai fixo em cada chamada, sem trocar de provedor.

Modelo candidato = "provedor:modelo" (claude:claude-sonnet-5, chatgpt:gpt-5.1, deepseek:deepseek-v4-pro,
ollama:gpt-oss:120b) para o resumo e o alerta; "embed:text-embedding-3-large" para a junção de produtos (a produção junta
por embeddings). Cada rodada só roda os tipos que o modelo faz em produção; o resto aparece como "não se aplica".

Medidas: latência = time.perf_counter em volta do caso inteiro; tokens = soma do uso relatado pelo provedor em cada
chamada; custo = tokens × ia_precos (nubi_web.custo_usd). Uma chamada sem uso relatado ou modelo sem preço cadastrado
deixa o custo NULL (nunca estimado, nunca zero).

Critério de acerto por tipo (definido aqui para o card):
- resumo_dia: JSON no formato fixo (schema do resumo) com as 8 seções e cada termo de gabarito["cita"] no texto.
  nota = fração dos termos citados (0 com JSON fora do formato).
- alerta: a seção "Alertas" do mesmo resumo (texto de alerta de produção). Acerta quando (1) cita todo produto de
  gabarito["cita"], (2) não cita nenhum de gabarito["nao_cita"] (produto que está bem nos dados) e (3) todo número do
  texto existe na entrada (nenhum número inventado). nota = fração das 3 condições.
- juncao: F1 dos PARES de títulos juntos (dois itens no mesmo grupo = 1 par; precisão = pares certos / pares juntados,
  recall = pares certos / pares do gabarito; nenhum par nos dois lados = 1). Acerta com F1 >= F1_MIN. nota = F1.
"""

import itertools
import re
import time
import unicodedata
from datetime import datetime, timezone

import ia
import nubi_web
import produtos_iguais

VERSAO = "v1"
F1_MIN = 0.9
MAX_TOKENS = 2600                                   # o mesmo do resumo do dia em produção

_DIA = ("VENDA ISOLADA DO DIA 20/09/2026 (export só do dia):\n"
        "- LOJA AROMA: R$ 12.400 no dia (média dos 7 dias anteriores R$ 8.000). Itens: Lattafa Asad 100ml EDP "
        "R$ 5.100 (30 un.); Armaf Club De Nuit Intense Man 105ml R$ 2.300 (9 un.).\n"
        "- PERFUMES BR: R$ 3.000 no dia (média dos 7 dias anteriores R$ 6.500). Itens: Lattafa Khamrah 100ml "
        "R$ 1.900 (8 un.); Armaf Club De Nuit Intense Man 105ml: 0 un. (anúncios pausados).\n"
        "MÊS (01 a 20/09 x 01 a 20/08): LOJA AROMA R$ 190 mil x R$ 160 mil; PERFUMES BR R$ 120 mil x R$ 140 mil.\n"
        "ALERTAS DE ESTOQUE EM ABERTO (maiores): Club De Nuit Intense Man 105ml (Armaf): sem estoque em PERFUMES BR; "
        "ainda vendem 1; R$ 600/dia parado")
_ALERTA = ("VENDA ISOLADA DO DIA 21/09/2026 (export só do dia):\n"
           "- LOJA AROMA: R$ 9.000 no dia (média dos 7 dias anteriores R$ 9.100). Item que mais vendeu: Lattafa Asad 100ml "
           "R$ 4.000 (24 un.).\n"
           "- PERFUMES BR: R$ 6.400 no dia (média dos 7 dias anteriores R$ 6.300).\n"
           "ALERTAS DE ESTOQUE EM ABERTO (maiores): Club De Nuit Intense Man 105ml (Armaf): sem estoque em PERFUMES BR, "
           "LOJA AROMA; ainda vendem 1; R$ 800/dia parado; Khamrah 100ml (Lattafa): sem estoque em LOJA AROMA; "
           "ainda vendem 3; R$ 450/dia parado")
_ITENS = [{"chave": "6291108735411", "titulo": "Perfume Lattafa Asad Eau De Parfum 100ml Masculino", "marca": "Lattafa", "v": 900},
          {"chave": "T:asad edp 100 ml original", "titulo": "Asad Lattafa Edp 100 Ml Original Lacrado", "marca": "Lattafa", "v": 300},
          {"chave": "T:perfume arabe asad 100ml", "titulo": "Perfume Arabe Asad 100ml Lattafa Masculino", "marca": "Lattafa", "v": 200},
          {"chave": "T:asad bourbon edp 100ml", "titulo": "Asad Bourbon Lattafa Edp 100ml", "marca": "Lattafa", "v": 150},
          {"chave": "6291108737897", "titulo": "Lattafa Khamrah Eau De Parfum 100ml", "marca": "Lattafa", "v": 700},
          {"chave": "T:khamrah 100ml edp", "titulo": "Khamrah Lattafa 100ml Edp Original", "marca": "Lattafa", "v": 250},
          {"chave": "T:khamrah qahwa edp 100ml", "titulo": "Lattafa Khamrah Qahwa Edp 100ml", "marca": "Lattafa", "v": 120}]

CASOS = [
    {"caso": "resumo_dia_1", "tipo": "resumo_dia", "entrada": {"dados": _DIA},
     "gabarito": {"cita": ["LOJA AROMA", "PERFUMES BR", "Asad", "Club De Nuit"]}},
    {"caso": "alerta_1", "tipo": "alerta", "entrada": {"dados": _ALERTA},
     "gabarito": {"cita": ["Club De Nuit", "Khamrah"], "nao_cita": ["Asad"]}},
    {"caso": "juncao_1", "tipo": "juncao", "entrada": {"itens": _ITENS},
     "gabarito": {"grupos": [["6291108735411", "T:asad edp 100 ml original", "T:perfume arabe asad 100ml"],
                             ["6291108737897", "T:khamrah 100ml edp"]]}},
]
TIPOS = ("resumo_dia", "alerta", "juncao")


def _norm(t):
    t = unicodedata.normalize("NFKD", str(t or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if not unicodedata.combining(c)))


def numeros(t):
    """Valores numéricos de um texto em português (1.234,5 -> 1234.5; 'R$ 1,2 mil' -> 1200)."""
    out = set()
    for m in re.finditer(r"(\d+(?:[.,]\d+)*)(\s*(?:mil\b|mi\b|milh))?", str(t or "")):
        s = m.group(1)
        s = s.replace(".", "").replace(",", ".") if "," in s or re.fullmatch(r"\d{1,3}(\.\d{3})+", s) else s
        try:
            v = float(s)
        except ValueError:
            continue
        mult = (m.group(2) or "").strip()
        out.add(round(v * (1000 if mult == "mil" else 1e6 if mult else 1), 4))
    return out


def pares(grupos):
    return {frozenset(p) for g in grupos for p in itertools.combinations(sorted(set(g)), 2)}


def f1(previstos, gabarito):
    if not previstos and not gabarito:
        return 1.0
    certos = len(previstos & gabarito)
    if not certos:
        return 0.0
    p, r = certos / len(previstos), certos / len(gabarito)
    return round(2 * p * r / (p + r), 4)


def _texto_secao(j, tipo):
    return " ".join(i.get("texto") or "" for s in (j or {}).get("secoes") or [] if s.get("tipo") == tipo
                    for i in s.get("itens") or [])


def avaliar(caso, saida):
    """(acerto, nota) da saída do modelo contra o gabarito do caso."""
    g = caso["gabarito"]
    if caso["tipo"] == "juncao":
        nota = f1(pares(saida), pares(g["grupos"]))
        return nota >= F1_MIN, nota
    if ia.erros_schema(saida, nubi_web._schema_secoes(nubi_web.SECOES_DIA)):
        return False, 0.0
    if caso["tipo"] == "resumo_dia":
        texto = _norm(" ".join(_texto_secao(saida, s[0]) for s in nubi_web.SECOES_DIA))
        tem = {s for s in nubi_web.SECOES_DIA if _texto_secao(saida, s[0]).strip()}
        citados = sum(1 for c in g["cita"] if _norm(c) in texto)
        nota = round(citados / len(g["cita"]), 4)
        return len(tem) == len(nubi_web.SECOES_DIA) and citados == len(g["cita"]), nota
    texto = _texto_secao(saida, "alerta")
    ok = [all(_norm(c) in _norm(texto) for c in g["cita"]),
          not any(_norm(c) in _norm(texto) for c in g.get("nao_cita") or []),
          bool(texto.strip()) and numeros(texto) <= numeros(caso["entrada"]["dados"])]
    return all(ok), round(sum(ok) / len(ok), 4)


def _executar(caso, prov, modelo):
    """Saída do modelo para o caso, pelas funções de produção."""
    if caso["tipo"] == "juncao":
        itens = caso["entrada"]["itens"]
        res, _ = produtos_iguais.agrupar(itens, ia.embeddings([produtos_iguais.texto_embedding(x) for x in itens], modelo))
        grupos = {}
        for k, (g, _) in res.items():
            grupos.setdefault(g, {g}).add(k)
        return [sorted(x) for x in grupos.values()]
    secoes = nubi_web.SECOES_DIA
    j, _ = ia.perguntar_estruturado(nubi_web._pedido_resumo_dia(caso["entrada"]["dados"]) + "\n" + nubi_web._formato_secoes(secoes),
                                    nubi_web._schema_secoes(secoes), "resumo_nubi", max_tokens=MAX_TOKENS, qual=prov, modelo=modelo)
    return j


def _separar(candidato):
    prov, _, modelo = str(candidato or "").strip().partition(":")
    if not modelo or prov not in ("claude", "chatgpt", "deepseek", "ollama", "embed"):
        raise nubi_web.ErroNuvem("Modelo candidato no formato provedor:modelo (claude, chatgpt, deepseek, ollama ou embed).")
    return prov, modelo


def rodar(repo, candidato, versao=VERSAO):
    """Roda os casos da versão no candidato e grava 1 linha por caso em ia_benchmark_execucoes."""
    if versao != VERSAO:
        raise nubi_web.ErroNuvem(f"Versão de casos desconhecida: {versao} (atual: {VERSAO}).")
    prov, modelo = _separar(candidato)
    casos = [c for c in CASOS if (c["tipo"] == "juncao") == (prov == "embed")]
    agora_ = datetime.now(timezone.utc).isoformat()
    repo._req("POST", "ia_benchmark_casos", corpo=[{"id": f"{versao}|{c['caso']}", "versao_casos": versao, "caso": c["caso"],
                                                    "tipo": c["tipo"], "entrada": c["entrada"], "gabarito": c["gabarito"]}
                                                   for c in CASOS], prefer="resolution=merge-duplicates,return=minimal")
    precos = nubi_web._precos(repo)
    rodada = f"{agora_[:19]}|{candidato}"
    antes = dict(ia.USO)
    linhas = []
    for c in casos:
        chamadas = []

        def gravar(fase, d, _prev=antes.get("gravar")):
            if fase == "fim":
                chamadas.append(d)
            return _prev(fase, d) if _prev else None   # continua registrando em agentes_uso quando ligado
        ia.USO.update({"gravar": gravar, "origem": f"benchmark {versao} {c['caso']}"})
        saida = erro = None
        t0 = time.perf_counter()
        try:
            saida = _executar(c, "chatgpt" if prov == "embed" else prov, modelo)
        except Exception as e:  # noqa: BLE001 — erro do modelo conta como erro do caso (acerto falso)
            erro = str(e)[:300]
        finally:
            latencia = int((time.perf_counter() - t0) * 1000)
            ia.USO.update({k: antes.get(k) for k in ("gravar", "origem")})
        ok = [x for x in chamadas if x.get("ok")]
        sem_uso = not ok or any(x.get("tokens_in") is None for x in ok)
        custos = [nubi_web.custo_usd(precos, x) for x in ok]
        acerto, nota = avaliar(c, saida) if erro is None else (False, 0.0)
        linhas.append({"rodada": rodada, "versao_casos": versao, "caso_id": f"{versao}|{c['caso']}", "tipo": c["tipo"],
                       "modelo": candidato, "modelo_api": (ok[-1].get("modelo") if ok else None) or modelo,
                       "latencia_ms": latencia,
                       "tokens_in": None if sem_uso else sum((x.get("tokens_in") or 0) + (x.get("cache_read_tokens") or 0)
                                                             + (x.get("cache_creation_tokens") or 0) for x in ok),
                       "tokens_out": None if sem_uso else sum(x.get("tokens_out") or 0 for x in ok),
                       "custo_usd": None if sem_uso or None in custos else round(sum(custos), 6),
                       "acerto": acerto, "nota": nota, "erro": erro,
                       "saida": saida if isinstance(saida, (dict, list)) else None, "criado_em": agora_})
    repo._req("POST", "ia_benchmark_execucoes", corpo=linhas, prefer="return=minimal")
    return {"rodada": rodada, "versao": versao, "execucoes": linhas}


def comparar(repo, versao=VERSAO, modelos=()):
    """Comparação lado a lado lida da tabela: a última rodada de cada modelo (sem misturar tentativas), por tipo."""
    rs = repo._todos("ia_benchmark_execucoes", {"select": "rodada,modelo,tipo,latencia_ms,tokens_in,tokens_out,custo_usd,acerto,nota,erro",
                                                "versao_casos": f"eq.{versao}", "order": "rodada.desc"})
    ultima = {}
    for r in rs:
        ultima.setdefault(r["modelo"], r["rodada"])
    modelos = [m for m in (modelos or sorted(ultima)) if m in ultima]
    por = {}
    for m in modelos:
        xs = [r for r in rs if r["modelo"] == m and r["rodada"] == ultima[m]]
        for t in TIPOS:
            ys = [r for r in xs if r["tipo"] == t]
            if not ys:
                por.setdefault(m, {})[t] = None    # tipo que o modelo não faz em produção: não se aplica
                continue
            custos = [r.get("custo_usd") for r in ys]
            por.setdefault(m, {})[t] = {
                "casos": len(ys), "acertos": sum(1 for r in ys if r.get("acerto")),
                "nota": round(sum(float(r.get("nota") or 0) for r in ys) / len(ys), 4),
                "latencia_ms": round(sum(r["latencia_ms"] for r in ys) / len(ys)),
                "custo_usd": None if None in custos else round(sum(float(c) for c in custos), 6),   # um NULL = sem dados
                "erros": sum(1 for r in ys if r.get("erro"))}
    return {"versao": versao, "modelos": modelos, "rodadas": {m: ultima[m] for m in modelos}, "por_tipo": por,
            "tabela": tabela(modelos, por)}


def tabela(modelos, por):
    """Markdown: uma coluna por modelo; linhas = acerto, latência e custo de cada tipo."""
    def cel(x, campo):
        if x is None:
            return "não se aplica"
        if campo == "acerto":
            return f"{x['acertos']}/{x['casos']} (nota {x['nota']:.2f})".replace(".", ",")
        if campo == "latencia_ms":
            return f"{x['latencia_ms']} ms"
        return "sem dados" if x["custo_usd"] is None else f"US$ {x['custo_usd']:.4f}".replace(".", ",")
    out = ["| Métrica | " + " | ".join(modelos) + " |", "|---|" + "---|" * len(modelos)]
    for t in TIPOS:
        for campo, nome in (("acerto", "acerto"), ("latencia_ms", "latência"), ("custo_usd", "custo")):
            out.append(f"| {t} · {nome} | " + " | ".join(cel(por[m][t], campo) for m in modelos) + " |")
    return "\n".join(out)
