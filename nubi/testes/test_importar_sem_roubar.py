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
    alw_set = s[(s["marca"] == "AL WATANIAH") & (s["inicio"].astype(str).str[:10] == "2026-09-01")]
    ids_armaf = set(repo.anuncios(int(armaf["id"].iloc[0]))["bruto"].map(lambda b: b.get("ID do anúncio")))
    ids_alw = set(repo.anuncios(int(alw_set["id"].iloc[0]))["bruto"].map(lambda b: b.get("ID do anúncio")))
    assert ids_armaf == {"A1"}, ids_armaf                 # a Armaf continua com o dela e perde só o perdido (W2)
    assert ids_alw == {"W1", "W2"}, ids_alw               # A1 não entra na Al Wataniah: não conta duas vezes
    assert un_por_snapshot(repo, id_alw59) == antes_59     # o período antigo não mudou
    assert len(s[s["marca"] == "AL WATANIAH"]) == 2        # 59 dias e setembro, lado a lado
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
    alw = ids_do(repo, "AL WATANIAH", "2026-09-01")
    assert set(alw) == {"W1", "H1"} and alw["H1"] == nubi.TIPO_OUTRA, alw  # H1 espera aqui (Al Haramain sem card de setembro)
    # a página da marca conta SÓ a marca (450 un. do W1) e lista a Al Haramain em "Outras marcas"
    r = nubi_web.relatorio(repo, "AL WATANIAH")
    z = r["resumo"]
    assert z["un"] == 450 and z["anuncios"] == 1 and z["vendedores"] == 1 and z["fat"] == 45000, z
    assert z["un_outras_marcas"] == 120 and z["anuncios_outras_marcas"] == 1 and z["fat_outras_marcas"] == 12000
    o = r["tabelas"]["outras"]
    assert len(o) == 1 and o[0]["marca"] == "AL HARAMAIN" and o[0]["un"] == 120 and o[0]["situacao"] == nubi_web.SIT_OUTRA_ESPERA, o
    assert [v["vendedor"] for v in r["tabelas"]["vendedores"]] == ["VEND.W1"]
    assert all(p["produto"].startswith("Al Wataniah") for p in r["tabelas"]["produtos"]), r["tabelas"]["produtos"]
    # chega o export de setembro da AL HARAMAIN (busca exata, SEM o H1): o H1 que esperava passa para o card dela
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
    nubi._juntar_por_id = lambda repo_, cfg_, marca, ini, fim, df, recem=(): nubi._ids(df)      # como a importação era antes
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


if __name__ == "__main__":
    test_expandido_nao_rouba_nem_soma()
    print("ok importar sem roubar nem somar")
    test_outras_marcas_vao_para_o_card_certo()
    print("ok outras marcas no card certo")
    test_encaminhar_card_importado_antes_da_regra()
    print("ok encaminhar card antigo")
