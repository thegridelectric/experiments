#!/usr/bin/env python3
"""What a call from a seldom-calling zone does to the distribution
return while another zone is in steady call, and how long the
source-to-return drop takes to come back: from the minute file
pump_speed.py writes, for a house in houses.ZONE_PAIRS.

An event is a call from the idle zone (its white wire on in one or
more consecutive minutes) with the steady zone calling alone, the loop
circulating and both temperature readings fresh for PRE_MIN before it
and at least POST_MIN after it. The pre-call drop is the mean over the
PRE_MIN minutes. Recovery is the first minute after the call ends
where the drop is within RECOVER_FRAC of the pre-call drop and stays
there the next minute too. An event whose post window ends before
recovery is censored at the window's length.

Writes <house>-bolus-recovery.txt (the distribution) and, with --plot,
<house>-bolus-recovery.png: one representative event (the recovered
event whose recovery time is the median, with the longest post window
among ties) with every temperature around the buffer and heat pump,
pulled from the journal DB for that window.

  uv run python bolus_recovery.py --house beech --plot
"""

import argparse
import datetime
import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

from grid import GRID_S, natural, on_grid, pull  # noqa: E402
from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.property_format import SpaceheatName, UTCSeconds  # noqa: E402
from houses import ZONE_PAIRS, hourly_files, minute_file, ta_alias  # noqa: E402
from pull_readings import ET  # noqa: E402
from records import HourRecord, MinuteArrays  # noqa: E402
from tables import Table  # noqa: E402

PRE_MIN = 10
POST_MIN = 10
POST_MAX = 60  # follow an event this long at most
RECOVER_FRAC = 0.05
FRESH_S = 120
FLOWING_GPM = 0.5
STEADY_HOUR = 0.95  # an hourly record with FlowingFraction at or above this fits the steady line
HELD_F = 3.0  # the source held when it stayed within this of its pre-call mean over HELD_FROM..POST_MIN after the call
HELD_FROM_MIN = 3  # the slug's own pass through the heat pump dips the source; the held test starts after it
CONTROL_CLEAR_MIN = 30  # a control minute has no idle-zone call this long before it
CONTROL_STRIDE = 5  # minutes between control samples
SLUG_F = 65.0  # the idle loop's water is taken to be at room temperature when the call starts
DEFICIT_AFTER_MIN = 5  # the return deficit is summed from the call's start to this long after it ends


class Event(NamedTuple):
    """One idle-zone call with a steady call around it.

    No sema word holds an analysis event; a word for channel-derived
    events retires this record.
    """

    call_start_s: UTCSeconds  # first minute the idle zone's wire was on
    call_minutes: int  # minutes the wire was on
    pre_drop_f: float  # mean source-to-return drop over PRE_MIN before the call
    pre_source_f: float
    post_minutes: int  # minutes of steady call after the call, up to POST_MAX
    recovery_min: int | None  # minutes after the call ended; None if censored
    peak_excess_f: float  # most the drop exceeded its pre-call value, from the call start to recovery or window end


class Minutes(NamedTuple):
    """The minute file's columns an event search reads, plus the drop."""

    t: np.ndarray  # minute start, UTC s
    gpm: np.ndarray
    swt: np.ndarray
    rwt: np.ndarray
    drop: np.ndarray  # swt - rwt
    age: np.ndarray  # oldest temperature reading used in the minute, s
    steady_call: np.ndarray  # steady zone's call fraction
    idle_call: np.ndarray  # idle zone's call fraction

    @classmethod
    def of(cls, m: MinuteArrays, house: str) -> "Minutes":
        zones = ZONE_PAIRS[house]
        return cls(t=m.minute_start_s, gpm=m.gpm, swt=m.source_f, rwt=m.return_f,
                   drop=m.source_f - m.return_f, age=m.temp_age_s,
                   steady_call=m.calls[zones.steady], idle_call=m.calls[zones.idle])

    def at(self, start_s: UTCSeconds) -> int:
        """The row of the minute that starts at start_s."""
        return int(np.where(self.t == start_s)[0][0])


