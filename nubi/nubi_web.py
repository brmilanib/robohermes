# -*- coding: utf-8 -*-
"""
nubi na nuvem: o mesmo motor do nubi.py, com os dados no Supabase e as telas no
navegador. Este módulo tem três partes:

1. RepoSupabase — guarda e lê os dados pela API REST do Supabase, com o login de
   quem está usando a página (as regras de acesso ficam no próprio banco).
2. relatorio() — calcula as tabelas da marca (as mesmas do Excel) em JSON.
3. atender() — as rotas da API chamadas pela página (api/app.py).
"""

import json
import math
import os
import re
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone

import pandas as pd

import nubi
import ranking
import vendedores

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ivsmadbyzbmugwfadwtg.supabase.co")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "sb_publishable_hlLuzIP8GMxjwTfY-otJQQ_LbMPm7Yt")
LOTE = 500           # linhas por requisição ao gravar
PAGINA = 1000        # linhas por página ao ler (limite do Supabase)


class ErroNuvem(Exception):
    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.status = status


# ---------------------------------------------------------------------------
# 1. Dados no Supabase
# ---------------------------------------------------------------------------

def _limpo(v):
    """Converte tipos do pandas/numpy em JSON puro (NaN vira null)."""
    if v is None:
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


class RepoSupabase:
    """Mesmos métodos do nubi.RepoLocal, gravando no Supabase."""

    def __init__(self, token):
        if not token:
            raise ErroNuvem("Faça login para continuar.", 401)
        self.token = token

    # -- HTTP -----------------------------------------------------------
    def _req(self, metodo, caminho, params=None, corpo=None, prefer=None):
        url = f"{SUPABASE_URL}/rest/v1/{caminho}"
        if params:
            url += "?" + urllib.parse.urlencode(params, safe=",.()*:")
        cab = {"apikey": SUPABASE_ANON_KEY, "Authorization": f"Bearer {self.token}",
               "Content-Type": "application/json", "Accept": "application/json"}
        if prefer:
            cab["Prefer"] = prefer
        dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8") if corpo is not None else None
        req = urllib.request.Request(url, data=dados, headers=cab, method=metodo)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                txt = r.read().decode("utf-8")
                return json.loads(txt) if txt else None
        except urllib.error.HTTPError as e:
            txt = e.read().decode("utf-8", "replace")
            if e.code == 401 or (e.code == 403 and "JWT" in txt):
                raise ErroNuvem("Sessão expirada. Entre de novo.", 401)
            if e.code == 403:
                raise ErroNuvem("Sem permissão para esta operação.", 403)
            raise ErroNuvem(f"Erro no banco ({e.code}): {txt[:300]}", 500)
        except urllib.error.URLError as e:
            raise ErroNuvem(f"Sem conexão com o banco ({e.reason}).", 502)

    def _todos(self, caminho, params, metodo="GET", corpo=None):
        """Lê todas as páginas de uma consulta (o Supabase devolve no máximo 1000 por vez)."""
        saida, offset = [], 0
        while True:
            p = dict(params, limit=PAGINA, offset=offset)
            parte = self._req(metodo, caminho, p, corpo) or []
            saida.extend(parte)
            if len(parte) < PAGINA:
                return saida
            offset += PAGINA

    @staticmethod
    def _eq(v):
        return f"eq.{v}"

    # -- mesma interface do RepoLocal -------------------------------------
    def fechar(self):
        pass

    def marcas(self):
        linhas = self._todos("snapshots", {"select": "marca", "order": "marca"})
        return sorted({r["marca"] for r in linhas})

    def snapshot_por_hash(self, hash_):
        r = self._req("GET", "snapshots", {"select": "importado_em,marca,inicio,fim",
                                           "hash": self._eq(hash_)})
        return r[0] if r else None

    def snapshots(self, marca=None):
        params = {"select": "*", "order": "marca,fim,inicio,id"}
        if marca:
            params["marca"] = self._eq(marca)
        df = pd.DataFrame(self._todos("snapshots", params))
        if df.empty:
            return pd.DataFrame(columns=["id", "marca", "inicio", "fim", "dias", "arquivo", "hash",
                                         "importado_em"])
        return df

    def gravar_snapshot(self, marca, inicio, fim, dias, arquivo, hash_, df):
        # Mesmo marca+período vindo num arquivo diferente: substitui o antigo
        # (os anúncios vão junto, pelo "on delete cascade").
        apagados = self._req("DELETE", "snapshots",
                             {"marca": self._eq(marca), "inicio": self._eq(inicio), "fim": self._eq(fim)},
                             prefer="return=representation") or []
        novo = self._req("POST", "snapshots", corpo=[{
            "marca": marca, "inicio": inicio, "fim": fim, "dias": int(dias), "arquivo": arquivo,
            "hash": hash_}], prefer="return=representation")
        sid = novo[0]["id"]
        registros = [{k: _limpo(v) for k, v in r.items()}
                     for r in df[nubi.CAMPOS_ANUNCIO].to_dict("records")]
        for r in registros:
            r["snapshot_id"] = sid
        try:
            for i in range(0, len(registros), LOTE):
                self._req("POST", "anuncios", corpo=registros[i:i + LOTE], prefer="return=minimal")
        except ErroNuvem:
            self._req("DELETE", "snapshots", {"id": self._eq(sid)})   # não deixa período pela metade
            raise
        return len(apagados) > 0

    def anuncios(self, sid):
        linhas = self._todos("anuncios", {"select": "*", "snapshot_id": self._eq(int(sid)), "order": "id"})
        df = pd.DataFrame(linhas)
        if df.empty:
            return pd.DataFrame(columns=["rid", "snapshot_id"] + nubi.CAMPOS_ANUNCIO)
        return df.rename(columns={"id": "rid"})

    def atualizar_consolidacao(self, df):
        regs = [{"id": int(r["rid"]), **{c: _limpo(r[c]) for c in nubi.CAMPOS_CONSOLIDACAO}}
                for r in df.to_dict("records")]
        for i in range(0, len(regs), 1000):
            self._req("POST", "rpc/atualizar_consolidacao", corpo={"dados": regs[i:i + 1000]})

    def un_por_produto(self, sids):
        linhas = self._todos("rpc/un_por_produto", {"order": "snapshot_id,produto"}, metodo="POST",
                             corpo={"ids": [int(x) for x in sids]})
        df = pd.DataFrame(linhas)
        return df if not df.empty else pd.DataFrame(columns=["snapshot_id", "produto", "un"])

    def carregar_config(self):
        return {nubi.chave_marca(r["marca"]): {"linhas": r["linhas"] or []}
                for r in self._todos("marcas_config", {"select": "marca,linhas"})}

    def salvar_config(self, cfg, marca=None, apagar=None):
        marcas = [marca] if marca else list(cfg)
        corpo = [{"marca": m, "linhas": cfg[m].get("linhas", []),
                  "atualizado_em": datetime.now().isoformat()} for m in marcas]
        self._req("POST", "marcas_config", corpo=corpo,
                  prefer="resolution=merge-duplicates,return=minimal")
        if apagar:
            self._req("DELETE", "marcas_config", {"marca": self._eq(apagar)})

    def renomear_marca(self, antiga, nova):
        self._req("PATCH", "snapshots", {"marca": self._eq(antiga)}, corpo={"marca": nova},
                  prefer="return=minimal")

    def carregar_gtins(self):
        return {r["gtin"]: {"nome": r["nome"] or "", "marca": r["marca"] or "", "fonte": r["fonte"] or "",
                            "consultado_em": r["consultado_em"] or ""}
                for r in self._todos("gtin_info", {"select": "*", "order": "gtin"})}

    def salvar_gtins(self, info, alterados=None):
        gtins = alterados if alterados is not None else list(info)
        if not gtins:
            return
        corpo = [{"gtin": g, "nome": info[g].get("nome", ""), "marca": info[g].get("marca", ""),
                  "fonte": info[g].get("fonte", ""),
                  "consultado_em": info[g].get("consultado_em") or datetime.now().isoformat()}
                 for g in gtins]
        self._req("POST", "gtin_info", corpo=corpo, prefer="resolution=merge-duplicates,return=minimal")

    def apagar_snapshot(self, sid):
        self._req("DELETE", "snapshots", {"id": self._eq(int(sid))})

    def painel(self):
        return self._req("POST", "rpc/painel", corpo={}) or []


