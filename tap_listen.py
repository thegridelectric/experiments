#!/usr/bin/env python3
"""Listen to the live fleet stream on the analytics tap broker, read-only.

Runs ON THE LAPTOP against `hw1-tap.electricity.works`, the broker that
holds a one-way copy of prod's `ear_tx` (routing key and body verbatim).
It logs in as `gw.analyst`, which may read `ear_tx` and declare its own
queues and may publish nowhere, so nothing done here reaches the fleet
or prod. This is the go-to for watching real traffic during an
experiment; prod itself is never the place to listen.

    uv run python tap_listen.py                      # every message, one line each
    uv run python tap_listen.py -k '#.beech.#'       # a binding pattern (repeatable)
    uv run python tap_listen.py --out <dir> --seconds 600

One line per message on stdout (laptop arrival time, body size, routing
key). With `--out`, also `<dir>/tap-capture-<YYYYMMDD-HHMMSS>.jsonl`, one
`TapMessage` per line, flushed per message. The queue is exclusive and
dies with the connection; its name is `gw.analyst.<random>`, the only
names that login may declare. Runs until Ctrl-C or the `--seconds` bound.

Env: `GWEXP_TAP__URL` in experiments/.env. Nothing here quotes it.
"""

import argparse
import base64
import json
import signal
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties
from pydantic import TypeAdapter

from gwexp.sema.property_format import UTCMilliseconds

HERE = Path(__file__).parent.resolve()
EXCHANGE = "ear_tx"
QUEUE_PREFIX = "gw.analyst."  # the only queue names gw.analyst may declare

UTC_MS = TypeAdapter(UTCMilliseconds)


class TapMessage(NamedTuple):
    """One message as heard on the tap's `ear_tx`.

    No sema word covers a raw broker capture yet; a `gw.broker.capture`
    word retires this record.
    """

    received_unix_ms: UTCMilliseconds  # laptop clock, when the listener received it
    routing_key: str  # as published on prod, verbatim
    payload_text: str | None  # the body when it is valid UTF-8, untouched
    payload_b64: str | None  # the body base64-encoded when it is not

    def to_dict(self) -> dict[str, object]:
        return {
            "ReceivedUnixMs": self.received_unix_ms,
            "RoutingKey": self.routing_key,
            "PayloadText": self.payload_text,
            "PayloadB64": self.payload_b64,
        }


def tap_url() -> str:
    for line in (HERE / ".env").read_text().splitlines():
        if line.startswith("GWEXP_TAP__URL="):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit("GWEXP_TAP__URL not found in experiments/.env")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Listen to the fleet stream on the analytics tap broker."
    )
    parser.add_argument(
        "-k", "--key", action="append", help="binding pattern on ear_tx (default '#')"
    )
    parser.add_argument(
        "--out", type=Path, help="also write a JSONL capture into this directory"
    )
    parser.add_argument(
        "--seconds", type=int, default=0, help="stop after N seconds (0 = until Ctrl-C)"
    )
    args = parser.parse_args()

    connection = pika.BlockingConnection(pika.URLParameters(tap_url()))
    channel = connection.channel()
    queue = channel.queue_declare(
        queue=f"{QUEUE_PREFIX}{uuid.uuid4().hex[:8]}", exclusive=True
    ).method.queue
    for key in args.key or ["#"]:
        channel.queue_bind(queue=queue, exchange=EXCHANGE, routing_key=key)

    out_file = None
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        out_file = (
            args.out / f"tap-capture-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
        ).open("w")

    def on_message(
        ch: BlockingChannel, method: Basic.Deliver, _props: BasicProperties, body: bytes
    ) -> None:
        try:
            text, b64 = body.decode("utf-8"), None
        except UnicodeDecodeError:
            text, b64 = None, base64.b64encode(body).decode("ascii")
        msg = TapMessage(
            received_unix_ms=UTC_MS.validate_python(int(time.time() * 1000)),
            routing_key=method.routing_key or "",
            payload_text=text,
            payload_b64=b64,
        )
        print(
            f"{datetime.now():%H:%M:%S}  {len(body):>7}  {msg.routing_key}", flush=True
        )
        if out_file:
            out_file.write(json.dumps(msg.to_dict()) + "\n")
            out_file.flush()

    channel.basic_consume(queue=queue, on_message_callback=on_message, auto_ack=True)
    if args.seconds:
        connection.call_later(args.seconds, channel.stop_consuming)
    signal.signal(signal.SIGTERM, lambda *_: channel.stop_consuming())
    print(
        f"listening on the tap's {EXCHANGE} ({', '.join(args.key or ['#'])})",
        file=sys.stderr,
        flush=True,
    )
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        pass
    finally:
        if out_file:
            out_file.close()
        if connection.is_open:
            connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
