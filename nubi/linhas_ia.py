# -*- coding: utf-8 -*-
"""
Revisão geral das linhas de produto por IA (01/10, Bruno: "Light Blue 100 ml juntou feminino, masculino, Intense e Capri
in Love; precisa de uma revisão geral nessas marcas e produtos").

As linhas de cada marca (marcas_config.linhas) eram detectadas por frequência de palavras nos títulos, o que deixava lixo
("blue femin", "blue for", "edpi") e nomes curtos demais ("light blue" engole "Light Blue Intense" e "Light Blue Capri in
Love"). Aqui a IA lê os títulos que mais vendem da marca e devolve os nomes OFICIAIS das linhas, do mais específico para
o mais genérico ("Light Blue Eau Intense Pour Homme" antes de "Light Blue"), cada um como [chave, rótulo]. Só entra chave
que aparece em pelo menos um título (normalizado); o resto é descartado. O que havia antes fica guardado em
ia_resumos `linhas_ia|<marca>` (antes/depois) para desfazer. Depois, a marca é reconsolidada.
"""
import json
from datetime import datetime, timezone

import nubi

CHAVE = "linhas_ia|"
DIAS_VALIDADE = 30
MAX_TITULOS = 150
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["linhas", "observacao"],
          "properties": {"observacao": {"type": "string"},
                         "linhas": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["chave", "rotulo"],
                                                               "properties": {"chave": {"type": "string"}, "rotulo": {"type": "string"}}}}}}


def titulos_da_marca(repo, marca, sid=None):
    """[(titulo, un)] do último export da marca, só perfumaria da própria marca (sem 'Outra marca' e sem outra categoria)."""
    snaps = repo.snapshots(marca)
    if snaps.empty:
        return [], None
    sid = sid or int(snaps["id"].max())
    out = {}
    for a in repo._todos("anuncios", {"select": "titulo,un,tipo,categoria", "snapshot_id": repo._eq(sid)}):
        if (a.get("categoria") or "") or str(a.get("tipo") or "").startswith("Outra"):
            continue
        t = " ".join(str(a.get("titulo") or "").split())
        if t:
            out[t] = out.get(t, 0) + int(float(a.get("un") or 0))
    return sorted(out.items(), key=lambda x: -x[1]), sid


def pedido(marca, atuais, titulos):
    lt = "\n".join(f"- ({un} un.) {t}" for t, un in titulos[:MAX_TITULOS])
    la = ", ".join(r for _, r in atuais) or "(nenhuma)"
    return (f"Marca de perfumaria: {nubi.nome_bonito(marca)}.\n"
            "Abaixo estão os títulos de anúncios do Mercado Livre desta marca que mais vendem (unidades no período). Monte a lista de "
            "LINHAS DE PRODUTO (nomes oficiais dos perfumes) para agrupar os anúncios. Regras:\n"
            "1. Uma linha = um perfume com nome próprio. Variações com nome próprio são linhas separadas: 'Light Blue', 'Light Blue "
            "Intense', 'Light Blue Eau Intense Pour Homme', 'Light Blue Capri in Love', 'Light Blue Pour Homme', 'Light Blue Forever'. "
            "Feminino e masculino com o mesmo nome base são linhas diferentes quando o título distingue (Pour Homme / For Men / Masculino).\n"
            "2. `chave` = o trecho EXATO que aparece nos títulos (minúsculas, sem acento, como está escrito nos anúncios: 'light blue capri "
            "in love'); pode dar mais de uma chave para a mesma linha quando os vendedores escrevem diferente ('for men' e 'pour homme' "
            "→ mesmo rótulo). `rotulo` = o nome bonito oficial.\n"
            "3. Ordem: da chave mais longa/específica para a mais curta. Nunca invente linha que não está nos títulos. Não inclua "
            "tipo (EDP/EDT), volume, gênero solto ('masculino'), 'perfume', 'kit', 'decant' nem o nome da marca sozinho.\n"
            "4. Deixe de fora contratipos e anúncios de outras marcas.\n"
            f"Linhas de hoje (detectadas por frequência, podem ter lixo): {la}\n\nTítulos:\n{lt}")


def validar(linhas, titulos):
    """Só chave que aparece em algum título (normalizado); sem repetição; da mais longa para a mais curta."""
    tn = [" " + nubi.normalizar(t) + " " for t, _ in titulos]
    out, vistas = [], set()
    for x in linhas or []:
        k = nubi.normalizar(str(x.get("chave") or "")).strip()
        r = " ".join(str(x.get("rotulo") or "").split())[:60]
        if not k or k in vistas or len(k) < 2 or not r:
            continue
        if not any(f" {k} " in t for t in tn):
            continue
        if len(k.split()) > 5:                       # 01/10 (Jequiti): título inteiro como "linha" não é linha
            continue
        vistas.add(k)
        out.append([k, r])
    out.sort(key=lambda kr: -len(kr[0]))
    return out


