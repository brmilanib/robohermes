# -*- coding: utf-8 -*-
"""03/10 (Bruno, Sospiro Vibrato: "não bate o número de venda do UpSeller com o nubi nem com o Nubimetrics"): a regra 14
juntava o export de 30 dias no card de 63 dias e o quadro fazia 63 × 30 ÷ 63. Agora cada export guarda a JANELA do arquivo
(un, fat e histórico por ID de anúncio) e a conferência com o Nubimetrics (vendas históricas no card = as do export)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import nubi  # noqa: E402
from test_importar_sem_roubar import _importador, _novo_banco, csv, lin, un_card  # noqa: E402


def test_janela_de_30_dias_e_conferencia():
    repo, cfg = _novo_banco(), {}
    imp = _importador(repo, cfg)
    # card de 63 dias (01/08–02/10): o líder (S1) criou o anúncio no fim de julho e vendeu quase tudo em setembro
    imp("sospiro_63.csv", csv(lin("Perfume Sospiro Vibrato Edp 100ml", "SOSPIRO", "S1", 546, 546),
                              lin("Perfume Sospiro Vibrato Edp 100ml", "SOSPIRO", "S2", 50, 400)), "SOSPIRO", "2026-08-01", "2026-10-02")
    # export dos últimos 30 dias (01/09–02/10, o que o Explorador mostra): S1 vendeu 400 e S2 32
    imp("sospiro_30.csv", csv(lin("Perfume Sospiro Vibrato Edp 100ml", "SOSPIRO", "S1", 400, 546),
                              lin("Perfume Sospiro Vibrato Edp 100ml", "SOSPIRO", "S2", 32, 400),
                              lin("Perfume Lattafa Asad Edp 100ml", "LATTAFA", "L1", 9, 9)), "SOSPIRO", "2026-09-01", "2026-10-02")
    ini, fim, dias, un = un_card(repo, "SOSPIRO")
    assert (ini, fim, dias) == ("2026-08-01", "2026-10-02", 63)        # a regra 14 continua: um card só
    jan = nubi.ler_janela(repo, "SOSPIRO")
    assert (jan["inicio"], jan["fim"], jan["dias"]) == ("2026-09-01", "2026-10-02", 32)
    por_id = {k.split(":")[-1] if ":" in k else k: v for k, v in jan["anuncios"].items()}
    assert sorted(v[0] for v in jan["anuncios"].values()) == [9, 32, 400]   # os números do ARQUIVO, sem proporção
    assert por_id
    conf = repo.resumos[nubi.CONFERENCIA.format("SOSPIRO")]
    assert conf["bate"] and conf["export"]["un_hist"] == 946 and conf["nubi"]["un_hist"] == 946, conf
    assert conf["export"]["anuncios"] == 2                                 # o anúncio da Lattafa não é da marca
    # o relatório da marca leva os 30 dias de verdade a cada vendedor do produto (o quadro usa no lugar da proporção)
    import nubi_web
    rel = nubi_web.relatorio(repo, "SOSPIRO")
    assert rel["resumo"]["janela"] == {"inicio": "2026-09-01", "fim": "2026-10-02", "dias": 32}
    vp = [v for lista in rel["vendedores_produto"].values() for v in lista]
    assert sorted((v["un"], v["un30"]) for v in vp if "un30" in v) == [(50, 32), (546, 400)], vp
    assert rel["resumo"]["conferencia"]["bate"]
    repo.fechar()


if __name__ == "__main__":
    test_janela_de_30_dias_e_conferencia()
    print("ok explorador janela")
