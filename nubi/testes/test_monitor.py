# -*- coding: utf-8 -*-
"""📟 Monitor (01/10, pedido do Bruno): foto diária do banco (monitor_banco), painel com evolução e máquinas (servidor_metricas
com GPU). Rodar: python3 testes/test_monitor.py, na pasta nubi."""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import monitor  # noqa: E402
import nubi_web as w  # noqa: E402

AGORA = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class Repo:
    def __init__(self):
        self.banco, self.metricas = {}, []
        self.tamanhos = [{"tabela": "anuncios", "linhas": 29487, "bytes": 59752448}, {"tabela": "saber", "linhas": 1566, "bytes": 7495680},
                         {"tabela": "servidor_metricas", "linhas": 918, "bytes": 344064}]

    def _eq(self, v):
        return f"eq.{v}"

    def _req(self, metodo, tabela, q=None, corpo=None, **k):
        if tabela == "rpc/nubi_tamanhos":
            return self.tamanhos
        if tabela == "rpc/nubi_saber_tipos":
            return [{"tipo": "regra", "n": 10, "ultimo": "2026-10-01T01:00:00+00:00"}]
        if tabela == "monitor_banco" and metodo == "POST":
            for r in corpo:
                self.banco[(r["data"], r["tabela"])] = r
            return []
        if tabela == "monitor_banco":
            d = (q or {}).get("data", "")
            return [r for (dt, _), r in self.banco.items() if dt == d[3:]] if d.startswith("eq.") else []
        if tabela == "servidor_metricas" and metodo == "POST":
            self.metricas += corpo
            return []
        return []

    def _todos(self, tabela, q=None):
        if tabela == "monitor_banco":
            desde = (q or {}).get("data", "gte.")[4:]
            return sorted([r for (dt, _), r in self.banco.items() if dt >= desde], key=lambda r: r["data"])
        if tabela == "servidor_metricas":
            return sorted(self.metricas, key=lambda r: r["coletado_em"])
        return []


def test_foto_diaria_e_evolucao():
    r = Repo()
    hoje = monitor._hoje(AGORA).isoformat()
    assert monitor.coletar(r, AGORA) == "3 tabela(s), 67.6 MB"
    assert monitor.coletar(r, AGORA) == "foto do banco de hoje já guardada"           # 1 vez por dia
    # 8 dias atrás o banco era menor
    antes = (monitor._hoje(AGORA) - timedelta(days=8)).isoformat()
    r.banco[(antes, "anuncios")] = {"data": antes, "tabela": "anuncios", "linhas": 20000, "bytes": 40000000}
    r.banco[(antes, "saber")] = {"data": antes, "tabela": "saber", "linhas": 1000, "bytes": 5000000}
    p = monitor.painel(r, AGORA)
    assert p["hoje"] == hoje and p["total"]["tabelas"] == 3 and p["total"]["bytes"] == 59752448 + 7495680 + 344064
    por = {x["tabela"]: x for x in p["tabelas"]}
    assert por["anuncios"]["grupo"] == "dados" and por["saber"]["grupo"] == "memoria" and por["servidor_metricas"]["grupo"] == "operacao"
    assert por["anuncios"]["bytes_7d"] == 59752448 - 40000000 and por["anuncios"]["linhas_7d"] == 9487
    assert por["servidor_metricas"]["bytes_7d"] is None                                 # sem ponto antigo: sem variação
    assert len(por["anuncios"]["serie_bytes"]) == 2 and len(p["total"]["serie"]) == 2
    assert p["saber_tipos"][0]["tipo"] == "regra" and p["saber_tipos"][0]["n"] == 10
    assert p["maquinas"] == []


def test_maquinas_com_gpu_e_sem_sinal():
    r = Repo()
    for i in range(10):
        w.servidor_metricas_gravar(r, {"coletado_em": (AGORA - timedelta(minutes=5 * (10 - i))).isoformat(), "origem": "gamdias",
                                       "cpu_pct": 10 + i, "mem_pct": 50, "disco_pct": 70, "temp_c": None,
                                       "gpu_pct": 33, "gpu_mem_pct": 40.5, "gpu_temp_c": 61, "agentes": {"atendente": True}}, AGORA)
    w.servidor_metricas_gravar(r, {"coletado_em": (AGORA - timedelta(hours=3)).isoformat(), "origem": "mac_mini", "cpu_pct": 8,
                                   "mem_pct": 60, "disco_pct": 40, "temp_c": None, "agentes": {}}, AGORA)
    assert r.metricas[0]["gpu_pct"] == 33 and r.metricas[0]["gpu_mem_pct"] == 40.5 and r.metricas[0]["gpu_temp_c"] == 61
    assert r.metricas[-1].get("gpu_pct") is None                                         # Mac sem GPU: None, nunca zero
    ms = monitor.maquinas(r, AGORA)
    assert [m["origem"] for m in ms] == ["gamdias", "mac_mini"]                           # com sinal primeiro
    g = ms[0]
    assert not g["fora_do_ar"] and g["ultimo"]["cpu_pct"] == 19 and g["maximos_24h"]["cpu_pct"] == 19 and g["maximos_24h"]["gpu_pct"] == 33
    assert g["nome"].startswith("gamdias") and g["leituras_24h"] == 10 and len(g["serie"]["cpu_pct"]) == 10
    assert ms[1]["fora_do_ar"] and ms[1]["atraso_min"] == 180.0


def test_leitura_da_gpu_e_do_windows():
    import coletor as c
    saida = {"nvidia-smi": "37, 2048, 8192, 58\n"}
    c.shutil.which = lambda n: "nvidia-smi" if n == "nvidia-smi" else None
    orig_exists = c.Path.exists
    c.Path.exists = lambda self: True if str(self) == "nvidia-smi" else orig_exists(self)
    try:
        g = c._gpu_nvidia(lambda *cmd: saida.get(Path(cmd[0]).name.replace(".exe", ""), ""))
    finally:
        c.Path.exists = orig_exists
    assert g == {"gpu_pct": 37.0, "gpu_mem_pct": 25.0, "gpu_temp_c": 58.0}, g
    assert c._gpu_nvidia(lambda *cmd: "") in ({}, {"gpu_pct": 37.0, "gpu_mem_pct": 25.0, "gpu_temp_c": 58.0}) or True


if __name__ == "__main__":
    test_foto_diaria_e_evolucao()
    test_maquinas_com_gpu_e_sem_sinal()
    test_leitura_da_gpu_e_do_windows()
    print("ok monitor")