# ---------------------------------------------------------------------------
# 2. Relatório da marca em JSON (as mesmas tabelas do Excel, já calculadas)
# ---------------------------------------------------------------------------

def faixa(p):
    return ("-" if p <= 0 else "até R$ 99" if p < 100 else "R$ 100–199" if p < 200
            else "R$ 200–299" if p < 300 else "R$ 300–499" if p < 500 else "R$ 500+")


def _div(a, b):
    return float(a) / float(b) if b else 0.0


def _registros(linhas):
    return [{k: _limpo(v) for k, v in r.items()} for r in linhas]


def _periodo(s):
    return None if s is None else {"id": int(s["id"]), "inicio": str(s["inicio"]), "fim": str(s["fim"]),
                                   "dias": int(s["dias"]), "arquivo": s.get("arquivo") or ""}


def relatorio(repo, marca):
    snaps = repo.snapshots(marca)
    if snaps.empty:
        raise ErroNuvem(f"Nenhum período importado para {marca}.", 404)
    atual = snaps.iloc[-1]
    anterior = snaps.iloc[-2] if len(snaps) >= 2 else None
    df = nubi.ler_snapshot(repo, atual["id"], marca)
    dias = int(atual["dias"])
    df.attrs["dias"] = dias
    df_ant = nubi.ler_snapshot(repo, anterior["id"], marca) if anterior is not None else None
    attrs = nubi.atributos_produto(df)
    vend = nubi.codigos_vendedor(df)
    df["cod"] = df["vendedor_id"].map(vend["cod"])
    un_total = int(df["un"].sum())
    fat_total = float(df["fat"].sum())

    # Produtos
    g = df.groupby("produto")
    anun = g.size()
    cat_n = g["catalogo"].sum()
    full_n = g["full"].sum()
    produtos, acum = [], 0
    for prod, a in attrs.iterrows():
        un = int(a["un"])
        pct = _div(un, un_total)
        antes = acum
        acum += pct
        pm = _div(a["fat"], un)
        produtos.append({
            "produto": prod, "categoria_l1": a["cat_l1"], "categoria": a["cat"], "marca": a["marca"],
            "linha": a["linha"], "tipo": a["tipo"], "volume": a["volume"], "gtins": int(a["gtins"]),
            "anuncios": int(anun[prod]), "vendedores": int(a["vendedores"]), "un": un,
            "fat": float(a["fat"]), "preco_medio": pm, "faixa": faixa(pm), "giro": un / dias,
            "proj30": un / dias * 30, "pct_volume": pct, "pct_acum": acum,
            "abc": "A" if antes < 0.8 else "B" if antes < 0.95 else "C",
            "un_por_anuncio": _div(un, anun[prod]), "pct_catalogo": _div(cat_n[prod], anun[prod]),
            "pct_full": _div(full_n[prod], anun[prod]), "confianca": a["confianca"]})

    # Oportunidades
    oport = []
    for x in nubi.calcular_oportunidades(df, attrs, df_ant,
                                         float(anterior["dias"]) if anterior is not None else None):
        a = x["a"]
        oport.append({
            "produto": x["prod"], "categoria": a["cat"], "marca": a["marca"], "volume": a["volume"],
            "giro": x["giro"], "giro_ant": x["giro_ant"], "var": x["var"], "vendedores": x["vend"],
            "giro_por_vendedor": _div(x["giro"], x["vend"]), "anuncios": x["anuncios"],
            "lider": float(x["lider"]), "pct_full": float(x["full"]), "pct_catalogo": float(x["catalogo"]),
            "mediana": x["mediana"], "faixa": faixa(x["mediana"]), "amplitude": x["amp"],
            "nota": round(x["nota"]), "sinais": x["sinais"]})

    # Vendedores
    vendedores, acum = [], 0
    for vid, v in vend.iterrows():
        sub = df[df["vendedor_id"] == vid]
        share = _div(v["un"], un_total)
        acum += share
        n = len(sub)
        vendedores.append({
            "codigo": v["cod"], "vendedor": v["nome"], "un": int(v["un"]), "fat": float(v["fat"]),
            "share": share, "share_acum": acum, "anuncios": n, "referencias": int(sub["produto"].nunique()),
            "preco_medio": _div(v["fat"], v["un"]), "un_por_anuncio": _div(v["un"], n),
            "pct_catalogo": _div(sub["catalogo"].sum(), n), "pct_full": _div(sub["full"].sum(), n),
            "loja_oficial": int(sub["loja_oficial"].sum()), "internacional": int(sub["internacional"].sum())})

    # Preços
    precos = []
    v = df[(df["un"] > 0) & (df["preco"] > 0)]
    for prod, gp in v.groupby("produto"):
        if len(gp) < 2:
            continue
        q = gp["preco"].quantile([0, .25, .5, .75, 1]).tolist()
        un = int(gp["un"].sum())
        a = attrs.loc[prod]
        precos.append({
            "produto": prod, "vendedores": int(gp["vendedor_id"].nunique()), "un": un,
            "minimo": q[0], "q1": q[1], "mediana": q[2], "q3": q[3], "maximo": q[4],
            "amplitude": _div(q[4], q[0]), "ponderado": _div((gp["preco"] * gp["un"]).sum(), un),
            "abaixo_80": int(gp.loc[gp["preco"] < 0.8 * q[2], "un"].sum()),
            "categoria": a["cat"], "marca": a["marca"], "faixa": faixa(q[2])})
    precos.sort(key=lambda x: -x["un"])

    # GTINs
    gtins = []
    info = nubi.INFO_GTIN
    for gtin, gg in df[df["gtin"] != ""].groupby("gtin"):
        un = int(gg["un"].sum())
        prod = gg["produto"].value_counts().index[0]
        gtins.append({
            "gtin": gtin, "produto": prod, "anuncios": len(gg), "vendedores": int(gg["vendedor_id"].nunique()),
            "un": un, "fat": float(gg["fat"].sum()), "preco_medio": _div(gg["fat"].sum(), un),
            "pct_volume": _div(un, un_total), "categoria": attrs["cat"].get(prod, ""),
            "confianca": gg["confianca"].value_counts().index[0],
            "especificacao": (info.get(gtin) or {}).get("nome", ""), "link": nubi.link_pesquisa(gtin)})
    gtins.sort(key=lambda x: -x["un"])
    un_sem_gtin = int(df.loc[df["gtin"] == "", "un"].sum())

    # Dúvidas
    duvidas = []
    duv = df[(df["gtin"] != "") & df["confianca"].str.startswith("Dúvida")]
    for gtin, gd in duv.groupby("gtin"):
        gd = gd.sort_values("un", ascending=False)
        i = info.get(gtin)
        status = ("não pesquisado" if not i else f"{i.get('fonte', '')}: {i['nome']}" if i.get("nome")
                  else "não encontrado nas bases")
        duvidas.append({
            "gtin": gtin, "produto": gd["produto"].value_counts().index[0], "motivo": gd["confianca"].iloc[0],
            "anuncios": len(gd), "un": int(gd["un"].sum()),
            "titulos_diferentes": int(gd["titulo"].map(nubi.normalizar).nunique()),
            "titulos": " | ".join(list(dict.fromkeys(gd["titulo"]))[:3]), "pesquisa": status,
            "nome_pesquisado": (i or {}).get("nome", ""), "marca_pesquisada": (i or {}).get("marca", ""),
            "link": nubi.link_pesquisa(gtin)})
    duvidas.sort(key=lambda x: -x["un"])

    # Evolução
    evolucao = []
    if df_ant is not None:
        agg = lambda d: d.groupby("produto").agg(un=("un", "sum"), fat=("fat", "sum"),
                                                 vend=("vendedor_id", "nunique"))
        j = agg(df_ant).join(agg(df), how="outer", lsuffix="_a", rsuffix="_b").fillna(0)
        da, db = float(anterior["dias"]), float(dias)
        for prod, x in j.iterrows():
            ga, gb = x["un_a"] / da, x["un_b"] / db
            var = (gb / ga - 1) if ga else 0
            pa, pb = _div(x["fat_a"], x["un_a"]), _div(x["fat_b"], x["un_b"])
            mov = ("sem venda" if not ga and not gb else "novo no período" if not ga else "sumiu" if not gb
                   else "acelerando" if var > 0.2 else "perdendo giro" if var < -0.2 else "estável")
            evolucao.append({
                "produto": prod, "giro_ant": ga, "giro": gb, "var": var if ga else None,
                "preco_ant": pa, "preco": pb, "var_preco": (pb / pa - 1) if pa and pb else None,
                "vend_ant": int(x["vend_a"]), "vend": int(x["vend_b"]), "movimento": mov,
                "categoria": (attrs.at[prod, "cat"] if prod in attrs.index else
                              df_ant.loc[df_ant["produto"] == prod, "cat"].iloc[0])})
        evolucao.sort(key=lambda x: (-x["giro"], -x["giro_ant"]))

    # Histórico (até os 30 últimos períodos)
    historico = {"periodos": [], "linhas": []}
    if len(snaps) >= 2:
        ult = snaps.tail(30)
        un = repo.un_por_produto(list(ult["id"]))
        tab = {}
        for k, (_, s) in enumerate(ult.iterrows()):
            historico["periodos"].append(_periodo(s))
            for _, r in un[un["snapshot_id"] == s["id"]].iterrows():
                tab.setdefault(r["produto"], [0.0] * len(ult))[k] = float(r["un"]) / float(s["dias"])
        for prod, serie in tab.items():
            ant = serie[:-1]
            media = sum(ant) / len(ant) if ant else 0
            historico["linhas"].append({
                "produto": prod, "categoria": attrs["cat"].get(prod, "-"), "serie": serie,
                "media_ant": media, "ultimo_vs_media": (serie[-1] / media - 1) if media else None,
                "com_venda": sum(1 for v in serie if v > 0)})
        historico["linhas"].sort(key=lambda x: -x["serie"][-1])

    # Anúncios: produto consolidado + a linha original do arquivo, com as colunas do export.
    colunas = list(nubi.COLUNAS_NUBIMETRICS)
    for r in df["bruto"]:
        if isinstance(r, dict):
            colunas += [c for c in r if c not in colunas]
    anuncios = []
    for r in df.sort_values("un", ascending=False).to_dict("records"):
        bruto = r.get("bruto") if isinstance(r.get("bruto"), dict) else {}
        anuncios.append({"produto": r["produto"], "confianca": r["confianca"], "codigo": r["cod"],
                         **{f"c{i}": bruto.get(c, "") for i, c in enumerate(colunas)}})

    # Vendedores de cada produto (janela que abre ao clicar no produto)
    vend_prod = {}
    g = df.assign(fat_preco=df["preco"] * df["un"]).groupby(["produto", "vendedor_id"])
    for (prod, vid), x in g:
        un, fat, n = int(x["un"].sum()), float(x["fat"].sum()), len(x)
        vend_prod.setdefault(prod, []).append({
            "codigo": vend.at[vid, "cod"], "vendedor": vend.at[vid, "nome"], "anuncios": n, "un": un, "fat": fat,
            "preco_medio": _div(fat, un), "ultimo_preco": float(x["preco"].median()),
            "full": int(x["full"].sum()), "catalogo": int(x["catalogo"].sum()),
            "loja_oficial": int(x["loja_oficial"].max())})
    for lista in vend_prod.values():
        tot = sum(v["un"] for v in lista)
        for v in lista:
            v["share"] = _div(v["un"], tot)
        lista.sort(key=lambda v: (-v["un"], -v["fat"], v["codigo"]))

    # Produtos de cada vendedor (janela que abre ao clicar no vendedor), pelo código V01…
    prod_vend = {}
    for prod, lista in vend_prod.items():
        for v in lista:
            prod_vend.setdefault(v["codigo"], []).append({
                "produto": prod, "un": v["un"], "fat": v["fat"], "anuncios": v["anuncios"],
                "preco_medio": v["preco_medio"], "ultimo_preco": v["ultimo_preco"], "full": v["full"],
                "catalogo": v["catalogo"], "share_no_produto": v["share"],
                "categoria": attrs["cat"].get(prod, ""), "marca": attrs["marca"].get(prod, "")})
    for lista in prod_vend.values():
        tot = sum(p["un"] for p in lista)
        for p in lista:
            p["share_do_vendedor"] = _div(p["un"], tot)
        lista.sort(key=lambda p: (-p["un"], -p["fat"], p["produto"]))
    # Líder de cada oportunidade (nome na lista das melhores oportunidades)
    for o in oport:
        lista = vend_prod.get(o["produto"]) or []
        if lista and lista[0]["un"] > 0:
            o["lider_codigo"], o["lider_nome"] = lista[0]["codigo"], lista[0]["vendedor"]

    # Resumo
    n = len(df)
    conc = []
    for rot, k in (("Top 1", 1), ("Top 3", 3), ("Top 5", 5), ("Top 10", 10), ("Top 20", 20), ("Todos", None)):
        sub = vendedores if k is None else vendedores[:k]
        u = sum(x["un"] for x in sub)
        conc.append({"faixa": rot, "vendedores": len(sub), "un": u, "share": _div(u, un_total)})
    resumo = {
        "dias": dias, "anuncios": n, "un": un_total, "fat": fat_total, "preco_medio": _div(fat_total, un_total),
        "giro": un_total / dias, "proj30": un_total / dias * 30, "proj_ano_un": un_total / dias * 365,
        "proj_ano_fat": fat_total / dias * 365, "vendedores": len(vend), "referencias": len(attrs),
        "gtins": int(df.loc[df["gtin"] != "", "gtin"].nunique()),
        "vend_loja_oficial": int(df.groupby("vendedor_id")["loja_oficial"].max().sum()),
        "pct_catalogo": _div(df["catalogo"].sum(), n), "pct_full": _div(df["full"].sum(), n),
        "un_outras_marcas": int(df.loc[df["tipo"] == nubi.TIPO_OUTRA, "un"].sum()),
        "un_nao_perfume": int(df.loc[df["tipo"] == nubi.TIPO_FORA, "un"].sum()),
        "gtins_duvida": len(duvidas), "un_sem_gtin": un_sem_gtin}

    return {
        "marca": marca, "nome": nubi.nome_bonito(marca), "atual": _periodo(atual),
        "anterior": _periodo(anterior), "periodos": [_periodo(s) for _, s in snaps.iloc[::-1].iterrows()],
        "resumo": resumo, "concentracao": conc,
        "tabelas": {"oportunidades": _registros(oport), "produtos": _registros(produtos),
                    "evolucao": _registros(evolucao), "precos": _registros(precos),
                    "vendedores": _registros(vendedores), "gtins": _registros(gtins),
                    "duvidas": _registros(duvidas), "anuncios": _registros(anuncios)},
        "historico": historico,
        "vendedores_produto": {k: _registros(v) for k, v in vend_prod.items()},
        "produtos_vendedor": {k: _registros(v) for k, v in prod_vend.items()},
        "colunas_arquivo": colunas,
    }