def events(m: Minutes) -> list[Event]:
    contiguous = np.diff(m.t) == 60
    steady = ((m.steady_call >= 0.999) & (m.idle_call <= 0.001)
              & (m.gpm >= FLOWING_GPM) & (m.age <= FRESH_S))
    out: list[Event] = []
    i = 1
    n = len(m.t)
    while i < n:
        if not (m.idle_call[i] > 0 and m.idle_call[i - 1] == 0):
            i += 1
            continue
        j = i
        while j + 1 < n and m.idle_call[j + 1] > 0 and contiguous[j]:
            j += 1
        pre = slice(i - PRE_MIN, i)
        pre_ok = i - PRE_MIN >= 0 and steady[pre].all() and contiguous[i - PRE_MIN:i].all()
        k = j + 1
        while k < n and k - j <= POST_MAX and steady[k] and contiguous[k - 1]:
            k += 1
        post_minutes = k - (j + 1)
        if not pre_ok or post_minutes < POST_MIN:
            i = j + 1
            continue
        pre_drop = float(m.drop[pre].mean())
        recovery = first_within(m, i, j, k, pre_drop, RECOVER_FRAC)
        end = j + 1 + recovery if recovery is not None else k
        out.append(Event(
            call_start_s=int(m.t[i]), call_minutes=j - i + 1, pre_drop_f=pre_drop,
            pre_source_f=float(m.swt[pre].mean()), post_minutes=post_minutes,
            recovery_min=recovery, peak_excess_f=float(m.drop[i:end + 1].max() - pre_drop),
        ))
        i = j + 1
    return out


def first_within(m: Minutes, i: int, j: int, k: int, pre_drop: float,
                 frac: float) -> int | None:
    """Minutes after the call (minutes i..j) ended until the drop is
    within frac of pre_drop for two consecutive minutes, searching the
    post window up to minute k."""
    for x in range(j + 1, k - 1):
        if (abs(m.drop[x] - pre_drop) <= frac * pre_drop
                and abs(m.drop[x + 1] - pre_drop) <= frac * pre_drop):
            return x - j
    return None


def recovery_at(m: Minutes, e: Event, frac: float) -> int | None:
    """An event's recovery time against another band."""
    i = m.at(e.call_start_s)
    j = i + e.call_minutes - 1
    return first_within(m, i, j, j + 1 + e.post_minutes, e.pre_drop_f, frac)


def excess_by_minute(m: Minutes, evs: list[Event]) -> list[tuple[int, float, int]]:
    """(minute after the call ended, median drop minus pre-call drop, events) for a few minutes."""
    out = []
    for x in (0, 1, 2, 3, 5, 7, 10, 15, 20, 30):
        vals = [m.drop[m.at(e.call_start_s) + e.call_minutes + x] - e.pre_drop_f
                for e in evs if e.post_minutes > x]
        if vals:
            out.append((x, float(np.median(vals)), len(vals)))
    return out


class SteadyLine(NamedTuple):
    """The house's steady-circulation drop as a line in source
    temperature, fitted to its steady hours. No sema word holds a
    fitted relation; a word for a channel-derived fit retires this."""

    intercept_f: float
    slope: float  # °F of drop per °F of source
    hours: int

    def drop_at(self, source_f: float) -> float:
        return self.intercept_f + self.slope * source_f


def steady_line(house: str) -> SteadyLine:
    hours: list[HourRecord] = [h for f in hourly_files() if f.ta_alias == ta_alias(house)
                               for h in f.hours if h.flowing_fraction >= STEADY_HOUR]
    source = np.array([h.source_f for h in hours], float)
    drop = np.array([h.drop_f for h in hours], float)
    slope, intercept = np.polyfit(source, drop, 1)
    return SteadyLine(intercept_f=float(intercept), slope=float(slope), hours=len(hours))


