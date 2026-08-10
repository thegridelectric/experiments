#!/usr/bin/env python3
"""Display CSV for channel-stats instances (gw.channel.jump.stats,
gw.channel.noise.stats): one row per instance, unit-bearing fields
converted to natural units via display.py.

Stats instances speak their channel's serialized units but do not carry
the encoding — that lives on the channel word. The word is resolved
from a *-gw.readings-000.json instance in the same folder as the stats
files; where none is present, values are emitted in wire units with the
encoding column reading "wire" and the channel's declaring word named.

Usage:
  uv run python stats_display.py <instance.json ...>
      writes <type.name>-display.csv beside the first input
"""

import csv
import datetime
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

import unit_encodings  # noqa: E402
from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.types import GwReadings  # noqa: E402
from gwexp.sema.property_format import (  # noqa: E402
    LeftRightDot,
    SpaceheatName,
    UTCMilliseconds,
)
from unit_encodings import Encoding, word_encoding  # noqa: E402

HERE = Path(__file__).parent



ET = ZoneInfo("America/New_York")

# The unit-bearing fields per stats type; everything else passes through.
UNIT_FIELDS: dict[LeftRightDot, list[str]] = {
    "gw.channel.jump.stats": ["JumpThreshold", "MaxAbsJump", "MedianAbsJump"],
    "gw.channel.noise.stats": ["Mean", "Sd", "P2p"],
}


def et(ms: UTCMilliseconds) -> str:
    return datetime.datetime.fromtimestamp(ms / 1000, tz=ET).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def folder_encodings(folder: Path, codec: SemaCodec) -> dict[SpaceheatName, Encoding]:
    """ChannelName -> wire encoding, from the folder's gw.readings
    instance(s) — the channel words travel there."""
    encodings: dict[SpaceheatName, Encoding] = {}
    candidates = [folder, folder.parent, folder.parent.parent]
    for path in [p for d in candidates for p in d.glob("*-gw.readings-000.json")]:
        pull = codec.from_dict(json.loads(path.read_text()), expect=GwReadings)
        for c in pull.channels:
            encodings[c.name] = word_encoding(c)
    return encodings


def main() -> None:
    paths = [Path(a) for a in sys.argv[1:]]
    if not paths:
        raise SystemExit(__doc__)
    codec = SemaCodec()
    instances = [codec.from_dict(json.loads(p.read_text())) for p in paths]
    type_names = {i.type_name for i in instances}
    if len(type_names) != 1:
        raise SystemExit(f"one stats type per CSV, got {sorted(type_names)}")
    type_name = type_names.pop()
    if type_name not in UNIT_FIELDS:
        raise SystemExit(f"unsupported type {type_name}")
    unit_fields = UNIT_FIELDS[type_name]

    encodings = folder_encodings(paths[0].parent, codec)

    rows = []
    for inst in instances:
        d = inst.to_dict()
        row = {}
        for k, v in d.items():
            if k in ("TypeName", "Version"):
                continue
            if k.endswith("UnixMs"):
                row[k.removesuffix("UnixMs") + "Et"] = et(v)
            elif k in unit_fields:
                encoding = encodings.get(d["ChannelName"])
                if encoding:
                    row[k], row["DisplayUnit"] = unit_encodings.to_display(v, encoding)
                else:
                    row[k], row["DisplayUnit"] = v, "wire"
            else:
                row[k] = v
        rows.append(row)

    out = paths[0].parent / f"{type_name}-display.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
