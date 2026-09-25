# -*- coding: utf-8 -*-
"""
Sala de reunião dos agentes (como um grupo de WhatsApp).

Quem fala: o dono (voce), os agentes de agentes.AGENTES (ChatGPT/Codex, DeepSeek; Hermes depois) e o Claude. A cada mensagem do dono (ou na reunião diária depois da
auditoria), o ChatGPT e o DeepSeek dão a opinião deles e o Claude fecha: responde, decide e registra o que vai para
desenvolvimento (tarefas e sugestões em reuniao_tarefas). Todos seguem a decisão do Claude.
@chatgpt / @deepseek (a chave do agente) na mensagem: só esse(s) agente(s) opinam antes do Claude.
"""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import agentes
import ia

AGENTES = {k: a["nome"] for k, a in agentes.AGENTES.items()} | {"claude": "Claude"}
STATUS = ["proposta", "aprovada", "em_desenvolvimento", "em_teste", "feita", "recusada"]


def _historico(msgs, n=30):
    return "\n".join(f"[{m['autor']}] {m['texto'][:1500]}" for m in msgs[-n:])


def _tarefas_txt(tarefas):
    abertas = [t for t in tarefas if t["status"] in ("proposta", "aprovada", "em_desenvolvimento")]
    return "\n".join(f"#{t['id']} [{t['status']}/{t['prioridade']}] {t['titulo']}" for t in abertas[:40]) or "nenhuma"


def participantes(texto):
    """Quem opina antes do Claude: os citados com @, senão todos os que têm chave."""
    t = (texto or "").lower()
    return agentes.ativos([k for k in agentes.AGENTES if f"@{k}" in t])


def _opinar(qual, historico, tarefas, extra):
    return agentes.perguntar(
        qual,
        "Você está no grupo com o dono e os outros agentes; o Claude coordena e decide no final.\n"
        "Responda à última mensagem do grupo como numa conversa de WhatsApp: curto (até 6 linhas), direto, "
        "com a sua opinião e no máximo 2 sugestões concretas. Não repita o que outro agente já disse.\n"
        f"{extra}\nTAREFAS EM ABERTO:\n{tarefas}\n\nCONVERSA:\n{historico}", max_tokens=900)


def _comentar(qual, extra, opinioes_texto):
    """2ª volta (reunião diária): cada agente lê o que os outros já disseram e comenta curto, sem repetir a própria opinião."""
    return agentes.perguntar(
        qual,
        "Você já deu sua opinião nesta reunião. Agora leia o que os outros agentes disseram e comente em até 3 linhas "
        "algo específico: concorde, discorde ou complemente — não repita a sua opinião anterior.\n"
        f"{extra}\nOPINIÕES DESTA RODADA:\n{opinioes_texto}", max_tokens=400)


def _decidir(historico, tarefas, opinioes, extra):
    """Claude fecha a rodada: resposta ao grupo + tarefas (novas ou mudanças de status) em JSON."""
    qual = "claude" if ia.tem("claude") else ("chatgpt" if ia.tem("chatgpt") else None)
    if not qual:
        raise ia.SemIA("nenhuma IA configurada")
    pedido = (
        "Você é o Claude, coordenador dos agentes do nubi: você decide e todos seguem a sua decisão. "
        + agentes.voz("claude") +
        "Leia a conversa e as opiniões desta rodada, responda ao grupo (curto, até 8 linhas, português, tom de WhatsApp, "
        "dizendo o que foi decidido e por quê) e registre o que vai para desenvolvimento.\n"
        "Você não executa nada: não diga que pediu coleta, rodou ou corrigiu algo; diga o que foi decidido e registre "
        "como tarefa (quem executa é o Claude da sessão de código e os agentes do despachante).\n"
        "Aprovação: o Bruno delegou a você aprovar as tarefas de risco BAIXO ou MÉDIO (status 'aprovada'). Classifique o "
        "risco de cada tarefa: ALTO quando mexe em dinheiro/custo relevante, senhas/chaves/acessos, apagar ou reescrever "
        "dados, estrutura do banco, coletor/login do Nubimetrics, publicação para clientes ou decisões de negócio do Bruno; "
        "MÉDIO quando muda telas ou regras de cálculo com teste; BAIXO para ajustes pequenos, textos, testes e documentação. "
        "Risco ALTO fica 'proposta' com a pergunta para o Bruno em 'pergunta'. Revise também as propostas em aberto e aprove "
        "as de risco baixo/médio que fizerem sentido (em 'atualizar').\n"
        "Critérios: prioridade para o que evita erro nos números e para o que o dono pediu; recuse o que for arriscado, "
        "caro ou fora do escopo, explicando; não crie tarefa repetida (veja as tarefas em aberto); tarefa = algo concreto "
        "que o Claude da sessão de código consegue implementar e testar.\n"
        f"{extra}\nTAREFAS EM ABERTO:\n{tarefas}\n\nCONVERSA:\n{historico}\n\nOPINIÕES DESTA RODADA:\n"
        + ("\n".join(f"[{k}] {v}" for k, v in opinioes.items()) or "nenhuma")
        + '\n\nResponda SOMENTE com um JSON: {"resposta": "<mensagem para o grupo>", "tarefas": [{"titulo": "<curto>", '
        '"descricao": "<o que fazer e como saber que está pronto>", "tipo": "tarefa|sugestao|decisao", '
        '"status": "aprovada|proposta|recusada", "risco": "baixo|medio|alto", "motivo_risco": "<1 frase>", '
        '"pergunta": "<só se risco alto: o que o Bruno precisa decidir>", "prioridade": "alta|media|baixa", '
        '"area": "<coletor|dados|site|ia|outro>", "proposto_por": "<quem sugeriu>"}], "atualizar": [{"id": <número da '
        'tarefa proposta>, "status": "aprovada|recusada", "risco": "baixo|medio|alto", "nota": "<por quê>"}]}. '
        'Listas vazias quando não houver nada.')
    j, _, q = ia.perguntar_json(pedido, web=False, max_tokens=2500, qual=qual, sistema=agentes.SISTEMA)
    if not j.get("resposta"):
        raise ia.SemIA("o coordenador não devolveu a decisão")
    return j, q


