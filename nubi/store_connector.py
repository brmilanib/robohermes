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
"""

from datetime import datetime, timedelta, timezone

BRASILIA = timezone(timedelta(hours=-3))


class ErroConector(Exception):
    pass


class StoreConnector:
    """Interface que todo conector de loja implementa. source identifica a loja (ex.: "mercado_livre")."""

    source = None

    def fetch_orders(self, **kwargs):
        raise NotImplementedError

    def fetch_ads_ranking(self, **kwargs):
        raise NotImplementedError


def normalizar_flag(valor, default):
    """Converte valor (bool, str vinda de config/env, ou None) num bool, sem o bug de
    bool("false") == True: string vazia/None usa default; "false"/"0"/"nao"/"não" é False;
    qualquer outro texto não vazio é True."""
    if valor is None or valor == "":
        return default
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str):
        return valor.strip().lower() not in ("false", "0", "nao", "não")
    return bool(valor)


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