def detrended_excess(m: Minutes, e: Event, line: SteadyLine, r: int) -> float:
    """The drop's excess over its pre-call value at row r, less the part
    the steady line assigns to the source's own move since the call."""
    return float(m.drop[r] - e.pre_drop_f - line.slope * (m.swt[r] - e.pre_source_f))


def first_within_detrended(m: Minutes, e: Event, line: SteadyLine, frac: float) -> int | None:
    i = m.at(e.call_start_s)
    j = i + e.call_minutes - 1
    k = j + 1 + e.post_minutes
    for x in range(j + 1, k - 1):
        if (abs(detrended_excess(m, e, line, x)) <= frac * e.pre_drop_f
                and abs(detrended_excess(m, e, line, x + 1)) <= frac * e.pre_drop_f):
            return x - j
    return None


def source_held(m: Minutes, e: Event) -> bool:
    """True when the source stayed within HELD_F of its pre-call mean
    from HELD_FROM_MIN through POST_MIN after the call ended (the
    slug's own pass through a running heat pump dips the source for
    the first minutes, so those are not the test)."""
    j1 = m.at(e.call_start_s) + e.call_minutes
    return bool(np.all(np.abs(m.swt[j1 + HELD_FROM_MIN:j1 + POST_MIN + 1] - e.pre_source_f) <= HELD_F))


def control_excess(m: Minutes, line: SteadyLine, lags: tuple[int, ...]) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """The drop's excess over the preceding PRE_MIN mean at each lag, raw
    and less the steady line's share of the source's move, at
    minutes of steady call with no idle-zone call from CONTROL_CLEAR_MIN
    before to the last lag after; every CONTROL_STRIDE-th such minute."""
    contiguous = np.diff(m.t) == 60
    steady = ((m.steady_call >= 0.999) & (m.idle_call <= 0.001)
              & (m.gpm >= FLOWING_GPM) & (m.age <= FRESH_S))
    out: dict[int, tuple[list[float], list[float]]] = {}
    for x in lags:
        vals: list[float] = []
        det: list[float] = []
        taken = 0
        for i in range(PRE_MIN, len(m.t) - x - 1):
            if not (steady[i - PRE_MIN:i + x + 1].all() and contiguous[i - PRE_MIN:i + x].all()):
                continue
            if (m.idle_call[max(0, i - CONTROL_CLEAR_MIN):i + x + 1] > 0).any():
                continue
            taken += 1
            if taken % CONTROL_STRIDE:
                continue
            vals.append(float(m.drop[i + x] - m.drop[i - PRE_MIN:i].mean()))
            det.append(vals[-1] - line.slope * float(m.swt[i + x] - m.swt[i - PRE_MIN:i].mean()))
        out[x] = (vals, det)
    return {x: (np.array(v), np.array(d)) for x, (v, d) in out.items()}


def slug_volume_gal(m: Minutes, e: Event, slug_f: float) -> float:
    """The idle loop's cold water as the volume at slug_f that carries
    the return's heat deficit over the event: sum of flow x (pre-call
    return - return) over the minutes from the call's start to
    DEFICIT_AFTER_MIN after it ends, over (pre-call return - slug_f).
    The emitter's iron takes heat from the water that fills it, so this
    is a cold-water equivalent, not the pipe and radiator volume."""
    i = m.at(e.call_start_s)
    pre_ret = float(m.rwt[i - PRE_MIN:i].mean())
    end = i + e.call_minutes + DEFICIT_AFTER_MIN
    deficit = np.clip(pre_ret - m.rwt[i:end], 0, None)
    return float(np.sum(m.gpm[i:end] * deficit) / (pre_ret - slug_f))