# Dúvida entre agentes ligada a um card (sem tabela/coluna nova: usa reuniao_mensagens.meta e tarefa_eventos)
LIMITE_DUVIDAS_DIA = 20
DESIGN_RE = re.compile(r"layout|design|\bux\b|\bui\b|tela|navega|menu|visual|celular|mobile|responsiv|cabe[çc]alho", re.I)
DADOS_RE = re.compile(r"n[úu]mero|total|venda|c[áa]lcul|conta|reconcilia|dados|pre[çc]o|custo|estoque|coleta|banco|desempenho|token|schema|json", re.I)
CODIGO_RE = re.compile(r"c[óo]digo|fun[çc][ãa]o\b|endpoint|rota\b|\bbug\b|deploy|refatora|implementa[çc][ãa]o|teste automatizado", re.I)
HISTORICO_RE = re.compile(r"hist[óo]rico|mem[óo]ria|j[áa] decidiu|j[áa] foi discutido|precedente|aprendizado|caixa de conhecimento", re.I)


class ErroDuvida(Exception):
    pass


def _especialista(texto, para=None):
    """Quem responde: quem foi citado (@nome) ou o especialista do assunto; None = só o coordenador responde."""
    p = str(para or "").lower().strip("@ ")
    if p in agentes.AGENTES or p == "hermes":
        return p
    if DESIGN_RE.search(texto):
        return "astra"
    if DADOS_RE.search(texto):
        return "deepseek"
    if CODIGO_RE.search(texto):
        return "chatgpt"
    if HISTORICO_RE.search(texto):
        return "hermes"
    return None


