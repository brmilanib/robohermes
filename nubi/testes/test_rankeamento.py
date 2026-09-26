"""Laboratório de Rankeamento (26/09): pesquisador + agentes contribuem e votam na mesma box; o coordenador fecha status e plano."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
os.environ.setdefault("ANTHROPIC_API_KEY", "x")
import nubi_web as w  # noqa: E402


class Repo:
    def __init__(self):
        self.t = {"rank_box": [], "meus_anuncios": [{"id": "MLB1", "loja": "aurascent", "titulo": "Club De Nuit", "preco": 249, "termo": "club nuit"}],
                  "anuncio_posicoes": [], "reuniao_mensagens": []}
        self.seq = 0

    def _eq(self, v):
        return f"eq.{v}"

    def _todos(self, t, q=None):
        return [dict(x) for x in self.t.get(t, [])]

    def _req(self, m, t, q=None, corpo=None, prefer=None):
        q = q or {}
        if m == "POST":
            for c in corpo:
                if t == "rank_box":
                    self.seq += 1
                    c = dict({"id": self.seq, "status": "nova", "votos": {}, "criado_em": "x", "atualizado_em": "x"}, **c)
                self.t.setdefault(t, []).append(c)
            return []
        rows = self.t.get(t, [])
        if "id" in q:
            rows = [r for r in rows if str(r["id"]) == q["id"][3:]]
        if q.get("tipo") == "eq.plano":
            rows = [r for r in rows if r["tipo"] == "plano"]
        if q.get("tipo") == "neq.comentario":
            rows = [r for r in rows if r["tipo"] != "comentario"]
        if m == "PATCH":
            for r in rows:
                r.update(corpo)
            return []
        return [dict(r) for r in rows]


def test_time_trabalha_junto_na_box():
    r = Repo()
    w.ia.disponivel = lambda: True
    chamadas = []

    def perguntar_json(pedido, **k):
        chamadas.append(pedido)
        if "PESQUISADOR" in pedido:
            return {"contribuicoes": [{"tipo": "tecnica", "titulo": "Full aumenta a exposição", "texto": "…", "fonte": "https://vendedores.mercadolivre.com.br/x"}]}, [], "claude"
        return {"status": [{"id": 1, "status": "testando", "motivo": "tem fonte, falta medir"}], "plano": "1. Colocar o MLB1 no Full", "resumo_sala": "plano pronto"}, [], "claude"
    w.ia.perguntar_json = perguntar_json
    w.agentes.ativos = lambda citados=None: ["deepseek", "gptoss"]
    respostas = {"deepseek": {"contribuicoes": [{"tipo": "hipotese", "titulo": "Preço 5% abaixo do 1º sobe 1 página", "anuncio_id": "mlb1"},
                                                 {"tipo": "tecnica", "titulo": "Full aumenta a exposição"}],     # repetida: não entra
                              "votos": [{"id": 1, "voto": 1, "motivo": "faz sentido"}]},
                 "gptoss": {"contribuicoes": [{"tipo": "experimento", "titulo": "Trocar a foto principal do MLB1 por 7 dias"}],
                            "votos": [{"id": 2, "voto": -1, "motivo": "preço menor pode reduzir margem"}]}}
    w.agentes.perguntar = lambda chave, texto, **k: (chamadas.append(texto) or json.dumps(respostas[chave]))
    res = w.laboratorio_rankeamento(r, forcar=True)
    box = r.t["rank_box"]
    titulos = [b["titulo"] for b in box if b["tipo"] not in ("comentario", "plano")]
    assert titulos == ["Full aumenta a exposição", "Preço 5% abaixo do 1º sobe 1 página", "Trocar a foto principal do MLB1 por 7 dias"]
    assert box[1]["autor"] == "DeepSeek" and box[1]["anuncio_id"] == "MLB1"
    assert box[0]["votos"] == {"DeepSeek": 1} and box[0]["status"] == "testando"                 # voto + status do coordenador
    assert any(b["tipo"] == "plano" and "Full" in b["texto"] for b in box)
    assert "Full aumenta a exposição" in chamadas[-1]                                              # o coordenador leu a box
    assert "Preço 5% abaixo" in chamadas[2]                                                        # o gpt-oss leu o que o DeepSeek escreveu
    assert r.t["reuniao_mensagens"] and "plano ok" in res


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