def volume_lines(m: Minutes, evs: list[Event]) -> list[str]:
    lines = [f"\nthe idle loop's cold water, as the volume at {SLUG_F:.0f} °F carrying the return's heat deficit "
             f"from the call's start to {DEFICIT_AFTER_MIN} min after it ended (gal): q25 / median / q75, "
             f"and the same with the slug 5 °F colder and warmer"]
    for slug in (SLUG_F, SLUG_F - 5, SLUG_F + 5):
        v = np.array([slug_volume_gal(m, e, slug) for e in evs])
        q = np.percentile(v, [25, 50, 75])
        lines.append(f"  slug {slug:.0f} °F: {q[0]:.1f} / {q[1]:.1f} / {q[2]:.1f}")
    extra = [float(m.gpm[m.at(e.call_start_s):m.at(e.call_start_s) + e.call_minutes].mean()
                   - m.gpm[m.at(e.call_start_s) - PRE_MIN:m.at(e.call_start_s)].mean()) for e in evs]
    lines.append(f"  flow added by the idle zone's valve during the call: median {np.median(extra):.2f} gpm")
    return lines


def excess_lines(m: Minutes, evs: list[Event], line: SteadyLine) -> list[str]:
    """The report's second half: what the drop did 10 to 30 minutes
    after the call and how much of it the source explains."""
    lines = [f"\nsteady line, {line.hours} steady hours: drop = {line.intercept_f:+.1f} {line.slope:+.3f} x source (°F)"]
    lags = (10, 15, 20, 30)
    ctrl = control_excess(m, line, lags)
    lines.append(f"excess of the drop over its pre-call value by minute after the call ended, °F "
                 f"(events whose window reaches that minute): share beyond ±{HELD_F:.0f}, median, "
                 f"median source move, detrended (the source's share removed by the steady line) q25/median/q75; "
                 f"then control minutes (steady call, no idle call for {CONTROL_CLEAR_MIN} min before): "
                 f"share beyond ±{HELD_F:.0f}, detrended q25/median/q75, n")
    q = lambda a: "/".join(f"{v:+.1f}" for v in np.percentile(a, [25, 50, 75]))  # noqa: E731
    for x in lags:
        sel = [e for e in evs if e.post_minutes > x]
        if not sel:
            continue
        rows = [(m.at(e.call_start_s) + e.call_minutes + x, e) for e in sel]
        ex = np.array([m.drop[r] - e.pre_drop_f for r, e in rows])
        ds = np.array([m.swt[r] - e.pre_source_f for r, e in rows])
        det = np.array([detrended_excess(m, e, line, r) for r, e in rows])
        c, cd = ctrl[x]
        lines.append(f"  +{x:2d}: n={len(sel):2d}  beyond ±{HELD_F:.0f}: {100 * np.mean(np.abs(ex) > HELD_F):3.0f}%  "
                     f"median {np.median(ex):+.1f}  source {np.median(ds):+.1f}  detrended {q(det)}  "
                     f"| control: {100 * np.mean(np.abs(c) > HELD_F):3.0f}%  detrended {q(cd)}  n={len(c)}")
    held = [e for e in evs if source_held(m, e)]
    moved = [e for e in evs if not source_held(m, e)]
    lines.append(f"source held within ±{HELD_F:.0f} °F of its pre-call mean over minutes {HELD_FROM_MIN} to {POST_MIN} after the call: {len(held)} of {len(evs)} events")
    if held:
        rec = [e.recovery_min for e in held if e.recovery_min is not None]
        w10 = sum(1 for r in rec if r <= POST_MIN)
        lines.append(f"  of those, recovered to within {RECOVER_FRAC:.0%} inside {POST_MIN} min: {w10} of {len(held)}; "
                     f"recovery minutes median {np.median(rec) if rec else float('nan'):.0f}, max {max(rec) if rec else float('nan')}")
        late = [e for e in held if e.recovery_min is None or e.recovery_min > POST_MIN]
        for e in late:
            lines.append(f"    not inside {POST_MIN} min: {datetime.datetime.fromtimestamp(e.call_start_s, ET):%Y-%m-%d %H:%M} ET, "
                         f"pre drop {e.pre_drop_f:.1f}, recovery {e.recovery_min}, post window {e.post_minutes} min")
    if moved:
        det_rec = [first_within_detrended(m, e, line, RECOVER_FRAC) for e in moved]
        got = [r for r in det_rec if r is not None]
        lines.append(f"  source moved in the other {len(moved)}: against the steady line, "
                     f"{len(got)} recovered (median {np.median(got) if got else float('nan'):.0f} min); "
                     f"{len(moved) - len(got)} did not inside their window")
    return lines


