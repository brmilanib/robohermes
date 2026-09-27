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


def _tick(r, maquina=None, pode=None):
    corpo = {"info": {"ollama": False}, "sala_ult": 1}
    if maquina:
        corpo.update(maquina=maquina, pode=pode)
    return w.rota_mac(r, "POST", "mac_tick", {}, json.dumps(corpo).encode(), "tok")


def _preparar():
    w.indexar_aos_poucos = lambda *a, **k: None
    w.ferreiro_proximo = lambda *a, **k: ""
    for f in ("atendente_proximo", "sac_proximo", "reinterpretar_pendentes", "retomar_esquecidas", "aprender_aos_poucos",
              "revisar_propostas", "fichar_aos_poucos"):
        setattr(w.atendimento, f, lambda *a, **k: None)


def test_servidor_pega_o_que_sabe_e_o_mac_fica_com_o_resto():
    _preparar()
    r = Repo(["importar_sac", "diario", "servidor_processos", "processos"])
    srv = _tick(r, "servidor", list(c.SERVIDOR_PODE))
    assert [p["comando"] for p in srv["pendentes"]] == ["importar_sac", "servidor_processos"], srv
    assert srv["sala"], "o servidor (com o Hermes) responde na Sala"
    assert not r.t["mac_estado"], "o sinal do servidor não finge ser o Mac"
    mac = _tick(r)
    assert [p["comando"] for p in mac["pendentes"]] == ["diario", "processos"] and mac["reserva"] is True, mac
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


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
