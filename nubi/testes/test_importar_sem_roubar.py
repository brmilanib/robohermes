# -*- coding: utf-8 -*-
"""02/10 (Bruno: "faça o teste antes" — importar o Explorador de setembro da AL WATANIAH, pesquisa expandida, não pode mexer
nos números que já existem): o export expandido traz anúncios da ARMAF, que já tem o mesmo período (01/09–30/09) importado.
O anúncio da Armaf fica no card da Armaf (sem contar duas vezes); só o anúncio da Al Wataniah que estava perdido no card
da Armaf passa para a Al Wataniah; o período antigo da Al Wataniah (01/08–28/09) não muda. Banco local (SQLite) temporário."""
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import pandas as pd  # noqa: E402
import nubi  # noqa: E402

CAB = ("Título;Vendedor;Categoria L1;Categoria final;Código Completo da Categoria;Código da Categoria L1;Código da Categoria Final;"
       "Categoria completa;Vendas em $ históricas;Vendas em $;Unidades vendidas históricas;Unidades vendidas;Último preço;"
       "Data de criação;Dias publicados;Exposição;Catálogo;FULL;FLEX;Compra Internacional;Marca;Modelo;Loja oficial;Frete grátis;"
       "ID do anúncio;ID do vendedor;Sku;Gtin;N° Peça;Oem")


def lin(titulo, marca, id_, un, hist):
    return (f"{titulo};VEND.{id_};Beleza e Cuidado Pessoal;Perfumes;;;;;{hist * 100};{un * 100};{hist};{un};100;01/01/2026;200;"
            f"Clássico;Não;Sim;Não;Não;{marca};;;Sim;{id_};h{id_};;;;")


def csv(*linhas):
    return "\n".join([CAB, *linhas]).encode("utf-8")


def un_por_snapshot(repo, sid):
    return int(repo.anuncios(sid)["un"].astype(int).sum())


def test_expandido_nao_rouba_nem_soma():
    tmp = Path(tempfile.mkdtemp())
    nubi.DADOS, nubi.BANCO, nubi.CONFIG, nubi.ARQ_GTINS = tmp, tmp / "base.db", tmp / "marcas.json", tmp / "gtins.json"
    nubi.definir_gtin_global({})
    nubi.INFO_GTIN.clear()
    repo = nubi.RepoLocal()
    cfg = {}
    imp = lambda nome, dados, marca, ini, fim: nubi.importar_dados(
        repo, cfg, nome, dados, lambda s: (marca, date.fromisoformat(ini), date.fromisoformat(fim)))
    # já no banco: AL WATANIAH 01/08–28/09 e ARMAF 01/09–30/09 (com 1 anúncio da Al Wataniah perdido no card da Armaf)
    imp("alw_59.csv", csv(lin("Perfume Al Wataniah Sabah Al Ward Edp 100ml", "AL WATANIAH", "W1", 900, 5000)),
        "AL WATANIAH", "2026-08-01", "2026-09-28")
    imp("armaf.csv", csv(lin("Perfume Armaf Club De Nuit Intense Man Edt 105ml", "ARMAF", "A1", 9000, 47000),
                         lin("Perfume Al Wataniah Ameerati Edp 100ml", "AL WATANIAH", "W2", 50, 300)),
        "ARMAF", "2026-09-01", "2026-09-30")
    s = repo.snapshots()
    id_alw59 = int(s[(s["marca"] == "AL WATANIAH")]["id"].iloc[0])
    antes_59 = un_por_snapshot(repo, id_alw59)
    # o export expandido da AL WATANIAH de setembro: traz o anúncio da Armaf (A1) e o perdido (W2)
    imp("alw_set.csv", csv(lin("Perfume Al Wataniah Sabah Al Ward Edp 100ml", "AL WATANIAH", "W1", 450, 5060),
                           lin("Perfume Armaf Club De Nuit Intense Man Edt 105ml", "ARMAF", "A1", 9000, 47000),
                           lin("Perfume Al Wataniah Ameerati Edp 100ml", "AL WATANIAH", "W2", 50, 300)),
        "AL WATANIAH", "2026-09-01", "2026-09-30")
    s = repo.snapshots()
    armaf = s[s["marca"] == "ARMAF"]
    alw = s[s["marca"] == "AL WATANIAH"]
    ids_armaf = set(repo.anuncios(int(armaf["id"].iloc[0]))["bruto"].map(lambda b: b.get("ID do anúncio")))
    assert ids_armaf == {"A1"}, ids_armaf                 # a Armaf continua com o dela e perde só o perdido (W2)
    # REGRA 14 (02/10, Bruno: "tem que ser aplicado para todos os cards"): setembro NÃO vira outro card; o card de 59 dias
    # vira 01/08–30/09 somando só a diferença: W1 900 + (5060 − 5000) = 960; W2 (que esperava na Armaf) entra inteiro
    assert len(alw) == 1 and str(alw["inicio"].iloc[0])[:10] == "2026-08-01" and str(alw["fim"].iloc[0])[:10] == "2026-09-30", alw
    a = repo.anuncios(int(alw["id"].iloc[0]))
    un = {b.get("ID do anúncio"): int(u) for b, u in zip(a["bruto"], a["un"])}
    assert un == {"W1": 960, "W2": 50}, un                 # A1 não entra na Al Wataniah: não conta duas vezes
    assert int(alw["dias"].iloc[0]) == 61 and antes_59 == 950      # 950 = o W2 já tinha entrado de carona na importação da Armaf
    repo.fechar()


