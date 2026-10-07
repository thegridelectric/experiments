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

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

from grid import GRID_S, natural, on_grid, pull  # noqa: E402
from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.property_format import SpaceheatName, UTCMilliseconds  # noqa: E402
from houses import ZONE_PAIRS, ta_alias  # noqa: E402
from pull_readings import ET  # noqa: E402

HOUSE = "beech"
DAY = datetime.date(2026, 1, 24)
SUPPLY: SpaceheatName = "dist-swt"
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


def main() -> None:
    zones = ZONE_PAIRS[HOUSE]
    names = [SUPPLY, RETURN, FLOW, PUMP_010V, zones.steady, zones.idle]
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
        (age[SUPPLY] <= FRESH_S) & (age[RETURN] <= FRESH_S)
        & (value[zones.steady] > CALLING_W) & (since_up >= AFTER_UP_MIN)
    )
    print(f"{HOUSE} {DAY}: 0-10 V steps, downstairs zone calling alone, upstairs "
          f"off for {AFTER_UP_MIN} min, both temperatures fresh within {FRESH_S} s, "
          f"{GRID_S} s grid")
    print("step         V    gpm  min  counted  swt mean (min-max)    rwt mean (min-max)   drop  kBTU/h")
    for a, b in STEPS:
        in_step = (p.grid_ms >= ms(a)) & (p.grid_ms < ms(b))
        f = in_step & counted
        swt, rwt, gpm = value[SUPPLY][f], value[RETURN][f], value[FLOW][f]
        drop = swt - rwt
        print(f"{a}-{b}  {np.median(value[PUMP_010V][in_step]):4.1f} {np.median(gpm):5.2f}  "
              f"{(ms(b) - ms(a)) // 60000:3d}  {100 * f.sum() / in_step.sum():4.0f}%  "
              f"{swt.mean():6.1f} ({swt.min():5.1f}-{swt.max():5.1f})  "
              f"{rwt.mean():6.1f} ({rwt.min():5.1f}-{rwt.max():5.1f})  "
              f"{drop.mean():5.1f}  {np.mean(BTU_PER_HR_PER_GPM_F * gpm * drop) / 1000:5.1f}")
    print("not reported: 6 V 11:05-11:21, no readings on any channel 11:06:30-11:21:10")


if __name__ == "__main__":
    main()
