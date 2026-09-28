# -*- coding: utf-8 -*-
"""27/09 (Bruno): o servidor Dell do escritório assume parte da fila do Mac. Enquanto ele dá sinal, o Mac não pega os
comandos que o servidor sabe fazer, nem a Sala; comandos servidor_* nunca vão para o Mac. Sem sinal, o Mac faz tudo.
Rodar: python3 testes/test_servidor_fila.py, na pasta nubi."""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import nubi_web as w  # noqa: E402

os.environ["NUBI_COLETOR_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402


class Repo:
    def __init__(self, cmds):
        self.t = {"mac_comandos": [dict(id=i + 1, comando=k, arg="", status="pendente") for i, k in enumerate(cmds)],
                  "ia_resumos": [], "mac_estado": [], "reuniao_mensagens": [{"id": 7, "autor": "voce", "texto": "@hermes oi",
                                                                             "criado_em": datetime.now(timezone.utc).isoformat()}],
                  "conhecimento": []}

    def _eq(self, v):
        return f"eq.{v}"

    def _req(self, metodo, tab, params=None, corpo=None, prefer=None):
        linhas = self.t.setdefault(tab, [])
        p = params or {}

        def bate(r):
            for k, v in p.items():
                if k in ("select", "order", "limit"):
                    continue
                x = str(r.get(k))
                if v.startswith("eq.") and x != v[3:]:
                    return False
                if v.startswith("in.(") and x not in v[4:-1].split(","):
                    return False
                if v.startswith("not.in.(") and x in v[8:-1].split(","):
                    return False
            return True
        if metodo == "GET":
            out = [dict(r) for r in linhas if bate(r)]
            return out[: int(p.get("limit", 10 ** 6))]
        if metodo == "PATCH":
            for r in linhas:
                if bate(r):
                    r.update(corpo)
            return None
        if metodo == "POST":
            for n in corpo:
                chave = "chave" if tab == "ia_resumos" else "id"
                velho = next((r for r in linhas if chave in n and r.get(chave) == n.get(chave)), None)
                if velho is not None:
                    velho.update(n)
                else:
                    linhas.append(dict(n))
            return None


def _tick(r, maquina=None, pode=None, nome=None, prioridade=1):
    corpo = {"info": {"ollama": False}, "sala_ult": 1}
    if maquina:
        corpo.update(maquina=maquina, pode=pode, prioridade=prioridade, **({"nome": nome} if nome else {}))
    return w.rota_mac(r, "POST", "mac_tick", {}, json.dumps(corpo).encode(), "tok")


def _preparar():
    w.indexar_aos_poucos = lambda *a, **k: None
    w.ferreiro_proximo = lambda *a, **k: ""
    for f in ("atendente_proximo", "sac_proximo", "reinterpretar_pendentes", "retomar_esquecidas", "aprender_aos_poucos",
              "revisar_propostas", "fichar_aos_poucos"):
        setattr(w.atendimento, f, lambda *a, **k: None)


def test_servidor_pega_o_que_sabe_e_o_mac_fica_com_o_resto():
    _preparar()
    r = Repo(["importar_sac", "programar_card", "servidor_processos", "processos"])
    srv = _tick(r, "servidor", list(c.SERVIDOR_PODE))
    assert [p["comando"] for p in srv["pendentes"]] == ["importar_sac", "servidor_processos"], srv
    assert srv["sala"], "o servidor (com o Hermes) responde na Sala"
    assert not r.t["mac_estado"], "o sinal do servidor não finge ser o Mac"
    mac = _tick(r)
    assert [p["comando"] for p in mac["pendentes"]] == ["programar_card", "processos"] and mac["reserva"] is True, mac
    assert mac["sala"] == []


def test_sem_sinal_do_servidor_o_mac_faz_tudo_menos_servidor_():
    _preparar()
    r = Repo(["importar_sac", "servidor_espaco"])
    _tick(r, "servidor", list(c.SERVIDOR_PODE))
    velho = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    r.t["ia_resumos"][0]["criado_em"] = velho
    for x in r.t["mac_comandos"]:
        x["status"] = "pendente"
    mac = _tick(r)
    assert [p["comando"] for p in mac["pendentes"]] == ["importar_sac"] and mac["reserva"] is False, mac


def test_comandos_do_servidor_no_windows():
    antes = c.WINDOWS
    try:
        c.WINDOWS = True
        assert c.comando_mac("servidor_processos")[0] == "powershell"
        assert c.comando_mac("importar_sac")[-1] == "importar-sac" and c.comando_mac("importar_sac")[0] == sys.executable
        assert c.comando_mac("rm -rf /") is None
        assert c._eh_servidor({"maquina": "servidor"}) and not c._eh_servidor({})
    finally:
        c.WINDOWS = antes


def test_rodar_logado_grava_saida_e_codigo():
    log = Path(tempfile.mkdtemp()) / "1.log"
    c.cmd_rodar_logado(str(log), [sys.executable, "-c", "print('ola'); raise SystemExit(3)"])
    assert "ola" in log.read_text() and Path(str(log) + ".rc").read_text() == "3"


def test_gamdias_so_com_o_sac_deixa_sala_e_vetores_no_mac():
    _preparar()
    r = Repo(["importar_sac", "hermes"])
    srv = _tick(r, "servidor", ["importar_sac", "servidor_processos"])
    assert [p["comando"] for p in srv["pendentes"]] == ["importar_sac"] and srv["sala"] == [], srv
    mac = _tick(r)
    assert [p["comando"] for p in mac["pendentes"]] == ["hermes"] and mac["sala"], mac


def test_opcao_so_sac():
    import argparse
    cfg = {}
    guardado = (c.salvar_config, c.subprocess.run, c.subprocess.Popen, c.time.sleep)
    c.salvar_config = lambda x: None
    try:
        c.time.sleep = lambda s: (_ for _ in ()).throw(KeyboardInterrupt())
        c.subprocess.run = lambda *a, **k: None
        c.subprocess.Popen = lambda *a, **k: type("P", (), {"poll": lambda self: None})()
        try:
            c.cmd_servidor(argparse.Namespace(so="sac", tudo=False, instalar=False, sem_atendente=False), cfg)
        except KeyboardInterrupt:
            pass
    finally:
        c.salvar_config, c.subprocess.run, c.subprocess.Popen, c.time.sleep = guardado
    assert cfg["maquina"] == "servidor" and cfg["servidor_pode"][0] == "importar_sac" and "hermes" not in cfg["servidor_pode"]


def test_gamdias_principal_e_dell_reserva():
    _preparar()
    r = Repo(["importar_sac", "hermes"])
    dell = _tick(r, "servidor", list(c.SERVIDOR_PODE), "DESKTOP-IRQKD9R", 2)
    assert [p["comando"] for p in dell["pendentes"]] == ["importar_sac", "hermes"], "sozinho, o Dell trabalha"
    for x in r.t["mac_comandos"]:
        x["status"] = "pendente"
    gam = _tick(r, "servidor", list(c.SERVIDOR_PODE), "gamdias", 1)
    assert [p["comando"] for p in gam["pendentes"]] == ["importar_sac", "hermes"], gam
    for x in r.t["mac_comandos"]:
        x["status"] = "pendente"
    dell = _tick(r, "servidor", list(c.SERVIDOR_PODE), "DESKTOP-IRQKD9R", 2)
    assert dell["pendentes"] == [] and dell["reserva"] is True, "com o gamdias vivo, o Dell não pega nada"
    # o atendente do Dell também fica parado; o do gamdias atende
    w.atendimento.canais_ligados = lambda repo: ["shopee"]
    w.atendimento.para_enviar = lambda repo: []
    q = lambda comp: w.atendimento.rota(r, "GET", "atendimento_para_enviar", {"computador": comp}, b"")
    assert q("servidor:gamdias")["canais"] == ["shopee"] and q("servidor:DESKTOP-IRQKD9R")["canais"] == []


def test_mac_pausado_nao_recebe_nada_e_o_servidor_assume():
    _preparar()
    r = Repo(["diario", "programar_card", "servidor_log"])
    r.t["ia_resumos"].append({"chave": "fila|mac_pausado", "texto": "malware achado em 27/09"})
    mac = _tick(r)
    assert mac["pendentes"] == [] and mac.get("pausado") is True and mac["sala"] == []
    srv = _tick(r, "servidor", list(c.SERVIDOR_PODE), "gamdias", 1)
    assert [p["comando"] for p in srv["pendentes"]] == ["diario", "servidor_log"], srv    # Ferreiro não vai para o gamdias


def test_estoque_liberado_no_mac_pausado():
    # 28/09 (Bruno, assumindo o risco): o Mac pausado ainda faz o estoque do UpSeller; o gamdias não pega o estoque
    _preparar()
    r = Repo(["diario"])
    r.t["ia_resumos"] += [{"chave": "fila|mac_pausado", "texto": "malware"}, {"chave": "fila|mac_libera", "texto": "estoque"}]
    mac = _tick(r)
    assert mac["pausado"] is True and mac["libera"] == ["estoque"] and mac["pendentes"] == []
    assert w._so_no_mac(r, "estoque") and not w._so_no_mac(r, "diario")
    r.t["rotinas"] = [{"id": "estoque", "ativo": True, "horario": "00:00", "dias_semana": ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]}]
    r.t["estoque_atualizacoes"] = []
    assert w.rota_estoque(r, "GET", "estoque_pendente", {"maquina": "servidor"}, b"") == {"rodar": False, "no_mac": True}
    assert w.rota_estoque(r, "GET", "estoque_pendente", {}, b"")["rodar"] is True          # o Mac pergunta sem 'maquina'


