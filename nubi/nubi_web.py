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
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime

import pandas as pd

import nubi

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

    def salvar_config(self, cfg, marca=None):
        marcas = [marca] if marca else list(cfg)
        corpo = [{"marca": m, "linhas": cfg[m].get("linhas", []),
                  "atualizado_em": datetime.now().isoformat()} for m in marcas]
        self._req("POST", "marcas_config", corpo=corpo,
                  prefer="resolution=merge-duplicates,return=minimal")

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
    df = nubi.ler_snapshot(repo, atual["id"])
    dias = int(atual["dias"])
    df.attrs["dias"] = dias
    df_ant = nubi.ler_snapshot(repo, anterior["id"]) if anterior is not None else None
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
            "produto": prod, "categoria": a["cat"], "linha": a["linha"], "tipo": a["tipo"],
            "volume": a["volume"], "tamanho": a["tamanho"], "genero": a["genero"],
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
            "produto": x["prod"], "categoria": a["cat"], "genero": a["genero"], "tamanho": a["tamanho"],
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
            "categoria": a["cat"], "genero": a["genero"], "faixa": faixa(q[2])})
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
                              nubi.categoria_de(df_ant.loc[df_ant["produto"] == prod, "tipo"].iloc[0]))})
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

    # Anúncios
    anuncios = []
    for r in df.sort_values("un", ascending=False).to_dict("records"):
        anuncios.append({
            "produto": r["produto"], "categoria": nubi.categoria_de(r["tipo"]), "genero": r["genero"],
            "confianca": r["confianca"], "titulo": r["titulo"], "codigo": r["cod"], "vendedor": r["vendedor"],
            "marca_anuncio": r["marca_anuncio"], "gtin": r["gtin"], "un": r["un"], "fat": r["fat"],
            "preco": r["preco"], "catalogo": r["catalogo"], "full": r["full"],
            "loja_oficial": r["loja_oficial"], "internacional": r["internacional"]})

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


def atender(metodo, rota, q, corpo, token):
    """Devolve (status, tipo de conteúdo, bytes, cabeçalhos extras)."""
    try:
        repo = RepoSupabase(token)
        if rota == "painel":
            # A tabela acesso só devolve a linha de quem está liberado (RLS).
            if not repo._req("GET", "acesso", {"select": "email", "limit": 1}):
                raise ErroNuvem("Este e-mail ainda não tem acesso ao nubi. Peça para liberar.", 403)
            return _json(repo.painel())

        if rota == "relatorio":
            _preparar(repo)
            return _json(relatorio(repo, q["marca"]))

        if rota == "importar" and metodo == "POST":
            log = _preparar(repo)
            cfg = repo.carregar_config()
            nome = q.get("arquivo") or "upload.csv"
            m = nubi.PADRAO_NOME.match(re.sub(r"\.csv$", "", nome, flags=re.I))

            def marca_periodo(sugestao):
                marca = nubi.chave_marca(q.get("marca") or (m.group(1).replace("_", " ") if m else sugestao))
                if not marca:
                    raise ErroNuvem("Informe a marca.")
                ini = _data(q.get("inicio") or (m.group(2) if m else ""), "Data inicial")
                fim = _data(q.get("fim") or (m.group(3) if m else ""), "Data final")
                if fim < ini:
                    raise ErroNuvem("A data final é anterior à inicial.")
                return marca, ini, fim

            avisar = nubi.avisar
            avisar(nome)
            marca = nubi.importar_dados(repo, cfg, nome, corpo, marca_periodo)
            pendentes = []
            if marca:
                pendentes = [g for g in nubi.gtins_em_duvida(repo, marca) if g[0] not in nubi.INFO_GTIN]
                if pendentes:
                    avisar(f"    Em dúvida: {len(pendentes)} GTIN(s) com títulos que não batem entre si. "
                           f"Use \"Pesquisar GTINs\" na aba Dúvidas.")
            return _json({"marca": marca, "log": log, "duvidas": len(pendentes)})

        if rota == "pesquisar" and metodo == "POST":
            log = _preparar(repo)
            marca = q.get("marca")
            lista = [g for g in (q.get("gtin") or "").split(",") if g.strip()] or None
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


def _json(obj, status=200):
    def padrao(o):
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        return _limpo(o)
    return status, "application/json; charset=utf-8", json.dumps(obj, ensure_ascii=False,
                                                                 default=padrao).encode("utf-8"), {}
