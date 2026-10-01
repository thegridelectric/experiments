"""The receiver for the witness: an HTTP server on loopback that prints
each notification Alertmanager delivers (status, alertname, subject,
startsAt/endsAt) one alert per line, so the run's log shows what a
Telegram group would have been sent.

    python webhook_receiver.py 9094
"""

from __future__ import annotations

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802 -- http.server's name
        length = int(self.headers.get("Content-Length", "0"))
        notification = json.loads(self.rfile.read(length))
        stamp = time.strftime("%H:%M:%S")
        for alert in notification["alerts"]:
            labels = alert["labels"]
            print(
                f"{stamp} {alert['status']:8s} {labels.get('alertname')} "
                f"{labels.get('category')} {labels.get('subject')} "
                f"starts {alert['startsAt']} ends {alert['endsAt']} "
                f"| {alert['annotations'].get('summary')}",
                flush=True,
            )
        self.send_response(200)
        self.end_headers()

    def log_message(self, *_args: object) -> None:
        return


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9094
    print(f"{time.strftime('%H:%M:%S')} receiving on 127.0.0.1:{port}", flush=True)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
