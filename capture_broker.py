#!/usr/bin/env python3
"""Capture every message published on the local dev broker, to a JSONL file.

Runs ON THE LAPTOP against `gw-dev-rabbit`. The capture rides RabbitMQ's
firehose: with tracing on for the vhost, the broker republishes every
message published to ANY exchange onto `amq.rabbitmq.trace`, routing key
`publish.<exchange>`, body untouched. One queue bound to `publish.#` sees
the scada's MQTT traffic (the MQTT plugin publishes to `amq.topic`, topic
slashes as dots) and every gwbase actor exchange alike, including
exchanges declared after the capture started.

    uv run python capture_broker.py <out-dir> [--seconds N]

Writes `<out-dir>/broker-capture-<YYYYMMDD-HHMMSS>.jsonl`, one
`CapturedMessage` per line, flushed per message, and a `.provenance.txt`
sidecar when it stops. Runs until SIGINT / SIGTERM or the `--seconds`
bound. Start it BEFORE the window opens: before it reports ready it
publishes a probe and requires the probe back through the firehose, so a
capture that prints `capturing` is proven connected and recording.

Tracing is a per-vhost broker switch, so one capture runs at a time (a
pidfile refuses a second); the capture turns tracing on at start and off
when it stops.

Env: `GWEXP_RABBIT__URL` in experiments/.env, the AMQP URL of the dev
broker. Nothing here quotes it.
"""

import argparse
import base64
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import NamedTuple
from urllib.parse import unquote, urlsplit

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties
from pydantic import TypeAdapter

from gwexp.sema.property_format import UTCMilliseconds

HERE = Path(__file__).parent.resolve()
BROKER_CONTAINER = "gw-dev-rabbit"
TRACE_EXCHANGE = "amq.rabbitmq.trace"
PROBE_EXCHANGE = "amq.topic"
PROBE_ROUTING_KEY = "gwexp.capture.probe"
PROBE_TIMEOUT_SECONDS = 5
PIDFILE = HERE / ".capture_broker.pid"

UTC_MS = TypeAdapter(UTCMilliseconds)


class CapturedMessage(NamedTuple):
    """One message as the broker's firehose reported it.

    No sema word covers a raw broker capture yet; a `gw.broker.capture`
    word retires this record.
    """

    captured_unix_ms: UTCMilliseconds  # laptop clock, when the capture received it
    exchange: str  # the exchange the message was published to ("" = default)
    routing_keys: list[str]  # as published; MQTT topics arrive dot-separated
    user: str  # the broker user that published it
    payload_text: str | None  # the body when it is valid UTF-8, untouched
    payload_b64: str | None  # the body base64-encoded when it is not

    def to_dict(self) -> dict[str, object]:
        return {
            "CapturedUnixMs": self.captured_unix_ms,
            "Exchange": self.exchange,
            "RoutingKeys": self.routing_keys,
            "User": self.user,
            "PayloadText": self.payload_text,
            "PayloadB64": self.payload_b64,
        }


def rabbit_url() -> str:
    for line in (HERE / ".env").read_text().splitlines():
        if line.startswith("GWEXP_RABBIT__URL="):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit("GWEXP_RABBIT__URL not found in experiments/.env")


def vhost_of(url: str) -> str:
    return unquote(urlsplit(url).path.lstrip("/"))


def set_tracing(vhost: str, on: bool) -> None:
    subprocess.run(
        ["docker", "exec", BROKER_CONTAINER, "rabbitmqctl", "trace_on" if on else "trace_off", "-p", vhost],
        check=True,
        capture_output=True,
    )


def from_trace(body: bytes, properties: BasicProperties) -> CapturedMessage:
    headers = properties.headers or {}
    keys = headers.get("routing_keys")
    try:
        text, b64 = body.decode("utf-8"), None
    except UnicodeDecodeError:
        text, b64 = None, base64.b64encode(body).decode("ascii")
    return CapturedMessage(
        captured_unix_ms=UTC_MS.validate_python(int(time.time() * 1000)),
        exchange=str(headers.get("exchange_name", "")),
        routing_keys=[str(k) for k in keys] if isinstance(keys, list) else [],
        user=str(headers.get("user", "")),
        payload_text=text,
        payload_b64=b64,
    )


def claim_pidfile() -> None:
    if PIDFILE.exists():
        pid = int(PIDFILE.read_text())
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise SystemExit(f"refusing: a capture is already running (pid {pid})")
    PIDFILE.write_text(str(os.getpid()))


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture every message published on the local dev broker.")
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--seconds", type=int, default=0, help="stop after N seconds (0 = until signalled)")
    args = parser.parse_args()

    url = rabbit_url()
    vhost = vhost_of(url)
    started = datetime.now().astimezone()
    out = args.out_dir / f"broker-capture-{started:%Y%m%d-%H%M%S}.jsonl"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    claim_pidfile()
    set_tracing(vhost, on=True)

    connection = pika.BlockingConnection(pika.URLParameters(url))
    channel = connection.channel()
    queue = channel.queue_declare("", exclusive=True, auto_delete=True).method.queue
    channel.queue_bind(queue, TRACE_EXCHANGE, routing_key="publish.#")

    count = 0
    probe_seen = False
    probe_body = f"probe {os.getpid()} {time.time()}".encode()

    def on_message(ch: BlockingChannel, method: Basic.Deliver, properties: BasicProperties, body: bytes) -> None:
        nonlocal count, probe_seen
        if body == probe_body:
            probe_seen = True
            return
        f.write(json.dumps(from_trace(body, properties).to_dict()) + "\n")
        f.flush()
        count += 1

    def stop(signum: int, frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        with out.open("x") as f:
            channel.basic_consume(queue, on_message, auto_ack=True)
            channel.basic_publish(PROBE_EXCHANGE, PROBE_ROUTING_KEY, probe_body)
            deadline = time.monotonic() + PROBE_TIMEOUT_SECONDS
            while not probe_seen and time.monotonic() < deadline:
                connection.process_data_events(time_limit=1)
            if not probe_seen:
                print("ABORT: the probe did not come back through the firehose; nothing is being captured", file=sys.stderr)
                return 1
            print(f"capturing vhost {vhost} -> {out}", flush=True)
            end = time.monotonic() + args.seconds if args.seconds else None
            try:
                while end is None or time.monotonic() < end:
                    connection.process_data_events(time_limit=1)
            except KeyboardInterrupt:
                pass
    finally:
        set_tracing(vhost, on=False)
        PIDFILE.unlink(missing_ok=True)
        if connection.is_open:
            connection.close()

    stopped = datetime.now().astimezone()
    out.with_suffix(".provenance.txt").write_text(
        f"Source: the laptop's {BROKER_CONTAINER}, vhost {vhost}: every message published to\n"
        f"  any exchange, as the broker's firehose ({TRACE_EXCHANGE}, publish.#)\n"
        f"  reported it, written by experiments/capture_broker.py.\n"
        f"Window: {started:%Y-%m-%d %H:%M:%S} to {stopped:%H:%M:%S %Z} (laptop clock); {count} messages.\n"
        f"Timestamps: CapturedUnixMs is the laptop clock at receipt; stamps inside a\n"
        f"  payload are the sender's clock.\n"
        f"Regeneration: not possible. A new capture is a new run.\n"
    )
    print(f"stopped: {count} messages in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
