"""30/09 (Bruno: "o Hermes e o gpt-oss têm que revisar e otimizar todo dia, tarefa simples e robótica"): o gpt-oss propõe
correções do agrupamento a partir da conferência do dia, o Hermes confere, e só o que os dois concordam é aplicado."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import nubi  # noqa: E402
import revisao  # noqa: E402
import nubi_web as w  # noqa: E402
import ia  # noqa: E402


class Repo:
    def __init__(self):
        self.res, self.cfg, self.apelidos, self.comandos, self.sala = {}, {"LATTAFA": {"linhas": [["asad", "Asad"], ["fakhar rose", "Fakhar Rose"]]}}, [], [], []

    def _eq(self, v):
        return f"eq.{v}"

    def _req(self, metodo, tabela, params=None, corpo=None, prefer=None):
        if tabela == "ia_resumos":
            if metodo == "GET":
                ch = (params or {}).get("chave", "")
                if ch.startswith("like."):
                    pref = ch[5:].rstrip("*")
                    ks = sorted((k for k in self.res if k.startswith(pref)), reverse=True)
                    return [{"texto": self.res[ks[0]], "criado_em": "x"}] if ks else []
                ch = ch.replace("eq.", "")
                return [{"texto": self.res[ch]}] if ch in self.res else []
            for r in corpo:
                self.res[r["chave"]] = r["texto"]
            return []
        if tabela == "mac_comandos":
            if metodo == "GET":
                return [c for c in self.comandos if c["status"] == "pendente"]
            self.comandos += corpo
            return []
        if tabela == "marca_apelidos":
            if metodo == "POST":
                self.apelidos += corpo
            return []
        if tabela == "reuniao_mensagens":
            self.sala += corpo
            return []
        return []

    def _todos(self, tabela, params=None):
        return []

    def snapshots(self, marca=None):                 # 01/10: a trava simula no último export (aqui, sem export)
        import pandas as pd
        return pd.DataFrame(columns=["id", "marca"])

    def carregar_config(self):
        return json.loads(json.dumps(self.cfg))

    def salvar_config(self, cfg, marca=None, apagar=None):
        self.cfg[marca] = cfg[marca]


AUD = {"marcas": [{"marca": "LATTAFA", "nota": 90, "achados": [
    {"tipo": "outra_marca_grande", "nome": "PERFUMES ÁRABES", "un": 500, "texto": "..."},
    {"tipo": "linhas_parecidas", "nome": "Khamrah / Khamarh", "un": 300, "texto": "..."},
    {"tipo": "marca_errada", "nome": "Lataffa", "un": 800, "corrigido": True}],
    "outros_top": [{"titulo": "Perfume Lattafa Ansaam Gold Edp 100ml", "un": 120}, {"titulo": "Lattafa Ansaam Gold 100 Ml", "un": 30}]},
    {"marca": "ARMAF", "nota": 99, "achados": [], "outros_top": [{"titulo": "Armaf Kit 3 Amostras", "un": 2}]}]}


def test_itens_pedido_e_propostas():
    itens = revisao.itens_da_auditoria(AUD, Repo().carregar_config())
    assert [i["tipo"] for i in itens] == ["outra_marca_grande", "linhas_parecidas", "outros_top"], itens   # ARMAF: < 5 un., fora
    txt = revisao.pedido(itens)
    assert "#1 marca LATTAFA" in txt and "Khamrah" in txt and "Ansaam Gold" in txt
    resp = {"decisoes": [
        {"id": 1, "acao": "outra_marca", "confianca": "alta", "motivo": "é categoria, não marca"},
        {"id": 2, "acao": "mesma_linha", "valor": "Khamrah", "confianca": "alta", "motivo": "erro de digitação"},
        {"id": 3, "acao": "linha_nova", "valor": "Ansaam Gold", "confianca": "alta", "motivo": "nome nos títulos"},
        {"id": 3, "acao": "linha_nova", "valor": "Perfume", "confianca": "alta", "motivo": "x"},          # palavra de anúncio: fora
        {"id": 9, "acao": "linha_nova", "valor": "Y", "confianca": "alta"}]}
    props = revisao.propostas_de(itens, resp)
    assert [(p["id"], p["acao"], p["valor"]) for p in props] == [(2, "mesma_linha", "Khamrah"), (3, "linha_nova", "Ansaam Gold")], props
    assert not revisao.propostas_de(itens, {"decisoes": [{"id": 2, "acao": "mesma_linha", "valor": "Khamrah", "confianca": "média"}]})
    print("ok test_itens_pedido_e_propostas")


def test_fluxo_gptoss_propoe_hermes_confere_e_aplica():
    r = Repo()
    hoje = w._agora_br().date().isoformat()
    r.res[w.AUDITORIA_CHAVE + hoje] = json.dumps(dict(AUD, dia=hoje))
    chamadas = []

    def fake_json(pergunta, **k):
        chamadas.append(k.get("qual"))
        return {"decisoes": [{"id": 1, "acao": "mesma_marca", "confianca": "alta", "motivo": "m"},
                             {"id": 2, "acao": "mesma_linha", "valor": "Khamrah", "confianca": "alta", "motivo": "m"},
                             {"id": 3, "acao": "linha_nova", "valor": "Ansaam Gold", "confianca": "alta", "motivo": "m"}]}, [], "ollama"
    orig = (ia.perguntar_json, nubi.reconsolidar, w._preparar)
    ia.perguntar_json = fake_json
    reproc = []
    nubi.reconsolidar = lambda repo, cfg, marcas=None: reproc.append(marcas)
    w._preparar = lambda repo: None
    try:
        res = w.revisar_agrupamento(r)
        assert "3 proposta(s)" in res and chamadas == ["ollama"], res
        assert r.comandos and r.comandos[0]["comando"] == "hermes_revisao"
        assert w.revisar_agrupamento(r) == "já feita hoje"
        pend = w.revisao_pendente(r)
        assert len(pend["propostas"]) == 3 and "Você concorda?" in pend["propostas"][0]["pedido"]
        # Hermes concorda com 2 e 3, discorda da 1 (PERFUMES ÁRABES não é a Lattafa)
        out = w.aplicar_revisao(r, hoje, [{"id": 1, "concordo": False, "motivo": "é categoria"},
                                          {"id": 2, "concordo": True, "motivo": "ok"}, {"id": 3, "concordo": True, "motivo": "ok"}])
        assert out["marcas"] == ["LATTAFA"] and len(out["aplicadas"]) == 2 and len(out["recusadas"]) == 1, out
        assert not r.apelidos                                                     # a 1 foi recusada: nenhum apelido
        linhas = r.cfg["LATTAFA"]["linhas"]
        assert ["ansaam gold", "Ansaam Gold"] in linhas and ["khamarh", "Khamrah"] in linhas, linhas
        assert reproc == [["LATTAFA"]] and r.sala and r.sala[0]["autor"] == "Hermes" and "Não apliquei" in r.sala[0]["texto"]
        assert w.revisao_pendente(r)["propostas"] == []                            # já aplicada
    finally:
        ia.perguntar_json, nubi.reconsolidar, w._preparar = orig
    print("ok test_fluxo_gptoss_propoe_hermes_confere_e_aplica")


def test_aplicar_no_config_mesma_linha_com_rotulo_existente():
    cfg = {"LATTAFA": {"linhas": [["khamrah", "Khamrah"], ["khamarh", "Khamarh"]]}}
    assert revisao.aplicar_no_config(cfg, {"marca": "LATTAFA", "acao": "mesma_linha", "nome": "Khamrah / Khamarh", "valor": "Khamrah"})
    assert cfg["LATTAFA"]["linhas"] == [["khamrah", "Khamrah"], ["khamarh", "Khamrah"]]
    assert not revisao.aplicar_no_config(cfg, {"marca": "LATTAFA", "acao": "linha_nova", "valor": "Khamrah"})   # já existe
    print("ok test_aplicar_no_config_mesma_linha_com_rotulo_existente")


if __name__ == "__main__":
    test_itens_pedido_e_propostas()
    test_fluxo_gptoss_propoe_hermes_confere_e_aplica()
    test_aplicar_no_config_mesma_linha_com_rotulo_existente()
