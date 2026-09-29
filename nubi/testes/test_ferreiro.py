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
    assert c.cmd_programar(type("A", (), {"id": "81"})(), c.ler_config()) == 1
    # não programa; devolve o card para a fila com o motivo (26/09: a fila automática espera 1 h antes de tentar de novo)
    assert len(passos) == 1 and passos[0]["status"] == "aprovada" and "limite do dia" in passos[0]["texto"]


def test_astra_programa_no_branch_dele():
    """Astra (Codex falso): muda a tela sem commit; o coletor faz o commit, testa e entrega em astra/card-N."""
    import shutil
    shutil.rmtree(c.PASTA / "projeto", ignore_errors=True)
    passos, sala = _preparar(_claude_falso())
    exe = TMP / "codex"
    exe.write_text("#!/bin/sh\nout=''\nwhile [ $# -gt 0 ]; do if [ \"$1\" = --output-last-message ]; then out=$2; fi; shift; done\n"
                   "echo tela nova > nubi/tela.txt\necho '## Feito\nPainel maior' > \"$out\"\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    c._codex_bin = lambda: str(exe)
    c._credencial = lambda site, cfg=None: ("bruno", "sk-falsa") if site in ("openai", "anthropic") else ("", "")
    assert c.cmd_programar(type("A", (), {"id": "90"})(), c.ler_config(), quem="astra") == 0
    assert "astra/card-90" in passos[-1]["texto"] and passos[-1]["status"] == "em_teste" and "Painel maior" in passos[-1]["texto"]
    assert all(p_["quem"] == "astra" for p_ in passos)                    # o servidor sabe que é o Astra, não o Ferreiro
    ramos = subprocess.run(["git", "branch", "-a"], cwd=c.REPO_GIT, capture_output=True, text=True).stdout
    assert "astra/card-90" in ramos
    assert c._cards_astra_hoje(c.ler_config()) == 1 and sala[-1]["autor"] == "Astra (design)"


def test_astra_sem_codex_devolve_para_a_fila():
    passos, _ = _preparar(_claude_falso())
    c._codex_bin = lambda: None
    assert c.cmd_programar(type("A", (), {"id": "91"})(), c.ler_config(), quem="astra") == 1
    assert passos[-1]["status"] == "aprovada" and "npm install -g @openai/codex" in passos[-1]["texto"]


def test_sobras_no_clone_vao_para_o_stash():
    """26/09: sobras de outro card travavam a troca de branch e o Ferreiro trabalhava num branch velho."""
    passos, sala = _preparar(_claude_falso())
    projeto = c.PASTA / "projeto"
    if not (projeto / ".git").exists():
        assert c.cmd_programar(type("A", (), {"id": "81"})(), c.ler_config()) == 0
    (projeto / "nubi" / "coletor.txt").write_text("sobra de outro card\n")
    c._gasto_ferreiro(c.ler_config())
    c.salvar_config({})
    assert c.cmd_programar(type("A", (), {"id": "82"})(), c.ler_config()) == 0
    assert passos[-1]["status"] == "em_teste" and "ferreiro/card-82" in passos[-1]["texto"]
    atual = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=projeto, capture_output=True, text=True).stdout.strip()
    assert atual == "ferreiro/card-82"
    assert "sobras antes do card 82" in subprocess.run(["git", "stash", "list"], cwd=projeto, capture_output=True, text=True).stdout


def test_ferreiro_responde_a_conversa_direta():
    passos, sala = _preparar(_claude_falso(commita=False))
    chamadas = []
    velho = c.api

    def api(token, rota, params=None, corpo=None, metodo=None, timeout=300):
        chamadas.append((rota, params, corpo))
        if rota == "conversa_contexto":
            return {"historico": [{"autor": "voce", "texto": "por que o #89 parou?", "criado_em": "2026-09-26T17:00:00+00:00"}],
                    "quadro": "QUADRO: #89 em_desenvolvimento\n", "instrucao_cards": "FERRAMENTA CARDS"}
        return velho(token, rota, params, corpo, metodo, timeout)
    c.api = api
    assert c.cmd_ferreiro_conversa(None, c.ler_config()) == 0
    post = [x for x in chamadas if x[0] == "reuniao_postar"][-1][2]
    assert post["direta"] == "claude_mac" and post["autor"] == "Ferreiro (Claude no Mac)" and "Causa" in post["texto"]
    assert c._gasto_ferreiro(c.ler_config()) == 1.25


