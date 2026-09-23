# -*- coding: utf-8 -*-
"""Função da Vercel: recebe as chamadas da página e repassa para nubi_web.atender()."""

import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import nubi_web  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def _rodar(self, metodo):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        rota = q.pop("r", "")
        n = int(self.headers.get("Content-Length") or 0)
        corpo = self.rfile.read(n) if n else b""
        auth = self.headers.get("Authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        status, tipo, dados, extra = nubi_web.atender(metodo, rota, q, corpo, token)
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Cache-Control", "no-store")
        for k, v in extra.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self):
        self._rodar("GET")

    def do_POST(self):
        self._rodar("POST")
