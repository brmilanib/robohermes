# -*- coding: utf-8 -*-
"""
Conector Gemini para criativos (card #14), sem internet e sem banco de verdade: Gemini falso em ia._http_json e
agentes_uso/ia_precos/ia_resumos numa lista (mesmo padrão do test_teto_custo.py).

(a) dry-run gera 1 imagem, salva o rascunho em ia_resumos e não publica nada;
(b) o custo da chamada aparece na aba Custos (provedor 'gemini', origem 'teste');
(c) a mesma credencial não escreve em vend_vendas_dia, vend_grupo_dia nem produto_grupos (3 tentativas negadas);
(d) com o teto do mês esgotado, a API do Gemini não é chamada e o bloqueio fica registrado.

Rodar: python3 testes/test_criativo.py (na pasta nubi).
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import criativo  # noqa: E402
import ia  # noqa: E402
import nubi_web  # noqa: E402


class Repo:
    def __init__(self, usos=(), precos=()):
        self.usos = list(usos)
        self.precos = list(precos)
        self.resumos = []

    def _todos(self, tab, params=None, metodo="GET", corpo=None):
        if tab == "agentes_uso":
            gte = (params or {}).get("inicio", "gte.").split("gte.", 1)[1]
            return [dict(u) for u in self.usos if u["inicio"] >= gte]
        if tab == "ia_precos":
            return [dict(p) for p in self.precos]
        return []

    def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
        if tab == "agentes_uso" and metodo == "POST":
            for c in corpo:
                self.usos.append(dict(c, id=len(self.usos) + 1))
            return [{"id": len(self.usos)}]
        if tab == "agentes_uso" and metodo == "PATCH":
            u = next(x for x in self.usos if x["id"] == int(params["id"].split(".")[1]))
            u.update(corpo)
            return []
        if tab == "ia_resumos" and metodo == "POST":
            self.resumos.extend(corpo)
            return []
        if tab == "reuniao_mensagens":
            return []
        raise AssertionError(f"escrita inesperada em {tab} ({metodo})")


CHAMADAS = []
_RESPOSTA_PADRAO = {"candidates": [{"content": {"parts": [{"text": "Perfume Lattafa em destaque, tom dourado."},
                                                          {"inlineData": {"mimeType": "image/png", "data": "aW1hZ2Vt"}}]},
                                    "finishReason": "STOP"}],
                     "usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 5}}


def _gemini_falso(url, corpo, cab, timeout=90):
    CHAMADAS.append(url)
    assert "key=" not in url, "a chave da API não pode ir na URL (vaza em log de erro)"
    assert cab.get("x-goog-api-key") == "chave-de-teste"
    return dict(_RESPOSTA_PADRAO, model=corpo["model"])


def _cenario(usos_extra=(), precos=({"modelo": "gemini-2.5-flash-image", "entrada": 0.3, "saida": 2.5},)):
    os.environ["GEMINI_API_KEY"] = "chave-de-teste"
    os.environ.pop("NUBI_TETO_GEMINI", None)
    repo = Repo(usos=usos_extra, precos=precos)
    ia._http_json = _gemini_falso
    nubi_web.ligar_registro_uso(repo, "teste")
    CHAMADAS.clear()
    return repo


def test_dry_run_gera_imagem_e_salva_rascunho_sem_publicar():
    repo = _cenario()
    r = criativo.gerar(repo, {"prompt": "Post de Instagram do perfume Lattafa Asad"})
    assert r["ok"] and r["dry_run"] is True and r["chave"].startswith("criativo|")
    assert len(repo.resumos) == 1
    rasc = repo.resumos[0]
    assert rasc["chave"] == r["chave"] and rasc["ia"] == "gemini"
    assert rasc["dados"]["imagem_b64"] == "aW1hZ2Vt" and rasc["dados"]["dry_run"] is True
    assert rasc["dados"]["publicado"] is False                    # dry-run nunca publica
    assert CHAMADAS and "generativelanguage.googleapis.com" in CHAMADAS[0]


def test_sem_prompt_nao_chama_a_api():
    repo = _cenario()
    try:
        criativo.gerar(repo, {"prompt": "  "})
        raise AssertionError("devia recusar prompt vazio")
    except nubi_web.ErroNuvem:
        pass
    assert CHAMADAS == [] and repo.resumos == []


def test_custo_da_chamada_aparece_na_aba_custos():
    repo = _cenario()
    criativo.gerar(repo, {"prompt": "Post de Instagram do perfume Lattafa Asad"})
    esperado = round((20 * 0.3 + 5 * 2.5) / 1e6, 6)                # custo real da chamada (tokens x ia_precos)
    assert repo.usos[-1]["custo_usd"] == esperado, repo.usos[-1]   # gravado certinho em agentes_uso (log #17)
    r = nubi_web._custos_painel(repo)
    p = {x["id"]: x for x in r["provedores"]}
    assert "gemini" in p, p                                        # card #14: aparece como qualquer outro provedor
    assert p["gemini"]["hoje"] is not None and p["gemini"]["mes"] is not None, p["gemini"]    # nunca "sem dados"
    log = {(x["origem"], x["provedor"]): x for x in r["log"]}
    assert log[("teste", "gemini")]["chamadas"] == 1, log


def test_bloqueia_escrita_nas_3_tabelas_de_venda():
    class RepoQueNuncaDeveSerChamado:
        def _req(self, *a, **k):
            raise AssertionError("não devia nem chegar ao repo real")

    seguro = criativo._RepoSemVendas(RepoQueNuncaDeveSerChamado())
    negadas = 0
    for tabela, metodo in (("vend_vendas_dia", "POST"), ("vend_grupo_dia", "PATCH"), ("produto_grupos", "DELETE")):
        try:
            seguro._req(metodo, tabela, corpo=[{"x": 1}])
            raise AssertionError(f"devia negar escrita em {tabela}")
        except criativo.EscritaBloqueada:
            negadas += 1
    assert negadas == 3


def test_teto_do_mes_esgotado_nao_chama_a_api():
    agora = datetime.now(timezone.utc)
    usos = [{"id": 1, "agente": "gemini", "modelo": "gemini-2.5-flash-image", "origem": "criativo",
             "inicio": (agora - timedelta(hours=1)).isoformat(), "ok": True, "custo_usd": 5.0}]
    repo = _cenario(usos_extra=usos)
    os.environ["NUBI_TETO_GEMINI"] = "/5"                          # só teto do mês, US$ 5 já usados
    try:
        ia.gemini_gerar_imagem("Post de Instagram do perfume Lattafa Asad")
        raise AssertionError("devia ficar em espera (teto do mês esgotado)")
    except ia.EmEspera as e:
        assert "Gemini" in str(e), e
    assert CHAMADAS == []                                          # nem chegou a chamar a API
    esperas = [u for u in repo.usos if u["agente"] == "teto"]
    assert len(esperas) == 1 and esperas[0].get("custo_usd") is None    # bloqueio registrado, sem custo (sem dados)


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
    print("tudo ok")
