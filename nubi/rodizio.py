# -*- coding: utf-8 -*-
"""
Rodízio de vendedores seguidos no Nubimetrics (02/10, Bruno: "o coletor para de seguir um vendedor já atualizado e segue o
que você quer coletar, e assim vai revezando"; "quando você segue um novo ele traz todos os dados do passado"; "quando
volta a seguir, tem todos os dados que não coletou"; "pode seguir e deixar de seguir quantas vezes quiser por dia").

Fase 1 (combinado com o Bruno): só as VAGAS LIVRES do grupo (17 seguidos de 20 = 3 vagas). Os seguidos de antes nunca são
mexidos: o rodízio só solta quem ELE mesmo seguiu (`ativos`). Caminho na tela (vídeo do Bruno, 02/10):
  seguir  = Explorador → busca pelo codinome → ícone do vendedor (roxo) → "Adicionar Grupo" → ADICIONAR no grupo "perfumes";
  soltar  = ícone do vendedor (check verde) → "Parar de seguir" (ou REMOVER no mesmo quadro).
Solta só depois que a coleta diária trouxe o histórico dele (venda diária até o último dia coletado de todos e 28+ dias).

Estado em ia_resumos `rodizio|estado`; o servidor só PLANEJA (`plano`), quem clica é o coletor (`coletor rodizio`).
"""
import json
import re
from datetime import date, datetime, timedelta, timezone

ESTADO = "rodizio|estado"
MAX_VAGAS = 3                       # fase 1: só as vagas livres (20 - 17 seguidos)
LIMITE = 20                         # seguidos no plano do Nubimetrics
DIAS_MIN = 28                       # dias de venda diária guardados para considerar o vendedor "baixado"
REPETIR_DIAS = 30                   # quem já passou pelo rodízio volta para a fila depois disso
CODINOME = re.compile(r"^[A-Z]+(\.[A-Z]+){2}$")
PADRAO = {"ligado": False, "vagas": MAX_VAGAS, "grupo": "perfumes", "ativos": {}, "feitos": {}, "historico": []}


def _agora():
    return datetime.now(timezone.utc).isoformat()


def ler(repo):
    r = (repo._req("GET", "ia_resumos", {"select": "texto", "chave": repo._eq(ESTADO)}) or [None])[0]
    e = json.loads(r["texto"]) if r and r.get("texto") else {}
    return {**PADRAO, **e}


def gravar(repo, e):
    e["historico"] = (e.get("historico") or [])[-200:]
    repo._req("POST", "ia_resumos", corpo=[{"chave": ESTADO, "ia": "rodízio de seguidos",
                                            "texto": json.dumps(e, ensure_ascii=False)}],
              prefer="resolution=merge-duplicates,return=minimal")


def hifen(codinome):
    """O relatório do seguido traz o codinome com hífen (AIRON-AMBAR-INQUIETANTE); o Explorador, com ponto."""
    return str(codinome or "").replace(".", "-")


def fila(repo, e, ids_seguidos, hoje=None, n=30):
    """Observados que mais vendem (último export de cada marca, sem repetir anúncio), que não são seguidos, não estão no
    rodízio agora e não passaram por ele nos últimos REPETIR_DIAS dias; só quem tem codinome (é por ele que a busca acha)."""
    hoje = hoje or date.today()
    out = []
    for o in repo._req("POST", "rpc/nubi_observados", corpo={}) or []:
        vid = str(o.get("vendedor_id") or "")
        if not vid or vid in ids_seguidos:
            continue
        cod = next((x for x in o.get("nomes") or [] if CODINOME.match(str(x or ""))), None)
        if not cod or cod in e["ativos"]:
            continue
        f = (e["feitos"].get(cod) or {}).get("soltou")
        if f and (hoje - date.fromisoformat(f[:10])).days < REPETIR_DIAS:
            continue
        out.append({"codinome": cod, "vendedor_id": vid, "un": int(o.get("un") or 0), "marcas": int(o.get("marcas") or 0)})
    out.sort(key=lambda x: -x["un"])
    return out[:n]


def baixado(repo, codinome):
    """Tem a venda diária até o último dia que a coleta já trouxe para todos, com DIAS_MIN+ dias guardados."""
    ult = (repo._req("GET", "vend_vendas_dia", {"select": "data", "order": "data.desc", "limit": 1}) or [{}])[0].get("data")
    dias = repo._todos("vend_vendas_dia", {"select": "data", "vendedor": repo._eq(hifen(codinome))})
    datas = {str(x["data"])[:10] for x in dias}
    return bool(ult) and str(ult)[:10] in datas and len(datas) >= DIAS_MIN, len(datas)


def seguidos_agora(repo, dias=5):
    """Vendedores com venda diária coletada nos últimos dias = quem está no grupo hoje (os do rodízio também)."""
    ult = (repo._req("GET", "vend_vendas_dia", {"select": "data", "order": "data.desc", "limit": 1}) or [{}])[0].get("data")
    if not ult:
        return set()
    desde = (date.fromisoformat(str(ult)[:10]) - timedelta(days=dias)).isoformat()
    return {str(x["vendedor"]) for x in repo._todos("vend_vendas_dia", {"select": "vendedor", "data": f"gte.{desde}"})}


def plano(repo, ids_seguidos):
    e = ler(repo)
    if not e.get("ligado"):
        return {"ligado": False, "seguir": [], "soltar": [], "grupo": e["grupo"]}
    soltar = []
    for cod in list(e["ativos"]):
        ok, n = baixado(repo, cod)
        e["ativos"][cod]["dias"] = n
        if ok:
            soltar.append(cod)
    # vagas reais = 20 − os seguidos que NÃO são do rodízio (o Bruno pode ter seguido alguém à mão: AIRON, 02/10)
    meus = {hifen(c) for c in e["ativos"]}
    fixos = len(seguidos_agora(repo) - meus)
    vagas = max(0, min(int(e.get("vagas") or 0), MAX_VAGAS, LIMITE - fixos))
    livres = max(0, vagas - (len(e["ativos"]) - len(soltar)))
    seguir = fila(repo, e, ids_seguidos)[:livres]
    return {"ligado": True, "grupo": e["grupo"], "seguir": seguir, "soltar": soltar, "seguidos_fixos": fixos, "vagas": vagas}


def registrar(repo, d):
    """O coletor conta o que fez: {seguiu: [codinome], soltou: [codinome], erros: [texto]}."""
    e = ler(repo)
    agora = _agora()
    for cod in d.get("seguiu") or []:
        e["ativos"][cod] = {"desde": agora}
        e["historico"].append({"em": agora, "seguiu": cod})
    for cod in d.get("soltou") or []:
        info = e["ativos"].pop(cod, {})
        e["feitos"][cod] = {"seguiu": info.get("desde"), "soltou": agora, "dias": info.get("dias")}
        e["historico"].append({"em": agora, "soltou": cod})
    for erro in d.get("erros") or []:
        e["historico"].append({"em": agora, "erro": str(erro)[:300]})
    gravar(repo, e)
    return {"ok": True, "ativos": list(e["ativos"])}


def configurar(repo, d):
    e = ler(repo)
    if "ligado" in d:
        e["ligado"] = bool(d["ligado"])
    if "vagas" in d:
        e["vagas"] = max(0, min(int(d["vagas"]), MAX_VAGAS))
    gravar(repo, e)
    return e
