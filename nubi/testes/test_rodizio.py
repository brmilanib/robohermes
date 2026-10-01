# -*- coding: utf-8 -*-
"""01/10 (Bruno: "usa um pouco no Mac, um pouco no Dell e um pouco no gamdias"): rodízio das leituras públicas do Mercado
Livre. Cada máquina viva recebe a sua fatia (sempre a mesma enquanto as mesmas máquinas estão vivas); sem rodízio, 1
máquina só ou máquina desconhecida: a lista inteira. Rodar: python3 testes/test_rodizio.py, na pasta nubi."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import nubi_web as w  # noqa: E402
import precos  # noqa: E402
from test_meli import Repo as _Repo  # noqa: E402


class Repo(_Repo):
    def _req(self, metodo, tabela, q=None, corpo=None, **k):
        c = str((q or {}).get("chave") or "")
        if tabela == "ia_resumos" and metodo == "DELETE":
            self.resumos.pop(c[3:], None)
            return []
        if tabela == "ia_resumos" and metodo == "GET" and c.startswith("like."):
            pre = c[5:].rstrip("*")
            return [{"chave": k_, "texto": v} for k_, v in self.resumos.items() if k_.startswith(pre)]
        return super()._req(metodo, tabela, q, corpo, **k)

ITENS = [{"mlb": f"MLB{n}"} for n in range(1000000, 1000030)]


def _vivas(mac=True, servidores=("gamdias", "dell")):
    w._mac_vivo = lambda repo, minutos=3: mac
    w.mac_pausado = lambda repo: False
    w.atendimento.servidores_vivos = lambda repo: [{"nome": n, "pode": ["ml_busca_foto", "diario"]} for n in servidores]


def test_fatias_cobrem_tudo_sem_repetir_e_sao_estaveis():
    _vivas()
    r = Repo()
    assert w.maquinas_ml(r) == ["mac", "servidor:gamdias", "servidor:dell"]
    partes = {}
    for q in ({"rodizio": "1"}, {"rodizio": "1", "maquina": "servidor", "nome": "gamdias"},
              {"rodizio": "1", "maquina": "servidor", "nome": "dell"}):
        fatia, info = w.fatia_rodizio(r, ITENS, "mlb", q)
        assert info["rodizio"] and info["de"] == 30
        partes[info["maquina"]] = [x["mlb"] for x in fatia]
    todos = sum(partes.values(), [])
    assert sorted(todos) == sorted(x["mlb"] for x in ITENS) and len(todos) == 30     # tudo coberto, nada repetido
    assert all(len(v) >= 5 for v in partes.values()), {k: len(v) for k, v in partes.items()}
    assert w.fatia_rodizio(r, ITENS, "mlb", {"rodizio": "1"})[0] == [x for x in ITENS if x["mlb"] in partes["mac"]]
    # máquina caiu: a parte dela se espalha nas outras (nada fica sem dono)
    _vivas(servidores=("gamdias",))
    a, _ = w.fatia_rodizio(r, ITENS, "mlb", {"rodizio": "1"})
    b, _ = w.fatia_rodizio(r, ITENS, "mlb", {"rodizio": "1", "maquina": "servidor", "nome": "gamdias"})
    assert len(a) + len(b) == 30 and not {x["mlb"] for x in a} & {x["mlb"] for x in b}


def test_sem_rodizio_ou_sozinha_leva_tudo():
    _vivas()
    r = Repo()
    assert w.fatia_rodizio(r, ITENS, "mlb", {})[0] == ITENS                              # comando da Central: tudo
    assert w.fatia_rodizio(r, ITENS, "mlb", {"rodizio": "1", "maquina": "servidor", "nome": "desconhecida"})[0] == ITENS
    _vivas(mac=True, servidores=())
    assert w.fatia_rodizio(r, ITENS, "mlb", {"rodizio": "1"})[0] == ITENS               # só o Mac vivo
    _vivas(mac=False, servidores=("gamdias",))
    assert w.fatia_rodizio(r, ITENS, "mlb", {"rodizio": "1", "maquina": "servidor", "nome": "gamdias"})[0] == ITENS


def test_rotas_pendentes_devolvem_a_fatia_e_o_rodar():
    _vivas()
    r = Repo()
    for x in ITENS[:6]:
        precos.seguir(r, {"mlb": x["mlb"], "titulo": "t"})
    hoje = w._agora_br().date().isoformat()
    w._rotina_na_hora = lambda repo, rid, agora=None: True
    p = w.rota_posicoes(r, "GET", "ml_precos_pendente", {"rodizio": "1"}, b"")
    p2 = w.rota_posicoes(r, "GET", "ml_precos_pendente", {"rodizio": "1", "maquina": "servidor", "nome": "dell"}, b"")
    assert p["rodizio"]["rodizio"] and p["total"] == 6 and len(p["itens"]) + len(p2["itens"]) <= 6
    assert w.rota_posicoes(r, "GET", "ml_precos_pendente", {}, b"")["itens"] and len(
        w.rota_posicoes(r, "GET", "ml_precos_pendente", {}, b"")["itens"]) == 6
    # busca por foto: quem já foi procurado hoje sai da rotina do dia (mas não do comando da Central)
    r.resumos["meli|seguidos"] = json.dumps({})
    w._vend_rels = lambda repo, vendedor=None: [{"vendedor": "MAMS ECOMMERCE TOP14"}, {"vendedor": "AIRON-AMBAR-INQUIETANTE"}]
    r.resumos["vend_fotos|MAMS ECOMMERCE TOP14"] = json.dumps({"itens": [{"Title": "Perfume X", "foto": "https://http2.mlstatic.com/D_863486-MLB114945658162_082025-O.jpg", "Si": 3}]})
    r.resumos["vend_fotos|AIRON.AMBAR.INQUIETANTE"] = json.dumps({"itens": [{"Title": "Perfume Y", "foto": "https://http2.mlstatic.com/D_111111-MLB22222222222_082025-O.jpg", "Si": 1}]})
    _vivas(mac=True, servidores=())
    b = w.rota_posicoes(r, "GET", "ml_busca_foto_pendente", {"rodizio": "1"}, b"")
    assert {v["vendedor"] for v in b["vendedores"]} == {"MAMS ECOMMERCE TOP14", "AIRON-AMBAR-INQUIETANTE"} and b["rodar"]
    w.rota_posicoes(r, "POST", "ml_busca_foto_fim", {}, json.dumps({"vendedores": ["MAMS ECOMMERCE TOP14"]}).encode())
    b = w.rota_posicoes(r, "GET", "ml_busca_foto_pendente", {"rodizio": "1"}, b"")
    assert [v["vendedor"] for v in b["vendedores"]] == ["AIRON-AMBAR-INQUIETANTE"]
    assert len(w.rota_posicoes(r, "GET", "ml_busca_foto_pendente", {}, b"")["vendedores"]) == 2
    assert json.loads(r.resumos["busca_foto|tentou"]) == {"MAMS ECOMMERCE TOP14": hoje}




def test_maquina_bloqueada_pelo_ml_sai_do_rodizio_e_da_central():
    """01/10: o gamdias caiu na verificação do ML: por 12 h ele sai do rodízio e os comandos do ML vão para o Mac."""
    _vivas()
    r = Repo()
    assert w.maquinas_ml(r) == ["mac", "servidor:gamdias", "servidor:dell"]
    w.marcar_ml_bloqueio(r, "gamdias", "FALHOU: o Mercado Livre pediu login (verificação de robô)")
    assert w.ml_bloqueado(r, "gamdias") and not w.ml_bloqueado(r, "dell")
    assert w.maquinas_ml(r) == ["mac", "servidor:dell"]
    w.atendimento.servidor_ativo = lambda repo: {"nome": "gamdias", "pode": ["hermes", "ml_busca_foto", "vitrine_seguidos", "entrar_ml", "diario"]}
    pode = w.servidor_pode(r)
    assert "ml_busca_foto" not in pode and "vitrine_seguidos" not in pode and "entrar_ml" in pode and "diario" in pode, pode
    w.desbloquear_ml(r, "gamdias")
    assert not w.ml_bloqueado(r, "gamdias") and "ml_busca_foto" in w.servidor_pode(r)
    assert w.RE_ML_BLOQUEIO.search("parou em www.mercadolivre.com.br/gz/account-verification")


if __name__ == "__main__":
    for f in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        f()
        print("ok", f.__name__)
