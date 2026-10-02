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


if __name__ == "__main__":
    test_expandido_nao_rouba_nem_soma()
    print("ok importar sem roubar nem somar")