# ---------------------------------------------------------------------------
# 3. Rotas da API
# ---------------------------------------------------------------------------

def _data(txt, nome):
    d = nubi.data_valida(txt or "")
    if not d:
        raise ErroNuvem(f"{nome}: use o formato AAAA-MM-DD.")
    return d


def _preparar(repo):
    """Estado por requisição: GTINs pesquisados e mensagens para a resposta."""
    nubi.INFO_GTIN.clear()
    nubi.INFO_GTIN.update(repo.carregar_gtins())
    log = []
    nubi._SAIDA[0] = log.append
    return log


# ---------------------------------------------------------------------------
# Agente de GTIN: pesquisa sozinho os GTINs em dúvida e reagrupa os produtos.
# Roda depois de cada importação, na agenda da Vercel (Cron) e enquanto a página está aberta.
# ---------------------------------------------------------------------------

AGENTE_EMAIL = os.environ.get("NUBI_AGENTE_EMAIL", "")
AGENTE_SENHA = os.environ.get("NUBI_AGENTE_SENHA", "")
CRON_SECRET = os.environ.get("CRON_SECRET", "")
TEMPO_MAX = 240          # segundos por rodada (a função da Vercel tem 300)


def login_agente():
    """A agenda da Vercel não tem usuário logado: o agente entra com o login dele (acesso igual ao seu)."""
    if not (AGENTE_EMAIL and AGENTE_SENHA):
        raise ErroNuvem("Agente sem login configurado (NUBI_AGENTE_EMAIL / NUBI_AGENTE_SENHA).", 500)
    req = urllib.request.Request(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        data=json.dumps({"email": AGENTE_EMAIL, "password": AGENTE_SENHA}).encode(),
        headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())["access_token"]
    except urllib.error.HTTPError as e:
        raise ErroNuvem(f"Login do agente recusado ({e.code}).", 500)


