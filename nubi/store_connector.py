# -*- coding: utf-8 -*-
"""
StoreConnector (card #1): contrato base para os conectores de loja (ML, Shopee, Amazon,
TikTok, ...) e a gravação idempotente dos pedidos no Supabase.

Cada conector real (próximos cards) herda de StoreConnector e implementa fetch_orders e
fetch_ads_ranking; a gravação sempre passa por persistir_pedidos, que faz upsert pela
chave única (source, id_externo) — pedido processado 2x fica só 1 registro. A idempotência
de fetch_ads_ranking não está no escopo deste card.

Dry-run obrigatório (card #2): todo conector novo roda em dry-run por padrão (não grava
no Supabase, só loga local). A escrita real só acontece com os dois flags explícitos:
dry_run=False e checklist_aprovado_por_bruno=True. Nenhuma rotina automática muda esses
flags; é o Bruno quem aprova o checklist manual antes de ligar a escrita de uma loja.

Retry isolado por conector (card #3): coletar_lojas roda cada loja na sua própria thread, com
retry/backoff exponencial + jitter e Retry-After (conector levanta ErroRateLimit no 429).
Falha ou rate-limit numa loja não para nem atrasa as outras; a loja que falhar volta como
"pendente" com erro e tentativas, e dados=None (nunca zero, fica fora dos totais).
"""

import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

BRASILIA = timezone(timedelta(hours=-3))


class ErroConector(Exception):
    pass


class ErroRateLimit(ErroConector):
    """HTTP 429 da loja. retry_after: valor do cabeçalho Retry-After (segundos ou data HTTP), se veio."""

    def __init__(self, mensagem="HTTP 429", retry_after=None):
        super().__init__(mensagem)
        self.retry_after = retry_after


class StoreConnector:
    """Interface que todo conector de loja implementa. source identifica a loja (ex.: "mercado_livre")."""

    source = None

    def fetch_orders(self, **kwargs):
        raise NotImplementedError

    def fetch_ads_ranking(self, **kwargs):
        raise NotImplementedError


def normalizar_flag(valor, default):
    """Converte valor (bool, str vinda de config/env, número, ou None) num bool, tratando
    qualquer valor vazio como "ainda não decidido" (usa default), nunca como desligado:
    sem o bug de bool("false") == True; string vazia, None, 0 e contêiner vazio ([]/{}) usam
    o default; "false"/"0"/"nao"/"não" (string) é False; qualquer outro valor truthy é True."""
    if valor is None:
        return default
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        texto = valor.strip().lower()
        if texto == "":
            return default
        return texto not in ("false", "0", "nao", "não")
    if not valor:
        return default
    return True


def _logar_dry_run(source, pedidos, motivo):
    agora = datetime.now(BRASILIA).strftime("%d/%m %H:%M")
    ids = [str(p.get("id_externo")) for p in pedidos]
    print(f"{agora} [dry-run:{source}] {motivo} — {len(pedidos)} pedido(s) não gravados: {ids}", flush=True)


def persistir_pedidos(repo, source, pedidos, dry_run=None, checklist_aprovado_por_bruno=None):
    """Grava pedidos de uma loja em store_orders, idempotente por (source, id_externo).

    pedidos: lista de dicts com id_externo (obrigatório), status (opcional) e dados (dict opcional).
    Pedido sem id_externo não é gravado e vira aviso. Retorna (quantos gravados, lista de avisos).

    dry_run (ligado por padrão, valor ausente/None/vazio conta como dry-run) e
    checklist_aprovado_por_bruno (desligado por padrão): a escrita real só ocorre com os dois
    flags explícitos (dry_run=False e checklist_aprovado_por_bruno=True); qualquer outra
    combinação fica em dry-run e só loga local, sem gravar nada no Supabase.
    """
    source = (source or "").strip()
    if not source:
        raise ErroConector("source obrigatório para gravar pedidos.")
    efetivo_dry_run = normalizar_flag(dry_run, True)
    checklist = normalizar_flag(checklist_aprovado_por_bruno, False)
    if efetivo_dry_run:
        _logar_dry_run(source, pedidos, "dry-run")
        return 0, [f"dry-run: {len(pedidos)} pedido(s) não gravados (checklist pendente)" if not checklist
                    else f"dry-run: {len(pedidos)} pedido(s) não gravados"]
    if not checklist:
        _logar_dry_run(source, pedidos, "checklist pendente")
        return 0, [f"checklist pendente: {len(pedidos)} pedido(s) não gravados"]
    agora = datetime.now(timezone.utc).isoformat()
    corpo, avisos = [], []
    for p in pedidos:
        bruto = p.get("id_externo")
        id_ext = "" if bruto is None else str(bruto).strip()
        if not id_ext:
            avisos.append(f"Pedido sem id_externo ignorado: {p}")
            continue
        corpo.append({"source": source, "id_externo": id_ext, "status": p.get("status"),
                      "dados": p.get("dados") or {}, "atualizado_em": agora})
    if corpo:
        repo._req("POST", "store_orders", corpo=corpo, prefer="resolution=merge-duplicates,return=minimal")
    return len(corpo), avisos


