#!/usr/bin/env python3
"""Steady running of the LG at beech and oak from the committed runs
files: per-run medians of hp-odu-pwr, hp-idu-pwr, their sum, flow,
lift and LWT, as p10 / median / p90, by season, by month and by
forecast outdoor air, with the hydro kit's compressor lag at a start.
Only runs of RUN_MIN_S or more count as steady.

  uv run python running.py > running.txt

Unfinished: never run; running.txt does not exist yet.
"""

import argparse
import datetime
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from lg_common import HOUSES, quantiles  # noqa: E402
from lg_records import Run, read  # noqa: E402
from pull_readings import ET  # noqa: E402

RUN_MIN_S = 1800  # a run this long has a steady stretch worth a median
SEASONS = {"2025-26": (datetime.date(2025, 10, 1), datetime.date(2026, 6, 1)),
           "2026-27": (datetime.date(2026, 10, 1), datetime.date(2026, 10, 22))}
OAT_BANDS = [(-30, 10), (10, 20), (20, 30), (30, 40), (40, 50), (50, 100)]


def col(rs: list[Run], f: str) -> np.ndarray:
    return np.array([getattr(r, f) for r in rs], dtype=float)


def day(r: Run) -> datetime.date:
    return datetime.datetime.fromtimestamp(r.start_s, tz=ET).date()


def main() -> None:
    argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0]).parse_args()
    for h in HOUSES:
        runs = read(h, Run)
        print(f"== {h}: {len(runs)} runs")
        for name, (a, b) in SEASONS.items():
            season = [r for r in runs if a <= day(r) < b]
            x = [r for r in season if r.dur_s >= RUN_MIN_S]
            if not x:
                continue
            print(f"{name}: {len(x)} runs of 30 min or more of {len(season)}; "
                  f"{int(col(x, 'odu_reports_steady').sum())} hp-odu-pwr reports in the steady stretches")
            for f, label in (("odu_med_w", "hp-odu-pwr W"), ("idu_med_w", "hp-idu-pwr W"),
                             ("flow_med_gpm", "primary-flow gpm"), ("lift_med_f", "lift F"),
                             ("lwt_med_f", "hp-lwt F"), ("foat_med_f", "forecast F")):
                print(f"  {label:18s} {quantiles(col(x, f))}")
            print(f"  {'sum W':18s} {quantiles(col(x, 'odu_med_w') + col(x, 'idu_med_w'))}")
            print(f"  {'length min':18s} {quantiles(col(x, 'dur_s') / 60)}")
            print(f"  {'idu lag s':18s} {quantiles(col(x, 'idu_lag_s'))}")
        steady = [r for r in runs if r.dur_s >= RUN_MIN_S]
        months = sorted({day(r).strftime("%Y-%m") for r in steady})
        print("  by month, median hp-odu-pwr W:",
              {m: round(float(np.nanmedian(col([r for r in steady if day(r).strftime('%Y-%m') == m], 'odu_med_w')))) for m in months})
        foat = col(steady, "foat_med_f")
        for lo, hi in OAT_BANDS:
            sel = [r for r, f in zip(steady, foat) if lo < f <= hi]
            if sel:
                print(f"  forecast {lo}..{hi} F: {len(sel)} runs, odu {np.nanmedian(col(sel, 'odu_med_w')):.0f} W, "
                      f"idu {np.nanmedian(col(sel, 'idu_med_w')):.0f} W, lift {np.nanmedian(col(sel, 'lift_med_f')):.1f} F")
        print(f"  highest steady p90 hp-odu-pwr W: {np.nanmax(col(steady, 'odu_p90_w')):.0f}")


if __name__ == "__main__":
    main()