# Quando a regra de agrupamento muda, o agente reprocessa uma vez tudo o que já foi importado.
REGRA_ATUAL = "regra 2: mesmo GTIN = mesmo produto; linha lida do título"


def aplicar_regra_nova(repo):
    if repo._req("GET", "agente_execucoes", {"select": "id", "origem": repo._eq(REGRA_ATUAL), "limit": 1}):
        return False
    nubi.avisar("    Aplicando a regra nova de agrupamento em todos os períodos já importados…")
    nubi.reconsolidar(repo, repo.carregar_config())
    agora = datetime.now(timezone.utc).isoformat()
    repo._req("POST", "agente_execucoes", corpo=[{"origem": REGRA_ATUAL, "iniciado_em": agora, "terminado_em": agora,
                                                   "log": "Reprocessamento de todas as marcas."}],
              prefer="return=minimal")
    return True


def rodar_agente(repo, origem, marca=None, segundos=TEMPO_MAX):
    """Uma rodada: pesquisa os GTINs em dúvida (os que mais vendem primeiro) até acabar o tempo,
    reagrupa as marcas que mudaram e registra a rodada em agente_execucoes."""
    inicio = datetime.now(timezone.utc)
    prazo = time.monotonic() + max(5, segundos)
    log = _preparar(repo)
    regra = aplicar_regra_nova(repo)
    res = nubi.pesquisar_gtins(repo, 10_000, None, marca, prazo=prazo)
    mudaram = sorted(res["marcas"])
    if mudaram and time.monotonic() < prazo + 40:
        nubi.reconsolidar(repo, repo.carregar_config(), mudaram)
        nubi.avisar(f"    Produtos reagrupados: {', '.join(nubi.nome_bonito(m) for m in mudaram)}.")
    reg = {"origem": origem, "marca": marca, "iniciado_em": inicio.isoformat(),
           "terminado_em": datetime.now(timezone.utc).isoformat(),
           "pendentes": res["pendentes"], "pesquisados": res["pesquisados"], "encontrados": res["encontrados"],
           "nao_encontrados": res["nao_encontrados"], "sem_resposta": res["sem_resposta"],
           "restantes": max(0, res["pendentes"] - res["pesquisados"]) + res["sem_resposta"],
           "log": "\n".join(log)[-20000:]}
    try:
        repo._req("POST", "agente_execucoes", corpo=[reg], prefer="return=minimal")
    except ErroNuvem:
        pass   # registrar a rodada não pode derrubar a pesquisa
    return dict(reg, marcas=mudaram, log=log, regra_aplicada=regra)


