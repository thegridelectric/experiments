#!/usr/bin/env python3
"""The LG's defrost at beech and oak: the dips file's defrosts against
its stops (phase timing, power, lift, LWT, flow, forecast), defrosts per
running hour by forecast band, and candidate defrost lines scored on
steady running from the regen pull: the deployed sum under 8.4 kW
(`actors/hp_boss/sensing.py` DEFROST_SIGNATURES) and the alternatives in
LINES, each held for each of DWELLS_S. A fire inside a defrost window
is a catch; any other fire is counted by forecast band.

  uv run python defrost.py > defrost.txt

Unfinished: never run; defrost.txt does not exist yet. The traced defrost case is read by hand, not scripted.
"""

import argparse
import sys
from pathlib import Path
from typing import Callable

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from lg_common import HOUSES, OFF_W, R6_ON, Grid, grid, quantiles, segments  # noqa: E402
from lg_records import Dip, Run, read  # noqa: E402

STEADY_FROM_S = 15 * 60
DWELLS_S = (0, 120, 300)
MARGIN_S = 120  # a defrost or stop window is widened this much each side
NO_DEFROST_ABOVE_F = 45.0  # forecast above which a fire is counted as not a defrost
OAT_BANDS = [(-30, 10), (10, 20), (20, 30), (30, 40), (40, 50), (50, 100)]
LINES: dict[str, Callable[[Grid], np.ndarray]] = {
    "sum < 8400 W (deployed)": lambda g: g.total < 8400,
    "sum < 6000 W": lambda g: g.total < 6000,
    "idu < 1500 W & odu > 350 W": lambda g: (g.idu < 1500) & (g.odu > OFF_W),
}


def col(rs: list[Dip], f: str) -> np.ndarray:
    return np.array([getattr(r, f) for r in rs], dtype=float)


def main() -> None:
    argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0]).parse_args()
    for h in HOUSES:
        dips, runs = read(h, Dip), read(h, Run)
        d = [x for x in dips if x.kind == "defrost"]
        s = [x for x in dips if x.kind == "stop"]
        print(f"== {h}: {len(d)} defrosts, {len(s)} stops")
        for f in ("total_s", "fall_to_idu_off_s", "idu_off_s", "sum_under_8400_s", "odu_min_w", "odu_med_w",
                  "idu_max_before_w", "lift_pre_f", "lift_min_f", "flow_min_gpm", "foat_f"):
            print(f"  defrost {f:20s} {quantiles(col(d, f))}")
        print(f"  defrost lwt drop F      {quantiles(col(d, 'lwt_pre_f') - col(d, 'lwt_min_f'))}")
        print(f"  defrosts with lift under 0: {int((col(d, 'lift_min_f') < 0).sum())}; within 20 min: {int((col(d, 'total_s') <= 1200).sum())}")
        print(f"  stops: lwt at 180 F or more before {int((col(s, 'lwt_max_pre_f') >= 180).sum())}; "
              f"forecast > 40 F {int((col(s, 'foat_f') > 40).sum())}; total s {quantiles(col(s, 'total_s'))}")
        run_foat = np.array([r.foat_med_f for r in runs])
        run_h = np.array([r.dur_s / 3600 for r in runs])
        dfoat = col(d, "foat_f")
        print("  defrosts per running hour by forecast:",
              {f"{lo}..{hi}": (int(((dfoat > lo) & (dfoat <= hi)).sum()), round(float(run_h[(run_foat > lo) & (run_foat <= hi)].sum())))
               for lo, hi in OAT_BANDS})
        g = grid(h, 10)
        starts = np.array([r.start_s * 1000 for r in runs], dtype=np.int64)
        ends = np.array([(r.start_s + r.dur_s) * 1000 for r in runs], dtype=np.int64)
        k = np.searchsorted(starts, g.t_ms) - 1
        inrun = (k >= 0) & (g.t_ms < ends[np.clip(k, 0, None)])
        since = np.where(k >= 0, (g.t_ms - starts[np.clip(k, 0, None)]) / 1000.0, np.nan)
        steady = inrun & (since >= STEADY_FROM_S) & (g.r6 == R6_ON)
        which = np.full(len(g.t_ms), -1)
        masked = np.zeros(len(g.t_ms), dtype=bool)
        for i, x in enumerate(dips):
            a, b = np.searchsorted(g.t_ms, [(x.start_s - MARGIN_S) * 1000, (x.start_s + x.total_s + MARGIN_S) * 1000])
            masked[a:b] = True
            if x.kind == "defrost":
                which[a:b] = i
        under = steady & ~masked & (g.total < 8400)
        print(f"  steady hours {steady.sum() / 360:.0f}; outside dips with sum < 8400 W {under.sum() / 360:.0f} h "
              f"({under.sum() / max(1, (steady & ~masked).sum()) * 100:.1f} %)")
        for name, rule in LINES.items():
            fires = rule(g) & steady
            for dwell in DWELLS_S:
                caught: set[int] = set()
                warm = cold = none = 0
                for a, b in segments(fires):
                    if (b - a) * g.step_s < max(dwell, g.step_s):
                        continue
                    hit = which[a:b]
                    if (hit >= 0).any():
                        caught.update(hit[hit >= 0].tolist())
                    elif not masked[a:b].any():
                        fo = g.foat[a:b]
                        fo = fo[np.isfinite(fo)]
                        if len(fo) == 0:
                            none += 1
                        elif np.median(fo) > NO_DEFROST_ABOVE_F:
                            warm += 1
                        else:
                            cold += 1
                print(f"  {name:28s} held {dwell:3d} s: caught {len(caught)} of {len(d)}; other fires "
                      f"forecast > {NO_DEFROST_ABOVE_F:.0f} F {warm}, <= {cold}, no forecast {none}")


if __name__ == "__main__":
    main()
