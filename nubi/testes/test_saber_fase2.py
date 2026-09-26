"""Base de conhecimento, fase 2 (26/09): pedaços com contexto, vetores, busca híbrida com reserva e avaliação."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("OPENAI_API_KEY", "x")
import ia  # noqa: E402
import saber  # noqa: E402


def test_pedacos_com_sobreposicao():
    assert saber.pedacos("curto") == ["curto"] and saber.pedacos("") == []
    longo = " ".join(f"Frase número {i} sobre o coletor." for i in range(400))
    ps = saber.pedacos(longo)
    assert len(ps) > 3 and all(len(p) <= saber.TAM for p in ps)
    assert ps[1][:40] in ps[0]                              # sobreposição: o começo do 2º está no fim do 1º
    assert ps[-1].endswith("coletor.")


def test_cabecalho():
    c = saber.cabecalho({"tipo": "decisao", "fonte_tabela": "reuniao_mensagens", "conversa": "sala", "autor": "Claude",
                         "criado_em": "2026-09-26T02:00:00+00:00", "titulo": "Decisões da rodada"})
    assert "decisao (mensagem da conversa sala)" in c and "em 25/09/2026" in c and "por Claude" in c   # Brasília


class Repo:
    def __init__(self, itens):
        self.itens, self.gravados, self.apagados, self.rpc = list(itens), [], [], []

    def _req(self, m, t, q=None, corpo=None, prefer=None):
        if t == "rpc/saber_pendentes":
            out, self.itens = self.itens[:corpo["lim"]], self.itens[corpo["lim"]:]
            return out
        if t == "saber_trechos" and m == "POST":
            self.gravados += corpo
        if t == "saber_trechos" and m == "DELETE":
            self.apagados.append(q)
        if t.startswith("rpc/buscar"):
            self.rpc.append((t, corpo))
            return getattr(self, t.split("/")[1], [])
        return []


def test_indexar_com_contexto_e_vetor():
    ia.embeddings = lambda textos, modelo=None: [[0.1] * 4 for _ in textos]
    ia.tem = lambda q: q == "ollama"
    ia.perguntar = lambda p, **k: ('["Trecho sobre a primeira parte.", "Trecho sobre a segunda."]', [], "ollama")
    longo = "Parágrafo A sobre o erro do coletor. " * 80
    r = Repo([{"id": 1, "tipo": "erro", "titulo": "Coletor falhou", "texto": longo, "autor": "Hermes", "fonte_tabela": "conhecimento",
               "criado_em": "2026-09-25T12:00:00+00:00", "hash": "h1"},
              {"id": 2, "tipo": "regra", "titulo": "Horário", "texto": "Sempre Brasília.", "autor": "Chefe",
               "fonte_tabela": "conhecimento", "criado_em": "2026-09-25T12:00:00+00:00", "hash": "h2"}])
    res = saber.indexar(r, segundos=30, lote=10)
    assert "2 item(ns)" in res and "1 com frase da IA" in res
    g1 = [x for x in r.gravados if x["saber_id"] == 1]
    assert len(g1) >= 2 and g1[0]["contexto"].endswith("Trecho sobre a primeira parte.") and g1[0]["hash"] == "h1"
    assert g1[0]["embedding"].startswith("[0.100000,")
    g2 = [x for x in r.gravados if x["saber_id"] == 2][0]
    assert "regra (caixa de conhecimento)" in g2["contexto"] and "—" not in g2["contexto"]    # item curto: só o cabeçalho
    assert {"saber_id": "eq.2", "ordem": "gte.1"} in r.apagados                            # tira pedaços velhos


def test_busca_hibrida_completa_com_a_antiga_sem_repetir():
    ia.embeddings = lambda textos, modelo=None: [[0.2] * 4 for _ in textos]
    r = Repo([])
    r.buscar_hibrido = [{"fonte_tabela": "conhecimento", "fonte_id": "10", "titulo": "Horário", "trecho": "Sempre Brasília"}]
    r.buscar_arquivo = [{"fonte_tabela": "conhecimento", "fonte_id": "10"}, {"fonte_tabela": "reuniao_tarefas", "fonte_id": "5"}]
    out = saber.buscar(r, "fuso horário", 5)
    assert [x["fonte_id"] for x in out] == ["10", "5"]
    assert r.rpc[0][1]["qvec"].startswith("[0.200000,")


def test_sem_openai_volta_para_a_fase_1():
    def falha(textos, modelo=None):
        raise ia.SemIA("sem chave")
    ia.embeddings = falha
    r = Repo([])
    r.buscar_arquivo = [{"fonte_tabela": "conhecimento", "fonte_id": "39"}]
    assert saber.buscar(r, "publicar branch", 5)[0]["fonte_id"] == "39"


def test_reordenar_com_ia_gratis():
    ia.tem = lambda q: q == "ollama"
    ia.perguntar = lambda p, **k: ("[2, 0]", [], "ollama")
    linhas = [{"titulo": f"t{i}"} for i in range(5)]
    assert [x["titulo"] for x in saber._reordenar("x", linhas, 3)] == ["t2", "t0", "t1"]
    ia.perguntar = lambda p, **k: ("não sei", [], "ollama")
    assert [x["titulo"] for x in saber._reordenar("x", linhas, 2)] == ["t0", "t1"]


def test_avaliacao_conta_acertos():
    ia.embeddings = lambda textos, modelo=None: [[0.3] * 4 for _ in textos]
    ia.tem = lambda q: False
    r = Repo([])
    r.buscar_hibrido = [{"fonte_tabela": "conhecimento", "fonte_id": "10"}]
    r.buscar_arquivo = []
    res = saber.avaliar(r)
    assert res["total"] == 20 and res["antiga"] == 0 and res["hibrida"] == 1 and res["reordenada"] == 1


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
