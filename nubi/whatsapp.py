"""💬 WhatsApp do chip da loja (03/10, Bruno): "um WhatsApp só para ele, rodando no Mac, integrado com o nubi; o Banguela
cuida de todos os atendimentos, me manda a mensagem primeiro no privado e eu aprovo ou mudo; cliente que vem do site da Via
Brazil Global ele já entende; e eu converso com o Ferreiro, o Codex ou o Hermes pelo WhatsApp".

- O `coletor whatsapp` (Mac, WhatsApp Web num Chrome só dele) lê as conversas novas e chama a rota `whatsapp_tick`.
- Cliente: `atendimento.receber` (canal "whatsapp", loja pela frase do site) → o Banguela escreve o rascunho → NADA sai
  sozinho (`atendimento.SEMPRE_APROVAR`): o rascunho vai ao Bruno no privado (do chip para o número dele) com um número.
- Bruno responde no privado: "ok" / "ok 12" = envia; "12 outro texto" ou só o texto = manda do jeito dele (ou, se o
  Banguela pediu informação, vira resposta do lojista e item da base); "não 12" = não responde.
  "Ferreiro, …" / "Codex, …" / "Hermes, …" = conversa com o agente no Mac (o coletor responde, com a memória do painel).
- O que o Bruno aprova volta no `whatsapp_tick` em `enviar` e o Mac digita devagar; depois `atendimento_enviado`.
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone

import atendimento as at

CANAL = "whatsapp"
DONO_PADRAO = "5544998812871"           # número pessoal do Bruno (03/10)
CHIP = "5547991388777"                  # o chip da loja (o mesmo do botão do site da Via Brazil Global)
AVISADOS = "whatsapp|avisados"          # ids de rascunho já mandados ao Bruno (para não repetir)
LEMBRETES = "banguela|lembretes"        # [{quando (UTC), texto, criado_em}] — assistente pessoal (03/10)
BOM_DIA = "banguela|bom_dia"            # data (Brasília) do último bom dia
AVISOS = "whatsapp|avisos"
BANGUELA_MODELO = at.SONNET     # 03/10 (Bruno): uma Banguela só — o mesmo modelo do atendimento aos clientes (Opus 5.5)              # avisos do nubi (fim de coleta, erro…) esperando a próxima volta do chip
BOM_DIA_HORA = 8
BRASILIA = timezone(timedelta(hours=-3))
LOJAS = [(re.compile(r"via\s*braz[il]{1,2}\s*global", re.I), "via_brazil")]
AGENTES = {"ferreiro": "claude", "claude": "claude", "codex": "codex", "hermes": "hermes", "banguela": "banguela"}
RE_AGENTE = re.compile(r"^\s*(ferreiro|claude|codex|hermes|banguela)\b[\s,:;.!-]*(.*)$", re.I | re.S)
RE_OK = re.compile(r"^\s*(ok|okay|sim|pode|manda|envia|aprovad[oa]|isso|👍|✅)(?:\s|[,.!:-])*#?(\d+)?\s*[.!]*\s*$", re.I)
RE_NAO = re.compile(r"^\s*(n[ãa]o|rejeit[ao]|ignora|cancela|deixa)(?:\s|[,.!:-])*#?(\d+)?\s*[.!]*\s*$", re.I)
RE_NUM = re.compile(r"^\s*#?(\d{1,7})(?:\s*[:,.\-–]\s*|\s+)(.+)$", re.S)


def dono():
    return re.sub(r"\D", "", os.environ.get("NUBI_WHATSAPP_DONO") or DONO_PADRAO)


def so_digitos(t):
    return re.sub(r"\D", "", str(t or ""))


def _base_fone(x):
    """DDD + 8 últimos dígitos: o mesmo celular com ou sem o +55 e com ou sem o 9 (o WhatsApp guarda muitos sem ele)."""
    d = so_digitos(x)
    d = d[2:] if d.startswith("55") and len(d) >= 12 else d
    return d[:2] + d[-8:] if len(d) >= 10 else ""


def eh_dono(fone_ou_nome):
    """O número que conversa com os agentes e aprova."""
    b = _base_fone(fone_ou_nome)
    return bool(b) and b == _base_fone(dono())


def loja_da_conversa(textos):
    junto = " ".join(str(t or "") for t in textos)
    return next((loja for rx, loja in LOJAS if rx.search(junto)), None)


def receber_cliente(repo, m):
    """{fone, nome, texto, historico:[{de, texto}]} lido no WhatsApp Web → rascunho do Banguela (nunca enviado sozinho)."""
    fone = so_digitos(m.get("fone"))
    externo = fone or str(m.get("nome") or "").strip()[:80]
    if not externo:
        raise ValueError("conversa sem número nem nome")
    hist = [h for h in (m.get("historico") or []) if isinstance(h, dict)][-30:]
    loja = loja_da_conversa([h.get("texto") for h in hist] + [m.get("texto")])
    if not loja:
        velha = (repo._req("GET", "atendimento_conversas", {"select": "loja", "canal": f"eq.{CANAL}", "externo_id": f"eq.{externo}"})
                 or [{}])[0]
        loja = velha.get("loja")
    nome = str(m.get("nome") or "").strip()
    cliente = nome if nome and so_digitos(nome) != fone else (f"+{fone}" if fone else nome)
    return at.receber(repo, CANAL, m.get("texto"), loja=loja or at.LOJA_PADRAO, cliente=cliente[:80], externo_id=externo,
                      historico=hist or None, pedido_dados={"fone": fone} if fone else None)


def _avisados(repo):
    r = (repo._req("GET", "ia_resumos", {"select": "texto", "chave": f"eq.{AVISADOS}"}) or [{}])[0]
    try:
        return [int(x) for x in json.loads(r.get("texto") or "[]")]
    except (TypeError, ValueError):
        return []


def _gravar_avisados(repo, ids):
    repo._req("POST", "ia_resumos", corpo=[{"chave": AVISADOS, "texto": json.dumps(ids[-300:]), "ia": "whatsapp",
                                            "criado_em": at._agora()}], prefer="resolution=merge-duplicates,return=minimal")


def _abertos(repo, lim=40, todos_canais=False):
    """Rascunhos esperando o Bruno (pendente = aprovar; precisa_info = ele responder), mais novos primeiro. Só do WhatsApp,
    ou de todos os canais (TikTok, Shopee…) quando o Bruno cita o número (03/10: "ok 172" era da Shopee e dava "não achei")."""
    rs = repo._req("GET", "atendimento_rascunhos", {"select": "id,conversa_id,mensagem_id,status,texto_gerado,pergunta_operador,criado_em",
                                                    "status": "in.(pendente,precisa_info)", "order": "id.desc", "limit": lim}) or []
    if not rs:
        return []
    conv = {c["id"]: c for c in repo._req("GET", "atendimento_conversas", {
        "select": "id,canal,cliente,loja,externo_id", "id": "in.(" + ",".join(str(r["conversa_id"]) for r in rs) + ")"}) or []}
    return [dict(r, conversa=conv[r["conversa_id"]]) for r in rs
            if r["conversa_id"] in conv and (todos_canais or conv[r["conversa_id"]].get("canal") == CANAL)]


def _msg_cliente(repo, r):
    if not r.get("mensagem_id"):
        return ""
    m = at._um(repo, "atendimento_mensagens", r["mensagem_id"]) or {}
    return str(m.get("texto") or "").strip()


def _quem(r):
    c = r.get("conversa") or {}
    loja = at.LOJA_NOMES.get(c.get("loja"), "")
    canal = "" if c.get("canal") in (None, CANAL) else (at.CANAIS[c["canal"]].nome if c["canal"] in at.CANAIS else c["canal"])
    return f"{c.get('cliente') or c.get('externo_id') or 'cliente'}" + (f" · {loja}" if loja else "") + (f" ({canal})" if canal else "")


def aviso_do_rascunho(repo, r):
    """Texto que o chip manda ao Bruno no privado."""
    msg = _msg_cliente(repo, r)[:600]
    cab = f"🦷 Banguela · #{r['id']}\n👤 {_quem(r)}\n💬 \"{msg}\""
    if r["status"] == "precisa_info":
        return (f"{cab}\n\n❓ {str(r.get('pergunta_operador') or 'Como respondo?')[:500]}\n\n"
                f"Me responda: *{r['id']} a resposta* (eu escrevo para o cliente do meu jeito e guardo na base).")
    return (f"{cab}\n\n✍️ Sugestão:\n{str(r.get('texto_gerado') or '')[:1200]}\n\n"
            f"*ok {r['id']}* = envio · *{r['id']} seu texto* = mando do seu jeito · *não {r['id']}* = não respondo")


def avisos_para_dono(repo):
    """Rascunhos novos do WhatsApp que o Bruno ainda não recebeu no privado (marca como avisados)."""
    feitos = _avisados(repo)
    novos = [r for r in reversed(_abertos(repo)) if r["id"] not in feitos]
    if not novos:
        return []
    _gravar_avisados(repo, feitos + [r["id"] for r in novos])
    return [aviso_do_rascunho(repo, r) for r in novos]


def _alvo(repo, num):
    """Rascunho a que o Bruno se refere: o número dito, senão o mais recente já avisado que ainda está aberto."""
    if num:
        r = next((r for r in _abertos(repo, 80, todos_canais=True) if r["id"] == int(num)), None)
        if not r:
            # 03/10 ("ok 3267" dava "não achei"): o atendente refaz a sugestão a cada poucos minutos e o número muda; o
            # número velho (ou o da conversa) leva à sugestão aberta mais nova da MESMA conversa
            x = at._um(repo, "atendimento_rascunhos", int(num))
            conv_id = x["conversa_id"] if x else (int(num) if at._um(repo, "atendimento_conversas", int(num)) else None)
            if conv_id:
                r = next((y for y in _abertos(repo, 200, todos_canais=True) if y["conversa_id"] == conv_id), None)
        return r, None
    abertos = _abertos(repo)
    avisados = _avisados(repo)
    return next((r for r in sorted(abertos, key=lambda x: -x["id"]) if r["id"] in avisados), None), abertos


def comando_dono(repo, texto):
    """Mensagem do Bruno no privado do chip → {resposta} (aprovação) ou {agente, texto} (conversa com o Mac)."""
    t = str(texto or "").strip()
    if not t:
        return {"resposta": None}
    ag = RE_AGENTE.match(t)
    if ag:
        if AGENTES[ag.group(1).lower()] == "banguela":      # o Banguela responde aqui mesmo (servidor), sem passar pelo Mac
            txt, ferreiro = banguela(repo, ag.group(2).strip() or t, com_acoes=True)
            return {"resposta": "🦷 Banguela:\n" + txt, "ferreiro": ferreiro}
        return {"agente": AGENTES[ag.group(1).lower()], "texto": ag.group(2).strip() or t}
    res = _aprovacao(repo, t)
    if res is not None:
        return res
    return {"agente": "claude", "texto": t}              # nada esperando: é conversa com o Ferreiro


def _aprovacao(repo, t, so_explicito=False):
    """ok / ok N / não N / N texto / (texto com algo esperando). None = não é aprovação. so_explicito (Painel): texto sem
    número nunca vira resposta ao cliente."""
    ok, nao, num = RE_OK.match(t), RE_NAO.match(t), RE_NUM.match(t)
    if ok or nao:
        r, _ = _alvo(repo, (ok or nao).group(2))
        if not r:
            return {"resposta": "Não achei mensagem esperando você. Para falar com os agentes: *Ferreiro, …*, *Codex, …* ou *Hermes, …*"}
        if nao:
            at.decidir(repo, r["id"], "rejeitar", "o Bruno não quis responder (WhatsApp)")
            return {"resposta": f"👌 #{r['id']} ({_quem(r)}): não vou responder."}
        if r["status"] == "precisa_info":
            return {"resposta": f"#{r['id']} ({_quem(r)}) precisa da sua resposta: me escreva *{r['id']} a resposta*."}
        at.decidir(repo, r["id"], "aprovar", operador="Bruno (WhatsApp)")
        return {"resposta": f"✅ #{r['id']} aprovado: envio para {_quem(r)} em instantes."}
    numero, corpo = (num.group(1), num.group(2)) if num else (None, t)
    if so_explicito and not numero:
        return None
    r, _ = _alvo(repo, numero)
    if not r and numero:
        if t.lstrip().startswith("#"):
            return {"resposta": f"Não achei a #{numero} esperando você (já foi respondida?)."}
        if so_explicito:
            return None
        numero, corpo = None, t                                # "500 unidades…": o número era parte do texto
        r, _ = _alvo(repo, None)
    if not r:
        return None
    corpo = corpo.strip()
    if r["status"] == "precisa_info":
        novo = at.responder_operador(repo, r["id"], corpo, operador="Bruno (WhatsApp)")
        return {"resposta": f"📝 #{r['id']}: anotei e guardei na base. "
                            + ("Já te mando a sugestão nova." if (novo.get("rascunho") or {}).get("status") == "pendente"
                               else "Vou montar a resposta com isso.")}
    at.decidir(repo, r["id"], "editar", corpo, operador="Bruno (WhatsApp)")
    return {"resposta": f"✅ #{r['id']}: mando o seu texto para {_quem(r)}."}


PAPEL_BANGUELA = """Você é a Banguela: cuida do atendimento das lojas do Bruno (Pure Perfumaria, Essence Prime e a importadora Via
Brazil Global) e é a ASSISTENTE PESSOAL dele. Agora você conversa com o BRUNO (dono), não com cliente.
Converse como uma pessoa inteligente e próxima: natural, calorosa, com opinião, entendendo o que ele quis dizer mesmo que
venha curto, com erro de digitação ou por áudio transcrito. Nada de respostas prontas ou de menu ("para falar com os
agentes, digite…"). Se não entendeu, pergunte de um jeito humano. Responda o que ele perguntou primeiro; depois, se fizer
sentido, ofereça o próximo passo. Português do Brasil, texto simples (pode usar *negrito* de WhatsApp), sem tabela.
Se o CONTEXTO tem acao_que_voce_acabou_de_fazer, conte em uma frase o que foi feito.
Use SÓ o CONTEXTO: a fila do atendimento, as vendas de hoje, o ADS, a base de conhecimento do nubi e os lembretes.
Não invente número, conversa nem compromisso; se não está no contexto, diga que não sabe e onde dá para ver.
SAC (WhatsApp, TikTok, Shopee): cada sugestão esperando tem um número N (é o "n" do contexto; muda quando o atendente refaz a
sugestão, então use sempre o "n" atual do contexto). Quando o Bruno
MANDA responder de outro jeito (ex.: "primeiro pede o número do pedido dela"), escreva o texto novo para o cliente e, numa
linha sozinha, [[editar:N|o texto exato para o cliente]] — ele sai na hora. Quando ele só diz para enviar a sugestão que
está lá ("pode mandar", "manda essa"), use [[aprovar:N]]. Na dúvida sobre QUAL conversa, pergunte o número.
VOCÊ É A MESMA Banguela que atende os clientes: o que o Bruno te ensina aqui (política, prazo, preço de atacado, como
responder um caso) tem que valer no atendimento. Quando ele disser algo que serve para responder clientes, grave numa
linha sozinha [[base:LOJA|a pergunta do cliente, do jeito que ele perguntaria|a resposta certa, como a loja responde]]
(LOJA = todas, principal ou via_brazil) e diga que guardou.
LEMBRETE: se ele pedir para lembrar de algo, escreva numa linha sozinha [[lembrete:AAAA-MM-DD HH:MM|o que lembrar]] (horário
de Brasília; "amanhã cedo" = 08:00; sem hora = 09:00) e confirme em uma frase. Para desmarcar: [[desmarcar:trecho do texto]].
FERREIRO: código, coleta, robôs, telas do nubi e erros são com o Ferreiro (Claude Code no Mac). Se o Bruno pedir algo assim,
ou você precisar dele, escreva numa linha sozinha [[ferreiro:o pedido completo, com o contexto]] e diga que passou para ele
(a resposta dele chega no WhatsApp do Bruno)."""

PAPEL_BOM_DIA = """Você é o Banguela, assistente do Bruno. Escreva o BOM DIA dele para o WhatsApp, curto (até 900 caracteres), em
tópicos com emoji: lembretes de hoje, como foram as vendas de ontem, o que está esperando ele no atendimento e qualquer
alerta do CONTEXTO. Só números do CONTEXTO; se algo não veio, não fale disso. Comece com "Bom dia, Bruno!"."""


def _ler(repo, chave, padrao):
    r = (repo._req("GET", "ia_resumos", {"select": "texto", "chave": f"eq.{chave}"}) or [{}])[0]
    try:
        return json.loads(r["texto"]) if r.get("texto") else padrao
    except (TypeError, ValueError):
        return padrao


def _gravar(repo, chave, valor):
    repo._req("POST", "ia_resumos", corpo=[{"chave": chave, "texto": json.dumps(valor, ensure_ascii=False), "ia": "banguela",
                                            "criado_em": at._agora()}], prefer="resolution=merge-duplicates,return=minimal")


def _agora_br(agora=None):
    return (agora or datetime.now(timezone.utc)).astimezone(BRASILIA)


def _contexto_negocio(repo, pergunta, agora=None):
    """Números do nubi para a assistente: vendas de hoje (UpSeller), ADS do ML, base de conhecimento e lembretes."""
    ctx = {"agora_brasilia": _agora_br(agora).strftime("%A %d/%m/%Y %H:%M")}
    try:
        import vendas_hoje
        tv = vendas_hoje.tv(repo, agora)
        ctx["vendas_hoje"] = {k: tv.get(k) for k in ("ate_agora", "ate_agora_comparar", "projecao", "ultima_hora", "lojas", "campeoes")
                              if tv.get(k) is not None}
    except Exception:  # noqa: BLE001
        pass
    try:
        ads = _ler(repo, "ads_ml|principal", {})
        ctx["ads_mercado_livre"] = {k: ads.get(k) for k in ("hoje", "ontem", "mes", "mes_fechado", "atualizado_em") if k in ads}
    except Exception:  # noqa: BLE001
        pass
    if pergunta:
        try:
            import saber
            ctx["base_de_conhecimento"] = [{"titulo": x.get("titulo"), "texto": str(x.get("texto") or x.get("trecho") or "")[:500]}
                                           for x in saber.buscar(repo, pergunta, 6)]
        except Exception:  # noqa: BLE001
            pass
    ctx["lembretes"] = [{"quando": _agora_br(datetime.fromisoformat(x["quando"])).strftime("%d/%m %H:%M"), "texto": x["texto"]}
                        for x in _ler(repo, LEMBRETES, [])][:20]
    return ctx


def _acoes_banguela(repo, txt):
    """[[lembrete:…]] grava; [[desmarcar:…]] apaga; [[ferreiro:…]] volta para o Mac. Devolve (texto limpo, pedidos ao Ferreiro)."""
    lembretes = _ler(repo, LEMBRETES, [])
    mudou = False
    for quando, oque in re.findall(r"\[\[lembrete:\s*(\d{4}-\d{2}-\d{2}[ T]\d{1,2}:\d{2})\s*\|([^\]]+)\]\]", txt):
        try:
            dt = datetime.strptime(quando.replace("T", " "), "%Y-%m-%d %H:%M").replace(tzinfo=BRASILIA)
        except ValueError:
            continue
        lembretes.append({"quando": dt.astimezone(timezone.utc).isoformat(), "texto": oque.strip()[:500], "criado_em": at._agora()})
        mudou = True
    for trecho in re.findall(r"\[\[desmarcar:([^\]]+)\]\]", txt):
        antes = len(lembretes)
        lembretes = [x for x in lembretes if trecho.strip().lower() not in x["texto"].lower()]
        mudou = mudou or len(lembretes) != antes
    if mudou:
        _gravar(repo, LEMBRETES, sorted(lembretes, key=lambda x: x["quando"])[:200])
    ferreiro = [x.strip() for x in re.findall(r"\[\[ferreiro:([^\]]+)\]\]", txt) if x.strip()]
    return re.sub(r"\[\[[^\]]+\]\]", "", txt).strip(), ferreiro


def banguela(repo, texto, historico=None, agora=None, com_acoes=False):
    """O Banguela conversando com o Bruno (Painel do coletor ou "Banguela, …" no WhatsApp): conversa de verdade (Opus),
    com o histórico; aprova/muda respostas, marca lembretes e passa pedidos ao Ferreiro como AÇÕES dentro da resposta.
    03/10 (Bruno: "ela é robótica"): nada de resposta pronta; "ok N"/"N texto" exatos são feitos na hora e ela comenta.
    com_acoes=True devolve (texto, pedidos_ao_ferreiro)."""
    t = str(texto or "").strip()
    feito_ja = None
    m = RE_OK.match(t) or RE_NAO.match(t)
    alvo_n = m.group(2) if m else (RE_NUM.match(t).group(1) if RE_NUM.match(t) else None)
    if alvo_n:                                                 # só com número: sem número, ela pergunta qual
        res = _aprovacao(repo, t, so_explicito=True)
        if res and not str(res.get("resposta") or "").startswith(("Não achei", "#")):
            feito_ja = res.get("resposta")
    abertos = _abertos(repo, 20, todos_canais=True)
    try:
        resumo = at.painel(repo, dias=1)
    except Exception:  # noqa: BLE001
        resumo = {}
    ctx = {"esperando_voce_no_atendimento": [{"n": r["id"], "cliente": _quem(r), "tipo": "aprovar" if r["status"] == "pendente" else "precisa_de_voce",
                                           "mensagem": _msg_cliente(repo, r)[:300], "sugestao": str(r.get("texto_gerado") or "")[:400],
                                           "pergunta": str(r.get("pergunta_operador") or "")[:300]} for r in abertos[:10]],
           "painel_do_sac_hoje": resumo, **_contexto_negocio(repo, t, agora)}
    conversa = "\n".join(f"{'BRUNO' if h.get('role') == 'user' else 'BANGUELA'}: {str(h.get('content'))[:600]}"
                         for h in (historico or [])[-8:])
    if feito_ja:
        ctx["acao_que_voce_acabou_de_fazer"] = feito_ja
    pedido = f"CONTEXTO:\n{json.dumps(ctx, ensure_ascii=False, default=str)[:9000]}\n\nCONVERSA ATÉ AGORA:\n{conversa}\nBRUNO: {t}"
    try:
        txt, _ = at.gerar_qualidade(repo, BANGUELA_MODELO)(pedido, PAPEL_BANGUELA)
    except Exception as e:  # noqa: BLE001
        txt = f"(não consegui pensar agora: {str(e)[:150]})"
    limpo, ferreiro = _acoes_banguela(repo, str(txt or ""))
    feitos = []
    for num, novo in re.findall(r"\[\[editar:\s*#?(\d+)\s*\|([^\]]+)\]\]", str(txt or "")):
        res = _aprovacao(repo, f"{num} {novo.strip()}", so_explicito=True)       # mesmo caminho do "N texto"
        if res:
            feitos.append(res.get("resposta") or "")
    for loja, perg, resp in re.findall(r"\[\[base:\s*([a-z_]*)\s*\|([^|\]]+)\|([^\]]+)\]\]", str(txt or "")):
        try:                                     # o que o Bruno ensina vale para o atendimento dos clientes na hora
            at.salvar_item_kb(repo, loja or "todas", perg.strip()[:500], resp.strip()[:2000], operador="Bruno (pela Banguela)",
                              tags=["ensinado_pelo_bruno"])
            feitos.append(f"📚 Guardei na base do atendimento: “{perg.strip()[:80]}”")
        except Exception:  # noqa: BLE001
            pass
    for num in re.findall(r"\[\[aprovar:\s*#?(\d+)\s*\]\]", str(txt or "")):
        res = _aprovacao(repo, f"ok {num}", so_explicito=True)
        if res:
            feitos.append(res.get("resposta") or "")
    if feito_ja and feito_ja not in feitos:
        feitos.insert(0, feito_ja)
    if feitos:
        limpo = (limpo + "\n\n" + "\n".join(feitos)).strip()
    if ferreiro and not com_acoes:
        limpo += "\n\n(Passe o pedido ao Ferreiro pelo WhatsApp ou pelo chat dele aqui no Painel.)"
    return (limpo[:3000], ferreiro) if com_acoes else limpo[:3000]


def enfileirar_aviso(repo, texto):
    """Aviso do nubi para o WhatsApp do Bruno: sai pelo chip na próxima volta do Mac (até 30 guardados)."""
    _gravar(repo, AVISOS, (_ler(repo, AVISOS, []) + [str(texto)[:1500]])[-30:])


def avisos_pendentes(repo):
    xs = _ler(repo, AVISOS, [])
    if xs:
        _gravar(repo, AVISOS, [])
    return xs


def lembretes_vencidos(repo, agora=None):
    """Lembretes cuja hora chegou (saem da lista)."""
    agora = agora or datetime.now(timezone.utc)
    todos = _ler(repo, LEMBRETES, [])
    vencidos = [x for x in todos if datetime.fromisoformat(x["quando"]) <= agora]
    if vencidos:
        _gravar(repo, LEMBRETES, [x for x in todos if x not in vencidos])
    return [f"⏰ Lembrete: {x['texto']}" for x in vencidos]


def bom_dia(repo, agora=None):
    """Uma vez por dia, a partir das 8h de Brasília: o resumo do dia no WhatsApp do Bruno (None = ainda não é hora/já foi)."""
    br = _agora_br(agora)
    if br.hour < BOM_DIA_HORA or br.hour >= 12 or _ler(repo, BOM_DIA, "") == br.date().isoformat():
        return None
    _gravar(repo, BOM_DIA, br.date().isoformat())
    abertos = _abertos(repo, 20)
    ctx = dict(_contexto_negocio(repo, "", agora), esperando_voce_no_sac=len(abertos))
    hoje = br.date()
    ctx["lembretes_de_hoje"] = [x for x in ctx.get("lembretes", []) if x["quando"].startswith(hoje.strftime("%d/%m"))]
    try:
        txt, _ = at.gerar_qualidade(repo)(f"CONTEXTO:\n{json.dumps(ctx, ensure_ascii=False, default=str)[:9000]}", PAPEL_BOM_DIA)
    except Exception:  # noqa: BLE001
        return None
    return "☀️ " + re.sub(r"\[\[[^\]]+\]\]", "", str(txt or "")).strip()[:1500]


def tick(repo, d):
    """Rota whatsapp_tick (Mac → nubi): clientes novos, mensagens do Bruno; volta o que enviar e o que avisar."""
    erros, recebidos = [], 0
    do_dono = list(d.get("dono") or [])
    for m in (d.get("clientes") or [])[:30]:
        try:
            if eh_dono(m.get("fone")) or eh_dono(m.get("nome")):     # o Mac ainda não sabia o número do Bruno
                do_dono.append({"texto": m.get("texto")})
                continue
            receber_cliente(repo, m)
            recebidos += 1
        except Exception as e:  # noqa: BLE001 — uma conversa ruim não trava as outras
            erros.append(f"{m.get('nome') or m.get('fone')}: {str(e)[:150]}")
    ao_dono, agentes = [], []
    for m in do_dono[:10]:
        try:
            r = comando_dono(repo, m.get("texto"))
        except Exception as e:  # noqa: BLE001
            r = {"resposta": f"Não consegui: {str(e)[:200]}"}
        if r.get("agente"):
            agentes.append({"agente": r["agente"], "texto": r["texto"]})
        elif r.get("resposta"):
            ao_dono.append(r["resposta"])
        agentes += [{"agente": "claude", "texto": f"(pedido do Bruno, passado pelo Banguela) {x}"} for x in r.get("ferreiro") or []]
    for extra in (lambda: avisos_pendentes(repo), lambda: lembretes_vencidos(repo), lambda: [bom_dia(repo)]):
        try:
            ao_dono += [x for x in extra() if x]
        except Exception as e:  # noqa: BLE001
            erros.append(f"assistente: {str(e)[:150]}")
    ao_dono += avisos_para_dono(repo)
    enviar = [{"id": x["id"], "fone": so_digitos(x.get("externo_id")), "cliente": x.get("cliente"), "texto": x["texto"]}
              for x in at.para_enviar(repo, CANAL)]
    return {"dono_fone": dono(), "ao_dono": ao_dono, "agentes": agentes, "enviar": enviar, "recebidos": recebidos, "erros": erros}


def rota(repo, metodo, nome, q, corpo):
    d = json.loads(corpo or b"{}") if metodo == "POST" else {}
    if nome == "whatsapp_tick" and metodo == "POST":
        return tick(repo, d)
    if nome == "whatsapp_banguela" and metodo == "POST":     # chat do Painel do coletor com o Banguela
        return {"texto": banguela(repo, d.get("texto"), d.get("historico") if isinstance(d.get("historico"), list) else None)}
    if nome == "whatsapp_estado" and metodo == "POST":       # o Mac conta como está o WhatsApp (conectado, QR, erro)
        repo._req("POST", "ia_resumos", corpo=[{"chave": "whatsapp|estado", "texto": json.dumps(d)[:4000], "ia": "whatsapp",
                                                "criado_em": at._agora()}], prefer="resolution=merge-duplicates,return=minimal")
        return {"ok": True}
    if nome == "whatsapp_estado":
        r = (repo._req("GET", "ia_resumos", {"select": "texto,criado_em", "chave": "eq.whatsapp|estado"}) or [{}])[0]
        try:
            return dict(json.loads(r.get("texto") or "{}"), visto_em=r.get("criado_em"))
        except ValueError:
            return {}
    raise ValueError("rota do WhatsApp desconhecida")
