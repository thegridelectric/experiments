#!/usr/bin/env python3
"""Raw broker capture for the spruce window — runs ON THE LAPTOP.

Subscribes to everything on the local gw-dev-rabbit MQTT face
(localhost:1885) for the window and appends one JSONL line per message:
{"CaptureUnixMs": ..., "Topic": ..., "Payload": <parsed JSON, or
{"B64": ...} for non-JSON bytes>}. This is the raw record of what the
spruce window scada published through the ssh -R tunnel; the per-channel
series and noise stats are distilled from it afterwards, decoding each
payload by its TypeName.

Broker creds come from the sibling scada checkout's .env
(SCADA_GRIDWORKS_MQTT__USERNAME/PASSWORD — the laptop's dev-rabbit pair);
nothing is hardcoded. Run with the scada venv (paho + dotenv):

    ../../gridworks-scada/gw_spaceheat/venv/bin/python capture_window.py \
        window-capture-<DATE>.jsonl [seconds]

Refuses to overwrite an existing capture (frozen evidence, like
collect_pi_evidence.sh).
"""

import base64
import json
import sys
import time
from pathlib import Path

import paho.mqtt.client as mqtt
from dotenv import dotenv_values

HERE = Path(__file__).parent.resolve()
SCADA_ENV = HERE.parent.parent / "gridworks-scada" / ".env"
DEFAULT_SECONDS = 600


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: capture_window.py <out.jsonl> [seconds]", file=sys.stderr)
        return 2
    out = Path(argv[0])
    if out.exists():
        print(f"refusing to overwrite existing capture {out}", file=sys.stderr)
        return 2
    seconds = int(argv[1]) if len(argv) > 1 else DEFAULT_SECONDS

    env = dotenv_values(SCADA_ENV)
    user, password = env["SCADA_GRIDWORKS_MQTT__USERNAME"], env["SCADA_GRIDWORKS_MQTT__PASSWORD"]

    count = 0
    with out.open("x") as f:

        def on_message(_client, _userdata, msg) -> None:
            nonlocal count
            try:
                payload = json.loads(msg.payload)
            except (UnicodeDecodeError, json.JSONDecodeError):
                payload = {"B64": base64.b64encode(msg.payload).decode()}
            f.write(json.dumps({
                "CaptureUnixMs": int(time.time() * 1000),
                "Topic": msg.topic,
                "Payload": payload,
            }) + "\n")
            f.flush()
            count += 1

        client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        client.username_pw_set(user, password)
        client.on_message = on_message
        client.connect("localhost", 1885)
        client.subscribe("#")
        client.loop_start()
        print(f"capturing localhost:1885 '#' -> {out} for {seconds}s")
        deadline = time.time() + seconds
        try:
            while time.time() < deadline:
                time.sleep(1)
        except KeyboardInterrupt:
            print("stopped early by hand")
        client.loop_stop()
        client.disconnect()
    print(f"captured {count} messages -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
