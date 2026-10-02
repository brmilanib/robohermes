"""02/10 (vídeo do Bruno): rodízio dos seguidos — seguir pelo quadro "Adicionar Grupo" (ADICIONAR em "perfumes") e soltar
pelo menu "Parar de seguir", só nas vagas livres; o servidor planeja. Páginas falsas; roda sem sites."""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import coletor as c  # noqa: E402
import rodizio  # noqa: E402

c.devagar = lambda *a, **k: None
c.enviar_foto = lambda *a, **k: None

PAGINA = """<html><body style="font-family:sans-serif">
<input placeholder="Buscar anúncios, codinome do vendedor, marcas e muito mais" id="b" style="width:500px">
<label><input type="radio" name="t"> Pesquisa exata</label><label><input type="radio" name="t" checked> Pesquisa expandida por IA</label>
<div id="res"></div>
<div id="quadro" style="display:none;position:fixed;top:100px;left:300px;background:#fff;border:1px solid #000;padding:10px">
  <h2>Adicionar Grupo</h2>
  <div><span>Nicknames Favoritos</span> <button id="bf">ADICIONAR</button></div>
  <div><span>perfumes</span> <button id="bp">ADICIONAR</button></div></div>
<div id="menu" style="display:none;position:fixed;top:300px;left:300px;background:#fff"><div id="parar">Parar de seguir</div>
  <div>Ir para analise um concorrente</div></div>
<script>
let seguido = %s;
const pinta = () => { document.getElementById('bp').innerText = seguido ? 'REMOVER' : 'ADICIONAR'; };
document.getElementById('b').onkeydown = e => { if (e.key !== 'Enter') return;
  document.getElementById('res').innerHTML = `<div style="display:flex;gap:8px;align-items:center;margin-top:20px">
    <span style="width:300px">Perfume Árabe Sabah</span><button title="anuncio" style="width:20px;height:20px">a</button></div>
    <div style="display:flex;gap:8px;align-items:center"><a href="#">${e.target.value.toUpperCase()}</a>
    <button id="iv" style="width:20px;height:20px;margin-left:120px">v</button></div>`;
  document.getElementById('iv').onclick = () => { if (seguido) document.getElementById('menu').style.display = 'block';
    else { pinta(); document.getElementById('quadro').style.display = 'block'; } }; };
document.getElementById('bp').onclick = () => { seguido = !seguido; pinta(); };
document.getElementById('parar').onclick = () => { seguido = false; document.getElementById('menu').style.display = 'none'; };
document.addEventListener('keydown', e => { if (e.key === 'Escape') { document.getElementById('quadro').style.display = 'none';
  document.getElementById('menu').style.display = 'none'; } });
window.estado = () => seguido;
</script></body></html>"""


def _pg(p, seguido):
    exe = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    nav = p.chromium.launch(executable_path=exe if os.path.exists(exe) else None)
    pg = nav.new_page()
    pg.set_content(PAGINA % ("true" if seguido else "false"))
    return nav, pg


def test_seguir_e_soltar_pela_tela():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        nav, pg = _pg(p, False)
        assert c.seguir_vendedor(pg, "AIRON.AMBAR.INQUIETANTE", "perfumes") is None
        assert pg.evaluate("estado()") is True
        assert c.seguir_vendedor(pg, "AIRON.AMBAR.INQUIETANTE", "perfumes") is None      # já seguido: não desfaz
        assert pg.evaluate("estado()") is True
        assert c.soltar_vendedor(pg, "AIRON.AMBAR.INQUIETANTE", "perfumes") is None
        assert pg.evaluate("estado()") is False
        nav.close()


def test_grupo_errado_nao_clica():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        nav, pg = _pg(p, False)
        erro = c.seguir_vendedor(pg, "AIRON.AMBAR.INQUIETANTE", "outro grupo")
        assert erro and "não achei o grupo" in erro and pg.evaluate("estado()") is False
        nav.close()


