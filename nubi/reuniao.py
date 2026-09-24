# -*- coding: utf-8 -*-
"""
Sala de reunião dos agentes (como um grupo de WhatsApp).

Quem fala: o dono (voce), ChatGPT, DeepSeek e Claude. A cada mensagem do dono (ou na reunião diária depois da
auditoria), o ChatGPT e o DeepSeek dão a opinião deles e o Claude fecha: responde, decide e registra o que vai para
desenvolvimento (tarefas e sugestões em reuniao_tarefas). Todos seguem a decisão do Claude.
@chatgpt / @deepseek na mensagem: só esse(s) agente(s) opinam antes do Claude.
"""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import ia

AGENTES = {"chatgpt": "ChatGPT", "deepseek": "DeepSeek", "claude": "Claude"}
STATUS = ["proposta", "aprovada", "em_desenvolvimento", "feita", "recusada"]

CONTEXTO = (
    "Vocês são os agentes do nubi, um sistema de análise de vendas de perfumes no Mercado Livre: um coletor (Python + "
    "Playwright no Mac mini do dono) baixa do Nubimetrics as vendas de 16 vendedores concorrentes (mês, mesmo período, "
    "venda isolada de cada dia, tabela do grupo com visitas e conversão) e o ranking de marcas; o site (Python na Vercel "
    "+ Supabase) mostra vendas diárias, comparação de concorrentes, alertas de estoque, ranking e categorias de marca, e "
    "a IA escreve resumos diários, semanais e mensais. O código é escrito pelo Claude (sessão de código); a próxima fase "
    "é conectar as lojas do dono (Mercado Livre, Shopee, Amazon, TikTok Shop) e monitorar o ranking dos anúncios dele.\n"
    "Regras do projeto: zero erro nos números (na dúvida, 'sem dados', nunca zero inventado); toda correção publicada "
    "roda na hora; nunca guardar senhas nem chaves; nada muda sozinho em produção sem teste.\n")


def _historico(msgs, n=30):
    return "\n".join(f"[{m['autor']}] {m['texto'][:1500]}" for m in msgs[-n:])


def _tarefas_txt(tarefas):
    abertas = [t for t in tarefas if t["status"] in ("proposta", "aprovada", "em_desenvolvimento")]
    return "\n".join(f"#{t['id']} [{t['status']}/{t['prioridade']}] {t['titulo']}" for t in abertas[:40]) or "nenhuma"


def participantes(texto):
    """Quem opina antes do Claude: os citados com @, senão todos os que têm chave."""
    t = (texto or "").lower()
    citados = [k for k in ("chatgpt", "deepseek") if f"@{k}" in t]
    base = citados or ["chatgpt", "deepseek"]
    return [k for k in base if ia.tem(k)]


def _opinar(qual, historico, tarefas, extra):
    papel = {"chatgpt": "Você é o ChatGPT, engenheiro de dados do nubi: foque em dados, números e análise.",
             "deepseek": "Você é o DeepSeek, engenheiro de software do nubi: foque em código, desempenho, custo e riscos técnicos."}[qual]
    t, _, _ = ia.perguntar(
        CONTEXTO + papel + " Está num grupo com o dono e os outros agentes; o Claude coordena e decide no final.\n"
        "Responda à última mensagem do grupo como numa conversa de WhatsApp: curto (até 6 linhas), direto, em português, "
        "com a sua opinião e no máximo 2 sugestões concretas. Não repita o que outro agente já disse; discorde se tiver "
        "motivo. Não invente números.\n"
        f"{extra}\nTAREFAS EM ABERTO:\n{tarefas}\n\nCONVERSA:\n{historico}",
        web=False, max_tokens=700, qual=qual)
    return t.strip()


def _decidir(historico, tarefas, opinioes, extra):
    """Claude fecha a rodada: resposta ao grupo + tarefas (novas ou mudanças de status) em JSON."""
    qual = "claude" if ia.tem("claude") else ("chatgpt" if ia.tem("chatgpt") else None)
    if not qual:
        raise ia.SemIA("nenhuma IA configurada")
    pedido = (
        CONTEXTO + "Você é o Claude, coordenador dos agentes do nubi: você decide e todos seguem a sua decisão. "
        "Leia a conversa e as opiniões desta rodada, responda ao grupo (curto, até 8 linhas, português, tom de WhatsApp, "
        "dizendo o que foi decidido e por quê) e registre o que vai para desenvolvimento.\n"
        "Critérios: prioridade para o que evita erro nos números e para o que o dono pediu; recuse o que for arriscado, "
        "caro ou fora do escopo, explicando; não crie tarefa repetida (veja as tarefas em aberto); tarefa = algo concreto "
        "que o Claude da sessão de código consegue implementar e testar.\n"
        f"{extra}\nTAREFAS EM ABERTO:\n{tarefas}\n\nCONVERSA:\n{historico}\n\nOPINIÕES DESTA RODADA:\n"
        + ("\n".join(f"[{k}] {v}" for k, v in opinioes.items()) or "nenhuma")
        + '\n\nResponda SOMENTE com um JSON: {"resposta": "<mensagem para o grupo>", "tarefas": [{"titulo": "<curto>", '
        '"descricao": "<o que fazer e como saber que está pronto>", "tipo": "tarefa|sugestao|decisao", '
        '"status": "aprovada|proposta|recusada", "prioridade": "alta|media|baixa", "area": "<coletor|dados|site|ia|outro>", '
        '"proposto_por": "<quem sugeriu>"}], "atualizar": [{"id": <número da tarefa em aberto>, "status": "<novo status>", '
        '"nota": "<por quê>"}]}. Listas vazias quando não houver nada.')
    j, _, q = ia.perguntar_json(pedido, web=False, max_tokens=1800, qual=qual)
    if not j.get("resposta"):
        raise ia.SemIA("o coordenador não devolveu a decisão")
    return j, q


