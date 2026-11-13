#!/usr/bin/env python3
"""Name the window scada's persisted events as sema instances in
`instances/`: `<HHMMSS ET>[-<subject>]-<type.name>-<version>.json` (a versionless
event, the startup event, takes 000), the
subject being the node a problem event is about (read off its Summary
"<node>") or the peer of a comm event. Input: the uid-named files `beech_window.sh off` copies from
the box's scada-experiment event dir into `instances/events-raw/`.

    python3 semafy_events.py
"""
import glob
import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "instances", "events-raw")

for path in sorted(glob.glob(os.path.join(RAW, "*.json"))):
    with open(path) as f:
        event = json.load(f)
    stamp = datetime.fromtimestamp(event["TimeCreatedMs"] / 1000, ET).strftime("%H%M%S")
    subject = ""
    if event["TypeName"] == "gridworks.event.problem":
        m = re.search(r"<([a-z0-9-]+)>", event["Summary"])
        subject = f"-{m.group(1)}" if m else ""
    elif "PeerName" in event:
        subject = f"-{event['PeerName']}"
    name = f"{stamp}{subject}-{event['TypeName']}-{event.get('Version', '000')}.json"
    target = os.path.join(HERE, "instances", name)
    if os.path.exists(target):
        raise SystemExit(f"collision: {name}")
    os.rename(path, target)
    print(name)
os.rmdir(RAW)
