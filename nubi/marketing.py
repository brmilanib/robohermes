# -*- coding: utf-8 -*-
"""
📣 Marketing do Bazar e dos Decants (01/10, Bruno: "vídeos curtos para stories com legenda falando das notas, uma arte top para o
Instagram e o WhatsApp, legenda convencendo a comprar com esse custo baixo; tudo pronto de dentro do nubi"; Veo com teto de
US$ 20/mês).

- Vídeo do Veo (Gemini API, `predictLongRunning`): a partir da FOTO do produto, 8 s em pé (9:16), SEM texto na imagem (vídeo de
  IA erra letras); a tela do nubi desenha nome, notas e preços por cima e grava o vídeo final. Assíncrono: `veo_iniciar` devolve a
  operação; `veo_conferir` consulta até ficar pronto, baixa o vídeo e devolve os bytes. Chave só no servidor (cabeçalho).
- Teto mensal próprio (`VEO_TETO_USD`, env NUBI_VEO_TETO, padrão 20): gasto do mês em `ia_resumos` `veo|gasto|AAAA-MM`, somado
  ANTES de pedir (vídeo pedido = cobrado, mesmo que falhe depois).
- Legendas (Instagram com hashtags, WhatsApp direto): a IA escreve SÓ texto, sem números; o nubi monta o bloco de preços.
"""
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://generativelanguage.googleapis.com/v1beta"
VEO_TETO_USD = float(os.environ.get("NUBI_VEO_TETO", "20"))
VEO_SEGUNDOS = 8
# do mais barato para o mais caro; preço por segundo de vídeo (Gemini API, 720p, out/2026)
VEO_MODELOS = [m for m in os.environ.get("NUBI_VEO_MODELOS", "veo-3.1-lite-generate-preview,veo-3.1-fast-generate-preview").split(",") if m]
VEO_PRECO_S = {"lite": 0.05, "fast": 0.10}
BRASILIA = timezone(timedelta(hours=-3))


class ErroMarketing(Exception):
    pass


def _ler(repo, chave, padrao):
    r = (repo._req("GET", "ia_resumos", {"select": "texto", "chave": f"eq.{chave}"}) or [None])[0]
    try:
        return json.loads(r["texto"]) if r and r.get("texto") else padrao
    except (TypeError, ValueError):
        return padrao


def _gravar(repo, chave, valor):
    repo._req("POST", "ia_resumos", corpo=[{"chave": chave, "ia": "nubi", "criado_em": datetime.now(timezone.utc).isoformat(),
                                            "texto": json.dumps(valor, ensure_ascii=False)}],
              prefer="resolution=merge-duplicates,return=minimal")


def _mes(agora=None):
    return (agora or datetime.now(BRASILIA)).strftime("%Y-%m")


def custo_video(modelo, segundos=VEO_SEGUNDOS):
    por_s = next((v for k, v in VEO_PRECO_S.items() if k in modelo), 0.40)    # desconhecido = preço do Standard
    return round(por_s * segundos, 2)


def gasto_mes(repo, agora=None):
    g = _ler(repo, f"veo|gasto|{_mes(agora)}", {}) or {}
    return {"usd": round(float(g.get("usd") or 0), 2), "videos": int(g.get("videos") or 0), "teto": VEO_TETO_USD}


def _somar_gasto(repo, usd, agora=None):
    chave = f"veo|gasto|{_mes(agora)}"
    g = _ler(repo, chave, {}) or {}
    g = {"usd": round(float(g.get("usd") or 0) + usd, 2), "videos": int(g.get("videos") or 0) + 1}
    _gravar(repo, chave, g)
    return g


PEDIDO_VEO = """Vertical 9:16 product video for a perfume shop's Instagram story. Start from the provided photo of the product and keep
the bottle, cap, box and label EXACTLY as they are (same shape, colors and printed text; do not invent or change any letters).
Slow cinematic camera push-in, soft studio light, elegant shallow depth of field, gentle light sweeps on the glass.
Around the bottle, subtle floating elements inspired by the fragrance notes: {elementos}. Mood: {familia}.
Absolutely NO text, captions, letters, numbers, logos or watermarks added to the video. Leave the top and bottom areas calm and
uncluttered (text will be added later). Soft ambient music, no voice."""


def pedido_veo(p):
    n = p.get("notas") or {}
    elementos = ", ".join(x for x in (n.get("notas_topo"), n.get("notas_coracao"), n.get("notas_fundo")) if x) or "soft petals and light mist"
    return PEDIDO_VEO.format(elementos=elementos[:400], familia=(n.get("familia") or "luxurious, warm and elegant")[:120])


