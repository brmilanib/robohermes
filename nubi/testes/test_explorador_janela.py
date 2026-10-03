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
    # 03/10 (Bruno: "vai guardar os números para ver um mês contra outro?"): cada export fica guardado por data, e a janela
    # por anúncio fica por mês
    h = repo.resumos[nubi.HISTORICO.format("SOSPIRO") + "|2026-10-02"]
    assert (h["un"], h["anuncios"], h["top_vendedores"][0]["vendedor"]) == (432, 2, "VEND.S1"), h
    assert repo.resumos[nubi.JANELA.format("SOSPIRO") + "|2026-10"]["inicio"] == "2026-09-01"
    assert repo.resumos[nubi.CONFERENCIA.format("SOSPIRO") + "|2026-10-02"]["bate"]
    # o relatório da marca leva os 30 dias de verdade a cada vendedor do produto (o quadro usa no lugar da proporção)
    import nubi_web
    rel = nubi_web.relatorio(repo, "SOSPIRO")
    assert rel["resumo"]["janela"] == {"inicio": "2026-09-01", "fim": "2026-10-02", "dias": 32}
    vp = [v for lista in rel["vendedores_produto"].values() for v in lista]
    assert sorted((v["un"], v["un30"]) for v in vp if "un30" in v) == [(50, 32), (546, 400)], vp
    assert rel["resumo"]["conferencia"]["bate"]
    repo.fechar()


def test_calibragem_com_o_upseller():
    """03/10 (Bruno: "o Nubimetrics mostra um pouco abaixo do real; descobrindo o percentual eu sei quanto ele mostra"): meus
    anúncios no export (AURASCENT) × o relatório Vendas por Anúncio do UpSeller, pelo título e pela loja."""
    repo, cfg = _novo_banco(), {}
    repo.__dict__["resumos"] = {nubi.VENDAS_UPSELLER: {"inicio": "2026-09-01", "fim": "2026-09-30", "dias": 30, "linhas": [
        {"produto": "Perfume Vibrato Sospiro Edp 100ml Importado Original", "loja": "AURA SCENT[Mercado Libre BR]", "anuncio": "MLB1", "unidades": 32},
        {"produto": "Perfume Vibrato Sospiro Edp 100ml Importado Original", "loja": "ESSENCE PRIME[Amazon BR]", "anuncio": "B0X", "unidades": 7},
        {"produto": "Perfume Erba Pura Xerjoff 100ml", "loja": "AURA SCENT[Mercado Libre BR]", "anuncio": "MLB2", "unidades": 5}]}}
    meu = lin("Perfume Vibrato Sospiro Edp 100ml Import", "SOSPIRO", "A1", 28, 300).replace("VEND.A1", "AURASCENT")
    _importador(repo, cfg)("sospiro.csv", csv(meu, lin("Perfume Sospiro Vibrato Edp 100ml", "SOSPIRO", "K1", 400, 546)),
                           "SOSPIRO", "2026-09-01", "2026-09-30")
    cal = repo.resumos[nubi.CALIBRAGEM.format("SOSPIRO")]
    assert (cal["anuncios"], cal["un_nubimetrics"], cal["un_real"]) == (1, 28, 32), cal     # a Amazon não conta (não é ML)
    assert cal["percentual"] == 0.875 and cal["itens"][0]["anuncio_ml"] == "MLB1"
    assert nubi._loja_casa("ESSENCE", "ESSENCE PRIME[Mercado Libre BR]") and not nubi._loja_casa("ESSENCE", "ESSENCE PRIME[Amazon BR]")
    repo.fechar()


