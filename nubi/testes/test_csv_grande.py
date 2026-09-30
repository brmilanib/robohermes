"""30/09 (Bruno, CSV de 4,7 MB da Oriente deu 413): a página manda o CSV grande compactado (X-Nubi-Gzip) e o servidor
volta ao original; a leitura e o hash não mudam."""
import gzip
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import nubi_web as w  # noqa: E402


def test_corpo_gzip_volta_ao_original():
    csv = ("Título;Vendedor;Marca;Vendas em $\n" + "\n".join(f"Perfume {i};V{i};ORIENTICA;{i}" for i in range(50000))).encode("utf-8")
    comp = gzip.compress(csv)
    assert len(comp) < len(csv) / 3
    assert w.corpo_recebido("1", comp) == csv and hashlib.sha256(w.corpo_recebido("1", comp)).hexdigest() == hashlib.sha256(csv).hexdigest()
    assert w.corpo_recebido(None, csv) == csv and w.corpo_recebido("", csv) == csv      # sem o cabeçalho: como veio
    assert w.corpo_recebido("1", b"nao e gzip") == b"nao e gzip"                          # cabeçalho errado não derruba


def test_pagina_compacta_acima_de_3mb():
    html = (Path(__file__).resolve().parents[1] / "public" / "index.html").read_text(encoding="utf-8")
    assert "async function corpoCsv" in html and 'CompressionStream("gzip")' in html and '"X-Nubi-Gzip": "1"' in html
    assert html.count("corpoCsv(it.f)") == 2                                             # analisar e importar
    assert "3 * 1024 * 1024" in html
    app = (Path(__file__).resolve().parents[1] / "api" / "app.py").read_text(encoding="utf-8")
    assert 'nubi_web.corpo_recebido(self.headers.get("X-Nubi-Gzip"), corpo)' in app



def test_csv_com_linhas_repetidas_le_ate_o_fim():
    """O arquivo da Oriente: 2 linhas com o mesmo ID; antes as colunas Gtin/Sku ficavam com o tamanho antigo e quebrava."""
    import nubi
    cab = ("Título;Vendedor;Categoria L1;Categoria final;Código Completo da Categoria;Código da Categoria L1;Código da Categoria Final;"
           "Categoria completa;Vendas em $ históricas;Vendas em $;Unidades vendidas históricas;Unidades vendidas;Último preço;"
           "Data de criação;Dias publicados;Exposição;Catálogo;FULL;FLEX;Compra Internacional;Marca;Modelo;Loja oficial;Frete grátis;"
           "ID do anúncio;ID do vendedor;Sku;Gtin;N° Peça;Oem")
    lin = lambda i, id_: (f"Perfume {i};V;Beleza e Cuidado Pessoal;Perfumes;;;;;1000;100;10;1;50;01/01/2026;10;Clássico;Não;Sim;Não;Não;"
                          f"ORIENTICA;;;Sim;{id_};V{i};;;;")
    csv = "\n".join([cab, lin(1, "A1"), lin(2, "A2"), lin(3, "A1")]).encode("utf-8")
    df, sug = nubi.ler_csv(csv)
    assert len(df) == 2 and sug == "ORIENTICA" and list(df["gtin"]) == ["", ""] and list(df["anuncio"]) == ["ID:A1", "ID:A2"]


def test_pagina_importa_marcas_em_levas():
    html = (Path(__file__).resolve().parents[1] / "public" / "index.html").read_text(encoding="utf-8")
    assert "const LEVA = 6" in html and "marcas: todas.slice(i, i + LEVA).join" in html
    assert "faltam ~" in html and 'class="up-barra"' in html and "<b>100%</b>" in html     # barra com % e previsão


if __name__ == "__main__":
    for nome, f in list(globals().items()):
        if nome.startswith("test_"):
            f()
            print("ok", nome)