def report(m: Minutes, evs: list[Event], house: str) -> str:
    lines = [f"upstairs calls with a steady downstairs-only call {PRE_MIN} min before and "
             f">= {POST_MIN} min after: {len(evs)}"]
    rec = np.array([e.recovery_min for e in evs if e.recovery_min is not None], float)
    cen = [e for e in evs if e.recovery_min is None]
    lines.append(f"recovered to within {RECOVER_FRAC:.0%} of the pre-call drop: {len(rec)}; "
                 f"not recovered inside the post window: {len(cen)}")
    if len(rec):
        q = np.percentile(rec, [25, 50, 75, 90])
        lines.append(f"recovery minutes after the call ended, recovered events: "
                     f"q25 {q[0]:.0f}  median {q[1]:.0f}  q75 {q[2]:.0f}  q90 {q[3]:.0f}  max {rec.max():.0f}")
    rec10 = [recovery_at(m, e, 0.10) for e in evs]
    lines.append(f"within 10% of the pre-call drop instead: recovered {sum(r is not None for r in rec10)}, "
                 f"median {np.median([r for r in rec10 if r is not None]):.0f} min")
    for lim in (5, 10, 15, 20, 30):
        within = sum(1 for e in evs if e.recovery_min is not None and e.recovery_min <= lim)
        able = sum(1 for e in evs if e.recovery_min is not None or e.post_minutes >= lim)
        lines.append(f"  recovered within {lim:2d} min: {within} of the {able} events whose window reaches {lim} min ({100 * within / max(able, 1):.0f}%)")
    lines.append("by upstairs call length (min): n, median recovery, share recovered within 10 min, median pre-call drop, median peak excess of the drop")
    for lo, hi in ((1, 2), (3, 5), (6, 10), (11, 20), (21, 999)):
        sel = [e for e in evs if lo <= e.call_minutes <= hi]
        if not sel:
            continue
        r = [e.recovery_min for e in sel if e.recovery_min is not None]
        w10 = sum(1 for e in sel if e.recovery_min is not None and e.recovery_min <= 10)
        able = sum(1 for e in sel if e.recovery_min is not None or e.post_minutes >= 10)
        lines.append(f"  {lo:2d}-{hi if hi < 999 else '':>3} : n={len(sel):3d}  median {np.median(r) if r else float('nan'):4.0f}  "
                     f"within 10: {100 * w10 / max(able, 1):3.0f}%  pre drop {np.median([e.pre_drop_f for e in sel]):4.1f}  "
                     f"peak {np.median([e.peak_excess_f for e in sel]):4.1f}")
    lines.append("median excess of the drop over its pre-call value, °F, by minute after the call ended "
                 "(events whose window reaches that minute):")
    lines.append("  " + "  ".join(f"+{x}: {v:+.1f} ({n})" for x, v, n in excess_by_minute(m, evs)))
    if cen:
        lines.append(f"censored events' post windows (min): median {np.median([e.post_minutes for e in cen]):.0f}, max {max(e.post_minutes for e in cen)}")
    lines.extend(excess_lines(m, evs, steady_line(house)))
    lines.extend(volume_lines(m, evs))
    return "\n".join(lines)


PLOT_TEMPS: list[tuple[SpaceheatName, str, str]] = [  # (channel, label, color)
    ("dist-swt", "dist source", "#eb6834"),
    ("dist-rwt", "dist return", "#2a78d6"),
    ("buffer-hot-pipe", "buffer hot pipe", "#1baf7a"),
    ("buffer-depth1", "buffer depth 1", "#eda100"),
    ("buffer-depth2", "buffer depth 2", "#e87ba4"),
    ("buffer-depth3", "buffer depth 3", "#008300"),
    ("hp-lwt", "hp leaving", "#5f5e58"),
    ("hp-ewt", "hp entering", "#9b9a92"),
]
HP_PWR: SpaceheatName = "hp-odu-pwr"
PLOT_FLOWS: list[tuple[SpaceheatName, str, str]] = [
    ("primary-flow", "primary gpm", "#1baf7a"),
    ("dist-flow", "dist gpm", "#2a78d6"),
]
PLOT_BEFORE_MIN = 15
PLOT_AFTER_MIN = 30