def test_teste_que_falha_aparece_com_o_nome():
    repo = Path(tempfile.mkdtemp())
    (repo / "nubi" / "testes").mkdir(parents=True)
    (repo / "nubi" / "testes" / "test_ok.py").write_text("print('ok')\n")
    (repo / "nubi" / "testes" / "test_ruim.py").write_text("raise AssertionError('botão sumiu')\n")
    (repo / "nubi" / "testes" / "fumaca.py").write_text("print('ok')\n")
    r = c._testes_projeto(repo, dict(os.environ))
    assert r.returncode == 1 and "test_ruim.py" in r.stdout and "botão sumiu" in r.stdout and "test_ok.py" not in r.stdout
    (repo / "nubi" / "testes" / "test_ruim.py").write_text("print('ok')\n")
    assert c._testes_projeto(repo, dict(os.environ)).returncode == 0


def test_caixa_que_falha_nao_derruba_o_ambiente_pronto():
    venv = c.PASTA / "venv-projeto"
    (venv / "bin").mkdir(parents=True, exist_ok=True)
    (venv / "bin" / "python").write_text("")
    (venv / ".pronto").write_text("assinatura-velha")
    original, py_original = c.instalar_da_caixa, c._python_novo
    c._python_novo = lambda: sys.executable

    def falha(*a, **k):
        raise c.Falha("sem roda para este Python")
    c.instalar_da_caixa = falha
    try:
        assert _AMBIENTE_ORIGINAL(Path(tempfile.mkdtemp())) == venv / "bin"
    finally:
        c.instalar_da_caixa, c._python_novo = original, py_original


def test_astra_com_codex_saindo_com_erro_mas_trabalho_feito_entrega():
    """26/09: o Codex saía com erro porque o sandbox bloqueava o commit dele; o coletor faz o commit e entrega igual."""
    import shutil
    shutil.rmtree(c.PASTA / "projeto", ignore_errors=True)
    c.salvar_config({})
    passos, sala = _preparar(_claude_falso())
    exe = TMP / "codex_erro"
    exe.write_text("#!/bin/sh\nout=''\nwhile [ $# -gt 0 ]; do if [ \"$1\" = --output-last-message ]; then out=$2; fi; shift; done\n"
                   "echo tela nova > nubi/tela.txt\necho '## Feito\nCommit bloqueado' > \"$out\"\nexit 1\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    c._codex_bin = lambda: str(exe)
    c._credencial = lambda site, cfg=None: ("bruno", "sk-falsa") if site in ("openai", "anthropic") else ("", "")
    assert c.cmd_programar(type("A", (), {"id": "93"})(), c.ler_config(), quem="astra") == 0
    assert passos[-1]["status"] == "em_teste" and "astra/card-93" in passos[-1]["texto"]


def test_deepseek_programa_o_estoque_pelo_aider_com_a_api_dele():
    """29/09 (Bruno: "libera a branch de código pra ele de estoque"): o DeepSeek programa com o Aider (o Codex 0.157 recusou a
    API de chat do DeepSeek), no branch deepseek/card-N, e o card fica com ele (deepseek_mac)."""
    import shutil
    shutil.rmtree(c.PASTA / "projeto", ignore_errors=True)
    c.salvar_config({})
    passos, sala = _preparar(_claude_falso())
    args_f, env_f = TMP / "aider_args.txt", TMP / "aider_env.txt"
    exe = TMP / "aider_ds"
    exe.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\" > " + str(args_f) + "\nenv > " + str(env_f) + "\n"
                   "echo estoque novo > nubi/estoque_tela.txt\necho 'Applied edit to nubi/estoque_tela.txt'\nexit 0\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    c._aider_bin = lambda: str(exe)
    c._credencial = lambda site, cfg=None: ("bruno", "sk-ds-falsa") if site == "deepseek" else ("", "")
    assert c.cmd_programar(type("A", (), {"id": "130"})(), c.ler_config(), quem="deepseek") == 0
    assert passos[-1]["status"] == "em_teste" and "deepseek/card-130" in passos[-1]["texto"] and passos[-1]["quem"] == "deepseek_mac"
    a = args_f.read_text()
    assert "deepseek/deepseek-v4-pro" in a and "--no-auto-commits" in a and "SÓ na parte do estoque" in a
    e = env_f.read_text()
    assert "DEEPSEEK_API_KEY=sk-ds-falsa" in e and "OPENAI_API_KEY" not in e and "ANTHROPIC_API_KEY" not in e
    # sem o Aider ou sem a chave: não começa e devolve o card com o motivo
    c._credencial = lambda site, cfg=None: ("", "")
    assert c.cmd_programar(type("A", (), {"id": "131"})(), c.ler_config(), quem="deepseek") == 1
    assert "guardar-senha deepseek" in passos[-1]["texto"] and passos[-1]["quem"] == "deepseek_mac"
    c._aider_bin = lambda: None
    assert c.cmd_programar(type("A", (), {"id": "132"})(), c.ler_config(), quem="deepseek") == 1
    assert "aider-install" in passos[-1]["texto"]


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
