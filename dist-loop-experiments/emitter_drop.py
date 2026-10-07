#!/usr/bin/env python3
"""Hourly distribution supply, return and flow for one house over a
window, from the journal DB as sema: the hourly file every table in
this folder reads.

Each week of the window is one journal query (grid.pull). On the 10 s
grid a sample is valid while both temperature channels have reported
within STALE_S; flow is forward-filled without a limit inside that
validity, because a steady flow reports rarely. An hour with at least
MIN_VALID of its samples valid becomes one HourRecord: the share of
the hour the loop circulated (flow at or above FLOWING_GPM), the
flow-weighted supply and return over the circulating samples, the mean
flow, and the heat delivered (500 x gpm x drop BTU/h, water, summed
over the hour).

  uv run python emitter_drop.py --house beech \
      --start 2025-10-01 --end 2026-05-01 > pull-beech.log
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
from records import HourlyFile, HourRecord  # noqa: E402

SUPPLY: SpaceheatName = "dist-swt"
RETURN: SpaceheatName = "dist-rwt"
FLOW: SpaceheatName = "dist-flow"

MIN_VALID = 0.95  # share of an hour's grid samples that must be valid
FLOWING_GPM = 0.5  # at or above this the distribution loop is circulating
BTU_PER_HR_PER_GPM_F = 500.0  # water: 8.33 lb/gal * 60 min/h * 1 BTU/lb/F
BTU_PER_HR_PER_KW = 3412.14


def hours_of(ta: LeftRightDot, start_ms: UTCMilliseconds, end_ms: UTCMilliseconds,
             codec: SemaCodec) -> list[HourRecord]:
    p = pull(ta, [SUPPLY, RETURN, FLOW], [], start_ms, end_ms, codec)
    missing = [n for n in (SUPPLY, RETURN, FLOW) if n not in p.rows or n not in p.words]
    if missing:
        print(f"  no readings or no channel word for {missing}; week skipped")
        return []
    value: dict[SpaceheatName, np.ndarray] = {}
    age: dict[SpaceheatName, np.ndarray] = {}
    for name in (SUPPLY, RETURN, FLOW):
        raw, age[name] = on_grid(p.rows[name], p.grid_ms)
        value[name] = natural(p.words[name], raw)
    valid = (age[SUPPLY] <= STALE_S) & (age[RETURN] <= STALE_S) & np.isfinite(age[FLOW])
    per_hour = 3600 // GRID_S
    out: list[HourRecord] = []
    for i in range(0, len(p.grid_ms) - per_hour + 1, per_hour):
        ok = valid[i:i + per_hour]
        if ok.mean() < MIN_VALID:
            continue
        gpm = value[FLOW][i:i + per_hour][ok]
        swt = value[SUPPLY][i:i + per_hour][ok]
        rwt = value[RETURN][i:i + per_hour][ok]
        flowing = gpm >= FLOWING_GPM
        weight = gpm[flowing].sum()
        heat_btu = (BTU_PER_HR_PER_GPM_F * gpm * (swt - rwt)).sum() * GRID_S / 3600
        out.append(HourRecord(
            hour_start_s=int(p.grid_ms[i] // 1000),
            valid_fraction=float(ok.mean()),
            flowing_fraction=float(flowing.mean()),
            mean_gpm=float(gpm.mean()),
            supply_f=float((swt[flowing] * gpm[flowing]).sum() / weight) if weight else None,
            return_f=float((rwt[flowing] * gpm[flowing]).sum() / weight) if weight else None,
            heat_kwh=float(heat_btu / BTU_PER_HR_PER_KW),
        ))
    return out


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
    hours: list[HourRecord] = []
    edges = chunk_edges(start, end)
    for a, b in zip(edges, edges[1:]):
        print(f"{args.house} {a} -> {b}")
        try:
            hours += hours_of(ta, et_midnight_ms(a), et_midnight_ms(b), codec)
        except SystemExit as no_layout:  # pull_readings: no layout.lite yet
            print(f"  {no_layout}")
    path = HourlyFile(ta, start, end, hours).write(HERE)
    print(f"wrote {path.name} ({len(hours)} hours)")


if __name__ == "__main__":
    main()