def test_vigia_de_seguranca_derruba_o_malware_e_avisa():
    # 28/09 (Bruno): de hora em hora, CPU e os arquivos do malware de 27/09
    import shutil
    base = Path(tempfile.mkdtemp())
    ag = base / "LaunchAgents"
    ag.mkdir()
    (ag / "com.google.keystone.agent.plist").write_text("x")
    pasta = base / "rigupdater"
    antes = (c.sys.platform, c.AGENTES_DIRS, c.MALWARE_PASTAS, c.token_nubi, c.api, c._postar_hermes_como, c.aviso_mac, c.Path.home)
    enviados, sala = [], []
    c.sys.platform, c.AGENTES_DIRS, c.MALWARE_PASTAS = "darwin", (str(ag),), (str(pasta),)
    c.token_nubi = lambda cfg: "T"
    c.api = lambda token, rota, params=None, corpo=None, metodo=None, timeout=300: enviados.append((rota, corpo)) or {}
    c._postar_hermes_como = lambda token, autor, texto, *a, **k: sala.append(texto)
    c.aviso_mac = lambda *a: None
    c.Path.home = staticmethod(lambda: base)
    try:
        cfg = {}
        assert c.seguranca_mac(cfg, forcar=True)["ok"] is True and cfg["seguranca_agentes"]     # 1ª vez: guarda o que existe
        assert not sala
        (ag / "com.vsbgoqkgoyeuwbdw.plist").write_text("malware")
        pasta.mkdir()
        (ag / "com.desconhecido.plist").write_text("?")
        rel = c.seguranca_mac(cfg, forcar=True)
        assert not rel["ok"] and not pasta.exists() and not (ag / "com.vsbgoqkgoyeuwbdw.plist").exists()
        assert list((base / "quarentena").iterdir())                                          # movido, não apagado
        assert (ag / "com.desconhecido.plist").exists()                                       # desconhecido: só avisa
        assert "LaunchAgent do malware voltou" in sala[0] and "com.desconhecido.plist" in sala[0]
        assert enviados[-1][0] == "mac_seguranca" and enviados[-1][1]["achados"]
        assert c.seguranca_mac(cfg)  is None                                                  # de hora em hora
    finally:
        (c.sys.platform, c.AGENTES_DIRS, c.MALWARE_PASTAS, c.token_nubi, c.api, c._postar_hermes_como, c.aviso_mac, c.Path.home) = antes
        shutil.rmtree(base, ignore_errors=True)


