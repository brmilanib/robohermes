"""30/09 (Bruno: "vou começar em Maquiagem"): o relatório MARCAS mensal entra em cada categoria configurada (Perfumes +
Maquiagem), e a rotina só baixa o mês que falta em cada uma."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "public" / "coletor"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["NUBI_COLETOR_DIR"] = "/tmp/nubi-coletor-teste-maquiagem"
import coletor as c  # noqa: E402
import ranking  # noqa: E402


def test_categorias_do_relatorio_marcas():
    cfg = dict(c.PADRAO_CONFIG)
    cats = c.categorias_marcas(cfg)
    assert cats[0] == ("MLB1246-MLB6284", ["Beleza e Cuidado Pessoal", "Perfumes"])
    assert cats[1] == ("MLB1246-MLB1248", ["Beleza e Cuidado Pessoal", "Maquiagem"])
    assert ranking.nome_categoria("MLB1246-MLB1248") == "Beleza e Cuidado Pessoal > Maquiagem"
    cfg["categorias_extra"] = [{"categoria": "MLB1246-MLB6284", "nomes": ["x"]}, {"categoria": "MLB1246-MLB1263"}]
    assert [k for k, _ in c.categorias_marcas(cfg)] == ["MLB1246-MLB6284", "MLB1246-MLB1263"]   # sem repetir a principal


def test_rotina_pede_so_o_mes_que_falta_em_cada_categoria():
    cfg = dict(c.PADRAO_CONFIG)
    pend = {"ranking": {"MLB1246-MLB6284": ["2026-08"], "MLB1246-MLB1248": []}}
    pers = [{"mes": "2026-08", "ate": None}, {"mes": "2026-09", "ate": "2026-09-28"}]
    faltam = [(cat_, per["mes"]) for cat_, _ in c.categorias_marcas(cfg) for per in pers
              if not per["ate"] and per["mes"] not in set(pend["ranking"].get(cat_, []))]
    assert faltam == [("MLB1246-MLB1248", "2026-08")]                        # Perfumes já tem agosto; Maquiagem não


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
