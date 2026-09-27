# -*- coding: utf-8 -*-
"""Card #92: saúde do Mac mini servidor no Início (CPU, memória, disco, temperatura, agentes e alertas).
Sem rede e sem banco: Supabase falso e saídas falsas do top/vm_stat. Rodar: python3 nubi/testes/test_servidor_metricas.py"""
import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone

AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, AQUI)
os.environ.update(OPENAI_API_KEY="x", ANTHROPIC_API_KEY="x")

import nubi_web  # noqa: E402

_esp = importlib.util.spec_from_file_location("coletor", os.path.join(AQUI, "public", "coletor", "coletor.py"))
coletor = importlib.util.module_from_spec(_esp)
_esp.loader.exec_module(coletor)

AGORA = datetime(2026, 9, 27, 15, 0, tzinfo=timezone.utc)           # 12:00 de Brasília


class Repo:
    """Supabase falso: upsert por coletado_em+origem e leitura da mais recente."""
    def __init__(self):
        self.linhas = []

    def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
        assert tab == "servidor_metricas", tab
        if metodo == "POST":
            assert params == {"on_conflict": "coletado_em,origem"} and "merge-duplicates" in prefer
            for r in corpo:
                self.linhas = [x for x in self.linhas if (x["coletado_em"], x["origem"]) != (r["coletado_em"], r["origem"])] + [r]
            return None
        return sorted(self.linhas, key=lambda x: x["coletado_em"], reverse=True)[:params.get("limit")]


def leitura(**k):
    m = {"coletado_em": "2026-09-27T14:55:00+00:00", "origem": "mac_mini", "cpu_pct": 23.5, "mem_pct": 61.2,
         "disco_pct": 74.0, "temp_c": 52.0, "agentes": {"coletor": True, "vigia": True}}
    m.update(k)
    return m


def test_coleta_normal_grava_ok():
    repo = Repo()
    r = nubi_web.servidor_metricas_gravar(repo, leitura(), AGORA)
    assert len(repo.linhas) == 1 and r["status"] == "ok" and r["alertas"] == [] and r["faltantes"] == []
    assert (r["cpu_pct"], r["mem_pct"], r["disco_pct"], r["temp_c"]) == (23.5, 61.2, 74.0, 52.0)
    s = nubi_web.servidor_status(repo, AGORA)
    assert s["coletado_em"] == "2026-09-27T14:55:00+00:00" and s["atrasado"] is False and s["cpu_pct"] == 23.5


def test_mesmo_horario_faz_upsert():
    repo = Repo()
    nubi_web.servidor_metricas_gravar(repo, leitura(), AGORA)
    nubi_web.servidor_metricas_gravar(repo, leitura(cpu_pct=30.0), AGORA)
    assert len(repo.linhas) == 1 and repo.linhas[0]["cpu_pct"] == 30.0
    nubi_web.servidor_metricas_gravar(repo, leitura(coletado_em="2026-09-27T14:50:00+00:00"), AGORA)
    assert len(repo.linhas) == 2 and nubi_web.servidor_status(repo, AGORA)["cpu_pct"] == 30.0   # max coletado_em


def test_alertas_cpu_e_agente_ausente():
    r = nubi_web.servidor_metricas_gravar(Repo(), leitura(cpu_pct=92.0, agentes={"coletor": True, "vigia": False}), AGORA)
    assert r["status"] == "alerta" and r["faltantes"] == ["vigia"]
    assert r["alertas"] == ["CPU 92,0% (limite 90%)", "agente ausente: vigia"], r["alertas"]
    r = nubi_web.servidor_metricas_gravar(Repo(), leitura(mem_pct=90, disco_pct=95.5, temp_c=85), AGORA)
    assert len(r["alertas"]) == 3 and r["status"] == "alerta"
    r = nubi_web.servidor_metricas_gravar(Repo(), leitura(cpu_pct=89.9), AGORA)
    assert r["status"] == "ok"


def test_sem_temperatura_fica_none_nunca_zero():
    r = nubi_web.servidor_metricas_gravar(Repo(), leitura(temp_c=None, mem_pct="x", disco_pct=130), AGORA)
    assert r["temp_c"] is None and r["mem_pct"] is None and r["disco_pct"] is None and r["status"] == "ok"


def test_sem_envio_recente_e_sem_leitura():
    repo = Repo()
    assert nubi_web.servidor_status(repo, AGORA) is None                 # nunca mandou: "sem dados"
    nubi_web.servidor_metricas_gravar(repo, leitura(coletado_em="2026-09-27T14:40:00+00:00"), AGORA)
    assert nubi_web.servidor_status(repo, AGORA)["atrasado"] is True     # 20 min sem envio: "sem dados desde…"