def event_traces(house: str, pick: Event) -> tuple[np.ndarray, dict[SpaceheatName, np.ndarray]]:
    """Every plotted channel on the 10 s grid around the event, in
    natural units, keyed by channel; minutes from the call start."""
    start_ms = (pick.call_start_s - PLOT_BEFORE_MIN * 60) * 1000
    end_ms = (pick.call_start_s + (pick.call_minutes + PLOT_AFTER_MIN) * 60) * 1000
    names = [n for n, _, _ in PLOT_TEMPS] + [HP_PWR] + [n for n, _, _ in PLOT_FLOWS]
    p = pull(ta_alias(house), names, [], start_ms, end_ms, SemaCodec())
    traces: dict[SpaceheatName, np.ndarray] = {}
    for name in names:
        if name in p.rows:
            raw, _ = on_grid(p.rows[name], p.grid_ms)
            traces[name] = natural(p.words[name], raw)
    minutes = (p.grid_ms / 1000 - pick.call_start_s) / 60
    return minutes, traces


def plot(house: str, evs: list[Event], path: Path) -> Event:
    import matplotlib  # only with --plot; the report needs no matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    recovered = [(e.recovery_min, e) for e in evs if e.recovery_min is not None]
    med = round(float(np.median([r for r, _ in recovered])))
    pick = max((e for r, e in recovered if r == med), key=lambda e: e.post_minutes)
    assert pick.recovery_min is not None
    back_at = pick.call_minutes + pick.recovery_min
    rel, tr = event_traces(house, pick)
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(9, 7), dpi=150, sharex=True,
                                  gridspec_kw={"height_ratios": [3, 1.2]})
    for a in (ax, ax2):
        a.axvspan(0, pick.call_minutes, color="#c3c2b7", alpha=0.35, lw=0)
        for sp in ("top", "right"):
            a.spines[sp].set_visible(False)
        a.grid(axis="y", color="#e6e5df", lw=0.8)
    for name, label, color in PLOT_TEMPS:
        if name in tr:
            ax.plot(rel, tr[name], color=color, lw=2 if name.startswith("dist") else 1.2, label=label)
    ax.axvline(back_at, color="#5f5e58", lw=1, ls="--")
    ax.text(back_at + 0.4, ax.get_ylim()[0] + 2,
            f"drop back within {RECOVER_FRAC:.0%}\n{pick.recovery_min} min after the call", fontsize=8, color="#5f5e58")
    when = datetime.datetime.fromtimestamp(pick.call_start_s, ET).strftime("%Y-%m-%d %H:%M")
    ax.set_title(f"{house}: an upstairs call of {pick.call_minutes} min during a steady downstairs call, {when} ET "
                 f"(shaded: upstairs zone calling)", fontsize=10)
    ax.set_ylabel("°F")
    ax.legend(frameon=False, fontsize=8, loc="lower right", ncol=2)
    if HP_PWR in tr:
        ax2.plot(rel, tr[HP_PWR] / 1000, color="#5f5e58", lw=1.2, label="hp outdoor unit kW")
    for name, label, color in PLOT_FLOWS:
        if name in tr:
            ax2.plot(rel, tr[name], color=color, lw=1.2, label=label)
    ax2.set_ylabel("kW · gpm")
    ax2.set_xlabel(f"minutes from the start of the upstairs call ({GRID_S} s grid)")
    ax2.legend(frameon=False, fontsize=8, loc="upper right", ncol=3)
    fig.tight_layout()
    fig.savefig(path)
    return pick


