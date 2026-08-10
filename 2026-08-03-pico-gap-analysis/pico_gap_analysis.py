#!/usr/bin/env python3
"""Pico reporting-gap analysis (READ-ONLY).

Measures inter-report gap statistics for pico-fed channels (flow / depth /
lwt / ewt / micro-v / pump-ct) over the last WINDOW_DAYS days of data,
aggregated per house (terminal_asset_alias).

A channel's normal cadence = median inter-report interval.
A GAP = an interval > max(10 min, 3 x median cadence).

All heavy lifting happens in SQL (one materialized lag() pass per channel);
python only sees one row per channel (with gap-duration / gap-start arrays,
which are small because gaps are rare).

Run anywhere with network reach to the GridWorks analytics database and
GJK_DB_URL set to its postgres URL (psycopg required).
"""

import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import LiteralString, NamedTuple

import psycopg
from pydantic import TypeAdapter

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.property_format import (  # noqa: E402
    LeftRightDot,
    SpaceheatName,
    UTCSeconds,
)

_LRD = TypeAdapter(LeftRightDot)
_SPACEHEAT = TypeAdapter(SpaceheatName)
_UTC_S = TypeAdapter(UTCSeconds)

WINDOW_DAYS = int(os.environ.get("WINDOW_DAYS", "14"))
ABS_GAP_S = 600.0  # 10 minutes
MEDIAN_MULT = 3.0
WORST_N = 5

# list[LiteralString] keeps the composed SQL a LiteralString for psycopg.
NAME_PATTERNS: list[LiteralString] = [
    "%-flow%", "%-depth%", "%-lwt%", "%-ewt%", "%micro-v%", "%-pump-ct%"]

ANCHOR_SQL = """
SELECT max("timestamp") FROM gridworks.readings
WHERE "timestamp" > now() - interval '1 day' * (%s + 16)
"""


HOUSE_SQL = f"""
WITH pico_channels AS (
    SELECT id, terminal_asset_alias
    FROM gridworks.reading_channels
    WHERE {" OR ".join("name LIKE '" + p.replace("%", "%%") + "'" for p in NAME_PATTERNS)}
),
house_ts AS (
    SELECT DISTINCT c.terminal_asset_alias AS ta, r."timestamp" AS ts
    FROM gridworks.readings r
    JOIN pico_channels c ON c.id = r.channel_id
    WHERE r."timestamp" >= %(t0)s AND r."timestamp" <= %(t1)s
),
hgaps AS (
    SELECT ta, ts,
           EXTRACT(EPOCH FROM ts - lag(ts) OVER
               (PARTITION BY ta ORDER BY ts)) AS dt
    FROM house_ts
)
SELECT ta, EXTRACT(EPOCH FROM ts) - dt AS gap_start, dt AS gap_dur
FROM hgaps WHERE dt > %(abs_gap)s
ORDER BY ta, gap_start
"""

