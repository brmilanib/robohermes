# -*- coding: utf-8 -*-
"""
Trava do agrupamento (01/10, Bruno: "esses dados são o coração das nossas análises; precisa ter regras mais firmes").

Nenhuma mudança nas linhas de uma marca (IA, revisão diária, agente) vai para o banco sem antes passar aqui. A mudança é
SIMULADA no último export da marca (a configuração de hoje x a proposta, nos mesmos anúncios) e é recusada se:

1. GTIN PARTIDO: um GTIN que hoje está num produto só passaria a estar em dois ou mais (GTIN é CPF: o mesmo código é o
   mesmo produto). Foi o que aconteceu com o Sabah Al Ward (ICARBONXX num produto, PHTEC em outro).
2. PRODUTO GRANDE PICADO: um dos 15 produtos que mais vendem perde mais de 10% das unidades para outros produtos.
3. EXPLOSÃO DE PRODUTOS: o número de produtos com venda cresce mais de 15% (e mais de 3).
4. LINHA ABSURDA: chave com mais de 5 palavras ou que não aparece em nenhum título.

Quem decide é o Bruno: a IA só PROPÕE; aplicar exige a aprovação dele, e mesmo aprovada a trava roda de novo.
"""
import nubi

MAX_PALAVRAS = 5
TOP_PRODUTOS = 15
PERDA_MAX = 0.10
CRESCE_MAX = 0.15


def _consolidado(df, marca, cfg):
    return nubi.consolidar(df, marca, cfg)


def simular(df, marca, cfg_atual, cfg_novo):
    """df: anúncios do último export da marca (nubi.preparar). -> {"ok", "motivos", "metricas", "exemplos"}."""
    marca = nubi.chave_marca(marca)
    motivos, exemplos = [], []
    for k, _ in (cfg_novo.get(marca) or {}).get("linhas") or []:
        if len(str(k).split()) > MAX_PALAVRAS:
            motivos.append(f"linha com mais de {MAX_PALAVRAS} palavras: \"{str(k)[:60]}\"")
    if df is None or df.empty:
        return {"ok": not motivos, "motivos": motivos or [], "metricas": {}, "exemplos": []}
    a = _consolidado(df, marca, cfg_atual)
    b = _consolidado(df, marca, cfg_novo)
    un = a["un"].astype(float)
    com_venda = lambda x: int(x.loc[un > 0, "produto"].nunique())
    n_a, n_b = com_venda(a), com_venda(b)
    # 1. GTIN partido
    g = a["gtin"].fillna("").astype(str)
    partidos = []
    for gtin, idx in a[g != ""].groupby(g[g != ""]).groups.items():
        if a.loc[idx, "produto"].nunique() == 1 and b.loc[idx, "produto"].nunique() > 1:
            partidos.append((gtin, float(un[idx].sum()), sorted(b.loc[idx, "produto"].unique())[:4]))
    partidos.sort(key=lambda x: -x[1])
    if partidos:
        motivos.append(f"{len(partidos)} GTIN(s) partido(s) em mais de um produto")
        exemplos += [f"GTIN {gt} ({un_:.0f} un.) iria para: {', '.join(ps)}" for gt, un_, ps in partidos[:5]]
    # 2. produto grande picado
    tops = a.assign(_un=un).groupby("produto")["_un"].sum().sort_values(ascending=False).head(TOP_PRODUTOS)
    for prod, total in tops.items():
        if total <= 0:
            continue
        idx = a.index[a["produto"] == prod]
        fica = b.loc[idx].assign(_un=un[idx]).groupby("produto")["_un"].sum().max()
        perda = 1 - float(fica) / float(total)
        if perda > PERDA_MAX:
            destinos = b.loc[idx].assign(_un=un[idx]).groupby("produto")["_un"].sum().sort_values(ascending=False)
            motivos.append(f"\"{prod}\" seria picado: perde {perda * 100:.0f}% das unidades")
            exemplos.append(f"{prod} ({total:.0f} un.) → " + ", ".join(f"{p} ({v:.0f})" for p, v in destinos.head(4).items()))
    # 3. explosão de produtos
    if n_b > n_a * (1 + CRESCE_MAX) and n_b - n_a > 3:
        motivos.append(f"produtos com venda iriam de {n_a} para {n_b} (+{(n_b / max(1, n_a) - 1) * 100:.0f}%)")
    return {"ok": not motivos, "motivos": motivos, "exemplos": exemplos[:12],
            "metricas": {"produtos_antes": n_a, "produtos_depois": n_b, "gtins_partidos": len(partidos), "anuncios": int(len(a))}}


def simular_marca(repo, marca, cfg_atual, cfg_novo):
    """Lê o último export da marca e simula. Sem export: só as regras das chaves."""
    marca = nubi.chave_marca(marca)
    snaps = repo.snapshots(marca)
    df = None if snaps.empty else nubi.preparar(repo.anuncios(int(snaps["id"].max())))
    return simular(df, marca, cfg_atual, cfg_novo)