def test_reserva_haiku_para_no_teto_mesmo_sem_custo_gravado():
    # 27/09: 2.440 chamadas do Haiku com custo_usd vazio (~US$ 73): o teto agora conta pelos tokens e pelo nº de chamadas
    import datetime as dt
    at = w.atendimento
    r = Repo([])
    agora = dt.datetime.now(dt.timezone.utc).isoformat()
    r.t["agentes_uso"] = [{"origem": at.NAVEGAR_ORIGEM, "inicio": agora, "custo_usd": None, "tokens_in": 46000, "tokens_out": 160}
                          for _ in range(70)]                                         # ~US$ 3,3 pelos tokens
    chamou = []
    antes_tem, antes_post = at.ia.tem, at.ia._post_json
    at.ia.tem = lambda q: True
    at.ia._post_json = lambda *a, **k: chamou.append(1) or {"content": []}
    try:
        assert at._navegar_reserva(r, {"mensagens": []}) is None and not chamou
        r.t["agentes_uso"] = [{"origem": at.NAVEGAR_ORIGEM, "inicio": agora, "custo_usd": 0, "tokens_in": 1}] * at.NAVEGAR_MAX_DIA
        assert at._navegar_reserva(r, {"mensagens": []}) is None and not chamou     # limite de chamadas por dia
    finally:
        at.ia.tem, at.ia._post_json = antes_tem, antes_post


