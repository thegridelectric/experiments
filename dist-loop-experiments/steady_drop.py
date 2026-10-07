#!/usr/bin/env python3
"""Emitter temperature drop in steady circulation, by source temperature,
per distribution system: the table behind mix-or-not claim 2.

Reads every hourly file in this folder through houses.systems(). A
steady hour is one whose distribution loop circulated for at least
STEADY of the hour. Hours are binned by flow-weighted source
temperature; each row gives the count and the quartiles of the drop,
the median flow and the median heat delivered.

  uv run python steady_drop.py > steady-drop.txt
"""

import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from houses import System, hour_day, systems  # noqa: E402
from tables import Table  # noqa: E402

STEADY = 0.95  # FlowingFraction at or above this is steady circulation
BIN_F = 10
MIN_HOURS = 10  # bins with fewer steady hours are not printed


class SteadyBin(NamedTuple):
    """Steady hours of one system in one source-temperature bin."""

    source_lo_f: int
    hours: int
    drop_q25_f: float
    drop_median_f: float
    drop_q75_f: float
    median_gpm: float
    median_kwh: float


def steady_bins(system: System) -> tuple[int, list[SteadyBin], SteadyBin | None]:
    """(steady hours, the populated bins, the all-steady-hours row)."""
    steady = [h for h in system.hours if h.flowing_fraction >= STEADY]
    source = np.array([h.source_f for h in steady])
    drop = np.array([h.drop_f for h in steady])
    gpm = np.array([h.mean_gpm for h in steady])
    kwh = np.array([h.heat_kwh for h in steady])
    bins = []
    for lo in range(60, 200, BIN_F):
        pick = (source >= lo) & (source < lo + BIN_F)
        if pick.sum() < MIN_HOURS:
            continue
        q25, q50, q75 = np.percentile(drop[pick], [25, 50, 75])
        bins.append(SteadyBin(lo, int(pick.sum()), float(q25), float(q50), float(q75),
                              float(np.median(gpm[pick])), float(np.median(kwh[pick]))))
    total = None
    if len(steady):
        q25, q50, q75 = np.percentile(drop, [25, 50, 75])
        total = SteadyBin(0, len(steady), float(q25), float(q50), float(q75),
                          float(np.median(gpm)), float(np.median(kwh)))
    return len(steady), bins, total


def tables() -> list[Table]:
    rows = []
    for system in systems():
        _, bins, _ = steady_bins(system)
        for b in bins:
            rows.append((system.name, b.source_lo_f, b.source_lo_f + BIN_F, b.hours,
                         round(b.drop_q25_f, 1), round(b.drop_median_f, 1), round(b.drop_q75_f, 1),
                         round(b.median_gpm, 2), round(b.median_kwh, 2)))
    return [Table("steady-drop", "Steady-circulation hours by source temperature bin: drop quartiles, median flow, median heat",
                  ("System", "SourceLoF", "SourceHiF", "Hours", "DropQ25F", "DropMedianF", "DropQ75F",
                   "MedianGpm", "MedianKwhPerH"), rows, "steady_drop.py")]


def main() -> None:
    for system in systems():
        n_steady, bins, total = steady_bins(system)
        print(f"\n{system.name}: {len(system.hours)} valid hours, {n_steady} steady "
              f"({hour_day(system.hours[0])} to {hour_day(system.hours[-1])})")
        print("  source F   hours   drop F p25 / median / p75   gpm   kWh/h")
        for b in bins:
            print(f"  {b.source_lo_f:3d}-{b.source_lo_f + BIN_F:3d}   {b.hours:5d}   "
                  f"{b.drop_q25_f:6.1f} / {b.drop_median_f:5.1f} / {b.drop_q75_f:5.1f}        "
                  f"{b.median_gpm:4.1f}   {b.median_kwh:5.2f}")
        if total:
            print(f"  all        {total.hours:5d}   {total.drop_q25_f:6.1f} / {total.drop_median_f:5.1f} / {total.drop_q75_f:5.1f}")


if __name__ == "__main__":
    main()
