#!/usr/bin/env python3
"""What the LG's outdoor unit draws with the compressor off, at beech
and oak: standby levels, the 200 W state (level, share of idle time by
month, share by minutes since the stop, how often a stop is followed by
it, the cadence through a long idle, short episodes against relay 6
changes), and the oak 2026-10-20 window readings.

Episode figures read the committed idle-episodes and runs files; the
standby levels and the time-since-stop shares read the regen pull on a
60 s grid. --window-log reads a window scada's stdout for its
`hp-odu-pwr=<W>W@<age>s` lines.

  uv run python idle.py > idle.txt
  uv run python idle.py --window-log <stdout.log> [--window-log ...] >> idle.txt

Unfinished: never run; idle.txt does not exist yet. The first oak window log lives outside the repo.
"""

import argparse
import datetime
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from lg_common import HOUSES, ODU, R6, grid, load, quantiles  # noqa: E402
from lg_records import IdleEpisode, Run, read  # noqa: E402
from pull_readings import ET  # noqa: E402

STATE_W = (150.0, 260.0)
SINCE_BINS_MIN = [0, 40, 50, 60, 120, 180, 360, 720, 1e9]
COLD_F, WARM_F = 50.0, 65.0  # forecast bands the shares are split on
FOLLOW_MIN = (30, 70)  # an episode this many minutes after a stop follows it
LONG_IDLE_MIN = 240


def window_log(path: Path) -> None:
    pat = re.compile(r"^(\S+ \S+) .*hp-odu-pwr=(\d+)W@(\d+)s")
    last = None
    for line in path.read_text(errors="replace").splitlines():
        m = pat.match(line)
        if m and m.group(2) != last:
            print(f"  {path.name}: {m.group(1)} hp-odu-pwr {m.group(2)} W (age {m.group(3)} s)")
            last = m.group(2)


def main() -> None:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    p.add_argument("--window-log", type=Path, action="append", default=[])
    args = p.parse_args()
    if args.window_log:
        for wl in args.window_log:
            window_log(wl)
        return
    for h in HOUSES:
        runs = read(h, Run)
        eps = read(h, IdleEpisode)
        g = grid(h, 60)
        ends = np.array([(r.start_s + r.dur_s) * 1000 for r in runs], dtype=np.int64)
        starts = np.array([r.start_s * 1000 for r in runs], dtype=np.int64)
        idle = np.ones(len(g.t_ms), dtype=bool)
        for a_ms, b_ms in zip(starts, ends):
            a, b = np.searchsorted(g.t_ms, [a_ms, b_ms])
            idle[a:b] = False
        ok = idle & np.isfinite(g.odu)
        state = (g.odu >= STATE_W[0]) & (g.odu <= STATE_W[1])
        month = np.array([datetime.datetime.fromtimestamp(t / 1000, tz=ET).month for t in g.t_ms])
        print(f"== {h}")
        winter, summer = ok & np.isin(month, [11, 12, 1, 2, 3]), ok & np.isin(month, [6, 7, 8])
        print(f"  standby W Nov-Mar {quantiles(g.odu[winter & (g.odu < 60)])}; Jun-Aug {quantiles(g.odu[summer & (g.odu < 60)])}")
        print(f"  hp-idu-pwr idle W {quantiles(g.idu[ok])}")
        print(f"  state share of idle minutes Nov-Mar {state[winter].mean() * 100:.0f} %, Jun-Aug {state[summer].mean() * 100:.0f} %")
        print(f"  idle minutes 260-400 W: {((g.odu > 260) & (g.odu < 400))[ok].mean() * 100:.2f} %")
        k = np.searchsorted(ends, g.t_ms) - 1
        since = np.where(k >= 0, (g.t_ms - ends[np.clip(k, 0, None)]) / 60000.0, np.nan)
        for label, band in (("forecast <= 50 F", g.foat <= COLD_F), ("forecast > 65 F", g.foat > WARM_F)):
            row = []
            for lo, hi in zip(SINCE_BINS_MIN, SINCE_BINS_MIN[1:]):
                m = ok & band & (since > lo) & (since <= hi)
                row.append(f"{lo:.0f}-{hi:.0f}:{state[m].mean() * 100:.0f}%({m.sum()})" if m.any() else f"{lo:.0f}-{hi:.0f}:-")
            print(f"  state share by minutes since stop, {label}: {' '.join(row)}")
        e = np.array([x.first_s for x in eps], dtype=np.int64)
        dmin = np.array([(x.last_s - x.first_s) / 60 for x in eps])
        dmax = np.array([(x.next_out_s - x.prev_out_s) / 60 for x in eps])
        since_ep = np.array([x.since_stop_s / 60 for x in eps])
        print(f"  episodes {len(eps)}; level W {quantiles(np.array([x.level_w for x in eps]))}")
        print(f"  length min, lower bound {quantiles(dmin)}, upper bound {quantiles(dmax)}")
        follow = (since_ep >= FOLLOW_MIN[0]) & (since_ep < FOLLOW_MIN[1])
        print(f"  episodes {FOLLOW_MIN[0]}-{FOLLOW_MIN[1]} min after a stop: {follow.sum()}, delay {quantiles(since_ep[follow])}")
        gaps = [(r_end, nxt) for r_end, nxt in zip(ends[:-1], starts[1:]) if (nxt - r_end) > 130 * 60000]
        hit = [bool(((e * 1000 >= a + FOLLOW_MIN[0] * 60000) & (e * 1000 < a + FOLLOW_MIN[1] * 60000)).any()) for a, _ in gaps]
        print(f"  stops followed by >= 130 min idle: {len(gaps)}, with an episode {FOLLOW_MIN[0]}-{FOLLOW_MIN[1]} min after: {sum(hit)}")
        long_eps = [x for x in eps if x.since_stop_s / 60 > LONG_IDLE_MIN]
        iv = np.array([(b.first_s - a.first_s) / 60 for a, b in zip(long_eps, long_eps[1:]) if b.since_stop_s > a.since_stop_s])
        print(f"  long idle: {len(long_eps)} episodes, start to start min {quantiles(iv)}, 6-8 h intervals {int(((iv >= 360) & (iv < 480)).sum())}")
        r6 = load(h)[R6]
        ch = r6.t_ms[np.r_[False, np.diff(r6.value) != 0]]
        def near(t_s: int) -> bool:
            return bool(((ch >= (t_s - 600) * 1000) & (ch <= (t_s + 300) * 1000)).any())
        short = [x for x, hi in zip(eps, dmax) if hi <= 15]
        longe = [x for x, lo in zip(eps, dmin) if lo >= 45]
        print(f"  short episodes (upper bound <= 15 min) {len(short)}, near a relay 6 change {sum(near(x.first_s) for x in short)}; "
              f"hour-long {len(longe)}, near one {sum(near(x.first_s) for x in longe)}")
        o = load(h)[ODU]
        dt = np.diff(o.t_ms)
        gap = np.r_[False, (dt > 600_000) & (dt < 3_600_000)] & np.r_[False, o.value[:-1] < 60]
        after = o.value[gap]
        print(f"  journal gaps 10-60 min after standby: {gap.sum()}, first report in the state: {int(((after >= STATE_W[0]) & (after <= STATE_W[1])).sum())}")


if __name__ == "__main__":
    main()
