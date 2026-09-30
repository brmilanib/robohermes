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


def test_categoria_nova_no_ranking_entra_na_coleta_e_pede_os_meses_desde_janeiro():
    # 30/09 (Bruno): "toda vez que eu importar uma categoria nova, coletar desde janeiro até o último mês fechado"
    from datetime import date
    import nubi_web as w
    cfg = dict(c.PADRAO_CONFIG)
    pend = {"ranking": {"MLB1246-MLB6284": ["2026-08"], "MLB1246-MLB1263": ["2026-08"], "lixo": []},
            "ranking_nomes": {"MLB1246-MLB1263": ["Beleza e Cuidado Pessoal", "Cuidados com a Pele"]}}
    cats = c.categorias_marcas(cfg, pend)
    assert ("MLB1246-MLB1263", ["Beleza e Cuidado Pessoal", "Cuidados com a Pele"]) in cats and "lixo" not in [k for k, _ in cats]
    assert [k for k, _ in cats][:2] == ["MLB1246-MLB6284", "MLB1246-MLB1248"]              # as do config continuam na frente

    assert w.meses_fechados(date(2026, 9, 30)) == [f"2026-0{m}" for m in range(1, 9)]
    chamadas = []

    class Repo:
        def _eq(self, v): return f"eq.{v}"
        def _todos(self, t, p): return [{"id": 9, "categoria": "MLB1246-MLB1263", "mes": "2026-08-01", "arquivo": "a", "importado_em": ""}]
        def _req(self, metodo, tabela, params=None, corpo=None, prefer=None):
            chamadas.append((metodo, tabela, corpo))
            return []
    r = Repo()
    faltam = w.meses_faltando_ranking(r, "MLB1246-MLB1263", date(2026, 9, 30))
    assert faltam == [f"2026-0{m}" for m in range(1, 8)], faltam
    assert w.pedir_coleta(r, "Ranking X: baixar " + ", ".join(faltam)) is True
    assert chamadas[-1][0] == "POST" and chamadas[-1][1] == "coletor_pedidos" and chamadas[-1][2][0]["tarefa"] == "diario"


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
