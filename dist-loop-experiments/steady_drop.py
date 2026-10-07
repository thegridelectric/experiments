#!/usr/bin/env python3
"""Emitter temperature drop in steady circulation, by supply temperature,
per distribution system: the table behind mix-or-not claim 2.

Reads every hourly file in this folder through houses.systems(). A
steady hour is one whose distribution loop circulated for at least
STEADY of the hour. Hours are binned by flow-weighted supply
temperature; each row gives the count and the quartiles of the drop,
the median flow and the median heat delivered.

  uv run python steady_drop.py > steady-drop.txt
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from houses import hour_day, systems  # noqa: E402

STEADY = 0.95  # FlowingFraction at or above this is steady circulation
BIN_F = 10
MIN_HOURS = 10  # bins with fewer steady hours are not printed


def main() -> None:
    for system in systems():
        hours = system.hours
        steady = [h for h in hours if h.flowing_fraction >= STEADY]
        supply = np.array([h.supply_f for h in steady])
        drop = np.array([h.drop_f for h in steady])
        gpm = np.array([h.mean_gpm for h in steady])
        kwh = np.array([h.heat_kwh for h in steady])
        print(f"\n{system.name}: {len(hours)} valid hours, {len(steady)} steady "
              f"({hour_day(hours[0])} to {hour_day(hours[-1])})")
        print("  supply F   hours   drop F p25 / median / p75   gpm   kWh/h")
        for lo in range(60, 200, BIN_F):
            pick = (supply >= lo) & (supply < lo + BIN_F)
            if pick.sum() < MIN_HOURS:
                continue
            q25, q50, q75 = np.percentile(drop[pick], [25, 50, 75])
            print(f"  {lo:3d}-{lo + BIN_F:3d}   {pick.sum():5d}   "
                  f"{q25:6.1f} / {q50:5.1f} / {q75:5.1f}        "
                  f"{np.median(gpm[pick]):4.1f}   {np.median(kwh[pick]):5.2f}")
        if len(steady):
            q25, q50, q75 = np.percentile(drop, [25, 50, 75])
            print(f"  all        {len(steady):5d}   {q25:6.1f} / {q50:5.1f} / {q75:5.1f}")


if __name__ == "__main__":
    main()
