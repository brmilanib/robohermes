# -*- coding: utf-8 -*-
"""
Revisão diária do agrupamento do Explorador (30/09, Bruno: "isso aí o Hermes e o gpt-oss têm que revisar e otimizar todo
dia, tarefa simples e robótica").

Fluxo (tudo grátis):
1. `propor` lê a conferência do dia (`auditar_explorador`: outra marca grande, linhas parecidas, o que mais vende em
   "Outros") e pede ao gpt-oss (Ollama Cloud, cota grátis) UMA decisão por item, em JSON. Só o que vem com confiança alta
   vira proposta; fica em `ia_resumos` `revisao|<dia>` esperando o Hermes.
2. O Hermes (hermes3 no Ollama do Mac, `coletor hermes-revisao`, comando `hermes_revisao`) lê as propostas e diz se
   concorda com cada uma (`revisao_pendente` -> `revisao_hermes`).
3. `aplicar` executa só o que os dois concordam: apelido de marca (Nomes de marcas), linha nova ou linha juntada na
   Configuração da marca, e reprocessa as marcas mexidas. O resultado vai para a Sala como Hermes. O que um dos dois
   recusou fica listado para o Bruno. Nada é apagado; tudo desfaz na tela.
"""
import json
import re
from datetime import datetime, timezone

import nubi

CHAVE = "revisao|"
MAX_ITENS = 25
ACOES = {"outra_marca_grande": ("mesma_marca", "linha_da_marca", "outra_marca"),
         "linhas_parecidas": ("mesma_linha", "linhas_diferentes"),
         "outros_top": ("linha_nova", "sem_linha")}
SEM_ACAO = {"outra_marca", "linhas_diferentes", "sem_linha"}

PAPEL = ("Você revisa o agrupamento de anúncios de perfumes do Mercado Livre por marca e linha de produto (ex.: marca "
         "LATTAFA, linhas Asad, Yara, Khamrah). Regras: GTIN não erra; título, SKU e marca digitada erram. 'Linha' é o nome "
         "do perfume dentro da marca, sem tipo (EDP/EDT), volume, gênero nem palavras de anúncio (perfume, original, "
         "importado, árabe). Nome de LOJA ou de outra marca de verdade NÃO é linha nem apelido. Na dúvida, confiança baixa. "
         "Responda SOMENTE com JSON.")


def _ln(txt):
    return nubi.normalizar(txt)


def itens_da_auditoria(auditoria, cfg, limite=MAX_ITENS):
    """A conferência do dia -> lista de itens para decidir, os de mais unidades primeiro."""
    itens = []
    for a in (auditoria or {}).get("marcas") or []:
        marca = a.get("marca") or ""
        linhas = [r for _, r in (cfg.get(nubi.chave_marca(marca)) or {}).get("linhas", [])]
        for x in a.get("achados") or []:
            if x.get("corrigido") or x.get("tipo") not in ("outra_marca_grande", "linhas_parecidas"):
                continue
            itens.append({"tipo": x["tipo"], "marca": marca, "nome": x.get("nome") or "", "un": float(x.get("un") or 0),
                          "linhas": linhas[:30], "texto": x.get("texto") or ""})
        top = [t for t in (a.get("outros_top") or []) if float(t.get("un") or 0) >= 5]
        if top:
            itens.append({"tipo": "outros_top", "marca": marca, "nome": "", "un": sum(float(t["un"]) for t in top),
                          "linhas": linhas[:30], "titulos": [str(t["titulo"])[:120] for t in top[:5]]})
    itens.sort(key=lambda i: -i["un"])
    for n, i in enumerate(itens[:limite], 1):
        i["id"] = n
    return itens[:limite]


def pedido(itens):
    """O pedido em lote para o gpt-oss: uma decisão por item."""
    linhas = []
    for i in itens:
        if i["tipo"] == "outra_marca_grande":
            linhas.append(f'#{i["id"]} marca {i["marca"]}: "{i["nome"]}" aparece na coluna Marca de anúncios com {int(i["un"])} un. '
                          f'Linhas conhecidas: {", ".join(i["linhas"]) or "-"}. Ações: mesma_marca (é a própria marca escrita de outro '
                          f'jeito), linha_da_marca (é uma linha/coleção desta marca; valor = nome da linha), outra_marca (loja ou marca diferente).')
        elif i["tipo"] == "linhas_parecidas":
            a, b = (i["nome"].split(" / ") + [""])[:2]
            linhas.append(f'#{i["id"]} marca {i["marca"]}: linhas "{a}" e "{b}". Ações: mesma_linha (valor = a grafia certa) ou linhas_diferentes.')
        else:
            linhas.append(f'#{i["id"]} marca {i["marca"]}: títulos sem linha identificada: ' + " | ".join(i.get("titulos") or [])
                          + f'. Linhas conhecidas: {", ".join(i["linhas"]) or "-"}. Ações: linha_nova (valor = o nome da linha que está '
                          f'nesses títulos, 1 a 3 palavras) ou sem_linha.')
    return ("Decida cada item. Responda SOMENTE com JSON no formato "
            '{"decisoes":[{"id":1,"acao":"...","valor":"...","confianca":"alta|média|baixa","motivo":"1 frase"}]}.\n\n'
            + "\n".join(linhas))