class Repo:
    def __init__(self):
        self.ia = {}
        self.dias = {}
        self.fixos = 17

    def _eq(self, v):
        return f"eq.{v}"

    def _req(self, metodo, tabela, params=None, corpo=None, **k):
        if tabela == "rpc/nubi_observados":
            return [{"vendedor_id": "h1", "nomes": ["AIRON.AMBAR.INQUIETANTE"], "un": 11000, "marcas": 2},
                    {"vendedor_id": "h2", "nomes": ["ICARBONXX P3"], "un": 50000, "marcas": 9},         # seguido
                    {"vendedor_id": "h3", "nomes": ["MORSA.OCRE.MISTERIOSO"], "un": 9000, "marcas": 1},
                    {"vendedor_id": "h4", "nomes": ["GATO.AZUL.FELIZ"], "un": 8000, "marcas": 1},
                    {"vendedor_id": "h5", "nomes": ["SAPO.ROXO.LENTO"], "un": 100, "marcas": 1}]
        if tabela == "ia_resumos":
            if metodo == "POST":
                self.ia[corpo[0]["chave"]] = corpo[0]["texto"]
                return []
            ch = params["chave"][3:]
            return [{"texto": self.ia[ch]}] if ch in self.ia else []
        if tabela == "vend_vendas_dia":
            return [{"data": "2026-09-30"}]
        return []

    def _todos(self, tabela, params=None):
        if "vendedor" not in params:                      # quem está no grupo: 17 fixos + os do rodízio
            return [{"vendedor": f"FIXO {i}"} for i in range(self.fixos)] + [{"vendedor": n} for n in self.dias]
        nome = params["vendedor"][3:]
        return [{"data": d} for d in self.dias.get(nome, [])]


def test_plano_so_nas_vagas_livres_e_solta_quem_ja_baixou():
    r = Repo()
    assert rodizio.plano(r, {"h2"})["ligado"] is False
    rodizio.configurar(r, {"ligado": True, "vagas": 9})
    assert rodizio.ler(r)["vagas"] == 3                                  # nunca passa das vagas livres
    p1 = rodizio.plano(r, {"h2"})
    assert [s["codinome"] for s in p1["seguir"]] == ["AIRON.AMBAR.INQUIETANTE", "MORSA.OCRE.MISTERIOSO", "GATO.AZUL.FELIZ"]
    rodizio.registrar(r, {"seguiu": [s["codinome"] for s in p1["seguir"]]})
    assert rodizio.plano(r, {"h2"})["seguir"] == []                       # vagas cheias, ninguém baixado ainda
    r.dias["AIRON-AMBAR-INQUIETANTE"] = [f"2026-09-{d:02d}" for d in range(1, 31)]   # coleta trouxe 30 dias até 30/09
    p2 = rodizio.plano(r, {"h2"})
    assert p2["soltar"] == ["AIRON.AMBAR.INQUIETANTE"] and [s["codinome"] for s in p2["seguir"]] == ["SAPO.ROXO.LENTO"]
    rodizio.registrar(r, {"soltou": ["AIRON.AMBAR.INQUIETANTE"], "seguiu": ["SAPO.ROXO.LENTO"]})
    e = rodizio.ler(r)
    assert "AIRON.AMBAR.INQUIETANTE" in e["feitos"] and "SAPO.ROXO.LENTO" in e["ativos"]
    assert all(s["codinome"] != "AIRON.AMBAR.INQUIETANTE" for s in rodizio.fila(r, e, {"h2"}))   # só volta em 30 dias
    r2 = Repo()
    r2.fixos = 19                                         # o Bruno seguiu 2 à mão: só 1 vaga
    rodizio.configurar(r2, {"ligado": True})
    p3 = rodizio.plano(r2, {"h2"})
    assert p3["vagas"] == 1 and len(p3["seguir"]) == 1, p3


def test_comando_da_central():
    assert c.comando_mac("rodizio_seguidos", "")[-1] == "rodizio"


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