def duvida(repo, tarefa_id, texto, quem="claude_code", para=None):
    """
    Uma dúvida ligada a um card: grava na Sala, chama o coordenador + 1 especialista (1 rodada só) e copia a
    melhor resposta como passo no card. Devolve o texto da decisão.
    """
    agora = lambda: datetime.now(timezone.utc).isoformat()
    texto = str(texto or "").strip()[:2000]
    if not texto:
        raise ErroDuvida("Escreva a dúvida.")
    if not ia.tem("claude"):
        raise ErroDuvida("Coordenador (Claude) não configurado.")
    hoje = datetime.now(timezone.utc).date().isoformat()
    ja_hoje = repo._req("GET", "reuniao_mensagens", {"select": "id", "meta->>tipo": "eq.duvida", "criado_em": f"gte.{hoje}"}) or []
    if len(ja_hoje) >= LIMITE_DUVIDAS_DIA:
        raise ErroDuvida(f"Limite de {LIMITE_DUVIDAS_DIA} dúvidas por dia na Sala; ela entra na pauta da próxima reunião.")
    especialista = _especialista(texto, para)
    msg = repo._req("POST", "reuniao_mensagens", corpo=[{"autor": quem, "texto": texto,
                    "meta": {"tipo": "duvida", "tarefa_id": tarefa_id, "para": especialista}, "criado_em": agora()}],
                    prefer="return=representation")
    duvida_id = (msg or [{}])[0].get("id")
    resposta_esp, nome_esp, hermes_async = "", "", False
    if especialista == "hermes":
        # Hermes roda no Mac mini (Ollama local) e só posta na Sala pelo despachante (assíncrono);
        # não dá pra chamar na hora daqui. O coordenador decide com o que já sabe e avisa que pode faltar resposta.
        nome_esp, hermes_async = "Hermes", True
    elif especialista in agentes.AGENTES and ia.tem(agentes.AGENTES[especialista]["qual"]):
        nome_esp = agentes.AGENTES[especialista]["nome"]
        try:
            resposta_esp = agentes.perguntar(especialista, f"DÚVIDA de outro agente sobre o card #{tarefa_id}:\n{texto}", max_tokens=900)
        except Exception:  # noqa: BLE001
            resposta_esp = ""
        if resposta_esp.strip():
            repo._req("POST", "reuniao_mensagens", corpo=[{"autor": nome_esp, "texto": resposta_esp,
                      "meta": {"tipo": "resposta_duvida", "duvida_id": duvida_id, "tarefa_id": tarefa_id}, "criado_em": agora()}],
                      prefer="return=minimal")
    pedido = (
        agentes.voz("claude") +
        "Você é o Claude, coordenador dos agentes do nubi. Um agente abriu uma dúvida ligada a um card de desenvolvimento "
        "(não é a reunião nem uma tarefa nova). Dê a MELHOR RESPOSTA, curta (até 6 linhas), objetiva, para quem vai "
        f"implementar o card.\nCARD #{tarefa_id}\nDÚVIDA: {texto}\n"
        + (f"\nRESPOSTA DE {nome_esp}: {resposta_esp}\n" if resposta_esp.strip() else "")
        + ("\nHermes (histórico/memória) foi citado, mas ele só responde de forma assíncrona pelo Mac mini: decida com o "
           "que você já sabe e diga que a resposta dele, se vier, chega depois na Sala.\n" if hermes_async else "")
        + "\n\nResponda só o texto da decisão, em português, sem JSON e sem repetir a dúvida.")
    decisao, _, _ = ia.perguntar(pedido, web=False, max_tokens=700, qual="claude", sistema=agentes.SISTEMA)
    decisao = decisao.strip()
    if not decisao:
        raise ErroDuvida("o coordenador não respondeu à dúvida")
    repo._req("POST", "reuniao_mensagens", corpo=[{"autor": "Claude", "texto": decisao,
              "meta": {"tipo": "decisao", "duvida_id": duvida_id, "tarefa_id": tarefa_id}, "criado_em": agora()}],
              prefer="return=minimal")
    repo._req("POST", "tarefa_eventos", corpo=[{"tarefa_id": tarefa_id, "autor": "claude", "tipo": "passo",
              "texto": f"💬 Dúvida na Sala: {texto[:300]}\n➡️ {decisao[:1500]}", "criado_em": agora()}], prefer="return=minimal")
    repo._req("PATCH", "reuniao_tarefas", {"id": f"eq.{tarefa_id}"}, corpo={"atualizado_em": agora()}, prefer="return=minimal")
    return decisao


# Travas que valem mesmo se a IA classificar errado: isso sempre vai para o Bruno aprovar
RISCO_ALTO = re.compile(r"senha|chave d[ae] api|api key|chave secreta|token de acesso|access token|cookie|credencia|acesso d[eo]|apagar|excluir|deletar|delete|drop |truncate|"
                        r"migra[çc][ãa]o d[oe] banco|schema do banco|estrutura do banco|drop table|alter table|pagamento|cobran[çc]a|cart[ãa]o|compra|pre[çc]o de venda|"
                        r"login do nubimetrics|publicar para|clientes? externo|vender para marcas|contrato", re.I)


def avaliar_risco(t):
    """(aprovar?, risco, motivo). A IA sugere; a trava de palavras e o risco alto sempre mandam para o dono."""
    risco = str(t.get("risco") or "medio").lower().replace("é", "e")
    risco = risco if risco in ("baixo", "medio", "alto") else "medio"
    texto = f"{t.get('titulo', '')} {t.get('descricao', '')}"
    if RISCO_ALTO.search(texto):
        return False, "alto", "mexe em algo sensível (" + RISCO_ALTO.search(texto).group(0) + ")"
    return risco != "alto", risco, str(t.get("motivo_risco") or "")[:200]


