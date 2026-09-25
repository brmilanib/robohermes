# -*- coding: utf-8 -*-
"""
StoreConnector (card #1): contrato base para os conectores de loja (ML, Shopee, Amazon,
TikTok, ...) e a gravação idempotente dos pedidos no Supabase.

Cada conector real (próximos cards) herda de StoreConnector e implementa fetch_orders e
fetch_ads_ranking; a gravação sempre passa por persistir_pedidos, que faz upsert pela
chave única (source, id_externo) — pedido processado 2x fica só 1 registro. A idempotência
de fetch_ads_ranking não está no escopo deste card.
"""

from datetime import datetime, timezone


class ErroConector(Exception):
    pass


class StoreConnector:
    """Interface que todo conector de loja implementa. source identifica a loja (ex.: "mercado_livre")."""

    source = None

    def fetch_orders(self, **kwargs):
        raise NotImplementedError

    def fetch_ads_ranking(self, **kwargs):
        raise NotImplementedError


def persistir_pedidos(repo, source, pedidos):
    """Grava pedidos de uma loja em store_orders, idempotente por (source, id_externo).

    pedidos: lista de dicts com id_externo (obrigatório), status (opcional) e dados (dict opcional).
    Pedido sem id_externo não é gravado e vira aviso. Retorna (quantos gravados, lista de avisos).
    """
    source = (source or "").strip()
    if not source:
        raise ErroConector("source obrigatório para gravar pedidos.")
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