MAIN_SQL = f"""
WITH pico_channels AS (
    SELECT id, name, terminal_asset_alias
    FROM gridworks.reading_channels
    WHERE {" OR ".join("name LIKE '" + p.replace("%", "%%") + "'" for p in NAME_PATTERNS)}
),
intervals AS MATERIALIZED (
    SELECT r.channel_id,
           r."timestamp" AS ts,
           EXTRACT(EPOCH FROM r."timestamp" - lag(r."timestamp") OVER
               (PARTITION BY r.channel_id ORDER BY r."timestamp")) AS dt
    FROM gridworks.readings r
    JOIN pico_channels c ON c.id = r.channel_id
    WHERE r."timestamp" >= %(t0)s AND r."timestamp" <= %(t1)s
),
med AS (
    SELECT channel_id,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY dt) AS median_dt
    FROM intervals
    WHERE dt IS NOT NULL
    GROUP BY channel_id
),
agg AS (
    SELECT i.channel_id,
           count(*)                          AS n_readings,
           min(i.ts)                         AS first_ts,
           max(i.ts)                         AS last_ts,
           array_agg(i.dt ORDER BY i.ts) FILTER
             (WHERE i.dt > GREATEST(%(abs_gap)s, %(med_mult)s * m.median_dt))
                                             AS gap_durs,
           array_agg(EXTRACT(EPOCH FROM i.ts) - i.dt ORDER BY i.ts) FILTER
             (WHERE i.dt > GREATEST(%(abs_gap)s, %(med_mult)s * m.median_dt))
                                             AS gap_starts
    FROM intervals i
    JOIN med m USING (channel_id)
    GROUP BY i.channel_id
)
SELECT c.terminal_asset_alias,
       c.name,
       m.median_dt,
       a.n_readings,
       a.first_ts,
       a.last_ts,
       a.gap_durs,
       a.gap_starts
FROM agg a
JOIN med m USING (channel_id)
JOIN pico_channels c ON c.id = a.channel_id
ORDER BY c.terminal_asset_alias, c.name
"""


class GapSpan(NamedTuple):
    """One reporting gap on one channel: silence start + duration."""
    start_unix_s: UTCSeconds
    dur_s: float

    @property
    def end_unix_s(self) -> float:
        return self.start_unix_s + self.dur_s


class HouseWindow(NamedTuple):
    """One whole-house silence (all pico channels quiet together —
    house / scada / pipeline outage, not pico data)."""
    start_unix_s: UTCSeconds
    end_unix_s: UTCSeconds


class ChannelRow(NamedTuple):
    """One channel's gap aggregate over the window (one MAIN_SQL row)."""
    ta: LeftRightDot
    name: SpaceheatName
    median_dt_s: float | None
    n_readings: int
    first_ts: datetime
    last_ts: datetime
    gaps: list[GapSpan]


class ChannelSummary(NamedTuple):
    """Per-channel display aggregate after house-window exclusion."""
    name: SpaceheatName
    median_dt_s: float
    gap_count: int
    gap_secs: float
    max_gap_s: float
    gap_pct: float


class GapEvent(NamedTuple):
    """One kept gap, channel-labeled, for cross-channel overlap."""
    channel: SpaceheatName
    start_unix_s: UTCSeconds
    end_s: float


def house_overlap_frac(gap: GapSpan, hgaps: list[HouseWindow]) -> float:
    """Fraction of a channel gap covered by house-silent windows."""
    g0, g1 = gap.start_unix_s, gap.end_unix_s
    cov = sum(max(0.0, min(g1, h.end_unix_s) - max(g0, h.start_unix_s))
              for h in hgaps)
    return cov / gap.dur_s if gap.dur_s > 0 else 0.0


def pctl(sorted_vals: list[float], q: float) -> float | None:
    """Linear-interpolated percentile of a pre-sorted list."""
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * q
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def fmin(secs: float) -> str:
    return f"{secs / 60:.1f}"


def house_short(alias: LeftRightDot) -> str:
    """Display name only: second-to-last alias segment."""
    parts = alias.split(".")
    return parts[-2] if len(parts) >= 2 and parts[-1] == "ta" else alias


def overlap_fraction(events: list[GapEvent]) -> float:
    """Fraction of gap events that overlap in time with a gap on a
    DIFFERENT channel of the same house."""
    if len(events) < 2:
        return 0.0
    n_overlap = 0
    for i, a in enumerate(events):
        for j, b in enumerate(events):
            if (i != j and b.channel != a.channel
                    and a.start_unix_s < b.end_s and b.start_unix_s < a.end_s):
                n_overlap += 1
                break
    return n_overlap / len(events)