def atender(metodo, rota, q, corpo, token):
    """Devolve (status, tipo de conteúdo, bytes, cabeçalhos extras)."""
    t0 = time.monotonic()
    try:
        if rota == "agente" and CRON_SECRET and token == CRON_SECRET:
            # Chamada da agenda (Vercel Cron manda "Authorization: Bearer CRON_SECRET").
            return _json(rodar_agente(RepoSupabase(login_agente()), "agendado"))
        repo = RepoSupabase(token)
        if rota == "agente" and metodo == "POST":
            seg = min(TEMPO_MAX, int(q.get("segundos") or 60))
            return _json(rodar_agente(repo, q.get("origem") or "manual", q.get("marca") or None, seg))
        if rota == "agente_status":
            ult = repo._req("GET", "agente_execucoes", {"select": "*", "order": "id.desc", "limit": 15,
                                                        "origem": "neq." + REGRA_ATUAL}) or []
            for u in ult:
                u["log"] = (u.get("log") or "")[-4000:]
            return _json({"execucoes": ult, "agendado": bool(CRON_SECRET and AGENTE_EMAIL)})
        if rota == "painel":
            # A tabela acesso só devolve a linha de quem está liberado (RLS).
            if not repo._req("GET", "acesso", {"select": "email", "limit": 1}):
                raise ErroNuvem("Este e-mail ainda não tem acesso ao nubi. Peça para liberar.", 403)
            return _json(repo.painel())

        if rota.startswith("vend_"):
            return _json(rota_vendedores(repo, metodo, rota, q, corpo))

        if rota.startswith("ranking"):
            return _json(rota_ranking(repo, metodo, rota, q, corpo))

        if rota == "marcas":
            # Marcas já cadastradas (com dados ou só com linhas configuradas), para o upload.
            return _json(sorted(set(repo.carregar_config()) | set(repo.marcas())))

        if rota == "analisar" and metodo == "POST":
            # Antes de importar: de qual marca é o arquivo (conteúdo + GTIN) e quais outras há nele.
            _preparar(repo)
            try:
                df, _ = nubi.ler_csv(corpo)
            except nubi.ErroArquivo as e:
                raise ErroNuvem(f"Não parece um export do Nubimetrics: {e}.")
            existentes = sorted(set(repo.carregar_config()) | set(repo.marcas()))
            ident = nubi.identificar_marca(df, existentes)
            if ident and ident["pesquisados"]:
                repo.salvar_gtins(nubi.INFO_GTIN, ident["pesquisados"])
            m = nubi.PADRAO_NOME.match(re.sub(r"\.csv$", "", q.get("arquivo", ""), flags=re.I))
            return _json({"marca": ident and ident["marca"], "nome": ident and nubi.nome_bonito(ident["marca"]),
                          "oficial": ident and ident["oficial"], "fonte": ident and ident["fonte"],
                          "gtin": ident and ident["gtin"], "grafia_arquivo": ident and ident["grafia_arquivo"],
                          "existente": ident and ident["existente"], "outras": (ident or {}).get("outras", []),
                          "anuncios": len(df), "un": int(df["un"].sum()),
                          "inicio": m.group(2) if m else None, "fim": m.group(3) if m else None})

        if rota == "redetectar" and metodo == "POST":
            # Refaz a detecção automática das linhas pelo período mais recente e reprocessa.
            marca = nubi.chave_marca(q["marca"])
            snaps = repo.snapshots(marca)
            if snaps.empty:
                raise ErroNuvem("Nenhum período importado para esta marca.", 404)
            log = _preparar(repo)
            cfg = repo.carregar_config()
            df = nubi.preparar(repo.anuncios(snaps.iloc[-1]["id"]))
            cfg[marca] = {"linhas": nubi.detectar_linhas(df, marca)}
            repo.salvar_config(cfg, marca)
            nubi.reconsolidar(repo, cfg, [marca])
            return _json({"ok": True, "linhas": cfg[marca]["linhas"], "log": log})

        if rota == "relatorio":
            _preparar(repo)
            return _json(relatorio(repo, q["marca"]))

        if rota == "importar" and metodo == "POST":
            log = _preparar(repo)
            cfg = repo.carregar_config()
            nome = q.get("arquivo") or "upload.csv"
            m = nubi.PADRAO_NOME.match(re.sub(r"\.csv$", "", nome, flags=re.I))

            def marca_periodo(sugestao):
                # Escolha manual na página > marca do conteúdo do arquivo > nome do arquivo.
                marca = nubi.chave_marca(q.get("marca") or sugestao or (m.group(1).replace("_", " ") if m else ""))
                if not marca:
                    raise ErroNuvem("Não achei a marca na coluna Marca do arquivo. Escolha a marca na lista.")
                ini = _data(q.get("inicio") or (m.group(2) if m else ""), "Data inicial")
                fim = _data(q.get("fim") or (m.group(3) if m else ""), "Data final")
                if fim < ini:
                    raise ErroNuvem("A data final é anterior à inicial.")
                return marca, ini, fim

            avisar = nubi.avisar
            avisar(nome)
            marca = nubi.importar_dados(repo, cfg, nome, corpo, marca_periodo)
            restantes = 0
            if marca:
                sobra = min(120, 250 - (time.monotonic() - t0))
                if sobra > 15:
                    avisar("    Agente de GTIN: pesquisando os GTINs em dúvida desta marca…")
                    r = rodar_agente(repo, "importação", marca, int(sobra))
                    log.extend(r["log"])
                    nubi._SAIDA[0] = log.append
                    restantes = r["restantes"]
                else:
                    restantes = len([g for g in nubi.gtins_em_duvida(repo, marca) if nubi.precisa_pesquisar(g[0])])
                if restantes:
                    avisar(f"    Ainda em dúvida: {restantes} GTIN(s). O agente continua sozinho "
                           f"(enquanto a página estiver aberta e na rodada diária).")
            return _json({"marca": marca, "log": log, "duvidas": restantes})

        if rota == "pesquisar" and metodo == "POST":
            log = _preparar(repo)
            marca = q.get("marca")
            lista = [g for g in (q.get("gtin") or "").split(",") if g.strip()] or None
            if not lista:
                return _json(rodar_agente(repo, "manual", marca, TEMPO_MAX))
            nubi.pesquisar_gtins(repo, int(q.get("limite") or 15), lista, marca)
            nubi.reconsolidar(repo, repo.carregar_config(), [marca] if marca else None)
            return _json({"log": log})

        if rota == "reprocessar" and metodo == "POST":
            log = _preparar(repo)
            marca = q.get("marca")
            nubi.reconsolidar(repo, repo.carregar_config(), [marca] if marca else None)
            log.append("Reprocessado com a configuração atual.")
            return _json({"log": log})

        if rota == "config":
            marca = nubi.chave_marca(q["marca"])
            cfg = repo.carregar_config()
            if metodo == "POST":
                linhas = json.loads(corpo or b"{}").get("linhas")
                if not isinstance(linhas, list) or not all(
                        isinstance(p, list) and len(p) == 2 and all(isinstance(x, str) for x in p) for p in linhas):
                    raise ErroNuvem('Formato das linhas: [["texto no título", "Nome no relatório"], ...]')
                cfg[marca] = {"linhas": [[nubi.normalizar(a), b.strip()] for a, b in linhas if a.strip()]}
                repo.salvar_config(cfg, marca)
                log = _preparar(repo)
                nubi.reconsolidar(repo, cfg, [marca])
                return _json({"ok": True, "log": log})
            return _json({"marca": marca, "linhas": cfg.get(marca, {}).get("linhas", [])})

        if rota == "gtin" and metodo == "POST":
            d = json.loads(corpo or b"{}")
            gtin = nubi.normalizar_gtin(d.get("gtin", "")) or re.sub(r"\D", "", d.get("gtin", ""))
            if not gtin:
                raise ErroNuvem("GTIN inválido.")
            log = _preparar(repo)
            nubi.INFO_GTIN[gtin] = {"nome": (d.get("nome") or "").strip(), "marca": (d.get("marca") or "").strip(),
                                    "fonte": "manual", "consultado_em": datetime.now().isoformat()}
            repo.salvar_gtins(nubi.INFO_GTIN, [gtin])
            nubi.reconsolidar(repo, repo.carregar_config(), [q["marca"]] if q.get("marca") else None)
            return _json({"ok": True, "log": log})

        if rota == "apagar" and metodo == "POST":
            repo.apagar_snapshot(q["id"])
            return _json({"ok": True})

        if rota == "excel":
            _preparar(repo)
            marca = q.get("marca")
            if marca:
                wb, nome = nubi.montar_planilha_marca(repo, marca)
            else:
                wb, nome = nubi.montar_painel(repo), "painel-geral.xlsx"
            if wb is None:
                raise ErroNuvem("Nada para exportar.", 404)
            import io
            buf = io.BytesIO()
            wb.save(buf)
            return (200, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buf.getvalue(),
                    {"Content-Disposition": f'attachment; filename="{nome}"'})

        raise ErroNuvem("Rota desconhecida.", 404)
    except ErroNuvem as e:
        return _json({"erro": str(e)}, e.status)
    except KeyError as e:
        return _json({"erro": f"Faltou o parâmetro {e}."}, 400)
    except Exception:  # noqa: BLE001 — a página mostra uma frase; o detalhe vai para o log da Vercel
        traceback.print_exc()
        return _json({"erro": "Algo deu errado no servidor. Tente de novo; se persistir, veja os logs."}, 500)