def rodada(repo, texto_dono=None, extra="", autor_extra=None, segunda_volta=False):
    """
    Uma rodada da reunião: grava a mensagem (do dono ou do sistema), coleta as opiniões (e, se segunda_volta, um
    comentário curto de cada agente sobre o que os outros disseram) e a decisão do Claude, grava tudo e as tarefas.
    Devolve as mensagens novas.
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
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {k: ex.submit(_opinar, k, hist, tt, extra) for k in quem}
        for k, f in futs.items():
            try:
                opinioes[AGENTES[k]] = f.result(timeout=170)
            except Exception as e:  # noqa: BLE001
                gravar("sistema", f"{AGENTES[k]} não respondeu: {str(e)[:200]}")
    for k, v in list(opinioes.items()):
        if not (v or "").strip():
            del opinioes[k]
            gravar("sistema", f"{k} não respondeu: resposta vazia")
    for k in quem:
        if AGENTES[k] in opinioes:
            gravar(AGENTES[k], opinioes[AGENTES[k]])
    if segunda_volta and len(opinioes) > 1:
        opinioes_texto = "\n".join(f"[{k}] {v}" for k, v in opinioes.items())
        comentarios = {}
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {k: ex.submit(_comentar, k, extra, opinioes_texto) for k in quem if AGENTES[k] in opinioes}
            for k, f in futs.items():
                try:
                    comentarios[AGENTES[k]] = f.result(timeout=120)
                except Exception as e:  # noqa: BLE001
                    gravar("sistema", f"{AGENTES[k]} não comentou na 2ª volta: {str(e)[:200]}")
        for k, v in list(comentarios.items()):
            if not (v or "").strip():
                del comentarios[k]
        for k in quem:
            if AGENTES[k] in comentarios:
                gravar(AGENTES[k], comentarios[AGENTES[k]], {"segunda_volta": True})
        for k, v in comentarios.items():
            if k in opinioes:
                opinioes[k] = f"{opinioes[k]}\n(2ª volta) {v}"
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
               "status": "proposta",
               "prioridade": t.get("prioridade") if t.get("prioridade") in ("alta", "media", "baixa") else "media",
               "area": str(t.get("area") or "")[:40], "proposto_por": str(t.get("proposto_por") or "")[:40],
               "decidido_por": coord, "mensagem_id": msg.get("id"), "criado_em": agora(), "atualizado_em": agora()}
        # risco baixo/médio: o Claude aprova sozinho (delegação do Bruno); alto: fica esperando o Bruno
        ok, risco, motivo = avaliar_risco(t)
        reg["risco"] = risco
        if t.get("status") == "recusada":
            reg["status"] = "recusada"
        elif t.get("status") == "aprovada" and ok:
            reg["status"], reg["decidido_por"] = "aprovada", f"{coord} (automático, risco {risco})"
        elif risco == "alto":
            reg["aguardando"] = (str(t.get("pergunta") or "").strip() or f"Risco alto: {motivo}. Aprova?")[:500]
        repo._req("POST", "reuniao_tarefas", corpo=[reg], prefer="return=minimal")
        registradas.append(f"{reg['titulo']} ({reg['status']}{', risco ' + risco if reg['status'] != 'recusada' else ''})")
    # o coordenador só mexe no que ainda é proposta (recusar); o que o dono aprovou ou está em código não volta atrás
    abertas = {t["id"] for t in tarefas if t["status"] == "proposta"}
    for u in (j.get("atualizar") or [])[:10]:
        try:
            tid = int(u.get("id"))
        except (TypeError, ValueError):
            continue
        if tid not in abertas or u.get("status") not in ("aprovada", "recusada"):
            continue
        reg = {"status": u["status"], "notas": str(u.get("nota") or "")[:500], "atualizado_em": agora()}
        if u["status"] == "aprovada":
            orig = next(t for t in tarefas if t["id"] == tid)
            ok, risco, motivo = avaliar_risco(dict(orig, risco=u.get("risco"), motivo_risco=u.get("nota")))
            if not ok:
                repo._req("PATCH", "reuniao_tarefas", {"id": f"eq.{tid}"}, corpo={"risco": "alto", "atualizado_em": agora(),
                          "aguardando": f"Risco alto: {motivo}. Aprova?"[:500]}, prefer="return=minimal")
                registradas.append(f"#{tid} espera o Bruno (risco alto)")
                continue
            reg.update(risco=risco, decidido_por=f"{coord} (automático, risco {risco})")
        repo._req("PATCH", "reuniao_tarefas", {"id": f"eq.{tid}"}, corpo=reg, prefer="return=minimal")
        registradas.append(f"#{tid} -> {u['status']}")
    if registradas:
        gravar("sistema", "📋 Registrado em Desenvolvimento: " + "; ".join(registradas))
    return novas