def test_horario_no_futuro_descartado():
    repo = Repo()
    futuro = (AGORA + timedelta(minutes=6)).isoformat()
    assert nubi_web.servidor_metricas_gravar(repo, leitura(coletado_em=futuro), AGORA) is None and repo.linhas == []
    assert nubi_web.servidor_metricas_gravar(repo, leitura(coletado_em=(AGORA + timedelta(minutes=4)).isoformat()), AGORA)
    assert nubi_web.servidor_metricas_gravar(repo, leitura(coletado_em="lixo"), AGORA) is None


def test_inicio_traz_o_servidor_e_nao_quebra_sem_tabela():
    repo = Repo()
    nubi_web.servidor_metricas_gravar(repo, leitura(coletado_em=datetime.now(timezone.utc).isoformat()))

    class RepoInicio(Repo):
        def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
            if tab != "servidor_metricas":
                raise RuntimeError("fora do teste")
            return Repo._req(self, metodo, tab, params, corpo, prefer)

        def _todos(self, *a, **k):
            raise RuntimeError("fora do teste")
    ri = RepoInicio()
    ri.linhas = repo.linhas
    assert nubi_web.tela_inicio(ri)["servidor"]["cpu_pct"] == 23.5
    ri.linhas = []
    assert nubi_web.tela_inicio(ri)["servidor"] is None


def test_mac_tick_grava_e_tabela_ausente_nao_trava():
    chamadas = []

    class RepoTick:
        def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
            chamadas.append((metodo, tab))
            if tab == "servidor_metricas":
                raise nubi_web.ErroNuvem("Erro no banco (404): relation does not exist", 500)
            return []
    velhos = nubi_web.indexar_aos_poucos, nubi_web.ferreiro_proximo, nubi_web.atendimento
    nubi_web.indexar_aos_poucos = lambda repo: None
    nubi_web.ferreiro_proximo = lambda *a, **k: None

    class Atd:
        def __getattr__(self, n):
            return lambda repo: None
    nubi_web.atendimento = Atd()
    try:
        corpo = b'{"metricas": {"coletado_em": "2026-01-01T00:00:00+00:00", "cpu_pct": 10}}'
        assert nubi_web.rota_mac(RepoTick(), "POST", "mac_tick", {}, corpo, "t") == {"pendentes": [], "sala": []}
        assert ("POST", "servidor_metricas") in chamadas
    finally:
        nubi_web.indexar_aos_poucos, nubi_web.ferreiro_proximo, nubi_web.atendimento = velhos


TOP = """Processes: 512 total
CPU usage: 3.10% user, 5.20% sys, 91.70% idle
Processes: 512 total
CPU usage: 12.40% user, 11.10% sys, 76.50% idle
"""
VM = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                               10000.
Pages active:                            200000.
Pages inactive:                           40000.
Pages speculative:                        10000.
Pages wired down:                        100000.
"""


def test_coletor_le_top_e_vm_stat():
    assert coletor._cpu_top(TOP) == 23.5                                  # última amostra: 100 − 76,5
    assert coletor._cpu_top("") is None
    total = 16 * 1024 ** 3                                                # 16 GB = 1.048.576 páginas de 16 KB
    assert coletor._mem_vm_stat(VM, total) == round((1048576 - 60000) / 1048576 * 100, 1)
    assert coletor._mem_vm_stat("", total) is None and coletor._mem_vm_stat(VM, None) is None


def test_coletor_metricas_sem_temperatura():
    saidas = {"/usr/sbin/sysctl": str(16 * 1024 ** 3), "/usr/bin/top": TOP, "/usr/bin/vm_stat": VM}

    class Res:
        def __init__(self, cmd):
            self.stdout = saidas.get(cmd[0], "")
            self.returncode = 0 if cmd[-1] == "com.nubi.coletor.vigia" else 113
    velho = coletor.subprocess.run
    coletor.subprocess.run = lambda cmd, **k: Res(cmd)
    try:
        m = coletor._metricas_mac({"ollama": True})
    finally:
        coletor.subprocess.run = velho
    assert m["cpu_pct"] == 23.5 and m["temp_c"] is None and 0 <= m["disco_pct"] <= 100
    assert m["agentes"] == {"coletor": False, "vigia": True, "ollama": True}
    r = nubi_web.servidor_metricas_gravar(Repo(), m)
    assert r["status"] == "alerta" and r["temp_c"] is None
    assert r["alertas"] == ["memória 94,3% (limite 90%)", "agente ausente: coletor"], r["alertas"]


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