def test_visao_7_e_30_dias():
    """03/10 (Bruno: "se eu quiser ver últimos 7 dias, últimos 30 dias"): exports diários; 7 dias = histórico de hoje − o
    de 7 dias atrás; 30 dias = o export do dia; a marca inteira (vendedores, produtos) troca de números."""
    import nubi_web
    repo, cfg = _novo_banco(), {}
    imp = _importador(repo, cfg)
    imp("s0.csv", csv(lin("Perfume Sospiro Vibrato Edp 100ml", "SOSPIRO", "S1", 300, 500),
                      lin("Perfume Sospiro Erba Gold Edp 100ml", "SOSPIRO", "S2", 20, 100)), "SOSPIRO", "2026-08-27", "2026-09-25")
    # 7 dias depois: S1 vendeu 70 (histórico 570), S2 vendeu 0, S3 é novo (8 un.)
    imp("s7.csv", csv(lin("Perfume Sospiro Vibrato Edp 100ml", "SOSPIRO", "S1", 320, 570).replace(";100;01/01/2026", ";89,90;01/01/2026"),
                      lin("Perfume Sospiro Erba Gold Edp 100ml", "SOSPIRO", "S2", 15, 100),
                      lin("Perfume Sospiro Accento Edp 100ml", "SOSPIRO", "S3", 8, 8)), "SOSPIRO", "2026-09-03", "2026-10-02")
    r7 = nubi_web.relatorio(repo, "SOSPIRO", visao="7")
    # 03/10 (Bruno: "mostra se tá caindo ou crescendo" e "as mudanças de preço pelos exports diários")
    mp = r7["mudancas_preco"]
    assert len(mp) == 1 and (mp[0]["de"], mp[0]["para"], mp[0]["dia"]) == (100.0, 89.9, "2026-10-02") and mp[0]["codigo"], mp
    vib = [x for x in r7["tabelas"]["produtos"] if "Vibrato" in x["produto"]][0]
    assert round(vib["tend"], 3) == round((70 / 7) / (320 / 30) - 1, 3), vib       # 10/dia na semana × 10,7/dia no mês
    erba = [x for x in r7["tabelas"]["produtos"] if "Erba" in x["produto"]][0]
    assert erba["tend"] == -1.0 and [x["produto"] for x in r7["tendencias"]["caindo"]] == [erba["produto"]], r7["tendencias"]
    v1 = r7["vendedores_produto"][vib["produto"]][0]
    assert v1["un7"] == 70 and v1["dias7"] == 7 and v1["tend"] is not None
    # 03/10 (Bruno: "clicar no preço do vendedor e ver o gráfico do dia, do preço e das unidades"): série por dia
    se = nubi_web.explorador_serie(repo, "SOSPIRO", v1["vid"], vib["produto"])
    assert [(p["dia"], p["preco"], p["un"]) for p in se["pontos"]] == [("2026-09-25", 100.0, None), ("2026-10-02", 89.9, 70)], se
    assert se["anuncios"] == 1 and len(se["mudancas"]) == 1
    assert r7["resumo"]["visao"] == {"tipo": "7", "inicio": "2026-09-26", "fim": "2026-10-02", "dias": 7}, r7["resumo"]["visao"]
    assert r7["resumo"]["un"] == 78 and r7["resumo"]["dias"] == 7, r7["resumo"]
    r30 = nubi_web.relatorio(repo, "SOSPIRO", visao="30")
    assert r30["resumo"]["un"] == 343 and r30["resumo"]["visao"]["dias"] == 30
    rc = nubi_web.relatorio(repo, "SOSPIRO")
    assert rc["resumo"]["visao"] is None and rc["resumo"]["tem_7"] and rc["resumo"]["tem_30"]
    repo.fechar()


def test_rota_do_explorador_diario_chega_no_servidor():
    """03/10: explorador_diario_pendente morava em rota_estoque, que só recebia estoque*/gestor_*: o coletor ganhava
    "Rota desconhecida" e o Explorador diário nunca rodou."""
    import json
    import nubi_web as w

    class R:
        def __init__(self, *a, **k):
            pass

        def _req(self, m, t, q=None, corpo=None, prefer=None):
            return [{"texto": json.dumps(["SOSPIRO"])}] if t == "ia_resumos" and "marcas_diarias" in str(q) else []

        def _eq(self, v):
            return f"eq.{v}"

        def _todos(self, t, q=None):
            return []
    antes = w.RepoSupabase, w.ligar_registro_uso
    w.RepoSupabase, w.ligar_registro_uso = R, (lambda *a, **k: None)
    try:
        st, _, corpo, _ = w.atender("GET", "explorador_diario_pendente", {}, b"", "TOKEN")
        assert st == 200 and json.loads(corpo)["marcas"] == ["SOSPIRO"], corpo
        st, _, corpo, _ = w.atender("GET", "explorador_quinzena_pendente", {}, b"", "TOKEN")
        assert st == 200, corpo
    finally:
        w.RepoSupabase, w.ligar_registro_uso = antes


if __name__ == "__main__":
    test_visao_7_e_30_dias()
    test_rota_do_explorador_diario_chega_no_servidor()
    test_janela_de_30_dias_e_conferencia()
    test_calibragem_com_o_upseller()
    print("ok explorador janela")