def valor_ok(item, valor):
    """O valor proposto tem que ser nome curto, não ser a marca nem palavra de anúncio e, para linha nova, estar nos títulos."""
    v = _ln(valor)
    if not v or len(v.split()) > 4 or len(v) < 3:
        return False
    if v in nubi.palavras_da_marca(item["marca"]) or set(v.split()) <= nubi.PALAVRAS_VAZIAS:
        return False
    if item["tipo"] == "outros_top":
        return any(f" {v} " in f" {_ln(t)} " for t in item.get("titulos") or [])
    return True


def propostas_de(itens, resposta):
    """As decisões do gpt-oss -> propostas (só ação com efeito, confiança alta e valor válido)."""
    por = {i["id"]: i for i in itens}
    out = []
    for d in (resposta or {}).get("decisoes") or []:
        try:
            i = por.get(int(d.get("id")))
        except (TypeError, ValueError):
            continue
        acao = str(d.get("acao") or "").strip().lower()
        if not i or acao not in ACOES[i["tipo"]] or acao in SEM_ACAO:
            continue
        if str(d.get("confianca") or "").lower() != "alta":
            continue
        valor = str(d.get("valor") or "").strip()
        if acao == "mesma_marca":
            valor = i["nome"]
        elif acao == "linha_da_marca" and not valor:
            valor = i["nome"]
        if acao != "mesma_marca" and not valor_ok(i, valor):
            continue
        out.append({"id": i["id"], "tipo": i["tipo"], "marca": i["marca"], "nome": i["nome"], "un": i["un"], "acao": acao,
                    "valor": valor, "motivo": str(d.get("motivo") or "")[:200], "titulos": i.get("titulos") or [],
                    "linhas": i.get("linhas") or []})
    return out


def descrever(p):
    m = nubi.nome_bonito(p["marca"])
    if p["acao"] == "mesma_marca":
        return f'{m}: "{p["nome"]}" é a própria marca (vira apelido em Nomes de marcas)'
    if p["acao"] == "linha_da_marca":
        return f'{m}: "{p["nome"]}" é a linha "{p["valor"]}" da marca (apelido + linha na Configuração)'
    if p["acao"] == "mesma_linha":
        return f'{m}: linhas "{p["nome"]}" viram uma só: "{p["valor"]}"'
    return f'{m}: linha nova "{p["valor"]}" (títulos em Outros)'


def pedido_hermes(p):
    """O que o Hermes recebe para conferir UMA proposta."""
    ev = ""
    if p["tipo"] == "outros_top":
        ev = "Títulos: " + " | ".join(p.get("titulos") or [])
    return (f"Proposta do gpt-oss: {descrever(p)}. Motivo dele: {p.get('motivo') or '-'}. Linhas já conhecidas da marca: "
            f"{', '.join(p.get('linhas') or []) or '-'}. {ev}\nVocê concorda? Responda SOMENTE com JSON: "
            '{"concordo": true|false, "motivo": "1 frase"}')


def aplicar_no_config(cfg, p):
    """Muda a configuração da marca (em memória). Devolve True se mudou."""
    chave = nubi.chave_marca(p["marca"])
    linhas = cfg.setdefault(chave, {"linhas": []}).setdefault("linhas", [])
    chaves = {c for c, _ in linhas}
    if p["acao"] in ("linha_da_marca", "linha_nova"):
        k = _ln(p["valor"])
        if k in chaves:
            return False
        linhas.insert(0, [k, nubi.nome_bonito(p["valor"])])
        return True
    if p["acao"] == "mesma_linha":
        certa = nubi.nome_bonito(p["valor"])
        a, b = (p["nome"].split(" / ") + [""])[:2]
        errada = a if _ln(b) == _ln(certa) else b
        mudou = False
        for par in linhas:
            if _ln(par[1]) == _ln(errada) and par[1] != certa:
                par[1] = certa
                mudou = True
        if _ln(errada) not in chaves and _ln(errada):
            linhas.append([_ln(errada), certa])
            mudou = True
        return mudou
    return False


def registro(dia, itens, propostas, estado, ia="gpt-oss"):
    return {"dia": dia, "em": datetime.now(timezone.utc).isoformat(), "ia": ia, "itens": len(itens),
            "propostas": propostas, "estado": estado}


def resumo_sala(dia, aplicadas, recusadas, propostas):
    txt = f"🦉 **Revisão diária do agrupamento ({dia[8:10]}/{dia[5:7]})** — gpt-oss propôs, eu conferi.\n"
    if aplicadas:
        txt += "Aplicado (as marcas foram reprocessadas; desfaz em Nomes de marcas / Configuração da marca):\n" + "\n".join(f"• {d}" for d in aplicadas) + "\n"
    if recusadas:
        txt += "Não apliquei (discordei; fica para o Bruno):\n" + "\n".join(f"• {d}" for d in recusadas) + "\n"
    if not aplicadas and not recusadas:
        txt += f"{len(propostas)} proposta(s) sem veredito; nada mudou."
    return txt[:3500]


def e_mlb_lixo(txt):
    return bool(re.search(r"MLB\d{6,}", str(txt or "")))
