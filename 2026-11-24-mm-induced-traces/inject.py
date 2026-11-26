#!/usr/bin/env python3
"""Address one message to the maker on the dev broker, as an LTN would.

Publishes a word's instance on the LTN mic exchange with the direct
routing key that the maker's queue is bound to, then prints the publish
instant. The body comes from the file given, byte for byte, so the
message is a real instance of its word and not one written here.

    uv run python inject.py <body.json> --type bid --from d1.isone.me.versant.keene.oak.ltn

Env: GWEXP_RABBIT__URL in experiments/.env, the AMQP URL of the dev broker.
"""

import argparse
import datetime
from pathlib import Path

import pika

HERE = Path(__file__).resolve().parent
ENV = HERE.parent / ".env"
MAKER = "d1.isone.me.versant.keene"
EXCHANGE = "ltnmic_tx"


def lrh(alias: str) -> str:
    return alias.replace(".", "-")


def broker_url() -> str:
    """GWEXP_RABBIT__URL from experiments/.env; nothing here quotes it."""
    for line in ENV.read_text().splitlines():
        if line.startswith("GWEXP_RABBIT__URL="):
            return line.split("=", 1)[1].strip().strip('"')
    raise SystemExit(f"GWEXP_RABBIT__URL not in {ENV}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("body", type=Path, help="the instance to send, a JSON file")
    p.add_argument("--type", required=True, help="the word's TypeName")
    p.add_argument("--from", dest="sender", required=True, help="the sender's alias")
    args = p.parse_args()
    url = broker_url()
    key = f"rj.{lrh(args.sender)}.ltn.{lrh(args.type)}.mm.{lrh(MAKER)}"
    body = args.body.read_bytes()
    conn = pika.BlockingConnection(pika.URLParameters(url))
    ch = conn.channel()
    ch.basic_publish(exchange=EXCHANGE, routing_key=key, body=body)
    sent = datetime.datetime.now(datetime.UTC).isoformat(timespec="milliseconds")
    conn.close()
    print(f"{sent} {EXCHANGE} {key} {len(body)} bytes")


if __name__ == "__main__":
    main()