def test_atendente_usa_a_ia_local_do_computador_antes_de_tudo():
    # 27/09 (Bruno): navegar no chat é simples; roda de graça no Ollama do gamdias (qwen3:8b), sem cota e sem Haiku
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    pedidos = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            pedidos.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            if pedidos[-1]["model"] == "qwen3:8b":                       # a 1ª local falha: entra a 2ª (hermes3), também grátis
                self.send_response(500); self.end_headers(); return
            corpo = json.dumps({"message": {"content": "", "tool_calls": [
                {"function": {"name": "clicar", "arguments": {"texto": "Todos"}}}]}}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    antes = (c.OLLAMA_CHAT, c._modelos_locais, c.api)
    c.OLLAMA_CHAT = f"http://127.0.0.1:{srv.server_port}/api/chat"
    c._modelos_locais = lambda: ["qwen3:8b", "hermes3:8b"]
    c.api = lambda *a, **k: (_ for _ in ()).throw(AssertionError("não devia chamar o nubi"))
    try:
        estado = {}
        msgs = [{"role": "user", "content": "leia o chat"},
                {"role": "assistant", "content": [{"type": "tool_use", "id": "a", "name": "ler", "input": {}}]},
                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "a", "content": "x" * 50000}]}]
        r = c._ia_atendente("chave-paga", msgs, "tok", estado)
        assert r["content"][0]["type"] == "tool_use" and r["content"][0]["name"] == "clicar", r
        assert estado.get("gratis") == 1 and not estado.get("pago")
        p = pedidos[1]
        assert [x["model"] for x in pedidos] == ["qwen3:8b", "hermes3:8b"]
        assert p["think"] is False and p["tools"][0]["type"] == "function"
        assert len(p["messages"][-1]["content"]) <= 12000                     # página encurtada para caber na placa
    finally:
        c.OLLAMA_CHAT, c._modelos_locais, c.api = antes
        srv.shutdown()


def test_le_a_taxa_da_shopee_na_aba_data_sem_ia():
    # 27/09 (print do Bruno): Shopee Chat → Data → Chat
    txt = ("Chats Respondidos\n5\nvs 30 Dias Anteriores\nChats Não-Respondidos\n3 Detalhes\nTempo médio de resposta\n03:14:11\n"
           "CSAT %\n50,00% Detalhes\nTaxa de conversão\n(Perguntas para\nRespostas)\n62,50%\nPeríodo dos Dados Últimos 30 Dias")
    d = c._taxa_do_texto(txt)
    assert d == {"respondidos": 5, "nao_respondidos": 3, "tempo_resposta": "03:14:11", "csat": 50.0,
                 "periodo": "Últimos 30 Dias", "taxa_resposta": 62.5}, d
    sem_rotulo = c._taxa_do_texto("Chats Respondidos\n9\nChats Não-Respondidos\n1")
    assert sem_rotulo["taxa_resposta"] == 90.0
    assert c._taxa_do_texto("página mudou") == {}


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