def rodada(repo, texto_dono=None, extra="", autor_extra=None):
    """
    Uma rodada da reunião: grava a mensagem (do dono ou do sistema), coleta as opiniões e a decisão do Claude,
    grava tudo e as tarefas. Devolve as mensagens novas.
    """
    agora = lambda: datetime.now(timezone.utc).isoformat()
    novas = []

    def gravar(autor, texto, meta=None):
        r = repo._req("POST", "reuniao_mensagens", corpo=[{"autor": autor, "texto": texto[:8000], "meta": meta,
                                                           "criado_em": agora()}], prefer="return=representation")
        novas.append(r[0] if r else {"autor": autor, "texto": texto})
        return novas[-1]
    if texto_dono:
        gravar(autor_extra or "voce", texto_dono)
    msgs = repo._todos("reuniao_mensagens", {"select": "id,autor,texto,criado_em", "order": "id"})[-60:]
    tarefas = repo._todos("reuniao_tarefas", {"select": "*", "order": "id.desc"})
    hist, tt = _historico(msgs), _tarefas_txt(tarefas)
    quem = participantes(texto_dono or "")
    opinioes = {}
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = {k: ex.submit(_opinar, k, hist, tt, extra) for k in quem}
        for k, f in futs.items():
            try:
                opinioes[AGENTES[k]] = f.result(timeout=170)
            except Exception as e:  # noqa: BLE001
                gravar("sistema", f"{AGENTES[k]} não respondeu: {str(e)[:200]}")
    for k in quem:
        if AGENTES[k] in opinioes:
            gravar(AGENTES[k], opinioes[AGENTES[k]])
    try:
        j, q = _decidir(hist + "".join(f"\n[{k}] {v}" for k, v in opinioes.items()), tt, opinioes, extra)
    except Exception as e:  # noqa: BLE001
        gravar("sistema", f"O coordenador não respondeu: {str(e)[:200]}")
        return novas
    coord = "Claude" if q == "claude" else f"{AGENTES.get(q, q)} (no lugar do Claude)"
    msg = gravar(coord, str(j["resposta"]), {"decisao": True})
    registradas = []
    ja = {re.sub(r"\W+", " ", t["titulo"].lower()).strip() for t in tarefas if t["status"] != "recusada"}
    for t in (j.get("tarefas") or [])[:8]:
        if not str(t.get("titulo") or "").strip():
            continue
        chave = re.sub(r"\W+", " ", str(t["titulo"]).lower()).strip()
        if chave in ja:
            continue                                   # a mesma tarefa já está registrada
        ja.add(chave)
        reg = {"titulo": str(t["titulo"])[:200], "descricao": str(t.get("descricao") or "")[:2000],
               "tipo": t.get("tipo") if t.get("tipo") in ("tarefa", "sugestao", "decisao") else "tarefa",
               "status": t.get("status") if t.get("status") in STATUS else "proposta",
               "prioridade": t.get("prioridade") if t.get("prioridade") in ("alta", "media", "baixa") else "media",
               "area": str(t.get("area") or "")[:40], "proposto_por": str(t.get("proposto_por") or "")[:40],
               "decidido_por": coord, "mensagem_id": msg.get("id"), "criado_em": agora(), "atualizado_em": agora()}
        repo._req("POST", "reuniao_tarefas", corpo=[reg], prefer="return=minimal")
        registradas.append(f"{reg['titulo']} ({reg['status']})")
    abertas = {t["id"] for t in tarefas}
    for u in (j.get("atualizar") or [])[:10]:
        try:
            tid = int(u.get("id"))
        except (TypeError, ValueError):
            continue
        if tid in abertas and u.get("status") in STATUS:
            repo._req("PATCH", "reuniao_tarefas", {"id": f"eq.{tid}"},
                      corpo={"status": u["status"], "notas": str(u.get("nota") or "")[:500], "atualizado_em": agora()},
                      prefer="return=minimal")
            registradas.append(f"#{tid} -> {u['status']}")
    if registradas:
        gravar("sistema", "📋 Registrado em Desenvolvimento: " + "; ".join(registradas))
    return novas