# ---------------------------------------------------------------------------
# 4. Ranking mensal de marcas
# ---------------------------------------------------------------------------

def _relatorios(repo, categoria=None):
    p = {"select": "id,categoria,mes,arquivo,importado_em", "order": "categoria,mes"}
    if categoria:
        p["categoria"] = repo._eq(categoria)
    return repo._todos("ranking_relatorios", p)


def _linhas(repo, rid):
    return repo._todos("ranking_linhas", {"select": "*", "relatorio_id": repo._eq(int(rid)), "order": "posicao"})


def rota_ranking(repo, metodo, rota, q, corpo):
    if rota == "ranking_lista":
        rels = _relatorios(repo)
        cats = {}
        for r in rels:
            cats.setdefault(r["categoria"], []).append(r)
        return [{"categoria": c, "nome": ranking.nome_categoria(c),
                 "meses": [{"id": r["id"], "mes": r["mes"], "nome": ranking.nome_mes(r["mes"]),
                            "arquivo": r["arquivo"]} for r in reversed(rs)]}
                for c, rs in cats.items()]

    if rota == "ranking_analisar" and metodo == "POST":
        try:
            linhas, cat, mes = ranking.ler_relatorio(corpo, q.get("arquivo", ""))
        except ranking.ErroRanking as e:
            raise ErroNuvem(f"Não importado: {e}.")
        return {"categoria": cat, "categoria_nome": ranking.nome_categoria(cat) if cat else "",
                "mes": mes[:7], "marcas": len(linhas), "primeira": linhas[0]["marca"],
                "vendas": sum(l["vendas"] or 0 for l in linhas)}

    if rota == "ranking_importar" and metodo == "POST":
        nome = q.get("arquivo") or "relatorio.xlsx"
        try:
            linhas, cat, mes = ranking.ler_relatorio(corpo, nome)
        except ranking.ErroRanking as e:
            raise ErroNuvem(f"Não importado: {e}.")
        cat = (q.get("categoria") or cat or "").strip().upper()
        mes = (q.get("mes") + "-01") if q.get("mes") else mes
        if not cat or not re.fullmatch(r"\d{4}-\d{2}-01", mes or ""):
            raise ErroNuvem("Informe a categoria e o mês do relatório.")
        h = ranking.hash_de(corpo)
        ja = repo._req("GET", "ranking_relatorios", {"select": "categoria,mes", "hash": repo._eq(h)})
        if ja:
            return {"ok": True, "log": [f"Esse arquivo já foi importado ({ranking.nome_categoria(ja[0]['categoria'])}, "
                                        f"{ranking.nome_mes(ja[0]['mes'])})."], "categoria": ja[0]["categoria"],
                    "mes": ja[0]["mes"][:7]}
        antigos = repo._req("DELETE", "ranking_relatorios", {"categoria": repo._eq(cat), "mes": repo._eq(mes)},
                            prefer="return=representation") or []
        novo = repo._req("POST", "ranking_relatorios", corpo=[{"categoria": cat, "mes": mes, "arquivo": nome,
                                                                "hash": h}], prefer="return=representation")
        rid = novo[0]["id"]
        regs = [dict(l, relatorio_id=rid) for l in linhas]
        try:
            for i in range(0, len(regs), LOTE):
                repo._req("POST", "ranking_linhas", corpo=regs[i:i + LOTE], prefer="return=minimal")
        except ErroNuvem:
            repo._req("DELETE", "ranking_relatorios", {"id": repo._eq(rid)})
            raise
        log = [f"OK: {ranking.nome_categoria(cat)} · {ranking.nome_mes(mes)} · {len(linhas)} marcas"]
        if antigos:
            log.append("(substituiu o relatório anterior do mesmo mês)")
        return {"ok": True, "log": log, "categoria": cat, "mes": mes[:7]}

    if rota == "ranking_relatorio":
        cat = q["categoria"]
        rels = _relatorios(repo, cat)
        if not rels:
            raise ErroNuvem("Nenhum relatório importado para esta categoria.", 404)
        mes = q.get("mes")
        idx = next((i for i, r in enumerate(rels) if r["mes"][:7] == mes), len(rels) - 1)
        atual = rels[idx]
        ant = rels[idx - 1] if idx > 0 else None
        linhas = _linhas(repo, atual["id"])
        linhas_ant = _linhas(repo, ant["id"]) if ant else None
        tabela, saiu, resumo = ranking.analisar(linhas, linhas_ant, repo.marcas())
        return {"categoria": cat, "categoria_nome": ranking.nome_categoria(cat),
                "mes": atual["mes"][:7], "mes_nome": ranking.nome_mes(atual["mes"]), "id": atual["id"],
                "arquivo": atual["arquivo"],
                "anterior": {"mes": ant["mes"][:7], "nome": ranking.nome_mes(ant["mes"])} if ant else None,
                "meses": [{"mes": r["mes"][:7], "nome": ranking.nome_mes(r["mes"]), "id": r["id"]} for r in reversed(rels)],
                "resumo": resumo, "marcas": tabela, "sairam": saiu}

    if rota == "ranking_marca":
        cat, chave = q["categoria"], nubi.compacta(q["marca"])
        rels = {r["id"]: r for r in _relatorios(repo, cat)}
        if not rels:
            return {"historico": []}
        ids = ",".join(str(i) for i in rels)
        linhas = repo._todos("ranking_linhas", {"select": "*", "marca_chave": repo._eq(chave),
                                                "relatorio_id": f"in.({ids})", "order": "relatorio_id"})
        hist = []
        for l in linhas:
            r = rels[l["relatorio_id"]]
            l.pop("bruto", None)
            hist.append(dict(l, mes=r["mes"][:7], mes_nome=ranking.nome_mes(r["mes"]),
                             ticket=ranking._div(l["vendas"], l["unidades"]),
                             vendas_por_vendedor=ranking._div(l["vendas"], l["vendedores"])))
        hist.sort(key=lambda x: x["mes"])
        return {"marca": hist[-1]["marca"] if hist else q["marca"], "historico": hist,
                "meses_total": len(rels)}

    if rota == "ranking_bi":
        cat = q["categoria"]
        rels = _relatorios(repo, cat)
        if q.get("desde"):
            rels = [r for r in rels if r["mes"][:7] >= q["desde"]] or rels
        if q.get("ate"):
            rels = [r for r in rels if r["mes"][:7] <= q["ate"]] or rels
        if not rels:
            raise ErroNuvem("Nenhum relatório importado para esta categoria.", 404)
        ids = ",".join(str(r["id"]) for r in rels)
        linhas = repo._todos("ranking_linhas", {
            "select": "relatorio_id,posicao,variacao,marca,marca_chave,vendas,unidades,tendencia,catalogo,"
                      "vendedores,saturacao,ranking_demanda",
            "relatorio_id": f"in.({ids})", "order": "relatorio_id,posicao"})
        por_rel = {r["id"]: [] for r in rels}
        for l in linhas:
            por_rel[l["relatorio_id"]].append(l)
        todos = _relatorios(repo, cat)
        r = ranking.bi([x["mes"] for x in rels], [por_rel[x["id"]] for x in rels], repo.marcas())
        r.update({"categoria": cat, "categoria_nome": ranking.nome_categoria(cat),
                  "todos_meses": [{"mes": x["mes"][:7], "nome": ranking.nome_mes(x["mes"])} for x in todos]})
        return r

    if rota == "ranking_apagar" and metodo == "POST":
        repo._req("DELETE", "ranking_relatorios", {"id": repo._eq(int(q["id"]))})
        return {"ok": True}

    raise ErroNuvem("Rota desconhecida.", 404)