def _novo_banco():
    tmp = Path(tempfile.mkdtemp())
    nubi.DADOS, nubi.BANCO, nubi.CONFIG, nubi.ARQ_GTINS = tmp, tmp / "base.db", tmp / "marcas.json", tmp / "gtins.json"
    nubi.definir_gtin_global({})
    nubi.INFO_GTIN.clear()
    return nubi.RepoLocal()


def _importador(repo, cfg):
    return lambda nome, dados, marca, ini, fim: nubi.importar_dados(
        repo, cfg, nome, dados, lambda s: (marca, date.fromisoformat(ini), date.fromisoformat(fim)))


def ids_do(repo, marca, ini):
    """{ID do anúncio: tipo} do card da marca que começa em `ini`."""
    s = repo.snapshots()
    sn = s[(s["marca"] == marca) & (s["inicio"].astype(str).str[:10] == ini)]
    if sn.empty:
        return None
    a = repo.anuncios(int(sn["id"].iloc[0]))
    return {b.get("ID do anúncio"): t for b, t in zip(a["bruto"], a["tipo"])}


def test_outras_marcas_vao_para_o_card_certo():
    """02/10 (Bruno: "os anúncios das outras marcas que vêm têm que ser colocados nos cards das marcas corretas"; Al Wataniah
    set/26 mostrava R$ 12,4 mi com 2.576 anúncios de outras marcas): marca com card do MESMO período recebe o anúncio dela;
    marca sem card: o anúncio espera no card de quem importou, fora da conta, e passa quando o export dela entra."""
    import nubi_web
    repo, cfg = _novo_banco(), {}
    imp = _importador(repo, cfg)
    # LATTAFA já tem setembro (com L1); AL HARAMAIN não tem card de setembro
    imp("lattafa.csv", csv(lin("Perfume Lattafa Yara Edp 100ml", "LATTAFA", "L1", 800, 4000)), "LATTAFA", "2026-09-01", "2026-09-30")
    imp("alw_set.csv", csv(lin("Perfume Al Wataniah Sabah Al Ward Edp 100ml", "AL WATANIAH", "W1", 450, 5060),
                           lin("Perfume Lattafa Yara Edp 100ml", "LATTAFA", "L1", 800, 4000),
                           lin("Perfume Lattafa Asad Edp 100ml", "LATTAFA", "L2", 300, 900),
                           lin("Perfume Al Haramain Amber Oud Edp 60ml", "AL HARAMAIN", "H1", 120, 500)),
        "AL WATANIAH", "2026-09-01", "2026-09-30")
    assert set(ids_do(repo, "LATTAFA", "2026-09-01")) == {"L1", "L2"}      # L2 veio na busca expandida: card da Lattafa
    # os anúncios de carona entram no card da Lattafa com os números da Lattafa (L1 estava lá: cópia descartada)
    la = repo.anuncios(int(repo.snapshots().query("marca == 'LATTAFA'")["id"].iloc[0]))
    assert {b.get("ID do anúncio"): int(u) for b, u in zip(la["bruto"], la["un"])} == {"L1": 800, "L2": 300}
    # 02/10 (Bruno: "marca sem card? cria o card dela, é marca nova"): a Al Haramain nasce com o H1
    assert set(ids_do(repo, "AL WATANIAH", "2026-09-01")) == {"W1"}
    assert ids_do(repo, "AL HARAMAIN", "2026-09-01") == {"H1": "EDP"}
    # a página da marca conta SÓ a marca (450 un. do W1), sem "Outras marcas"
    r = nubi_web.relatorio(repo, "AL WATANIAH")
    z = r["resumo"]
    assert z["un"] == 450 and z["anuncios"] == 1 and z["vendedores"] == 1 and z["fat"] == 45000, z
    assert z["un_outras_marcas"] == 0 and r["tabelas"]["outras"] == []
    assert [v["vendedor"] for v in r["tabelas"]["vendedores"]] == ["VEND.W1"]
    assert all(p["produto"].startswith("Al Wataniah") for p in r["tabelas"]["produtos"]), r["tabelas"]["produtos"]
    # chega o export de setembro da AL HARAMAIN (busca exata, SEM o H1): mesmo período, o H2 entra e o H1 fica
    imp("alh.csv", csv(lin("Perfume Al Haramain Lavender Oud Edp 100ml", "AL HARAMAIN", "H2", 60, 200)),
        "AL HARAMAIN", "2026-09-01", "2026-09-30")
    assert set(ids_do(repo, "AL HARAMAIN", "2026-09-01")) == {"H1", "H2"}
    assert set(ids_do(repo, "AL WATANIAH", "2026-09-01")) == {"W1"}
    assert set(ids_do(repo, "LATTAFA", "2026-09-01")) == {"L1", "L2"}
    assert nubi_web.relatorio(repo, "AL HARAMAIN")["resumo"]["un"] == 180
    repo.fechar()


