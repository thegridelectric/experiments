#!/usr/bin/env python3
"""One line per message between the spruce scada and its LTN in a
`capture_broker.py` JSONL file: ET wall clock, the leg (scada→ltn or
ltn→scada), the inner type, AckRequired and the MessageId's first eight
characters. Everything else on the broker is counted and summarized at
the end. Read-only over the capture.

    uv run python trace_summary.py captures/<file>.jsonl [--all]
"""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
SCADA_TO_LTN = ".to.ltn."
LTN_TO_SCADA = ".to.s."


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("capture")
    ap.add_argument("--all", action="store_true", help="also list the other traffic")
    args = ap.parse_args()
    other: Counter[str] = Counter()
    with open(args.capture) as f:
        for line in f:
            m = json.loads(line)
            key = m["RoutingKeys"][0] if m["RoutingKeys"] else ""
            t = datetime.fromtimestamp(m["CapturedUnixMs"] / 1000, tz=ET).strftime("%H:%M:%S.%f")[:-3]
            if SCADA_TO_LTN in key:
                leg = "scada→ltn"
            elif LTN_TO_SCADA in key:
                leg = "ltn→scada"
            else:
                other[f"{m['Exchange']} {key}"] += 1
                if args.all:
                    print(f"{t}  {m['Exchange']:12} {key}")
                continue
            try:
                body = json.loads(m["PayloadText"])
                header = body.get("Header", {})
                payload = body.get("Payload", {})
                type_name = header.get("MessageType") or payload.get("TypeName", "?")
                ack = "ack-req" if header.get("AckRequired") else "       "
                mid = (header.get("MessageId") or payload.get("MessageId") or "")[:8]
                extra = ""
                if type_name == "gridworks.ack":
                    extra = f"acks {payload.get('AckMessageID', '')[:8]}"
                elif "PeerName" in payload:
                    extra = f"peer={payload['PeerName']}"
            except (json.JSONDecodeError, AttributeError):
                type_name, ack, mid, extra = "(undecodable)", "", "", ""
            print(f"{t}  {leg:10} {type_name:45} {ack} {mid:8} {extra}")
    print("\n-- other traffic on the broker --", file=sys.stderr)
    for k, n in other.most_common():
        print(f"{n:6}  {k}", file=sys.stderr)


if __name__ == "__main__":
    main()
