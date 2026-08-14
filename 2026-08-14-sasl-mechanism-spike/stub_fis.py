"""Stub FIS for the SASL-mechanism spike: logs every /auth/* POST body
verbatim and answers "allow". Stdlib only — zero deps, runs in
python:3.12-slim. STUB_DELAY_S delays each response, for probing the
broker-side auth-callback timeout budget (design "Build-time artifacts")."""

import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qsl

DELAY_S = float(os.environ.get("STUB_DELAY_S", "0"))


class AuthHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8", "replace")
        params = dict(parse_qsl(body, keep_blank_values=True))
        print(f"POST {self.path} :: {params}", flush=True)
        if DELAY_S:
            time.sleep(DELAY_S)
        payload = b"allow"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: object) -> None:
        pass  # the do_POST print is the log


print(f"stub FIS listening on :8080 (delay={DELAY_S}s)", flush=True)
HTTPServer(("", 8080), AuthHandler).serve_forever()