def test_encaminhar_card_importado_antes_da_regra():
    """Card importado antes desta regra (o 1008 da Al Wataniah): `encaminhar_outras_marcas` (rota `explorador_encaminhar`,
    botão da aba Outras marcas) leva os anúncios de outra marca para o card dela no mesmo período."""
    repo, cfg = _novo_banco(), {}
    imp = _importador(repo, cfg)
    imp("klassey.csv", csv(lin("Perfume Klassey Noir Edp 100ml", "KLASSEY", "K1", 100, 300)), "KLASSEY", "2026-09-01", "2026-09-30")
    juntar = nubi._juntar_por_id
    nubi._juntar_por_id = lambda repo_, cfg_, marca, ini, fim, df, recem=(), *a, **k: nubi._ids(df)   # como a importação era antes
    try:
        imp("alw.csv", csv(lin("Perfume Al Wataniah Sabah Al Ward Edp 100ml", "AL WATANIAH", "W1", 450, 5060),
                           lin("Perfume Klassey Noir Edp 100ml", "KLASSEY", "K1", 100, 300),
                           lin("Perfume Klassey Rouge Edp 100ml", "KLASSEY", "K2", 40, 90)),
            "AL WATANIAH", "2026-09-01", "2026-09-30")
    finally:
        nubi._juntar_por_id = juntar
    assert set(ids_do(repo, "AL WATANIAH", "2026-09-01")) == {"W1", "K1", "K2"}
    s = repo.snapshots()
    sid = int(s[s["marca"] == "AL WATANIAH"]["id"].iloc[0])
    r = nubi.encaminhar_outras_marcas(repo, cfg, "AL WATANIAH", sid)
    assert r == {"marcas": {"KLASSEY": 1}, "saiu": 2}, r       # K1 já estava lá (a cópia sai daqui); K2 entra no card da Klassey
    assert set(ids_do(repo, "KLASSEY", "2026-09-01")) == {"K1", "K2"}
    assert set(ids_do(repo, "AL WATANIAH", "2026-09-01")) == {"W1"}
    assert nubi.encaminhar_outras_marcas(repo, cfg, "AL WATANIAH", int(repo.snapshots().query("marca == 'AL WATANIAH'")["id"].iloc[0])) == {"marcas": {}, "saiu": 0}
    repo.fechar()


def un_card(repo, marca):
    s = repo.snapshots(marca)
    assert len(s) == 1, s
    a = repo.anuncios(int(s["id"].iloc[0]))
    return (str(s["inicio"].iloc[0])[:10], str(s["fim"].iloc[0])[:10], int(s["dias"].iloc[0]),
            {b.get("ID do anúncio"): int(u) for b, u in zip(a["bruto"], a["un"])})


