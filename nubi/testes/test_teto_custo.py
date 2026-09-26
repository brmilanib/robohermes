# -*- coding: utf-8 -*-
"""
Teto de custo por provedor e regra de degradação (card #10), sem internet e sem banco: provedor falso em ia._http_json
e agentes_uso numa lista. Com o teto do DeepSeek estourado:
(a) texto/triagem responde no modelo local e fica registrado como 'local' (custo 0), nunca no DeepSeek;
(b) conferência de número e nível 3 ficam em espera, sem chamar o provedor, e o dono é avisado na Sala (1 vez);
(c) a soma do dia e do mês usa o dia de Brasília e não conta a mesma execução duas vezes;
(d) a aba Custos mostra o log por tarefa/rotina e "sem dados" (None) onde não há custo.

Rodar: python3 testes/test_teto_custo.py (na pasta nubi).
"""
import copy
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ia  # noqa: E402
import nubi_web  # noqa: E402


class Repo:
    def __init__(self, usos):
        self.usos = usos
        self.mensagens = []

    def _todos(self, tab, params=None, metodo="GET", corpo=None):
        if tab == "agentes_uso":
            gte = (params or {}).get("inicio", "gte.").split("gte.", 1)[1]
            return copy.deepcopy([u for u in self.usos if u["inicio"] >= gte])
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
        if tab == "reuniao_mensagens" and metodo == "POST":
            self.mensagens.extend(corpo)
            return []
        if tab == "reuniao_mensagens":
            return copy.deepcopy(self.mensagens)
        return []


CHAMADAS = []


def _provedor_falso(url, corpo, cab, timeout=90):
    CHAMADAS.append(url)
    if "ollama.com" in url:
        return {"model": corpo["model"], "message": {"content": "resposta local"}, "prompt_eval_count": 10, "eval_count": 5}
    return {"model": corpo["model"], "choices": [{"message": {"content": "resposta paga"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


def _hoje_br_utc(hora_br):
    """'inicio' (UTC) de hoje em Brasília à hora 'hora_br'."""
    d = nubi_web._agora_br().date()
    return (datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(hours=hora_br + 3)).isoformat()


def _cenario(usos_extra=()):
    os.environ.update({"NUBI_TETO_DEEPSEEK": "1/50", "DEEPSEEK_API_KEY": "x", "OLLAMA_API_KEY": "x"})
    os.environ.pop("NUBI_IA_MODELO_DEEPSEEK", None)
    usos = [{"id": 1, "agente": "deepseek", "modelo": "deepseek-flash", "origem": "rotina analise_foco",
             "inicio": _hoje_br_utc(1), "fim": _hoje_br_utc(1), "ok": True, "custo_usd": 1.20}] + list(usos_extra)
    repo = Repo(usos)
    ia._http_json = _provedor_falso
    nubi_web.ligar_registro_uso(repo, "teste")
    CHAMADAS.clear()
    return repo


def test_texto_cai_para_local_e_nunca_fica_no_deepseek():
    repo = _cenario()
    ia.USO["nivel"] = "triagem"
    texto, _, quem = ia.perguntar("resuma", web=False, qual="deepseek")
    assert (texto, quem) == ("resposta local", "local")
    assert CHAMADAS and all("ollama.com" in u for u in CHAMADAS), CHAMADAS          # o DeepSeek nem foi chamado
    novas = repo.usos[1:]
    assert [u["agente"] for u in novas] == ["local"] and novas[0]["custo_usd"] == 0.0, novas
    assert not repo.mensagens and ia.USO["local"] is False


def test_conferencia_e_nivel3_ficam_em_espera_e_avisam_o_dono_uma_vez():
    repo = _cenario()
    for nivel in ("conferencia", "nivel3"):
        ia.USO["nivel"] = nivel
        try:
            ia.perguntar("confira os números", web=False, qual="deepseek")
            raise AssertionError("devia ficar em espera")
        except ia.EmEspera as e:
            assert "teto diário do DeepSeek" in str(e), e
    assert CHAMADAS == [], CHAMADAS                                                  # sem chamar provedor nenhum
    esperas = [u for u in repo.usos if u["agente"] == "teto"]
    assert len(esperas) == 2 and all(u.get("custo_usd") is None for u in esperas)   # espera: "sem dados", não 0
    assert len(repo.mensagens) == 1 and "em espera" in repo.mensagens[0]["texto"], repo.mensagens   # mesmo provedor/tarefa: 1 aviso
    dec = nubi_web.inicio_decisoes(repo)["execucao"]["travadas_por_custo"]
    assert dec["total"] == 2, dec


def test_sem_nivel_fica_em_espera_por_seguranca():
    _cenario()
    ia.USO["nivel"] = None
    try:
        ia.perguntar("x", web=False, qual="deepseek")
        raise AssertionError("devia ficar em espera")
    except ia.EmEspera:
        pass
    assert CHAMADAS == []


def test_soma_usa_dia_de_brasilia_e_nao_conta_duas_vezes():
    d = nubi_web._agora_br().date()
    ontem_23h_br = (datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(hours=2)).isoformat()  # 02h UTC de hoje
    repo = _cenario([{"id": 2, "agente": "deepseek", "modelo": "deepseek-flash", "origem": "sala", "inicio": ontem_23h_br,
                      "ok": True, "custo_usd": 0.5}])
    repo.usos.append(copy.deepcopy(repo.usos[0]))                                    # mesma execução (id 1) vinda duas vezes
    dia, mes = nubi_web._gasto_provedor(repo, "deepseek")
    assert round(dia, 2) == 1.20, dia                                                # 23h de ontem em Brasília fica fora de hoje
    assert round(mes, 2) == (1.70 if d.day > 1 else 1.20), mes


def test_abaixo_do_teto_chama_o_provedor_normal():
    repo = _cenario()
    os.environ["NUBI_TETO_DEEPSEEK"] = "5/50"
    ia.USO["nivel"] = "conferencia"
    texto, _, quem = ia.perguntar("x", web=False, qual="deepseek")
    assert (texto, quem) == ("resposta paga", "deepseek") and repo.usos[-1]["agente"] == "deepseek"


def test_aba_custos_mostra_log_espera_e_sem_dados():
    repo = _cenario()
    ia.USO["nivel"] = "texto"
    ia.perguntar("resuma", web=False, qual="deepseek")
    ia.USO["nivel"] = "conferencia"
    try:
        ia.perguntar("confira", web=False, qual="deepseek")
    except ia.EmEspera:
        pass
    r = nubi_web._custos_painel(repo)
    p = {x["id"]: x for x in r["provedores"]}
    assert p["deepseek"]["estourado"] and p["deepseek"]["hoje"] == 1.2 and p["deepseek"]["teto_dia"] == 1.0, p["deepseek"]
    assert p["sonnet"]["hoje"] is None and p["sonnet"]["teto_dia"] is None                         # sem dados, nunca 0
    assert len(r["espera"]) == 1 and "DeepSeek" in r["espera"][0]["motivo"], r["espera"]
    log = {(x["origem"], x["provedor"]): x for x in r["log"]}
    assert log[("rotina analise_foco", "deepseek")]["custo"] == 1.2
    assert log[("teste", "local")]["custo"] == 0.0, log


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
    print("tudo ok")
