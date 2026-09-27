# -*- coding: utf-8 -*-
"""
Rotinas de criativo (card #14): conector Gemini (ia.gemini_gerar_imagem) para gerar imagens de post/Instagram.

Sem acesso de escrita a vend_vendas_dia, vend_grupo_dia e produto_grupos (dados de venda): o repo usado aqui é
envolvido por _RepoSemVendas, que recusa qualquer escrita nessas 3 tabelas, mesmo com a mesma credencial do resto
do servidor (a rejeição é no código, não muda a estrutura do banco nem a role do Supabase).

dry_run=True (padrão): gera a imagem e grava o rascunho em ia_resumos (chave 'criativo|<id>', tabela já existente,
sem campo novo), sem publicar em lugar nenhum — não existe ainda uma rotina de publicação (Instagram etc.).
dry_run=False só marca o rascunho como pronto para publicar; a publicação em si fica para quando essa integração
existir (fora do escopo deste card).

Custo e teto mensal (regra do card #10) são automáticos: ia._post_json já registra a chamada em agentes_uso e
confere o teto do provedor 'gemini' (NUBI_TETO_GEMINI) antes de chamar a API — a aba Custos lista qualquer id de
ia.TETO_PROVEDORES, sem precisar de código novo aqui.
"""
import uuid

import ia
import nubi_web

TABELAS_VENDA = ("vend_vendas_dia", "vend_grupo_dia", "produto_grupos")


class EscritaBloqueada(PermissionError):
    pass


class _RepoSemVendas:
    """Envelope do repo real: recusa qualquer escrita (POST/PATCH/PUT/DELETE) nas 3 tabelas de venda."""

    def __init__(self, repo):
        self._repo = repo

    def __getattr__(self, nome):
        return getattr(self._repo, nome)

    def _req(self, metodo, tabela, params=None, corpo=None, prefer=None):
        if metodo in ("POST", "PATCH", "PUT", "DELETE") and tabela in TABELAS_VENDA:
            raise EscritaBloqueada(f"conector de criativo (card #14) não escreve em {tabela}")
        return self._repo._req(metodo, tabela, params, corpo, prefer)


def gerar(repo, corpo):
    """POST /api/app?r=criativo_gerar {prompt, dry_run}: gera 1 imagem com o Gemini e salva o rascunho em
    ia_resumos. dry_run (padrão True) nunca publica; só marca o rascunho pronto para publicar quando vier False."""
    prompt = str((corpo or {}).get("prompt") or "").strip()
    if not prompt:
        raise nubi_web.ErroNuvem("Informe o prompt do criativo.")
    dry_run = bool((corpo or {}).get("dry_run", True))
    seguro = _RepoSemVendas(repo)
    imagem_b64, texto, modelo = ia.gemini_gerar_imagem(prompt)
    chave = f"criativo|{uuid.uuid4().hex[:16]}"
    seguro._req("POST", "ia_resumos", corpo=[{"chave": chave, "texto": texto[:2000], "ia": "gemini",
                "dados": {"prompt": prompt[:2000], "modelo": modelo, "imagem_b64": imagem_b64,
                          "dry_run": dry_run, "publicado": False}}], prefer="return=minimal")
    return {"ok": True, "chave": chave, "dry_run": dry_run, "modelo": modelo}
