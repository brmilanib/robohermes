"""Ferreiro (Claude Code no Mac, pela API): pega o card, corrige num branch próprio, testa e entrega para o Chefe.
Roda sem Mac, sem API e sem GitHub: Claude Code falso (script), repositório git local e nubi falso."""
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402

TMP = Path(tempfile.mkdtemp())
_AMBIENTE_ORIGINAL = c._ambiente_projeto


def _sh(*cmd, cwd=None):
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def _repo_falso():
    """Repositório 'GitHub' local com a branch do nubi e testes que passam."""
    base = Path(tempfile.mkdtemp())
    origem, trab = base / "origem.git", base / "trab"
    _sh("git", "init", "--bare", str(origem))
    _sh("git", "init", "-b", c.BRANCH_NUBI, str(trab))
    (trab / "nubi" / "testes").mkdir(parents=True)
    (trab / "nubi" / "testes" / "test_ok.py").write_text("print('ok')\n")
    (trab / "nubi" / "testes" / "fumaca.py").write_text("print('fumaça ok')\n")
    (trab / "nubi" / "coletor.txt").write_text("com erro\n")
    for cmd in (["git", "add", "-A"], ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "base"],
                ["git", "push", str(origem), c.BRANCH_NUBI]):
        _sh(*cmd, cwd=trab)
    return origem


def _claude_falso(commita=True):
    """'claude -p' falso: corrige o arquivo, faz commit e devolve o JSON com custo, como o de verdade."""
    exe = TMP / ("claude" if commita else "claude_nada")
    acao = ("echo corrigido > nubi/coletor.txt && git add -A && git -c user.name=f -c user.email=f@f commit -qm 'Corrige' && "
            if commita else "")
    saida = json.dumps({"result": "## Causa\nX\n## Solução\nY", "total_cost_usd": 1.25})
    (TMP / "saida.json").write_text(saida)
    exe.write_text("#!/bin/sh\n" + acao + f"cat {TMP / 'saida.json'}\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return str(exe)


def _preparar(claude):
    passos, sala = [], []
    c.REPO_GIT = str(_repo_falso())
    c._claude_bin = lambda: claude
    c._ambiente_projeto = lambda repo: Path(sys.executable).parent      # no Mac: venv com as bibliotecas do projeto
    c._credencial = lambda site, cfg=None: ("bruno", "sk-ant-falsa") if site == "anthropic" else ("", "")
    c.token_nubi = lambda cfg: "T"

    def api(token, rota, params=None, corpo=None, metodo=None, timeout=300):
        if rota == "tarefa_eventos":
            return {"tarefa": {"id": 81, "titulo": "🩺 Coletor: gestor falhando — X", "descricao": "erro X"}, "eventos": []}
        (passos if rota == "tarefa_mac_passo" else sala).append(corpo)
        return {}
    c.api = api
    c.salvar_config({})
    return passos, sala


def test_ferreiro_corrige_e_entrega_no_branch():
    import shutil
    shutil.rmtree(c.PASTA / "projeto", ignore_errors=True)
    passos, sala = _preparar(_claude_falso())
    assert c.cmd_programar(type("A", (), {"id": "81"})(), c.ler_config()) == 0
    assert passos[0]["status"] == "em_desenvolvimento" and passos[-1]["status"] == "em_teste"
    assert "ferreiro/card-81" in passos[-1]["texto"] and "US$ 1.25" in passos[-1]["texto"]
    ramos = subprocess.run(["git", "branch", "-a"], cwd=c.REPO_GIT, capture_output=True, text=True).stdout
    assert "ferreiro/card-81" in ramos and c.BRANCH_NUBI in ramos       # entregou no branch próprio
    base = subprocess.run(["git", "show", f"{c.BRANCH_NUBI}:nubi/coletor.txt"], cwd=c.REPO_GIT, capture_output=True, text=True).stdout
    assert base.strip() == "com erro"                                   # a branch do nubi não foi mexida
    assert c._gasto_ferreiro(c.ler_config()) == 1.25 and "Chefe" in sala[-1]["texto"]


def test_ferreiro_sem_commit_devolve_para_o_chefe():
    import shutil
    shutil.rmtree(c.PASTA / "projeto", ignore_errors=True)
    passos, sala = _preparar(_claude_falso(commita=False))
    assert c.cmd_programar(type("A", (), {"id": "81"})(), c.ler_config()) == 1
    assert passos[-1]["status"] == "aprovada" and passos[-1]["tipo"] == "erro_teste"


def test_python_velho_pede_brew():
    c._python_novo = lambda: None
    import shutil
    d = Path(tempfile.mkdtemp())
    shutil.rmtree(c.PASTA / "venv-projeto", ignore_errors=True)
    try:
        _AMBIENTE_ORIGINAL(d)
        assert False, "tinha que pedir o Python novo"
    except c.Falha as e:
        assert "brew install python@3.12" in str(e)


def test_teto_do_dia():
    passos, sala = _preparar(_claude_falso())
    c._gasto_ferreiro(c.ler_config(), 10.0)
    assert c.cmd_programar(type("A", (), {"id": "81"})(), c.ler_config()) == 1 and not passos


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
