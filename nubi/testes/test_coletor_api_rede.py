"""api() do coletor: repete quando a rede oscila (card #141) e vira Falha clara se não voltar."""
import importlib.util, os, sys, urllib.request, urllib.error, io
sys.dont_write_bytecode = True
raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("coletor", os.path.join(raiz, "public/coletor/coletor.py"))
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
c.time.sleep = lambda s: None
orig = urllib.request.urlopen

class R:
    def __init__(s, b): s.b = b
    def __enter__(s): return s
    def __exit__(s, *a): pass
    def read(s): return s.b

n = {"v": 0}
def duas_falhas(req, timeout=0):
    n["v"] += 1
    if n["v"] < 3: raise TimeoutError("timed out")
    return R(b'{"ok": 1}')
urllib.request.urlopen = duas_falhas
assert c.api("t", "x") == {"ok": 1} and n["v"] == 3

def sempre(req, timeout=0): raise TimeoutError("timed out")
urllib.request.urlopen = sempre
try: c.api("t", "x"); raise SystemExit("devia falhar")
except c.Falha as e: assert "não respondeu" in str(e)

def http500(req, timeout=0): raise urllib.error.HTTPError("u", 500, "x", {}, io.BytesIO(b'{"erro": "ruim"}'))
urllib.request.urlopen = http500
try: c.api("t", "x"); raise SystemExit("devia falhar")
except c.Falha as e: assert str(e) == "ruim"
urllib.request.urlopen = orig
print("ok")

# POST que estoura na leitura não é reenviado (poderia gravar em dobro)
n["v"] = 0
def post_lento(req, timeout=0):
    n["v"] += 1; raise TimeoutError("timed out")
urllib.request.urlopen = post_lento
try: c.api("t", "x", corpo={"a": 1}); raise SystemExit("devia falhar")
except c.Falha: assert n["v"] == 1
urllib.request.urlopen = orig
print("ok post")