def tables(house: str) -> list[Table]:
    m = Minutes.of(minute_file(house).minutes.arrays(), house)
    evs = events(m)
    line = steady_line(house)
    lags = (10, 15, 20, 30)
    ctrl = control_excess(m, line, lags)
    event_rows = []
    for e in evs:
        event_rows.append((
            datetime.datetime.fromtimestamp(e.call_start_s, ET).strftime("%Y-%m-%d %H:%M"), e.call_minutes,
            round(e.pre_drop_f, 1), round(e.pre_source_f, 1), e.post_minutes, e.recovery_min,
            recovery_at(m, e, 0.10), round(e.peak_excess_f, 1), source_held(m, e),
            round(slug_volume_gal(m, e, SLUG_F), 1)))
    excess_rows = []
    for x in lags:
        sel = [e for e in evs if e.post_minutes > x]
        rows = [(m.at(e.call_start_s) + e.call_minutes + x, e) for e in sel]
        ex = np.array([m.drop[r] - e.pre_drop_f for r, e in rows])
        ds = np.array([m.swt[r] - e.pre_source_f for r, e in rows])
        det = np.array([detrended_excess(m, e, line, r) for r, e in rows])
        c, cd = ctrl[x]
        q = lambda a: tuple(round(float(v), 1) for v in np.percentile(a, [25, 50, 75]))  # noqa: E731
        excess_rows.append((x, len(sel), round(float(np.mean(np.abs(ex) > HELD_F)), 2), round(float(np.median(ex)), 1),
                            round(float(np.median(ds)), 1), *q(det), len(c),
                            round(float(np.mean(np.abs(c) > HELD_F)), 2), *q(cd)))
    volume_rows = []
    for slug in (SLUG_F - 5, SLUG_F, SLUG_F + 5):
        v = np.array([slug_volume_gal(m, e, slug) for e in evs])
        q25, q50, q75 = np.percentile(v, [25, 50, 75])
        volume_rows.append((slug, round(float(q25), 1), round(float(q50), 1), round(float(q75), 1)))
    tag = f"{house}-cold-zone"
    return [
        Table(f"{tag}-events", f"{house}: each idle-zone call inside a steady call, its recovery and the cold water it returned",
              ("CallStartEt", "CallMinutes", "PreDropF", "PreSourceF", "PostMinutes", "RecoveryMin5Pct", "RecoveryMin10Pct",
               "PeakExcessF", "SourceHeld", "SlugGal"), event_rows, "bolus_recovery.py"),
        Table(f"{tag}-excess", f"{house}: the drop's excess over its pre-call value by minute after the call, against control minutes; detrended = the steady line's share of the source's move removed (slope {line.slope:.3f} F per F)",
              ("MinutesAfter", "Events", "ShareBeyond3F", "MedianExcessF", "MedianSourceMoveF", "DetrendedQ25F", "DetrendedMedianF",
               "DetrendedQ75F", "ControlMinutes", "ControlShareBeyond3F", "ControlDetrendedQ25F", "ControlDetrendedMedianF",
               "ControlDetrendedQ75F"), excess_rows, "bolus_recovery.py"),
        Table(f"{tag}-slug-volume", f"{house}: the idle loop's cold water as a volume at the slug temperature, quartiles over the calls",
              ("SlugF", "GalQ25", "GalMedian", "GalQ75"), volume_rows, "bolus_recovery.py"),
    ]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--house", required=True, choices=sorted(ZONE_PAIRS))
    p.add_argument("--plot", action="store_true")
    args = p.parse_args()
    m = Minutes.of(minute_file(args.house).minutes.arrays(), args.house)
    evs = events(m)
    text = report(m, evs, args.house)
    if args.plot:
        png = HERE / f"{args.house}-bolus-recovery.png"
        pick = plot(args.house, evs, png)
        text += (f"\nplotted: {png.name}, the upstairs call at "
                 f"{datetime.datetime.fromtimestamp(pick.call_start_s, ET).strftime('%Y-%m-%d %H:%M')} ET "
                 f"({pick.call_minutes} min, recovered {pick.recovery_min} min after)")
    (HERE / f"{args.house}-bolus-recovery.txt").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
