#!/usr/bin/env python3
"""The broker capture of the two windows, reduced to what the sieg
question needs, so the folder stays under the repo's 2 MB file cap.

The full capture is 91 MB, almost all of it `snapshot.spaceheat`
messages every few seconds. Every line that is not a snapshot is kept
verbatim. Each snapshot is decoded through the vendored sema classes
and reduced to one row holding the sieg loop's readings and machine
states; a row is written only when one of those changed since the
previous row written, since a settled loop posts nothing new.

    uv run python reduce_capture.py <full capture>.jsonl

writes `<full capture>.reduced.jsonl` beside the script. The full
capture is in the immutable store; the README names its key.
"""

import json
import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.property_format import SpaceheatName, UTCMilliseconds  # noqa: E402
from gwexp.sema.types import SnapshotSpaceheat  # noqa: E402

HERE = Path(__file__).parent
CHANNELS: tuple[SpaceheatName, ...] = (  # the two meters r is made of, and the relays the protocol sets
    "sieg-flow", "sieg-send-flow",
    "hp-loop-keep-send-relay", "hp-loop-on-off-relay", "charge-discharge-relay", "store-pump-relay",
)
HANDLE_MARK = "sieg-loop"  # the sieg loop actor and its relays, in both command trees
SNAPSHOT_KEY_TAIL = ".snapshot-spaceheat"


class Reading(NamedTuple):
    """One channel's latest reading in a snapshot: the wire integer and when the scada read it."""

    value: int
    scada_read_time_unix_ms: UTCMilliseconds


class State(NamedTuple):
    """One machine's latest state in a snapshot and when it entered it."""

    state: str
    unix_ms: UTCMilliseconds


class SnapshotRow(NamedTuple):
    """A snapshot reduced to the sieg loop. No sema word holds a reduced
    snapshot; a word for a channel-filtered snapshot retires this."""

    captured_unix_ms: UTCMilliseconds
    snapshot_time_unix_ms: UTCMilliseconds
    readings: dict[SpaceheatName, Reading]
    states: dict[str, State]

    def to_jsonable(self) -> dict:
        return {
            "CapturedUnixMs": self.captured_unix_ms,
            "SnapshotTimeUnixMs": self.snapshot_time_unix_ms,
            "Readings": {k: [v.value, v.scada_read_time_unix_ms] for k, v in sorted(self.readings.items())},
            "States": {k: [v.state, v.unix_ms] for k, v in sorted(self.states.items())},
        }


def reduce_snapshot(captured_unix_ms: UTCMilliseconds, snap: SnapshotSpaceheat) -> SnapshotRow:
    return SnapshotRow(
        captured_unix_ms, snap.snapshot_time_unix_ms,
        {r.channel_name: Reading(r.value, r.scada_read_time_unix_ms)
         for r in snap.latest_reading_list if r.channel_name in CHANNELS},
        {s.machine_handle: State(s.state, s.unix_ms)
         for s in snap.latest_state_list if HANDLE_MARK in s.machine_handle},
    )


def main(full: Path) -> None:
    codec = SemaCodec()
    out = HERE / full.name.replace(".jsonl", ".reduced.jsonl")
    kept = snapshots = written = 0
    last: tuple | None = None
    with full.open() as src, out.open("w") as dst:
        for line in src:
            d = json.loads(line)
            if not d["RoutingKeys"][0].endswith(SNAPSHOT_KEY_TAIL):
                dst.write(line if line.endswith("\n") else line + "\n")
                kept += 1
                continue
            snapshots += 1
            snap = codec.from_dict(json.loads(d["PayloadText"])["Payload"], expect=SnapshotSpaceheat)
            row = reduce_snapshot(d["CapturedUnixMs"], snap)
            key = (row.readings, row.states)
            if key == last:
                continue
            last = key
            dst.write(json.dumps(row.to_jsonable(), separators=(",", ":")) + "\n")
            written += 1
    print(f"{full.name}: {kept} lines kept verbatim; {snapshots} snapshots -> {written} rows; "
          f"wrote {out.name} ({out.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(Path(sys.argv[1]))
