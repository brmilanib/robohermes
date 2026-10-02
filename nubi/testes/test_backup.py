"""02/10 (Bruno: "uma cópia aqui no meu Mac e uma no meu Drive"): coletor backup — banco em páginas (token do ML fora),
código com todo o histórico (git bundle), arquivo único no Mac e cópia na pasta do Drive, guardando só as últimas."""
import gzip
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "public" / "coletor"))
import coletor  # noqa: E402

tmp = Path(tempfile.mkdtemp())
DADOS = {"ia_resumos": [{"chave": "estoque|markup", "texto": "{}"}, {"chave": "meli|conta", "texto": "SEGREDO"}],
         "anuncios": [{"id": i, "titulo": f"anúncio {i}"} for i in range(2500)]}
pedidos = []


def rest_falso(token, t, params=None):
    pedidos.append((t, params["order"], params["offset"]))
    return DADOS[t][params["offset"]:params["offset"] + params["limit"]]


# um repositório git local no lugar do GitHub
origem = tmp / "origem"
origem.mkdir()
for c in (["git", "init", "-q", "-b", "principal"], ["git", "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "um"]):
    subprocess.run(c, cwd=origem, check=True)

coletor.token_nubi = lambda cfg: "t"
coletor.tabelas_do_banco = lambda token: {"anuncios": ["id"], "ia_resumos": ["chave"]}
coletor._rest = rest_falso
coletor.REPO_GIT = str(origem)
coletor.BACKUP_DIR = tmp / "nubi-backup"
coletor.BACKUP_MANTER = 2
drive = tmp / "Meu Drive"
drive.mkdir()
coletor._drive_dir = lambda: drive

# cópias antigas: só as 2 últimas ficam (contando a de hoje); arquivo de outro nome nunca é apagado
coletor.BACKUP_DIR.mkdir()
for d in ("2026-01-04", "2026-01-11", "2026-01-18"):
    (coletor.BACKUP_DIR / f"nubi-{d}.tar.gz").write_bytes(b"x")
(coletor.BACKUP_DIR / "minhas-notas.txt").write_text("não apagar")

assert coletor.cmd_backup(None, {}) == 0
arqs = sorted(p.name for p in coletor.BACKUP_DIR.glob("nubi-*.tar.gz"))
hoje = coletor.date.today().isoformat()
assert arqs == ["nubi-2026-01-18.tar.gz", f"nubi-{hoje}.tar.gz"], arqs
assert (coletor.BACKUP_DIR / "minhas-notas.txt").exists()
assert (drive / "nubi-backup" / f"nubi-{hoje}.tar.gz").exists()
assert not (coletor.BACKUP_DIR / f"nubi-{hoje}").exists()          # a pasta de trabalho some, fica só o .tar.gz
assert [p for p in pedidos if p[0] == "anuncios"] == [("anuncios", "id", 0), ("anuncios", "id", 1000), ("anuncios", "id", 2000)]

with tarfile.open(coletor.BACKUP_DIR / f"nubi-{hoje}.tar.gz") as tar:
    nomes = tar.getnames()
    base = f"nubi-{hoje}"
    assert f"{base}/codigo.bundle" in nomes and f"{base}/LEIA-ME.txt" in nomes, nomes
    linhas = gzip.decompress(tar.extractfile(f"{base}/banco/anuncios.jsonl.gz").read()).decode().splitlines()
    assert len(linhas) == 2500 and json.loads(linhas[0])["titulo"] == "anúncio 0"
    ia = gzip.decompress(tar.extractfile(f"{base}/banco/ia_resumos.jsonl.gz").read()).decode()
    assert "estoque|markup" in ia and "SEGREDO" not in ia and "meli|conta" not in ia      # o token do ML não sai do banco
    resumo = json.loads(tar.extractfile(f"{base}/resumo.json").read())
    assert resumo["tabelas"] == {"anuncios": 2500, "ia_resumos": 1} and resumo["codigo"] == "ok", resumo
    tar.extract(f"{base}/codigo.bundle", tmp / "x")
out = subprocess.run(["git", "bundle", "verify", str(tmp / "x" / base / "codigo.bundle")], capture_output=True, text=True)
assert out.returncode == 0, out.stderr

# sem o Google Drive para computador: a cópia do Mac sai do mesmo jeito e o resultado avisa
coletor._drive_dir = lambda: None
assert coletor.cmd_backup(None, {}) == 1
assert any("Google Drive para computador não encontrado" in x for x in coletor.LOG)
assert "backup" in coletor.comando_mac("backup")
print("ok backup")
