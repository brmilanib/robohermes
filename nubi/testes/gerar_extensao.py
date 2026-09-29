# -*- coding: utf-8 -*-
"""Gera public/extensao/nubi-ml.zip a partir da pasta public/extensao/nubi-ml (rodar depois de mexer na extensão)."""
import zipfile
from pathlib import Path

PASTA = Path(__file__).resolve().parents[1] / "public" / "extensao"


def gerar():
    zip_ = PASTA / "nubi-ml.zip"
    with zipfile.ZipFile(zip_, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted((PASTA / "nubi-ml").iterdir()):
            info = zipfile.ZipInfo(f"nubi-ml/{f.name}", date_time=(2026, 9, 29, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, f.read_bytes())
    return zip_


if __name__ == "__main__":
    print(gerar())
