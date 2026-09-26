"""Card #28: caixa de pacotes e bibliotecas aprovadas. O coletor instala só o que está em public/coletor/caixa.txt, a
partir da cópia local (wheelhouse), com o hash conferido pelo pip; pacote fora da lista é recusado. Roda sem internet:
rodas (wheels) falsas num wheelhouse temporário e página falsa com o código real da aba Conhecimento."""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "public" / "coletor"))
import coletor as c  # noqa: E402

CAIXA = RAIZ / "public" / "coletor" / "caixa.txt"
TMP = Path(tempfile.mkdtemp())


def _roda(wh, nome, versao="1.0"):
    """Roda (wheel) mínima de um pacote puro, como as que ficam no wheelhouse do Mac. Devolve o sha256."""
    mod, info = nome.replace("-", "_"), f"{nome.replace('-', '_')}-{versao}.dist-info"
    arq = wh / f"{mod}-{versao}-py3-none-any.whl"
    with zipfile.ZipFile(arq, "w") as z:
        z.writestr(f"{mod}/__init__.py", f"NOME = {nome!r}\n")
        z.writestr(f"{info}/METADATA", f"Metadata-Version: 2.1\nName: {nome}\nVersion: {versao}\n")
        z.writestr(f"{info}/WHEEL", "Wheel-Version: 1.0\nGenerator: teste\nRoot-Is-Purelib: true\nTag: py3-none-any\n")
        z.writestr(f"{info}/RECORD", f"{mod}/__init__.py,,\n{info}/METADATA,,\n{info}/WHEEL,,\n{info}/RECORD,,\n")
    return hashlib.sha256(arq.read_bytes()).hexdigest()


def test_caixa_tem_versao_fixa_e_hash():
    linhas = [x for x in CAIXA.read_text().splitlines() if x.strip() and not x.startswith("#")]
    assert linhas, "a caixa está vazia"
    for x in linhas:
        assert re.match(r"^[A-Za-z0-9_.\-]+==\S+ --hash=sha256:[0-9a-f]{64}\s+#", x), x
    nomes = {c._nome_pacote(x) for x in linhas}
    assert {"pandas", "openpyxl", "playwright"} <= nomes            # site + coletor
    assert "# ollama: hermes3:8b" in CAIXA.read_text()               # modelos do Ollama do Mac
    for m in c.MODELOS_OK:
        assert f"# ollama: {m}" in CAIXA.read_text(), m


def test_recusa_pacote_fora_da_lista():
    txt = CAIXA.read_text()
    assert c.fora_da_caixa(["pandas==3.0.6", "Typing_Extensions", "playwright"], txt) == []
    assert c.fora_da_caixa(["requests", "pandas"], txt) == ["requests"]
    chamou = []
    velho, c.subprocess.run = c.subprocess.run, lambda *a, **k: chamou.append(a)
    try:
        c.instalar_da_caixa(sys.executable, CAIXA, TMP / "wh-nada", pacotes=["requests"])
        assert False, "tinha que recusar o pacote fora da caixa"
    except c.Falha as e:
        assert "requests" in str(e) and "Bruno" in str(e)
    finally:
        c.subprocess.run = velho
    assert chamou == [], "não pode nem chamar o pip com pacote fora da caixa"


def test_instala_so_da_copia_local_com_hash():
    wh = TMP / "wheelhouse"
    wh.mkdir()
    h = _roda(wh, "pacote-caixa")
    _roda(wh, "intruso")
    caixa = TMP / "caixa.txt"
    caixa.write_text(f"pacote-caixa==1.0 --hash=sha256:{h}  # coletor · teste\n")
    venv = TMP / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True, capture_output=True, timeout=300)
    py = venv / "bin" / "python"
    c.instalar_da_caixa(py, caixa, wh)               # --no-index: sem internet, só do wheelhouse
    r = subprocess.run([str(py), "-c", "import pacote_caixa; print(pacote_caixa.NOME)"], capture_output=True, text=True)
    assert r.stdout.strip() == "pacote-caixa", r.stderr
    # o pip também recusa: pacote fora da caixa não tem hash aprovado, mesmo estando no wheelhouse
    r = subprocess.run([str(py), "-m", "pip", "install", "-q", "--no-index", "--find-links", str(wh), "--require-hashes",
                        "-r", str(caixa), "intruso"], capture_output=True, text=True)
    assert r.returncode and "hash" in (r.stderr + r.stdout).lower()
    assert subprocess.run([str(py), "-c", "import intruso"], capture_output=True).returncode
    # roda trocada (hash não bate) também é recusada
    caixa.write_text(f"pacote-caixa==1.0 --hash=sha256:{'0' * 64}\n")
    subprocess.run([str(py), "-m", "pip", "uninstall", "-y", "-q", "pacote-caixa"], capture_output=True)
    velho = c.subprocess.run
    c.subprocess.run = lambda cmd, **k: velho(cmd if "download" not in cmd else [str(py), "-c", "raise SystemExit(1)"], **k)
    try:
        c.instalar_da_caixa(py, caixa, wh)
        assert False, "hash errado tinha que falhar"
    except c.Falha:
        pass
    finally:
        c.subprocess.run = velho


def test_aba_conhecimento_mostra_versao_e_hash():
    html = (RAIZ / "public" / "index.html").read_text(encoding="utf-8")
    js = re.search(r"(function caixaPacotes.*?)async function telaConhecimento", html, re.S).group(1)
    pagina = TMP / "pagina.html"
    pagina.write_text(f"""<html><body><div id="m"></div><script>
      const S = {{}}; const esc = s => String(s).replace(/[&<>"]/g, ch => ({{"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}})[ch]);
      {js}
      window.CAIXA = {json.dumps(CAIXA.read_text())};
      document.getElementById("m").innerHTML = caixaHtml(window.CAIXA);
      window.ITENS = caixaPacotes(window.CAIXA);
    </script></body></html>""", encoding="utf-8")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.goto(pagina.as_uri())
        itens = pg.evaluate("window.ITENS")
        pg.evaluate("document.querySelector('details').open = true")
        texto = pg.inner_text("#m")
        b.close()
    pandas = next(x for x in itens if x["nome"] == "pandas")
    assert pandas["versao"] == "3.0.6" and len(pandas["hash"]) == 64 and "site" in pandas["onde"]
    hermes = next(x for x in itens if x["nome"] == "hermes3:8b")
    assert hermes["onde"] == "Ollama (Mac)" and hermes["hash"] == ""
    assert len(itens) == len([x for x in CAIXA.read_text().splitlines() if x and (not x.startswith("#") or "ollama:" in x)])
    assert "sha256:" + pandas["hash"] in texto and "aprovação do Bruno" in texto and "hash: não informado" in texto


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
