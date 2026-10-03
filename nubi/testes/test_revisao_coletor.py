"""03/10 (Bruno: "o Codex ir aprendendo a cada dia o que o coletor faz e ir melhorando o código"): revisão diária —
números do dia sem IA, Codex só lendo (sandbox read-only), cards PROPOSTA + aprendizados + post na Sala."""
import json
import os
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
os.environ["NUBI_TOKEN"] = "t"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor  # noqa: E402

P = coletor.PASTA
hoje = date.today().isoformat()
(P / "coletor.log").write_text("\n".join([f"{hoje} 12:21:25   o download se perdeu (TargetClosedError); baixando direto pelo link"] * 30
                                         + [f"{hoje} 12:04:43 FALHOU: Relatório de vendas do Gestor: nenhum mês",
                                            "2026-01-01 10:00:00 linha de outro dia"]) + "\n")
(P / "comandos").mkdir()
(P / "comandos" / "540.log").write_text("FALHOU: algo\n")
(P / "comandos" / "540.log.rc").write_text("1")
(P / "comandos" / "541.log").write_text("OK\n")
(P / "comandos" / "541.log.rc").write_text("0")
(P / "despachante.json").write_text(json.dumps({"rodando": {}, "nomes": {"540": "gestor_relatorio", "541": "gestor_painel"}}))
r = coletor.resumo_do_dia()
assert r["linhas_log"] == 31 and r["ok"] == 1 and r["erros"] == 1
assert r["repetidas"][0]["vezes"] == 30 and "TargetClosedError" in r["repetidas"][0]["mensagem"]
assert any("FALHOU" in f for f in r["falhas"]) and {c["comando"] for c in r["comandos"]} == {"gestor_relatorio", "gestor_painel"}

chamadas, rodou = [], []
coletor.api = lambda token, rota, params=None, corpo=None, **k: chamadas.append((rota, corpo)) or {"id": 170}
coletor.astra_pronto = lambda cfg=None: (True, "")
coletor._credencial = lambda site, cfg=None: ("u", "sk-x")
coletor._codex_bin = lambda: "codex"


class R:
    stdout = stderr = ""
    returncode = 0


def run_falso(argv, **k):
    rodou.append(argv)
    Path(argv[argv.index("--output-last-message") + 1]).write_text(json.dumps({
        "relatorio": "Hoje o histórico baixou vendas; o download se perdeu 30 vezes.",
        "aprendizados": [{"titulo": "UpSeller fecha a aba no download", "texto": "TargetClosedError; o link direto resolve"}],
        "melhorias": [{"titulo": "Baixar direto pelo link de primeira", "descricao": "30 tentativas perdidas", "ganho": "~15 min/dia", "risco": "baixo"}]}))
    return R()


coletor.subprocess.run = run_falso
assert coletor.cmd_revisao_coletor(None, {}) == 0
a = rodou[0]
assert a[a.index("--sandbox") + 1] == "read-only" and "TargetClosedError" in a[-1]
card = [c for r_, c in chamadas if r_ == "reuniao_tarefa_salvar"][0]
assert card["status"] == "proposta" and card["area"] == "coletor" and card["titulo"].startswith("Coletor: Baixar direto")
assert any(r_ == "conhecimento_salvar" for r_, _ in chamadas) and any(r_ == "reuniao_postar" for r_, _ in chamadas)
assert json.loads(coletor.REVISAO_ULTIMA.read_text())["cards"] == ["#170 Baixar direto pelo link de primeira"]
assert coletor.comando_mac("revisao_coletor")[-1] == "revisao-coletor"
print("ok revisão diária do coletor")
