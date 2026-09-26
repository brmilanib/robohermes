# -*- coding: utf-8 -*-
"""
nubi na nuvem: o mesmo motor do nubi.py, com os dados no Supabase e as telas no
navegador. Este módulo tem três partes:

1. RepoSupabase — guarda e lê os dados pela API REST do Supabase, com o login de
   quem está usando a página (as regras de acesso ficam no próprio banco).
2. relatorio() — calcula as tabelas da marca (as mesmas do Excel) em JSON.
3. atender() — as rotas da API chamadas pela página (api/app.py).
"""

import hashlib
import json
import math
import os
import re
import statistics
import time
import traceback
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import pandas as pd

import nubi
import ranking
import categorias
import ia
import pesquisa_marca
import produtos_iguais
import auditoria
import agentes
import estoque
import reuniao
import vend_bi
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
AGENTES_LOCAIS = ("Hermes", "Qwen (revisor)", "DeepSeek R1 (Mac)", "Ferreiro (Claude no Mac)")   # modelos grátis que rodam no Mac mini (Ollama)
# Conversa direta na Sala (card #64, fase 2): nome de exibição de cada agente que aparece na lista de conversas.
CONVERSA_NOME = {"claude": "Claude", "chatgpt": "ChatGPT", "deepseek": "DeepSeek", "gptoss": "gpt-oss",
                 "astra": "Astra (design)", "hermes": "Hermes", "qwen": "Qwen (revisor)",
                 "claude_mac": "Ferreiro (Claude no Mac)", "copilot": "Copilot"}
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


def _dt_utc(ts):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _duracoes_feitas_por_responsavel(tarefas):
    por_resp = {}
    for t in tarefas:
        if t.get("status") != "feita":
            continue
        resp = str(t.get("responsavel") or "").strip()
        if not resp:
            continue
        ini, fim = _dt_utc(t.get("iniciado_em")), _dt_utc(t.get("atualizado_em"))
        if not ini or not fim or fim < ini:
            continue
        dur = (fim - ini).total_seconds() / 60
        por_resp.setdefault(resp, []).append((fim, dur))
    refs = {}
    for resp, vals in por_resp.items():
        vals.sort(key=lambda x: x[0], reverse=True)
        refs[resp] = [d for _, d in vals[:20]]
    return refs


def _previsao_min_card_execucao(tarefa, refs_por_responsavel, agora=None):
    if tarefa.get("status") not in ("em_desenvolvimento", "em_teste"):
        return None
    resp = str(tarefa.get("responsavel") or "").strip()
    refs = refs_por_responsavel.get(resp) if resp else None
    if not refs or len(refs) < 3:
        return None
    ini = _dt_utc(tarefa.get("iniciado_em"))
    if not ini:
        return None
    ag = agora or datetime.now(timezone.utc)
    rodando = max(0, (ag - ini).total_seconds() / 60)
    return max(5, int(math.ceil(statistics.median(refs) - rodando)))


