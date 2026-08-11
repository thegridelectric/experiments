#!/usr/bin/env python3
"""Band-classified power timelines for the Samsung, from this folder's
instances (no DB access).

Question: is the ODU's behavior after 16:00 on 08-10 (post-visit,
FSV 2091 back under external authority) any different from the healthy
internal-schedule days before (2091=0)? Prints hp-odu-pwr and
hp-ctrl-box-pwr as run-length band segments per day, from the
`hp.baseline` pull (08-03 -> 08-10 13:00) and the `hp.norun` pull
(08-10 15:00 -> 22:30).

Bands (W), calibrated on the 07-30 postmortem + the 07-16 witnessed
test: ODU low < 25 (the distinct low-power state, ~12-17 W), standby
25-400 (~60 W normal), active > 400 (compressor, 1.7-1.8 kW steady);
ctrl-box idle < 10 (~4-6 W), active >= 10 (pump-scale draw).

  uv run python hp_power_analysis.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal, NamedTuple
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.property_format import (  # noqa: E402
    SpaceheatName,
    UTCMilliseconds,
)
from gwexp.sema.types import GwReadings  # noqa: E402

ET = ZoneInfo("America/New_York")

Band = Literal["low", "standby", "ACTIVE", "idle", "active"]


class Segment(NamedTuple):
    """One run of consecutive readings in the same band: [start, end]
    in scada read-time ms, with the min/max W seen inside the run."""

    start_ms: UTCMilliseconds
    end_ms: UTCMilliseconds
    band: Band
    lo_w: int
    hi_w: int


def odu_band(w: int) -> Band:
    if w < 25:
        return "low"
    if w <= 400:
        return "standby"
    return "ACTIVE"


def ctrl_band(w: int) -> Band:
    return "idle" if w < 10 else "active"


def load(condition: str) -> GwReadings:
    path = next(HERE.glob(f"*-{condition}-gw.readings-000.json"))
    return SemaCodec().from_dict(json.loads(path.read_text()),
                                 expect=GwReadings)


def channel_series(
    pull: GwReadings, name: SpaceheatName
) -> list[tuple[UTCMilliseconds, int]]:
    for cr in pull.channel_readings_list:
        if cr.channel_name == name:
            return sorted(zip(cr.scada_read_time_unix_ms_list,
                              cr.value_list))
    raise SystemExit(f"channel {name!r} not in pull")


def segments(series: list[tuple[UTCMilliseconds, int]],
             classify) -> list[Segment]:
    out: list[Segment] = []
    for t, w in series:
        band = classify(w)
        if out and out[-1].band == band:
            prev = out[-1]
            out[-1] = Segment(prev.start_ms, t, band,
                              min(prev.lo_w, w), max(prev.hi_w, w))
        else:
            out.append(Segment(t, t, band, w, w))
    return out


BUCKET_MS = 30 * 60 * 1000


class Bucket(NamedTuple):
    """One 30-min bucket: the dominant band by sample count and the
    max W seen (so a single compressor spike is never hidden)."""

    start_ms: UTCMilliseconds
    band: Band
    hi_w: int


def buckets(series: list[tuple[UTCMilliseconds, int]],
            classify) -> list[Bucket]:
    out: list[Bucket] = []
    by_bucket: dict[int, list[int]] = {}
    for t, w in series:
        by_bucket.setdefault(t // BUCKET_MS, []).append(w)
    for b in sorted(by_bucket):
        ws = by_bucket[b]
        counts: dict[Band, int] = {}
        for w in ws:
            band = classify(w)
            counts[band] = counts.get(band, 0) + 1
        dominant = max(counts, key=lambda k: counts[k])
        out.append(Bucket(b * BUCKET_MS, dominant, max(ws)))
    return out


def show(title: str, series: list[tuple[UTCMilliseconds, int]],
         classify) -> None:
    """Merged dominant-band timeline (30-min buckets) + daily totals."""
    print(f"\n== {title} ==")
    bks = buckets(series, classify)
    merged: list[tuple[UTCMilliseconds, UTCMilliseconds, Band, int]] = []
    for b in bks:
        if merged and merged[-1][2] == b.band \
                and b.start_ms - merged[-1][1] <= BUCKET_MS:
            s, _, band, hi = merged[-1]
            merged[-1] = (s, b.start_ms, band, max(hi, b.hi_w))
        else:
            merged.append((b.start_ms, b.start_ms, b.band, b.hi_w))
    day = ""
    for s_ms, e_ms, band, hi in merged:
        start = datetime.fromtimestamp(s_ms / 1000, tz=ET)
        end = datetime.fromtimestamp((e_ms + BUCKET_MS) / 1000, tz=ET)
        if start.strftime("%a %m-%d") != day:
            day = start.strftime("%a %m-%d")
            print(f"  -- {day} --")
        print(f"  {start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
              f"  {band:7}  (max seen {hi} W)")


def main() -> int:
    for condition in ("hp.baseline", "hp.norun"):
        pull = load(condition)
        show(f"hp-odu-pwr · {condition}",
             channel_series(pull, "hp-odu-pwr"), odu_band)
        show(f"hp-ctrl-box-pwr · {condition}",
             channel_series(pull, "hp-ctrl-box-pwr"), ctrl_band)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
