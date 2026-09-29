"""Ferrari (30/09, print do Bruno): "Ferrari Black" e "Ferrari Scuderia Black" eram o mesmo perfume em 2 produtos. A coluna
Marca traz "SCUDERIA FERRARI": a palavra antes da marca faz parte do nome da marca e não vira linha."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("OLLAMA_API_KEY", "x")
import pandas as pd  # noqa: E402
import nubi  # noqa: E402


def test_scuderia_nao_vira_linha():
    linhas = [("Ferrari Black Masculino Eau De Toilette Spray 125ml", "8002135111905", 120, "FERRARI"),
              ("Perfume Ferrari Black Edt 125ml Masculino", "", 30, "FERRARI"),
              ("Ferrari Black 125ml Masculino Scuderia", "8002135111906", 90, "SCUDERIA FERRARI"),
              ("Scuderia Ferrari Black Edt 125ml", "", 40, "SCUDERIA FERRARI"),
              ("Scuderia Ferrari Red Edt 125ml", "", 20, "SCUDERIA FERRARI"),
              ("Ferrari Red Edt 125ml", "", 10, "FERRARI")]
    df = pd.DataFrame([{"titulo": t, "gtin": g, "un": u, "fat": u * 200.0, "categoria": "", "marca_anuncio": m,
                        "vendedor": "v", "preco": 200.0} for t, g, u, m in linhas])
    assert nubi.prefixos_da_marca(df["marca_anuncio"], "FERRARI") == {"scuderia"}
    out = nubi.consolidar(df, "FERRARI", {}, info={})
    ls = list(out["linha"])
    assert not any("scuderia" in l.lower() for l in ls), ls
    assert ls[0] == ls[1] == ls[2] == ls[3], ls
    assert ls[4] == ls[5], ls
    assert len(set(out.loc[[0, 1, 2, 3], "produto"])) == 1, list(out["produto"])
    # um anúncio só com "SCUDERIA FERRARI" não basta (pode ser erro de um vendedor)
    assert nubi.prefixos_da_marca(["SCUDERIA FERRARI", "FERRARI"], "FERRARI") == set()


if __name__ == "__main__":
    test_scuderia_nao_vira_linha()
    print("ok test_scuderia_nao_vira_linha")
