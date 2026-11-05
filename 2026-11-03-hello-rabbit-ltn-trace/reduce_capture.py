#!/usr/bin/env python3
"""Reduce a `capture_broker.py` JSONL to the scada–LTN link trace: one
compact row per message on the two legs (scada→ltn, ltn→scada), bodies
kept only for the link's control words (acks, pings, the comm and
lifecycle events, send.layout) and dropped for the reports, snapshots,
glitches and layouts whose size is the reason the raw capture cannot be
committed. The raw capture stays beside it, gitignored, as the evidence.

    uv run python reduce_capture.py captures/<file>.jsonl > link-trace.jsonl
"""

import argparse
import json

KEEP_BODY_PREFIXES = ("gridworks.", "send.layout")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("capture")
    args = ap.parse_args()
    with open(args.capture) as f:
        for line in f:
            m = json.loads(line)
            key = m["RoutingKeys"][0] if m["RoutingKeys"] else ""
            if ".to.ltn." in key:
                leg = "scada→ltn"
            elif ".to.s." in key:
                leg = "ltn→scada"
            else:
                continue
            try:
                body = json.loads(m["PayloadText"])
                header = body.get("Header", {})
                payload = body.get("Payload", {})
            except (json.JSONDecodeError, AttributeError):
                header, payload = {}, {}
            type_name = header.get("MessageType") or payload.get("TypeName", "")
            row = {
                "CapturedUnixMs": m["CapturedUnixMs"],
                "Leg": leg,
                "RoutingKey": key,
                "TypeName": type_name,
                "AckRequired": bool(header.get("AckRequired")),
                "MessageId": header.get("MessageId") or payload.get("MessageId", ""),
            }
            if type_name.startswith(KEEP_BODY_PREFIXES):
                row["Payload"] = payload
            print(json.dumps(row))


if __name__ == "__main__":
    main()
