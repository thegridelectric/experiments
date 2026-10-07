#!/usr/bin/env python3
"""The beech 2026-01-24 hand test of the distribution pump's 0-10 V
output, one row per step, from the journal DB as sema.

From 09:35 to 11:45 ET the downstairs zone called continuously and the
output was stepped by hand (STEPS, from the day's notes). Readings are
forward-filled onto the 10 s grid; a sample counts only when both
temperature sensors reported within FRESH_S, the downstairs zone was
calling (white wire above CALLING_W), and the upstairs wire had been
off for at least AFTER_UP_MIN, since an upstairs call pushes the cold
water of its loop past the return sensor for some minutes after it
ends (bolus_recovery.py measures how long). Each step is reported over
its counted samples.

One step is not reported: 6 V from 11:05 to 11:21. Every channel
stopped reporting from 11:06:30 to 11:21:10, so that step's grid is
forward-filled values, which the ten-minute STALE_S of the minute file
lets through as valid; the minute file carries TempAgeS for that.

  uv run python beech_jan24_steps.py > beech-2026-01-24-steps.txt
"""

import datetime
import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

from grid import GRID_S, natural, on_grid, pull  # noqa: E402
from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.property_format import SpaceheatName, UTCMilliseconds  # noqa: E402
from houses import ZONE_PAIRS, ta_alias  # noqa: E402
from pull_readings import ET  # noqa: E402
from tables import Table  # noqa: E402

HOUSE = "beech"
DAY = datetime.date(2026, 1, 24)
SOURCE: SpaceheatName = "dist-swt"
RETURN: SpaceheatName = "dist-rwt"
FLOW: SpaceheatName = "dist-flow"
PUMP_010V: SpaceheatName = "dist-010v"
FRESH_S = 90
CALLING_W = 10.0
AFTER_UP_MIN = 10  # minutes after the upstairs wire drops before a sample counts
BTU_PER_HR_PER_GPM_F = 500.0
STEPS = [  # (start, end) ET, each one hand-set level of the output
    ("09:35", "09:53"), ("10:03", "10:15"), ("10:23", "10:53"),
    ("10:55", "11:03"), ("11:22", "11:45"),
]


def ms(hhmm: str) -> UTCMilliseconds:
    h, m = map(int, hhmm.split(":"))
    return int(datetime.datetime(DAY.year, DAY.month, DAY.day, h, m, tzinfo=ET).timestamp() * 1000)


class StepRow(NamedTuple):
    """One hand-set level of the 0-10 V output over its counted samples."""

    start: str  # ET hh:mm
    end: str
    volts: float  # median commanded output over the step
    gpm: float  # median flow over counted samples
    held_min: int
    counted_share: float  # share of the step's samples that count
    source_mean_f: float
    source_min_f: float
    source_max_f: float
    return_mean_f: float
    return_min_f: float
    return_max_f: float
    drop_f: float  # mean of the per-sample drop
    heat_kbtu_per_h: float  # mean of 500 x gpm x drop per sample


def steps() -> list[StepRow]:
    zones = ZONE_PAIRS[HOUSE]
    names = [SOURCE, RETURN, FLOW, PUMP_010V, zones.steady, zones.idle]
    p = pull(ta_alias(HOUSE), names, [], ms("09:00"), ms("12:30"), SemaCodec())
    value: dict[SpaceheatName, np.ndarray] = {}
    age: dict[SpaceheatName, np.ndarray] = {}
    for name in names:
        raw, age[name] = on_grid(p.rows[name], p.grid_ms)
        value[name] = natural(p.words[name], raw)
    up_on = value[zones.idle] > CALLING_W
    since_up = np.full(len(p.grid_ms), np.inf)  # minutes since the upstairs wire was last on
    last_on = -np.inf
    for i, g in enumerate(p.grid_ms):
        if up_on[i]:
            last_on = g
        since_up[i] = (g - last_on) / 60000
    counted = (
        (age[SOURCE] <= FRESH_S) & (age[RETURN] <= FRESH_S)
        & (value[zones.steady] > CALLING_W) & (since_up >= AFTER_UP_MIN)
    )
    out = []
    for a, b in STEPS:
        in_step = (p.grid_ms >= ms(a)) & (p.grid_ms < ms(b))
        f = in_step & counted
        swt, rwt, gpm = value[SOURCE][f], value[RETURN][f], value[FLOW][f]
        drop = swt - rwt
        out.append(StepRow(
            a, b, float(np.median(value[PUMP_010V][in_step])), float(np.median(gpm)),
            int((ms(b) - ms(a)) // 60000), float(f.sum() / in_step.sum()),
            float(swt.mean()), float(swt.min()), float(swt.max()),
            float(rwt.mean()), float(rwt.min()), float(rwt.max()),
            float(drop.mean()), float(np.mean(BTU_PER_HR_PER_GPM_F * gpm * drop) / 1000)))
    return out


def tables() -> list[Table]:
    rows = [(r.start, r.end, round(r.volts, 1), round(r.gpm, 2), r.held_min, round(r.counted_share, 2),
             round(r.source_mean_f, 1), round(r.source_min_f, 1), round(r.source_max_f, 1),
             round(r.return_mean_f, 1), round(r.return_min_f, 1), round(r.return_max_f, 1),
             round(r.drop_f, 1), round(r.heat_kbtu_per_h, 1)) for r in steps()]
    return [Table("beech-2026-01-24-steps",
                  f"Beech {DAY}: each hand-set level of the pump's 0-10 V output over its counted samples (downstairs calling alone, both temperatures fresh within {FRESH_S} s)",
                  ("StartEt", "EndEt", "Volts", "Gpm", "HeldMin", "CountedShare", "SourceMeanF", "SourceMinF", "SourceMaxF",
                   "ReturnMeanF", "ReturnMinF", "ReturnMaxF", "DropF", "HeatKbtuPerH"), rows, "beech_jan24_steps.py")]


def main() -> None:
    print(f"{HOUSE} {DAY}: 0-10 V steps, downstairs zone calling alone, upstairs "
          f"off for {AFTER_UP_MIN} min, both temperatures fresh within {FRESH_S} s, "
          f"{GRID_S} s grid")
    print("step         V    gpm  min  counted  swt mean (min-max)    rwt mean (min-max)   drop  kBTU/h")
    for r in steps():
        print(f"{r.start}-{r.end}  {r.volts:4.1f} {r.gpm:5.2f}  {r.held_min:3d}  {100 * r.counted_share:4.0f}%  "
              f"{r.source_mean_f:6.1f} ({r.source_min_f:5.1f}-{r.source_max_f:5.1f})  "
              f"{r.return_mean_f:6.1f} ({r.return_min_f:5.1f}-{r.return_max_f:5.1f})  "
              f"{r.drop_f:5.1f}  {r.heat_kbtu_per_h:5.1f}")
    print("not reported: 6 V 11:05-11:21, no readings on any channel 11:06:30-11:21:10")


if __name__ == "__main__":
    main()
