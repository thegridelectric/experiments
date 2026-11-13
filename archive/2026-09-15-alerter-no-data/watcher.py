"""A bus tap for the NoData witness: bind `#` on ear_tx, keep the alert
words, decode each through this repo's snapshot, print it, and write it
to instances/ as a sema instance.

Runs in the alerter's venv (gwbase, pika) with this repo's snapshot on
the path:

    PYTHONPATH=../src uv run --project ../../gridworks-alerter \
        python watcher.py instances
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pika
from gwbase.topology import EAR_EXCHANGE
from gwbase.transport_encoding import parse_routing_key
from gwexp.sema.codec import default_codec
from gwexp.sema.types import GwAlert
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

ALERT_TYPE = GwAlert.type_name_value()


def instance_path(out_dir: Path, word: GwAlert) -> Path:
    """`<subject>-<condition>-<type.name>-<version>.json`: subject is the
    house alias, condition the alert's state, so the firing and resolved
    words of one alert are two files."""
    return out_dir / (
        f"{word.about_g_node_alias}-{word.state.value.lower()}"
        f"-{word.type_name}-{word.version}.json"
    )


def main(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = pika.BlockingConnection(
        pika.URLParameters(os.environ["GWALERTER_RABBIT__URL"])
    )
    channel = conn.channel()
    queue = channel.queue_declare("", exclusive=True).method.queue
    channel.queue_bind(queue, EAR_EXCHANGE, routing_key="#")
    print(
        f"{time.strftime('%H:%M:%S')} watching {EAR_EXCHANGE} via {queue}", flush=True
    )

    def on_message(
        _channel: BlockingChannel,
        method: Basic.Deliver,
        _properties: BasicProperties,
        body: bytes,
    ) -> None:
        routing_key = str(method.routing_key)
        envelope = parse_routing_key(routing_key)
        if envelope.type_name != ALERT_TYPE:
            return
        word = default_codec.from_bytes(body)
        assert isinstance(word, GwAlert)
        print(
            f"{time.strftime('%H:%M:%S')} {routing_key}\n  "
            f"{word.type_name} {word.state.value} {word.kind.value} "
            f"about {word.about_g_node_alias} "
            f"id {word.alert_id}",
            flush=True,
        )
        instance_path(out_dir, word).write_bytes(word.to_bytes() + b"\n")

    channel.basic_consume(queue, on_message, auto_ack=True)
    try:
        channel.start_consuming()
    finally:
        conn.close()


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "instances"))
