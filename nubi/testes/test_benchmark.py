"""Mini-benchmark (card #15): mesmo conjunto de casos em 2 modelos, 1 linha por caso e modelo, custo NULL sem uso ou
sem preço (nunca zero) e acerto de cada tipo conferido contra o gabarito. Provedores falsos (nenhuma API de verdade)."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
os.environ.setdefault("OPENAI_API_KEY", "x")
import ia  # noqa: E402
import nubi_benchmark as nb  # noqa: E402
import nubi_web  # noqa: E402


class Repo:
    def __init__(self):
        self.t = {"ia_precos": [{"modelo": "claude-sonnet-5", "entrada": 2, "saida": 10},
                                {"modelo": "text-embedding-3-small", "entrada": 0.02, "saida": 0}],
                  "ia_benchmark_casos": [], "ia_benchmark_execucoes": []}

    def _req(self, m, t, q=None, corpo=None, prefer=None):
        if m == "POST":
            self.t[t] += json.loads(json.dumps(corpo))       # tem que ser JSON puro
        return []

    def _todos(self, t, q):
        xs = self.t[t]
        if "versao_casos" in q:
            xs = [r for r in xs if r["versao_casos"] == q["versao_casos"][3:]]
        return sorted(xs, key=lambda r: r.get("rodada") or "", reverse=True)


def _secoes(alerta, extra=""):
    itens = lambda t: [{"texto": t, "vendedor": "", "produto": "", "marca": ""}]
    return {"secoes": [{"tipo": s, "itens": itens(alerta if s == "alerta" else
                                                  f"LOJA AROMA subiu, PERFUMES BR caiu; Asad puxou e Club De Nuit pausado {extra}")}
                       for s, _, _ in nubi_web.SECOES_DIA]}


ALERTA_CERTO = "Club De Nuit Intense Man 105ml sem estoque em PERFUMES BR e LOJA AROMA: R$ 800/dia parado; Khamrah sem estoque, R$ 450/dia"
ALERTA_ERRADO = "Club De Nuit e Khamrah sem estoque; Asad em risco: R$ 1.900/dia"   # cita produto que está bem e inventa número


def _http_falso(url, corpo, cab, timeout=90):
    """Claude: resumo com uso, alerta SEM uso relatado. ChatGPT (sem preço cadastrado): resumo certo, alerta errado."""
    if "embeddings" in url:
        palavras = ("asad", "khamrah", "bourbon", "qahwa")
        vet = [[t.lower().count(p) for p in palavras] + [1] for t in corpo["input"]]
        return {"data": [{"index": i, "embedding": v} for i, v in enumerate(vet)], "model": corpo["model"],
                "usage": {"prompt_tokens": 70, "total_tokens": 70}}
    alerta = "21/09/2026" in corpo.get("input", "") or "21/09/2026" in json.dumps(corpo.get("messages", ""))
    if "anthropic" in url:
        r = {"model": "claude-sonnet-5-20260901", "stop_reason": "end_turn",
             "content": [{"type": "text", "text": json.dumps(_secoes(ALERTA_CERTO))}]}
        if not alerta:
            r["usage"] = {"input_tokens": 1000, "output_tokens": 500}
        return r
    return {"model": corpo["model"], "usage": {"input_tokens": 900, "output_tokens": 400},
            "output": [{"type": "message", "content": [{"type": "output_text",
                                                        "text": json.dumps(_secoes(ALERTA_ERRADO if alerta else ALERTA_CERTO))}]}]}


def _rodar_dois():
    ia._http_json = _http_falso
    repo = Repo()
    a = nb.rodar(repo, "claude:claude-sonnet-5")
    b = nb.rodar(repo, "chatgpt:gpt-novo")
    return repo, a, b


def test_mesmo_conjunto_em_dois_modelos_uma_linha_por_caso():
    repo, a, b = _rodar_dois()
    ex = repo.t["ia_benchmark_execucoes"]
    assert sorted((r["modelo"], r["caso_id"]) for r in ex) == sorted(
        (m, f"v1|{c}") for m in ("claude:claude-sonnet-5", "chatgpt:gpt-novo") for c in ("resumo_dia_1", "alerta_1"))
    assert {r["versao_casos"] for r in ex} == {"v1"} and len({r["id"] for r in repo.t["ia_benchmark_casos"]}) == 3
    for r in ex:
        assert isinstance(r["latencia_ms"], int) and r["latencia_ms"] >= 0 and r["acerto"] in (True, False) and not r["erro"]


def test_custo_null_sem_uso_ou_sem_preco_nunca_zero():
    repo, a, b = _rodar_dois()
    por = {(r["modelo"], r["tipo"]): r for r in repo.t["ia_benchmark_execucoes"]}
    r = por[("claude:claude-sonnet-5", "resumo_dia")]
    assert (r["tokens_in"], r["tokens_out"], r["custo_usd"]) == (1000, 500, 0.007)      # (1000×2 + 500×10)/1e6
    r = por[("claude:claude-sonnet-5", "alerta")]                                         # provedor não mandou o uso
    assert r["tokens_in"] is None and r["tokens_out"] is None and r["custo_usd"] is None
    r = por[("chatgpt:gpt-novo", "resumo_dia")]                                           # modelo sem preço cadastrado
    assert r["tokens_in"] == 900 and r["custo_usd"] is None


def test_acerto_de_cada_tipo_contra_o_gabarito():
    repo, a, b = _rodar_dois()
    por = {(r["modelo"], r["tipo"]): r for r in repo.t["ia_benchmark_execucoes"]}
    assert por[("claude:claude-sonnet-5", "resumo_dia")]["acerto"] is True
    assert por[("claude:claude-sonnet-5", "alerta")]["acerto"] is True
    assert por[("chatgpt:gpt-novo", "alerta")]["acerto"] is False and por[("chatgpt:gpt-novo", "alerta")]["nota"] == 0.3333
    # resumo sem uma das seções não acerta, mesmo citando tudo
    j = _secoes(ALERTA_CERTO)
    j["secoes"] = j["secoes"][:-1]
    assert nb.avaliar(nb.CASOS[0], j) == (False, 1.0)
    # alerta com número que não está na entrada não acerta
    assert nb.avaliar(nb.CASOS[1], _secoes("Club De Nuit e Khamrah sem estoque: R$ 999/dia"))[0] is False
    # junção: F1 dos pares
    ia._http_json = _http_falso
    repo2 = Repo()
    r = nb.rodar(repo2, "embed:text-embedding-3-small")["execucoes"]
    assert [(x["tipo"], x["acerto"], x["nota"], x["tokens_in"], x["custo_usd"]) for x in r] == [("juncao", True, 1.0, 70, 1e-06)]
    grupos = nb.CASOS[2]["gabarito"]["grupos"]
    assert nb.f1(nb.pares([grupos[0][:2]]), nb.pares(grupos)) == 0.4                      # 1 de 4 pares: P=1, R=0,25
    assert nb.f1(nb.pares(grupos + [["T:asad bourbon edp 100ml", "6291108735411"]]), nb.pares(grupos)) == 0.8889


def test_comparacao_lado_a_lado_lida_da_tabela():
    repo, a, b = _rodar_dois()
    c = nb.comparar(repo, "v1", ["claude:claude-sonnet-5", "chatgpt:gpt-novo"])
    pa, pb = c["por_tipo"]["claude:claude-sonnet-5"], c["por_tipo"]["chatgpt:gpt-novo"]
    assert pa["alerta"]["acertos"] == 1 and pb["alerta"]["acertos"] == 0 and pa["juncao"] is None
    assert pa["resumo_dia"]["custo_usd"] == 0.007 and pa["alerta"]["custo_usd"] is None
    linha = next(l for l in c["tabela"].splitlines() if l.startswith("| alerta · custo"))
    assert linha == "| alerta · custo | sem dados | sem dados |"
    assert "| juncao · acerto | não se aplica | não se aplica |" in c["tabela"]
    assert "US$ 0,0070" in c["tabela"]
    assert nubi_web.rota_agentes(repo, "GET", "agentes_benchmark", {}, b"")["tabela"] == nb.comparar(repo)["tabela"]


def test_modelo_de_producao_nao_muda():
    antes = (dict(ia.USO), os.environ.get("NUBI_IA_MODELO"), os.environ.get("NUBI_IA_MODELO_CLAUDE"))
    _rodar_dois()
    assert (dict(ia.USO), os.environ.get("NUBI_IA_MODELO"), os.environ.get("NUBI_IA_MODELO_CLAUDE")) == antes
    try:
        nb.rodar(Repo(), "gpt-sem-provedor")
        assert False, "candidato sem provedor deveria ser recusado"
    except nubi_web.ErroNuvem:
        pass


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
