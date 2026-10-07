#!/usr/bin/env python3
"""Minute grid of one house's distribution loop with the pump's
commanded speed, its power draw and each zone's heat call, over a
window, from the journal DB as sema: the minute file the pump-speed
and cold-zone-call analyses read.

Each week of the window is one journal query (grid.pull). On the 10 s
grid a sample is valid while both temperature channels have reported
within STALE_S; the other channels are forward-filled without a limit
inside that validity (a steady value reports rarely). A minute whose
six samples are all valid becomes one entry: the minute means of flow,
pump power, pump volts, supply and return, the age of the oldest
temperature reading any of its samples used (STALE_S is generous, so
an analysis that needs fresher data filters on this), and each zone's
call fraction.

A zone's heat call is read from its thermostat white-wire power
channel (`zone<n>-<name>-whitewire-pwr`): the wire carries power while
the thermostat calls. The call fraction is the share of the minute's
samples with the wire above CALLING_W.

  uv run python pump_speed.py --house beech \
      --start 2025-10-01 --end 2026-05-01 > pull-beech-pump.log
"""

import argparse
import datetime
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

from grid import (  # noqa: E402
    GRID_S,
    STALE_S,
    chunk_edges,
    et_midnight_ms,
    natural,
    on_grid,
    pull,
)
from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.property_format import LeftRightDot, SpaceheatName, UTCMilliseconds  # noqa: E402
from houses import ta_alias  # noqa: E402
from records import MinuteColumns, MinuteFile  # noqa: E402

SUPPLY: SpaceheatName = "dist-swt"
RETURN: SpaceheatName = "dist-rwt"
FLOW: SpaceheatName = "dist-flow"
PUMP_PWR: SpaceheatName = "dist-pump-pwr"
PUMP_010V: SpaceheatName = "dist-010v"
WHITEWIRE_LIKE = "zone%-whitewire-pwr"  # SQL LIKE: every zone's white wire
WHITEWIRE_SUFFIX = "-whitewire-pwr"

PER_MINUTE = 60 // GRID_S
CALLING_W = 10.0  # white wire above this: the thermostat is calling


def by_minute(x: np.ndarray) -> np.ndarray:
    return x[: len(x) // PER_MINUTE * PER_MINUTE].reshape(-1, PER_MINUTE)


def minute_mean(x: np.ndarray) -> np.ndarray:
    return by_minute(x).mean(axis=1)


def rounded(x: np.ndarray, digits: int) -> list[float]:
    """Finite values only; a NaN here is a bug in the validity mask."""
    assert np.isfinite(x).all()
    return [round(float(v), digits) for v in x]


def rounded_or_none(x: np.ndarray, digits: int) -> list[float | None]:
    return [None if not np.isfinite(v) else round(float(v), digits) for v in x]


def minutes_of(ta: LeftRightDot, start_ms: UTCMilliseconds, end_ms: UTCMilliseconds,
               codec: SemaCodec) -> MinuteColumns | None:
    p = pull(ta, [SUPPLY, RETURN, FLOW, PUMP_PWR, PUMP_010V], [WHITEWIRE_LIKE],
             start_ms, end_ms, codec)
    missing = [n for n in (SUPPLY, RETURN, FLOW) if n not in p.rows or n not in p.words]
    if missing:
        print(f"  no readings or no channel word for {missing}; week skipped")
        return None
    value: dict[SpaceheatName, np.ndarray] = {}
    age: dict[SpaceheatName, np.ndarray] = {}
    for name in (SUPPLY, RETURN, FLOW):
        raw, age[name] = on_grid(p.rows[name], p.grid_ms)
        value[name] = natural(p.words[name], raw)
    for name in (PUMP_PWR, PUMP_010V):
        if name in p.rows:
            raw, _ = on_grid(p.rows[name], p.grid_ms)
            value[name] = natural(p.words[name], raw)
        else:
            print(f"  {name}: no readings this week")
            value[name] = np.full(len(p.grid_ms), np.nan)
    calling: dict[SpaceheatName, np.ndarray] = {}
    for name in sorted(n for n in p.rows if n.endswith(WHITEWIRE_SUFFIX)):
        raw, _ = on_grid(p.rows[name], p.grid_ms)
        calling[name] = (natural(p.words[name], raw) > CALLING_W).astype(np.float64)
    valid = (age[SUPPLY] <= STALE_S) & (age[RETURN] <= STALE_S) & np.isfinite(age[FLOW])
    ok = minute_mean(valid.astype(np.float64)) == 1.0
    starts = p.grid_ms[: len(p.grid_ms) // PER_MINUTE * PER_MINUTE : PER_MINUTE] // 1000
    return MinuteColumns(
        minute_start_s=[int(s) for s in starts[ok]],
        gpm=rounded(minute_mean(value[FLOW])[ok], 3),
        pump_w=rounded_or_none(minute_mean(value[PUMP_PWR])[ok], 1),
        pump_v=rounded_or_none(minute_mean(value[PUMP_010V])[ok], 2),
        supply_f=rounded(minute_mean(value[SUPPLY])[ok], 2),
        return_f=rounded(minute_mean(value[RETURN])[ok], 2),
        temp_age_s=rounded(by_minute(np.maximum(age[SUPPLY], age[RETURN])).max(axis=1)[ok], 0),
        calls={n: rounded_or_none(minute_mean(c)[ok], 3) for n, c in calling.items()},
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--house", required=True)
    p.add_argument("--start", required=True, help="first day, ET (YYYY-MM-DD)")
    p.add_argument("--end", required=True, help="day after the last, ET")
    args = p.parse_args()
    ta = ta_alias(args.house)
    start = datetime.date.fromisoformat(args.start)
    end = datetime.date.fromisoformat(args.end)
    codec = SemaCodec()
    weeks: list[MinuteColumns] = []
    edges = chunk_edges(start, end)
    for a, b in zip(edges, edges[1:]):
        print(f"{args.house} {a} -> {b}")
        try:
            week = minutes_of(ta, et_midnight_ms(a), et_midnight_ms(b), codec)
        except SystemExit as no_layout:  # pull_readings: no layout.lite yet
            print(f"  {no_layout}")
            continue
        if week is not None:
            weeks.append(week)
    merged = MinuteColumns.concat(weeks)
    path = MinuteFile(ta, start, end, merged).write(HERE)
    print(f"wrote {path.name} ({len(merged.minute_start_s)} minutes, wires {sorted(merged.calls)})")


if __name__ == "__main__":
    main()
