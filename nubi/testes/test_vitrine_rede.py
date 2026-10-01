# -*- coding: utf-8 -*-
"""Card #136 (01/10): na vitrine dos seguidos, um "[Errno 60] Operation timed out" no envio dos cards ao nubi
(ml_vitrine_salvar) derrubava a loja inteira e a tarefa terminava "com erros". Falha de rede tenta de novo.
Página falsa (nada do ML de verdade). Rodar: python3 testes/test_vitrine_rede.py, na pasta nubi."""
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
import coletor as c  # noqa: E402


class Pagina:
    url = "https://lista.mercadolivre.com.br/_CustId_3168346514"

    class mouse:  # noqa: N801
        @staticmethod
        def wheel(x, y):
            pass

    def add_init_script(self, js):
        pass

    def goto(self, url, **k):
        self.url = url

    def evaluate(self, js):
        return {"cards": ["<li>MLB1</li>", "<li>MLB2</li>"], "scripts": [], "total": 2}


class Contexto:
    pages = [Pagina()]

    def close(self):
        pass


def test_timeout_no_envio_tenta_de_novo():
    chamadas = []

    def api(token, rota, params=None, corpo=None, **k):
        chamadas.append(rota)
        if rota == "ml_vitrine_pendente":
            return {"lojas": [{"vendedor": "cand|3168346514|AUMA PERFUMARIA P2", "seller_id": "3168346514", "nome": "AUMA"}]}
        if chamadas.count("ml_vitrine_salvar") == 1:
            raise urllib.error.URLError(TimeoutError(60, "Operation timed out"))
        return {"mlbs": ["MLB1", "MLB2"]}

    c.api, c._ml_navegador, c._ml_bloqueado, c.devagar = api, lambda p, cfg: Contexto(), lambda pg: False, lambda s=0: None
    c.time.sleep = lambda s: None
    feitos, total, erros, msg = c.coletar_vitrine_seguidos(None, {}, "t")
    assert (feitos, total, erros) == (1, 2, 0), msg
    assert chamadas.count("ml_vitrine_salvar") == 2


if __name__ == "__main__":
    test_timeout_no_envio_tenta_de_novo()
    print("ok")
