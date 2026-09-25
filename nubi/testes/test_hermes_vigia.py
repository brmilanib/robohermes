"""Hermes vigia de erros (coletor) e plano B do download do estoque. Roda sem Mac, sem Ollama e sem sites."""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402

ERRO_25_09 = "TargetClosedError: Download.save_as: Target page, context or browser has been closed"


def _preparar():
    soltos, posts, cards = [], [], []
    c.token_nubi = lambda cfg: "T"
    c._soltar = lambda cmd, env=None: soltos.append((cmd, env))
    c.aviso_mac = lambda *a: None
    c._outra_rodando = lambda: None
    c.time.sleep = lambda s: None

    def api(token, rota, params=None, corpo=None, metodo=None, timeout=300):
        (posts if rota == "reuniao_postar" else cards).append(corpo)
        return {}
    c.api = api
    c.FALHAS.unlink(missing_ok=True)
    c.salvar_config({})
    return soltos, posts, cards


def test_diagnostico_do_erro_da_madrugada():
    assert c.diagnosticar(ERRO_25_09)[0] == "visivel"
    assert c.diagnosticar("O UpSeller pediu login de novo")[0] == "avisar"
    assert c.diagnosticar("Locator.click: Timeout 30000ms exceeded")[0] == "repetir"
    assert c.diagnosticar("ProcessSingleton: profile appears to be in use")[0] == "destravar"
    assert c.diagnosticar("algo inédito") == (None, None)


def test_hermes_conserta_e_depois_abre_card():
    soltos, posts, cards = _preparar()
    for rodada in range(3):
        c.anotar_falha("estoque", ERRO_25_09)
        assert c._falhas_pendentes()
        c.cmd_hermes_vigia(None, c.ler_config())
        assert not c._falhas_pendentes()                  # tratada: não repete
    assert soltos == [("estoque", {"NUBI_VER": "1"})] * 2   # 2 consertos por dia, com o navegador visível
    assert "conserto 1 de 2" in posts[0]["texto"] and posts[0]["autor"] == "Hermes"
    assert "abri um card" in posts[2]["texto"]
    assert len(cards) == 1 and cards[0]["status"] == "aprovada"
    import nubi_web
    assert nubi_web.card_pronto(cards[0]["descricao"])[0]  # o card já nasce com os 4 itens do #44


def test_login_vencido_so_avisa():
    soltos, posts, cards = _preparar()
    c.anotar_falha("estoque", "O UpSeller pediu login de novo. No Mac mini, rode: entrar-upseller")
    c.cmd_hermes_vigia(None, c.ler_config())
    assert soltos == [] and "precisa do Bruno" in posts[0]["texto"]


def test_erro_desconhecido_sem_ollama_avisa():
    soltos, posts, _ = _preparar()
    c.anotar_falha("gestor", "algo inédito")
    c.cmd_hermes_vigia(None, c.ler_config())            # Ollama não existe aqui -> avisar, nunca inventa ação
    assert soltos == [] and "precisa do Bruno" in posts[0]["texto"]


def test_download_perdido_baixa_pelo_link():
    class Resp:
        ok, status = True, 200
        def body(self):
            return b"PK\x03\x04planilha"
    class Req:
        def get(self, url, timeout=None):
            assert url == "https://app.upseller.com/arquivo.xlsx"
            return Resp()
    class Ctx:
        request = Req()
    class Pg:
        context = Ctx()
    class Dl:
        url = "https://app.upseller.com/arquivo.xlsx"
        def save_as(self, caminho):
            raise RuntimeError(ERRO_25_09)
    arq = Path(os.environ["NUBI_COLETOR_DIR"]) / "Estoque.xlsx"
    c._salvar_download(Pg(), Dl(), arq)
    assert arq.read_bytes().startswith(b"PK")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    os.environ.setdefault("OLLAMA_API_KEY", "x")
    os.environ.setdefault("ANTHROPIC_API_KEY", "x")
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