def _post(url, corpo, chave, timeout=60):
    req = urllib.request.Request(url, data=json.dumps(corpo).encode(), method="POST",
                                 headers={"x-goog-api-key": chave, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "{}")


def _get(url, chave, timeout=60, cru=False):
    req = urllib.request.Request(url, headers={"x-goog-api-key": chave})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        dados = r.read()
    return dados if cru else json.loads(dados.decode() or "{}")


def veo_iniciar(repo, p, foto, mime, post=None, agora=None):
    """Pede o vídeo ao Veo (foto → vídeo 9:16 de 8 s). Confere o teto ANTES. -> {"operacao", "modelo", "custo", "gasto"}"""
    chave = os.environ.get("GEMINI_API_KEY")
    if not chave:
        raise ErroMarketing("falta a chave do Gemini (GEMINI_API_KEY) na Vercel")
    g = gasto_mes(repo, agora)
    import base64
    corpo = {"instances": [{"prompt": pedido_veo(p), "image": {"bytesBase64Encoded": base64.b64encode(foto).decode(), "mimeType": mime}}],
             "parameters": {"aspectRatio": "9:16", "durationSeconds": VEO_SEGUNDOS, "resolution": "720p"}}
    ultimo = ""
    for modelo in VEO_MODELOS:
        custo = custo_video(modelo)
        if g["usd"] + custo > VEO_TETO_USD:
            raise ErroMarketing(f"teto do Veo no mês atingido: US$ {g['usd']:.2f} de US$ {VEO_TETO_USD:.0f} "
                                f"({g['videos']} vídeos). O vídeo grátis do nubi continua funcionando.")
        try:
            r = (post or _post)(f"{BASE}/models/{modelo}:predictLongRunning", corpo, chave)
        except urllib.error.HTTPError as e:
            ultimo = f"{modelo}: HTTP {e.code}"
            if e.code in (400, 404):                  # modelo não existe/não liberado nesta conta: tenta o próximo
                continue
            raise ErroMarketing(f"o Veo recusou o pedido ({ultimo})")
        if not r.get("name"):
            ultimo = f"{modelo}: sem operação"
            continue
        gasto = _somar_gasto(repo, custo, agora)
        return {"operacao": r["name"], "modelo": modelo, "custo": custo, "gasto": dict(gasto, teto=VEO_TETO_USD)}
    raise ErroMarketing(f"nenhum modelo do Veo aceitou o pedido ({ultimo or 'sem resposta'})")


def veo_conferir(operacao, get=None):
    """-> {"pronto": False} ou {"pronto": True, "video": bytes} ; erro do Veo vira ErroMarketing."""
    if not re.fullmatch(r"models/[\w.\-]+/operations/[\w\-]+", str(operacao or "")):
        raise ErroMarketing("operação inválida")
    chave = os.environ.get("GEMINI_API_KEY") or ""
    r = (get or _get)(f"{BASE}/{operacao}", chave)
    if not r.get("done"):
        return {"pronto": False}
    if r.get("error"):
        raise ErroMarketing(f"o Veo não fez o vídeo: {str(r['error'].get('message') or r['error'])[:200]}")
    resp = r.get("response") or {}
    amostras = ((resp.get("generateVideoResponse") or {}).get("generatedSamples") or [])
    if not amostras:
        motivo = (resp.get("generateVideoResponse") or {}).get("raiMediaFilteredReasons") or "sem vídeo na resposta"
        raise ErroMarketing(f"o Veo não devolveu vídeo ({str(motivo)[:200]})")
    uri = (amostras[0].get("video") or {}).get("uri") or ""
    if not uri.startswith("https://generativelanguage.googleapis.com/"):
        raise ErroMarketing("endereço do vídeo inesperado")
    return {"pronto": True, "video": (get or _get)(uri, chave, timeout=120, cru=True)}


# ---------- legendas ----------
PEDIDO_LEGENDAS = """Você escreve posts para a PURE PERFUMARIA (perfumes 100% originais). Produto: {tipo}.
PERFUME: {nome}
FAMÍLIA: {familia}
NOTAS DE TOPO: {topo}
NOTAS DE CORAÇÃO: {coracao}
NOTAS DE FUNDO: {fundo}
LEMBRA: {inspirado}
ARGUMENTO: {argumento}

Escreva DUAS legendas em português do Brasil, tom elegante, animado e sensorial (descreva o cheiro com as notas de um jeito fácil),
com emojis na medida:
1) "instagram": até 6 linhas + uma linha final com 6 a 10 hashtags relevantes (perfume, marca, notas, decant/promoção).
2) "whatsapp": até 4 linhas, direta, chamando para responder no grupo para reservar.
REGRAS: NÃO escreva preço, valor, desconto, ml, quantidade, porcentagem nem NENHUM número (os preços entram depois pelo sistema).
Não invente notas. Responda SÓ JSON numa linha: {{"instagram": "...", "whatsapp": "..."}}"""


def pedido_legendas(p):
    n = p.get("notas") or {}
    decant = p.get("aba") == "decant"
    tipo = "DECANT (perfume original fracionado em frasquinho)" if decant else {
        "avariada": "perfume novo com a caixa avariada (vai na caixa), preço especial",
        "sem_caixa": "perfume novo sem caixa, preço especial", "promocao": "perfume em OUTLET, preço especial"}.get(p.get("aba"), "perfume")
    argumento = ("experimentar na pele, sentir a fixação e levar na bolsa pagando pouco, antes de investir no frasco inteiro"
                 if decant else "o mesmo perfume original pagando bem menos, por pouco tempo")
    return PEDIDO_LEGENDAS.format(tipo=tipo, nome=p.get("produto") or "", familia=n.get("familia") or "-",
                                  topo=n.get("notas_topo") or "-", coracao=n.get("notas_coracao") or "-",
                                  fundo=n.get("notas_fundo") or "-", inspirado=n.get("inspirado_em") or "-", argumento=argumento)


def _sem_numeros(t):
    t = re.sub(r"(R\$\s*)?\d+([.,]\d+)?\s*(ml|reais|%|x)?", "", str(t or ""), flags=re.I)
    linhas = [re.sub(r"[ \t]{2,}", " ", l).strip() for l in t.splitlines()]
    out = []
    for l in linhas:
        if l or (out and out[-1]):
            out.append(l)
    return "\n".join(out).strip()


def legendas_do_texto(texto):
    m = re.search(r"\{.*\}", str(texto or ""), re.S)
    try:
        d = json.loads(m.group(0), strict=False) if m else {}     # IA às vezes manda quebra de linha crua no texto
    except ValueError:
        d = {}
    ig, wa = _sem_numeros(d.get("instagram"))[:2000], _sem_numeros(d.get("whatsapp"))[:1200]
    return {"instagram": ig, "whatsapp": wa} if ig and wa else {}


def bloco_precos(p, brl, preco_frasco=None):
    """Preços SEMPRE do sistema, embaixo da legenda da IA."""
    if p.get("aba") == "decant":
        ds = sorted([d for d in (p.get("decant") or []) if d.get("preco")], key=lambda d: d["ml"])
        linhas = [f"🧪 {d['ml']} ml por {brl(d['preco'])}" for d in ds]
        if preco_frasco and ds:
            linhas.append(f"💡 Sinta por {brl(ds[0]['preco'])} antes de investir {brl(preco_frasco)} no frasco!")
        return "\n".join(linhas)
    if p.get("preco_original") is None or p.get("preco_promo") is None:
        return ""
    return f"De {brl(p['preco_original'])} por apenas {brl(p['preco_promo'])} 😱🔥\n💰 Economize {brl(p['economia'])}!"


# ---------- link curto (01/10, Bruno: "um campo de link do site para colocar na legenda um link minimizado") ----------
ENCURTADORES = ("https://is.gd/create.php?format=simple&url={u}", "https://tinyurl.com/api-create.php?url={u}")


def encurtar(link, get=None):
    """Link curto pelo is.gd (senão TinyURL). Só aceita resposta https curta do próprio encurtador; falhou: o link original."""
    import urllib.parse
    import urllib.request
    if not link:
        return ""
    def _get(u):
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "nubi"}), timeout=10) as r:
            return r.read(300).decode("utf-8", "replace")
    get = get or _get
    for modelo in ENCURTADORES:
        try:
            r = (get(modelo.format(u=urllib.parse.quote(link, safe=""))) or "").strip()
        except Exception:  # noqa: BLE001 — encurtador fora: tenta o próximo
            continue
        if re.fullmatch(r"https://(is\.gd|tinyurl\.com)/[A-Za-z0-9_-]{3,40}", r):
            return r
    return link
