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


SABER = []          # caixa de conhecimento falsa


def _preparar():
    soltos, posts, cards = [], [], []
    c.token_nubi = lambda cfg: "T"
    c._soltar = lambda cmd, env=None: soltos.append((cmd, env))
    c.aviso_mac = lambda *a: None
    c._outra_rodando = lambda: None
    c.time.sleep = lambda s: None
    c.ferreiro_pronto = lambda cfg=None: (False, "sem Ferreiro no teste")   # não lê o Chaveiro do Mac de verdade

    def api(token, rota, params=None, corpo=None, metodo=None, timeout=300):
        if rota == "conhecimento":
            return {"itens": [x for x in SABER if (params or {}).get("q", "").lower() in x["titulo"].lower()]}
        if rota == "reuniao_tarefas":
            return {"tarefas": [{"id": 70 + i, "titulo": x["titulo"], "status": "aprovada"} for i, x in enumerate(cards)]}
        (posts if rota == "reuniao_postar" else cards).append(corpo)
        return {"id": 70 + len(cards) - 1} if rota == "reuniao_tarefa_salvar" else {}
    c.api = api
    SABER.clear()
    c.FALHAS.unlink(missing_ok=True)
    c.salvar_config({})
    return soltos, posts, cards


def test_diagnostico_do_erro_da_madrugada():
    assert c.diagnosticar(ERRO_25_09)[0] == "visivel"
    assert c.diagnosticar("O UpSeller pediu login de novo")[0] == "janela_login"
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
    assert "URGENTE" in posts[2]["texto"] and "#70" in posts[2]["texto"]
    assert len(cards) == 1 and cards[0]["status"] == "aprovada" and cards[0]["prioridade"] == "urgente"
    assert cards[0]["responsavel"] == "claude_code"
    import nubi_web
    assert nubi_web.card_pronto(cards[0]["descricao"])[0]  # o card já nasce com os 4 itens do #44


class _Rc:
    def __init__(self, rc):
        self.returncode, self.stdout = rc, "Nubimetrics: sem senha salva no navegador do coletor nem no Chaveiro"


def test_login_vencido_entra_sozinho_e_roda_de_novo():
    soltos, posts, cards = _preparar()
    chamadas = []
    c.subprocess.run = lambda cmd, **k: chamadas.append(cmd[-2:]) or _Rc(0)
    c.anotar_falha("estoque", "O UpSeller pediu login de novo. No Mac mini, rode: entrar-upseller")
    c.cmd_hermes_vigia(None, c.ler_config())
    assert chamadas == [["entrar-auto", "upseller"]]    # entrou sozinho: nem abriu a janela
    assert soltos == [("estoque", None)]
    assert "entrei sozinho" in posts[0]["texto"]


def test_login_vencido_sem_senha_abre_a_janela_e_roda_de_novo():
    soltos, posts, cards = _preparar()
    chamadas = []
    c.subprocess.run = lambda cmd, **k: chamadas.append(cmd[-1]) or _Rc(1 if "entrar-auto" in cmd else 0)
    c.anotar_falha("estoque", "O UpSeller pediu login de novo. No Mac mini, rode: entrar-upseller")
    c.cmd_hermes_vigia(None, c.ler_config())
    assert chamadas == ["upseller", "entrar-upseller"]  # tentou sozinho; não deu -> abriu a janela (o Bruno clica)
    assert soltos == [("estoque", None)]                # entrou -> rodou a tarefa de novo
    assert "Tentei entrar sozinho" in posts[0]["texto"] and "Login do Upseller feito" in posts[1]["texto"]
    assert "sem senha salva" in posts[0]["texto"]       # o motivo do login automático aparece na Sala
    c.anotar_falha("estoque", "O UpSeller pediu login de novo.")
    c.cmd_hermes_vigia(None, c.ler_config())            # 2ª vez no dia: tenta de novo
    assert len(chamadas) == 4
    c.anotar_falha("estoque", "O UpSeller pediu login de novo.")
    c.cmd_hermes_vigia(None, c.ler_config())            # 3ª vez: não tenta mais, só avisa
    assert len(chamadas) == 4 and "só com você" in posts[-1]["texto"]


def test_versao_nova_roda_de_novo_o_que_falhou_hoje():
    soltos, posts, cards = _preparar()
    from datetime import datetime, timedelta, timezone
    agora = datetime.now(timezone.utc).isoformat()
    ontem = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    execs = [{"tarefa": "gestor", "ok": False, "iniciado_em": agora, "mensagem": "conferência: SKU não encontrado"},
             {"tarefa": "estoque", "ok": True, "iniciado_em": agora, "mensagem": "640 SKUs"},
             {"tarefa": "diario", "ok": False, "iniciado_em": ontem, "mensagem": "login"}]
    rodou = []

    def api(token, rota, params=None, corpo=None, metodo=None, timeout=300):
        if rota == "coletor_status":
            if rodou:
                return {"execucoes": [{"tarefa": "gestor", "ok": True, "iniciado_em": agora, "mensagem": "custo conferido"}] + execs}
            return {"execucoes": execs}
        posts.append(corpo)
        return {}
    c.api = api
    c.subprocess.run = lambda cmd, **k: rodou.append(cmd[-1]) or _Rc(0)
    c.cmd_repetir_falhas(None, c.ler_config())
    assert rodou == ["gestor"]                           # só o que falhou hoje (estoque deu certo; diario é de ontem)
    assert "rodei de novo a tarefa **gestor**" in posts[-1]["texto"] and "✅ custo conferido" in posts[-1]["texto"]


def test_erro_sem_conserto_vira_card_urgente_na_hora():
    soltos, posts, cards = _preparar()
    erro = "conferência: no Gestor Seller o custo de ARMAF-MEGA-200 não bateu com a planilha (48.00); a tela mostra: X"
    c.anotar_falha("gestor", erro)
    c.cmd_hermes_vigia(None, c.ler_config())            # Ollama não existe aqui -> sem conserto: card urgente, não o Bruno
    assert soltos == [] and "URGENTE" in posts[0]["texto"] and "precisa do Bruno" not in posts[0]["texto"]
    assert len(cards) == 1 and cards[0]["prioridade"] == "urgente"
    c.anotar_falha("gestor", erro.replace("48.00", "49.00"))
    c.cmd_hermes_vigia(None, c.ler_config())            # mesmo erro de novo: não duplica o card
    assert len(cards) == 1 and "já está aberto" in posts[-1]["texto"]


def test_erro_que_ja_tem_solucao_mostra_a_solucao():
    soltos, posts, cards = _preparar()
    erro = "conferência: no Gestor Seller o custo de ARMAF-MEGA-200 não bateu com a planilha (48.00); a tela mostra: X"
    SABER.append({"titulo": "Solução: gestor falhando — " + c.assinatura_erro(erro),
                  "texto": "Causa: a lista do Gestor é de blocos (div). Solução: _linha_do_sku no coletor.py."})
    c.anotar_falha("gestor", erro)
    c.cmd_hermes_vigia(None, c.ler_config())
    assert "Já vimos esse erro antes" in posts[0]["texto"] and "_linha_do_sku" in posts[0]["texto"]
    assert "_linha_do_sku" in cards[0]["descricao"]      # o programador recebe a solução antiga no card


def test_assinatura_ignora_numeros_e_detalhes():
    a = c.assinatura_erro("custo de X não bateu (48.00); a tela mostra: Y. [sku=1 etapa=2]")
    assert a == c.assinatura_erro("custo de X não bateu (51.30); a tela mostra: Y. [sku=9 etapa=3]")
    assert "48" not in a and "[" not in a


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