def segundos_retry_after(valor, agora=None):
    """Retry-After em segundos (aceita "120" ou data HTTP); None se ausente ou ilegível."""
    if valor is None:
        return None
    texto = str(valor).strip()
    try:
        return max(0.0, float(texto))
    except ValueError:
        pass
    try:
        quando = parsedate_to_datetime(texto)
    except (TypeError, ValueError):
        return None
    if quando is None:
        return None
    return max(0.0, (quando - (agora or datetime.now(timezone.utc))).total_seconds())


def espera_backoff(tentativa, inicial, maximo, jitter, aleatorio=random.random):
    """Espera antes da tentativa k (k >= 2): min(maximo, inicial * 2^(k-2)) * (1 + U(0, jitter))."""
    return min(maximo, inicial * 2 ** (tentativa - 2)) * (1 + aleatorio() * jitter)


def _nome_loja(conector):
    return getattr(conector, "source", None) or type(conector).__name__


def coletar_com_retry(conector, metodo="fetch_orders", max_tentativas=3, backoff_inicial_s=2, backoff_max_s=60,
                      jitter=0.25, dormir=time.sleep, aleatorio=random.random, **kwargs):
    """Chama conector.<metodo>(**kwargs) com retry; nunca levanta. Retorna dict com source, status
    ("ok" ou "pendente"), dados (None se pendente, nunca zero), tentativas, erro e aviso."""
    source = _nome_loja(conector)
    erro = None
    for tentativa in range(1, max_tentativas + 1):
        if tentativa > 1:
            espera = espera_backoff(tentativa, backoff_inicial_s, backoff_max_s, jitter, aleatorio)
            retry_after = segundos_retry_after(getattr(erro, "retry_after", None))
            dormir(espera if retry_after is None else max(retry_after, espera))
        try:
            dados = getattr(conector, metodo)(**kwargs)
            return {"source": source, "status": "ok", "dados": dados, "tentativas": tentativa, "erro": None,
                    "aviso": None}
        except Exception as e:  # noqa: BLE001 — erro de uma loja não pode derrubar as outras
            erro = e
    return {"source": source, "status": "pendente", "dados": None, "tentativas": max_tentativas,
            "erro": f"{type(erro).__name__}: {erro}"[:500],
            "aviso": f"Coleta pendente: não foi possível concluir a coleta de {source} "
                     f"({max_tentativas} tentativa(s))."}


def coletar_lojas(conectores, metodo="fetch_orders", **opcoes):
    """Coleta todas as lojas em paralelo (uma thread "coleta-<source>" por loja), cada uma com retry
    próprio. Retorna {source: resultado de coletar_com_retry}."""
    if not conectores:
        return {}

    def rodar(conector):
        threading.current_thread().name = f"coleta-{_nome_loja(conector)}"
        return coletar_com_retry(conector, metodo, **opcoes)

    with ThreadPoolExecutor(max_workers=len(conectores)) as ex:
        return {r["source"]: r for r in ex.map(rodar, conectores)}