def fetch(cur: psycopg.Cursor, t0: datetime,
          anchor: datetime) -> tuple[list[ChannelRow], dict[LeftRightDot, list[HouseWindow]]]:
    """Both SQL passes, converted to typed records at this boundary."""
    params = {"t0": t0, "t1": anchor,
              "abs_gap": ABS_GAP_S, "med_mult": MEDIAN_MULT}
    cur.execute(MAIN_SQL, params)
    rows = [ChannelRow(
        ta=_LRD.validate_python(ta),
        name=_SPACEHEAT.validate_python(name),
        median_dt_s=float(med) if med is not None else None,
        n_readings=n,
        first_ts=first_ts,
        last_ts=last_ts,
        gaps=[GapSpan(start_unix_s=_UTC_S.validate_python(int(s)),
                      dur_s=float(d))
              for s, d in zip(gstarts or [], gdurs or [])],
    ) for ta, name, med, n, first_ts, last_ts, gdurs, gstarts in cur.fetchall()]

    cur.execute(HOUSE_SQL, params)
    house_gaps: dict[LeftRightDot, list[HouseWindow]] = {}
    for ta, gs, gd in cur.fetchall():
        house_gaps.setdefault(_LRD.validate_python(ta), []).append(
            HouseWindow(start_unix_s=_UTC_S.validate_python(int(gs)),
                        end_unix_s=_UTC_S.validate_python(int(float(gs) + float(gd)))))
    return rows, house_gaps