def test_regra_14_card_vivo():
    """REGRA 14 (02/10, Bruno: "é o mesmo anúncio? mesmo período? descarta. Período maior? só a diferença. Não tem? é novo,
    entra somando. Mesma coisa o vendedor e a marca"): todo export do Explorador entra no card da marca pela diferença."""
    repo, cfg = _novo_banco(), {}
    imp = _importador(repo, cfg)
    # card da Lattafa 01/08–29/09: L1 (800 un., histórico 4.000) e L3 (50 / 100)
    imp("lattafa_60.csv", csv(lin("Perfume Lattafa Yara Edp 100ml", "LATTAFA", "L1", 800, 4000),
                              lin("Perfume Lattafa Khamrah Edp 100ml", "LATTAFA", "L3", 50, 100)), "LATTAFA", "2026-08-01", "2026-09-29")
    # de carona no export expandido da Al Wataniah (01/09–30/09): L1 (histórico 4.030 = vendeu 30 no dia 30) e L2 novo
    imp("alw.csv", csv(lin("Perfume Al Wataniah Sabah Al Ward Edp 100ml", "AL WATANIAH", "W1", 450, 5060),
                       lin("Perfume Lattafa Yara Edp 100ml", "LATTAFA", "L1", 700, 4030),
                       lin("Perfume Lattafa Asad Edp 100ml", "LATTAFA", "L2", 300, 900)), "AL WATANIAH", "2026-09-01", "2026-09-30")
    assert un_card(repo, "LATTAFA") == ("2026-08-01", "2026-09-30", 61, {"L1": 830, "L2": 300, "L3": 50})
    assert un_card(repo, "AL WATANIAH") == ("2026-09-01", "2026-09-30", 30, {"W1": 450})
    assert [(d["marca"], d["de"], d["ate"], d["un"]) for d in repo.dias] == [("LATTAFA", "2026-09-29", "2026-09-30", 330)]
    # export da própria Lattafa de outubro (01/10–01/10): L1 vendeu 20 (histórico 4.050) → card 01/08–01/10
    imp("lattafa_out.csv", csv(lin("Perfume Lattafa Yara Edp 100ml", "LATTAFA", "L1", 20, 4050)), "LATTAFA", "2026-10-01", "2026-10-01")
    assert un_card(repo, "LATTAFA") == ("2026-08-01", "2026-10-01", 62, {"L1": 850, "L2": 300, "L3": 50})
    # mesmo início (o export cobre o período inteiro): números do export substituem, o card estica
    imp("alw_2.csv", csv(lin("Perfume Al Wataniah Sabah Al Ward Edp 100ml", "AL WATANIAH", "W1", 470, 5080),
                         lin("Perfume Al Wataniah Ameerati Edp 100ml", "AL WATANIAH", "W2", 5, 5)), "AL WATANIAH", "2026-09-01", "2026-10-02")
    assert un_card(repo, "AL WATANIAH") == ("2026-09-01", "2026-10-02", 32, {"W1": 470, "W2": 5})
    d = [x for x in repo.dias if x["marca"] == "AL WATANIAH"][-1]
    assert (d["de"], d["ate"], d["un"], d["anuncios_novos"]) == ("2026-09-30", "2026-10-02", 25, 1), d
    # export mais velho que o card (01/09–30/09 de novo, com um anúncio que faltava): o card já cobre; só o novo entra
    imp("alw_velho.csv", csv(lin("Perfume Al Wataniah Sabah Al Ward Edp 100ml", "AL WATANIAH", "W1", 450, 5060),
                             lin("Perfume Al Wataniah Durrat Edp 85ml", "AL WATANIAH", "W3", 9, 9)), "AL WATANIAH", "2026-09-01", "2026-09-30")
    assert un_card(repo, "AL WATANIAH") == ("2026-09-01", "2026-10-02", 32, {"W1": 470, "W2": 5, "W3": 9})
    # carona com erro de digitação vai para a marca certa; título colado no campo Marca e marca genérica ficam onde estão
    imp("alw_3.csv", csv(lin("Perfume Al Wataniah Sabah Al Ward Edp 100ml", "AL WATANIAH", "W1", 480, 5090),
                         lin("Perfume Lataffa Yara Edp 100ml", "LATAFFA", "L4", 7, 7),
                         lin("Toff Pomada Creme 100g", "TOFF POMADA CREME 100G N3 GEL INTENSO DORES", "T1", 30, 30),
                         lin("Perfume Arabe Decant 5ml", "GENÉRICO", "G1", 9, 9),
                         lin("Perfume Finke Sabah Edp 100ml", "FINKÈ", "F1", 300, 900),
                         lin("Perfume Finke Oud Edp 100ml", "FINKÈ", "F2", 200, 500)), "AL WATANIAH", "2026-09-01", "2026-10-03")
    assert un_card(repo, "LATTAFA")[3] == {"L1": 850, "L2": 300, "L3": 50, "L4": 7}
    assert un_card(repo, "FINKE") == ("2026-09-01", "2026-10-03", 33, {"F1": 300, "F2": 200})     # marca nova com corpo: card
    assert set(ids_do(repo, "AL WATANIAH", "2026-09-01")) == {"W1", "W2", "W3", "T1", "G1"}       # lixo fica aqui, fora da conta
    assert nubi.destino_carona("AL WATANIAH", {"LATTAFA": "LATTAFA"}, "AL WATHANIAH", pd.DataFrame({"un": [5], "vendedor_id": ["x"]})) == (None, False)
    assert nubi.destino_carona("AL WATANIAH", {"LATTAFA": "LATTAFA", "ASDAAF": "ASDAAF"}, "ASDAAF LATTAFA", pd.DataFrame({"un": [5], "vendedor_id": ["x"]})) == ("LATTAFA", False)
    assert nubi.destino_carona("AL WATANIAH", {}, "MAKIAJ", pd.DataFrame({"un": [110], "vendedor_id": ["x"]})) == ("MAKIAJ", True)
    assert nubi.destino_carona("AL WATANIAH", {}, "NA", pd.DataFrame({"un": [110], "vendedor_id": ["x"]})) == (None, False)
    # o mesmo arquivo de novo não muda nada (histórico igual = diferença 0; o card guarda só o hash do último arquivo)
    antes = un_card(repo, "AL WATANIAH")
    imp("alw_velho.csv", csv(lin("Perfume Al Wataniah Sabah Al Ward Edp 100ml", "AL WATANIAH", "W1", 450, 5060),
                             lin("Perfume Al Wataniah Durrat Edp 85ml", "AL WATANIAH", "W3", 9, 9)), "AL WATANIAH", "2026-09-01", "2026-09-30")
    assert un_card(repo, "AL WATANIAH") == antes
    repo.fechar()


