"""Reduce a tap capture to one compact row per message.

The full captures (`evidence/tap-capture-*.jsonl`) are the evidence and
stay untouched, but exceed the repo's 2 MB cap, so they go to the
immutable store and the folder commits this reduction: for every message
its receive time, routing key, the payload's TypeName and Version, and
its byte count. Rows are written beside the capture with the tail
`-rows.jsonl`.

    uv run python 2026-11-18-spruce-plant-seam-roll/reduce_capture.py
"""

import json
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).parent
EVIDENCE = HERE / "evidence"


class Row(NamedTuple):
    """One captured message, reduced. No sema word covers a capture index yet."""

    received_unix_ms: int
    routing_key: str
    type_name: str
    version: str
    payload_bytes: int


def reduce(capture: Path) -> Path:
    out = capture.with_name(capture.stem + "-rows.jsonl")
    with capture.open() as src, out.open("w") as dst:
        for line in src:
            rec = json.loads(line)
            text = rec.get("PayloadText", "")
            try:
                payload = json.loads(text)
                body = payload.get("Payload", payload)
                type_name, version = body.get("TypeName", ""), body.get("Version", "")
            except (json.JSONDecodeError, AttributeError):
                type_name, version = "", ""
            row = Row(rec["ReceivedUnixMs"], rec["RoutingKey"], type_name, version, len(text.encode()))
            dst.write(json.dumps(row._asdict()) + "\n")
    return out


def main() -> None:
    for capture in sorted(EVIDENCE.glob("tap-capture-*.jsonl")):
        if capture.stem.endswith("-rows"):
            continue
        print(reduce(capture))


if __name__ == "__main__":
    main()