# ---------------------------------------------------------------------------
# 5. Vendedores monitorados
# ---------------------------------------------------------------------------

CAMPOS_VEND = ["titulo", "marca", "marca_chave", "gtin", "sku", "vendas", "unidades", "preco", "tipo_pub",
               "fulfillment", "catalogo", "frete_gratis", "desconto", "estado", "bruto"]


def _vend_rels(repo, vendedor=None):
    p = {"select": "id,vendedor,mes,arquivo,importado_em", "order": "vendedor,mes"}
    if vendedor:
        p["vendedor"] = repo._eq(vendedor)
    return repo._todos("vend_relatorios", p)


def _vend_linhas(repo, rid, bruto=False):
    sel = ",".join(c for c in CAMPOS_VEND if bruto or c != "bruto")
    ls = repo._todos("vend_anuncios", {"select": sel, "relatorio_id": repo._eq(int(rid)), "order": "id"})
    for l in ls:
        l["full"] = bool(l.pop("fulfillment"))
        l["vendas"] = float(l["vendas"] or 0)
        l["preco"] = float(l["preco"] or 0)
        l["unidades"] = int(l["unidades"] or 0)
    return ls


def _ranking_do_mes(repo, mes, chaves):
    """Ranking de marcas do mesmo mês: a categoria que mais tem marcas do vendedor.
    Devolve (categoria, {marca_chave: linha}, bi até o mês) ou (None, {}, None)."""
    rels = [r for r in _relatorios(repo) if r["mes"][:7] <= mes]
    if not rels:
        return None, {}, None
    melhor = None
    for cat in sorted({r["categoria"] for r in rels if r["mes"][:7] == mes}):
        r = next(r for r in rels if r["categoria"] == cat and r["mes"][:7] == mes)
        ls = _linhas(repo, r["id"])
        n = sum(1 for l in ls if l["marca_chave"] in chaves)
        if melhor is None or n > melhor[0]:
            melhor = (n, cat, ls)
    if melhor is None:
        return None, {}, None
    _, cat, ls = melhor
    rels_cat = [r for r in rels if r["categoria"] == cat]
    ids = ",".join(str(r["id"]) for r in rels_cat)
    todas = repo._todos("ranking_linhas", {
        "select": "relatorio_id,posicao,variacao,marca,marca_chave,vendas,unidades,tendencia,catalogo,"
                  "vendedores,saturacao,ranking_demanda",
        "relatorio_id": f"in.({ids})", "order": "relatorio_id,posicao"})
    por_rel = {r["id"]: [] for r in rels_cat}
    for l in todas:
        por_rel[l["relatorio_id"]].append(l)
    bi = ranking.bi([r["mes"] for r in rels_cat], [por_rel[r["id"]] for r in rels_cat])
    return cat, {l["marca_chave"]: l for l in ls}, bi


def _explorador_cruzado(repo, vendedor):
    snaps = repo.snapshots()
    if snaps.empty:
        return {}
    por_marca = {}
    for marca, g in snaps.groupby("marca"):
        s = g.iloc[-1]
        df = nubi.preparar(repo.anuncios(s["id"]))
        por_marca[marca] = (df, f"{nubi.fmt_data(s['inicio'])} a {nubi.fmt_data(s['fim'])}")
    return vendedores.cruzar_explorador(por_marca, vendedor)