def test_rodada_repetida_nao_zera_o_dia():
    """02/10 (produção): a 2ª rodada do encaminhar não tinha nada novo para a Ard Al Zaafaran e gravou o dia 30/09 com 0 un.
    por cima do +61 da 1ª. Dia vazio só entra quando o dia ainda não existe (aí vale para a média de 30 dias)."""
    class R:
        pass
    r = R()
    dia = {"de": "2026-09-29", "ate": "2026-09-30", "novos": 0, "vendedores_novos": 0}
    cheio = pd.DataFrame([{"anuncio": "A", "vendedor": "V", "vendedor_id": "1", "produto": "P", "tipo": "", "_du": 61, "_dfat": 100.0}])
    vazio = cheio.assign(_du=0, _dfat=0.0)
    nubi.registrar_dia(r, "ARD AL ZAAFARAN", cheio, dict(dia, novos=10), "x.csv")
    nubi.registrar_dia(r, "ARD AL ZAAFARAN", vazio, dia, "x.csv")
    assert [d["un"] for d in r.dias] == [61], r.dias
    nubi.registrar_dia(r, "OUTRA", vazio, dia, "x.csv")
    assert [(d["marca"], d["un"]) for d in r.dias] == [("ARD AL ZAAFARAN", 61), ("OUTRA", 0)]


if __name__ == "__main__":
    test_expandido_nao_rouba_nem_soma()
    print("ok importar sem roubar nem somar")
    test_regra_14_card_vivo()
    print("ok regra 14")
    test_outras_marcas_vao_para_o_card_certo()
    print("ok outras marcas no card certo")
    test_encaminhar_card_importado_antes_da_regra()
    print("ok encaminhar card antigo")
    test_rodada_repetida_nao_zera_o_dia()
    print("ok rodada repetida não zera o dia")