def atender(metodo, rota, q, corpo, token):
    """Devolve (status, tipo de conteúdo, bytes, cabeçalhos extras)."""
    t0 = time.monotonic()
    try:
        if rota == "agente" and CRON_SECRET and token == CRON_SECRET:
            # Chamada da agenda (Vercel Cron manda "Authorization: Bearer CRON_SECRET").
            return _json(rodar_agente(RepoSupabase(login_agente()), "agendado"))
        if rota in ("rotinas_cron", "rotina_8h") and CRON_SECRET and token == CRON_SECRET:
            # de hora em hora (Vercel Cron): as tarefas de rotina do servidor cujo dia e horário chegaram
            rc = RepoSupabase(login_agente())
            ligar_registro_uso(rc, "rotinas")
            return _json(rodar_rotinas(rc))
        repo = RepoSupabase(token)
        ligar_registro_uso(repo, rota)
        if rota == "agente" and metodo == "POST":
            seg = min(TEMPO_MAX, int(q.get("segundos") or 60))
            return _json(rodar_agente(repo, q.get("origem") or "manual", q.get("marca") or None, seg))
        if rota == "agente_status":
            ult = repo._req("GET", "agente_execucoes", {"select": "*", "order": "id.desc", "limit": 15,
                                                        "origem": "neq." + REGRA_ATUAL}) or []
            for u in ult:
                u["log"] = (u.get("log") or "")[-4000:]
            return _json({"execucoes": ult, "agendado": bool(CRON_SECRET and AGENTE_EMAIL)})
        if rota == "versao":
            # a página compara com a versão que carregou e se recarrega sozinha quando sai uma nova
            return _json({"v": os.environ.get("VERCEL_GIT_COMMIT_SHA", "")[:12]})
        if rota == "painel":
            # A tabela acesso só devolve a linha de quem está liberado (RLS).
            if not repo._req("GET", "acesso", {"select": "email", "limit": 1}):
                raise ErroNuvem("Este e-mail ainda não tem acesso ao nubi. Peça para liberar.", 403)
            return _json(repo.painel())

        if rota == "coletor_status":
            # consultado a cada 4 s durante a coleta: log só da que está rodando; o resto via coletor_log
            ult = repo._req("GET", "coletor_execucoes", {"select": "*", "order": "id.desc", "limit": 10}) or []
            parado = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
            for u in ult:
                if u.get("em_andamento") and str(u.get("atualizado_em") or u.get("iniciado_em") or "") < parado:
                    # sem notícia há 30 min: o processo parou sem avisar (Mac dormiu, Terminal fechado)
                    u["em_andamento"] = False
                    u["ok"] = False
                    u["mensagem"] = "parou sem avisar (sem notícia do Mac há mais de 30 min); a próxima coleta continua de onde parou"
                lg = u.get("log") or ""
                u["tem_log"] = bool(lg)
                u["log"] = lg[-12000:] if u.get("em_andamento") else ""
            try:
                ped = repo._req("GET", "coletor_pedidos", {"select": "id,pedido_em,motivo", "atendido_em": "is.null",
                                                           "order": "id.desc", "limit": 1}) or []
            except ErroNuvem:
                ped = []
            return _json({"execucoes": ult, "pedido": ped[0] if ped else None})
        if rota == "coletor_log":
            r = repo._req("GET", "coletor_execucoes", {"select": "log", "id": repo._eq(int(q.get("id", 0)))}) or []
            return _json({"log": (r[0].get("log") or "") if r else ""})
        if rota == "coletor_registrar" and metodo == "POST":
            # Chamado no começo (em_andamento), a cada poucos segundos (andamento + log) e no fim.
            d = json.loads(corpo or b"{}")
            reg = {k: d[k] for k in ("iniciado_em", "terminado_em", "tarefa", "ok", "arquivos", "importados",
                                     "erros", "mensagem", "em_andamento", "feito", "total", "atual") if k in d}
            if "log" in d:
                reg["log"] = str(d.get("log") or "")[-20000:]
            reg["atualizado_em"] = datetime.now(timezone.utc).isoformat()
            if d.get("id"):
                repo._req("PATCH", "coletor_execucoes", {"id": repo._eq(int(d["id"]))}, corpo=reg,
                          prefer="return=minimal")
                if d.get("em_andamento") is False and d.get("tarefa") in ("estoque", "gestor", "memoria"):
                    _marcar_rotina(repo, d["tarefa"], ("" if d.get("ok") else "erro: ") + str(d.get("mensagem") or ""))
                if d.get("em_andamento") is False and d.get("tarefa") == "diario":
                    try:
                        rt = (repo._req("GET", "rotinas", {"select": "*", "id": "eq.resumo_dia"}) or [None])[0]
                        ag = _agora_br()
                        # coleta terminou depois do horário do resumo: o resumo dos dados novos sai agora
                        if rt and rt.get("ativo") and rotina_no_dia(rt, ag) and ag.strftime("%H:%M") >= rt["horario"]:
                            x = gerar_resumo_dia(repo)
                            if x["novo"]:
                                _marcar_rotina(repo, "resumo_dia", f"dados até {_ddmm(x['atual']['chave'].split('|')[1])}: "
                                                                   "gerado quando a coleta terminou")
                    except Exception:  # noqa: BLE001
                        pass
                return _json({"ok": True, "id": int(d["id"])})
            novo = repo._req("POST", "coletor_execucoes", corpo=[reg], prefer="return=representation")
            return _json({"ok": True, "id": novo[0]["id"] if novo else None})
        if rota == "coletor_pedir" and metodo == "POST":
            # "Rodar coleta agora": o vigia do Mac (a cada 15 min) pega o pedido e roda a coleta
            d = json.loads(corpo or b"{}")
            tarefa = "estoque" if d.get("tarefa") == "estoque" else "diario"
            aberto = repo._req("GET", "coletor_pedidos", {"select": "id", "atendido_em": "is.null", "tarefa": repo._eq(tarefa),
                                                          "limit": 1}) or []
            if not aberto:
                repo._req("POST", "coletor_pedidos", corpo=[{"motivo": str(d.get("motivo") or "pedido no site")[:200],
                                                             "tarefa": tarefa}], prefer="return=minimal")
            return _json({"ok": True, "ja_havia": bool(aberto)})
        if rota == "coletor_pedido":
            # o vigia do Mac pergunta se há pedido de coleta (dos últimos 2 dias)
            desde = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
            p = repo._req("GET", "coletor_pedidos", {"select": "id,motivo,tarefa,pedido_em", "atendido_em": "is.null",
                                                     "pedido_em": f"gte.{desde}", "order": "id", "limit": 1}) or []
            return _json({"pedido": p[0] if p else None})
        if rota == "coletor_pedido_ok" and metodo == "POST":
            d = json.loads(corpo or b"{}")
            filtro = {"atendido_em": "is.null", "id": f"lte.{int(d.get('id') or 0)}"}
            if d.get("tarefa"):
                filtro["tarefa"] = repo._eq(str(d["tarefa"]))       # atender o estoque não apaga um pedido de coleta
            repo._req("PATCH", "coletor_pedidos", filtro,
                      corpo={"atendido_em": datetime.now(timezone.utc).isoformat(), "resultado": str(d.get("resultado") or "")[:200]},
                      prefer="return=minimal")
            return _json({"ok": True})
        if rota == "coletor_foto" and metodo == "POST":
            # foto da tela + resumo dos botões quando o coletor erra no Nubimetrics (para ver o erro de fora do Mac)
            d = json.loads(corpo or b"{}")
            repo._req("POST", "coletor_fotos", corpo=[{"execucao_id": d.get("execucao_id"), "rotulo": str(d.get("rotulo") or "")[:200],
                                                       "tela": str(d.get("tela") or "")[:3000],
                                                       "foto": str(d.get("foto") or "")[:1_500_000]}], prefer="return=minimal")
            return _json({"ok": True})
        if rota == "coletor_pendencias":
            # O que já existe no nubi, para o coletor não baixar de novo o que já foi importado.
            vend, por_hash = {}, {}
            for r in _vend_rels(repo):
                vend.setdefault(r["vendedor"], {})[r["mes"][:7]] = r.get("ate")
                if r.get("seller_hash"):
                    por_hash.setdefault(r["seller_hash"], {})[r["mes"][:7]] = r.get("ate")
            rk = {}
            for r in _relatorios(repo):
                rk.setdefault(r["categoria"], []).append(r["mes"][:7])
            try:
                rot = (repo._req("GET", "rotinas", {"select": "ativo,dias_semana,dia_mes", "id": "eq.coleta"}) or [None])[0]
            except ErroNuvem:
                rot = None
            return _json({"vendedores": vend, "hashes": por_hash, "ranking": rk, "rotina": rot})

        if rota == "apelido_ia" and metodo == "POST":
            d = json.loads(corpo or b"{}")
            a, b = (d.get("apelido") or "").strip(), (d.get("marca") or "").strip()
            if not ia.disponivel():
                raise ErroNuvem("Configure uma chave de IA (OPENAI_API_KEY) na Vercel para usar esta função.")
            try:
                j, links, qual = ia.perguntar_json(
                    f'No mercado de perfumes (Mercado Livre Brasil), "{a}" e "{b}" são a MESMA marca escrita de outro jeito '
                    "(erro de digitação, sigla, nome curto/longo, com ou sem acento) ou são marcas DIFERENTES? Pesquise na web se "
                    'precisar. Responda SOMENTE com JSON: {"mesma": true|false, "confianca": "alta|média|baixa", '
                    '"motivo": "<1 frase em português>"}.')
            except Exception as e:  # noqa: BLE001
                raise ErroNuvem(f"A IA não respondeu: {str(e)[:150]}")
            return _json({"mesma": bool(j.get("mesma")), "confianca": j.get("confianca") or "baixa",
                          "motivo": j.get("motivo") or "", "fonte": links[0] if links else "", "ia": ia.nome(qual)})

        if rota.startswith("apelido"):
            return _json(rota_apelidos(repo, metodo, rota, q, corpo))

        if rota.startswith("vend_"):
            return _json(rota_vendedores(repo, metodo, rota, q, corpo))

        if rota == "estoque_gestor":
            # planilha de importação do Gestor Seller (cadastro de produtos) feita da atualização de estoque pedida
            aid = q.get("id") or ((repo._req("GET", "estoque_atualizacoes", {"select": "id", "order": "id.desc", "limit": 1}) or [{}])[0]).get("id")
            if not aid:
                raise ErroNuvem("Ainda não há estoque importado do UpSeller.", 404)
            reg = (repo._req("GET", "estoque_atualizacoes", {"select": "id,criado_em", "id": repo._eq(int(aid))}) or [None])[0]
            if not reg:
                raise ErroNuvem("Atualização de estoque não encontrada.", 404)
            itens = _estoque_itens_ordem(repo, reg["id"])
            nome = f"import_gestor_seller_{_br(reg['criado_em']):%d-%m-%Y}.xlsx"
            return (200, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", estoque.gerar_gestor(itens),
                    {"Content-Disposition": f'attachment; filename="{nome}"', "X-Nome-Arquivo": nome})
        if rota.startswith("estoque") or rota.startswith("gestor_") or rota == "coleta_pendente":
            return _json(rota_estoque(repo, metodo, rota, q, corpo))
        if rota == "conhecimento":
            p = {"select": "id,tipo,titulo,texto,autor,fonte,fixo,atualizado_em", "order": "fixo.desc,atualizado_em.desc", "limit": 200}
            if q.get("q"):
                termo = re.sub(r"[,()*%]", " ", q["q"])[:80].strip()
                p["or"] = f"(titulo.ilike.*{termo}*,texto.ilike.*{termo}*)"
            return _json({"itens": repo._req("GET", "conhecimento", p) or []})
        if rota == "conhecimento_pendente":
            # card #39: o que o Hermes (Mac mini) tem para memorizar desde a última rodada da rotina 'memoria'
            itens, desde = _conhecimento_pendente(repo)
            return _json({"itens": itens, "desde": desde})
        if rota == "memoria_pendente":
            # o vigia do Mac pergunta se está na hora da rotina 'memoria' (Hermes documenta, Qwen revisa)
            rot = (repo._req("GET", "rotinas", {"select": "*", "id": "eq.memoria"}) or [None])[0]
            return _json({"rodar": bool(rot and rotina_pendente(rot)), "horario": (rot or {}).get("horario")})
        if rota == "conhecimento_salvar" and metodo == "POST":
            d = json.loads(corpo or b"{}")
            reg = {k: str(d[k]).strip()[:20000] for k in ("titulo", "texto", "tipo", "fonte") if d.get(k)}
            if not reg.get("titulo") or not reg.get("texto"):
                raise ErroNuvem("Título e texto são obrigatórios.")
            reg["atualizado_em"] = datetime.now(timezone.utc).isoformat()
            if d.get("id"):
                repo._req("PATCH", "conhecimento", {"id": repo._eq(int(d["id"]))}, corpo=reg, prefer="return=minimal")
            else:
                reg.setdefault("tipo", "aprendizado")
                reg["autor"] = str(d.get("autor") or "Bruno")[:60]
                repo._req("POST", "conhecimento", corpo=[reg], prefer="return=minimal")
            return _json({"ok": True})
        if rota.startswith("mac_"):
            return _json(rota_mac(repo, metodo, rota, q, corpo, token))
        if rota.startswith("ml_") or rota == "posicoes" or rota.startswith("rank_"):
            return _json(rota_posicoes(repo, metodo, rota, q, corpo))
        if rota.startswith("agentes"):
            return _json(rota_agentes(repo, metodo, rota, q, corpo))
        if rota.startswith("rotina") or rota.startswith("ops_"):
            return _json(rota_rotinas(repo, metodo, rota, q, corpo))

        if rota == "reuniao":
            apos = int(q.get("apos") or 0)
            conversa = str(q.get("conversa") or "sala").strip()
            p = {"select": "id,autor,texto,criado_em,meta", "id": f"gt.{apos}", "order": "id"}
            if conversa == "sala":
                p["or"] = "(meta.is.null,meta->>conversa.neq.direta)"
            else:
                p["meta->>conversa"] = "eq.direta"
                p["meta->>agente"] = f"eq.{conversa}"
            if q.get("perto") and not apos:                    # abrir uma mensagem antiga achada na pesquisa
                p["id"] = f"gte.{max(0, int(q['perto']) - 60)}"
            msgs = repo._todos("reuniao_mensagens", p)
            if not apos and not q.get("perto"):
                msgs = msgs[-200:]
            try:
                apel = {a["nome"]: a["apelido"] for a in repo._todos("agentes", {"select": "nome,apelido"}) if a.get("apelido")}
            except ErroNuvem:
                apel = {}
            return _json({"mensagens": msgs, "agentes": {k: ia.tem(k) for k in ("chatgpt", "deepseek", "claude", "ollama")},
                          "apelidos": apel,
                          **({"sistema": agentes.SISTEMA} if q.get("sistema") else {})})
        if rota == "reuniao_buscar":
            # barra de pesquisa da Sala (pedido do Bruno, 26/09): mensagens (grupo e diretas) + caixa de conhecimento
            return _json({"resultados": agentes.buscar_arquivo(repo, q.get("q"), int(q.get("n") or 40))})
        if rota == "reuniao_conversas":
            # última mensagem de cada conversa (Sala + uma por agente), para a lista estilo WhatsApp (card #64, fase 2)
            out, nao, lido = reuniao_nao_lidas(repo)
            return _json({"conversas": out, "nao_lidas": nao, "lido": lido})
        if rota == "reuniao_lido" and metodo == "POST":
            d = json.loads(corpo or b"{}")
            conv, uid = str(d.get("conversa") or "sala"), int(d.get("ultimo_id") or 0)
            if conv != "sala" and conv not in CONVERSA_NOME:
                raise ErroNuvem("Conversa desconhecida.")
            atual = (repo._req("GET", "reuniao_leituras", {"select": "ultimo_id", "conversa": repo._eq(conv)}) or [{}])[0].get("ultimo_id") or 0
            if uid > int(atual):                                     # nunca volta para trás (outro aparelho pode estar à frente)
                repo._req("POST", "reuniao_leituras", corpo=[{"conversa": conv, "ultimo_id": uid, "lido_em": datetime.now(timezone.utc).isoformat()}],
                          prefer="resolution=merge-duplicates,return=minimal")
            return _json({"ok": True})
        if rota == "reuniao_postar" and metodo == "POST":
            # agentes locais do Mac mini (Hermes e outros via Ollama) postam a resposta sem abrir uma rodada nova
            d = json.loads(corpo or b"{}")
            autor, texto = str(d.get("autor") or "").strip(), str(d.get("texto") or "").strip()
            if autor not in AGENTES_LOCAIS:
                raise ErroNuvem(f"Autor não permitido: {autor or '?'}.")
            if not texto:
                raise ErroNuvem("Mensagem vazia.")
            aid = {"Hermes": "hermes", "Qwen (revisor)": "qwen", "Ferreiro (Claude no Mac)": "claude_mac"}.get(autor)
            if aid:
                agora_ = datetime.now(timezone.utc).isoformat()
                try:
                    repo._req("POST", "agentes_uso", corpo=[{
                        "agente": aid, "modelo": str(d.get("modelo") or "")[:60], "origem": "sala (Mac)",
                        "inicio": d.get("inicio") or agora_, "fim": agora_, "ok": True, "custo_usd": float(d.get("custo_usd") or 0),
                        "tokens_in": int(d.get("tokens_in") or 0), "tokens_out": int(d.get("tokens_out") or 0)}],
                        prefer="return=minimal")
                    if str(d.get("apelido") or "").strip():
                        repo._req("PATCH", "agentes", {"id": f"eq.{aid}"}, corpo={
                            "apelido": str(d["apelido"]).strip()[:30], "atualizado_em": agora_}, prefer="return=minimal")
                except ErroNuvem:
                    pass
            r = repo._req("POST", "reuniao_mensagens", corpo=[{"autor": autor, "texto": texto[:8000],
                          "meta": {"local": True, "modelo": str(d.get("modelo") or "")[:60]},
                          "criado_em": datetime.now(timezone.utc).isoformat()}], prefer="return=representation")
            return _json({"ok": True, "id": (r or [{}])[0].get("id")})
        if rota == "reuniao_enviar" and metodo == "POST":
            d = json.loads(corpo or b"{}")
            texto = str(d.get("texto") or "").strip()
            if not texto:
                raise ErroNuvem("Escreva a mensagem.")
            if not (ia.tem("chatgpt") or ia.tem("claude") or ia.tem("deepseek")):
                raise ErroNuvem("Nenhuma IA configurada na Vercel.")
            return _json({"novas": reuniao.rodada(repo, texto[:4000])})
        if rota == "reuniao_enviar_direto" and metodo == "POST":
            # conversa direta com um agente (card #64, fase 2): a Sala vira lista de conversas, uma por agente
            d = json.loads(corpo or b"{}")
            chave = str(d.get("agente") or "").strip().lower()
            texto = str(d.get("texto") or "").strip()
            if chave not in CONVERSA_NOME:
                raise ErroNuvem("Agente inválido.")
            if not texto:
                raise ErroNuvem("Escreva a mensagem.")
            # confere ANTES de gravar qualquer coisa (como a reuniao_enviar antiga): sem isso, uma chave que falta na
            # Vercel deixava a mensagem do usuário órfã na conversa, sem resposta nem aviso (achado do revisor)
            aviso_mac = ("O Ferreiro atende só pelo comando fechado do Mac (card 🩺 urgente ou Central); conversa "
                         "direta com ele fica para a próxima fase." if chave == "claude_mac" else
                         "O Copilot atende por tarefa do GitHub aberta pelo Chefe; conversa direta com ele fica para "
                         "a próxima fase." if chave == "copilot" else
                         f"{CONVERSA_NOME[chave]} ainda não responde à conversa direta (fica para a próxima fase); o "
                         "trabalho dele no Mac continua igual, fora daqui." if chave in ("hermes", "qwen")
                         else "")
            if not aviso_mac:
                if chave == "claude" and not ia.tem("claude"):
                    raise ErroNuvem("Claude (coordenador) não configurado.")
                if chave in agentes.AGENTES and not ia.tem(agentes.AGENTES[chave]["qual"]):
                    raise ErroNuvem(f"{CONVERSA_NOME[chave]} não configurado.")
            meta = {"conversa": "direta", "agente": chave}
            agora_ = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731
            repo._req("POST", "reuniao_mensagens", corpo=[{"autor": "voce", "texto": texto[:4000], "meta": meta,
                      "criado_em": agora_()}], prefer="return=minimal")
            if aviso_mac:
                repo._req("POST", "reuniao_mensagens", corpo=[{"autor": "sistema", "texto": aviso_mac, "meta": meta,
                          "criado_em": agora_()}], prefer="return=minimal")
                return _json({"ok": True})
            # a conversa direta agora vai com o histórico dela (antes o agente via só a última mensagem) e com o ARQUIVO
            hist = repo._req("GET", "reuniao_mensagens", {"select": "autor,texto,criado_em", "meta->>conversa": "eq.direta",
                                                          "meta->>agente": f"eq.{chave}", "order": "id.desc", "limit": 21}) or []
            hist = list(reversed(hist))[:-1]                   # sem a mensagem que acabou de chegar
            contexto = ("CONVERSA DIRETA ATÉ AGORA (você e o Bruno):\n" + "\n".join(
                f"[{_br(m['criado_em']):%d/%m %H:%M}] {'Bruno' if m['autor'] == 'voce' else m['autor']}: {str(m['texto'])[:700]}" for m in hist)
                + "\n\n") if hist else ""
            pedido = contexto + "NOVA MENSAGEM DO BRUNO: " + texto
            arq = agentes.arquivo_de(repo)
            try:
                if chave == "claude":
                    resposta = agentes.com_arquivo(lambda t: ia.perguntar(agentes.voz("claude") + t, web=False, max_tokens=800, qual="claude",
                                                                         sistema=agentes.SISTEMA)[0], pedido, arq)
                    nome = "Claude"
                else:
                    nome = agentes.AGENTES[chave]["nome"]
                    resposta = agentes.perguntar(chave, pedido, arquivo=arq)
            except Exception:  # noqa: BLE001
                resposta = ""
            resposta = (resposta or "").strip()
            if resposta:
                repo._req("POST", "reuniao_mensagens", corpo=[{"autor": nome, "texto": resposta[:8000], "meta": meta,
                          "criado_em": agora_()}], prefer="return=minimal")
            else:
                repo._req("POST", "reuniao_mensagens", corpo=[{"autor": "sistema", "texto": "sem resposta do agente",
                          "meta": meta, "criado_em": agora_()}], prefer="return=minimal")
            return _json({"ok": True})
        if rota == "reuniao_duvida" and metodo == "POST":
            # qualquer agente (programador automático, agente do card, especialistas) abre uma dúvida ligada a um card
            d = json.loads(corpo or b"{}")
            tid = int(d.get("tarefa_id") or 0)
            texto = str(d.get("texto") or "").strip()
            if not tid or not texto:
                raise ErroNuvem("Informe o card e a dúvida.")
            try:
                decisao = reuniao.duvida(repo, tid, texto, quem=str(d.get("quem") or "claude_code")[:40], para=d.get("para"))
            except reuniao.ErroDuvida as e:
                raise ErroNuvem(str(e))
            return _json({"ok": True, "decisao": decisao})
        if rota == "reuniao_tarefas":
            ts = repo._todos("reuniao_tarefas", {"select": "*", "order": "id.desc"})
            try:
                evs = repo._req("GET", "tarefa_eventos", {"select": "tarefa_id,autor,tipo,texto,criado_em", "order": "id.desc", "limit": 400}) or []
            except ErroNuvem:
                evs = []
            try:
                apelidos = {a["id"]: a["apelido"] for a in repo._todos("agentes", {"select": "id,apelido"}) if a.get("apelido")}
            except ErroNuvem:
                apelidos = {}
            refs = _duracoes_feitas_por_responsavel(ts)
            ult = {}
            for e in evs:
                ult.setdefault(e["tarefa_id"], e)
            for t in ts:
                t["ultimo_evento"] = ult.get(t["id"])
                t["n_eventos"] = sum(1 for e in evs if e["tarefa_id"] == t["id"])
                if t.get("status") in ("em_desenvolvimento", "em_teste"):
                    t["previsao_min"] = _previsao_min_card_execucao(t, refs)
                if t.get("responsavel") in apelidos:
                    t["responsavel_apelido"] = apelidos[t["responsavel"]]
                if t.get("testador") in apelidos:
                    t["testador_apelido"] = apelidos[t["testador"]]
            return _json({"tarefas": ts, "status": reuniao.STATUS, "apelidos": apelidos})
        if rota == "tarefa_eventos":
            tid = int(q.get("id") or 0)
            t = (repo._req("GET", "reuniao_tarefas", {"select": "*", "id": repo._eq(tid)}) or [None])[0]
            if not t:
                raise ErroNuvem("Tarefa não encontrada.", 404)
            evs = repo._todos("tarefa_eventos", {"select": "*", "tarefa_id": f"eq.{tid}", "order": "id"})
            return _json({"tarefa": t, "eventos": evs})
        if rota == "tarefa_agente_entregar" and metodo == "POST":
            # o Hermes (Mac) entrega o card que fez; o coordenador testa
            d = json.loads(corpo or b"{}")
            autor = str(d.get("autor") or "hermes")
            if autor not in AGENTES_MAC:
                raise ErroNuvem("Autor não permitido.")
            return _json({"ok": True, "resultado": entregar_card(repo, int(d.get("id") or 0), autor, str(d.get("texto") or ""))})
        if rota == "tarefa_mac_passo" and metodo == "POST":
            # o Ferreiro (Claude Code no Mac mini, pela API) registra o trabalho no card: começou (em_desenvolvimento),
            # passo, e entregou num branch (em_teste, o Chefe revisa, junta e publica). Nunca fecha nem publica.
            d = json.loads(corpo or b"{}")
            tid, tipo = int(d.get("id") or 0), str(d.get("tipo") or "passo")
            if not tid or tipo not in ("passo", "erro_teste", "relatorio"):
                raise ErroNuvem("Card ou tipo inválido.")
            _evento(repo, tid, "claude_mac", str(d.get("texto") or "")[:7500], tipo=tipo)
            reg = {"atualizado_em": datetime.now(timezone.utc).isoformat()}
            if d.get("status") == "em_desenvolvimento":
                reg.update(status="em_desenvolvimento", responsavel="claude_mac", iniciado_em=reg["atualizado_em"])
            elif d.get("status") == "em_teste":
                reg.update(status="em_teste", responsavel="claude_mac", testador="claude_code")
            elif d.get("status") == "aprovada":           # não conseguiu: devolve para o programador-chefe
                reg.update(status="aprovada", responsavel="claude_code")
            repo._req("PATCH", "reuniao_tarefas", {"id": repo._eq(tid)}, corpo=reg, prefer="return=minimal")
            return _json({"ok": True})
        if rota == "tarefa_responder" and metodo == "POST":
            # o dono responde ao agente dentro do card (aprovar, recusar ou escrever)
            d = json.loads(corpo or b"{}")
            tid, texto = int(d.get("id") or 0), str(d.get("texto") or "").strip()
            dec = d.get("decisao")
            if dec == "aprovar":
                texto = "✅ Aprovado" + (f": {texto}" if texto else "")
            elif dec == "recusar":
                texto = "❌ Não aprovado" + (f": {texto}" if texto else "")
            if not texto:
                raise ErroNuvem("Escreva a resposta.")
            agora_ = datetime.now(timezone.utc).isoformat()
            repo._req("POST", "tarefa_eventos", corpo=[{"tarefa_id": tid, "autor": "voce", "tipo": "resposta", "texto": texto[:4000],
                                                        "criado_em": agora_}], prefer="return=minimal")
            mud = {"aguardando": None, "atualizado_em": agora_}
            atual = (repo._req("GET", "reuniao_tarefas", {"select": "status", "id": repo._eq(tid)}) or [{}])[0]
            if atual.get("status") == "proposta" and dec in ("aprovar", "recusar"):
                mud.update(status="aprovada" if dec == "aprovar" else "recusada", decidido_por="Bruno")
            repo._req("PATCH", "reuniao_tarefas", {"id": repo._eq(tid)}, corpo=mud, prefer="return=minimal")
            if d.get("texto"):
                # o agente do card responde na hora (e pode pedir um comando da lista fechada ao Mac)
                try:
                    responder_card(repo, tid)
                except Exception as e:  # noqa: BLE001
                    repo._req("POST", "tarefa_eventos", corpo=[{"tarefa_id": tid, "autor": "sistema", "tipo": "status",
                                                                "texto": f"o agente não conseguiu responder agora ({str(e)[:150]})"}],
                              prefer="return=minimal")
            return _json({"ok": True})
        if rota == "reuniao_tarefa_salvar" and metodo == "POST":
            d = json.loads(corpo or b"{}")
            reg = {k: d[k] for k in ("titulo", "descricao", "status", "prioridade", "area", "notas", "tipo", "responsavel", "risco")
                   if k in d}
            if "status" in reg and reg["status"] not in reuniao.STATUS:
                raise ErroNuvem("Status inválido.")
            reg["atualizado_em"] = datetime.now(timezone.utc).isoformat()
            if d.get("id"):
                if reg.get("status") == "em_desenvolvimento":
                    reg["iniciado_em"] = reg["atualizado_em"]
                repo._req("PATCH", "reuniao_tarefas", {"id": repo._eq(int(d["id"]))}, corpo=reg, prefer="return=minimal")
                if "status" in reg:
                    try:
                        repo._req("POST", "tarefa_eventos", corpo=[{"tarefa_id": int(d["id"]), "autor": "voce", "tipo": "status",
                                  "texto": f"Status mudou para: {reg['status'].replace('_', ' ')}", "criado_em": reg["atualizado_em"]}],
                                  prefer="return=minimal")
                    except ErroNuvem:
                        pass
            else:
                if not str(reg.get("titulo") or "").strip():
                    raise ErroNuvem("Dê um título para a tarefa.")
                reg.update(proposto_por=str(d.get("autor") or "voce")[:40], decidido_por="voce")
                novo = repo._req("POST", "reuniao_tarefas", corpo=[reg], prefer="return=representation") or [{}]
                return _json({"ok": True, "id": novo[0].get("id")})
            return _json({"ok": True})

        if rota == "auditoria":
            # relatório da auditoria de dados e código (o mais recente, ou o de ?data=)
            lista = repo._req("GET", "auditorias", {"select": "data,resumo", "order": "data.desc", "limit": 30}) or []
            d = q.get("data") or (lista[0]["data"] if lista else None)
            atual = (repo._req("GET", "auditorias", {"select": "*", "data": repo._eq(d)}) or [None])[0] if d else None
            return _json({"atual": atual, "datas": [x["data"] for x in lista],
                          "ias": {"chatgpt": ia.tem("chatgpt"), "claude": ia.tem("claude"), "deepseek": ia.tem("deepseek")},
                          "modelo_codigo": ia.modelo_codex() if ia.tem("chatgpt") else "—"})

        if rota == "resumo_semana":
            if metodo == "POST":
                return _json(gerar_resumo_semana(repo, forcar=bool(q.get("novo"))))
            lista = repo._req("GET", "ia_resumos", {"select": "chave,texto,ia,criado_em", "chave": "like.semana|*",
                                                    "order": "chave.desc", "limit": 12}) or []
            esc = next((x for x in lista if x["chave"].endswith(q.get("data") or "#")), lista[0] if lista else None)
            return _json({"atual": esc, "datas": [x["chave"].split("|")[1] for x in lista]})

        if rota == "inicio":
            return _json(tela_inicio(repo))
        if rota == "inicio_extras":
            return _json(inicio_extras(repo))
        if rota == "inicio_decisoes":
            return _json(inicio_decisoes(repo))
        if rota == "resumo_dia":
            # resumo diário dos vendedores monitorados (o mais recente, ou o de ?data=AAAA-MM-DD)
            if metodo == "POST":
                return _json(gerar_resumo_dia(repo, forcar=bool(q.get("novo"))))
            lista = repo._req("GET", "ia_resumos", {"select": "chave,texto,ia,criado_em", "chave": "like.vendedores|*",
                                                    "order": "chave.desc", "limit": 15}) or []
            esc = next((x for x in lista if x["chave"].endswith(q.get("data", ""))), lista[0] if lista else None) \
                if q.get("data") else (lista[0] if lista else None)
            data = esc["chave"].split("|")[1] if esc else None
            try:
                pnl = _painel_dia(repo, data)
            except ErroNuvem:
                pnl = {"tem": False}
            return _json({"atual": esc, "datas": [x["chave"].split("|")[1] for x in lista],
                          "disponivel": bool(ia.disponivel()), "painel": pnl})

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
            grupos = nubi.agrupar_marcas(df, existentes, {k: v[1] for k, v in apelidos(repo).items()})
            return _json({"grupos": [{k: v for k, v in g.items() if k != "linhas"} for g in grupos],
                          "marca": ident and ident["marca"], "nome": ident and nubi.nome_bonito(ident["marca"]),
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
            if q.get("marcas"):
                # arquivo com várias marcas: cada marca escolhida vira um card próprio
                ini = _data(q.get("inicio") or (m.group(2) if m else ""), "Data inicial")
                fim = _data(q.get("fim") or (m.group(3) if m else ""), "Data final")
                if fim < ini:
                    raise ErroNuvem("A data final é anterior à inicial.")
                feitas = nubi.importar_por_marca(repo, cfg, nome, corpo, ini, fim, q["marcas"].split(","),
                                                 {k: v[1] for k, v in apelidos(repo).items()})
                return _json({"marca": feitas[0] if feitas else None, "marcas": feitas, "log": log, "duvidas": 0})
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

        if rota == "apagar_marca" and metodo == "POST":
            marca = nubi.chave_marca(q["marca"])
            snaps = repo.snapshots(marca)
            for sid in ([] if snaps.empty else snaps["id"].tolist()):
                repo.apagar_snapshot(sid)
            repo._req("DELETE", "marcas_config", {"marca": repo._eq(marca)})
            return _json({"ok": True, "periodos": 0 if snaps.empty else len(snaps)})

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
    return unificar_marcas(repo, repo._todos("ranking_linhas", {"select": "*", "relatorio_id": repo._eq(int(rid)),
                                                                 "order": "posicao"}), somar=True)


def _guardar_resumo(repo, chave, texto, qual, dados=None):
    reg = {"chave": chave, "texto": texto, "ia": ia.nome(qual), "criado_em": datetime.now(timezone.utc).isoformat()}
    if dados is not None:
        reg["dados"] = dados
    repo._req("POST", "ia_resumos", corpo=[reg], prefer="resolution=merge-duplicates,return=minimal")


# Resumos em FORMATO FIXO: a IA devolve JSON (structured outputs) com as seções abaixo; o nubi monta o texto dos cards
# sempre igual e liga cada tópico ao vendedor, produto ou marca citado.
SECOES_DIA = [("resumo", "📊", "O dia em resumo"), ("alta", "🔥", "Produtos que puxaram o dia"),
              ("queda", "📉", "Quedas e sinais de atenção"), ("periodo", "📆", "Mesmo período no mês"),
              ("estoque", "📦", "Estoque dos concorrentes"), ("oportunidade", "💡", "Oportunidades"),
              ("alerta", "⚠️", "Alertas"), ("acao", "✅", "O que fazer hoje")]
SECOES_SEMANA = [("numeros", "🗓️", "A semana em números"), ("cresceram", "🏆", "Vendedores que cresceram"),
                 ("cairam", "📉", "Vendedores que caíram"), ("produtos", "🔥", "Produtos da semana"),
                 ("estoque", "📦", "Estoque e rupturas"), ("confirmou", "🔁", "O que se confirmou dos alertas"),
                 ("oportunidade", "💡", "Oportunidades para esta semana"), ("acao", "✅", "Plano da semana")]
SECOES_MARCAS = [("mercado", "📊", "Mercado no mês"), ("categorias", "🧭", "Categorias"), ("alta", "🔥", "Marcas em alta"),
                 ("queda", "📉", "Marcas em queda"), ("entradas", "🔁", "Entraram e saíram do top"),
                 ("oportunidade", "💡", "Oportunidades"), ("concorrentes", "📦", "Concorrentes e sinais de compra"),
                 ("acao", "✅", "Plano para o próximo mês")]


def _schema_secoes(secoes):
    item = {"type": "object", "additionalProperties": False, "required": ["texto", "vendedor", "produto", "marca"],
            "properties": {"texto": {"type": "string"}, "vendedor": {"type": "string"}, "produto": {"type": "string"},
                           "marca": {"type": "string"}}}
    sec = {"type": "object", "additionalProperties": False, "required": ["tipo", "itens"],
           "properties": {"tipo": {"type": "string", "enum": [s[0] for s in secoes]},
                          "itens": {"type": "array", "items": item}}}
    return {"type": "object", "additionalProperties": False, "required": ["secoes"],
            "properties": {"secoes": {"type": "array", "items": sec}}}


def _formato_secoes(secoes, detalhe=""):
    return ("FORMATO DA RESPOSTA (JSON, o site monta um card por seção):\n"
            "- 'secoes': uma entrada para cada seção abaixo, nesta ordem, cada uma com 2 a 5 'itens'" + detalhe + ":\n"
            + "\n".join(f"  · {t} = {n}" for t, _, n in secoes) + "\n"
            "- Cada item: 'texto' = uma frase curta com números (R$ 1,2 mi, R$ 350 mil, +12%), sem markdown, sem asteriscos "
            "(pode usar **negrito** só no número principal); 'vendedor' = o nome EXATO do vendedor citado, como aparece nos "
            "dados (ou ''); 'produto' = o nome do produto como aparece nos dados (ou ''); 'marca' = a marca citada (ou '').\n")


def _chave_prod(nomes, produto):
    """Acha a chave do produto citado pela IA entre os produtos que foram nos dados: nome igual, ou um único produto
    cujo nome começa igual (na dúvida, sem link — melhor nenhum link do que o produto errado)."""
    p = re.sub(r"\s+", " ", (produto or "").lower()).strip()
    if len(p) < 8:
        return None
    if p in nomes:
        return nomes[p]
    achados = {k for n, k in nomes.items() if n.startswith(p) or p.startswith(n)}
    return achados.pop() if len(achados) == 1 else None


def _md_secoes(j, secoes, vendedores=(), produtos=None):
    """JSON das seções -> markdown dos cards, com links para vendedor (#/vendedores/X), produto (vprod:) e marca (marca:)."""
    por = {}
    for sc in (j or {}).get("secoes") or []:
        por.setdefault(sc.get("tipo"), []).extend(sc.get("itens") or [])
    vset = {v.upper(): v for v in vendedores}
    nomes = {re.sub(r"\s+", " ", (n or "").lower()).strip(): k for n, k in (produtos or {}).items() if n}
    out = []
    for tid, emo, tit in secoes:
        itens = [i for i in por.get(tid, []) if (i.get("texto") or "").strip()]
        if not itens:
            continue
        out.append(f"## {emo} {tit}")
        for it in itens[:6]:
            txt = re.sub(r"^[\-•*\s]+", "", it["texto"].strip()).replace("\n", " ")
            lk = []
            v = vset.get((it.get("vendedor") or "").strip().upper())
            if v:
                lk.append(f"[{v} ↗](#/vendedores/{urllib.parse.quote(v)})")
            k = _chave_prod(nomes, it.get("produto"))
            if k:
                lk.append(f"[ver produto ↗](vprod:{urllib.parse.quote(k)})")
            elif (it.get("marca") or "").strip() and not v:
                lk.append(f"[{it['marca'].strip()} ↗](marca:{urllib.parse.quote(it['marca'].strip())})")
            out.append("- " + txt + ("  " + " ".join(lk) if lk else ""))
    return "\n".join(out)


def _sem_links(t):
    """Texto de um resumo guardado sem os links dos cards (para voltar a ser lido pela IA)."""
    return re.sub(r"\s*\[[^\]]*↗\]\([^)]*\)", "", t or "")


def _escrever_resumo(pedido, secoes, vendedores=(), produtos=None, max_tokens=2600):
    """Pede o resumo em JSON (formato fixo) e devolve (markdown, json, ia). Sem JSON válido: texto livre."""
    try:
        j, qual = ia.perguntar_estruturado(pedido + "\n" + _formato_secoes(secoes), _schema_secoes(secoes),
                                           "resumo_nubi", max_tokens=max_tokens)
        md = _md_secoes(j, secoes, vendedores, produtos)
        if md.strip():
            return md, j, qual
    except Exception:  # noqa: BLE001 — cai para o texto livre
        pass
    texto, _, qual = ia.perguntar(pedido + "\nFormato: markdown simples, uma seção '## ' para cada item: "
                                  + "; ".join(f"{e} {n}" for _, e, n in secoes) + ".", web=False, max_tokens=max_tokens)
    return texto, None, qual


def gerar_resumo_marcas(repo, cat, rels, chave):
    """Resumo MENSAL e detalhado das marcas (ranking MARCAS do mês fechado), em formato fixo."""
    mes = rels[-1]["mes"][:7]
    try:
        texto, dados, qual = _escrever_resumo(
            "Você é analista de e-commerce de perfumes no Mercado Livre Brasil. Com os dados abaixo (do sistema nubi), "
            f"escreva a análise MENSAL das marcas de {ranking.nome_mes(mes + '-01')} (mês fechado) para o dono de uma loja de "
            "perfumes, em português simples e com números: o mercado no mês, as categorias (quem ganhou e perdeu espaço), "
            "marcas em alta e em queda, quem entrou e saiu do top, oportunidades (marcas subindo em que vale investir e por "
            "quê), concorrentes e sinais de compra, e um plano para o próximo mês (4 ações práticas). "
            "Use só os dados fornecidos, não invente números."
            + _obs_rotina(repo, "resumo_marcas") + "\n\nDADOS:\n" + _dados_resumo(repo, cat, rels, detalhado=True),
            SECOES_MARCAS, max_tokens=3000)
    except Exception as e:  # noqa: BLE001
        raise ErroNuvem(f"A IA não respondeu: {str(e)[:150]}")
    _guardar_resumo(repo, chave, texto, qual, dados)
    return texto, qual


def _dados_resumo(repo, cat, rels, detalhado=False):
    """Os números do mês (ranking, categorias e concorrentes) em texto curto, para a IA escrever o resumo."""
    ids = ",".join(str(r["id"]) for r in rels)
    linhas = unificar_marcas(repo, repo._todos("ranking_linhas", {
        "select": "relatorio_id,posicao,variacao,marca,marca_chave,vendas,unidades,tendencia,catalogo,vendedores,saturacao,ranking_demanda",
        "relatorio_id": f"in.({ids})", "order": "relatorio_id,posicao"}), somar=True)
    por_rel = {r["id"]: [] for r in rels}
    for l in linhas:
        por_rel[l["relatorio_id"]].append(l)
    b = ranking.bi([x["mes"] for x in rels], [por_rel[x["id"]] for x in rels], repo.marcas())
    fm = lambda v: f"R$ {v / 1e6:.1f} mi".replace(".", ",") if v and v >= 1e6 else f"R$ {(v or 0) / 1e3:.0f} mil"
    pc = lambda v: "—" if v is None else f"{v * 100:+.0f}%"
    ult = rels[-1]["mes"][:7]
    out = [f"MERCADO (ranking MARCAS, categoria {ranking.nome_categoria(cat)}): " + "; ".join(
        f"{m['mes'][:7]}: {fm(m['vendas'])}" for m in b["meses"][-4:])]
    z = b.get("resumo") or {}
    out.append(f"Crescimento no período: {pc(z.get('cresc_vendas'))}; entradas no top no período: {z.get('entradas')}; saídas: {z.get('saidas')}.")
    ms = [x for x in b["marcas"] if x.get("posicao")]
    alta = sorted([x for x in ms if x.get("status") in ("Subindo forte", "Crescimento consistente", "Nova")],
                  key=lambda x: -(x.get("nota") or 0))[:15 if detalhado else 8]
    queda = sorted([x for x in ms if x.get("status") in ("Em queda", "Perdeu fôlego")],
                   key=lambda x: -(x.get("vendas_atual") or 0))[:12 if detalhado else 6]
    out.append("MARCAS EM ALTA: " + "; ".join(f"{x['marca']} #{x['posicao']} {fm(x.get('vendas_atual'))} 3m {pc(x.get('cresc_3m'))} ({x['status']})" for x in alta))
    out.append("MARCAS EM QUEDA: " + "; ".join(f"{x['marca']} #{x['posicao']} {fm(x.get('vendas_atual'))} 3m {pc(x.get('cresc_3m'))}" for x in queda))
    ent = [e for e in b.get("entradas", []) if str(e.get("mes"))[:7] == ult][:12 if detalhado else 6]
    sai = [e for e in b.get("saidas", []) if str(e.get("mes"))[:7] == ult][:12 if detalhado else 6]
    out.append("ENTRARAM NO TOP NO MÊS: " + "; ".join(f"{e['marca']} #{e.get('posicao')}" for e in ent))
    out.append("SAÍRAM DO TOP NO MÊS: " + "; ".join(str(e.get("marca")) for e in sai))
    manuais = {r["marca_chave"]: r["categoria"] for r in repo._todos("marca_categorias", {"select": "marca_chave,categoria"})}
    c = categorias.relatorio([x["mes"] for x in rels], [por_rel[x["id"]] for x in rels], manuais)
    out.append("CATEGORIAS (fatia do mercado no mês e variação em pontos): " + "; ".join(
        f"{k} {c['serie'][k]['share'][-1] * 100:.1f}% ({(c['serie'][k]['var_share'] or 0) * 100:+.1f} p.p.)"
        for k in c["categorias"] if c["serie"][k]["vendas"][-1]))
    if detalhado:
        for k in c["categorias"]:
            top = [m for m in c["marcas"] if m["categoria"] == k and m["ultimo"]][:5]
            if top:
                out.append(f"  {k}, maiores: " + "; ".join(f"{m['marca']} {fm(m['ultimo'])} ({pc(m['var_mes'])} no mês)" for m in top))
    try:
        al = rota_vendedores(repo, "GET", "vend_alertas", {}, b"")
        top = [p for p in al["produtos"] if p["sem_estoque"] > 0][:8]
        out.append(f"CONCORRENTES MONITORADOS ({al['vendedores']} vendedores). Produtos que vendiam bem e estão sem estoque: " + "; ".join(
            f"{p['produto'][:50]} ({p['marca']}): {', '.join(a['vendedor'] for a in p['alertas'][:3])} sem estoque, "
            f"ainda vendem {len(p['ainda_vendem'])}, {fm(p['perda_dia'])}/dia parado" for p in top))
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(out)


def _fotos_mes(repo, mes):
    return repo._todos("vend_produto_dia", {"select": "vendedor,chave,dias", "mes": repo._eq(mes + "-01"),
                                            "order": "vendedor,chave"})


def _comparativo(repo, fotos=None):
    """
    Mês atual até o último dia coletado x MESMO PERÍODO do mês anterior (ex.: 01/09–22/09 x 01/08–22/08), por vendedor
    e por produto. O mês anterior vem da foto do mesmo dia (o coletor baixa esse período todo dia); sem essa foto,
    usa a proporção do mês fechado (marcado como estimado).
    """
    rels = _vend_rels(repo)
    if not rels:
        return {"tem": False}
    mes = max(r["mes"] for r in rels)[:7]
    fotos = fotos if fotos is not None else _fotos_mes(repo, mes)
    datas = sorted({d for f in fotos for d in f["dias"]})
    if not datas:
        return {"tem": False, "mes": mes}
    d1 = datas[-1]
    dia = int(d1[8:10])
    ant = (date.fromisoformat(mes + "-01") - timedelta(days=1)).strftime("%Y-%m")
    dias_ant = vend_bi.dias_do_mes(ant)
    d_ant = f"{ant}-{min(dia, dias_ant):02d}"
    f_ant = _fotos_mes(repo, ant)
    vend, prod = {}, {}
    for f in fotos:
        a = f["dias"].get(d1)
        if not a:
            continue
        x = vend.setdefault(f["vendedor"], {"vendedor": f["vendedor"], "v": 0.0, "u": 0, "produtos": 0,
                                            "v_ant": 0.0, "u_ant": 0, "exato": False, "fim_ant": 0.0})
        x["v"] += float(a.get("v") or 0)
        x["u"] += int(a.get("u") or 0)
        x["produtos"] += 1
        p = prod.setdefault((f["vendedor"], f["chave"]), {"u": 0, "v": 0.0, "u_ant": 0, "v_ant": 0.0})
        p["u"], p["v"] = int(a.get("u") or 0), float(a.get("v") or 0)
    for f in f_ant:
        x = vend.get(f["vendedor"])
        if not x:
            continue
        b = f["dias"].get(d_ant)
        if b:
            x["exato"] = True
            x["v_ant"] += float(b.get("v") or 0)
            x["u_ant"] += int(b.get("u") or 0)
            p = prod.setdefault((f["vendedor"], f["chave"]), {"u": 0, "v": 0.0, "u_ant": 0, "v_ant": 0.0})
            p["u_ant"], p["v_ant"] = int(b.get("u") or 0), float(b.get("v") or 0)
        if f["dias"]:
            fim = f["dias"].get(max(f["dias"])) or {}
            x["fim_ant"] += float(fim.get("v") or 0)
            x.setdefault("fim_ant_u", 0)
            x["fim_ant_u"] += int(fim.get("u") or 0)
    for x in vend.values():
        if not x["exato"]:                         # sem a foto do mesmo dia: proporção do mês fechado
            x["v_ant"] = x["fim_ant"] * min(dia, dias_ant) / dias_ant
            x["u_ant"] = round(x.get("fim_ant_u", 0) * min(dia, dias_ant) / dias_ant)
        x["var"] = (x["v"] / x["v_ant"] - 1) if x["v_ant"] else None
    # produtos que mais ganharam e perderam vendas (só com foto exata do mês anterior)
    por_chave = {}
    grp = _mapa_grupos(repo)
    for (v, k), p in prod.items():
        k = grp.get(k, k)
        if not vend.get(v, {}).get("exato"):
            continue
        c = por_chave.setdefault(k, {"chave": k, "u": 0, "u_ant": 0, "v": 0.0, "v_ant": 0.0, "vendedores": set()})
        c["u"] += p["u"]; c["u_ant"] += p["u_ant"]; c["v"] += p["v"]; c["v_ant"] += p["v_ant"]
        if p["u"]:
            c["vendedores"].add(v)
    lista = [dict(c, vendedores=len(c["vendedores"]), dif=c["v"] - c["v_ant"]) for c in por_chave.values()]
    ganhos = sorted([c for c in lista if c["dif"] > 0], key=lambda c: -c["dif"])[:10]
    perdas = sorted([c for c in lista if c["dif"] < 0], key=lambda c: c["dif"])[:10]
    gt = [c["chave"] for c in ganhos + perdas if not c["chave"].startswith("T:")]
    nomes = {}
    if gt:
        ids = ",".join(str(r["id"]) for r in rels if r["mes"][:7] in (mes, ant))
        for r in repo._todos("vend_anuncios", {"select": "gtin,titulo,marca,unidades", "relatorio_id": f"in.({ids})",
                                               "gtin": f"in.({','.join(gt)})", "order": "unidades.desc"}):
            nomes.setdefault(r["gtin"], {"produto": r["titulo"], "marca": r["marca"]})
    for c in ganhos + perdas:
        n = nomes.get(c["chave"]) or {"produto": c["chave"].replace("T:", ""), "marca": ""}
        c.update(n)
    vs = sorted(vend.values(), key=lambda x: -x["v"])
    tot = {"v": sum(x["v"] for x in vs), "v_ant": sum(x["v_ant"] for x in vs), "u": sum(x["u"] for x in vs),
           "u_ant": sum(x["u_ant"] for x in vs)}
    tot["var"] = (tot["v"] / tot["v_ant"] - 1) if tot["v_ant"] else None
    return {"tem": True, "mes": mes, "mes_ant": ant, "ate": d1, "ate_ant": d_ant, "dia": dia,
            "exatos": sum(1 for x in vs if x["exato"]), "vendedores": vs, "total": tot, "ganhos": ganhos, "perdas": perdas}


def _fm(v):
    v = v or 0
    if abs(v) >= 1e6:
        return f"R$ {v / 1e6:.1f} mi".replace(".", ",")
    if abs(v) >= 1e3:
        return f"R$ {v / 1e3:.1f} mil".replace(".", ",")
    return f"R$ {v:.0f}"


def _ddmm(d):
    return f"{d[8:10]}/{d[5:7]}"


def _vendas_dias(repo, desde, ate):
    """Linhas de vend_vendas_dia entre desde e ate (inclusive)."""
    return [r for r in repo._todos("vend_vendas_dia", {"select": "vendedor,data,v,u,itens", "data": f"gte.{desde}",
                                                        "order": "data,vendedor"}) if str(r["data"])[:10] <= ate]


def _mapa_grupos(repo):
    """{chave: grupo} dos produtos iguais: títulos juntados pela IA ('ia') e GTINs que o Bruno juntou na conferência
    ('manual', 26/09). Resolve a corrente (título → GTIN que foi juntado a outro GTIN → GTIN final)."""
    try:
        m = {r["chave"]: r["grupo"] for r in repo._todos("produto_grupos", {"select": "chave,grupo", "metodo": "in.(ia,manual)"})}
    except ErroNuvem:
        return {}
    for k in list(m):
        g, vistos = m[k], {k}
        while g in m and g not in vistos:
            vistos.add(g)
            g = m[g]
        m[k] = g
    return m


def conferir_gtins(repo, por):
    """GTINs diferentes com o mesmo nome de perfume: nunca junta sozinho; grava os pares 'gtin_conferir' para o Bruno
    decidir em Ajustes → Produtos iguais (Juntar = 'manual'; Não é o mesmo = 'gtin_nao', não pergunta de novo)."""
    rs = repo._todos("produto_grupos", {"select": "chave,metodo"})
    decididos = {r["chave"] for r in rs if r["metodo"] in ("gtin_nao", "manual", "separado")}
    gt = sorted((x for x in por.values() if not x["chave"].startswith("T:") and x["marca"]), key=lambda x: -x["v"])[:1500]
    if len(gt) < 2:
        return 0
    vet = ia.embeddings([produtos_iguais.texto_embedding(x) for x in gt])
    pares = [(a, b, sim) for a, b, sim in produtos_iguais.gtins_parecidos(gt, vet)
             if f"par:{a}|{b}" not in decididos and b not in decididos]
    nomes = {x["chave"]: x for x in gt}
    repo._req("DELETE", "produto_grupos", {"metodo": "eq.gtin_conferir"})
    agora_ = datetime.now(timezone.utc).isoformat()
    regs = [{"chave": f"par:{a}|{b}", "grupo": a, "titulo": nomes[b]["titulo"][:200], "grupo_titulo": nomes[a]["titulo"][:200],
             "marca": nomes[a]["marca"], "similaridade": round(sim, 4), "metodo": "gtin_conferir", "atualizado_em": agora_}
            for a, b, sim in pares]
    if regs:
        repo._req("POST", "produto_grupos", corpo=regs, prefer="resolution=merge-duplicates,return=minimal")
    return len(regs)


def agrupar_produtos(repo):
    """Tarefa de rotina: junta os títulos sem GTIN que são o mesmo perfume (embeddings + regras) em produto_grupos."""
    rels = _vend_rels(repo)
    if not rels:
        return "nenhum vendedor importado"
    meses = sorted({r["mes"][:7] for r in rels})[-2:]
    ids = [r["id"] for r in rels if r["mes"][:7] in meses]
    por = {}
    for l in _prod_mes(repo, ids):
        x = por.setdefault(l["chave"], {"chave": l["chave"], "titulo": "", "marca": l.get("marca") or "", "v": 0.0, "_v": -1})
        v = float(l.get("vendas") or 0)
        x["v"] += v
        if v > x["_v"]:
            x["titulo"], x["marca"], x["_v"] = l.get("titulo") or "", l.get("marca") or x["marca"], v
    itens = sorted(por.values(), key=lambda x: -x["v"])
    sem = [x for x in itens if x["chave"].startswith("T:")]
    if not sem:
        return "nenhum produto sem GTIN"
    marcas_sem = {x["marca"].upper() for x in sem}
    itens = [x for x in itens if x["marca"].upper() in marcas_sem][:4000]
    bloqueados = {r["chave"] for r in repo._todos("produto_grupos", {"select": "chave", "metodo": "eq.separado"})}
    vet = ia.embeddings([produtos_iguais.texto_embedding(x) for x in itens])
    res = produtos_iguais.agrupar(itens, vet, bloqueados)
    nomes = {x["chave"]: x for x in itens}
    repo._req("DELETE", "produto_grupos", {"metodo": "eq.ia"})
    regs = [{"chave": k, "grupo": g, "titulo": nomes[k]["titulo"][:200], "marca": nomes[k]["marca"],
             "grupo_titulo": nomes[g]["titulo"][:200], "similaridade": round(sim, 4), "metodo": "ia",
             "atualizado_em": datetime.now(timezone.utc).isoformat()} for k, (g, sim) in res.items()]
    for i in range(0, len(regs), 500):
        repo._req("POST", "produto_grupos", corpo=regs[i:i + 500], prefer="resolution=merge-duplicates,return=minimal")
    try:
        n_gtin = conferir_gtins(repo, por)
    except Exception as e:  # noqa: BLE001
        n_gtin = f"erro na conferência de GTINs: {str(e)[:120]}"
    extra = (f"; {n_gtin} par(es) de GTINs diferentes com o mesmo nome para o Bruno conferir" if isinstance(n_gtin, int)
             else f"; {n_gtin}") if n_gtin else ""
    return f"{len(regs)} título(s) juntado(s) a outro do mesmo produto ({len(sem)} produtos sem GTIN conferidos){extra}"


def _painel_dia(repo, d=None):
    """
    Venda isolada do último dia liberado (export de 1 dia de cada vendedor): quem mais vendeu, quem mais caiu e os
    produtos em alta e em queda, contra a média dos 7 dias anteriores (sem esses dias: o ritmo do mês).
    """
    if not d:
        ult = repo._req("GET", "vend_vendas_dia", {"select": "data", "order": "data.desc", "limit": 1}) or []
        if not ult:
            return {"tem": False}
        d = str(ult[0]["data"])[:10]
    desde = (date.fromisoformat(d) - timedelta(days=7)).isoformat()
    rows = _vendas_dias(repo, desde, d)
    grp = _mapa_grupos(repo)
    for r in rows:
        r["data"] = str(r["data"])[:10]
        for it in r["itens"] or []:
            it["k"] = grp.get(it["k"], it["k"])
    ant = sorted({r["data"] for r in rows if r["data"] < d})
    n = len(ant)
    base, pbase, hoje, prod = {}, {}, {}, {}
    # dia sem linha de um vendedor = coleta que falhou (dia sem venda vem como linha zerada): não conta como venda zero
    hoje_v = {r["vendedor"] for r in rows if r["data"] == d}
    for r in rows:
        if r["data"] < d:
            b = base.setdefault(r["vendedor"], [0.0, 0, 0])
            b[0] += float(r["v"] or 0)
            b[1] += int(r["u"] or 0)
            b[2] += 1                                      # dias com dado desse vendedor
            if r["vendedor"] not in hoje_v:
                continue                                   # produtos de quem não tem o dia não entram nas quedas
            for it in r["itens"] or []:
                pb = pbase.setdefault(it["k"], {"v": 0.0, "u": 0, "t": it.get("t"), "m": it.get("m")})
                pb["v"] += float(it.get("v") or 0)
                pb["u"] += int(it.get("u") or 0)
        else:
            hoje[r["vendedor"]] = r
            for it in r["itens"] or []:
                p = prod.setdefault(it["k"], {"chave": it["k"], "produto": it.get("t") or it["k"], "marca": it.get("m") or "",
                                              "v": 0.0, "u": 0, "vendedores": []})
                p["v"] += float(it.get("v") or 0)
                p["u"] += int(it.get("u") or 0)
                p["vendedores"].append(r["vendedor"])
    if not hoje:
        return {"tem": False}
    # o mesmo dia do mês anterior (22/09 -> 22/08), baixado isolado de cada vendedor
    dd = date.fromisoformat(d)
    ult_ant = date(dd.year, dd.month, 1) - timedelta(days=1)
    d_mes = ult_ant.replace(day=dd.day).isoformat() if dd.day <= ult_ant.day else None
    vm, pm = {}, {}
    for r in (_vendas_dias(repo, d_mes, d_mes) if d_mes else []):
        vm[r["vendedor"]] = float(r["v"] or 0)
        for it in r["itens"] or []:
            k = grp.get(it["k"], it["k"])
            pm[k] = pm.get(k, 0.0) + float(it.get("v") or 0)
    ritmo = {}
    if not n:                                            # sem dias anteriores: ritmo do mês (fotos acumuladas)
        try:
            c = _comparativo(repo)
            if c.get("tem") and c.get("dia"):
                ritmo = {x["vendedor"]: x["v"] / c["dia"] for x in c["vendedores"]}
        except Exception:  # noqa: BLE001
            ritmo = {}
    vs = []
    faltam = sorted(set(base) - set(hoje))                 # sem o arquivo do dia (coleta pendente)
    for v in sorted(hoje):
        r = hoje.get(v)
        med = (base[v][0] / base[v][2]) if n and v in base and base[v][2] else ritmo.get(v)
        x = {"vendedor": v, "v": float(r["v"] or 0) if r else 0.0, "u": int(r["u"] or 0) if r else 0,
             "itens": len(r["itens"] or []) if r else 0, "media": med, "sem_dados": not r,
             "top": [{"produto": it.get("t"), "marca": it.get("m"), "u": it.get("u"), "v": it.get("v")}
                     for it in (r["itens"] or [])[:3]] if r else []}
        x["dif"] = (x["v"] - med) if med is not None else None
        x["var"] = (x["v"] / med - 1) if med else None
        x["v_mes"] = vm.get(v) if vm else None
        x["var_mes"] = (x["v"] / vm[v] - 1) if vm.get(v) else None
        vs.append(x)
    ps = []
    for k, p in prod.items():
        med = pbase[k]["v"] / n if n and k in pbase else None
        ps.append(dict(p, vendedores=len(set(p["vendedores"])), media=med,
                       dif=(p["v"] - med) if med is not None else None, var=(p["v"] / med - 1) if med else None,
                       v_mes=pm.get(k) if pm else None, var_mes=(p["v"] / pm[k] - 1) if pm.get(k) else None))
    queda = []
    if n:
        for k, pb in pbase.items():
            med = pb["v"] / n
            hj = prod.get(k, {}).get("v", 0.0)
            if med >= 300 and hj < med * 0.85:                # caiu pelo menos 15%
                queda.append({"chave": k, "produto": pb["t"] or k, "marca": pb["m"] or "", "v": hj, "media": med,
                              "dif": hj - med, "var": hj / med - 1})
    tot = {"v": sum(x["v"] for x in vs), "u": sum(x["u"] for x in vs)}
    meds = [x["media"] for x in vs if x["media"] is not None]
    tot["media"] = sum(meds) if meds else None
    tot["var"] = (tot["v"] / tot["media"] - 1) if tot["media"] else None
    tot["v_mes"] = sum(vm.values()) if vm else None
    tot["var_mes"] = (tot["v"] / tot["v_mes"] - 1) if tot["v_mes"] else None
    if vm:                                                 # mesmo dia do mês anterior só dos vendedores que têm o dia
        tot["v_mes"] = sum(vm.get(x["vendedor"], 0.0) for x in vs)
        tot["var_mes"] = (tot["v"] / tot["v_mes"] - 1) if tot["v_mes"] else None
    return {"tem": True, "data": d, "data_mes": d_mes if vm else None, "base": "7 dias" if n else ("ritmo do mês" if ritmo else None), "dias_base": n,
            "sem_coleta": faltam,
            "total": tot, "vendedores": sorted(vs, key=lambda x: -x["v"]),
            "mais_venderam": sorted([x for x in vs if x["v"] > 0], key=lambda x: -x["v"])[:8],
            "mais_cairam": sorted([x for x in vs if (x["dif"] or 0) < 0], key=lambda x: x["dif"])[:8],
            "produtos_alta": sorted(ps, key=lambda p: -p["v"])[:10],
            "produtos_queda": sorted(queda, key=lambda p: p["dif"])[:10]}


def _obs_rotina(repo, rid):
    """Observação que o dono escreveu na tarefa de rotina (vira instrução no prompt da IA)."""
    try:
        r = repo._req("GET", "rotinas", {"select": "observacao", "id": repo._eq(rid)}) or []
    except ErroNuvem:
        return ""
    o = ((r[0].get("observacao") or "") if r else "").strip()
    return f"\n\nINSTRUÇÕES DO DONO PARA ESTA TAREFA (siga à risca):\n{o[:2000]}" if o else ""


def _dados_resumo_dia(repo):
    """
    O que aconteceu no último dia liberado (dados de 2 dias atrás) com os vendedores monitorados: a venda isolada do
    dia de cada vendedor com os itens vendidos (export de 1 dia), o mesmo período x mês anterior e o estoque.
    Devolve (data, texto, painel) ou (None, motivo, None).
    """
    rels = _vend_rels(repo)
    if not rels:
        return None, "nenhum vendedor importado", None
    mes = max(r["mes"] for r in rels)[:7]
    fotos = _fotos_mes(repo, mes)
    datas = sorted({d for f in fotos for d in f["dias"]})
    pnl = _painel_dia(repo)
    d1 = max([x for x in (datas[-1] if datas else None, pnl.get("data")) if x], default=None)
    if not d1:
        return None, "ainda sem dados diários do mês", None
    if pnl.get("tem") and pnl["data"] != d1:
        pnl = _painel_dia(repo, d1) if pnl["data"] > d1 else {"tem": False}
    linhas = [f"DADOS ATÉ {_ddmm(d1)} (o Nubimetrics libera com 2 dias de atraso; hoje o dono lê sobre {_ddmm(d1)})."]
    if pnl.get("tem"):
        t = pnl["total"]
        base = f"média dos {pnl['dias_base']} dias anteriores" if pnl["dias_base"] else "ritmo diário do mês"
        linhas.append(f"VENDA ISOLADA DO DIA {_ddmm(d1)} (exata: export só desse dia de cada vendedor). Comparação com a {base}.")
        sem = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
        dsem = lambda x: sem[date.fromisoformat(x).weekday()]
        dm_ = pnl.get("data_mes")
        if dm_:
            linhas.append(f"Também há o MESMO DIA DO MÊS ANTERIOR ({_ddmm(dm_)}, {dsem(dm_)}) baixado isolado; o dia analisado é "
                          f"{dsem(d1)}. Dias da semana diferentes vendem diferente: leve isso em conta.")
        linhas.append(f"TOTAL DO DIA: {_fm(t['v'])}, {t['u']} un." + (f" x {_fm(t['media'])} de média ({t['var'] * 100:+.0f}%)"
                                                                         if t["var"] is not None else "")
                      + (f"; x {_fm(t['v_mes'])} em {_ddmm(dm_)} ({t['var_mes'] * 100:+.0f}%)" if t.get("var_mes") is not None else ""))
        for x in pnl["vendedores"]:
            cab = (f"- {x['vendedor']}: " + ("NÃO VENDEU NADA NO DIA" if not x["itens"] else f"{_fm(x['v'])}, {x['u']} un., {x['itens']} produto(s)")
                   + (f"; média {_fm(x['media'])} ({x['var'] * 100:+.0f}%)" if x["var"] is not None else "")
                   + (f"; em {_ddmm(dm_)}: {_fm(x['v_mes'])} ({x['var_mes'] * 100:+.0f}%)" if x.get("var_mes") is not None else ""))
            linhas.append(cab)
        if pnl.get("sem_coleta"):
            linhas.append("AINDA SEM O ARQUIVO DO DIA (a coleta falhou e vai tentar de novo; NÃO é venda zero, NÃO comente "
                          "como queda, só avise que faltam): " + ", ".join(pnl["sem_coleta"]) + ". Os totais do dia são só dos "
                          "outros vendedores.")
        # itens vendidos de cada vendedor no dia (os 12 maiores)
        hoje = {r["vendedor"]: r for r in _vendas_dias(repo, d1, d1)}
        linhas.append("ITENS VENDIDOS NO DIA POR VENDEDOR (maiores primeiro):")
        for v, r in sorted(hoje.items(), key=lambda kv: -float(kv[1]["v"] or 0)):
            its = r["itens"] or []
            linhas.append(f"  {v}: " + "; ".join(f"{(it.get('t') or '')[:48]} ({it.get('m')}) {it.get('u')} un. {_fm(it.get('v'))}"
                                                  + (" [anúncios pausados]" if not it.get("a") else "") for it in its[:12])
                          + (f"; e mais {len(its) - 12} produto(s)" if len(its) > 12 else ""))
        linhas.append("PRODUTOS QUE MAIS VENDERAM NO DIA (todos os vendedores): " + "; ".join(
            f"{p['produto'][:50]} ({p['marca']}): {p['u']} un., {_fm(p['v'])}, {p['vendedores']} vendedor(es)"
            + (f", {p['var'] * 100:+.0f}% vs média" if p["var"] is not None else ", novo no período")
            + (f", {p['var_mes'] * 100:+.0f}% vs {_ddmm(pnl['data_mes'])}" if p.get("var_mes") is not None else "") for p in pnl["produtos_alta"]))
        if pnl["produtos_queda"]:
            linhas.append("PRODUTOS QUE MAIS CAÍRAM NO DIA (vs média): " + "; ".join(
                f"{p['produto'][:50]} ({p['marca']}): {_fm(p['v'])} x média {_fm(p['media'])}" for p in pnl["produtos_queda"]))
    else:
        linhas.append("ATENÇÃO: ainda não há a venda isolada do dia (o coletor começa a baixar o export de 1 dia por "
                      "vendedor na próxima coleta). Fale do acumulado do mês e do mesmo período; NÃO diga que as vendas do dia foram zero.")
    cmp_ = _comparativo(repo, fotos)
    if cmp_.get("tem"):
        t = cmp_["total"]
        linhas.append(f"MESMO PERÍODO ({ranking.nome_mes(cmp_['mes'] + '-01')} x {ranking.nome_mes(cmp_['mes_ant'] + '-01')}; "
                      f"01 a {_ddmm(cmp_['ate'])} x 01 a {_ddmm(cmp_['ate_ant'])}): {_fm(t['v'])} x {_fm(t['v_ant'])}"
                      + (f" ({t['var'] * 100:+.0f}%)" if t["var"] is not None else "")
                      + ("" if cmp_["exatos"] == len(cmp_["vendedores"]) else
                         f" — {len(cmp_['vendedores']) - cmp_['exatos']} vendedor(es) com o mês anterior ESTIMADO pela proporção do mês"))
        for x in cmp_["vendedores"]:
            linhas.append(f"  · {x['vendedor']}: {_fm(x['v'])} x {_fm(x['v_ant'])}"
                          + (f" ({x['var'] * 100:+.0f}%)" if x["var"] is not None else "") + ("" if x["exato"] else " [estimado]"))
        if cmp_["ganhos"]:
            linhas.append("PRODUTOS QUE MAIS GANHARAM VENDAS no mesmo período: " + "; ".join(
                f"{c['produto'][:50]} ({c['marca']}): {_fm(c['v'])} x {_fm(c['v_ant'])}" for c in cmp_["ganhos"][:8]))
        if cmp_["perdas"]:
            linhas.append("PRODUTOS QUE MAIS PERDERAM VENDAS no mesmo período: " + "; ".join(
                f"{c['produto'][:50]} ({c['marca']}): {_fm(c['v'])} x {_fm(c['v_ant'])}" for c in cmp_["perdas"][:8]))
    try:
        al = rota_vendedores(repo, "GET", "vend_alertas", {}, b"")
        top = [p for p in al["produtos"] if p["sem_estoque"] > 0][:6]
        linhas.append("ALERTAS DE ESTOQUE EM ABERTO (maiores): " + "; ".join(
            f"{p['produto'][:50]} ({p['marca']}): sem estoque em {', '.join(a['vendedor'] for a in p['alertas'][:3])}; "
            f"ainda vendem {len(p['ainda_vendem'])}; {_fm(p['perda_dia'])}/dia parado" for p in top))
    except Exception:  # noqa: BLE001
        pass
    return d1, "\n".join(linhas), pnl


def tela_inicio(repo):
    """Tudo de um pouco para a tela Início: o dia de vendas, contagens, resumo da IA e a operação."""
    def seguro(f, padrao=None):
        try:
            return f()
        except Exception:  # noqa: BLE001 — um bloco com problema não derruba a tela inteira
            return padrao
    out = {}
    pnl = seguro(lambda: _painel_dia(repo), {"tem": False}) or {"tem": False}
    out["dia"] = {k: pnl.get(k) for k in ("tem", "data", "data_mes", "base", "sem_coleta", "total")} if pnl.get("tem") else {"tem": False}
    if pnl.get("tem"):
        out["dia"]["top"] = [{k: v.get(k) for k in ("vendedor", "v", "dif")} for v in pnl.get("mais_venderam", [])[:3]]
        out["dia"]["queda"] = [{k: v.get(k) for k in ("vendedor", "v", "dif")} for v in pnl.get("mais_cairam", [])[:3]]
        out["dia"]["produto"] = [{"t": p.get("produto"), "m": p.get("marca"), "v": p.get("v"), "u": p.get("u"), "dif": p.get("dif")} for p in pnl.get("produtos_alta", [])[:3]]
        # cobertura da coleta do dia (card #68, widget Vendas dos concorrentes): quantos vendedores pendentes x total
        out["dia"]["pendentes"] = len(pnl.get("sem_coleta") or [])
        out["dia"]["total_vendedores"] = out["dia"]["pendentes"] + len(pnl.get("vendedores") or [])
    rs = seguro(lambda: repo._req("GET", "ia_resumos", {"select": "chave,texto,dados,criado_em", "chave": "like.vendedores|*",
                                                        "order": "chave.desc", "limit": 1}), []) or []
    out["resumo"] = {"data": rs[0]["chave"].split("|")[1], "texto": (rs[0].get("texto") or "")[:1500]} if rs else None
    rels = seguro(lambda: _relatorios(repo), []) or []
    ult_rel = rels[-1] if rels else None
    n_marcas = seguro(lambda: len(repo._todos("ranking_linhas", {"select": "marca", "relatorio_id": repo._eq(ult_rel["id"])})), 0) if ult_rel else 0
    desde30 = (_agora_br().date() - timedelta(days=30)).isoformat()
    vend = seguro(lambda: {r["vendedor"] for r in repo._todos("vend_vendas_dia", {"select": "vendedor", "data": f"gte.{desde30}"})}, set()) or set()
    out["contagens"] = {
        "marcas_ranking": n_marcas, "mes_ranking": (ult_rel or {}).get("mes"),
        "marcas_explorador": seguro(lambda: len(repo._todos("marcas_config", {"select": "marca"})), 0),
        "vendedores": len(vend),
        "produtos_iguais": seguro(lambda: len(repo._todos("produto_grupos", {"select": "chave"})), 0),
    }
    tar = seguro(lambda: repo._todos("reuniao_tarefas", {"select": "status"}), []) or []
    out["tarefas"] = {k: sum(1 for t in tar if t["status"] == k) for k in ("proposta", "aprovada", "em_desenvolvimento", "feita")}
    det = seguro(lambda: repo._todos("reuniao_tarefas", {"select": "id,titulo,status,responsavel,aguardando,atualizado_em",
                                                         "status": "in.(em_desenvolvimento,feita)", "order": "atualizado_em.desc"}), []) or []
    limite = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    out["andamento"] = [t for t in det if t["status"] in ("em_desenvolvimento", "em_teste")][:5]
    out["feitas_recentes"] = [t for t in det if t["status"] == "feita" and str(t.get("atualizado_em") or "") > limite][:5]
    out["aguardando_voce"] = seguro(lambda: [t for t in repo._todos("reuniao_tarefas", {"select": "id,titulo,aguardando",
                                                                                          "aguardando": "not.is.null"})
                                             if (t.get("aguardando") or "").strip()], []) or []
    hoje = _agora_br().date()
    usos = seguro(lambda: repo._todos("agentes_uso", {"select": "inicio,custo_usd,fim",
                                                      "inicio": f"gte.{hoje.replace(day=1).isoformat()}"}), []) or []
    out["ia"] = {"custo_hoje": round(sum(float(u.get("custo_usd") or 0) for u in usos if _br(u["inicio"]).date() == hoje), 4),
                 "custo_mes": round(sum(float(u.get("custo_usd") or 0) for u in usos), 4),
                 "chamadas_hoje": sum(1 for u in usos if _br(u["inicio"]).date() == hoje)}
    col = seguro(lambda: repo._req("GET", "coletor_execucoes", {"select": "iniciado_em,terminado_em,ok,em_andamento,mensagem,tarefa",
                                                                "tarefa": "neq.estoque", "order": "id.desc", "limit": 1}), []) or []
    est = seguro(lambda: repo._req("GET", "estoque_atualizacoes", {"select": "id,criado_em,skus,unidades,valor,zerados,resumo,analise_por",
                                                                   "order": "id.desc", "limit": 1}), []) or []
    out["estoque"] = est[0] if est else None
    if out["estoque"]:
        # "baixo" não é uma coluna gravada em estoque_atualizacoes (resumo é só texto): mesma fórmula de
        # estoque.totais() (atual > 0 e <= estoque_min), sem criar limite novo (card #68 widget Estoque).
        # None (não [] ou 0) se a consulta falhar: sem confundir "consulta falhou" com "zero baixo de verdade".
        itens_est = seguro(lambda: repo._todos("estoque_itens", {"select": "atual,estoque_min",
                                                                  "atualizacao_id": repo._eq(out["estoque"]["id"])}))
        out["estoque"]["baixo"] = (sum(1 for it in itens_est if (it.get("atual") or 0) > 0 and it.get("estoque_min")
                                        and it["atual"] <= it["estoque_min"]) if itens_est is not None else None)
    out["coleta"] = col[0] if col else None
    if out["coleta"]:
        out["coleta"]["mensagem"] = (out["coleta"].get("mensagem") or "")[:200]
    # análise diária do DeepSeek (rotina analise_foco): onde focar, cruzando os concorrentes com o meu estoque
    fo = seguro(lambda: repo._req("GET", "ia_resumos", {"select": "chave,texto,ia,criado_em,dados", "chave": "like.foco|*",
                                                        "order": "chave.desc", "limit": 1}), []) or []
    sem = seguro(lambda: repo._req("GET", "ia_resumos", {"select": "chave,texto,criado_em", "chave": "like.foco_semana|*",
                                                         "order": "chave.desc", "limit": 1}), []) or []
    if sem and (_agora_br().date() - date.fromisoformat(sem[0]["chave"].split("|")[1])).days <= 7:
        out["plano_semana"] = {"texto": sem[0]["texto"], "criado_em": sem[0]["criado_em"], "data": sem[0]["chave"].split("|")[1]}
    if fo:
        dd = fo[0].get("dados") or {}
        out["foco"] = {"texto": fo[0]["texto"], "ia": fo[0].get("ia"), "criado_em": fo[0]["criado_em"], "mes": dd.get("mes"),
                       "vendedores": dd.get("vendedores"), "produtos": (dd.get("produtos") or [])[:8]}
    return out


def inicio_decisoes(repo):
    """Painel 'Decisões de hoje' da Início (card #24): risco de dado, oportunidade de preço e execução.
    Cada bloco vem com fonte e referência; falha na consulta vira None ('sem dados'), nunca zero inventado."""
    def seguro(f, padrao=None):
        try:
            return f()
        except Exception:  # noqa: BLE001 — um bloco com problema não derruba o painel inteiro
            return padrao
    hoje = _agora_br().date()

    pnl = seguro(lambda: _painel_dia(repo), {"tem": False}) or {"tem": False}
    pendentes = None
    if pnl.get("tem"):
        itens = [{"vendedor": v, "dia": pnl.get("data")} for v in (pnl.get("sem_coleta") or [])]
        pendentes = {"total": len(itens), "itens": itens[:10], "fonte": "Central > Coletor", "referencia": pnl.get("data")}

    au = seguro(lambda: (repo._req("GET", "auditorias", {"select": "data,conferencias", "order": "data.desc", "limit": 1}) or [None])[0])
    alertas = None
    if au:
        ach = [a for a in (au.get("conferencias") or []) if a.get("nivel") in ("erro", "alerta")]
        alertas = {"total": len(ach), "itens": [{"titulo": a.get("titulo"), "area": a.get("area"), "nivel": a.get("nivel")}
                                                for a in ach[:10]],
                   "fonte": "Central > Auditoria", "referencia": au.get("data")}

    # Oportunidade de preço: a especificação do Astra pede confirmar com o Bruno (definição de "preço atual",
    # cobertura da média, regra do top 5, produtos agrupados) antes de implementar — até lá, "sem dados".
    preco = {"sem_dados": True,
             "motivo": "Aguardando o Bruno definir preço atual, cobertura da média, regra do top 5 e produtos agrupados (card #24)."}

    propostas = seguro(lambda: repo._todos("reuniao_tarefas", {"select": "id,titulo,responsavel", "status": "eq.proposta"}))
    aguardando_aprovacao = None if propostas is None else {
        "total": len(propostas), "itens": [{"id": t["id"], "titulo": t["titulo"], "responsavel": t.get("responsavel")}
                                            for t in propostas[:10]],
        "fonte": "Central > Desenvolvimento", "referencia": hoje.isoformat()}

    usos = seguro(lambda: repo._todos("agentes_uso", {"select": "inicio,custo_usd", "inicio": f"gte.{hoje.replace(day=1).isoformat()}"}))
    custo_hoje = None if usos is None else round(sum(float(u.get("custo_usd") or 0) for u in usos if _br(u["inicio"]).date() == hoje), 4)
    # ainda não existe teto de custo registrado no banco (card #10 pendente): nunca deduzir "travada" pelo valor
    # gasto sozinho (regra do plano técnico do card #24) — a lista fica vazia até o card #10 gravar o estado.
    travadas_por_custo = {"total": 0, "itens": [], "custo_hoje": custo_hoje, "fonte": "agentes_uso (log #17)",
                          "referencia": hoje.isoformat()}

    return {"gerado_em": datetime.now(timezone.utc).isoformat(),
            "risco": {"pendentes": pendentes, "alertas": alertas},
            "preco": preco,
            "execucao": {"aguardando_aprovacao": aguardando_aprovacao, "travadas_por_custo": travadas_por_custo}}


# Card #69: dados novos do Início (dólar do dia, datas de vendas, notícias dos marketplaces, análises dos agentes)
URL_DOLAR = "https://economia.awesomeapi.com.br/json/last/USD-BRL"
_DOLAR = {"quando": 0.0, "valor": None}      # cache de 30 min na instância do servidor


def dolar_do_dia():
    """Cotação USD-BRL da AwesomeAPI (grátis, sem chave), com cache de 30 min; None se a API falhar (= 'sem dados')."""
    if _DOLAR["valor"] and time.monotonic() - _DOLAR["quando"] < 30 * 60:
        return _DOLAR["valor"]
    try:
        d = (nubi._get_json(URL_DOLAR) or {}).get("USDBRL") or {}
        v = {"compra": float(d["bid"]), "venda": float(d["ask"]), "variacao": float(d.get("pctChange") or 0),
             "quando": d.get("create_date")}
    except Exception:  # noqa: BLE001 — API fora do ar ou resposta estranha: "sem dados", nunca um número inventado
        return None
    _DOLAR.update(quando=time.monotonic(), valor=v)
    return v


def _nesimo_domingo(ano, mes, n):
    d = date(ano, mes, 1)
    return d + timedelta(days=(6 - d.weekday()) % 7 + 7 * (n - 1))


def _black_friday(ano):
    d = date(ano, 11, 1)
    return d + timedelta(days=(3 - d.weekday()) % 7 + 22)     # 4ª quinta de novembro + 1 dia


DATAS_VENDAS = [
    ("Dia do Consumidor", lambda a: date(a, 3, 15)), ("Dia das Mães", lambda a: _nesimo_domingo(a, 5, 2)),
    ("Dia dos Namorados", lambda a: date(a, 6, 12)), ("Dia dos Pais", lambda a: _nesimo_domingo(a, 8, 2)),
    ("9.9", lambda a: date(a, 9, 9)), ("Dia das Crianças", lambda a: date(a, 10, 12)), ("10.10", lambda a: date(a, 10, 10)),
    ("11.11", lambda a: date(a, 11, 11)), ("Black Friday", _black_friday), ("12.12", lambda a: date(a, 12, 12)),
    ("Natal", lambda a: date(a, 12, 25)),
]


def datas_vendas(hoje=None):
    """Próxima ocorrência de cada data do varejo/marketplaces (já passou este ano = a do ano que vem) e os dias que faltam."""
    hoje = hoje or _agora_br().date()
    out = []
    for nome_, f in DATAS_VENDAS:
        d = f(hoje.year)
        if d < hoje:
            d = f(hoje.year + 1)
        out.append({"nome": nome_, "data": d.isoformat(), "faltam": (d - hoje).days})
    return sorted(out, key=lambda x: x["faltam"])


def gerar_noticias(repo, forcar=False):
    """Rotina 'noticias' (07:00): a IA com busca na web resume até 8 novidades dos marketplaces para quem vende perfumes;
    grava 1 vez por dia em ia_resumos (chave 'noticias|AAAA-MM-DD')."""
    chave = f"noticias|{_agora_br().date().isoformat()}"
    if not forcar and repo._req("GET", "ia_resumos", {"select": "chave", "chave": repo._eq(chave)}):
        return {"chave": chave, "novo": False}
    if not ia.disponivel():
        raise ErroNuvem("Configure uma chave de IA para buscar as notícias.")
    j, links, qual = ia.perguntar_json(
        "Pesquise na web as novidades dos últimos dias que importam para quem vende perfumes no Mercado Livre, Shopee, "
        "Amazon e TikTok Shop no Brasil: mudanças de taxa/comissão, regras, frete, campanhas e datas promocionais. "
        "Traga no máximo 8, só com fonte real (link). Responda SÓ com JSON: "
        '{"noticias": [{"marketplace": "...", "titulo": "...", "resumo": "1 ou 2 frases", "fonte": "https://..."}]}'
        + _obs_rotina(repo, "noticias"), web=True, max_tokens=2500)
    itens = [n for n in (j.get("noticias") or []) if isinstance(n, dict) and n.get("titulo") and n.get("fonte")][:8]
    texto = "\n".join(f"- **{n.get('marketplace') or ''}** {n['titulo']}: {n.get('resumo') or ''} ([fonte]({n['fonte']}))" for n in itens)
    _guardar_resumo(repo, chave, texto or "sem novidades", qual, {"noticias": itens})
    return {"chave": chave, "novo": True, "n": len(itens)}


_PALAVRAS_VAZIAS = {"perfume", "perfumes", "masculino", "feminino", "unissex", "eau", "de", "da", "do", "parfum", "toilette",
                    "edp", "edt", "original", "importado", "ml", "com", "para", "e", "o", "a", "the", "lacrado", "kit", "spray"}


def _tokens_produto(titulo):
    """Palavras que identificam o produto (sem acento, sem as genéricas) + o volume em ml."""
    t = unicodedata.normalize("NFKD", str(titulo or "").lower()).encode("ascii", "ignore").decode()
    vol = re.search(r"(\d{2,4})\s*ml", t)
    pal = {p for p in re.findall(r"[a-z0-9]+", t) if len(p) >= 3 and p not in _PALAVRAS_VAZIAS and not p.isdigit()
           and not re.fullmatch(r"\d+ml", p)}                       # volume não conta como palavra do produto
    return pal, (vol.group(1) if vol else None)


def casar_estoque(titulo, estoque):
    """O item do MEU estoque que é o mesmo produto do concorrente (os SKUs são diferentes: casa pelo título).
    Mesmo volume quando os dois têm; pelo menos 2 palavras em comum e 60% das palavras do concorrente."""
    pal, vol = _tokens_produto(titulo)
    if len(pal) < 2:
        return None
    melhor, nota_m = None, 0.0
    for it in estoque:
        p2, v2 = it["_tok"]
        if vol and v2 and vol != v2:
            continue
        comum = len(pal & p2)
        nota = comum / len(pal)
        if comum >= 2 and nota >= 0.6 and nota > nota_m:
            melhor, nota_m = it, nota
    return melhor


def dados_foco(repo, limite=30):
    """Números da análise diária do DeepSeek (card do Bruno, 25/09), todos calculados aqui — a IA só interpreta:
    produtos que mais vendem nos concorrentes monitorados no mês (R$, unidades, vendedores, preço médio = 'Preço Médio' do
    Nubimetrics) cruzados com o MEU estoque do UpSeller (tenho/zerado/não tenho, custo e margem antes das taxas)."""
    rels = _vend_rels(repo)
    if not rels:
        return None
    mes = max(r["mes"] for r in rels)[:7]
    ult = {}
    for r in rels:
        if r["mes"][:7] == mes and (r["vendedor"] not in ult or str(r.get("importado_em")) > str(ult[r["vendedor"]].get("importado_em"))):
            ult[r["vendedor"]] = r
    prods, grp = {}, {k: g for k, g in _mapa_grupos(repo).items() if not k.startswith("T:")}
    for vend, r in ult.items():
        for l in _vend_linhas(repo, r["id"]):
            u = int(l.get("unidades") or 0)
            if u <= 0:
                continue
            chave = l.get("gtin") or nubi.compacta(f"{l.get('marca') or ''} {l.get('titulo') or ''}")[:70]
            chave = grp.get(chave, chave)                    # GTINs que o Bruno juntou na conferência (Produtos iguais)
            p = prods.setdefault(chave, {"titulo": l.get("titulo") or "", "marca": l.get("marca") or "", "gtin": l.get("gtin"), "v": 0.0, "u": 0,
                                         "vendedores": set(), "_pu": 0.0, "precos": []})
            p["v"] += float(l.get("vendas") or 0)
            p["u"] += u
            p["vendedores"].add(vend)
            if l.get("preco"):
                p["_pu"] += float(l["preco"]) * u
                p["precos"].append(float(l["preco"]))
    top = sorted(prods.values(), key=lambda p: -p["v"])[:limite]
    at = (repo._req("GET", "estoque_atualizacoes", {"select": "id,criado_em", "order": "id.desc", "limit": 1}) or [None])[0]
    estoque = []
    if at:
        estoque = repo._todos("estoque_itens", {"select": "sku,titulo,disponivel,atual,custo_medio", "atualizacao_id": repo._eq(at["id"])})
        for it in estoque:
            it["_tok"] = _tokens_produto(it.get("titulo"))
    gtins = {str(it.get("gtin") or it["sku"]).strip(): it for it in estoque
             if re.fullmatch(r"\d{8,14}", str(it.get("gtin") or it.get("sku") or "").strip())}
    linhas = []
    for p in top:
        pm = round(p["_pu"] / p["u"], 2) if p["_pu"] else None
        # 1º pelo GTIN (pedido do Bruno): o item do estoque com o mesmo GTIN (hoje só quando o SKU é o próprio GTIN; os anúncios
        # das Minhas Lojas vão trazer o GTIN de cada produto); 2º pelo título, como reserva
        meu, por = (gtins.get(p["gtin"]), "gtin") if p.get("gtin") and gtins.get(p["gtin"]) else (None, None)
        if not meu and estoque:
            meu, por = casar_estoque(p["titulo"], estoque), "titulo"
        disp = int(float(meu.get("disponivel") if meu.get("disponivel") is not None else meu.get("atual") or 0)) if meu else None
        custo = float(meu["custo_medio"]) if meu and meu.get("custo_medio") else None
        linhas.append({"produto": p["titulo"][:90], "marca": p["marca"], "vendas": round(p["v"], 2), "unidades": p["u"],
                       "vendedores": len(p["vendedores"]), "preco_medio": pm,
                       "preco_min": min(p["precos"]) if p["precos"] else None, "preco_max": max(p["precos"]) if p["precos"] else None,
                       "meu_sku": meu["sku"] if meu else None, "meu_disponivel": disp, "meu_custo": custo,
                       "margem_antes_taxas": round(pm - custo, 2) if pm and custo else None,
                       "situacao": "não tenho" if not meu else "zerado" if not disp else "tenho",
                       "gtin": p.get("gtin"), "casado_por": por if meu else None})
    return {"mes": mes, "vendedores": len(ult), "estoque_de": at["criado_em"] if at else None, "produtos": linhas}


def analise_foco(repo, forcar=False, semanal=False):
    """Rotina diária 'analise_foco' (DeepSeek): onde o Bruno deve focar, com os números de dados_foco. Uma por dia.
    semanal=True (rotina 'analise_semana', sábado): o plano da semana seguinte, para começar a segunda a todo vapor."""
    hoje = _agora_br().date().isoformat()
    chave = f"{'foco_semana' if semanal else 'foco'}|{hoje}"
    if not forcar and repo._req("GET", "ia_resumos", {"select": "chave", "chave": repo._eq(chave), "limit": 1}):
        return "já feita hoje"
    d = dados_foco(repo, limite=40 if semanal else 30)
    if not d or not d["produtos"]:
        return "sem dados de concorrentes"
    fm = lambda x: "—" if x is None else f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    tabela = "\n".join(
        f"{i}. {p['produto']} ({p['marca']}): vendas {fm(p['vendas'])}, {p['unidades']} un., {p['vendedores']} vendedor(es), "
        f"preço médio {fm(p['preco_medio'])} (de {fm(p['preco_min'])} a {fm(p['preco_max'])}); MEU ESTOQUE: {p['situacao']}"
        + (f", SKU {p['meu_sku']}, {p['meu_disponivel']} un., custo {fm(p['meu_custo'])}, margem antes das taxas {fm(p['margem_antes_taxas'])}"
           f" (casado pelo {'GTIN' if p['casado_por'] == 'gtin' else 'título: confira'})" if p["meu_sku"] else "") for i, p in enumerate(d["produtos"], 1))
    pedido = (
        "Você é o DeepSeek, analista de números do nubi. Abaixo, os produtos que mais venderam no mês "
        f"{d['mes'][5:7]}/{d['mes'][:4]} nos {d['vendedores']} concorrentes monitorados, já cruzados com o estoque do Bruno "
        "(os números foram calculados pelo sistema: NÃO recalcule e NÃO invente nenhum número; o cruzamento com o estoque é "
        "pelo GTIN quando dá e, se não, pelo título, que pode errar — diga 'confira' quando for decisivo). Margem 'antes das "
        "taxas' não desconta as tarifas do marketplace nem o frete.\n\nTABELA:\n" + tabela
        + (_pedido_semana(d) if semanal else
        "\n\nEscreva em português do Brasil, direto, em markdown curto, com estas seções:\n"
        "## Onde focar hoje\n3 a 5 produtos, cada um com o porquê em 1 linha (vende muito, poucos vendedores, eu tenho estoque, "
        "margem boa) e a ação (anunciar/impulsionar, repor, comprar, rever preço).\n"
        "## Preço\nonde o meu custo deixa competir com o preço médio e onde não dá.\n"
        "## Repor ou comprar\no que vende bem e eu tenho zerado ou não tenho.\n"
        "## Atenção\n1 ou 2 riscos (produto com muitos vendedores e preço caindo, margem apertada)."))
    ia.USO["origem"] = f"rotina {'analise_semana' if semanal else 'analise_foco'}"
    txt, _, qual = ia.perguntar(pedido, web=False, max_tokens=2500, qual="deepseek", modelo="pro", sistema=agentes.SISTEMA)
    if not (txt or "").strip():
        return "o DeepSeek não respondeu"
    repo._req("POST", "ia_resumos", corpo=[{"chave": chave, "texto": txt.strip(), "ia": ia.nome(qual), "dados": d}],
              prefer="resolution=merge-duplicates,return=minimal")
    return f"{'plano da semana gravado' if semanal else 'análise do dia gravada'} ({len(d['produtos'])} produtos, {d['vendedores']} concorrentes)"


def _pedido_semana(d):
    """Seções do plano semanal (sábado): contexto de datas de vendas próximas + o que fazer de segunda a domingo."""
    prox = [x for x in datas_vendas() if x["faltam"] <= 45]
    datas = "; ".join(f"{x['nome']} em {x['faltam']} dia(s)" for x in prox) or "nenhuma data grande nos próximos 45 dias"
    return (f"\n\nDATAS DE VENDAS PRÓXIMAS: {datas}.\n\n"
            "Este é o PLANO DA SEMANA (feito no sábado para o Bruno começar a segunda a todo vapor). Escreva em português do "
            "Brasil, direto, em markdown, com estas seções:\n"
            "## Resumo da semana\n3 linhas: o que está vendendo no mercado e como o estoque do Bruno está posicionado.\n"
            "## 5 prioridades da semana\nnumeradas, cada uma com a ação concreta e o produto (ex.: 'Segunda: repor X').\n"
            "## Comprar ou repor antes de segunda\nlista curta, do mais urgente ao menos.\n"
            "## Preços para revisar\nonde o custo permite brigar e onde é melhor não entrar.\n"
            "## Campanhas e datas\no que preparar para as datas de vendas próximas.\n"
            "## Riscos\n1 ou 2.")


def inicio_extras(repo):
    """Os 4 blocos novos do Início; cada um vira None ("sem dados") quando faltar."""
    def seguro(f):
        try:
            return f() or None
        except Exception:  # noqa: BLE001 — um bloco com problema não derruba os outros
            return None
    nt = seguro(lambda: repo._req("GET", "ia_resumos", {"select": "chave,dados,criado_em", "chave": "like.noticias|*",
                                                         "order": "chave.desc", "limit": 1}))
    rs = seguro(lambda: repo._req("GET", "ia_resumos", {"select": "chave,texto,ia,criado_em", "chave": "not.like.noticias|*",
                                                         "order": "criado_em.desc", "limit": 4})) or []
    au = seguro(lambda: repo._req("GET", "auditorias", {"select": "data,resumo", "order": "data.desc", "limit": 1})) or []
    analises = [{"chave": r["chave"], "ia": r.get("ia"), "criado_em": r.get("criado_em"), "texto": (r.get("texto") or "")[:600]} for r in rs]
    return {
        "dolar": seguro(dolar_do_dia),
        "datas": seguro(datas_vendas),
        "noticias": {"data": nt[0]["chave"].split("|")[1], "itens": (nt[0].get("dados") or {}).get("noticias") or []} if nt else None,
        "analises": {"resumos": analises, "auditoria": au[0] if au else None} if (analises or au) else None,
    }


def gerar_resumo_dia(repo, forcar=False):
    """Resumo do dia dos vendedores (guardado por data dos dados; forcar=True escreve de novo)."""
    if not ia.disponivel():
        raise ErroNuvem("Configure uma chave de IA (OPENAI_API_KEY) na Vercel para gerar o resumo.")
    d1, dados, pnl = _dados_resumo_dia(repo)
    if not d1:
        raise ErroNuvem(f"Sem dados para o resumo do dia: {dados}.")
    chave = f"vendedores|{d1}"
    if not forcar:
        ja = repo._req("GET", "ia_resumos", {"select": "chave,texto,ia,criado_em", "chave": repo._eq(chave)}) or []
        if ja:
            return {"atual": ja[0], "novo": False}
    ontem = repo._req("GET", "ia_resumos", {"select": "chave,texto", "chave": "like.vendedores|*",
                                            "order": "chave.desc", "limit": 2}) or []
    ontem = next((x for x in ontem if x["chave"] != chave), None)
    try:
        texto, dados_ia, qual = _escrever_resumo(
            "Você é o analista de mercado do dono de uma loja de perfumes no Mercado Livre Brasil. Todo dia você acompanha "
            "os vendedores concorrentes que ele monitora (dados do Nubimetrics, liberados com 2 dias de atraso) e escreve o "
            "RESUMO DO DIA: curto, direto, em português simples e sempre com números.\n"
            "Como analisar:\n"
            "- O DIA: use a VENDA ISOLADA DO DIA (export só daquele dia, com os itens de cada vendedor). Compare cada "
            "vendedor e produto com a média dos dias anteriores: quem acelerou, quem caiu, que produto puxou a venda de "
            "cada um, produto novo aparecendo, produto que sumiu ou com anúncios pausados (sem estoque).\n"
            "- Se houver o MESMO DIA DO MÊS ANTERIOR (ex.: 22/09 x 22/08), compare também dia com dia, lembrando que o dia "
            "da semana pode ser diferente.\n"
            "- O MÊS: a comparação é o MESMO PERÍODO (dia 1 até o último dia com dados x os mesmos dias do mês anterior). "
            "Nunca compare um mês parcial com um mês fechado.\n"
            "- OPORTUNIDADES: produto vendendo mais no mercado, concorrente sem estoque de um produto que vende bem, marca subindo.\n"
            "- ALERTAS: queda forte, concorrente acelerando muito, muitos vendedores brigando no mesmo produto.\n"
            "- Se houver o resumo de ontem, acompanhe os alertas de ontem (confirmou? piorou? resolveu?).\n"
            "- No futuro o nubi vai ter as vendas e o estoque da própria loja; por enquanto recomende o que ele deve olhar "
            "na loja dele (ex.: confira se você tem estoque de X).\n"
            "- Use só os dados fornecidos; não invente números; quando um dado for estimado, avise.\n"
            "- O site já mostra os cards 'quem mais vendeu' e 'quem mais caiu' com os números de cada vendedor: não repita "
            "a lista inteira, comente só o que importa. Em 'O que fazer hoje' dê 2 ou 3 ações.\n"
            + _obs_rotina(repo, "resumo_dia") + "\n\nDADOS:\n"
            + dados + (f"\n\nRESUMO DE ONTEM ({ontem['chave'].split('|')[1]}):\n{_sem_links(ontem['texto'])[:3000]}" if ontem else ""),
            SECOES_DIA, *_links_resumo(repo, pnl), max_tokens=2600)
    except Exception as e:  # noqa: BLE001
        raise ErroNuvem(f"A IA não respondeu: {str(e)[:150]}")
    _guardar_resumo(repo, chave, texto, qual, dados_ia)
    return {"atual": {"chave": chave, "texto": texto, "ia": ia.nome(qual),
                      "criado_em": datetime.now(timezone.utc).isoformat()}, "novo": True}


def _links_resumo(repo, pnl=None):
    """Vendedores monitorados e {nome do produto: chave} que foram nos dados, para ligar os tópicos da IA."""
    vend = {r["vendedor"] for r in _vend_rels(repo)} | {x["vendedor"] for x in (pnl or {}).get("vendedores") or []}
    try:
        vend |= {r["vendedor"] for r in repo._req("GET", "vend_vendas_dia", {"select": "vendedor", "order": "data.desc",
                                                                              "limit": 60}) or []}
    except ErroNuvem:
        pass
    vend = sorted(vend)
    prods = {}
    for lista in ((pnl or {}).get("produtos_alta") or [], (pnl or {}).get("produtos_queda") or []):
        for p in lista:
            prods.setdefault(p.get("produto"), p.get("chave"))
    try:
        c = _comparativo(repo)
        for p in c.get("ganhos", []) + c.get("perdas", []):
            prods.setdefault(p.get("produto"), p.get("chave"))
    except Exception:  # noqa: BLE001
        pass
    try:
        for p in rota_vendedores(repo, "GET", "vend_alertas", {}, b"").get("produtos", [])[:40]:
            prods.setdefault(p.get("produto"), p.get("chave"))
    except Exception:  # noqa: BLE001
        pass
    return vend, prods


def _links_semana(repo, sem):
    vend, prods = _links_resumo(repo)
    for k, p in list(sem["prod"]["atual"].items()) + list(sem["prod"]["ant"].items()):
        prods.setdefault(p["produto"], k)
    return vend, prods


def _semana(repo):
    """A semana que terminou no último dia liberado x a semana anterior (vendas isoladas de cada dia)."""
    ult = repo._req("GET", "vend_vendas_dia", {"select": "data", "order": "data.desc", "limit": 1}) or []
    fim = str(ult[0]["data"])[:10] if ult else None
    if not fim:
        rs = repo._req("GET", "ia_resumos", {"select": "chave", "chave": "like.vendedores|*", "order": "chave.desc", "limit": 1}) or []
        fim = rs[0]["chave"].split("|")[1] if rs else None
    if not fim:
        return None
    f = date.fromisoformat(fim)
    ini, ini_ant = (f - timedelta(days=6)).isoformat(), (f - timedelta(days=13)).isoformat()
    rows = _vendas_dias(repo, ini_ant, fim)
    sem = {"fim": fim, "ini": ini, "ini_ant": ini_ant, "fim_ant": (f - timedelta(days=7)).isoformat()}
    agg = {"atual": {}, "ant": {}}
    prod = {"atual": {}, "ant": {}}
    dias = {"atual": set(), "ant": set()}
    for r in rows:
        k = "atual" if str(r["data"])[:10] >= ini else "ant"
        dias[k].add(str(r["data"])[:10])
        a = agg[k].setdefault(r["vendedor"], [0.0, 0])
        a[0] += float(r["v"] or 0)
        a[1] += int(r["u"] or 0)
        for it in r["itens"] or []:
            p = prod[k].setdefault(it["k"], {"produto": it.get("t") or it["k"], "marca": it.get("m") or "", "v": 0.0, "u": 0})
            p["v"] += float(it.get("v") or 0)
            p["u"] += int(it.get("u") or 0)
    sem.update(dias_atual=len(dias["atual"]), dias_ant=len(dias["ant"]), agg=agg, prod=prod)
    return sem


def gerar_resumo_semana(repo, forcar=False):
    """Toda segunda: a semana que passou (resumos diários guardados + vendas de cada dia) x a semana anterior."""
    if not ia.disponivel():
        raise ErroNuvem("Configure uma chave de IA (OPENAI_API_KEY) na Vercel para gerar a análise.")
    s = _semana(repo)
    if not s:
        raise ErroNuvem("Ainda não há dados diários para a análise da semana.")
    chave = f"semana|{s['fim']}"
    if not forcar:
        ja = repo._req("GET", "ia_resumos", {"select": "chave,texto,ia,criado_em", "chave": repo._eq(chave)}) or []
        if ja:
            return {"atual": ja[0], "novo": False}
    L = [f"SEMANA ANALISADA: {_ddmm(s['ini'])} a {_ddmm(s['fim'])} ({s['dias_atual']} dia(s) com venda isolada coletada); "
         f"SEMANA ANTERIOR: {_ddmm(s['ini_ant'])} a {_ddmm(s['fim_ant'])} ({s['dias_ant']} dia(s) coletados)."]
    at, an = s["agg"]["atual"], s["agg"]["ant"]
    if at:
        tv, ta = sum(x[0] for x in at.values()), sum(x[0] for x in an.values())
        L.append(f"TOTAL DOS VENDEDORES: {_fm(tv)} na semana" + (f" x {_fm(ta)} na anterior ({(tv / ta - 1) * 100:+.0f}%)" if ta else ""))
        for v in sorted(set(at) | set(an), key=lambda v: -(at.get(v, [0])[0])):
            a, b = at.get(v, [0.0, 0]), an.get(v, [0.0, 0])
            L.append(f"- {v}: {_fm(a[0])} ({a[1]} un.)" + (f" x {_fm(b[0])} ({(a[0] / b[0] - 1) * 100:+.0f}%)" if b[0] else ""))
        pa, pn = s["prod"]["atual"], s["prod"]["ant"]
        top = sorted(pa.items(), key=lambda kv: -kv[1]["v"])[:15]
        L.append("PRODUTOS MAIS VENDIDOS NA SEMANA: " + "; ".join(
            f"{p['produto'][:50]} ({p['marca']}): {p['u']} un., {_fm(p['v'])}" + (f" x {_fm(pn[k]['v'])}" if k in pn else " (novo)" if pn else "")
            for k, p in top))
        if pn:
            difs = [(k, pa.get(k, {}).get("v", 0.0) - p["v"], p) for k, p in pn.items()]
            L.append("MAIORES QUEDAS DE PRODUTO x SEMANA ANTERIOR: " + "; ".join(
                f"{p['produto'][:50]} ({p['marca']}): {_fm(pa.get(k, {}).get('v', 0.0))} x {_fm(p['v'])}"
                for k, d, p in sorted(difs, key=lambda t: t[1])[:10] if d < 0))
            L.append("MAIORES ALTAS DE PRODUTO x SEMANA ANTERIOR: " + "; ".join(
                f"{pa[k]['produto'][:50]} ({pa[k]['marca']}): {_fm(pa[k]['v'])} x {_fm(pn.get(k, {}).get('v', 0.0))}"
                for k in sorted(pa, key=lambda k: -(pa[k]["v"] - pn.get(k, {}).get("v", 0.0)))[:10]))
    else:
        L.append("Ainda não há a venda isolada de cada dia; use os resumos diários e o mesmo período do mês.")
    c = _comparativo(repo)
    if c.get("tem") and c["total"]["var"] is not None:
        L.append(f"MESMO PERÍODO NO MÊS (01 a {_ddmm(c['ate'])} x 01 a {_ddmm(c['ate_ant'])}): {_fm(c['total']['v'])} x "
                 f"{_fm(c['total']['v_ant'])} ({c['total']['var'] * 100:+.0f}%)")
    diarios = repo._req("GET", "ia_resumos", {"select": "chave,texto", "chave": "like.vendedores|*", "order": "chave.desc",
                                              "limit": 8}) or []
    diarios = [x for x in diarios if s["ini"] <= x["chave"].split("|")[1] <= s["fim"]]
    for x in reversed(diarios):
        L.append(f"\nRESUMO DO DIA {_ddmm(x['chave'].split('|')[1])}:\n{_sem_links(x['texto'])[:1400]}")
    ant = repo._req("GET", "ia_resumos", {"select": "chave,texto", "chave": "like.semana|*", "order": "chave.desc", "limit": 2}) or []
    ant = next((x for x in ant if x["chave"] != chave), None)
    if ant:
        L.append(f"\nANÁLISE DA SEMANA PASSADA:\n{_sem_links(ant['texto'])[:2500]}")
    try:
        texto, dados_ia, qual = _escrever_resumo(
            "Você é o analista de mercado do dono de uma loja de perfumes no Mercado Livre Brasil. Toda segunda de manhã "
            "você escreve a ANÁLISE DA SEMANA dos vendedores concorrentes que ele monitora, com base nas vendas de cada dia "
            "e nos resumos diários que você mesmo escreveu. Seja direto, em português simples e sempre com números.\n"
            "- Compare a semana com a anterior (quando houver os dois períodos) e com o mesmo período do mês anterior.\n"
            "- Mostre tendências (o que se repetiu vários dias), não fatos de um dia só.\n"
            "- Confira os alertas e oportunidades dos resumos diários: o que se confirmou, o que não.\n"
            "- Termine com um plano prático para a semana que começa.\n"
            "- Use só os dados fornecidos; não invente números. No plano da semana dê 3 a 5 ações.\n"
            + _obs_rotina(repo, "resumo_semana") + "\n\nDADOS:\n" + "\n".join(L),
            SECOES_SEMANA, *_links_semana(repo, s), max_tokens=3000)
    except Exception as e:  # noqa: BLE001
        raise ErroNuvem(f"A IA não respondeu: {str(e)[:150]}")
    _guardar_resumo(repo, chave, texto, qual, dados_ia)
    return {"atual": {"chave": chave, "texto": texto, "ia": ia.nome(qual),
                      "criado_em": datetime.now(timezone.utc).isoformat()}, "novo": True}


SCHEMA_CATEGORIA = {"type": "object", "additionalProperties": False, "required": ["categoria", "confianca", "motivo"],
                    "properties": {"categoria": {"type": "string", "enum": list(pesquisa_marca.CATS_IA)},
                                   "confianca": {"type": "string", "enum": ["alta", "média", "baixa"]},
                                   "motivo": {"type": "string"}}}


def categorias_lote(repo):
    """
    Tarefa de rotina: 1) confere o lote aberto na OpenAI e, pronto, guarda as sugestões em marca_sugestoes;
    2) sem lote aberto, manda num lote novo as marcas do ranking em Outros ou sem categoria que ainda não têm sugestão.
    """
    abertos = [l for l in repo._todos("ia_lotes", {"select": "*", "tipo": "eq.categorias"})
               if l["status"] not in ("completed", "failed", "expired", "cancelled", "aplicado")]
    msgs = []
    for l in abertos:
        st = ia.lote_status(l["id"])
        estado = st.get("status") or "?"
        if estado == "completed" and st.get("output_file_id"):
            falhas = []
            res = ia.lote_resultados(st["output_file_id"], falhas, st.get("error_file_id"))
            manuais = {r["marca_chave"] for r in repo._todos("marca_categorias", {"select": "marca_chave"})}
            nomes = json.loads(l.get("detalhe") or "{}")
            regs = []
            for k, txt in res.items():
                try:
                    j = json.loads(txt)
                except ValueError:
                    continue
                if k in manuais or j.get("categoria") not in pesquisa_marca.CATS_IA:
                    continue
                regs.append({"marca_chave": k, "marca": nomes.get(k, k), "categoria": j["categoria"],
                             "confianca": j.get("confianca") or "baixa", "motivo": (j.get("motivo") or "")[:400],
                             "fonte": "IA em lote (ChatGPT)", "estado": "nova"})
            for i in range(0, len(regs), 300):
                repo._req("POST", "marca_sugestoes", corpo=regs[i:i + 300], prefer="resolution=merge-duplicates,return=minimal")
            estado = "aplicado"
            # o que falhou (ou veio fora do formato) não ganha sugestão: volta sozinho no próximo lote
            pend = sorted(set(nomes) - {r["marca_chave"] for r in regs} - manuais) if nomes else [f["id"] for f in falhas]
            msgs.append(f"lote pronto: {len(regs)} sugestão(ões) em Ranking > Categorias"
                        + (f"; {len(pend)} pendente(s) para o próximo lote ({', '.join(str(x) for x in pend[:8])}"
                           f"{'…' if len(pend) > 8 else ''})" if pend else ""))
        else:
            msgs.append(f"lote {estado} ({(st.get('request_counts') or {}).get('completed', 0)} de {l.get('itens')})")
        repo._req("PATCH", "ia_lotes", {"id": repo._eq(l["id"])},
                  corpo={"status": estado, "atualizado_em": datetime.now(timezone.utc).isoformat()}, prefer="return=minimal")
    if any(not m.startswith("lote pronto") for m in msgs):
        return "; ".join(msgs)
    # marcas do último mês de cada categoria do ranking em Outros/sem categoria, sem sugestão e sem escolha manual
    manuais = {r["marca_chave"]: r["categoria"] for r in repo._todos("marca_categorias", {"select": "marca_chave,categoria"})}
    ja = {r["marca_chave"] for r in repo._todos("marca_sugestoes", {"select": "marca_chave"})}
    cands = {}
    por_cat = {}
    for r in _relatorios(repo):
        por_cat.setdefault(r["categoria"], []).append(r)
    for cat, rels in por_cat.items():
        for l in repo._todos("ranking_linhas", {"select": "marca,vendas,unidades", "relatorio_id": repo._eq(rels[-1]["id"])}):
            c, fonte = categorias.classificar(l["marca"], manuais)
            k = nubi.compacta(l["marca"] or "")
            if not k or fonte == "manual" or c not in ("Outros", categorias.SEM) or k in ja:
                continue
            x = cands.setdefault(k, {"marca": l["marca"], "vendas": 0.0, "unidades": 0})
            x["vendas"] += float(l.get("vendas") or 0)
            x["unidades"] += int(l.get("unidades") or 0)
    if not cands:
        return "; ".join(msgs) or "nenhuma marca para classificar"
    lista = "\n".join(f"- {c}: {d}" for c, d in pesquisa_marca.CATS_IA.items())
    pedidos = []
    for k, x in sorted(cands.items(), key=lambda kv: -kv[1]["vendas"])[:500]:
        preco = x["vendas"] / x["unidades"] if x["unidades"] else None
        pedidos.append((k, {"model": os.environ.get("NUBI_IA_MODELO", "gpt-4.1"), "max_output_tokens": 300,
                            "input": (f'Marca de perfumes vendida no Mercado Livre Brasil: "{x["marca"]}"'
                                      + (f" (preço médio R$ {preco:,.0f})".replace(",", ".") if preco else "")
                                      + f". Classifique em UMA categoria:\n{lista}\nRegras: grife de moda importada = "
                                      "Designer; importada que só faz perfume e é barata = Importados low ticket; brasileira = "
                                      "Nacional (mesmo com nome estrangeiro); do Oriente Médio = Árabe; casa de luxo clássica = "
                                      "Alta perfumaria. Se não conhece a marca, confiança baixa. Motivo: 1 frase em português."),
                            "text": {"format": {"type": "json_schema", "name": "categoria", "schema": SCHEMA_CATEGORIA,
                                                "strict": True}}}))
    lote = ia.lote_criar(pedidos, "categorias")
    repo._req("POST", "ia_lotes", corpo=[{"id": lote, "tipo": "categorias", "status": "validating", "itens": len(pedidos),
                                          "detalhe": json.dumps({k: cands[k]["marca"] for k, _ in pedidos}, ensure_ascii=False)}],
              prefer="return=minimal")
    return "; ".join(msgs + [f"lote novo com {len(pedidos)} marca(s); a resposta chega em até 24 h"])


def resumos_marcas_pendentes(repo):
    """Análise mensal das marcas de cada categoria cujo mês fechado ainda não tem análise."""
    out = {}
    cats = {}
    for r in _relatorios(repo):
        cats.setdefault(r["categoria"], []).append(r)
    for cat, rels in cats.items():
        chave = f"ranking|{cat}|{rels[-1]['mes'][:7]}"
        if repo._req("GET", "ia_resumos", {"select": "chave", "chave": repo._eq(chave)}):
            continue
        try:
            gerar_resumo_marcas(repo, cat, rels, chave)
            out[chave] = "gerado"
        except ErroNuvem as e:
            out[chave] = str(e)
    return out


# ---------------------------------------------------------------------------
# Tarefas de rotina (tabela rotinas, editável no site). A Vercel chama r=rotinas de hora em hora;
# roda aqui as tarefas do servidor cujo dia e horário (Brasília) chegaram e que ainda não rodaram hoje.
# A coleta roda no Mac mini (launchd) e só consulta se está ligada no dia.
# ---------------------------------------------------------------------------
DIAS_SEM = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
NO_MAC = ("coleta", "estoque", "gestor", "memoria")  # rodam no Mac mini (coletor); o servidor só diz se está na hora
NO_SERVIDOR = ("rankeamento", "categorias_lote", "produtos_ia", "resumo_dia", "analise_foco", "analise_semana", "resumo_semana", "resumo_marcas", "nomes_marcas",
               "noticias", "auditoria", "reuniao", "design", "agente")     # nesta ordem (o agente usa o tempo que sobrar)
CAMPOS_ROTINA = ("nome", "descricao", "responsavel", "horario", "dias_semana", "dia_mes", "ativo", "observacao", "ordem")


def _agora_br():
    return datetime.now(timezone.utc) - timedelta(hours=3)


def _br(ts):
    return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone(timezone.utc) - timedelta(hours=3)


def rotina_no_dia(r, agora=None):
    agora = agora or _agora_br()
    if r.get("dia_mes"):
        return agora.day >= int(r["dia_mes"])          # mensal: do dia marcado em diante (a tarefa só faz o que falta)
    return DIAS_SEM[agora.weekday()] in (r.get("dias_semana") or [])


def rotina_pendente(r, agora=None):
    agora = agora or _agora_br()
    if not r.get("ativo") or not rotina_no_dia(r, agora) or agora.strftime("%H:%M") < (r.get("horario") or "00:00"):
        return False
    return not (r.get("ultima_execucao") and _br(r["ultima_execucao"]).date() == agora.date())


def _marcar_rotina(repo, rid, resultado):
    try:
        repo._req("PATCH", "rotinas", {"id": repo._eq(rid)}, corpo={
            "ultima_execucao": datetime.now(timezone.utc).isoformat(), "ultimo_resultado": str(resultado)[:600]},
            prefer="return=minimal")
    except ErroNuvem:
        pass


def _conhecimento_pendente(repo):
    """Card #39: mensagens da Sala e cards concluídos desde a última rodada da rotina 'memoria' (ou, na primeira vez,
    das últimas 24h), para o Hermes (Mac mini) memorizar na caixa de conhecimento e o Qwen revisar."""
    rot = (repo._req("GET", "rotinas", {"select": "ultima_execucao", "id": "eq.memoria"}) or [None])[0]
    desde = (rot or {}).get("ultima_execucao") or (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    msgs = repo._req("GET", "reuniao_mensagens", {"select": "id,autor,texto,criado_em", "criado_em": f"gt.{desde}",
                                                   "order": "id", "limit": 200}) or []
    cards = repo._req("GET", "reuniao_tarefas", {"select": "id,titulo,notas,relatorio,atualizado_em", "status": "eq.feita",
                                                  "atualizado_em": f"gt.{desde}", "order": "atualizado_em", "limit": 100}) or []
    itens = [{"fonte": f"reuniao_mensagens:{m['id']}", "autor": m.get("autor") or "", "texto": (m.get("texto") or "")[:2000]}
             for m in msgs]
    itens += [{"fonte": f"reuniao_tarefas:{c['id']}", "autor": "card",
               "texto": f"{c['titulo']}\n{(c.get('relatorio') or c.get('notas') or '')[:3000]}"} for c in cards]
    return itens, desde


_ORDEM_PRIORIDADE = {"urgente": 0, "alta": 1, "media": 2, "baixa": 3}
_ORDEM_RISCO = {"baixo": 0, "medio": 1, "alto": 2}


def ordem_fila(t):
    """Chave de ordenação da fila do programador (card #43): prioridade (urgente > alta > média > baixa), depois
    risco (baixo antes de médio/alto), depois id mais antigo. Uso: sorted(cards, key=ordem_fila)."""
    return (_ORDEM_PRIORIDADE.get(t.get("prioridade"), 2), _ORDEM_RISCO.get(t.get("risco") or "medio", 1), t["id"])


def _pauta_diaria(repo, ultima_execucao):
    """Pauta automática da reunião diária (determinística, sem IA): feito, travado, melhorar, próximos."""
    agora = datetime.now(timezone.utc)
    desde = str(ultima_execucao or (agora - timedelta(hours=24)).isoformat())

    feitas = repo._req("GET", "reuniao_tarefas", {"select": "id,titulo,notas", "status": "eq.feita",
                        "atualizado_em": f"gte.{desde}", "order": "atualizado_em.desc", "limit": 15}) or []
    feito = "\n".join(f"- #{t['id']} {t['titulo']}" + (f" — {t['notas']}" if t.get("notas") else "") for t in feitas) \
        or "nada concluído desde a última reunião"

    travadas = repo._req("GET", "reuniao_tarefas", {"select": "id,titulo,status,aguardando",
                          "aguardando": "not.is.null", "order": "atualizado_em.desc", "limit": 10}) or []
    trav = "\n".join(f"- #{t['id']} {t['titulo']} ({t['status']}): {t['aguardando']}" for t in travadas)
    try:
        erros = [e for e in _ops_erros(repo) if str(e.get("inicio") or "") >= desde][:10]
    except ErroNuvem:
        erros = []
    erros_txt = "\n".join(f"- {e['fonte']}: {e['nome']} — {(e.get('resultado') or '')[:150]}" for e in erros)
    duv_txt = ""
    try:
        duvidas = repo._req("GET", "reuniao_mensagens", {"select": "id,texto,meta", "meta->>tipo": "eq.duvida",
                            "criado_em": f"gte.{desde}", "order": "id"}) or []
        decididas = {(m.get("meta") or {}).get("duvida_id") for m in repo._req("GET", "reuniao_mensagens",
                    {"select": "meta", "meta->>tipo": "eq.decisao", "criado_em": f"gte.{desde}"}) or []}
        abertas = [m for m in duvidas if m["id"] not in decididas]
        duv_txt = "\n".join(f"- dúvida sem resposta (card #{(m.get('meta') or {}).get('tarefa_id')}): {m['texto'][:150]}" for m in abertas)
    except ErroNuvem:
        pass
    travado = "\n".join(x for x in (trav, erros_txt, duv_txt) if x) or "nada travado"

    hoje = _agora_br().date()
    inicio_mes = agora.replace(day=1, hour=3, minute=0, second=0, microsecond=0)
    usos = repo._todos("agentes_uso", {"select": "agente,custo_usd,inicio", "inicio": f"gte.{min(inicio_mes, agora - timedelta(days=1)).isoformat()}"})
    custo = {}
    for u in usos:
        d = custo.setdefault(u["agente"], {"dia": 0.0, "mes": 0.0})
        c = float(u.get("custo_usd") or 0)
        if str(u["inicio"]) >= inicio_mes.isoformat():
            d["mes"] += c
        if _br(u["inicio"]).date() == hoje:
            d["dia"] += c
    custo_txt = "\n".join(f"- {a}: hoje US$ {v['dia']:.3f}, mês US$ {v['mes']:.2f}" for a, v in custo.items()) or "sem uso de IA registrado"
    try:
        reprovas = len(repo._req("GET", "tarefa_eventos", {"select": "id", "tipo": "eq.erro_teste", "criado_em": f"gte.{desde}"}) or [])
    except ErroNuvem:
        reprovas = 0
    melhorar = f"Custo de IA (mês em curso):\n{custo_txt}\nRetrabalho: {reprovas} reprovação(ões) de teste desde a última reunião."

    aprovadas = repo._req("GET", "reuniao_tarefas", {"select": "id,titulo,prioridade,risco", "status": "eq.aprovada",
                           "aguardando": "is.null", "order": "id", "limit": 500}) or []
    proximas = sorted(aprovadas, key=ordem_fila)[:5]
    prox = "\n".join(f"- #{t['id']} [{t.get('prioridade')}] {t['titulo']}" for t in proximas) or "fila vazia"

    return ("## O que foi feito desde a última reunião\n" + feito
            + "\n\n## O que travou\n" + travado
            + "\n\n## O que dá para melhorar\n" + melhorar
            + "\n\n## Próximos da fila\n" + prox)


def rodar_rotinas(repo, so=None):
    """Roda as tarefas do servidor que chegaram na hora (ou só a tarefa 'so', agora)."""
    t0 = time.monotonic()
    agora = _agora_br()
    rot = {r["id"]: r for r in repo._todos("rotinas", {"select": "*", "order": "ordem,id"})}
    out = {}
    if not so:
        try:                                            # base de conhecimento: junta o que mudou na última hora (fase 1, 26/09)
            out["saber"] = agentes.sincronizar_saber(repo, forcar=True)
        except Exception as e:  # noqa: BLE001
            out["saber"] = f"erro: {str(e)[:120]}"
    for rid in NO_SERVIDOR:
        r = rot.get(rid)
        if rid == "design" and r and not so:
            # de hora em hora (não 1 vez por dia): o Astra (design) e o DeepSeek (dados) especificam os cards que chegaram
            ult = r.get("ultima_execucao")
            if not r.get("ativo") or not rotina_no_dia(r, agora) or (ult and (datetime.now(timezone.utc) - datetime.fromisoformat(
                    str(ult).replace("Z", "+00:00"))).total_seconds() < 50 * 60):
                continue
        elif not r or (so and rid != so) or (not so and not rotina_pendente(r, agora)):
            continue
        inicio = datetime.now(timezone.utc).isoformat()
        ia.USO["origem"] = f"rotina {rid}"
        try:
            if rid == "reuniao":
                au = (repo._req("GET", "auditorias", {"select": "*", "order": "data.desc", "limit": 1}) or [None])[0]
                extra = ""
                if au:
                    extra = ("AUDITORIA DE " + str(au["data"]) + ": " + (au.get("resumo") or "") + "\n"
                             + "\n".join(f"[{c['nivel']}] {c['titulo']} — {c['detalhe']}" for c in (au.get("conferencias") or [])[:25])
                             + "\n" + "\n".join(f"({m['autor']}) {m['texto'][:1500]}" for m in (au.get("conversa") or [])))
                obs = (r.get("observacao") or "").strip()
                abertura = ("📋 Reunião diária — pauta de hoje:\n\n" + _pauta_diaria(repo, r.get("ultima_execucao"))
                            + "\n\nDiscutam: o que foi feito, o que travou, o que dá para melhorar, os próximos da fila "
                            "e a auditoria de hoje; decidam o que vai para desenvolvimento."
                            + (f"\nPauta do dono: {obs}" if obs else ""))
                x = reuniao.rodada(repo, abertura, extra, autor_extra="sistema", segunda_volta=True)
                res = f"{len(x)} mensagem(ns) na Sala de reunião"
            elif rid == "auditoria":
                reg = auditoria.rodar(repo, (r.get("observacao") or "").strip())
                repo._req("POST", "auditorias", corpo=[reg], prefer="resolution=merge-duplicates,return=minimal")
                res = reg["resumo"]
            elif rid == "design":
                partes = []
                for nome_, f_ in (("memória", memorizar_solucoes), ("especialistas", especificar_cards),
                                  ("modelo", completar_modelos), ("distribuição", distribuir_cards), ("agentes", trabalhar_agentes)):
                    try:
                        r_ = f_(repo)
                    except Exception as e:  # noqa: BLE001
                        r_ = f"erro em {nome_}: {str(e)[:120]}"
                    if r_:
                        partes.append(r_)
                res = " · ".join(partes) or "nada a fazer"
            elif rid == "categorias_lote":
                res = categorias_lote(repo)
            elif rid == "produtos_ia":
                res = agrupar_produtos(repo)
            elif rid == "resumo_dia":
                x = gerar_resumo_dia(repo, forcar=bool(so))
                res = f"dados até {_ddmm(x['atual']['chave'].split('|')[1])}: " + ("gerado" if x["novo"] else "já existia")
            elif rid == "resumo_semana":
                x = gerar_resumo_semana(repo, forcar=bool(so))
                res = f"semana até {_ddmm(x['atual']['chave'].split('|')[1])}: " + ("gerada" if x["novo"] else "já existia")
            elif rid == "noticias":
                x = gerar_noticias(repo, forcar=bool(so))
                res = f"{x.get('n', 0)} notícia(s) gravada(s)" if x["novo"] else "já existia"
            elif rid == "rankeamento":
                res = laboratorio_rankeamento(repo, forcar=bool(so))
            elif rid == "analise_foco":
                res = analise_foco(repo, forcar=bool(so))
            elif rid == "analise_semana":
                res = analise_foco(repo, forcar=bool(so), semanal=True)
            elif rid == "nomes_marcas":
                res = conferir_nomes_marcas(repo)
            elif rid == "resumo_marcas":
                x = resumos_marcas_pendentes(repo)
                res = "; ".join(f"{k.split('|')[1]} {k.split('|')[2]}: {v}" for k, v in x.items()) or "nada novo (análises do mês já feitas)"
            else:
                seg = min(TEMPO_MAX, 280 - (time.monotonic() - t0))
                if seg < 40:
                    continue                                   # sem tempo nesta chamada: roda na próxima hora
                x = rodar_agente(repo, "agendado" if not so else "manual", segundos=seg)
                res = f"{x['pesquisados']} GTIN(s) pesquisado(s), {x['encontrados']} encontrado(s)"
        except ErroNuvem as e:
            res = f"erro: {e}"
        except Exception as e:  # noqa: BLE001
            res = f"erro: {str(e)[:200]}"
        _marcar_rotina(repo, rid, res)
        _registrar_execucao(repo, rid, "manual" if so else "agendada", inicio, res)
        out[rid] = res
    return out


def _registrar_execucao(repo, rid, origem, inicio, res):
    try:
        repo._req("POST", "rotinas_execucoes", corpo=[{
            "rotina": rid, "origem": origem, "inicio": inicio, "fim": datetime.now(timezone.utc).isoformat(),
            "ok": not str(res).startswith("erro"), "resultado": str(res)[:1000]}], prefer="return=minimal")
    except ErroNuvem:
        pass                                           # sem a tabela ainda: a rotina roda do mesmo jeito


def _ops_execucoes(repo, dias=14):
    """Execuções das rotinas (servidor) e das coletas (Mac) dos últimos dias, mais novas primeiro."""
    desde = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()
    nomes = {r["id"]: r["nome"] for r in repo._todos("rotinas", {"select": "id,nome"})}
    out = []
    try:
        for e in repo._req("GET", "rotinas_execucoes", {"select": "*", "inicio": f"gte.{desde}", "order": "inicio.desc", "limit": 400}) or []:
            out.append({"tipo": "rotina", "id": e["rotina"], "nome": nomes.get(e["rotina"], e["rotina"]), "origem": e.get("origem"),
                        "inicio": e["inicio"], "fim": e.get("fim"), "ok": e.get("ok"), "resultado": e.get("resultado") or ""})
    except ErroNuvem:
        pass
    for c in repo._req("GET", "coletor_execucoes", {"select": "id,iniciado_em,terminado_em,tarefa,ok,arquivos,importados,erros,mensagem,em_andamento",
                                                      "iniciado_em": f"gte.{desde}", "order": "id.desc", "limit": 200}) or []:
        out.append({"tipo": "coleta", "id": c["id"], "nome": f"Coleta ({c.get('tarefa') or 'diario'})", "origem": "Mac mini",
                    "inicio": c["iniciado_em"], "fim": c.get("terminado_em"), "em_andamento": c.get("em_andamento"),
                    "ok": c.get("ok") if (c.get("erros") or 0) == 0 or c.get("ok") is False else False,
                    "resultado": (c.get("mensagem") or "") + (f" · {c['erros']} erro(s)" if c.get("erros") else "")})
    out.sort(key=lambda x: str(x["inicio"]), reverse=True)
    return out


def _ops_erros(repo):
    """Tudo o que deu errado, num lugar só: rotinas, coletas, auditoria do dia e agentes que não responderam."""
    erros = [dict(e, fonte="Tarefa de rotina" if e["tipo"] == "rotina" else "Coletor (Mac)")
             for e in _ops_execucoes(repo, 30) if e.get("ok") is False]
    au = (repo._req("GET", "auditorias", {"select": "data,conferencias", "order": "data.desc", "limit": 1}) or [None])[0]
    if au:
        for c in au.get("conferencias") or []:
            if c.get("nivel") == "erro":
                erros.append({"fonte": "Auditoria", "nome": c.get("titulo"), "inicio": str(au["data"]) + "T12:00:00+00:00",
                              "resultado": c.get("detalhe") or "", "area": c.get("area"), "ok": False})
    desde = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    for m in repo._req("GET", "reuniao_mensagens", {"select": "id,texto,criado_em", "autor": "eq.sistema",
                                                     "criado_em": f"gte.{desde}", "order": "id.desc", "limit": 50}) or []:
        if "não respondeu" in (m.get("texto") or ""):
            erros.append({"fonte": "Sala de reunião", "nome": "Agente não respondeu", "inicio": m["criado_em"],
                          "resultado": m["texto"], "ok": False})
    erros.sort(key=lambda x: str(x["inicio"]), reverse=True)
    return erros


def rotina_8h(repo):
    """Compatibilidade com a agenda antiga (r=rotina_8h): roda as tarefas de rotina pendentes."""
    return rodar_rotinas(repo)


# ---------------------------------------------------------------------------
# Agentes: quem são, custo (tokens × preço), se estão rodando algo, teste de versão e apelido
# ---------------------------------------------------------------------------

AGENTE_QUAL = {"chatgpt": "codex", "deepseek": "deepseek", "gptoss": "ollama", "claude": "claude", "astra": "chatgpt"}   # testáveis daqui
AGENTE_MODELO = {"deepseek": "pro", "astra": "gpt-6-astra"}
AGENTE_AUTOR = {"chatgpt": "ChatGPT", "deepseek": "DeepSeek", "gptoss": "gpt-oss", "claude": "Claude", "astra": "Astra (design)", "qwen": "Qwen (revisor)",
                "hermes": "Hermes", "claude_code": "Claude (código)", "claude_mac": "Ferreiro", "copilot": "Copilot"}


def _precos(repo):
    try:
        return {p["modelo"]: p for p in repo._todos("ia_precos", {"select": "*"})}
    except ErroNuvem:
        return {}


def _preco_de(precos, modelo):
    """Preço do modelo exato ou do mais parecido cadastrado (ex.: 'gpt-5.3-codex-2026...' usa 'gpt-5.3-codex')."""
    if modelo in precos:
        return precos[modelo]
    cands = [k for k in precos if modelo.startswith(k)]
    return precos[max(cands, key=len)] if cands else None


# Preço de cache da Anthropic é um fator do preço de entrada do modelo, não um preço próprio por modelo (card #21):
# leitura de cache custa ~1/10 da entrada normal, criação (TTL padrão de 5 min) custa ~1,25x.
CACHE_LEITURA_FATOR = 0.1
CACHE_CRIACAO_FATOR = 1.25


def ligar_registro_uso(repo, origem):
    """Cada chamada de IA desta requisição vira uma linha em agentes_uso (aba Agentes)."""
    cache = {}

    def gravar(fase, d):
        if fase == "inicio":
            r = repo._req("POST", "agentes_uso", corpo=[dict(d, inicio=datetime.now(timezone.utc).isoformat())],
                          prefer="return=representation")
            return (r or [{}])[0].get("id")
        if not d.get("id"):
            return None
        reg = {k: d[k] for k in ("ok", "erro", "modelo", "tokens_in", "tokens_out", "cache_read_tokens",
                                  "cache_creation_tokens", "latencia_ms") if k in d}
        reg["fim"] = datetime.now(timezone.utc).isoformat()
        if d.get("ok") and d.get("modelo"):
            if "p" not in cache:
                cache["p"] = _precos(repo)
            p = _preco_de(cache["p"], d["modelo"])
            if p and p.get("entrada") is not None and p.get("saida") is not None and d.get("tokens_in") is not None:
                p_entrada = float(p["entrada"])
                custo = ((d.get("tokens_in") or 0) * p_entrada
                        + (d.get("cache_read_tokens") or 0) * p_entrada * CACHE_LEITURA_FATOR
                        + (d.get("cache_creation_tokens") or 0) * p_entrada * CACHE_CRIACAO_FATOR
                        + (d.get("tokens_out") or 0) * float(p["saida"])) / 1e6
                reg["custo_usd"] = round(custo, 6)
        repo._req("PATCH", "agentes_uso", {"id": f"eq.{d['id']}"}, corpo=reg, prefer="return=minimal")
        return None
    def gravar_web(pergunta, resposta, links, qual):
        # base de conhecimento (fase 1, 26/09): toda pesquisa na internet dos agentes fica guardada, com a pergunta, a resposta e as fontes
        agora_ = datetime.now(timezone.utc).isoformat()
        chave = hashlib.sha1(f"{agora_}|{pergunta}".encode()).hexdigest()[:20]
        repo._req("POST", "saber", corpo=[{"tipo": "pesquisa_web", "titulo": re.sub(r"\s+", " ", pergunta)[:160],
                                           "texto": f"PERGUNTA:\n{pergunta[:6000]}\n\nRESPOSTA:\n{resposta[:12000]}",
                                           "autor": ia.nome(qual), "fonte_tabela": "web", "fonte_id": chave, "links": links[:20],
                                           "tags": [str(origem or "")[:60]], "criado_em": agora_}], prefer="return=minimal")
    ia.USO.update({"gravar": gravar, "origem": origem, "web": gravar_web})


def _resumo_uso(xs):
    """Soma chamadas/tokens/custo de uma lista de agentes_uso e o detalhamento por rotina/tarefa (origem) — card #18.
    Lista vazia (nenhuma chamada no período) fica com chamadas=0: a tela mostra 'Sem dados', nunca um zero calculado."""
    grupos = {}
    for x in xs:
        g = grupos.setdefault(x.get("origem") or "outros", {"origem": x.get("origem") or "outros",
                                                              "chamadas": 0, "tokens_in": 0, "tokens_out": 0, "custo": 0.0})
        g["chamadas"] += 1
        g["tokens_in"] += int(x.get("tokens_in") or 0)
        g["tokens_out"] += int(x.get("tokens_out") or 0)
        g["custo"] += float(x.get("custo_usd") or 0)
    detalhe = sorted((dict(g, custo=round(g["custo"], 4)) for g in grupos.values()), key=lambda d: -d["custo"])[:8]
    return {"chamadas": len(xs), "tokens_in": sum(int(x.get("tokens_in") or 0) for x in xs),
            "tokens_out": sum(int(x.get("tokens_out") or 0) for x in xs),
            "custo": round(sum(float(x.get("custo_usd") or 0) for x in xs), 4), "detalhe": detalhe}


def _agentes_painel(repo):
    ags = repo._todos("agentes", {"select": "*", "order": "ordem"})
    agora = datetime.now(timezone.utc)
    inicio_mes = agora.replace(day=1, hour=3, minute=0, second=0, microsecond=0)    # 00h de Brasília do dia 1
    janela = min(inicio_mes, agora - timedelta(days=31))   # cobre também Ontem e os últimos 7/30 dias (card #18)
    usos = repo._todos("agentes_uso", {"select": "agente,modelo,origem,inicio,fim,ok,tokens_in,tokens_out,custo_usd,erro",
                                       "inicio": f"gte.{janela.isoformat()}",
                                       "order": "inicio"})
    hoje = _agora_br().date()
    ult_msg = {}
    for m in repo._req("GET", "reuniao_mensagens", {"select": "autor,criado_em", "order": "id.desc", "limit": 400}) or []:
        ult_msg.setdefault(m["autor"], m["criado_em"])
    for a in ags:
        u = [x for x in usos if x["agente"] == a["id"]]
        dia = [x for x in u if _br(x["inicio"]).date() == hoje]
        ontem = [x for x in u if _br(x["inicio"]).date() == hoje - timedelta(days=1)]
        dia7 = [x for x in u if _br(x["inicio"]).date() > hoje - timedelta(days=7)]
        dia30 = [x for x in u if _br(x["inicio"]).date() > hoje - timedelta(days=30)]
        mes = [x for x in u if str(x["inicio"]) >= inicio_mes.isoformat()]
        sem_preco = any(x.get("ok") and x.get("custo_usd") is None and (x.get("tokens_in") or x.get("tokens_out")) for x in mes)
        rodando = [x for x in u if not x.get("fim") and str(x["inicio"]) > (agora - timedelta(minutes=10)).isoformat()]
        erros = [x for x in u if x.get("ok") is False and str(x["inicio"]) > (agora - timedelta(hours=24)).isoformat()]
        qual = AGENTE_QUAL.get(a["id"])
        chave = ia.tem(qual) if qual else None
        ultima = max([str(x["inicio"]) for x in u] + [str(ult_msg.get(AGENTE_AUTOR.get(a["id"]), ""))] or [""])
        a.update({
            "hoje": _resumo_uso(dia), "mes": _resumo_uso(mes), "ontem": _resumo_uso(ontem),
            "dia7": _resumo_uso(dia7), "dia30": _resumo_uso(dia30),
            "sem_preco": sem_preco, "rodando": [{"origem": x.get("origem"), "desde": x["inicio"]} for x in rodando],
            "erros_24h": len(erros), "ultimo_erro": erros[-1]["erro"] if erros else None,
            "modelo_atual": next((x["modelo"] for x in reversed(u) if x.get("modelo") and x.get("ok")), None),
            "ultima_atividade": ultima or None, "chave": chave, "testavel": bool(qual),
            "status": "executando" if rodando else "sem chave" if chave is False else "com erro" if erros
            else "ativo" if qual or (ultima and ultima > (agora - timedelta(hours=24)).isoformat()) else "parado",
            "perfil": agentes.PERFIS.get(a["id"])})
    return {"agentes": ags, "precos": sorted(_precos(repo).values(), key=lambda p: p["modelo"])}


def _perguntar_agente(aid, texto, max_tokens=300):
    qual = AGENTE_QUAL[aid]
    modelo = AGENTE_MODELO.get(aid)
    return ia.perguntar(texto, web=False, max_tokens=max(max_tokens, 4000) if aid == "astra" else max_tokens,
                        qual=qual, modelo=modelo)


# ---------------------------------------------------------------------------
# Minhas Lojas → Estoque (UpSeller). O coletor do Mac exporta a Lista de Estoque de madrugada (rotina 'estoque')
# e manda para estoque_importar; cada envio vira uma foto completa, comparada com a anterior e analisada pelo Estoquista.
# ---------------------------------------------------------------------------
CAMPOS_ESTOQUE = ("sku", "titulo", "armazem", "estante", "estoque_min", "transito_compra", "transito_transf", "ocupado",
                  "disponivel", "atual", "custo_medio", "subtotal", "criado", "ordem")


def _normalizar_sku(sku):
    """trim + upper + sem caracteres invisíveis (categoria Unicode "Cf"); mesma regra do coletor (card #57)."""
    if not sku:
        return ""
    limpo = "".join(ch for ch in str(sku) if unicodedata.category(ch) != "Cf").replace("\xa0", " ")
    return limpo.strip().upper()


def _estoque_itens(repo, aid):
    return repo._todos("estoque_itens", {"select": ",".join(CAMPOS_ESTOQUE), "atualizacao_id": repo._eq(int(aid)), "order": "sku"})


def _estoque_itens_ordem(repo, aid):
    """Itens na ordem da planilha do UpSeller (mais novos primeiro), como o modelo do Gestor Seller."""
    xs = _estoque_itens(repo, aid)
    if all(it.get("ordem") is not None for it in xs):
        return sorted(xs, key=lambda it: it["ordem"])
    return sorted(sorted(xs, key=lambda it: it["sku"]), key=lambda it: it.get("criado") or "", reverse=True)   # a lista do UpSeller vem do mais novo


def estoque_importar(repo, conteudo, arquivo, origem="coletor", esperado=None):
    try:
        itens = estoque.ler_planilha(conteudo)
    except estoque.ErroEstoque as e:
        raise ErroNuvem(f"Estoque não importado: {e}.")
    if esperado and int(esperado) != len(itens):
        raise ErroNuvem(f"Estoque não importado: a tela do UpSeller mostrava {esperado} SKUs e a planilha tem {len(itens)} "
                        "(export incompleto; o coletor tenta de novo).")
    h = ranking.hash_de(conteudo)
    ja = repo._req("GET", "estoque_atualizacoes", {"select": "id,criado_em", "hash": repo._eq(h), "limit": 1}) or []
    if ja:
        return {"ok": True, "id": ja[0]["id"], "repetido": True,
                "log": [f"Essa planilha já foi importada (atualização de {_br(ja[0]['criado_em']):%d/%m %H:%M})."]}
    ant = (repo._req("GET", "estoque_atualizacoes", {"select": "id", "order": "id.desc", "limit": 1}) or [None])[0]
    anteriores = _estoque_itens(repo, ant["id"]) if ant else []
    for it in anteriores:
        for c in estoque.NUMEROS:
            it[c] = None if it.get(c) is None else float(it[c])
    d = estoque.comparar(anteriores, itens)
    t, resumo = d["totais"], estoque.resumo_texto(d)
    novo = repo._req("POST", "estoque_atualizacoes", corpo=[{
        "origem": origem, "arquivo": arquivo, "hash": h, "esperado": int(esperado) if esperado else None,
        "skus": t["skus"], "unidades": t["unidades"], "valor": t["valor"], "zerados": t["zerados"],
        "resumo": resumo, "diff": d}], prefer="return=representation")
    aid = novo[0]["id"]
    regs = [dict({c: it.get(c) for c in CAMPOS_ESTOQUE}, atualizacao_id=aid, ordem=i) for i, it in enumerate(itens)]
    try:
        for i in range(0, len(regs), LOTE):
            repo._req("POST", "estoque_itens", corpo=regs[i:i + LOTE], prefer="return=minimal")
    except ErroNuvem:
        repo._req("DELETE", "estoque_atualizacoes", {"id": repo._eq(aid)})
        raise
    analise = estoque_analisar(repo, aid, d, itens)
    return {"ok": True, "id": aid, "log": [f"OK: estoque importado ({arquivo})."] + resumo + ([analise] if analise else [])}


def estoque_analisar(repo, aid, d=None, itens=None):
    """O Estoquista escreve a leitura curta da atualização (grava em analise/analise_por). Devolve o aviso, se falhar."""
    if d is None:
        reg = (repo._req("GET", "estoque_atualizacoes", {"select": "diff", "id": repo._eq(int(aid))}) or [None])[0]
        if not reg:
            raise ErroNuvem("Atualização de estoque não encontrada.", 404)
        d, itens = reg["diff"], _estoque_itens(repo, aid)
        for it in itens:
            for c in estoque.NUMEROS:
                it[c] = None if it.get(c) is None else float(it[c])
    ia.USO["origem"] = "estoque"
    texto, quem = estoque.analisar_ia(d, itens, agentes.SISTEMA)
    if texto:
        repo._req("PATCH", "estoque_atualizacoes", {"id": repo._eq(int(aid))}, corpo={"analise": texto, "analise_por": quem},
                  prefer="return=minimal")
        return ""
    return f"(análise do Estoquista não saiu agora: {quem})"


def rota_estoque(repo, metodo, rota, q, corpo):
    if rota == "estoque_importar" and metodo == "POST":
        return estoque_importar(repo, corpo, (q.get("arquivo") or "Lista_de_Estoque.xlsx")[:200],
                                "manual" if q.get("origem") == "manual" else "coletor",
                                int(q["esperado"]) if str(q.get("esperado") or "").isdigit() else None)
    if rota == "estoque_analisar" and metodo == "POST":
        aid = int(json.loads(corpo or b"{}").get("id") or 0)
        aviso = estoque_analisar(repo, aid)
        if aviso:
            raise ErroNuvem(aviso.strip("()"))
        return {"ok": True}
    if rota == "estoque_pedir" and metodo == "POST":
        aberto = repo._req("GET", "coletor_pedidos", {"select": "id", "atendido_em": "is.null", "tarefa": "eq.estoque", "limit": 1}) or []
        if not aberto:
            repo._req("POST", "coletor_pedidos", corpo=[{"motivo": "atualizar o estoque (pedido no site)", "tarefa": "estoque"}],
                      prefer="return=minimal")
        return {"ok": True, "ja_havia": bool(aberto)}
    if rota == "gestor_pedir" and metodo == "POST":
        # "Importar no Gestor Seller agora": o vigia do Mac pega o pedido em até 15 min
        if not repo._req("GET", "estoque_atualizacoes", {"select": "id", "limit": 1}):
            raise ErroNuvem("Ainda não há estoque importado do UpSeller para montar a planilha.")
        aberto = repo._req("GET", "coletor_pedidos", {"select": "id", "atendido_em": "is.null", "tarefa": "eq.gestor", "limit": 1}) or []
        if not aberto:
            repo._req("POST", "coletor_pedidos", corpo=[{"motivo": "importar a planilha no Gestor Seller (pedido no site)", "tarefa": "gestor"}],
                      prefer="return=minimal")
        return {"ok": True, "ja_havia": bool(aberto)}
    if rota == "gestor_amostra":
        # SKUs para o coletor conferir no Gestor Seller depois de importar (o custo tem que bater com a planilha)
        ult = (repo._req("GET", "estoque_atualizacoes", {"select": "id", "order": "id.desc", "limit": 1}) or [None])[0]
        if not ult:
            return {"skus": []}
        com = [it for it in _estoque_itens_ordem(repo, ult["id"]) if it.get("custo_medio") and float(it["custo_medio"]) > 0]
        idx = sorted({0, len(com) // 2, len(com) - 1}) if com else []
        return {"skus": [{"sku": com[i]["sku"], "custo": round(float(com[i]["custo_medio"]), 2), "titulo": com[i].get("titulo") or ""}
                         for i in idx]}
    if rota == "estoque_sku_existe":
        # card #57: diagnóstico do "SKU não encontrado" no Gestor Seller — existe na última foto de estoque_itens?
        norm = _normalizar_sku(q.get("sku") or "")
        ult = (repo._req("GET", "estoque_atualizacoes", {"select": "id", "order": "id.desc", "limit": 1}) or [None])[0]
        if not ult or not norm:
            return {"existe": False}
        existe = any(_normalizar_sku(it["sku"]) == norm for it in _estoque_itens(repo, ult["id"]))
        return {"existe": existe}
    if rota == "gestor_pendente":
        # rotina 'gestor' (ex.: 00:40, 10 min depois do estoque): importa 1 vez por dia, só se o estoque de hoje já entrou
        rot = (repo._req("GET", "rotinas", {"select": "*", "id": "eq.gestor"}) or [None])[0]
        agora = _agora_br()
        na_hora = bool(rot and rot.get("ativo") and rotina_no_dia(rot, agora) and agora.strftime("%H:%M") >= (rot.get("horario") or "00:40"))
        ok = (repo._req("GET", "coletor_execucoes", {"select": "iniciado_em", "tarefa": "eq.gestor", "ok": "eq.true", "order": "id.desc", "limit": 1})
              or [None])[0]
        feito = bool(ok and _br(ok["iniciado_em"]).date() == agora.date())
        est = (repo._req("GET", "estoque_atualizacoes", {"select": "criado_em", "origem": "eq.coletor", "order": "id.desc", "limit": 1}) or [None])[0]
        estoque_hoje = bool(est and _br(est["criado_em"]).date() == agora.date())
        return {"rodar": na_hora and not feito and estoque_hoje, "feito_hoje": feito, "estoque_hoje": estoque_hoje,
                "horario": (rot or {}).get("horario")}
    if rota == "gestor_auto":
        # depois de cada estoque, o coletor pergunta se importa no Gestor Seller sozinho (rotina 'gestor' ligada)
        rot = (repo._req("GET", "rotinas", {"select": "ativo", "id": "eq.gestor"}) or [None])[0]
        return {"ligado": bool(rot and rot.get("ativo"))}
    if rota == "coleta_pendente":
        # o vigia do Mac segue o horário da rotina 'coleta' (Central → Rotinas): roda 1 vez por dia, do horário em diante
        rot = (repo._req("GET", "rotinas", {"select": "*", "id": "eq.coleta"}) or [None])[0]
        agora = _agora_br()
        ult = (repo._req("GET", "coletor_execucoes", {"select": "iniciado_em", "tarefa": "eq.diario", "order": "id.desc", "limit": 1}) or [None])[0]
        hoje_ok = bool(ult and _br(ult["iniciado_em"]).date() == agora.date() and _br(ult["iniciado_em"]).strftime("%H:%M") >= (rot or {}).get("horario", "07:00"))
        na_hora = bool(rot and rot.get("ativo") and rotina_no_dia(rot, agora) and agora.strftime("%H:%M") >= (rot.get("horario") or "07:00"))
        return {"rodar": na_hora and not hoje_ok, "horario": (rot or {}).get("horario") or "07:00"}
    if rota == "estoque_pendente":
        # o vigia do Mac pergunta se está na hora da atualização da madrugada (rotina 'estoque', 1 vez por dia)
        rot = (repo._req("GET", "rotinas", {"select": "*", "id": "eq.estoque"}) or [None])[0]
        agora = _agora_br()
        ult = (repo._req("GET", "estoque_atualizacoes", {"select": "criado_em", "origem": "eq.coletor", "order": "id.desc", "limit": 1})
               or [None])[0]
        hoje_ok = bool(ult and _br(ult["criado_em"]).date() == agora.date())
        na_hora = bool(rot and rot.get("ativo") and rotina_no_dia(rot, agora) and agora.strftime("%H:%M") >= (rot.get("horario") or "03:00"))
        return {"rodar": na_hora and not hoje_ok, "feito_hoje": hoje_ok, "horario": (rot or {}).get("horario")}
    if rota == "estoque":
        hist = repo._req("GET", "estoque_atualizacoes", {
            "select": "id,criado_em,origem,arquivo,skus,unidades,valor,zerados,resumo,analise_por", "order": "id.desc", "limit": 60}) or []
        if not hist:
            return {"atual": None, "historico": [], "itens": []}
        aid = int(q.get("id") or hist[0]["id"])
        atual = (repo._req("GET", "estoque_atualizacoes", {"select": "*", "id": repo._eq(aid)}) or [None])[0]
        if not atual:
            raise ErroNuvem("Atualização de estoque não encontrada.", 404)
        rot = (repo._req("GET", "rotinas", {"select": "horario,ativo,ultima_execucao,ultimo_resultado", "id": "eq.estoque"}) or [None])[0]
        falha = (repo._req("GET", "coletor_execucoes", {"select": "iniciado_em,ok,mensagem,em_andamento", "tarefa": "eq.estoque",
                                                         "order": "id.desc", "limit": 1}) or [None])[0]
        gestor = repo._req("GET", "coletor_execucoes", {"select": "iniciado_em,terminado_em,ok,mensagem,em_andamento", "tarefa": "eq.gestor",
                                                        "order": "id.desc", "limit": 8}) or []
        rot_g = (repo._req("GET", "rotinas", {"select": "ativo,horario", "id": "eq.gestor"}) or [None])[0]
        pend_g = repo._req("GET", "coletor_pedidos", {"select": "id,pedido_em", "atendido_em": "is.null", "tarefa": "eq.gestor", "limit": 1}) or []
        return {"atual": atual, "itens": _estoque_itens(repo, aid), "historico": hist, "rotina": rot, "ultima_execucao": falha,
                "gestor": {"importacoes": gestor, "automatico": bool(rot_g and rot_g.get("ativo")), "horario": (rot_g or {}).get("horario"), "pedido": pend_g[0] if pend_g else None}}
    raise ErroNuvem("Rota desconhecida.", 404)


# ---------------------------------------------------------------------------
# Agente do card (Desenvolvimento): responde o dono na hora e, quando precisa, pede ao Mac um comando da lista
# FECHADA (COMANDOS_MAC); o despachante do Mac executa e a saída volta como passo no próprio card.
# ---------------------------------------------------------------------------
PAPEL_CARD = ("Você é o agente responsável por esta tarefa de desenvolvimento do nubi e está conversando com o dono (Bruno) "
              "dentro do card. Responda em português do Brasil, curto e direto (até 8 linhas), sempre sobre ESTA tarefa. "
              "O que você PODE fazer agora: explicar, conferir o que já foi feito pelos passos do card, dizer o próximo passo e "
              "pedir ao Mac mini UM comando da lista fechada abaixo (ele roda sozinho em até 1 minuto e a saída aparece no card) "
              "ou abrir uma DÚVIDA na Sala para outro agente, quando não souber algo com certeza. "
              "O que você NÃO faz: escrever ou publicar código (isso é da sessão do Claude Code, que só anda quando está aberta; "
              "diga isso com clareza quando for o caso), inventar comandos fora da lista, dizer que fez algo que não fez, ou "
              "inventar uma resposta técnica que você não tem certeza (abra uma dúvida em vez disso). "
              "Nunca peça senhas, chaves ou tokens.")


def responder_card(repo, tid):
    t = (repo._req("GET", "reuniao_tarefas", {"select": "*", "id": repo._eq(int(tid))}) or [None])[0]
    if not t:
        return
    evs = repo._req("GET", "tarefa_eventos", {"select": "autor,tipo,texto,criado_em", "tarefa_id": repo._eq(int(tid)),
                                               "order": "id.desc", "limit": 20}) or []
    hist = "\n".join(f"[{e['autor']}] {e['texto'][:1200]}" for e in reversed(evs))
    est = (repo._req("GET", "mac_estado", {"select": "visto_em", "id": "eq.1"}) or [None])[0]
    online = bool(est and est.get("visto_em") and (datetime.now(timezone.utc) - datetime.fromisoformat(
        str(est["visto_em"]).replace("Z", "+00:00"))).total_seconds() < 300)
    lista = "\n".join(f"- {k}: {v}" for k, v in COMANDOS_MAC.items() if k not in ("baixar_modelo", "hermes_card"))
    try:
        caixa = "\n\n".join(f"### {c['titulo']}\n{c['texto'][:2500]}" for c in repo._req("GET", "conhecimento", {
            "select": "titulo,texto", "fixo": "eq.true", "order": "atualizado_em.desc", "limit": 6}) or [])
    except ErroNuvem:
        caixa = ""
    pedido = (PAPEL_CARD + f"\n\nTAREFA #{t['id']} ({t.get('status')}, responsável {t.get('responsavel') or 'claude_code'}): "
              f"{t.get('titulo')}\n{t.get('descricao') or ''}\nNota: {t.get('notas') or '-'}"
              f"\n\nMAC MINI: {'online' if online else 'OFFLINE (não peça comando; diga que o Mac está sem sinal)'}"
              f"\nCOMANDOS PERMITIDOS (chave: o que faz):\n{lista}"
              + (f"\n\nCAIXA DE CONHECIMENTO (fixos):\n{caixa}" if caixa else "")
              + f"\n\nCONVERSA DO CARD (mais antiga primeiro; 'voce' é o dono):\n{hist}"
              '\n\nResponda SOMENTE com JSON: {"resposta": "<texto para o dono, ou vazio se só abrir dúvida>", '
              '"comando": "<chave da lista ou null>", "duvida": "<pergunta objetiva para outro agente da Sala, ou null>"}')
    ia.USO["origem"] = f"card #{tid}"
    j, _, qual = ia.perguntar_json(pedido, web=False, max_tokens=1500, qual="claude" if ia.tem("claude") else None,
                                   sistema=agentes.SISTEMA)
    resposta = str(j.get("resposta") or "").strip()
    duvida_texto = str(j.get("duvida") or "").strip()
    if duvida_texto:
        try:
            decisao = reuniao.duvida(repo, int(tid), duvida_texto, quem="agente_card")
            resposta = (resposta + "\n\n" if resposta else "") + f"💬 Abri uma dúvida na Sala: \"{duvida_texto}\" — resposta: {decisao}"
        except Exception as e:  # noqa: BLE001 - falha ao abrir a dúvida não pode derrubar a resposta principal já pronta
            if not resposta:
                resposta = f"Eu não sabia responder com certeza e não consegui abrir uma dúvida agora ({str(e)[:150]})."
    if not resposta:
        raise ErroNuvem("resposta vazia da IA")
    autor = "claude" if qual == "claude" else {"chatgpt": "chatgpt", "codex": "chatgpt", "deepseek": "deepseek", "ollama": "gptoss"}.get(qual, "claude")
    agora_ = datetime.now(timezone.utc).isoformat()
    eventos = [{"tarefa_id": int(tid), "autor": autor, "tipo": "passo", "texto": resposta[:4000], "criado_em": agora_}]
    cmd = j.get("comando")
    if cmd and cmd in COMANDOS_MAC and cmd not in ("baixar_modelo", "hermes_card") and online:
        novo = repo._req("POST", "mac_comandos", corpo=[{"comando": cmd, "arg": None, "pedido_por": f"agente do card #{tid}",
                                                          "status": "pendente", "criado_em": agora_, "tarefa_id": int(tid)}],
                         prefer="return=representation")
        eventos.append({"tarefa_id": int(tid), "autor": "mac", "tipo": "passo", "criado_em": agora_,
                        "texto": f"🖥️ Na fila do Mac: **{COMANDOS_MAC[cmd]}** (comando #{novo[0]['id']}). A saída aparece aqui."})
    repo._req("POST", "tarefa_eventos", corpo=eventos, prefer="return=minimal")
    repo._req("PATCH", "reuniao_tarefas", {"id": repo._eq(int(tid))}, corpo={"atualizado_em": agora_}, prefer="return=minimal")


# ---------------------------------------------------------------------------
# Especialistas: o Astra (design) e o DeepSeek (dados) escrevem o plano dos cards antes do programador pegar.
# ---------------------------------------------------------------------------
DESIGN_RE = re.compile(r"layout|design|\bux\b|\bui\b|tela|navega|menu|visual|celular|mobile|responsiv|cabe[çc]alho|card|bot[ãa]o|cores|tipografia", re.I)
DADOS_RE = re.compile(r"n[úu]mero|total|venda|c[áa]lcul|conta|reconcilia|dados|pre[çc]o|custo|estoque|coleta|banco|consulta|"
                      r"desempenho|performance|lento|cache|token|schema|json|ia\.py|auditoria|confer[êe]ncia|gate|teto", re.I)
PAPEL_DESIGN = ("Você é o Astra, designer de produto e UX do nubi (o programador é o Claude Code, que vai implementar exatamente "
                "o que você especificar, em HTML/CSS/JS puro no public/index.html). Escreva a ESPECIFICAÇÃO DE DESIGN deste card, "
                "em português do Brasil, em markdown curto, com estas seções: ## Objetivo (1 frase) · ## Onde (tela e rota, ex.: "
                "#/estoque) · ## Mudanças (lista numerada, concreta: componente, hierarquia, texto, ordem, estados vazio/carregando/erro) "
                "· ## Celular (como fica em 390 px; sem rolagem para o lado) · ## Critérios de pronto (3 a 6 itens verificáveis). "
                "Minimalista, dados mais importantes primeiro, navegação fácil, consistente com o resto do nubi (cards, chips, "
                "barra de baixo no celular). Não invente dados que o sistema não tem; se faltar informação, diga o que perguntar ao Bruno.")
PAPEL_DADOS = ("Você é o DeepSeek, engenheiro de dados e revisor de contas do nubi (o programador é o Claude Code, que vai "
               "implementar seguindo o seu plano em Python no servidor nubi_web.py/módulos e Supabase/PostgREST). Escreva o PLANO "
               "TÉCNICO deste card, em português do Brasil, markdown curto, com estas seções: ## Objetivo (1 frase) · ## Onde "
               "(arquivo/função/tabela prováveis; diga 'a confirmar no código' quando não tiver certeza) · ## Regras de cálculo "
               "(fórmulas exatas e de onde vem cada número) · ## Invariantes (o que tem que bater: dia × mês × grupo, soma de "
               "partes = total etc.) · ## Casos de borda (dia sem arquivo = pendente, zero, nulo, arredondamento do Nubimetrics, "
               "duplicados, fuso de Brasília) · ## Testes (3 a 6 testes concretos com entrada e saída esperada) · ## Custo "
               "(consultas ao banco e chamadas de IA; evite N+1). Regra do dono: zero erro nos números; na dúvida 'sem dados'. "
               "Não invente tabelas ou colunas: se não souber, diga o que conferir.")
# agente -> (quem, papel, regex dos cards, título do bloco, qual/modelo na IA, tokens)
ESPECIALISTAS = [
    ("astra", "Astra", PAPEL_DESIGN, DESIGN_RE, "📐 **Especificação de design (Astra)**", "Especificação de design", "chatgpt", "gpt-6-astra", 4000, ("site", "design", "layout", "ux")),
    ("deepseek", "DeepSeek", PAPEL_DADOS, DADOS_RE, "🧮 **Plano técnico (DeepSeek)**", "Plano técnico", "deepseek", "pro", 6000, ("dados", "numeros", "desempenho", "custo")),
]


def especificar_cards(repo, limite=2):
    """De hora em hora: o Astra (design) e o DeepSeek (dados) escrevem o plano dos cards aprovados da área deles."""
    cards = repo._req("GET", "reuniao_tarefas", {"select": "id,titulo,descricao,area,notas,risco,prioridade", "status": "eq.aprovada",
                                                 "aguardando": "is.null", "order": "id"}) or []
    cards.sort(key=ordem_fila)            # o que o Bruno pediu com urgência é especificado primeiro (antes: por id)
    saida = []
    for aid, nome, papel, rx, cab, marca, qual, modelo, toks, areas in ESPECIALISTAS:
        if not ia.tem(qual):
            saida.append(f"{nome}: sem chave")
            continue
        feitos = []
        for t in cards:
            if len(feitos) >= limite:
                break
            if not (t.get("area") in areas or rx.search(f"{t.get('titulo')} {t.get('descricao') or ''}")):
                continue
            if repo._req("GET", "tarefa_eventos", {"select": "id", "tarefa_id": repo._eq(t["id"]), "autor": repo._eq(aid),
                                                    "texto": f"like.*{marca}*", "limit": 1}):
                continue
            evs = repo._req("GET", "tarefa_eventos", {"select": "autor,texto", "tarefa_id": repo._eq(t["id"]), "order": "id.desc", "limit": 10}) or []
            conversa = "\n".join(f"[{e['autor']}] {e['texto'][:800]}" for e in reversed(evs))
            ia.USO["origem"] = f"{marca.lower()} card #{t['id']}"
            try:
                txt, _, _ = ia.perguntar(papel + f"\n\nCARD #{t['id']}: {t['titulo']}\n{t.get('descricao') or ''}\nNota: {t.get('notas') or '-'}"
                                         + (f"\n\nCONVERSA DO CARD:\n{conversa}" if conversa else ""),
                                         web=False, max_tokens=toks, qual=qual, modelo=modelo, sistema=agentes.SISTEMA)
            except Exception as e:  # noqa: BLE001
                saida.append(f"{nome} #{t['id']}: erro {str(e)[:80]}")
                continue
            if not (txt or "").strip():
                continue
            repo._req("POST", "tarefa_eventos", corpo=[{"tarefa_id": t["id"], "autor": aid, "tipo": "passo",
                                                        "texto": f"{cab}\n\n" + txt.strip()[:8000]}], prefer="return=minimal")
            repo._req("PATCH", "reuniao_tarefas", {"id": repo._eq(t["id"])}, corpo={"atualizado_em": datetime.now(timezone.utc).isoformat()},
                      prefer="return=minimal")
            feitos.append(f"#{t['id']}")
        if feitos:
            saida.append(f"{nome}: {', '.join(feitos)}")
    return "; ".join(saida) or "nenhum card esperando especificação"



# ---------------------------------------------------------------------------
# Time trabalhando sozinho: o coordenador distribui os cards aprovados, cada agente responsável faz a parte dele
# (texto: análise, documentação, plano, inventário) e o coordenador testa a entrega. Código fica com o programador
# (claude_code). Risco alto nunca anda sem o Bruno.
# ---------------------------------------------------------------------------
AGENTES_TEXTO = {"chatgpt", "deepseek", "astra", "gptoss"}      # trabalham pela API
AGENTES_MAC = {"hermes", "qwen"}                                 # trabalham no Mac (Ollama, grátis)
ENTREGA_TENTATIVAS = 3

# Card #44: card aprovado só executa com os 4 itens preenchidos na descrição (nem só o placeholder do modelo).
CARD_MODELO = [
    ("Escopo", (r"escopo",)),
    ("Arquivo/função", (r"arquivo\s*/\s*fun[cç][aã]o", r"arquivo\s+e\s+fun[cç][aã]o", r"arquivo\s*/\s*modulo", r"arquivo\s*/\s*módulo")),
    ("Teste", (r"teste",)),
    ("Critério de aceite", (r"crit[eé]rio\s+de\s+aceite",)),
]
CARD_MODELO_TXT = ("Escopo: [o que mudar e os limites da alteração]\n"
                    "Arquivo/função: [onde implementar]\nTeste: [como verificar a mudança]\n"
                    "Critério de aceite: [resultado verificável para considerar pronto]")


def _card_secoes(descricao):
    """Quebra a descrição do card nas seções rotuladas "Rótulo: texto" (card #44); devolve {nome canônico: corpo}."""
    linhas = (descricao or "").splitlines()
    marcas = []
    for i, linha in enumerate(linhas):
        m = re.match(r"\s*([^:\n]{1,40}):\s*(.*)$", linha)
        if not m:
            continue
        rotulo = m.group(1).strip().lower()
        for nome, variantes in CARD_MODELO:
            if any(re.fullmatch(v, rotulo) for v in variantes):
                marcas.append((i, nome, m.group(2)))
                break
    secoes = {}
    for idx, (i, nome, resto) in enumerate(marcas):
        fim = marcas[idx + 1][0] if idx + 1 < len(marcas) else len(linhas)
        secoes[nome] = "\n".join([resto] + linhas[i + 1:fim]).strip()
    return secoes


def card_pronto(descricao):
    """True + [] se a descrição tem os 4 itens do modelo preenchidos (card #44); senão False + os que faltam/vazios."""
    secoes = _card_secoes(descricao)
    faltando = [nome for nome, _ in CARD_MODELO
                if not secoes.get(nome) or re.fullmatch(r"\[.*\]", secoes[nome].strip())]
    return not faltando, faltando


def memorizar_solucoes(repo):
    """Pedido do Bruno (25/09): cada erro do coletor resolvido (card 🩺 fechado) vira uma 'Solução' fixa na caixa de
    conhecimento, com causa e correção. Se o erro voltar, o Hermes acha a solução pelo jeito do erro e já mostra na Sala."""
    cards = repo._req("GET", "reuniao_tarefas", {"select": "id,titulo,notas,relatorio", "status": "eq.feita",
                                                 "titulo": "like.🩺*", "order": "id.desc", "limit": 20}) or []
    feitos = []
    for t in cards:
        fonte = f"card #{t['id']}"
        if repo._req("GET", "conhecimento", {"select": "id", "fonte": repo._eq(fonte), "limit": 1}):
            continue
        rel = t.get("relatorio") or t.get("notas") or ""
        if not rel.strip():
            continue
        partes = {k: v.strip() for k, v in re.findall(r"##\s*(Causa|Solu[cç][aã]o|O que foi feito)\s*\n(.*?)(?=\n##|\Z)", rel, re.S | re.I)}
        corpo = "\n".join(f"{k}: {v[:900]}" for k, v in partes.items()) or rel[:1800]
        repo._req("POST", "conhecimento", corpo=[{
            "tipo": "solucao", "titulo": "Solução: " + t["titulo"].replace("🩺 Coletor: ", "").strip()[:150],
            "texto": f"{corpo}\n(card #{t['id']}; se o erro voltar, confira se a correção ainda está no coletor.py)",
            "autor": "Hermes", "fonte": fonte, "fixo": True, "atualizado_em": datetime.now(timezone.utc).isoformat()}],
            prefer="return=minimal")
        feitos.append(f"#{t['id']}")
    return "soluções guardadas: " + ", ".join(feitos) if feitos else ""


def completar_modelos(repo, limite=4):
    """Card aprovado sem os 4 itens do #44 não pode ficar travado (a fila parou a madrugada de 25/09): o coordenador preenche
    Escopo/Arquivo-função/Teste/Critério a partir do título, da descrição e dos planos do Astra/DeepSeek, e acrescenta na descrição."""
    if not ia.tem("claude"):
        return ""
    cards = [t for t in (repo._req("GET", "reuniao_tarefas", {"select": "id,titulo,descricao,area,risco", "status": "eq.aprovada",
                                                              "aguardando": "is.null", "order": "id"}) or [])
             if not card_pronto(t.get("descricao"))[0]]
    feitos = []
    for t in cards[:limite]:
        evs = repo._req("GET", "tarefa_eventos", {"select": "autor,texto", "tarefa_id": repo._eq(t["id"]), "order": "id"}) or []
        planos = "\n\n".join(e["texto"][:3000] for e in evs if e["autor"] in ("astra", "deepseek", "voce"))[-8000:]
        j, _, _ = ia.perguntar_json(
            "Você é o coordenador do time do nubi. Este card aprovado precisa do modelo obrigatório de 4 itens para ser executado. "
            "Escreva cada item em 1 a 3 linhas objetivas, com base SÓ no card e nos planos abaixo (não invente tabela, coluna ou "
            "arquivo que não esteja citado; na dúvida, diga onde procurar).\n\n"
            f"CARD #{t['id']} [{t.get('area') or '-'}] {t['titulo']}\n{(t.get('descricao') or '')[:3000]}\n\nPLANOS:\n{planos or '-'}"
            '\n\nResponda SOMENTE JSON: {"escopo": "...", "arquivo": "...", "teste": "...", "criterio": "..."}',
            web=False, max_tokens=1200, qual="claude", sistema=agentes.SISTEMA)
        itens = [str(j.get(k) or "").strip().replace("\n", " ") for k in ("escopo", "arquivo", "teste", "criterio")]
        if not all(itens):
            continue
        bloco = (f"Escopo: {itens[0]}\nArquivo/função: {itens[1]}\nTeste: {itens[2]}\nCritério de aceite: {itens[3]}")
        desc = ((t.get("descricao") or "").rstrip() + "\n\n" + bloco).strip()
        if not card_pronto(desc)[0]:
            continue
        repo._req("PATCH", "reuniao_tarefas", {"id": repo._eq(t["id"])},
                  corpo={"descricao": desc, "atualizado_em": datetime.now(timezone.utc).isoformat()}, prefer="return=minimal")
        _evento(repo, t["id"], "claude", "📝 Coordenador preencheu o modelo do card (#44) para ele poder andar:\n\n" + bloco)
        feitos.append(f"#{t['id']}")
    return "modelo preenchido: " + ", ".join(feitos) if feitos else ""


def _conhecimento_fixo(repo, n=6):
    try:
        return "\n\n".join(f"### {c['titulo']}\n{c['texto'][:2000]}" for c in repo._req("GET", "conhecimento", {
            "select": "titulo,texto", "fixo": "eq.true", "order": "atualizado_em.desc", "limit": n}) or [])
    except ErroNuvem:
        return ""


def _evento(repo, tid, autor, texto, tipo="passo"):
    agora_ = datetime.now(timezone.utc).isoformat()
    repo._req("POST", "tarefa_eventos", corpo=[{"tarefa_id": int(tid), "autor": autor, "tipo": tipo, "texto": texto[:8000],
                                                "criado_em": agora_}], prefer="return=minimal")
    return agora_


def distribuir_cards(repo, limite=6):
    """O coordenador escolhe o responsável dos cards aprovados sem dono (código -> programador; texto -> agente)."""
    cards = repo._req("GET", "reuniao_tarefas", {"select": "id,titulo,descricao,area,risco", "status": "eq.aprovada",
                                                 "responsavel": "is.null", "aguardando": "is.null", "order": "id", "limit": limite}) or []
    if not cards or not ia.tem("claude"):
        return ""
    lista = "\n".join(f"#{c['id']} [{c.get('area') or '-'}] {c['titulo']}: {(c.get('descricao') or '')[:400]}" for c in cards)
    j, _, _ = ia.perguntar_json(
        "Você é o coordenador do time do nubi. Para cada card, escolha UM responsável:\n"
        "- claude_code: qualquer card que precise escrever, mudar ou publicar código (site, servidor, coletor, banco);\n"
        "- copilot: SÓ card de código pequeno e bem especificado, de risco baixo, que mexe apenas na tela (public/index.html: "
        "botão, texto, cor, layout), sem servidor, banco, coletor nem números (programa pelo GitHub; o chefe revisa e publica);\n"
        "- chatgpt: análise, documentação técnica, inventário, revisão de código por texto;\n"
        "- deepseek: contas, números, custos, planos de dados;\n"
        "- astra: design e UX por escrito (sem programar);\n"
        "- hermes: memória, organização da caixa de conhecimento, documentação do histórico (roda de graça no Mac).\n"
        "Na dúvida se precisa de código, escolha claude_code.\n\nCARDS:\n" + lista +
        '\n\nResponda SOMENTE JSON: {"cards": [{"id": N, "responsavel": "...", "motivo": "<curto>"}]}',
        web=False, max_tokens=2000, qual="claude", sistema=agentes.SISTEMA)
    feitos = []
    validos = {"claude_code", "copilot"} | AGENTES_TEXTO | AGENTES_MAC
    risco = {c["id"]: c.get("risco") or "medio" for c in cards}
    for x in (j.get("cards") or []):
        tid, resp = int(x.get("id") or 0), str(x.get("responsavel") or "")
        if tid not in risco or resp not in validos:
            continue
        if resp == "copilot" and risco[tid] != "baixo":   # Copilot só pega risco baixo; o resto fica com o chefe
            resp = "claude_code"
        repo._req("PATCH", "reuniao_tarefas", {"id": repo._eq(tid), "responsavel": "is.null"},
                  corpo={"responsavel": resp, "atualizado_em": datetime.now(timezone.utc).isoformat()}, prefer="return=minimal")
        _evento(repo, tid, "claude", f"🧭 Coordenador: responsável **{resp}** — {str(x.get('motivo') or '')[:200]}")
        feitos.append(f"#{tid}→{resp}")
    return "distribuídos: " + ", ".join(feitos) if feitos else ""


def _tentativas(repo, tid):
    return len(repo._req("GET", "tarefa_eventos", {"select": "id", "tarefa_id": repo._eq(int(tid)), "tipo": "eq.erro_teste"}) or [])


def _pedido_card(t, evs, caixa):
    conversa = "\n".join(f"[{e['autor']}] {e['texto'][:1200]}" for e in evs[-15:])
    return (f"Você é o RESPONSÁVEL por este card do quadro de Desenvolvimento do nubi e vai entregá-lo agora.\n"
            f"CARD #{t['id']}: {t['titulo']}\n{t.get('descricao') or ''}\nNota: {t.get('notas') or '-'}\n\n"
            + (f"CAIXA DE CONHECIMENTO (fixos):\n{caixa}\n\n" if caixa else "")
            + (f"HISTÓRICO DO CARD (inclui reprovações anteriores; corrija o que foi apontado):\n{conversa}\n\n" if conversa else "")
            + "Entregue o RESULTADO COMPLETO em markdown, pronto para uso (não um plano de como faria). Você não edita código, "
              "não acessa o banco e não roda comandos: se o card só puder ser concluído com código, entregue o plano técnico "
              "detalhado e termine com uma linha exatamente assim: PRECISA_CODIGO. Não invente números nem fatos.")


def entregar_card(repo, tid, autor, texto):
    """Recebe a entrega de um agente, passa para Em teste e o coordenador confere (aprova -> feita com relatório)."""
    t = (repo._req("GET", "reuniao_tarefas", {"select": "*", "id": repo._eq(int(tid))}) or [None])[0]
    if not t or not (texto or "").strip():
        return "entrega vazia"
    texto = texto.strip()
    _evento(repo, tid, autor, "📦 **Entrega**\n\n" + texto[:7500])
    if "PRECISA_CODIGO" in texto:
        repo._req("PATCH", "reuniao_tarefas", {"id": repo._eq(int(tid))}, corpo={
            "status": "aprovada", "responsavel": "claude_code", "atualizado_em": datetime.now(timezone.utc).isoformat()}, prefer="return=minimal")
        _evento(repo, tid, "claude", "🔀 Precisa de código: o plano acima fica para o programador automático, que assume o card.")
        return f"#{tid}: passou para o programador"
    repo._req("PATCH", "reuniao_tarefas", {"id": repo._eq(int(tid))}, corpo={
        "status": "em_teste", "testador": "claude", "atualizado_em": datetime.now(timezone.utc).isoformat()}, prefer="return=minimal")
    j, _, _ = ia.perguntar_json(
        f"Você é o coordenador do nubi e TESTA a entrega de um agente. CARD #{t['id']}: {t['titulo']}\n{t.get('descricao') or ''}"
        f"\n\nENTREGA de {autor}:\n{texto[:9000]}\n\nConfira: cumpre o que o card pede? Está correta, sem números "
        "inventados, útil para o Bruno? Responda SOMENTE JSON: {\"aprovado\": true|false, \"motivo\": \"<o que está errado ou "
        "faltando, se reprovado>\", \"relatorio\": \"<markdown: ## O que foi feito · ## Entrega (resumo) · ## Teste do "
        "coordenador · ## Como usar>\", \"conhecimento\": {\"titulo\": \"...\", \"texto\": \"...\"} ou null}",
        web=False, max_tokens=3000, qual="claude", sistema=agentes.SISTEMA)
    agora_ = datetime.now(timezone.utc).isoformat()
    if j.get("aprovado"):
        rel = str(j.get("relatorio") or "").strip() or f"Entrega de {autor} aprovada pelo coordenador."
        _evento(repo, tid, "claude", "✅ Teste do coordenador: aprovado.", tipo="teste_ok")
        _evento(repo, tid, "claude", rel, tipo="relatorio")
        repo._req("PATCH", "reuniao_tarefas", {"id": repo._eq(int(tid))}, corpo={
            "status": "feita", "relatorio": rel[:20000], "notas": f"Entregue por {autor} e testado pelo coordenador.",
            "atualizado_em": agora_}, prefer="return=minimal")
        c = j.get("conhecimento")
        if isinstance(c, dict) and c.get("titulo") and c.get("texto"):
            repo._req("POST", "conhecimento", corpo=[{"tipo": "aprendizado", "titulo": str(c["titulo"])[:200], "texto": str(c["texto"])[:8000],
                                                      "autor": autor, "fonte": f"card #{tid}"}], prefer="return=minimal")
        return f"#{tid}: aprovado"
    _evento(repo, tid, "claude", "❌ " + str(j.get("motivo") or "entrega não atende ao card")[:2000], tipo="erro_teste")
    volta = {"status": "aprovada", "atualizado_em": agora_}
    if _tentativas(repo, tid) >= ENTREGA_TENTATIVAS:
        volta["aguardando"] = f"O agente {autor} não conseguiu entregar em {ENTREGA_TENTATIVAS} tentativas. Reescrevo o card, troco o responsável ou você decide?"
    repo._req("PATCH", "reuniao_tarefas", {"id": repo._eq(int(tid))}, corpo=volta, prefer="return=minimal")
    return f"#{tid}: reprovado"


def trabalhar_agentes(repo, limite=2):
    """Os agentes responsáveis (não o programador) fazem os cards aprovados deles. Risco alto e cards esperando o Bruno ficam."""
    cards = [t for t in (repo._req("GET", "reuniao_tarefas", {"select": "*", "status": "eq.aprovada", "aguardando": "is.null",
                                                              "order": "id"}) or [])
             if t.get("responsavel") in AGENTES_TEXTO | AGENTES_MAC and (t.get("risco") or "medio") != "alto"]
    saida, caixa = [], None
    for t in cards:
        if len([x for x in saida if not x.startswith("Mac")]) >= limite:
            break
        tid, resp = t["id"], t["responsavel"]
        ok, faltando = card_pronto(t.get("descricao"))
        if not ok:
            msg = f"Card não executado: preencha {', '.join(faltando)} na descrição."
            ultimo = (repo._req("GET", "tarefa_eventos", {"select": "texto", "tarefa_id": repo._eq(tid), "order": "id.desc", "limit": 1}) or [None])[0]
            if not ultimo or ultimo.get("texto") != msg:
                _evento(repo, tid, "sistema", msg, tipo="status")
            continue
        if resp in AGENTES_MAC:
            est = (repo._req("GET", "mac_estado", {"select": "visto_em", "id": "eq.1"}) or [None])[0]
            online = bool(est and (datetime.now(timezone.utc) - datetime.fromisoformat(str(est["visto_em"]).replace("Z", "+00:00"))).total_seconds() < 300)
            ja = repo._req("GET", "mac_comandos", {"select": "id", "comando": "eq.hermes_card", "arg": repo._eq(str(tid)),
                                                    "status": "in.(pendente,rodando)", "limit": 1})
            if not online or ja:
                continue
            agora_ = datetime.now(timezone.utc).isoformat()
            repo._req("POST", "mac_comandos", corpo=[{"comando": "hermes_card", "arg": str(tid), "pedido_por": "coordenador",
                                                      "status": "pendente", "criado_em": agora_, "tarefa_id": tid}], prefer="return=minimal")
            repo._req("PATCH", "reuniao_tarefas", {"id": repo._eq(tid)}, corpo={"status": "em_desenvolvimento", "iniciado_em": agora_,
                                                                                 "atualizado_em": agora_}, prefer="return=minimal")
            _evento(repo, tid, "hermes", "🪽 Peguei o card: vou fazer no Mac mini (grátis) e entrego aqui.")
            saida.append(f"Mac #{tid}")
            continue
        agora_ = datetime.now(timezone.utc).isoformat()
        repo._req("PATCH", "reuniao_tarefas", {"id": repo._eq(tid)}, corpo={"status": "em_desenvolvimento", "iniciado_em": agora_,
                                                                             "atualizado_em": agora_}, prefer="return=minimal")
        _evento(repo, tid, resp, "Peguei o card e estou trabalhando nele.")
        if caixa is None:
            caixa = _conhecimento_fixo(repo)
        evs = repo._req("GET", "tarefa_eventos", {"select": "autor,texto", "tarefa_id": repo._eq(tid), "order": "id"}) or []
        ia.USO["origem"] = f"card #{tid} ({resp})"
        try:
            chave = resp if resp in agentes.AGENTES else "chatgpt"
            txt = agentes.perguntar(chave, _pedido_card(t, evs, caixa), max_tokens=6000)
        except Exception as e:  # noqa: BLE001
            _evento(repo, tid, "sistema", f"{resp} não respondeu ({str(e)[:150]}); tenta na próxima hora.", tipo="status")
            repo._req("PATCH", "reuniao_tarefas", {"id": repo._eq(tid)}, corpo={"status": "aprovada"}, prefer="return=minimal")
            continue
        saida.append(entregar_card(repo, tid, resp, txt))
    return "; ".join(saida)

# Terminal do Mac: lista FECHADA (o Mac confere de novo do lado dele); nada vira comando livre
COMANDOS_MAC = {
    "status": "Status das coletas", "diario": "Rodar a coleta agora", "parar_coleta": "Parar a coleta em andamento",
    "atualizar": "Atualizar o coletor", "vigia_status": "Ver serviços do nubi (launchd)", "vigia_reativar": "Reativar o vigia",
    "log_vigia": "Últimas linhas do vigia", "log_coleta": "Últimas linhas da coleta",
    "hermes": "Hermes responder na Sala", "qwen": "Qwen revisar a Sala",
    "ollama_modelos": "Modelos do Ollama", "ollama_rodando": "Modelos carregados agora", "espaco": "Espaço em disco",
    "baixar_modelo": "Baixar modelo do Ollama", "estoque": "Atualizar o estoque do UpSeller agora",
    "gestor": "Importar a planilha no Gestor Seller", "hermes_card": "Hermes fazer um card (no Mac)",
    "entrar": "Abrir o login do Nubimetrics no Mac (você clica em Entrar)",
    "entrar_upseller": "Abrir o login do UpSeller no Mac", "entrar_gestor": "Abrir o login do Gestor Seller no Mac",
    "entrar_auto_nubimetrics": "Entrar sozinho no Nubimetrics",
    "entrar_auto_upseller": "Entrar sozinho no UpSeller (com o código do e-mail)",
    "entrar_auto_gestor": "Entrar sozinho no Gestor Seller",
    "ferreiro_status": "Ferreiro: conferir se está pronto (Claude Code, chave e git no Mac)",
    "programar_card": "Ferreiro programar um card agora (número do card)",
    "entrar_ml": "Mercado Livre: abrir a janela no Mac para passar pela verificação (você resolve o 'não sou um robô')",
    "ml_lojas": "Mercado Livre: achar os anúncios das minhas lojas", "ml_posicoes": "Mercado Livre: posição dos meus anúncios agora",
}
MODELOS_MAC = ("hermes3:8b", "qwen3:8b", "nomic-embed-text")


# ---------- Posição do anúncio no Mercado Livre (card #78, pedido do Bruno em 25/09) ----------
# O coletor do Mac (Chrome) acha os anúncios das minhas lojas (ml_lojas → meus_anuncios) e, toda semana, a posição e a
# página de cada um na busca do seu termo (anuncio_posicoes). 48 anúncios por página; patrocinado conta à parte.
ML_POR_PAGINA = 48
_ML_COMUNS = {"perfume", "perfumes", "original", "originais", "lacrado", "importado", "masculino", "feminino", "unissex",
              "arabe", "edp", "edt", "eau", "de", "parfum", "toilette", "para", "com", "da", "do", "e", "ml"}


def termo_padrao(titulo):
    """Termo de busca inicial de um anúncio: marca + nome do perfume + tamanho, sem as palavras de anúncio (o Bruno edita)."""
    t = nubi.sem_acento(str(titulo or "")).lower()
    vol = re.search(r"(\d{2,4})\s*ml", t)
    ps = [w for w in re.findall(r"[a-z0-9]+", re.sub(r"\d{2,4}\s*ml", " ", t)) if w not in _ML_COMUNS and not w.isdigit()]
    return " ".join(ps[:5] + ([vol.group(1) + "ml"] if vol else []))


def anuncio_do_link(link, loja=None):
    """Link de anúncio do ML (produto.mercadolivre…/MLB-123-…, /p/MLB… ou /up/MLBU…?pdp_filters=item_id:MLB…, wid=MLB…)
    → {id, titulo, link, termo, loja}. O título vem do próprio endereço (o Mac completa foto e preço depois)."""
    u = urllib.parse.unquote(urllib.parse.unquote(str(link or "").strip()))
    m = re.search(r"(?:item_id[:=]|wid=)(MLB-?\d{6,})", u) or re.search(r"/(MLB-\d{6,})", u) or re.search(r"\b(MLB\d{8,})\b", u)
    if not m:
        return None
    aid = m.group(1).replace("-", "").upper()
    caminho = urllib.parse.urlparse(u).path
    slug = next((p for p in caminho.split("/") if "-" in p and not p.upper().startswith("MLB")), "")
    if not slug:
        s2 = re.search(r"/MLB-\d+-([^/_?#]+)", caminho)
        slug = s2.group(1) if s2 else ""
    titulo = " ".join(w.capitalize() for w in slug.split("-") if w)[:200]
    limpo = link.split("#")[0]
    # anatomia do link (26/09, a pedido do Bruno): o que cada pedaço diz sobre o anúncio e de onde ele foi aberto
    up = re.search(r"/up/(MLBU\d+)", u)
    cat = re.search(r"/p/(MLB\d+)", u)
    frag = urllib.parse.parse_qs(urllib.parse.urlparse(u).fragment.replace("#", "&"))
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)
    pega = lambda k: (frag.get(k) or qs.get(k) or [None])[0]                     # noqa: E731
    sid, cli = pega("sid") or "", pega("polycard_client") or ""
    origem = ("vitrine" if sid == "storefronts" or "mshops" in cli else "busca" if sid == "search" or "search" in cli
              else "catalogo" if cat else "anuncio")
    contexto = {k: v for k, v in {"sid": sid or None, "polycard_client": cli or None, "componente": pega("component"),
                                  "vitrine_titulo": pega("title"), "posicao_no_carrossel": pega("global_position")}.items() if v}
    return {"id": aid, "titulo": titulo or aid, "link": limpo[:500], "termo": termo_padrao(titulo) if titulo else "",
            "loja": str(loja or "").strip().lower() or None, "user_product": up.group(1) if up else None,
            "catalogo": cat.group(1) if cat else None, "origem": origem, "contexto": contexto}


def posicoes_de_busca(termo, itens, meus_ids, data):
    """itens: resultados da busca na ordem da tela [{id, titulo, vendedor, patrocinado}] → linhas de anuncio_posicoes
    dos meus anúncios e dos 3 primeiros concorrentes orgânicos. Posição orgânica ignora os patrocinados."""
    linhas, org, vistos, concorrentes = [], 0, set(), 0
    for i, it in enumerate(itens, start=1):
        aid = str(it.get("id") or "").upper().replace("-", "")
        if not aid or aid in vistos:
            continue
        vistos.add(aid)
        patroc = bool(it.get("patrocinado"))
        if not patroc:
            org += 1
        meu = aid in meus_ids
        if meu or (not patroc and concorrentes < 3):
            concorrentes += 0 if meu else 1
            linhas.append({"data": data, "termo": termo, "anuncio_id": aid, "titulo": str(it.get("titulo") or "")[:200],
                           "vendedor": str(it.get("vendedor") or "")[:80], "meu": meu, "posicao": i,
                           "posicao_organica": None if patroc else org, "pagina": (i - 1) // ML_POR_PAGINA + 1,
                           "patrocinado": patroc})
    return linhas


# ---------- Laboratório de Rankeamento (pedido do Bruno, 26/09): a box onde todos os agentes juntam técnicas ----------
RANK_TIPOS = ("tecnica", "hipotese", "experimento", "resultado", "pergunta", "plano", "comentario")
RANK_STATUS = ("nova", "testando", "comprovada", "descartada")


def _rank_contexto(repo, n=40):
    """O que os agentes leem antes de contribuir: a box (sem os comentários) e a situação dos meus anúncios."""
    box = repo._req("GET", "rank_box", {"select": "id,tipo,titulo,texto,autor,status,fonte,anuncio_id,votos",
                                        "tipo": "neq.comentario", "order": "atualizado_em.desc", "limit": n}) or []
    an = repo._todos("meus_anuncios", {"select": "id,loja,titulo,preco,termo", "ativo": "is.true"})[:25]
    ps = repo._req("GET", "anuncio_posicoes", {"select": "data,termo,anuncio_id,titulo,vendedor,meu,posicao,posicao_organica,pagina,patrocinado",
                                                "order": "data.desc", "limit": 300}) or []
    ult = ps[0]["data"] if ps else None
    atual = {p["anuncio_id"]: p for p in ps if p["data"] == ult and p["meu"]}
    topo = {}
    for p in ps:
        if p["data"] == ult and not p["meu"]:
            topo.setdefault(p["termo"], []).append(p)
    linhas_box = "\n".join(f"#{b['id']} [{b['tipo']}/{b['status']}] {b['titulo']} — {str(b.get('texto') or '')[:220]} (por {b['autor']}"
                           f"{', fonte ' + b['fonte'] if b.get('fonte') else ''}{', votos ' + json.dumps(b['votos'], ensure_ascii=False) if b.get('votos') else ''})"
                           for b in box) or "(vazia)"
    linhas_an = "\n".join(f"{a['id']} ({a.get('loja')}) {a.get('titulo')} · R$ {a.get('preco') or '?'} · busca '{a.get('termo')}' · "
                          + (f"posição {atual[a['id']].get('posicao_organica') or atual[a['id']]['posicao']}, página {atual[a['id']]['pagina']}"
                             if a["id"] in atual else "posição ainda não medida / fora do top 144")
                          for a in an) or "(ainda sem anúncios meus cadastrados)"
    linhas_topo = "\n".join(f"'{t}': " + "; ".join(f"{x.get('posicao_organica') or x['posicao']}º {x.get('titulo')} ({x.get('vendedor')})" for x in xs[:3])
                            for t, xs in list(topo.items())[:10]) or "(sem medição ainda)"
    return box, an, f"BOX DE RANKEAMENTO (mais recentes):\n{linhas_box}\n\nMEUS ANÚNCIOS:\n{linhas_an}\n\nTOPO DAS BUSCAS:\n{linhas_topo}"


def _rank_gravar(repo, itens, autor, existentes):
    """Grava as contribuições novas (sem repetir título já na box); devolve quantas entraram."""
    vistos = {nubi.compacta(b["titulo"]) for b in existentes}
    regs = []
    for x in itens or []:
        if not isinstance(x, dict) or not str(x.get("titulo") or "").strip():
            continue
        k = nubi.compacta(x["titulo"])
        if k in vistos:
            continue
        vistos.add(k)
        tipo = x.get("tipo") if x.get("tipo") in RANK_TIPOS else "tecnica"
        regs.append({"tipo": tipo, "titulo": str(x["titulo"])[:200], "texto": str(x.get("texto") or "")[:3000], "autor": autor,
                     "fonte": str(x.get("fonte") or "")[:500] or None, "anuncio_id": (str(x.get("anuncio_id") or "").upper() or None)})
    if regs:
        repo._req("POST", "rank_box", corpo=regs, prefer="return=minimal")
    return len(regs)


def _rank_votar(repo, votos, autor):
    n = 0
    for v in votos or []:
        try:
            bid, val = int(v.get("id")), (1 if int(v.get("voto")) > 0 else -1)
        except (TypeError, ValueError, AttributeError):
            continue
        b = (repo._req("GET", "rank_box", {"select": "id,votos", "id": repo._eq(bid)}) or [None])[0]
        if not b:
            continue
        vs = dict(b.get("votos") or {})
        vs[autor] = val
        repo._req("PATCH", "rank_box", {"id": repo._eq(bid)}, corpo={"votos": vs}, prefer="return=minimal")
        if v.get("motivo"):
            repo._req("POST", "rank_box", corpo=[{"tipo": "comentario", "titulo": "voto", "texto": str(v["motivo"])[:600],
                                                  "autor": autor, "pai_id": bid}], prefer="return=minimal")
        n += 1
    return n


PEDIDO_RANK = ("Você está no LABORATÓRIO DE RANKEAMENTO do nubi: o objetivo do Bruno é entender o algoritmo de busca do Mercado Livre "
               "(relevância, conversão, vendas recentes, preço, frete/Full, reputação e MercadoLíder, qualidade do anúncio, fotos, ficha "
               "técnica/atributos, catálogo, tags como 'Mais vendido', 'Oferta do dia', 'Full', 'Loja oficial', 'Recomendado', anúncio "
               "patrocinado/Mercado Ads, perguntas respondidas, reclamações) para fazer os anúncios DELE subirem de posição e vender mais. "
               "Todos os agentes trabalham juntos na mesma box: leia o que os outros já escreveram, NÃO repita, complemente, discorde com "
               "argumento e vote. Não invente números nem regras do ML: o que for suposição é 'hipotese'; o que tem fonte, ponha o link; "
               "o que dá para testar num anúncio, proponha como 'experimento' (o que mudar, em qual anúncio, o que medir e por quantos dias).\n\n")


def laboratorio_rankeamento(repo, forcar=False):
    """Rotina 'rankeamento' (todo dia): pesquisador com web → agentes contribuem e votam → coordenador fecha status e plano."""
    if not ia.disponivel():
        return "sem chave de IA"
    hoje = _agora_br().date().isoformat()
    if not forcar and repo._req("GET", "rank_box", {"select": "id", "tipo": "eq.plano", "autor": "eq.Claude",
                                                    "criado_em": f"gte.{hoje}T03:00:00+00:00", "limit": 1}):
        return "já feito hoje"
    box, _, ctx = _rank_contexto(repo)
    feitos = []
    # 1) pesquisador: técnicas com fonte real
    try:
        j, _, _ = ia.perguntar_json(PEDIDO_RANK + ctx + "\n\nVocê é o PESQUISADOR. Pesquise na web (central do vendedor do Mercado Livre, "
                                    "Mercado Livre Developers, blogs e cursos de vendedores sérios) e traga até 3 técnicas NOVAS (que não estão na box) "
                                    "sobre como o ML ranqueia e expõe anúncios, cada uma com link. Responda SÓ JSON: "
                                    '{"contribuicoes": [{"tipo": "tecnica", "titulo": "...", "texto": "o que é e como aplicar nos anúncios do Bruno", "fonte": "https://..."}]}',
                                    web=True, max_tokens=2500, qual="claude", sistema=agentes.SISTEMA)
        n = _rank_gravar(repo, j.get("contribuicoes"), "Claude (pesquisa)", box)
        feitos.append(f"pesquisa {n}")
    except Exception as e:  # noqa: BLE001
        feitos.append(f"pesquisa falhou ({str(e)[:80]})")
    # 2) cada agente contribui (com o jeito dele) e vota nas ideias dos outros
    for chave in agentes.ativos():
        nome = agentes.AGENTES[chave]["nome"]
        box, _, ctx = _rank_contexto(repo)
        try:
            t = agentes.perguntar(chave, PEDIDO_RANK + ctx + "\n\nSua vez: traga no máximo 2 contribuições NOVAS (técnica, hipótese, experimento "
                                  "num anúncio específico do Bruno com o ID MLB, ou pergunta) e vote em até 4 itens da box (+1 concorda, -1 discorda, "
                                  "com motivo curto). Responda SÓ JSON: {\"contribuicoes\": [{\"tipo\": \"tecnica|hipotese|experimento|pergunta\", "
                                  "\"titulo\": \"...\", \"texto\": \"...\", \"anuncio_id\": \"MLB... ou vazio\", \"fonte\": \"link ou vazio\"}], "
                                  "\"votos\": [{\"id\": 12, \"voto\": 1, \"motivo\": \"...\"}]}", max_tokens=1800,
                                  arquivo=agentes.arquivo_de(repo))
            j = ia._primeiro_json(t)
            n = _rank_gravar(repo, j.get("contribuicoes"), nome, box)
            v = _rank_votar(repo, j.get("votos"), nome)
            feitos.append(f"{nome} {n}+{v}v")
        except Exception as e:  # noqa: BLE001
            feitos.append(f"{nome} falhou ({str(e)[:60]})")
    # 3) coordenador: status das ideias e o plano de ação de cada anúncio
    box, an, ctx = _rank_contexto(repo, n=60)
    try:
        j, _, _ = ia.perguntar_json(PEDIDO_RANK + ctx + "\n\nVocê é o COORDENADOR. Com o que o time escreveu e votou: (a) atualize o status "
                                    "(nova/testando/comprovada/descartada) de até 8 itens — 'comprovada' só com fonte oficial ou resultado medido "
                                    "nas posições; (b) escreva o PLANO DE AÇÃO de hoje: as 5 ações de maior impacto, cada uma dizendo em qual "
                                    "anúncio (ID MLB) ou 'todos', o que fazer e como vamos medir. Responda SÓ JSON: "
                                    '{"status": [{"id": 3, "status": "testando", "motivo": "..."}], "plano": "markdown curto em português", '
                                    '"resumo_sala": "3 linhas para a Sala"}', web=False, max_tokens=2500, qual="claude", sistema=agentes.SISTEMA)
        ids = {b["id"] for b in box}
        for x in j.get("status") or []:
            try:
                bid = int(x.get("id"))
            except (TypeError, ValueError):
                continue
            if bid in ids and x.get("status") in RANK_STATUS:
                repo._req("PATCH", "rank_box", {"id": repo._eq(bid)}, corpo={"status": x["status"], "atualizado_em": datetime.now(timezone.utc).isoformat()},
                          prefer="return=minimal")
                if x.get("motivo"):
                    repo._req("POST", "rank_box", corpo=[{"tipo": "comentario", "titulo": "status", "texto": f"→ {x['status']}: {str(x['motivo'])[:500]}",
                                                          "autor": "Claude", "pai_id": bid}], prefer="return=minimal")
        if j.get("plano"):
            repo._req("POST", "rank_box", corpo=[{"tipo": "plano", "titulo": f"Plano de ação de {hoje[8:10]}/{hoje[5:7]}", "texto": str(j["plano"])[:6000],
                                                  "autor": "Claude", "status": "testando"}], prefer="return=minimal")
        if j.get("resumo_sala"):
            repo._req("POST", "reuniao_mensagens", corpo=[{"autor": "Claude", "texto": "🧪 **Laboratório de Rankeamento**\n" + str(j["resumo_sala"])[:1500]
                                                           + "\n(Minhas Lojas → 🧪 Rankeamento)"}], prefer="return=minimal")
        feitos.append("plano ok")
    except Exception as e:  # noqa: BLE001
        feitos.append(f"coordenador falhou ({str(e)[:80]})")
    return "; ".join(feitos)[:300]


def rota_posicoes(repo, metodo, rota, q, corpo):
    d = json.loads(corpo or b"{}") if metodo == "POST" else {}
    agora_ = datetime.now(timezone.utc).isoformat()
    if rota == "ml_config":
        # para o coletor: as lojas e os termos de busca de cada anúncio meu
        lojas = repo._todos("ml_lojas", {"select": "nome,url", "ativo": "is.true"})
        an = repo._todos("meus_anuncios", {"select": "id,titulo,termo", "ativo": "is.true"})
        termos = sorted({(a.get("termo") or "").strip() for a in an if (a.get("termo") or "").strip()})
        # dica do Bruno (26/09): as lojas se acham buscando os MEUS produtos (os do estoque do UpSeller com mais valor)
        buscas = []
        try:
            at = (repo._req("GET", "estoque_atualizacoes", {"select": "id", "order": "id.desc", "limit": 1}) or [None])[0]
            if at:
                its = repo._todos("estoque_itens", {"select": "titulo,atual,subtotal", "atualizacao_id": repo._eq(at["id"])})
                its = sorted((i for i in its if (i.get("atual") or 0) > 0 and i.get("titulo")), key=lambda i: -(i.get("subtotal") or 0))
                for i in its:
                    t = termo_padrao(i["titulo"])
                    if t and t not in buscas:
                        buscas.append(t)
                    if len(buscas) >= 15:
                        break
        except ErroNuvem:
            pass
        sem_loja = [x for x in repo._todos("meus_anuncios", {"select": "id,link,titulo", "ativo": "is.true", "loja": "is.null"}) if x.get("link")]
        return {"lojas": lojas, "anuncios": an, "termos": termos, "buscas_produtos": buscas, "sem_loja": sem_loja,
                "por_pagina": ML_POR_PAGINA}
    if rota == "ml_anuncios_gravar" and metodo == "POST":
        # o coletor achou os anúncios de uma loja: grava (sem apagar o termo que o Bruno editou)
        loja = str(d.get("loja") or "").strip().lower()
        ja = {a["id"]: a for a in repo._todos("meus_anuncios", {"select": "id,termo"})}
        regs = []
        for x in d.get("anuncios") or []:
            aid = str(x.get("id") or "").upper().replace("-", "")
            if not re.fullmatch(r"MLB\d{6,}", aid):
                continue
            regs.append({"id": aid, "loja": loja, "titulo": str(x.get("titulo") or "")[:200],
                         "preco": x.get("preco") if isinstance(x.get("preco"), (int, float)) else None,
                         "link": str(x.get("link") or "")[:500], "foto": str(x.get("foto") or "")[:500],
                         "termo": (ja.get(aid) or {}).get("termo") or termo_padrao(x.get("titulo")), "visto_em": agora_})
        for i in range(0, len(regs), 200):
            repo._req("POST", "meus_anuncios", corpo=regs[i:i + 200], prefer="resolution=merge-duplicates,return=minimal")
        if loja:
            repo._req("PATCH", "ml_lojas", {"nome": repo._eq(loja)},
                      corpo={"achado_em": agora_, "url": str(d.get("url") or "")[:500] or None,
                             "obs": f"{len(regs)} anúncio(s) achado(s)" if regs else str(d.get("obs") or "nenhum anúncio achado")[:300]},
                      prefer="return=minimal")
        return {"ok": True, "gravados": len(regs)}
    if rota == "ml_anuncio_completar" and metodo == "POST":
        # o Mac abriu o anúncio e leu o vendedor, a foto e o preço (anúncio colado pelo Bruno sem loja)
        aid = str(d.get("id") or "").upper()
        vend = str(d.get("vendedor") or "").strip()
        mud = {"visto_em": agora_}
        if d.get("vendedor_id"):
            mud["vendedor_id"] = str(d["vendedor_id"])[:40]
        if vend:
            mud["vendedor"] = vend[:80]
            mud["loja"] = vend.lower()[:80]
            if not repo._req("GET", "ml_lojas", {"select": "nome", "nome": repo._eq(mud["loja"])}):
                repo._req("POST", "ml_lojas", corpo=[{"nome": mud["loja"], "ativo": True, "obs": "achada pelo anúncio " + aid}],
                          prefer="resolution=merge-duplicates,return=minimal")
        for k in ("titulo", "foto"):
            if d.get(k):
                mud[k] = str(d[k])[:500 if k == "foto" else 200]
        if isinstance(d.get("preco"), (int, float)) and d["preco"] > 0:
            mud["preco"] = d["preco"]
        repo._req("PATCH", "meus_anuncios", {"id": repo._eq(aid)}, corpo=mud, prefer="return=minimal")
        return {"ok": True, "loja": mud.get("loja")}
    if rota == "ml_posicoes_gravar" and metodo == "POST":
        termo = str(d.get("termo") or "").strip()
        meus = {a["id"] for a in repo._todos("meus_anuncios", {"select": "id"})}
        linhas = posicoes_de_busca(termo, d.get("itens") or [], meus, _agora_br().date().isoformat())
        if linhas:
            repo._req("DELETE", "anuncio_posicoes", {"termo": repo._eq(termo), "data": repo._eq(linhas[0]["data"])})
            repo._req("POST", "anuncio_posicoes", corpo=linhas, prefer="return=minimal")
        return {"ok": True, "linhas": len(linhas), "meus": sum(1 for x in linhas if x["meu"])}
    if rota == "ml_posicoes_pendente":
        rot = (repo._req("GET", "rotinas", {"select": "*", "id": "eq.posicoes"}) or [None])[0]
        agora = _agora_br()
        ult = (repo._req("GET", "anuncio_posicoes", {"select": "data", "order": "data.desc", "limit": 1}) or [None])[0]
        hoje_ok = bool(ult and str(ult["data"])[:10] == agora.date().isoformat())
        na_hora = bool(rot and rot.get("ativo") and rotina_no_dia(rot, agora) and agora.strftime("%H:%M") >= (rot.get("horario") or "07:30"))
        return {"rodar": na_hora and not hoje_ok, "horario": (rot or {}).get("horario")}
    if rota == "posicoes":
        lojas = repo._todos("ml_lojas", {"select": "*", "order": "nome"})
        an = repo._todos("meus_anuncios", {"select": "*", "order": "loja,titulo"})
        desde = (_agora_br().date() - timedelta(days=70)).isoformat()
        ps = repo._todos("anuncio_posicoes", {"select": "data,termo,anuncio_id,titulo,vendedor,meu,posicao,posicao_organica,pagina,patrocinado",
                                              "data": f"gte.{desde}", "order": "data.desc"})
        hist = {}
        for p in ps:
            hist.setdefault((p["anuncio_id"], p["termo"]), []).append(p)
        for a in an:
            h = hist.get((a["id"], (a.get("termo") or "").strip())) or []
            a["atual"] = h[0] if h else None
            ant = next((x for x in h[1:] if str(x["data"]) <= str((date.fromisoformat(str(h[0]["data"])[:10]) - timedelta(days=6)))), None) if h else None
            a["anterior"] = ant
            a["serie"] = [{"data": x["data"], "posicao": x["posicao_organica"] or x["posicao"], "pagina": x["pagina"]} for x in reversed(h[:8])]
        ult_data = ps[0]["data"] if ps else None
        concorrentes = {}
        for p in ps:
            if p["data"] == ult_data and not p["meu"]:
                concorrentes.setdefault(p["termo"], []).append(p)
        rot = (repo._req("GET", "rotinas", {"select": "horario,dias_semana,ativo,ultima_execucao", "id": "eq.posicoes"}) or [None])[0]
        pedido = (repo._req("GET", "mac_comandos", {"select": "comando,status,criado_em", "comando": "in.(ml_lojas,ml_posicoes)",
                                                    "order": "id.desc", "limit": 2}) or [])
        return {"lojas": lojas, "anuncios": an, "ultima_data": ult_data, "concorrentes": concorrentes, "rotina": rot,
                "pedidos": pedido, "por_pagina": ML_POR_PAGINA}
    if rota == "ml_loja_salvar" and metodo == "POST":
        nome = str(d.get("nome") or "").strip().lower()
        if not nome:
            raise ErroNuvem("Nome da loja vazio.")
        if d.get("remover"):
            repo._req("PATCH", "ml_lojas", {"nome": repo._eq(nome)}, corpo={"ativo": False}, prefer="return=minimal")
        else:
            repo._req("POST", "ml_lojas", corpo=[{"nome": nome, "ativo": True}], prefer="resolution=merge-duplicates,return=minimal")
        return {"ok": True}
    if rota == "ml_anuncio_link" and metodo == "POST":
        # o Bruno cola o link de um anúncio dele (26/09): tira o código (item_id/wid) e o título do próprio link
        a = anuncio_do_link(d.get("link"), d.get("loja"))
        if not a:
            raise ErroNuvem("Não achei o código do anúncio (MLB…) nesse link.")
        ja = (repo._req("GET", "meus_anuncios", {"select": "id,termo,loja", "id": repo._eq(a["id"])}) or [None])[0]
        if ja:
            a["termo"], a["loja"] = ja.get("termo") or a["termo"], a["loja"] or ja.get("loja")
        repo._req("POST", "meus_anuncios", corpo=[dict(a, visto_em=agora_, ativo=True)], prefer="resolution=merge-duplicates,return=minimal")
        return {"ok": True, "anuncio": a}
    if rota == "ml_anuncio_salvar" and metodo == "POST":
        aid = str(d.get("id") or "").upper()
        mud = {k: d[k] for k in ("termo", "ativo") if k in d}
        if "termo" in mud:
            mud["termo"] = str(mud["termo"] or "").strip()[:120]
        repo._req("PATCH", "meus_anuncios", {"id": repo._eq(aid)}, corpo=mud, prefer="return=minimal")
        return {"ok": True}
    if rota == "rank_box":
        todos = repo._todos("rank_box", {"select": "*", "order": "atualizado_em.desc"})
        coment = {}
        for b in todos:
            if b["tipo"] == "comentario" and b.get("pai_id"):
                coment.setdefault(b["pai_id"], []).append(b)
        itens = [dict(b, comentarios=sorted(coment.get(b["id"], []), key=lambda c: c["criado_em"])) for b in todos if b["tipo"] != "comentario"]
        plano = next((b for b in itens if b["tipo"] == "plano"), None)
        an = repo._todos("meus_anuncios", {"select": "id,titulo,loja", "ativo": "is.true"})
        rot = (repo._req("GET", "rotinas", {"select": "horario,ativo,ultima_execucao,ultimo_resultado", "id": "eq.rankeamento"}) or [None])[0]
        return {"itens": [b for b in itens if b["tipo"] != "plano"], "plano": plano, "anuncios": an, "rotina": rot}
    if rota == "rank_salvar" and metodo == "POST":
        # o Bruno escreve na box (técnica, pergunta, resultado) ou comenta/muda o status de um item
        if d.get("id"):
            mud = {k: d[k] for k in ("status",) if d.get(k) in RANK_STATUS}
            if mud:
                mud["atualizado_em"] = agora_
                repo._req("PATCH", "rank_box", {"id": repo._eq(int(d["id"]))}, corpo=mud, prefer="return=minimal")
            if str(d.get("comentario") or "").strip():
                repo._req("POST", "rank_box", corpo=[{"tipo": "comentario", "titulo": "comentário", "texto": str(d["comentario"])[:2000],
                                                      "autor": "Bruno", "pai_id": int(d["id"])}], prefer="return=minimal")
                repo._req("PATCH", "rank_box", {"id": repo._eq(int(d["id"]))}, corpo={"atualizado_em": agora_}, prefer="return=minimal")
            return {"ok": True}
        tit = str(d.get("titulo") or "").strip()
        if not tit:
            raise ErroNuvem("Escreva um título.")
        repo._req("POST", "rank_box", corpo=[{"tipo": d.get("tipo") if d.get("tipo") in RANK_TIPOS else "tecnica", "titulo": tit[:200],
                                              "texto": str(d.get("texto") or "")[:4000], "autor": "Bruno", "fonte": str(d.get("fonte") or "")[:500] or None,
                                              "anuncio_id": str(d.get("anuncio_id") or "").upper() or None}], prefer="return=minimal")
        return {"ok": True}
    if rota == "rank_rodar" and metodo == "POST":
        return {"ok": True, "resultado": laboratorio_rankeamento(repo, forcar=True)}
    if rota == "ml_pedir" and metodo == "POST":
        k = "ml_lojas" if d.get("o_que") == "lojas" else "ml_posicoes"
        pend = repo._req("GET", "mac_comandos", {"select": "id", "comando": repo._eq(k), "status": "in.(pendente,rodando)", "limit": 1}) or []
        if not pend:
            repo._req("POST", "mac_comandos", corpo=[{"comando": k, "arg": "", "status": "pendente", "pedido_por": "Bruno"}],
                      prefer="return=minimal")
        return {"ok": True, "ja_havia": bool(pend)}
    raise ErroNuvem("Rota desconhecida.", 404)


def reuniao_nao_lidas(repo):
    """Última mensagem de cada conversa da Sala + quantas não lidas (pedido do Bruno, 26/09: igual ao WhatsApp)."""
    out, nao, lido = {}, {}, {}
    try:
        lido = {r["conversa"]: int(r["ultimo_id"] or 0) for r in repo._todos("reuniao_leituras", {"select": "conversa,ultimo_id"})}
    except ErroNuvem:
        lido = {}
    for chave in ("sala",) + tuple(CONVERSA_NOME):
        p = {"select": "id,autor,texto,criado_em", "order": "id.desc", "limit": 1}
        if chave == "sala":
            p["or"] = "(meta.is.null,meta->>conversa.neq.direta)"
        else:
            p["meta->>conversa"] = "eq.direta"
            p["meta->>agente"] = f"eq.{chave}"
        ult = repo._req("GET", "reuniao_mensagens", p)
        out[chave] = ult[0] if ult else None
        if ult and ult[0]["id"] > lido.get(chave, 0):
            q2 = dict(p, select="id", limit=100, id=f"gt.{lido.get(chave, 0)}", autor="neq.voce")
            nao[chave] = len(repo._req("GET", "reuniao_mensagens", q2) or [])
    return out, nao, lido


def rota_mac(repo, metodo, rota, q, corpo, token):
    d = json.loads(corpo or b"{}") if metodo == "POST" else {}
    agora_ = datetime.now(timezone.utc).isoformat()
    if rota == "mac_painel":
        est = (repo._req("GET", "mac_estado", {"select": "*", "id": "eq.1"}) or [None])[0]
        cmds = repo._req("GET", "mac_comandos", {"select": "*", "order": "id.desc", "limit": int(q.get("n") or 25)}) or []
        online = bool(est and est.get("visto_em") and _br(est["visto_em"]) > _br(agora_) - timedelta(minutes=3))
        return {"estado": est, "online": online, "comandos": cmds,
                "lista": [{"k": k, "nome": v} for k, v in COMANDOS_MAC.items()], "modelos": MODELOS_MAC}
    if rota == "mac_pedir" and metodo == "POST":
        k, arg = str(d.get("comando") or ""), str(d.get("arg") or "")
        msg = None
        if k not in COMANDOS_MAC:
            msg = "Comando fora da lista permitida."
        elif k == "baixar_modelo" and arg not in MODELOS_MAC:
            msg = "Modelo fora da lista permitida."
        elif k == "hermes_card" and not arg.isdigit():
            msg = "Informe o número do card."
        if msg:
            repo._req("POST", "mac_comandos", corpo=[{"comando": k[:60] or "?", "arg": arg[:60] or None,
                                                       "pedido_por": "Bruno", "status": "recusado", "criado_em": agora_,
                                                       "fim": agora_, "saida": msg}], prefer="return=minimal")
            raise ErroNuvem(msg)
        quem = "Bruno"
        r = repo._req("POST", "mac_comandos", corpo=[{"comando": k, "arg": arg or None, "pedido_por": quem, "status": "pendente",
                                                      "criado_em": agora_}], prefer="return=representation")
        return {"ok": True, "id": (r or [{}])[0].get("id")}
    if rota == "mac_comando":
        return (repo._req("GET", "mac_comandos", {"select": "*", "id": repo._eq(int(q.get("id") or 0))}) or [None])[0] or {}
    if rota == "mac_tick" and metodo == "POST":
        # o Mac: estado + saídas dos comandos em andamento; recebe os pendentes e as mensagens novas da Sala
        if d.get("info") is not None:
            repo._req("POST", "mac_estado", corpo=[{"id": 1, "visto_em": agora_, "info": d["info"]}],
                      prefer="resolution=merge-duplicates,return=minimal")
        for sd in d.get("saidas") or []:
            reg = {"saida": str(sd.get("saida") or "")[-12000:], "status": sd.get("status") or "rodando"}
            if reg["status"] in ("ok", "erro", "recusado"):
                reg["fim"] = agora_
            repo._req("PATCH", "mac_comandos", {"id": repo._eq(int(sd["id"]))}, corpo=reg, prefer="return=minimal")
            if reg["status"] in ("ok", "erro", "recusado"):
                # comando pedido pelo agente de um card: a saída volta para o card
                c = (repo._req("GET", "mac_comandos", {"select": "comando,tarefa_id", "id": repo._eq(int(sd["id"]))}) or [{}])[0]
                if c.get("tarefa_id"):
                    ic = {"ok": "✅", "erro": "⚠️", "recusado": "⛔"}[reg["status"]]
                    fim = reg["saida"].strip()[-1500:] or "(sem saída)"
                    repo._req("POST", "tarefa_eventos", corpo=[{"tarefa_id": c["tarefa_id"], "autor": "mac", "tipo": "passo", "criado_em": agora_,
                                                                "texto": f"{ic} Mac terminou **{COMANDOS_MAC.get(c['comando'], c['comando'])}**:\n```\n{fim}\n```"}],
                              prefer="return=minimal")
        pend = []
        if d.get("info") is not None:
            pend = repo._req("GET", "mac_comandos", {"select": "id,comando,arg", "status": "eq.pendente", "order": "id", "limit": 3}) or []
            for p in pend:
                repo._req("PATCH", "mac_comandos", {"id": repo._eq(p["id"])}, corpo={"status": "rodando", "iniciado_em": agora_},
                          prefer="return=minimal")
        ult = int(d.get("sala_ult") or 0)
        sala = []
        if d.get("info") is not None:
            if not ult:          # primeira vez: começa do fim (não responde ao histórico)
                u = repo._req("GET", "reuniao_mensagens", {"select": "id", "order": "id.desc", "limit": 1}) or []
                sala = [{"id": u[0]["id"], "texto": ""}] if u else []
            else:
                sala = repo._req("GET", "reuniao_mensagens", {"select": "id,autor,texto,criado_em", "id": f"gt.{ult}", "order": "id",
                                                               "autor": "in.(voce,sistema)", "limit": 20}) or []
                if not sala:
                    u = repo._req("GET", "reuniao_mensagens", {"select": "id", "order": "id.desc", "limit": 1}) or []
                    sala = [{"id": u[0]["id"], "texto": ""}] if u and u[0]["id"] > ult else []
        return {"pendentes": pend, "sala": sala}
    raise ErroNuvem("Rota desconhecida.", 404)


def rota_agentes(repo, metodo, rota, q, corpo):
    d = json.loads(corpo or b"{}") if metodo == "POST" else {}
    if rota == "agentes":
        return _agentes_painel(repo)
    if rota == "agentes_testar" and metodo == "POST":
        aid = d.get("id") or ""
        if aid not in AGENTE_QUAL:
            raise ErroNuvem("Este agente roda fora do servidor: o Hermes testa no Mac (coletor hermes) e o Claude (código) "
                            "na sessão de código.")
        ia.USO["origem"] = "teste (aba Agentes)"
        t0 = time.monotonic()
        try:
            txt, _, _ = _perguntar_agente(aid, "Teste de funcionamento do nubi. Responda em uma linha, em português: "
                                               "'OK' e o nome exato do seu modelo/versão.", 400)
            ok, erro = bool(txt.strip()), None
        except Exception as e:  # noqa: BLE001
            txt, ok, erro = "", False, str(e)[:300]
        ult = (repo._req("GET", "agentes_uso", {"select": "modelo,tokens_in,tokens_out,custo_usd", "agente": f"eq.{aid}",
                                                 "order": "id.desc", "limit": 1}) or [{}])[0]
        res = {"ok": ok, "resposta": txt[:400], "erro": erro, "ms": int((time.monotonic() - t0) * 1000),
               "modelo_api": ult.get("modelo"), "quando": datetime.now(timezone.utc).isoformat()}
        repo._req("PATCH", "agentes", {"id": f"eq.{aid}"}, corpo={"ultimo_teste": res}, prefer="return=minimal")
        return res
    if rota == "agentes_apelido" and metodo == "POST":
        aid = d.get("id") or ""
        apelido = str(d.get("apelido") or "").strip()
        if d.get("pedir"):
            if aid not in AGENTE_QUAL:
                raise ErroNuvem("O Hermes escolhe o apelido dele na próxima vez que rodar no Mac (coletor hermes).")
            ag = (repo._req("GET", "agentes", {"select": "nome,papel", "id": f"eq.{aid}"}) or [{}])[0]
            ia.USO["origem"] = "apelido (aba Agentes)"
            txt, _, _ = _perguntar_agente(aid, f"Você é o {ag.get('nome')} no time de agentes de IA do nubi ({ag.get('papel')}). "
                                               "Escolha um apelido curto para você no time (1 ou 2 palavras, em português, "
                                               "criativo e profissional). Responda SOMENTE o apelido, sem aspas.", 200)
            apelido = re.sub(r"[\"'*_`]", "", txt.strip().splitlines()[0] if txt.strip() else "").strip()[:30]
        if not apelido:
            raise ErroNuvem("Apelido vazio.")
        repo._req("PATCH", "agentes", {"id": f"eq.{aid}"}, corpo={"apelido": apelido,
                  "atualizado_em": datetime.now(timezone.utc).isoformat()}, prefer="return=minimal")
        return {"ok": True, "apelido": apelido}
    if rota == "agentes_preco" and metodo == "POST":
        modelo = str(d.get("modelo") or "").strip()
        if not modelo:
            raise ErroNuvem("Informe o modelo.")
        num = lambda v: None if v in (None, "") else float(str(v).replace(",", "."))
        repo._req("POST", "ia_precos", corpo=[{"modelo": modelo, "entrada": num(d.get("entrada")), "saida": num(d.get("saida")),
                                               "obs": str(d.get("obs") or "")[:200]}],
                  prefer="resolution=merge-duplicates,return=minimal")
        return {"ok": True}
    raise ErroNuvem("Rota desconhecida.", 404)


def rota_rotinas(repo, metodo, rota, q, corpo):
    if rota == "rotinas":
        rs = repo._todos("rotinas", {"select": "*", "order": "ordem,id"})
        ag = _agora_br()
        for r in rs:
            r["automatica"] = r["id"] in NO_SERVIDOR or r["id"] in NO_MAC
            r["pendente"] = r["id"] in NO_SERVIDOR and rotina_pendente(r, ag)
        return {"rotinas": rs, "agora": ag.strftime("%Y-%m-%d %H:%M"), "dias": DIAS_SEM}
    if rota == "ops_execucoes":
        return {"execucoes": _ops_execucoes(repo, int(q.get("dias") or 14))}
    if rota == "ops_erros":
        return {"erros": _ops_erros(repo)}
    if rota == "ops_resumo":
        ex, er = _ops_execucoes(repo, 1), _ops_erros(repo)
        hoje = _agora_br().date().isoformat()
        return {"erros_hoje": sum(1 for e in er if _br(e["inicio"]).date().isoformat() == hoje),
                "aprovadas": len(repo._req("GET", "reuniao_tarefas", {"select": "id", "status": "eq.aprovada"}) or []),
                "rodando": sum(1 for e in ex if e.get("em_andamento")),
                "sala_nao_lidas": sum(reuniao_nao_lidas(repo)[1].values())}
    if rota == "rotina_salvar" and metodo == "POST":
        d = json.loads(corpo or b"{}")
        reg = {k: d[k] for k in CAMPOS_ROTINA if k in d}
        if "horario" in reg and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(reg["horario"])):
            raise ErroNuvem("Horário no formato HH:MM (ex.: 08:00).")
        if "dias_semana" in reg:
            reg["dias_semana"] = [x for x in DIAS_SEM if x in (reg["dias_semana"] or [])]
        if "dia_mes" in reg:
            reg["dia_mes"] = int(reg["dia_mes"]) if reg["dia_mes"] not in (None, "", 0, "0") else None
            if reg["dia_mes"] is not None and not 1 <= reg["dia_mes"] <= 28:
                raise ErroNuvem("Dia do mês de 1 a 28.")
        if "nome" in reg and not str(reg["nome"]).strip():
            raise ErroNuvem("Dê um nome para a tarefa.")
        reg["atualizado_em"] = datetime.now(timezone.utc).isoformat()
        if d.get("id"):
            repo._req("PATCH", "rotinas", {"id": repo._eq(d["id"])}, corpo=reg, prefer="return=minimal")
            return {"ok": True, "id": d["id"]}
        reg.setdefault("responsavel", "Você")
        reg.setdefault("nome", "Nova tarefa")
        reg["id"] = "t" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        reg.setdefault("ordem", 100)
        repo._req("POST", "rotinas", corpo=[reg], prefer="return=minimal")
        return {"ok": True, "id": reg["id"]}
    if rota == "rotina_apagar" and metodo == "POST":
        rid = json.loads(corpo or b"{}").get("id") or ""
        if rid in NO_SERVIDOR or rid in NO_MAC:
            raise ErroNuvem("As tarefas do sistema não podem ser apagadas; desligue-a (Ativa) se não quiser que rode.")
        repo._req("DELETE", "rotinas", {"id": repo._eq(rid)})
        return {"ok": True}
    if rota == "rotina_rodar" and metodo == "POST":
        rid = json.loads(corpo or b"{}").get("id") or ""
        if rid not in NO_SERVIDOR:
            raise ErroNuvem("Esta tarefa não roda no servidor (a coleta roda no Mac mini).")
        return {"ok": True, "resultado": rodar_rotinas(repo, so=rid).get(rid, "")}
    raise ErroNuvem("Rota desconhecida.", 404)


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
        cat = q["categoria"]
        ap = apelidos(repo)
        chave = ap.get(nubi.compacta(q["marca"]), (nubi.compacta(q["marca"]), None))[0]
        grafias = sorted({chave} | {a for a, (c, _) in ap.items() if c == chave})
        rels = {r["id"]: r for r in _relatorios(repo, cat)}
        if not rels:
            return {"historico": []}
        ids = ",".join(str(i) for i in rels)
        linhas = unificar_marcas(repo, repo._todos("ranking_linhas", {
            "select": "*", "marca_chave": f"in.({','.join(grafias)})",
            "relatorio_id": f"in.({ids})", "order": "relatorio_id"}), somar=True)
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
        linhas = unificar_marcas(repo, repo._todos("ranking_linhas", {
            "select": "relatorio_id,posicao,variacao,marca,marca_chave,vendas,unidades,tendencia,catalogo,"
                      "vendedores,saturacao,ranking_demanda",
            "relatorio_id": f"in.({ids})", "order": "relatorio_id,posicao"}), somar=True)
        por_rel = {r["id"]: [] for r in rels}
        for l in linhas:
            por_rel[l["relatorio_id"]].append(l)
        todos = _relatorios(repo, cat)
        r = ranking.bi([x["mes"] for x in rels], [por_rel[x["id"]] for x in rels], repo.marcas())
        r.update({"categoria": cat, "categoria_nome": ranking.nome_categoria(cat),
                  "todos_meses": [{"mes": x["mes"][:7], "nome": ranking.nome_mes(x["mes"])} for x in todos]})
        return r

    if rota == "ranking_categorias":
        # Designer, Nicho, Árabe, Nacional e Outros: vendas e fatia de cada categoria mês a mês
        cat = q["categoria"]
        rels = _relatorios(repo, cat)
        if not rels:
            raise ErroNuvem("Nenhum relatório importado para esta categoria.", 404)
        ids = ",".join(str(r["id"]) for r in rels)
        linhas = unificar_marcas(repo, repo._todos("ranking_linhas", {
            "select": "relatorio_id,posicao,marca,marca_chave,vendas,unidades", "relatorio_id": f"in.({ids})",
            "order": "relatorio_id,posicao"}), somar=True)
        por_rel = {r["id"]: [] for r in rels}
        for l in linhas:
            por_rel[l["relatorio_id"]].append(l)
        manuais = {r["marca_chave"]: r["categoria"] for r in repo._todos("marca_categorias", {"select": "marca_chave,categoria"})}
        r = categorias.relatorio([x["mes"] for x in rels], [por_rel[x["id"]] for x in rels], manuais)
        r.update({"categoria": cat, "categoria_nome": ranking.nome_categoria(cat), "opcoes": categorias.CATEGORIAS})
        try:
            sug = {x["marca_chave"]: x for x in repo._todos("marca_sugestoes", {"select": "*", "estado": "eq.nova"})}
        except ErroNuvem:
            sug = {}
        r["sugestoes"] = [dict(sug[nubi.compacta(m["marca"])], atual=m["categoria"], ultimo=m.get("ultimo"))
                          for m in r["marcas"] if nubi.compacta(m["marca"]) in sug and m.get("fonte") != "manual"
                          and sug[nubi.compacta(m["marca"])]["categoria"] != m["categoria"]]
        return r

    if rota == "ranking_sugestao_ignorar" and metodo == "POST":
        k = json.loads(corpo or b"{}").get("marca_chave") or ""
        repo._req("PATCH", "marca_sugestoes", {"marca_chave": repo._eq(k)}, corpo={"estado": "ignorada"}, prefer="return=minimal")
        return {"ok": True}

    if rota == "ranking_categoria_pesquisar" and metodo == "POST":
        # sugere a categoria: país do código de barras dos produtos da marca + internet + preço médio
        d = json.loads(corpo or b"{}")
        marca = (d.get("marca") or "").strip()
        if not marca:
            raise ErroNuvem("Informe a marca.")
        gtins = [r["gtin"] for r in repo._req("GET", "vend_anuncios", {"select": "gtin", "marca": repo._eq(marca),
                                                                        "gtin": "neq.", "limit": 400}) or []]
        gtins += [r["gtin"] for r in repo._req("GET", "anuncios", {"select": "gtin", "marca_anuncio": repo._eq(marca),
                                                                    "gtin": "neq.", "limit": 400}) or []]
        preco = d.get("preco_medio")
        return pesquisa_marca.sugerir(marca, gtins, float(preco) if preco else None)

    if rota == "ranking_categoria_salvar" and metodo == "POST":
        d = json.loads(corpo or b"{}")
        marca, c = (d.get("marca") or "").strip(), d.get("categoria") or ""
        k = nubi.compacta(marca)
        if not k:
            raise ErroNuvem("Informe a marca.")
        if c in categorias.CATEGORIAS:
            repo._req("POST", "marca_categorias", corpo=[{"marca_chave": k, "marca": marca, "categoria": c,
                                                          "atualizado_em": datetime.now(timezone.utc).isoformat()}],
                      prefer="resolution=merge-duplicates,return=minimal")
        else:                                      # volta para a classificação automática
            repo._req("DELETE", "marca_categorias", {"marca_chave": repo._eq(k)})
        cat, fonte = categorias.classificar(marca, {k: c} if c in categorias.CATEGORIAS else None)
        try:
            repo._req("PATCH", "marca_sugestoes", {"marca_chave": repo._eq(k)}, corpo={"estado": "aplicada"}, prefer="return=minimal")
        except ErroNuvem:
            pass
        return {"ok": True, "categoria": cat, "fonte": fonte}

    if rota == "ranking_resumo_ia":
        # resumo do mês escrito pela IA a partir dos números do nubi (fica guardado; "novo=1" escreve de novo)
        cat = q["categoria"]
        rels = _relatorios(repo, cat)
        if not rels:
            raise ErroNuvem("Nenhum relatório importado para esta categoria.", 404)
        mes = rels[-1]["mes"][:7]
        chave = f"ranking|{cat}|{mes}"
        if not q.get("novo"):
            ja = repo._req("GET", "ia_resumos", {"select": "texto,ia,criado_em", "chave": repo._eq(chave)}) or []
            if ja or metodo != "POST":
                return {"mes": mes, "texto": ja[0]["texto"] if ja else "", "ia": ja[0]["ia"] if ja else None,
                        "criado_em": ja[0]["criado_em"] if ja else None, "disponivel": bool(ia.disponivel())}
        if not ia.disponivel():
            raise ErroNuvem("Configure uma chave de IA (OPENAI_API_KEY) na Vercel para gerar o resumo.")
        texto, qual = gerar_resumo_marcas(repo, cat, rels, chave)
        return {"mes": mes, "texto": texto, "ia": ia.nome(qual), "criado_em": datetime.now(timezone.utc).isoformat(),
                "disponivel": True}

    if rota == "ranking_apagar" and metodo == "POST":
        repo._req("DELETE", "ranking_relatorios", {"id": repo._eq(int(q["id"]))})
        return {"ok": True}

    raise ErroNuvem("Rota desconhecida.", 404)



# ---------------------------------------------------------------------------
# 5. Vendedores monitorados
# ---------------------------------------------------------------------------

CAMPOS_VEND = ["titulo", "marca", "marca_chave", "gtin", "sku", "vendas", "unidades", "preco", "tipo_pub",
               "fulfillment", "catalogo", "frete_gratis", "desconto", "estado", "bruto"]


def _prod_mes(repo, ids):
    """Produtos (por GTIN) de cada relatório, somando os anúncios (SQL vend_prod_mes)."""
    return repo._todos("rpc/vend_prod_mes", {"order": "relatorio_id,chave"}, "POST", {"ids": ids})


def _dias_mes(repo, vendedor, mes):
    """{chave: {dia: foto}} do vendedor num mês (vend_produto_dia)."""
    rs = repo._todos("vend_produto_dia", {"select": "chave,dias", "vendedor": repo._eq(vendedor),
                                          "mes": repo._eq(str(mes)[:7] + "-01"), "order": "chave"})
    return {r["chave"]: r["dias"] for r in rs}


def _vend_rels(repo, vendedor=None):
    p = {"select": "id,vendedor,mes,ate,arquivo,importado_em,seller_hash,nome_exibido", "order": "vendedor,mes"}
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
    return unificar_marcas(repo, ls)


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
    todas = unificar_marcas(repo, repo._todos("ranking_linhas", {
        "select": "relatorio_id,posicao,variacao,marca,marca_chave,vendas,unidades,tendencia,catalogo,"
                  "vendedores,saturacao,ranking_demanda",
        "relatorio_id": f"in.({ids})", "order": "relatorio_id,posicao"}), somar=True)
    por_rel = {r["id"]: [] for r in rels_cat}
    for l in todas:
        por_rel[l["relatorio_id"]].append(l)
    bi = ranking.bi([r["mes"] for r in rels_cat], [por_rel[r["id"]] for r in rels_cat])
    return cat, {l["marca_chave"]: l for l in ls}, bi


def _registrar_achado_auditoria(repo, achado):
    """Acrescenta 1 achado {nivel, area, titulo, detalhe} na auditoria do dia (Brasília) do gate de publicação (card
    #9), sem apagar o que já tinha: junta com o que existir hoje e regrava o resumo. Acrescenta origem=gate_publicacao
    (a rotina noturna 'auditoria' preserva achados com essa origem em vez de sobrescrever a lista inteira do zero —
    ver auditoria.rodar). Reprovação repetida do MESMO vendedor/dia/motivo (mesma área+título) atualiza o achado
    existente em vez de duplicar. nivel='erro' já aparece na hora em Central > Erros (_ops_erros lê a auditoria mais
    recente)."""
    achado = dict(achado, origem="gate_publicacao")
    hoje = _agora_br().date().isoformat()
    atual = repo._req("GET", "auditorias", {"select": "*", "data": f"eq.{hoje}", "limit": 1}) or []
    reg = atual[0] if atual else {"data": hoje, "resumo": "", "modulo": None, "conversa": []}
    conf = list(reg.get("conferencias") or [])
    igual = next((a for a in conf if a.get("area") == achado["area"] and a.get("titulo") == achado["titulo"]), None)
    if igual:
        igual.update(achado)
    else:
        conf.append(achado)
    n = {k: sum(1 for a in conf if a.get("nivel") == k) for k in ("erro", "alerta", "info")}
    reg["conferencias"] = conf
    reg["resumo"] = f"{n['erro']} erro(s), {n['alerta']} alerta(s), {n['info']} informação(ões)" + (
        f"; {reg['resumo'].split(';', 1)[1].strip()}" if "; " in (reg.get("resumo") or "") else "")
    repo._req("POST", "auditorias", corpo=[reg], prefer="resolution=merge-duplicates,return=minimal")


def validar_reconciliacao_publicacao(repo, vendedor, dia, v, u, itens):
    """Gate de publicação do card #9: confere o lote de UM dia de UM vendedor antes de gravar em vend_vendas_dia.
    Devolve (True, None) se pode publicar, ou (False, motivo) se deve ficar pendente (não escreve; o coletor detecta
    o erro e tenta de novo no próximo ciclo, do mesmo jeito que já trata qualquer outra falha de envio).
    Regras duras (sem tolerância, sempre bloqueiam): valor negativo; item com vendas em R$ mas sem nenhuma unidade;
    e item com unidades vendidas E vendas em R$ mas preço médio zerado (coluna de preço não veio no export) — item
    com unidades vendidas e R$ 0 é brinde/amostra grátis, não bloqueia. Regras com tolerância (só quando já existe
    referência, igual à auditoria): soma de R$ e de unidades do dia x a tabela do grupo do Nubimetrics
    (vend_grupo_dia), tolerância de arredondamento 3% (mínimo R$ 500 ou 5 unidades). Se a tabela do grupo ainda não
    chegou para esse vendedor/dia, não bloqueia (não é erro, é coleta ainda incompleta)."""
    if v is None or u is None or v < 0 or u < 0:
        return False, f"total do dia negativo ou ausente (v={v}, u={u})"
    for it in itens or []:
        iu, iv, ip = it.get("u") or 0, it.get("v") or 0, it.get("p") or 0
        if iu < 0 or iv < 0 or ip < 0:
            return False, f"item {it.get('t') or it.get('k')}: valor negativo (u={iu}, v={iv}, p={ip})"
        if iu == 0 and iv > 0:
            return False, f"item {it.get('t') or it.get('k')}: R$ {iv:.2f} em vendas sem nenhuma unidade"
        if iu > 0 and iv > 0 and ip <= 0:
            return False, f"item {it.get('t') or it.get('k')}: vendeu {iu} unidade(s) por R$ {iv:.2f} sem preço médio (conferir export)"
    grupo = repo._req("GET", "vend_grupo_dia", {"select": "v,u", "data": f"eq.{dia}",
                                                "vendedor": f"eq.{vendedor}", "limit": 1}) or []
    if grupo:
        gv = float(grupo[0].get("v") or 0)
        if abs(gv - v) > max(500, 0.03 * max(gv, v)):
            return False, (f"tabela do grupo (Nubimetrics) R$ {gv:,.0f} x soma do export do dia R$ {v:,.0f}"
                           .replace(",", ".") + (f" ({(v / gv - 1) * 100:+.1f}%)".replace(".", ",") if gv else ""))
        gu = grupo[0].get("u")
        if gu is not None:
            gu = float(gu)
            if abs(gu - u) > max(5, 0.03 * max(gu, u)):
                return False, f"tabela do grupo {gu:.0f} unidade(s) x soma do export do dia {u} unidade(s)"
    return True, None


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
            out.setdefault(r["vendedor"], []).append({"id": r["id"], "mes": r["mes"][:7], "ate": r.get("ate"),
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
        ja = repo._req("GET", "vend_relatorios", {"select": "id,vendedor,mes,seller_hash", "hash": repo._eq(h)})
        if ja and q.get("seller_hash") and not ja[0].get("seller_hash"):
            # mesmo arquivo importado antes à mão: só falta guardar o hash do vendedor
            repo._req("PATCH", "vend_relatorios", {"vendedor": repo._eq(ja[0]["vendedor"]), "seller_hash": "is.null"},
                      corpo={"seller_hash": q["seller_hash"]})
        if ja:
            return {"ok": True, "log": [f"Esse arquivo já foi importado ({ja[0]['vendedor']}, "
                                        f"{ranking.nome_mes(ja[0]['mes'])})."],
                    "vendedor": ja[0]["vendedor"], "mes": ja[0]["mes"][:7]}
        exibido = vend
        imp = vendedores.impressao(linhas)
        log = []
        vend, decisoes = _identificar_vendedor(repo, vend, q.get("seller_hash") or None, mes, imp, log)
        antigos = repo._req("DELETE", "vend_relatorios", {"vendedor": repo._eq(vend), "mes": repo._eq(mes + "-01")},
                            prefer="return=representation") or []
        ate = q.get("ate") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", q.get("ate") or "") else None
        novo = repo._req("POST", "vend_relatorios", corpo=[{
            "vendedor": vend, "mes": mes + "-01", "arquivo": nome, "hash": h, "ate": ate,
            "seller_hash": q.get("seller_hash") or None, "nome_exibido": exibido, "impressao": imp}],
            prefer="return=representation")
        rid = novo[0]["id"]
        if decisoes:
            repo._req("POST", "vend_decisoes", corpo=[dict(d, relatorio_id=rid) for d in decisoes],
                      prefer="return=minimal")
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
        # foto acumulada de cada produto no dia (vendas por dia e ruptura de estoque)
        fts = vend_bi.fotos(linhas, vend, mes, ate)
        for i in range(0, len(fts), LOTE):
            repo._req("POST", "rpc/vend_dia_gravar", corpo={"dados": fts[i:i + LOTE]})
        log.insert(0, f"OK: {vend} · {ranking.nome_mes(mes + '-01')} · {len(linhas)} anúncios · "
                      f"R$ {sum(l['vendas'] for l in linhas):,.0f}".replace(",", "."))
        if antigos:
            log.append("(substituiu o relatório anterior do mesmo mês)")
        return {"ok": True, "log": log, "vendedor": vend, "mes": mes}

    if rota == "vend_foto" and metodo == "POST":
        # export de um período parcial de mês passado (ex.: 01/08 a 22/08) só para a comparação com o mesmo período:
        # vira a foto acumulada do dia 22/08 em vend_produto_dia; o relatório do mês fechado continua o mesmo
        nome = q.get("arquivo") or "vendedor.xlsx"
        try:
            linhas, vend, _ = vendedores.ler_vendedor(corpo, nome)
        except vendedores.ErroVendedor as e:
            raise ErroNuvem(f"Não importado: {e}.")
        mes, ate = q.get("mes") or "", q.get("ate") or ""
        if not re.fullmatch(r"\d{4}-\d{2}", mes) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", ate):
            raise ErroNuvem("Informe o mês e a data (ate) da foto.")
        vend = (vend or "").strip().upper()
        if q.get("seller_hash"):
            r = repo._req("GET", "vend_relatorios", {"select": "vendedor", "seller_hash": repo._eq(q["seller_hash"]),
                                                     "order": "mes.desc", "limit": 1}) or []
            if r:
                vend = r[0]["vendedor"]
        fts = vend_bi.fotos(linhas, vend, mes, ate)
        for i in range(0, len(fts), LOTE):
            repo._req("POST", "rpc/vend_dia_gravar", corpo={"dados": fts[i:i + LOTE]})
        return {"ok": True, "log": [f"Foto de {vend} até {ate[8:10]}/{ate[5:7]} gravada ({len(fts)} produtos), "
                                    "para comparar com o mesmo período do mês atual."], "vendedor": vend}

    if rota == "vend_dia" and metodo == "POST":
        # export de UM dia (ex.: 21/09 a 21/09): a venda isolada do dia do vendedor, com todos os itens vendidos
        nome = q.get("arquivo") or "vendedor.xlsx"
        try:
            linhas, vend, _ = vendedores.ler_vendedor(corpo, nome)
        except vendedores.ErroVendedor as e:
            raise ErroNuvem(f"Não importado: {e}.")
        dia = q.get("ate") or ""
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dia):
            raise ErroNuvem("Informe o dia (ate).")
        vend = (vend or "").strip().upper()
        if q.get("seller_hash"):
            r = repo._req("GET", "vend_relatorios", {"select": "vendedor", "seller_hash": repo._eq(q["seller_hash"]),
                                                     "order": "mes.desc", "limit": 1}) or []
            if r:
                vend = r[0]["vendedor"]
        itens = vend_bi.itens_dia(linhas)
        v_dia, u_dia = round(sum(i["v"] for i in itens), 2), sum(i["u"] for i in itens)
        ok, motivo = validar_reconciliacao_publicacao(repo, vend, dia, v_dia, u_dia, itens)
        if not ok:
            _registrar_achado_auditoria(repo, {"nivel": "erro", "area": "dados",
                "titulo": f"{vend} em {dia[8:10]}/{dia[5:7]}: gate de publicação reprovou (card #9)", "detalhe": motivo})
            raise ErroNuvem(f"Dado ficou pendente (não publicado): {motivo}")
        repo._req("POST", "vend_vendas_dia", corpo=[{
            "vendedor": vend, "data": dia, "v": v_dia, "u": u_dia,
            "anuncios": len(linhas), "itens": itens, "atualizado_em": datetime.now(timezone.utc).isoformat()}],
            prefer="resolution=merge-duplicates,return=minimal")
        return {"ok": True, "vendedor": vend, "log": [
            f"Vendas de {vend} em {dia[8:10]}/{dia[5:7]}: {len(itens)} produto(s), "
            f"R$ {sum(i['v'] for i in itens):,.0f}".replace(",", ".")]}

    if rota == "vend_grupo" and metodo == "POST":
        # tabela do grupo no dia (Comparar concorrentes do Nubimetrics): vendas, unidades, visitas e conversão de todos
        dia = q.get("ate") or ""
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dia):
            raise ErroNuvem("Informe o dia (ate).")
        try:
            linhas = vendedores.ler_grupo(corpo, q.get("arquivo") or "grupo.xlsx")
        except vendedores.ErroVendedor as e:
            raise ErroNuvem(f"Não importado: {e}.")
        conhecidos = {re.sub(r"[^A-Z0-9]", "", v.upper()): v for v in
                      {r["vendedor"] for r in _vend_rels(repo)} | {r["vendedor"] for r in repo._req("GET", "vend_vendas_dia", {"select": "vendedor", "limit": 500}) or []}}
        regs = []
        for l in linhas:
            nome = conhecidos.get(re.sub(r"[^A-Z0-9]", "", l["vendedor"].upper()), l["vendedor"].upper())
            regs.append({"data": dia, "vendedor": nome, "nome_exibido": l["vendedor"], "v": l["v"],
                         "u": int(l["u"]) if l["u"] is not None else None, "visitas": int(l["visitas"]) if l["visitas"] is not None else None,
                         "conversao": l["conversao"], "share_v": l["share_v"], "share_u": l["share_u"], "bruto": l["bruto"],
                         "atualizado_em": datetime.now(timezone.utc).isoformat()})
        repo._req("POST", "vend_grupo_dia", corpo=regs, prefer="resolution=merge-duplicates,return=minimal")
        return {"ok": True, "log": [f"{len(regs)} vendedor(es), R$ {sum(r['v'] or 0 for r in regs):,.0f}".replace(",", ".")
                                    + (f", {sum(r['visitas'] or 0 for r in regs):,} visitas".replace(",", ".") if any(r['visitas'] for r in regs) else "")]}

    if rota == "vend_dia_vazio" and metodo == "POST":
        # o vendedor não vendeu nada no dia (o Nubimetrics exportou vazio): guarda o dia zerado (diferente de "sem coleta")
        dia = q.get("ate") or ""
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dia):
            raise ErroNuvem("Informe o dia (ate).")
        vend = (q.get("nome") or "").strip().upper()
        if q.get("seller_hash"):
            r = repo._req("GET", "vend_relatorios", {"select": "vendedor", "seller_hash": repo._eq(q["seller_hash"]),
                                                     "order": "mes.desc", "limit": 1}) or []
            if r:
                vend = r[0]["vendedor"]
        if not vend:
            raise ErroNuvem("Vendedor não identificado.")
        repo._req("POST", "vend_vendas_dia", corpo=[{"vendedor": vend, "data": dia, "v": 0, "u": 0, "anuncios": 0, "itens": [],
                                                      "atualizado_em": datetime.now(timezone.utc).isoformat()}],
                  prefer="resolution=merge-duplicates,return=minimal")
        return {"ok": True}

    if rota == "vend_painel_dia":
        return _painel_dia(repo)

    if rota == "vend_concorrentes":
        # Comparar concorrentes (como no Nubimetrics): período escolhido x o período anterior do mesmo tamanho
        lim = repo._req("GET", "vend_vendas_dia", {"select": "data", "order": "data.desc", "limit": 1}) or []
        if not lim:
            return {"tem": False}
        ult = str(lim[0]["data"])[:10]
        pri = str((repo._req("GET", "vend_vendas_dia", {"select": "data", "order": "data.asc", "limit": 1}) or lim)[0]["data"])[:10]
        ate = q.get("ate") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", q.get("ate") or "") else ult
        desde = q.get("desde") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", q.get("desde") or "") else ate
        if desde > ate:
            desde, ate = ate, desde
        n = (date.fromisoformat(ate) - date.fromisoformat(desde)).days + 1
        ate_ant = (date.fromisoformat(desde) - timedelta(days=1)).isoformat()
        desde_ant = (date.fromisoformat(desde) - timedelta(days=n)).isoformat()
        linhas = repo._todos("rpc/vend_dia_serie", {}, "POST", {"desde": desde_ant, "ate": ate})
        # a tabela do grupo (Nubimetrics > Comparar concorrentes) manda quando existe: são os números da própria tela
        # deles, com visitas e conversão; sem ela, a soma do export de 1 dia de cada vendedor
        try:
            grupo = [g for g in repo._todos("vend_grupo_dia", {"select": "data,vendedor,v,u,visitas,conversao", "data": f"gte.{desde_ant}"})
                     if str(g["data"])[:10] <= ate]
        except ErroNuvem:
            grupo = []
        dia_v = {}
        for l in linhas:
            dia_v[(l["vendedor"], str(l["data"])[:10])] = {"v": float(l["v"] or 0), "u": int(l["u"] or 0), "visitas": None,
                                                            "conv": None, "fonte": "dia"}
        for g in grupo:
            k = (g["vendedor"], str(g["data"])[:10])
            x = dia_v.setdefault(k, {"v": 0.0, "u": 0, "visitas": None, "conv": None, "fonte": "grupo"})
            if g.get("v") is not None:
                x["v"], x["fonte"] = float(g["v"]), "grupo"
            if g.get("u") is not None:
                x["u"] = int(g["u"])
            x["visitas"] = g.get("visitas")
            x["conv"] = float(g["conversao"]) if g.get("conversao") is not None else None
        dias = [(date.fromisoformat(desde) + timedelta(days=i)).isoformat() for i in range(n)]
        pos = {d: i for i, d in enumerate(dias)}
        por = {}
        for (vd, d), l in sorted(dia_v.items(), key=lambda kv: kv[0][1]):
            x = por.setdefault(vd, {"vendedor": vd, "v": 0.0, "u": 0, "v_ant": 0.0, "u_ant": 0, "visitas": 0, "com_visitas": 0,
                                    "visitas_ant": 0, "u_vis": 0, "u_vis_ant": 0,
                                    "dias": 0, "dias_ant": 0, "serie_v": [None] * n, "serie_u": [None] * n, "fonte_grupo": 0})
            if d >= desde:
                x["v"] += l["v"]
                x["u"] += l["u"]
                x["dias"] += 1
                x["serie_v"][pos[d]] = l["v"]
                x["serie_u"][pos[d]] = l["u"]
                x["fonte_grupo"] += 1 if l["fonte"] == "grupo" else 0
                if l["visitas"] is not None:
                    x["visitas"] += l["visitas"]
                    # conversão do Nubimetrics, ponderada pelas visitas (sem ela: unidades / visitas)
                    x["u_vis"] += (l["conv"] * l["visitas"]) if l["conv"] is not None else l["u"]
                    x["com_visitas"] += 1
            else:
                x["v_ant"] += l["v"]
                x["u_ant"] += l["u"]
                x["dias_ant"] += 1
                if l["visitas"] is not None:
                    x["visitas_ant"] += l["visitas"]
                    x["u_vis_ant"] += (l["conv"] * l["visitas"]) if l["conv"] is not None else l["u"]
        vs = [x for x in por.values() if x["dias"]]
        tv, tu = sum(x["v"] for x in vs), sum(x["u"] for x in vs)
        for x in vs:
            # variação só quando o vendedor tem o período anterior inteiro coletado (senão compara com buraco)
            comp = x["dias_ant"] >= n and x["dias"] >= n
            x["var_v"] = (x["v"] / x["v_ant"] - 1) if comp and x["v_ant"] else None
            x["var_u"] = (x["u"] / x["u_ant"] - 1) if comp and x["u_ant"] else None
            x["share_v"] = x["v"] / tv if tv else 0
            x["share_u"] = x["u"] / tu if tu else 0
            x["completo"] = x["dias"] >= n
            x["conversao"] = x["u_vis"] / x["visitas"] if x["com_visitas"] and x["visitas"] else None
            conv_ant = x["u_vis_ant"] / x["visitas_ant"] if x["visitas_ant"] else None
            x["var_visitas"] = (x["visitas"] / x["visitas_ant"] - 1) if comp and x["com_visitas"] and x["visitas_ant"] else None
            x["var_conversao"] = (x["conversao"] / conv_ant - 1) if comp and x["conversao"] and conv_ant else None
            if not x["com_visitas"]:
                x["visitas"] = None
        vs.sort(key=lambda x: -x["v"])
        coletados = sorted({d for (_, d) in dia_v if d >= desde})
        return {"tem": True, "desde": desde, "ate": ate, "desde_ant": desde_ant, "ate_ant": ate_ant, "dias": dias,
                "com_visitas": any(x["visitas"] is not None for x in vs),
                "coletados": coletados, "primeiro": pri, "ultimo": ult, "vendedores": vs,
                "total": {"v": tv, "u": tu, "v_ant": sum(x["v_ant"] for x in vs), "u_ant": sum(x["u_ant"] for x in vs)}}

    if rota == "vend_conc_vendedor":
        # produtos que o vendedor vendeu no período: preço atual, preço médio de 30 dias e se o anúncio está pausado
        vend = q.get("vendedor") or ""
        ate = q.get("ate") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", q.get("ate") or "") else None
        desde = q.get("desde") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", q.get("desde") or "") else ate
        if not vend or not ate:
            raise ErroNuvem("Informe o vendedor e o período.")
        ini30 = (date.fromisoformat(ate) - timedelta(days=29)).isoformat()
        inicio = min(desde, ini30)
        rows = [r for r in repo._todos("vend_vendas_dia", {"select": "data,v,u,itens", "vendedor": repo._eq(vend),
                                                            "data": f"gte.{inicio}", "order": "data"})
                if str(r["data"])[:10] <= ate]
        # por produto = GTIN (como o nubi agrupa); sem os "produtos iguais" da IA, para bater com o Nubimetrics
        dias = [(date.fromisoformat(desde) + timedelta(days=i)).isoformat()
                for i in range((date.fromisoformat(ate) - date.fromisoformat(desde)).days + 1)]
        pos = {d: i for i, d in enumerate(dias)}
        prods, anuncios = {}, {}
        for r in rows:
            d = str(r["data"])[:10]
            for it in r["itens"] or []:
                k = it["k"]
                p = prods.setdefault(k, {"chave": k, "produto": it.get("t") or k, "marca": it.get("m") or "", "v": 0.0, "u": 0,
                                         "pu30": 0.0, "u30": 0, "v30": 0.0, "dias": 0, "ult_dia": None, "preco_atual": None,
                                         "ativos": None, "anuncios": None, "serie": [None] * len(dias), "_tu": -1})
                v, u = float(it.get("v") or 0), int(it.get("u") or 0)
                pr = float(it.get("p") or 0) or (v / u if u else 0)
                if d >= ini30 and u:
                    p["pu30"] += pr * u
                    p["u30"] += u
                    p["v30"] += v
                if d >= desde:
                    p["v"] += v
                    p["u"] += u
                    p["dias"] += 1
                    p["serie"][pos[d]] = (p["serie"][pos[d]] or 0) + v
                    if u > p["_tu"]:                       # título do anúncio que mais vendeu no período
                        p["produto"], p["_tu"] = it.get("t") or p["produto"], u
                    for a in it.get("l") or []:            # anúncio a anúncio (como a tela do Nubimetrics)
                        x = anuncios.setdefault((k, a["t"]), {"titulo": a["t"], "chave": k, "marca": it.get("m") or "",
                                                              "v": 0.0, "u": 0, "preco": None, "estado": "", "tipo": "",
                                                              "full": False, "ult": ""})
                        x["v"] += float(a.get("v") or 0)
                        x["u"] += int(a.get("u") or 0)
                        if d >= x["ult"]:
                            x.update(preco=a.get("p") or None, estado=a.get("e") or "", tipo=a.get("tp") or "",
                                     full=bool(a.get("f")), ult=d)
                if u and (p["ult_dia"] is None or d >= p["ult_dia"]):
                    p["ult_dia"], p["preco_atual"] = d, pr
                    p["ativos"], p["anuncios"] = it.get("a"), it.get("n")
        lista = []
        for p in prods.values():
            if not p["u"]:
                continue
            p.pop("_tu", None)
            p["preco_medio"] = p["v"] / p["u"]
            p["preco_30d"] = p["pu30"] / p["u30"] if p["u30"] else None
            p["dif_preco"] = (p["preco_atual"] / p["preco_30d"] - 1) if p["preco_atual"] and p["preco_30d"] else None
            p["pausado"] = p["ativos"] == 0
            lista.append(p)
        lista.sort(key=lambda p: -p["v"])
        tot = {"v": sum(p["v"] for p in lista), "u": sum(p["u"] for p in lista), "produtos": len(lista),
               "pausados": sum(1 for p in lista if p["pausado"])}
        coletados = sorted({str(r["data"])[:10] for r in rows if str(r["data"])[:10] >= desde})
        return {"vendedor": vend, "desde": desde, "ate": ate, "dias": dias, "coletados": coletados, "produtos": lista,
                "anuncios": sorted(anuncios.values(), key=lambda a: -a["v"]), "total": tot, "ini30": ini30,
                "com_anuncios": any(it.get("l") for r in rows for it in (r["itens"] or [])[:1])}

    if rota == "vend_diario":
        # aba Vendas diárias: série dia a dia por vendedor, dia da semana, produtos do período e o dia escolhido
        lim = repo._req("GET", "vend_vendas_dia", {"select": "data", "order": "data.desc", "limit": 1}) or []
        if not lim:
            return {"tem": False}
        ult = str(lim[0]["data"])[:10]
        pri = str((repo._req("GET", "vend_vendas_dia", {"select": "data", "order": "data.asc", "limit": 1}) or [{"data": ult}])[0]["data"])[:10]
        per = q.get("periodo") or "30d"
        if re.fullmatch(r"\d{4}-\d{2}", per):
            desde, ate = f"{per}-01", min(ult, f"{per}-{vend_bi.dias_do_mes(per):02d}")
        elif per == "tudo":
            desde, ate = pri, ult
        else:
            n = int(re.sub(r"\D", "", per) or 30)
            desde, ate = max(pri, (date.fromisoformat(ult) - timedelta(days=n - 1)).isoformat()), ult
        vend = q.get("vendedor") or None
        linhas = repo._todos("rpc/vend_dia_serie", {}, "POST", {"desde": desde, "ate": ate})
        todos = sorted({l["vendedor"] for l in linhas})
        coletados = {str(l["data"])[:10] for l in linhas}          # dias coletados (de qualquer vendedor)
        if vend:
            linhas = [l for l in linhas if l["vendedor"] == vend]
        dias, d = [], date.fromisoformat(desde)
        while d.isoformat() <= ate:
            dias.append(d.isoformat())
            d += timedelta(days=1)
        por_v = {}
        for l in linhas:
            dd = str(l["data"])[:10]
            x = por_v.setdefault(l["vendedor"], {"vendedor": l["vendedor"], "v": [None] * len(dias), "u": [0] * len(dias)})
            i = dias.index(dd)
            x["v"][i] = float(l["v"] or 0)
            x["u"][i] = int(l["u"] or 0)
        vs = []
        for x in por_v.values():
            tv = sum(v for v in x["v"] if v is not None)
            nd = sum(1 for v in x["v"] if v is not None)      # dias com o arquivo desse vendedor
            com = [(dias[i], v) for i, v in enumerate(x["v"]) if v is not None]
            melhor = max(com, key=lambda t: t[1]) if com else (None, 0)
            vs.append(dict(x, total=tv, unidades=sum(x["u"]), media=tv / nd if nd else 0,
                           melhor_dia=melhor[0], melhor_v=melhor[1],
                           dias_sem_venda=sum(1 for dd, v in com if v == 0)))
        vs.sort(key=lambda x: -x["total"])
        sem = repo._req("POST", "rpc/vend_dia_semana", corpo={"desde": desde, "ate": ate, "so_vendedor": vend}) or []
        prods = repo._req("POST", "rpc/vend_dia_produtos", corpo={"desde": desde, "ate": ate, "so_vendedor": vend, "lim": 40}) or []
        for p in prods:
            p["serie"] = [float((p.get("por_dia") or {}).get(dd, 0)) if dd in coletados else None for dd in dias]
            p.pop("por_dia", None)
        dia = q.get("data") if q.get("data") in coletados else max(coletados) if coletados else ult
        pnl = _painel_dia(repo, dia)
        regs = repo._req("GET", "vend_vendas_dia", {"select": "vendedor,v,u,itens", "data": repo._eq(dia),
                                                    **({"vendedor": repo._eq(vend)} if vend else {})}) or []
        itens = sorted([{"vendedor": r["vendedor"], "v": float(r["v"] or 0), "u": int(r["u"] or 0), "n": len(r["itens"] or []),
                         "itens": (r["itens"] or [])[:80]} for r in regs], key=lambda r: -r["v"])
        meses, m = [], pri[:7]
        while m <= ult[:7]:
            meses.insert(0, m)
            a, b = map(int, m.split("-"))
            m = f"{a + (b == 12)}-{b % 12 + 1:02d}"
        return {"tem": True, "periodo": per, "desde": desde, "ate": ate, "primeiro": pri, "ultimo": ult, "meses": meses,
                "dias": dias, "coletados": sorted(coletados), "vendedores": vs, "semana": sem, "produtos": prods,
                "dia": dia, "painel": pnl, "itens_dia": itens, "vendedor": vend,
                "todos_vendedores": todos}

    if rota == "vend_produtos_iguais":
        # grupos que a IA juntou (para conferir e separar o que estiver errado)
        rs = repo._todos("produto_grupos", {"select": "*", "order": "marca,grupo"})
        grupos = {}
        for r in rs:
            if r["metodo"] not in ("ia", "manual"):
                continue
            g = grupos.setdefault(r["grupo"], {"grupo": r["grupo"], "titulo": r.get("grupo_titulo") or r["grupo"],
                                               "marca": r.get("marca") or "", "membros": []})
            g["membros"].append({"chave": r["chave"], "titulo": r.get("titulo"), "similaridade": r.get("similaridade"),
                                 "metodo": r["metodo"]})
        separados = [r for r in rs if r["metodo"] == "separado"]
        conferir = sorted((r for r in rs if r["metodo"] == "gtin_conferir"), key=lambda r: -(r.get("similaridade") or 0))
        return {"grupos": sorted(grupos.values(), key=lambda g: (g["marca"], g["titulo"] or "")), "separados": separados,
                "conferir_gtins": conferir}

    if rota == "vend_gtin_decidir" and metodo == "POST":
        # conferência de GTINs diferentes com o mesmo nome (26/09): o Bruno junta ou diz que não é o mesmo
        d = json.loads(corpo or b"{}")
        par = str(d.get("par") or "")
        r = (repo._req("GET", "produto_grupos", {"select": "*", "chave": repo._eq(par)}) or [None])[0]
        if not r or not par.startswith("par:"):
            raise ErroNuvem("Par não encontrado (a lista pode ter sido refeita; recarregue).")
        a_, b_ = par[4:].split("|", 1)
        agora_ = datetime.now(timezone.utc).isoformat()
        if d.get("juntar"):
            repo._req("POST", "produto_grupos", corpo=[{"chave": b_, "grupo": a_, "titulo": r.get("titulo") or "",
                                                         "grupo_titulo": r.get("grupo_titulo") or "", "marca": r.get("marca") or "",
                                                         "similaridade": r.get("similaridade"), "metodo": "manual", "atualizado_em": agora_}],
                      prefer="resolution=merge-duplicates,return=minimal")
            repo._req("DELETE", "produto_grupos", {"chave": repo._eq(par)})
        else:
            repo._req("PATCH", "produto_grupos", {"chave": repo._eq(par)}, corpo={"metodo": "gtin_nao", "atualizado_em": agora_})
        return {"ok": True}

    if rota == "vend_produto_separar" and metodo == "POST":
        d = json.loads(corpo or b"{}")
        k = d.get("chave") or ""
        if d.get("desfazer"):
            repo._req("DELETE", "produto_grupos", {"chave": repo._eq(k), "metodo": "eq.separado"})
        else:
            repo._req("POST", "produto_grupos", corpo=[{"chave": k, "grupo": k, "titulo": d.get("titulo") or "", "metodo": "separado",
                                                         "atualizado_em": datetime.now(timezone.utc).isoformat()}],
                      prefer="resolution=merge-duplicates,return=minimal")
        return {"ok": True}

    if rota == "vend_periodo":
        return _comparativo(repo)

    if rota == "vend_relatorio":
        vend = q["vendedor"]
        rels = _vend_rels(repo, vend)
        if not rels:
            raise ErroNuvem("Nenhum relatório deste vendedor.", 404)
        mes = q.get("mes")
        fechado = max((i for i, r in enumerate(rels) if not r.get("ate")), default=len(rels) - 1)
        idx = next((i for i, r in enumerate(rels) if r["mes"][:7] == mes), fechado)
        atual, ant = rels[idx], (rels[idx - 1] if idx > 0 else None)
        linhas = _vend_linhas(repo, atual["id"])
        linhas_ant = _vend_linhas(repo, ant["id"]) if ant else None
        cat, rk_mes, bi = _ranking_do_mes(repo, atual["mes"][:7], {l["marca_chave"] for l in linhas})
        ex = _explorador_cruzado(repo, vend)
        r = vendedores.analisar(linhas, linhas_ant, rk_mes, bi, ex, vend)
        evol = []                                    # a evolução mês a mês está na visão do ano (vend_bi)
        r.update({"vendedor": vend, "mes": atual["mes"][:7], "mes_nome": ranking.nome_mes(atual["mes"]),
                  "id": atual["id"], "arquivo": atual["arquivo"],
                  "anterior": {"mes": ant["mes"][:7], "nome": ranking.nome_mes(ant["mes"])} if ant else None,
                  "meses": [{"mes": x["mes"][:7], "ate": x.get("ate"), "nome": ranking.nome_mes(x["mes"]) + (
                      f" (parcial até {nubi.fmt_data(x['ate'])[:5]})" if x.get("ate") else "")} for x in reversed(rels)],
                  "parcial_ate": atual.get("ate"),
                  "evolucao": evol, "ranking": {"categoria": cat, "categoria_nome": ranking.nome_categoria(cat) if cat else "",
                                                "mes_ok": bool(rk_mes)},
                  "explorador_gtins": sum(1 for p in r["produtos"] if p["ex_preco_medio"] is not None)})
        return r

    if rota == "vend_bi":
        vend = q["vendedor"]
        rels = _vend_rels(repo, vend)
        if not rels:
            raise ErroNuvem("Nenhum relatório deste vendedor.", 404)
        prods = _prod_mes(repo, [r["id"] for r in rels])
        ult, ant = rels[-1], (rels[-2] if len(rels) > 1 else None)
        dias = _dias_mes(repo, vend, ult["mes"])
        r = vend_bi.ano(rels, prods, dias)
        r["alertas"] = vend_bi.alertas(vend, ant, ult, [p for p in prods if p["relatorio_id"] == ant["id"]],
                                       [p for p in prods if p["relatorio_id"] == ult["id"]], dias) if ant else []
        r.update({"vendedor": vend, "diario_dias": len({d for x in dias.values() for d in x})})
        return r

    if rota == "vend_alertas":
        rels = _vend_rels(repo)
        por = {}
        for r in rels:
            por.setdefault(r["vendedor"], []).append(r)

        def um(item):
            vend, rs = item
            if len(rs) < 2:
                return [], []
            ant, ult = rs[-2], rs[-1]
            prods = _prod_mes(repo, [ant["id"], ult["id"]])
            p_ult = [p for p in prods if p["relatorio_id"] == ult["id"]]
            al = vend_bi.alertas(vend, ant, ult, [p for p in prods if p["relatorio_id"] == ant["id"]], p_ult,
                                 _dias_mes(repo, vend, ult["mes"]))
            d = vend_bi.dias_periodo(ult)
            return al, [(p["chave"], {"vendedor": vend, "ritmo": (p["unidades"] or 0) / d if d else 0,
                                      "ativos": p["ativos"], "preco": float(p["vendas"] or 0) / p["unidades"]
                                      if p["unidades"] else 0}) for p in p_ult]
        with ThreadPoolExecutor(8) as ex:
            res = list(ex.map(um, por.items()))
        todos, quem = [], {}
        for al, qv in res:
            todos.extend(al)
            for k, v in qv:
                quem.setdefault(k, []).append(v)
        for v in quem.values():
            v.sort(key=lambda x: -x["ritmo"])
        return {"produtos": vend_bi.cruzar_alertas(todos, quem), "alertas": todos,
                "vendedores": len(por), "fotos": {v: rs[-1].get("ate") or rs[-1]["mes"][:7] for v, rs in por.items()}}

    if rota == "vend_produto":
        k = q["chave"]
        rels = {r["id"]: r for r in _vend_rels(repo)}
        serie = repo._req("POST", "rpc/vend_prod_serie", corpo={"p_chave": k}) or []
        dias = repo._todos("vend_produto_dia", {"select": "vendedor,mes,dias", "chave": repo._eq(k),
                                                "order": "vendedor,mes"})
        meses = sorted({r["mes"][:7] for r in rels.values()})
        por = {}
        titulo, marca = "", ""
        for x in sorted(serie, key=lambda x: rels[x["relatorio_id"]]["mes"] if x["relatorio_id"] in rels else ""):
            r = rels.get(x["relatorio_id"])
            if not r:
                continue
            v = por.setdefault(r["vendedor"], {"vendedor": r["vendedor"], "u": {}, "v": {}, "ritmo": {},
                                               "ativos": None, "anuncios": None, "ult": ""})
            m, d = r["mes"][:7], vend_bi.dias_periodo(r)
            v["u"][m], v["v"][m] = int(x["unidades"] or 0), float(x["vendas"] or 0)
            v["ritmo"][m] = (x["unidades"] or 0) / d if d else 0
            if m >= v["ult"]:
                v["ult"], v["ativos"], v["anuncios"] = m, x["ativos"], x["anuncios"]
                v["full"], v["catalogo"] = x["fulfillment"], x["catalogo"]
                titulo, marca = x["titulo"] or titulo, x["marca"] or marca
        ult_rel = {}
        for r in rels.values():
            if r["mes"] >= ult_rel.get(r["vendedor"], {}).get("mes", ""):
                ult_rel[r["vendedor"]] = r
        for linha in dias:
            v = por.get(linha["vendedor"])
            if v and linha["mes"][:7] == v["ult"]:
                v["diario"] = vend_bi.diario(linha["dias"], linha["mes"])
                v["parado"] = vend_bi.dias_parado(linha["dias"])
        for v in por.values():
            r = ult_rel.get(v["vendedor"])
            v["no_ultimo"] = bool(r and r["mes"][:7] == v["ult"])      # vendeu no último relatório dele
            v["ult_rel"] = r["mes"][:7] if r else ""
            v["ult_ate"] = r.get("ate") if r else None
            v["vendas"], v["unidades"] = sum(v["v"].values()), sum(v["u"].values())
        vs = sorted(por.values(), key=lambda v: -v["vendas"])
        return {"chave": k, "produto": titulo or k.replace("T:", ""), "marca": marca,
                "gtin": "" if k.startswith("T:") else k, "meses": meses, "vendedores": vs,
                "foco": q.get("vendedor") or ""}

    if rota == "vend_comparar":
        rels = _vend_rels(repo)
        if not rels:
            return {"meses": [], "vendedores": []}
        meses = sorted({r["mes"][:7] for r in rels})
        # sem mês pedido: o último mês FECHADO (o parcial tem poucos dias e poucos vendedores)
        fechados = sorted({r["mes"][:7] for r in rels if not r.get("ate")})
        mes = q.get("mes") if q.get("mes") in meses else (fechados[-1] if fechados else meses[-1])
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
                # mês parcial: compara o ritmo por dia, não o total
                d, da = vend_bi.dias_periodo(r), vend_bi.dias_periodo(antes[-1])
                z["var_vendas"] = ((z["vendas"] / d) / (za["vendas"] / da) - 1) if za["vendas"] and d and da else None
            z["parcial_ate"] = r.get("ate")
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
                "parciais": {r["mes"][:7]: r["ate"] for r in rels if r.get("ate")},
                "vendedores": vends, "matriz": mat, "categoria": cat}

    if rota == "vend_nomes":
        rels = _vend_rels(repo)
        pessoas = {}
        for r in rels:
            x = pessoas.setdefault(r["vendedor"], {"vendedor": r["vendedor"], "meses": [], "nomes": set(), "hashes": set()})
            x["meses"].append(r["mes"][:7])
            if r.get("nome_exibido"):
                x["nomes"].add(r["nome_exibido"])
            if r.get("seller_hash"):
                x["hashes"].add(r["seller_hash"])
        lista = []
        for x in sorted(pessoas.values(), key=lambda x: x["vendedor"]):
            lista.append(dict(x, nomes=sorted(x["nomes"] - {x["vendedor"]}), hashes=[h[:12] for h in sorted(x["hashes"])],
                              ofuscado=vendedores.ofuscado(x["vendedor"]), meses=sorted(x["meses"])))
        dec = repo._todos("vend_decisoes", {"select": "*", "order": "id.desc"})
        return {"vendedores": lista, "pendentes": [d for d in dec if d["status"] == "pendente"],
                "historico": [d for d in dec if d["status"] != "pendente"][:40]}

    if rota == "vend_juntar" and metodo == "POST":
        d = json.loads(corpo or b"{}")
        de, para = (d.get("de") or "").strip().upper(), (d.get("para") or "").strip().upper()
        if not de or not para or de == para:
            raise ErroNuvem("Escolha dois vendedores diferentes.")
        n = _renomear_vendedor(repo, de, para)
        repo._req("POST", "vend_decisoes", corpo=[{"vendedor_antes": de, "vendedor_depois": para, "tipo": "manual",
                                                   "status": "aplicado", "detalhe": f"{n} mês(es) juntados"}],
                  prefer="return=minimal")
        return {"ok": True, "meses": n}

    if rota == "vend_decisao" and metodo == "POST":
        d = json.loads(corpo or b"{}")
        dec = repo._req("GET", "vend_decisoes", {"select": "*", "id": repo._eq(int(d["id"]))})
        if not dec:
            raise ErroNuvem("Decisão não encontrada.", 404)
        dec = dec[0]
        acao = d.get("acao")
        if acao == "aceitar" and dec["status"] == "pendente":
            _renomear_vendedor(repo, dec["vendedor_antes"], dec["vendedor_depois"])
            novo = "aplicado"
        elif acao == "recusar" and dec["status"] == "pendente":
            novo = "recusado"
        elif acao == "desfazer" and dec["status"] == "aplicado":
            if dec.get("relatorio_id"):
                r = repo._req("GET", "vend_relatorios", {"select": "id,mes", "id": repo._eq(dec["relatorio_id"])})
                if r and repo._req("GET", "vend_relatorios", {"select": "id", "vendedor": repo._eq(dec["vendedor_antes"]),
                                                              "mes": repo._eq(r[0]["mes"])}):
                    raise ErroNuvem(f"{dec['vendedor_antes']} já tem esse mês; apague um dos dois antes.")
                repo._req("PATCH", "vend_relatorios", {"id": repo._eq(dec["relatorio_id"])},
                          corpo={"vendedor": dec["vendedor_antes"]})
            else:
                raise ErroNuvem("Junção manual: para separar, junte de novo no sentido contrário ou apague o mês.")
            novo = "desfeito"
        else:
            raise ErroNuvem("Ação inválida para esta decisão.")
        repo._req("PATCH", "vend_decisoes", {"id": repo._eq(dec["id"])}, corpo={"status": novo})
        return {"ok": True}

    if rota == "vend_apagar" and metodo == "POST":
        repo._req("DELETE", "vend_relatorios", {"id": repo._eq(int(q["id"]))})
        return {"ok": True}

    raise ErroNuvem("Rota desconhecida.", 404)



def _renomear_vendedor(repo, de, para):
    """Junta todos os meses de `de` em `para`. Mês que os dois têm: fica o de `para`."""
    meses_para = {r["mes"] for r in _vend_rels(repo, para)}
    n = 0
    for r in _vend_rels(repo, de):
        if r["mes"] in meses_para:
            repo._req("DELETE", "vend_relatorios", {"id": repo._eq(r["id"])})
        else:
            repo._req("PATCH", "vend_relatorios", {"id": repo._eq(r["id"])}, corpo={"vendedor": para})
            n += 1
    return n


def _impressao_rel(repo, r):
    if r.get("impressao"):
        return r["impressao"]
    imp = vendedores.impressao(_vend_linhas(repo, r["id"]))
    repo._req("PATCH", "vend_relatorios", {"id": repo._eq(r["id"])}, corpo={"impressao": imp})
    return imp


def _identificar_vendedor(repo, vend, seller_hash, mes, imp, log):
    """Quem é este vendedor? 1º pelo hash do Nubimetrics; sem hash (ou nome novo/ofuscado),
    pela impressão digital dos anúncios comparada com os vendedores que não têm este mês.
    Devolve (nome no nubi, decisões a registrar)."""
    rels = repo._todos("vend_relatorios", {"select": "id,vendedor,mes,seller_hash,impressao", "order": "mes.desc"})
    decisoes = []
    if seller_hash:
        mesmo = next((r for r in rels if r.get("seller_hash") == seller_hash), None)
        if mesmo and mesmo["vendedor"] != vend:
            antigo = mesmo["vendedor"]
            if vendedores.ofuscado(antigo) and not vendedores.ofuscado(vend):
                n = _renomear_vendedor(repo, antigo, vend)
                log.append(f"(ganhou apelido: {antigo} agora é {vend}; {n} mês(es) antigos juntados)")
                decisoes.append({"vendedor_antes": antigo, "vendedor_depois": vend, "tipo": "hash", "status": "aplicado",
                                 "detalhe": "mesmo hash do Nubimetrics, novo apelido"})
            else:
                log.append(f"(mesmo vendedor que {antigo}, pelo hash do Nubimetrics)")
                decisoes.append({"vendedor_antes": vend, "vendedor_depois": antigo, "tipo": "hash", "status": "aplicado",
                                 "detalhe": "mesmo hash do Nubimetrics"})
                vend = antigo
            return vend, decisoes
        if mesmo or (not vendedores.ofuscado(vend) and any(r["vendedor"] == vend for r in rels)):
            return vend, decisoes
    elif any(r["vendedor"] == vend for r in rels) and not vendedores.ofuscado(vend):
        return vend, decisoes
    # impressão digital: candidatos = vendedores que ainda não têm este mês
    recusados = {d["vendedor_depois"] for d in repo._todos("vend_decisoes", {
        "select": "vendedor_depois", "vendedor_antes": repo._eq(vend), "status": "eq.recusado"})}
    com_mes = {r["vendedor"] for r in rels if r["mes"][:7] == mes}
    ultimo = {}
    for r in rels:
        if r["vendedor"] != vend and r["vendedor"] not in com_mes and r["vendedor"] not in recusados:
            ultimo.setdefault(r["vendedor"], r)
    melhor = None
    for nome_c, r in ultimo.items():
        c = vendedores.comparar(imp, _impressao_rel(repo, r))
        nota = c["itens"] + 0.5 * c["vendas"] + 0.3 * c["marcas"]     # itens pesam mais; desempata no faturamento
        if melhor is None or nota > melhor[2]:
            melhor = (nome_c, c, nota)
    if not melhor:
        return vend, decisoes
    nome_c, c, _ = melhor
    txt = (f"itens {c['itens']:.0%}, faturamento {c['vendas']:.0%}, marcas {c['marcas']:.0%}, "
           f"tamanho do catálogo {c['tamanho']:.0%}")
    decisao = vendedores.decidir(c)
    if decisao == "mesmo":
        log.append(f"(reconhecido como {nome_c} pelos anúncios: {txt})")
        decisoes.append({"vendedor_antes": vend, "vendedor_depois": nome_c, "tipo": "impressao", "status": "aplicado",
                         "similaridade": round(c["itens"], 3), "detalhe": txt})
        return nome_c, decisoes
    if decisao == "revisar":
        log.append(f"(parece {nome_c} ({txt}); importado como {vend} — confira em Nomes de vendedores)")
        decisoes.append({"vendedor_antes": vend, "vendedor_depois": nome_c, "tipo": "impressao", "status": "pendente",
                         "similaridade": round(c["itens"], 3), "detalhe": txt})
    return vend, decisoes

# ---------------------------------------------------------------------------
# 6. Nomes de marca: a mesma marca escrita de jeitos diferentes (YSL = Yves Saint Laurent)
# ---------------------------------------------------------------------------

def apelidos(repo):
    """{grafia compactada: (chave oficial, nome oficial)} — carregado uma vez por requisição."""
    if getattr(repo, "_apelidos", None) is None:
        ap = {}
        for r in repo._todos("marca_apelidos", {"select": "apelido,marca,ignorar"}):
            if r["marca"] and not r["ignorar"]:
                ap[nubi.compacta(r["apelido"])] = (nubi.compacta(r["marca"]), r["marca"].strip().upper())
        repo._apelidos = ap
    return repo._apelidos


def unificar_marcas(repo, linhas, somar=False):
    """Troca cada grafia pelo nome oficial. somar=True (ranking): se duas grafias caem no
    mesmo relatório, vira uma linha só (vendas/unidades/vendedores somados, melhor posição)."""
    ap = apelidos(repo)
    if not ap:
        return linhas
    for l in linhas:
        k = l.get("marca_chave") or nubi.compacta(l.get("marca") or "")
        if k in ap:
            l["marca_original"] = l.get("marca")
            l["marca_chave"], l["marca"] = ap[k]
    if not somar:
        return linhas
    saida, vistos = [], {}
    for l in linhas:
        chave = (l.get("relatorio_id"), l["marca_chave"])
        if chave not in vistos:
            vistos[chave] = l
            saida.append(l)
            continue
        a = vistos[chave]
        for c in ("vendas", "unidades", "vendedores"):
            if l.get(c) is not None:
                a[c] = (a.get(c) or 0) + l[c]
        if l.get("posicao") and (not a.get("posicao") or l["posicao"] < a["posicao"]):
            a["posicao"] = l["posicao"]
    return saida


def _distancia(a, b):
    """Quantas letras trocar/pôr/tirar para ir de a até b (Levenshtein)."""
    ant = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        atual = [i]
        for j, cb in enumerate(b, 1):
            atual.append(min(ant[j] + 1, atual[j - 1] + 1, ant[j - 1] + (ca != cb)))
        ant = atual
    return ant[-1]


def grafia_parecida(a, b):
    """Duas chaves compactas parecem a mesma marca digitada diferente (ex.: LATAFFA x LATTAFA)."""
    import difflib
    if min(len(a), len(b)) < 5:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.88 or (min(len(a), len(b)) >= 6 and _distancia(a, b) <= 2)


def _iniciais(nome):
    return "".join(p[0] for p in re.split(r"[^A-Z0-9]+", nubi.sem_acento(nome).upper()) if p)


def _contem_palavras(x, y):
    """Um dos nomes aparece inteiro, em palavras, dentro do outro (WELLA / WELLA PROFISSIONAL)."""
    px, py = nubi.sem_acento(x).upper().split(), nubi.sem_acento(y).upper().split()
    if len(px) == len(py):
        return False
    curto, longo = (px, py) if len(px) < len(py) else (py, px)
    return any(longo[i:i + len(curto)] == curto for i in range(len(longo) - len(curto) + 1))


def ia_mesma_marca(a, b):
    """A IA (com pesquisa na web) diz se duas grafias são a mesma marca de perfume."""
    j, links, qual = ia.perguntar_json(
        f'No mercado de perfumes (Mercado Livre Brasil), "{a}" e "{b}" são a MESMA marca escrita de outro jeito '
        "(erro de digitação, sigla, nome curto/longo, com ou sem acento) ou são marcas DIFERENTES? Pesquise na web se "
        'precisar. Responda SOMENTE com JSON: {"mesma": true|false, "confianca": "alta|média|baixa", '
        '"motivo": "<1 frase em português>"}.')
    return {"mesma": bool(j.get("mesma")), "confianca": j.get("confianca") or "baixa",
            "motivo": j.get("motivo") or "", "fonte": links[0] if links else "", "ia": ia.nome(qual)}


def juntar_apelido(repo, apelido, marca):
    apelido, marca = apelido.strip().upper(), marca.strip().upper()
    repo._req("DELETE", "marca_apelidos", {"apelido": repo._eq(marca)})      # o oficial não pode ser apelido de outra
    repo._req("POST", "marca_apelidos", corpo=[{"apelido": apelido, "marca": marca, "ignorar": False}],
              prefer="resolution=merge-duplicates,return=minimal")
    repo._req("PATCH", "marca_apelidos", {"marca": repo._eq(apelido)}, corpo={"marca": marca})


def conferir_nomes_marcas(repo, limite=8):
    """Rotina diária (pedido do Bruno, 25/09): a IA confere as sugestões de Nomes de marcas; mesma marca com confiança alta
    por grafia parecida ou sigla = junta sozinha (dá para desfazer na tela); o resto fica para o Bruno, com a opinião da IA."""
    if not ia.disponivel():
        return "sem chave de IA"
    sug, _ = sugestoes_apelidos(repo)
    juntou, conferir = [], []
    for x in sug[:limite]:
        try:
            r = ia_mesma_marca(x["apelido"], x["marca"])
        except Exception:  # noqa: BLE001
            continue
        if r["mesma"] and r["confianca"] == "alta" and x["motivo"] in ("grafia parecida", "sigla"):
            juntar_apelido(repo, x["apelido"], x["marca"])
            juntou.append(f"{x['apelido']} → {x['marca']}")
        elif r["mesma"]:
            conferir.append(f"{x['apelido']} → {x['marca']} ({r['confianca']}: {r['motivo'][:90]})")
    if juntou or conferir:
        txt = "🔗 **Nomes de marcas (conferência diária)**\n"
        if juntou:
            txt += "Juntei (a IA confirmou com confiança alta; desfaz em Minhas marcas → Nomes de marcas): " + "; ".join(juntou) + "\n"
        if conferir:
            txt += "Para o Bruno conferir: " + "; ".join(conferir)
        try:
            repo._req("POST", "reuniao_mensagens", corpo=[{"autor": "Claude (marcas)", "texto": txt[:3500]}], prefer="return=minimal")
        except ErroNuvem:
            pass
    return (f"{len(juntou)} juntada(s)" + (f" ({', '.join(juntou)[:300]})" if juntou else "")
            + f"; {len(conferir)} para conferir; {len(sug)} sugestão(ões) na tela")


def sugestoes_apelidos(repo):
    """Pares de grafias que parecem a mesma marca, para você confirmar."""
    import difflib
    ap = apelidos(repo)
    decididos = {nubi.compacta(r["apelido"]) for r in repo._todos("marca_apelidos", {"select": "apelido"})}
    # cada grafia no último mês/período em que aparece, por fonte (ranking, vendedores, explorador)
    vistas = {}
    for r in repo._req("POST", "rpc/marcas_resumo", corpo={}) or []:
        k = nubi.compacta(r["marca"] or "")
        if not k:
            continue
        x = vistas.setdefault(k, {"nomes": {}, "fontes": set(), "info": {}})
        v = float(r["vendas"] or 0)
        x["nomes"][r["marca"]] = x["nomes"].get(r["marca"], 0) + v
        x["fontes"].add(r["fonte"])
        i = x["info"].get(r["fonte"])
        if not i or str(r["fim"] or r["mes"]) > str(i.get("fim") or i["mes"]):
            x["info"][r["fonte"]] = {"mes": str(r["mes"])[:10], "fim": str(r["fim"])[:10] if r["fim"] else None, "vendas": v,
                                     "vendedores": r["vendedores"], "posicao": r["posicao"]}
        elif r["fonte"] != "ranking":             # outra grafia com a mesma chave, mesmo período: soma
            i["vendas"] += v
    for x in vistas.values():
        x["nome"] = max(x["nomes"], key=x["nomes"].get)
        inf = x["info"]
        # para comparar tamanhos: o mês do ranking; sem ranking, o maior entre vendedores e explorador
        x["vendas"] = inf["ranking"]["vendas"] if "ranking" in inf else max(
            [inf[f]["vendas"] for f in ("vendedores", "explorador") if f in inf] or [0])
    chaves = [k for k in vistas if k not in ap]
    out = []
    for a in chaves:
        if a in decididos:
            continue
        for b in chaves:
            if a == b:
                continue
            A, B = vistas[a], vistas[b]
            # o ranking do Nubimetrics é o nome canônico; mas o próprio ranking tem erro de digitação (LATAFFA x LATTAFA,
            # 25/09): nome do ranking só vai para outro nome do ranking, e só por grafia parecida
            if "ranking" in A["fontes"] and "ranking" not in B["fontes"]:
                continue
            if re.sub(r"\D", "", a) != re.sub(r"\D", "", b):   # "212" e "212 VIP" não são grafias da mesma coisa
                continue
            motivo = None
            if len(a) <= 5 and len(B["nome"].split()) >= 2 and a == _iniciais(B["nome"]):
                motivo = "sigla"
            elif min(len(a), len(b)) >= 4 and _contem_palavras(A["nome"], B["nome"]) and \
                    ("ranking" in B["fontes"] or B["vendas"] >= A["vendas"]):
                motivo = "nome contido"      # um nome está dentro do outro; vai para o que mais vende
            elif grafia_parecida(a, b) and A["vendas"] <= B["vendas"]:
                motivo = "grafia parecida"
            if not motivo or ("ranking" in A["fontes"] and motivo != "grafia parecida"):
                continue
            # vai para o nome do ranking (o do mercado) ou, sem ranking, o que mais vende
            if "ranking" in A["fontes"] and "ranking" not in B["fontes"]:
                continue
            out.append({"apelido": A["nome"], "marca": B["nome"], "motivo": motivo,
                        "vendas_apelido": A["vendas"], "vendas_marca": B["vendas"],
                        "fontes_apelido": sorted(A["fontes"]), "fontes_marca": sorted(B["fontes"]),
                        "info_apelido": A["info"], "info_marca": B["info"]})
    ordem = {"sigla": 0, "grafia parecida": 1, "nome contido": 2}
    out.sort(key=lambda x: (ordem[x["motivo"]], "ranking" not in x["fontes_marca"], -x["vendas_marca"]))
    melhor = {}
    for x in out:                          # um destino por grafia: o mais provável
        melhor.setdefault(x["apelido"], x)
    out = sorted(melhor.values(), key=lambda x: (ordem[x["motivo"]], -x["vendas_apelido"]))
    return out[:80], sorted({v["nome"] for v in vistas.values()})


def rota_apelidos(repo, metodo, rota, q, corpo):
    if rota == "apelidos":
        lista = repo._todos("marca_apelidos", {"select": "*", "order": "marca,apelido"})
        sug, nomes = sugestoes_apelidos(repo)
        return {"apelidos": [r for r in lista if r["marca"] and not r["ignorar"]],
                "ignorados": [r for r in lista if r["ignorar"]], "sugestoes": sug, "marcas": nomes}
    d = json.loads(corpo or b"{}")
    apelido = (d.get("apelido") or "").strip().upper()
    if not apelido:
        raise ErroNuvem("Informe o nome da marca.")
    if rota == "apelido_salvar" and metodo == "POST":
        marca = (d.get("marca") or "").strip().upper()
        if not marca or nubi.compacta(marca) == nubi.compacta(apelido):
            raise ErroNuvem("Informe o nome oficial (diferente do apelido).")
        # o oficial não pode ser apelido de outra (evita cadeia YSL -> X -> Y)
        repo._req("DELETE", "marca_apelidos", {"apelido": repo._eq(marca)})
        repo._req("POST", "marca_apelidos", corpo=[{"apelido": apelido, "marca": marca, "ignorar": False}],
                  prefer="resolution=merge-duplicates,return=minimal")
        repo._req("PATCH", "marca_apelidos", {"marca": repo._eq(apelido)}, corpo={"marca": marca})
        return {"ok": True}
    if rota == "apelido_ignorar" and metodo == "POST":
        repo._req("POST", "marca_apelidos", corpo=[{"apelido": apelido, "marca": None, "ignorar": True}],
                  prefer="resolution=merge-duplicates,return=minimal")
        return {"ok": True}
    if rota == "apelido_apagar" and metodo == "POST":
        repo._req("DELETE", "marca_apelidos", {"apelido": repo._eq(apelido)})
        return {"ok": True}
    raise ErroNuvem("Rota desconhecida.", 404)

def _json(obj, status=200):
    def padrao(o):
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        return _limpo(o)
    return status, "application/json; charset=utf-8", json.dumps(obj, ensure_ascii=False,
                                                                 default=padrao).encode("utf-8"), {}
