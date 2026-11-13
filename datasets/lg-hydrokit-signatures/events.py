#!/usr/bin/env python3
"""From one house's regen pull to its three committed files: compressor
runs, idle episodes of the 200 W state, and mid-run indoor-compressor
dips (record definitions in lg_records.py).

Runs come from a hysteresis on the 10 s grid's hp-odu-pwr (lg_common
ON_W / OFF_W and their holds). Idle episodes come from the raw
hp-odu-pwr reports, since the step between the two idle levels is under
the channel's 300 W report change and shows only at its 300 s capture.
Dips come from the 10 s grid.

  uv run python events.py --house beech
  uv run python events.py --house oak

Unfinished: never run; its committed record files do not exist yet.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from lg_common import (  # noqa: E402
    IDU, ODU, OFF_HOLD_S, OFF_W, ON_HOLD_S, ON_W, R6, R6_ON, FOAT, Channel, Grid, grid, load, segments,
)
from lg_records import Dip, IdleEpisode, Run, write  # noqa: E402

STEADY_FROM_S = 15 * 60  # steady running starts this long after a run's start
STEADY_TO_S = 60  # and stops this long before its end
STATE_W = (150.0, 260.0)  # the 200 W idle state on a raw report
STANDBY_W = 60.0  # a raw report under this is standby
DIP_IDU_W, DIP_PRE_ODU_W, DIP_BACK_W = 800.0, 5000.0, 9000.0


def compressor_on(odu: np.ndarray, step_s: int) -> np.ndarray:
    """The run state at each grid sample; a stale sample keeps the state."""
    on = np.zeros(len(odu), dtype=bool)
    state, hi, lo = False, 0, 0
    need_hi, need_lo = ON_HOLD_S // step_s, OFF_HOLD_S // step_s
    for i, v in enumerate(odu):
        if v == v:
            if not state:
                hi = hi + 1 if v > ON_W else 0
                if hi >= need_hi:
                    state, lo = True, 0
            else:
                lo = lo + 1 if v < OFF_W else 0
                if lo >= need_lo:
                    state, hi = False, 0
        on[i] = state
    return on


def med(x: np.ndarray) -> float:
    v = x[np.isfinite(x)]
    return float(np.median(v)) if len(v) else float("nan")


def q(x: np.ndarray, p: float) -> float:
    v = x[np.isfinite(x)]
    return float(np.quantile(v, p)) if len(v) else float("nan")


def runs_of(g: Grid, on: np.ndarray, odu_raw: Channel, idu_raw: Channel) -> list[Run]:
    out: list[Run] = []
    a_steady, b_steady = STEADY_FROM_S // g.step_s, STEADY_TO_S // g.step_s
    for s, e in segments(on):
        t0 = int(g.t_ms[s]) // 1000
        t1 = int(g.t_ms[min(e, len(g.t_ms) - 1)]) // 1000
        sl = slice(s + a_steady, max(s + a_steady, e - b_steady))
        n_rep = int(((odu_raw.t_ms >= (t0 + STEADY_FROM_S) * 1000) & (odu_raw.t_ms < (t1 - STEADY_TO_S) * 1000)).sum())
        # indoor compressor lag on the raw reports
        lag = float("nan")
        w = (odu_raw.t_ms >= (t0 - 600) * 1000) & (odu_raw.t_ms < (t0 + 600) * 1000) & (odu_raw.value > ON_W)
        if w.any():
            t2 = int(odu_raw.t_ms[w][0])
            wi = (idu_raw.t_ms >= t2 - 600_000) & (idu_raw.t_ms < t2 + 900_000) & (idu_raw.value > 1500)
            if wi.any():
                lag = (int(idu_raw.t_ms[wi][0]) - t2) / 1000
        out.append(Run(
            start_s=t0, dur_s=t1 - t0, r6_at_start=float(g.r6[s]),
            odu_med_w=med(g.odu[sl]), odu_p10_w=q(g.odu[sl], 0.1), odu_p90_w=q(g.odu[sl], 0.9),
            idu_med_w=med(g.idu[sl]), flow_med_gpm=med(g.flow[sl]), lift_med_f=med(g.lift[sl]),
            lwt_med_f=med(g.lwt[sl]), ewt_med_f=med(g.ewt[sl]), foat_med_f=med(g.foat[s:e]),
            odu_reports_steady=n_rep, idu_lag_s=lag,
        ))
    return out


def idle_episodes(runs: list[Run], odu: Channel, foat: Channel, r6: Channel) -> list[IdleEpisode]:
    t, v = odu.t_ms, odu.value
    starts = np.array([r.start_s * 1000 for r in runs], dtype=np.int64)
    ends = np.array([(r.start_s + r.dur_s) * 1000 for r in runs], dtype=np.int64)
    inrun = np.zeros(len(t), dtype=bool)
    for a_ms, b_ms in zip(starts, ends):
        a, b = np.searchsorted(t, [a_ms, b_ms])
        inrun[a:b] = True
    hi = (v >= STATE_W[0]) & (v <= STATE_W[1]) & ~inrun

    def kind(i: int) -> str:
        if i < 0 or i >= len(t):
            return "other"
        return "standby" if (v[i] < STANDBY_W and not inrun[i]) else ("run" if inrun[i] else "other")

    out: list[IdleEpisode] = []
    i, n = 0, len(t)
    while i < n:
        if not hi[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and hi[j + 1] and t[j + 1] - t[j] < 330_000:
            j += 1
        k = int(np.searchsorted(ends, t[i])) - 1
        kn = int(np.searchsorted(starts, t[j]))
        fi = int(np.searchsorted(foat.t_ms, t[i])) - 1
        ri = int(np.searchsorted(r6.t_ms, t[i])) - 1
        out.append(IdleEpisode(
            first_s=int(t[i]) // 1000, last_s=int(t[j]) // 1000,
            prev_out_s=int(t[i - 1 if i > 0 else i]) // 1000, next_out_s=int(t[j + 1 if j + 1 < n else j]) // 1000,
            prev_kind=kind(i - 1), next_kind=kind(j + 1), reports=j - i + 1,
            level_w=float(np.median(v[i:j + 1])),
            since_stop_s=(int(t[i]) - int(ends[k])) / 1000 if k >= 0 else float("nan"),
            to_next_start_s=(int(starts[kn]) - int(t[j])) / 1000 if kn < len(starts) else float("nan"),
            foat_f=float(foat.value[fi]) if fi >= 0 and t[i] - foat.t_ms[fi] < 7_200_000 else float("nan"),
            r6=float(r6.value[ri]) if ri >= 0 else float("nan"),
        ))
        i = j + 1
    return out


def dips_of(g: Grid, runs: list[Run]) -> list[Dip]:
    st = g.step_s
    starts = np.array([r.start_s * 1000 for r in runs], dtype=np.int64)
    k = np.searchsorted(starts, g.t_ms) - 1
    since = np.where(k >= 0, (g.t_ms - starts[np.clip(k, 0, None)]) / 1000.0, np.nan)
    odu, idu, tot, lift = g.odu, g.idu, g.total, g.lift
    pre, back, maxlen = 300 // st, 2400 // st, 1800 // st
    out: list[Dip] = []
    for s, e in segments(idu < DIP_IDU_W):
        if s < 2 * pre or e + back >= len(odu) or not since[s] >= STEADY_FROM_S or (e - s) > maxlen:
            continue
        if not np.nanmax(odu[s - pre:s]) > DIP_PRE_ODU_W or not (g.r6[s:e] == R6_ON).mean() > 0.9:
            continue
        f = s - 1
        while f > s - 2 * pre and not odu[f] > DIP_PRE_ODU_W:
            f -= 1
        r = e
        while r < e + back and not tot[r] > DIP_BACK_W:
            r += 1
        if r >= e + back:
            continue
        w = slice(f, r)
        out.append(Dip(
            start_s=int(g.t_ms[f]) // 1000, kind="defrost" if np.nanmin(odu[f:e]) >= OFF_W else "stop",
            total_s=(r - f) * st, fall_to_idu_off_s=(s - f) * st, idu_off_s=(e - s) * st,
            sum_under_8400_s=int(np.nansum(tot[w] < 8400) * st),
            odu_min_w=float(np.nanmin(odu[f:e])), odu_med_w=med(odu[w]), idu_max_before_w=float(np.nanmax(idu[f:s + 1])),
            lift_pre_f=med(lift[f - pre:f]), lift_min_f=float(np.nanmin(lift[w])) if np.isfinite(lift[w]).any() else float("nan"),
            lwt_pre_f=med(g.lwt[f - pre:f]), lwt_max_pre_f=float(np.nanmax(g.lwt[f - 2 * pre:f + 1])) if np.isfinite(g.lwt[f - 2 * pre:f + 1]).any() else float("nan"),
            lwt_min_f=float(np.nanmin(g.lwt[w])) if np.isfinite(g.lwt[w]).any() else float("nan"),
            flow_min_gpm=float(np.nanmin(g.flow[w])) if np.isfinite(g.flow[w]).any() else float("nan"), flow_med_gpm=med(g.flow[w]),
            foat_f=med(g.foat[w]), since_start_s=float(since[f]),
        ))
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    p.add_argument("--house", required=True, choices=["beech", "oak"])
    args = p.parse_args()
    g = grid(args.house, 10)
    raw = load(args.house)
    runs = runs_of(g, compressor_on(g.odu, g.step_s), raw[ODU], raw[IDU])
    eps = idle_episodes(runs, raw[ODU], raw[FOAT], raw[R6])
    dips = dips_of(g, runs)
    for rec, rows in ((Run, runs), (IdleEpisode, eps), (Dip, dips)):
        path = write(args.house, rec, rows)  # pyright: ignore[reportArgumentType]
        print(f"wrote {path.name} ({len(rows)} records)")


if __name__ == "__main__":
    main()