def main() -> None:
    url = os.environ["GJK_DB_URL"].replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(ANCHOR_SQL, (WINDOW_DAYS,))
            row = cur.fetchone()
            anchor = row[0] if row else None
            if anchor is None:
                raise SystemExit("no readings in the last 30 days")
            t0 = anchor - timedelta(days=WINDOW_DAYS)
            rows, house_gaps = fetch(cur, t0, anchor)

    window_s = WINDOW_DAYS * 86400.0
    print(f"Pico reporting-gap analysis — window {t0:%Y-%m-%d %H:%M} .. "
          f"{anchor:%Y-%m-%d %H:%M} UTC ({WINDOW_DAYS} d)")
    print(f"Gap = interval > max({ABS_GAP_S / 60:.0f} min, "
          f"{MEDIAN_MULT:.0f} x median cadence)\n")

    houses: dict[LeftRightDot, list[ChannelRow]] = defaultdict(list)
    for r in rows:
        houses[r.ta].append(r)

    fleet_lines: list[str] = []
    hour_hist: Counter[int] = Counter()

    for alias in sorted(houses):
        chans = houses[alias]
        short = house_short(alias)
        medians = sorted(c.median_dt_s for c in chans
                         if c.median_dt_s is not None)
        hgaps = house_gaps.get(alias, [])
        all_gap_durs: list[float] = []
        events: list[GapEvent] = []
        tot_gap_secs, tot_gaps = 0.0, 0
        excl_house_gaps, excl_house_secs = 0, 0.0
        per_chan: list[ChannelSummary] = []
        for c in chans:
            kept: list[GapSpan] = []
            for g in c.gaps:
                if house_overlap_frac(g, hgaps) >= 0.6:
                    excl_house_gaps += 1
                    excl_house_secs += g.dur_s
                else:
                    kept.append(g)
            gsecs = sum(g.dur_s for g in kept)
            all_gap_durs.extend(g.dur_s for g in kept)
            tot_gap_secs += gsecs
            tot_gaps += len(kept)
            span = (c.last_ts - c.first_ts).total_seconds() or 1.0
            per_chan.append(ChannelSummary(
                name=c.name,
                median_dt_s=c.median_dt_s or 0.0,
                gap_count=len(kept),
                gap_secs=gsecs,
                max_gap_s=max((g.dur_s for g in kept), default=0.0),
                gap_pct=100.0 * gsecs / span,
            ))
            for g in kept:
                events.append(GapEvent(channel=c.name,
                                       start_unix_s=g.start_unix_s,
                                       end_s=g.end_unix_s))
                hour_hist[datetime.fromtimestamp(
                    g.start_unix_s, tz=timezone.utc).hour] += 1

        all_gap_durs.sort()
        n_chan = len(chans)
        gap_pct = 100.0 * tot_gap_secs / (n_chan * window_s)
        ovl = overlap_fraction(events)

        print("=" * 78)
        if hgaps:
            hsum = sum(h.end_unix_s - h.start_unix_s for h in hgaps)
            print(f"  HOUSE-WIDE SILENCE (all pico channels quiet together — house/"
                  f"scada/pipeline outage, NOT pico problems): {len(hgaps)} "
                  f"window(s), {fmin(hsum)} total; {excl_house_gaps} channel-gaps "
                  f"({fmin(excl_house_secs)}) EXCLUDED from the stats above.")
            for h in hgaps[:5]:
                print(f"    {datetime.fromtimestamp(h.start_unix_s, tz=timezone.utc):%m-%d %H:%M} -> "
                      f"{datetime.fromtimestamp(h.end_unix_s, tz=timezone.utc):%m-%d %H:%M} UTC "
                      f"({fmin(h.end_unix_s - h.start_unix_s)})")
        print(f"HOUSE {short}  ({alias})")
        print(f"  pico channels analyzed : {n_chan}")
        if medians:
            med_of_meds = pctl(medians, 0.5) or 0.0
            print(f"  median cadence range   : {medians[0]:.0f}s .. {medians[-1]:.0f}s"
                  f"  (median of medians {med_of_meds:.0f}s)")
        print(f"  total gaps             : {tot_gaps}")
        if all_gap_durs:
            p50 = pctl(all_gap_durs, 0.5) or 0.0
            p95 = pctl(all_gap_durs, 0.95) or 0.0
            print(f"  gap duration (min)     : p50={fmin(p50)}"
                  f"  p95={fmin(p95)}"
                  f"  max={fmin(all_gap_durs[-1])}")
        print(f"  gapped time % of window: {gap_pct:.3f}%  "
              f"(sum {tot_gap_secs / 3600:.1f} ch-hours over {n_chan} ch x {WINDOW_DAYS} d)")
        print(f"  cross-channel overlap  : {100 * ovl:.0f}% of gaps overlap a gap on "
              f"another channel")
        print(f"  worst {WORST_N} channels (by gapped time):")
        print(f"    {'channel':38s} {'med_s':>6s} {'gaps':>5s} "
              f"{'gap_min':>8s} {'max_min':>8s} {'gap%':>6s}")
        for s in sorted(per_chan, key=lambda x: -x.gap_secs)[:WORST_N]:
            print(f"    {s.name:38s} {s.median_dt_s:6.0f} {s.gap_count:5d} "
                  f"{s.gap_secs / 60:8.1f} {s.max_gap_s / 60:8.1f} {s.gap_pct:6.3f}")
        print()

        p50s = fmin(pctl(all_gap_durs, 0.5) or 0.0) if all_gap_durs else "-"
        p95s = fmin(pctl(all_gap_durs, 0.95) or 0.0) if all_gap_durs else "-"
        maxs = fmin(all_gap_durs[-1]) if all_gap_durs else "-"
        fleet_lines.append(
            f"  {short:12s} chans={n_chan:3d}  gaps={tot_gaps:4d}  "
            f"p50={p50s:>6s}m  p95={p95s:>6s}m  max={maxs:>7s}m  "
            f"gapped={gap_pct:.3f}%  overlap={100 * ovl:.0f}%")

    print("=" * 78)
    print("FLEET SUMMARY (per house)")
    for line in fleet_lines:
        print(line)
    print()
    print("Gap-start hour-of-day histogram (UTC, fleet-wide):")
    total = sum(hour_hist.values()) or 1
    for h in range(24):
        c = hour_hist.get(h, 0)
        print(f"  {h:02d}h {c:4d} {'#' * round(60 * c / total)}")


if __name__ == "__main__":
    main()