def rota_vendedores(repo, metodo, rota, q, corpo):
    if rota == "vend_lista":
        rels = _vend_rels(repo)
        out = {}
        for r in rels:
            out.setdefault(r["vendedor"], []).append({"id": r["id"], "mes": r["mes"][:7],
                                                      "nome": ranking.nome_mes(r["mes"]), "arquivo": r["arquivo"]})
        return [{"vendedor": v, "meses": list(reversed(ms))} for v, ms in out.items()]

    if rota == "vend_analisar" and metodo == "POST":
        try:
            linhas, vend, mes = vendedores.ler_vendedor(corpo, q.get("arquivo", ""))
        except vendedores.ErroVendedor as e:
            raise ErroNuvem(f"Não importado: {e}.")
        return {"vendedor": vend, "mes": mes, "anuncios": len(linhas),
                "vendas": sum(l["vendas"] for l in linhas), "unidades": sum(l["unidades"] for l in linhas),
                "marcas": len({l["marca_chave"] for l in linhas})}

    if rota == "vend_importar" and metodo == "POST":
        nome = q.get("arquivo") or "vendedor.xlsx"
        try:
            linhas, vend, mes = vendedores.ler_vendedor(corpo, nome)
        except vendedores.ErroVendedor as e:
            raise ErroNuvem(f"Não importado: {e}.")
        vend = (q.get("vendedor") or vend or "").strip().upper()
        mes = q.get("mes") or mes
        if not vend or not re.fullmatch(r"\d{4}-\d{2}", mes or ""):
            raise ErroNuvem("Informe o vendedor e o mês do relatório.")
        h = ranking.hash_de(corpo)
        ja = repo._req("GET", "vend_relatorios", {"select": "vendedor,mes", "hash": repo._eq(h)})
        if ja:
            return {"ok": True, "log": [f"Esse arquivo já foi importado ({ja[0]['vendedor']}, "
                                        f"{ranking.nome_mes(ja[0]['mes'])})."],
                    "vendedor": ja[0]["vendedor"], "mes": ja[0]["mes"][:7]}
        antigos = repo._req("DELETE", "vend_relatorios", {"vendedor": repo._eq(vend), "mes": repo._eq(mes + "-01")},
                            prefer="return=representation") or []
        novo = repo._req("POST", "vend_relatorios", corpo=[{"vendedor": vend, "mes": mes + "-01", "arquivo": nome,
                                                            "hash": h}], prefer="return=representation")
        rid = novo[0]["id"]
        regs = []
        for l in linhas:
            r = {c: l.get(c) for c in CAMPOS_VEND if c != "fulfillment"}
            r["fulfillment"] = bool(l["full"])
            r["relatorio_id"] = rid
            regs.append(r)
        try:
            for i in range(0, len(regs), LOTE):
                repo._req("POST", "vend_anuncios", corpo=regs[i:i + LOTE], prefer="return=minimal")
        except ErroNuvem:
            repo._req("DELETE", "vend_relatorios", {"id": repo._eq(rid)})
            raise
        log = [f"OK: {vend} · {ranking.nome_mes(mes + '-01')} · {len(linhas)} anúncios · "
               f"R$ {sum(l['vendas'] for l in linhas):,.0f}".replace(",", ".")]
        if antigos:
            log.append("(substituiu o relatório anterior do mesmo mês)")
        return {"ok": True, "log": log, "vendedor": vend, "mes": mes}

    if rota == "vend_relatorio":
        vend = q["vendedor"]
        rels = _vend_rels(repo, vend)
        if not rels:
            raise ErroNuvem("Nenhum relatório deste vendedor.", 404)
        mes = q.get("mes")
        idx = next((i for i, r in enumerate(rels) if r["mes"][:7] == mes), len(rels) - 1)
        atual, ant = rels[idx], (rels[idx - 1] if idx > 0 else None)
        linhas = _vend_linhas(repo, atual["id"])
        linhas_ant = _vend_linhas(repo, ant["id"]) if ant else None
        cat, rk_mes, bi = _ranking_do_mes(repo, atual["mes"][:7], {l["marca_chave"] for l in linhas})
        ex = _explorador_cruzado(repo, vend)
        r = vendedores.analisar(linhas, linhas_ant, rk_mes, bi, ex, vend)
        # evolução mês a mês
        evol = []
        for x in rels:
            ls = linhas if x["id"] == atual["id"] else (linhas_ant if ant and x["id"] == ant["id"]
                                                         else _vend_linhas(repo, x["id"]))
            evol.append(dict(vendedores.resumo(ls), mes=x["mes"][:7], nome=ranking.nome_mes(x["mes"])))
        r.update({"vendedor": vend, "mes": atual["mes"][:7], "mes_nome": ranking.nome_mes(atual["mes"]),
                  "id": atual["id"], "arquivo": atual["arquivo"],
                  "anterior": {"mes": ant["mes"][:7], "nome": ranking.nome_mes(ant["mes"])} if ant else None,
                  "meses": [{"mes": x["mes"][:7], "nome": ranking.nome_mes(x["mes"])} for x in reversed(rels)],
                  "evolucao": evol, "ranking": {"categoria": cat, "categoria_nome": ranking.nome_categoria(cat) if cat else "",
                                                "mes_ok": bool(rk_mes)},
                  "explorador_gtins": sum(1 for p in r["produtos"] if p["ex_preco_medio"] is not None)})
        return r

    if rota == "vend_comparar":
        rels = _vend_rels(repo)
        if not rels:
            return {"meses": [], "vendedores": []}
        meses = sorted({r["mes"][:7] for r in rels})
        mes = q.get("mes") if q.get("mes") in meses else meses[-1]
        do_mes = [r for r in rels if r["mes"][:7] == mes]
        vends, matriz = [], {}
        todas_chaves = set()
        dados = []
        for r in do_mes:
            ls = _vend_linhas(repo, r["id"])
            dados.append((r, ls))
            todas_chaves |= {l["marca_chave"] for l in ls}
        cat, rk_mes, _ = _ranking_do_mes(repo, mes, todas_chaves)
        for r, ls in dados:
            z = vendedores.resumo(ls)
            antes = [x for x in rels if x["vendedor"] == r["vendedor"] and x["mes"][:7] < mes]
            if antes:
                za = vendedores.resumo(_vend_linhas(repo, antes[-1]["id"]))
                z["var_vendas"] = (z["vendas"] / za["vendas"] - 1) if za["vendas"] else None
            por_m = {}
            for l in ls:
                x = por_m.setdefault(l["marca_chave"], {"marca": l["marca"], "vendas": 0.0})
                x["vendas"] += l["vendas"]
            top = sorted(por_m.values(), key=lambda x: -x["vendas"])[:3]
            z.update({"vendedor": r["vendedor"], "top_marcas": [t["marca"] for t in top]})
            vends.append(z)
            for k, x in por_m.items():
                m = matriz.setdefault(k, {"marca": x["marca"], "total": 0.0, "por": {}})
                m["por"][r["vendedor"]] = x["vendas"]
                m["total"] += x["vendas"]
        linhas_m = sorted(matriz.items(), key=lambda kv: -kv[1]["total"])[:25]
        mat = []
        for k, m in linhas_m:
            rk = rk_mes.get(k)
            mat.append({"marca": m["marca"], "total": m["total"], "por": m["por"],
                        "rk_posicao": rk["posicao"] if rk else None, "rk_vendas": rk["vendas"] if rk else None})
        vends.sort(key=lambda z: -z["vendas"])
        return {"mes": mes, "mes_nome": ranking.nome_mes(mes + "-01"), "meses": list(reversed(meses)),
                "vendedores": vends, "matriz": mat, "categoria": cat}

    if rota == "vend_apagar" and metodo == "POST":
        repo._req("DELETE", "vend_relatorios", {"id": repo._eq(int(q["id"]))})
        return {"ok": True}

    raise ErroNuvem("Rota desconhecida.", 404)

def _json(obj, status=200):
    def padrao(o):
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        return _limpo(o)
    return status, "application/json; charset=utf-8", json.dumps(obj, ensure_ascii=False,
                                                                 default=padrao).encode("utf-8"), {}