def revisar_marca(repo, marca, perguntar, cfg=None):
    """Pede as linhas à IA, valida, guarda antes/depois, grava e reconsolida a marca. -> dict com o resultado."""
    marca = nubi.chave_marca(marca)
    cfg = cfg if cfg is not None else repo.carregar_config()
    atuais = list((cfg.get(marca) or {}).get("linhas") or [])
    titulos, sid = titulos_da_marca(repo, marca)
    if len(titulos) < 3:
        return {"marca": marca, "ok": False, "motivo": "poucos títulos de perfumaria da marca"}
    j, quem = perguntar(pedido(marca, atuais, titulos), SCHEMA)
    novas = validar(j.get("linhas"), titulos)
    if len(novas) < 1:
        return {"marca": marca, "ok": False, "motivo": "a IA não devolveu linha que apareça nos títulos", "ia": quem}
    reg = {"marca": marca, "em": datetime.now(timezone.utc).isoformat(), "ia": quem, "snapshot": sid, "antes": atuais, "depois": novas,
           "descartadas": sorted({nubi.normalizar(str(x.get("chave") or "")).strip() for x in (j.get("linhas") or [])} - {k for k, _ in novas})[:20],
           "observacao": str(j.get("observacao") or "")[:500]}
    repo._req("POST", "ia_resumos", corpo=[{"chave": CHAVE + marca, "ia": quem or "ia", "criado_em": reg["em"], "texto": json.dumps(reg, ensure_ascii=False)}],
              prefer="resolution=merge-duplicates,return=minimal")
    cfg.setdefault(marca, {})["linhas"] = novas
    repo.salvar_config(cfg, marca)
    nubi.reconsolidar(repo, cfg, [marca])
    return {**reg, "ok": True}


def desfazer(repo, marca):
    marca = nubi.chave_marca(marca)
    r = (repo._req("GET", "ia_resumos", {"select": "texto", "chave": f"eq.{CHAVE}{marca}"}) or [None])[0]
    reg = json.loads(r["texto"]) if r and r.get("texto") else None
    if not reg:
        return {"ok": False, "motivo": "sem revisão guardada"}
    cfg = repo.carregar_config()
    cfg.setdefault(marca, {})["linhas"] = reg.get("antes") or []
    repo.salvar_config(cfg, marca)
    nubi.reconsolidar(repo, cfg, [marca])
    repo._req("DELETE", "ia_resumos", {"chave": f"eq.{CHAVE}{marca}"})
    return {"ok": True, "marca": marca, "linhas": cfg[marca]["linhas"]}


def revisadas(repo):
    """{marca: em} das marcas já revisadas pela IA."""
    out = {}
    for r in repo._todos("ia_resumos", {"select": "chave,criado_em", "chave": f"like.{CHAVE}%"}):
        out[str(r["chave"])[len(CHAVE):]] = r.get("criado_em")
    return out


def pendentes(repo, agora=None):
    """Marcas por unidades no último export, sem revisão nos últimos DIAS_VALIDADE dias."""
    agora = agora or datetime.now(timezone.utc)
    feitas = revisadas(repo)
    snaps = repo.snapshots()
    if snaps.empty:
        return []
    ult = snaps.sort_values("id").groupby("marca").tail(1)
    marcas = []
    for _, s in ult.iterrows():
        m = s["marca"]
        em = feitas.get(m)
        try:
            if em and (agora - datetime.fromisoformat(str(em).replace("Z", "+00:00"))).days < DIAS_VALIDADE:
                continue
        except ValueError:
            pass
        marcas.append(m)
    return marcas


def revisar_pendentes(repo, perguntar, max_marcas=10):
    """Rotina `linhas_ia`: revisa até `max_marcas` marcas por vez (as de maior venda primeiro). -> texto."""
    ms = pendentes(repo)
    if not ms:
        return "todas as marcas revisadas nos últimos 30 dias"
    un = {}
    try:
        for r in repo._req("POST", "rpc/nubi_un_por_marca", corpo={}) or []:
            un[r["marca"]] = int(r.get("un") or 0)
    except Exception:  # noqa: BLE001
        pass
    ms.sort(key=lambda m: -un.get(m, 0))
    cfg = repo.carregar_config()
    out = []
    for m in ms[:max_marcas]:
        try:
            x = revisar_marca(repo, m, perguntar, cfg)
            out.append(f"{nubi.nome_bonito(m)}: {len(x['depois'])} linha(s)" if x.get("ok") else f"{nubi.nome_bonito(m)}: {x.get('motivo')}")
        except Exception as e:  # noqa: BLE001
            out.append(f"{nubi.nome_bonito(m)}: erro {str(e)[:120]}")
    return f"{len(ms)} pendente(s); " + "; ".join(out)
