#!/usr/bin/env python3
"""Pico reporting-gap analysis (READ-ONLY).

Measures inter-report gap statistics for pico-fed channels (flow / depth /
lwt / ewt / micro-v / pump-ct) over the last 14 days of data, aggregated
per house (terminal_asset_alias).

A channel's normal cadence = median inter-report interval.
A GAP = an interval > max(10 min, 3 x median cadence).

All heavy lifting happens in SQL (one materialized lag() pass per channel);
python only sees one row per channel (with gap-duration / gap-start arrays,
which are small because gaps are rare).

Run anywhere with network reach to the GridWorks analytics database and
GJK_DB_URL set to its postgres URL (psycopg required).
"""

import os
from collections import Counter, defaultdict
from datetime import datetime, timezone

import psycopg

import os
WINDOW_DAYS = int(os.environ.get("WINDOW_DAYS", "14"))
ABS_GAP_S = 600.0  # 10 minutes
MEDIAN_MULT = 3.0
WORST_N = 5

NAME_PATTERNS = ["%-flow%", "%-depth%", "%-lwt%", "%-ewt%", "%micro-v%", "%-pump-ct%"]

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
FROM hgaps WHERE dt > {ABS_GAP_S}
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
           count(*) FILTER
             (WHERE i.dt > GREATEST({ABS_GAP_S}, {MEDIAN_MULT} * m.median_dt))
                                             AS gap_count,
           COALESCE(sum(i.dt) FILTER
             (WHERE i.dt > GREATEST({ABS_GAP_S}, {MEDIAN_MULT} * m.median_dt)), 0)
                                             AS gap_secs,
           array_agg(i.dt ORDER BY i.dt) FILTER
             (WHERE i.dt > GREATEST({ABS_GAP_S}, {MEDIAN_MULT} * m.median_dt))
                                             AS gap_durs,
           array_agg(EXTRACT(EPOCH FROM i.ts) - i.dt ORDER BY i.ts) FILTER
             (WHERE i.dt > GREATEST({ABS_GAP_S}, {MEDIAN_MULT} * m.median_dt))
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
       a.gap_count,
       a.gap_secs,
       a.gap_durs,
       a.gap_starts
FROM agg a
JOIN med m USING (channel_id)
JOIN pico_channels c ON c.id = a.channel_id
ORDER BY c.terminal_asset_alias, c.name
"""


def house_overlap_frac(gap_start, gap_dur, hgaps):
    """Fraction of a channel gap covered by house-silent windows."""
    g0, g1 = gap_start, gap_start + gap_dur
    cov = 0.0
    for h0, h1 in hgaps:
        cov += max(0.0, min(g1, h1) - max(g0, h0))
    return cov / gap_dur if gap_dur > 0 else 0.0


def pctl(sorted_vals, q):
    """Linear-interpolated percentile of a pre-sorted list."""
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * q
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def fmin(secs):
    return f"{secs / 60:.1f}"


def house_short(alias):
    parts = alias.split(".")
    return parts[-2] if len(parts) >= 2 and parts[-1] == "ta" else alias


def overlap_fraction(events):
    """events: list of (chan, start_s, end_s). Fraction of gap events that
    overlap in time with a gap on a DIFFERENT channel of the same house."""
    if len(events) < 2:
        return 0.0
    n_overlap = 0
    for i, (ch, s, e) in enumerate(events):
        for j, (ch2, s2, e2) in enumerate(events):
            if i != j and ch2 != ch and s < e2 and s2 < e:
                n_overlap += 1
                break
    return n_overlap / len(events)


def main():
    url = os.environ["GJK_DB_URL"].replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(url) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(ANCHOR_SQL, (WINDOW_DAYS,))
            anchor = cur.fetchone()[0]
            if anchor is None:
                raise SystemExit("no readings in the last 30 days")
            t0 = anchor - __import__("datetime").timedelta(days=WINDOW_DAYS)
            cur.execute(MAIN_SQL, {"t0": t0, "t1": anchor})
            rows = cur.fetchall()
            cur.execute(HOUSE_SQL, {"t0": t0, "t1": anchor})
            house_gaps = {}
            for ta, gs, gd in cur.fetchall():
                house_gaps.setdefault(ta, []).append((float(gs), float(gs) + float(gd)))

    window_s = WINDOW_DAYS * 86400.0
    print(f"Pico reporting-gap analysis — window {t0:%Y-%m-%d %H:%M} .. "
          f"{anchor:%Y-%m-%d %H:%M} UTC ({WINDOW_DAYS} d)")
    print(f"Gap = interval > max({ABS_GAP_S / 60:.0f} min, "
          f"{MEDIAN_MULT:.0f} x median cadence)\n")

    houses = defaultdict(list)
    for r in rows:
        houses[r[0]].append(r)

    fleet_lines = []
    hour_hist = Counter()

    for alias in sorted(houses):
        chans = houses[alias]
        short = house_short(alias)
        medians = sorted(float(c[2]) for c in chans if c[2] is not None)
        hgaps = house_gaps.get(alias, [])
        all_gap_durs, events = [], []
        tot_gap_secs, tot_gaps = 0.0, 0
        excl_house_gaps, excl_house_secs = 0, 0.0
        per_chan = []
        for (_, name, med, n, first_ts, last_ts, gc, gsecs, gdurs, gstarts) in chans:
            gdurs = [float(d) for d in (gdurs or [])]
            gstarts = [float(s) for s in (gstarts or [])]
            kept_d, kept_s = [], []
            for s, d in zip(gstarts, gdurs):
                if house_overlap_frac(s, d, hgaps) >= 0.6:
                    excl_house_gaps += 1
                    excl_house_secs += d
                else:
                    kept_d.append(d)
                    kept_s.append(s)
            gdurs, gstarts = kept_d, kept_s
            gc = len(gdurs)
            gsecs = sum(gdurs)
            all_gap_durs.extend(gdurs)
            tot_gap_secs += float(gsecs)
            tot_gaps += gc
            span = (last_ts - first_ts).total_seconds() or 1.0
            per_chan.append((name, float(med) if med else 0.0, n, gc,
                             float(gsecs), max(gdurs) if gdurs else 0.0,
                             100.0 * float(gsecs) / span))
            for s, d in zip(gstarts, gdurs):
                events.append((name, s, s + d))
                hour_hist[datetime.fromtimestamp(s, tz=timezone.utc).hour] += 1

        all_gap_durs.sort()
        n_chan = len(chans)
        gap_pct = 100.0 * tot_gap_secs / (n_chan * window_s)
        ovl = overlap_fraction(events)

        print("=" * 78)
        if hgaps:
            hsum = sum(h1 - h0 for h0, h1 in hgaps)
            print(f"  HOUSE-WIDE SILENCE (all pico channels quiet together — house/"
                  f"scada/pipeline outage, NOT pico problems): {len(hgaps)} "
                  f"window(s), {fmin(hsum)} total; {excl_house_gaps} channel-gaps "
                  f"({fmin(excl_house_secs)}) EXCLUDED from the stats above.")
            for h0, h1 in hgaps[:5]:
                from datetime import datetime as _dt
                print(f"    {_dt.fromtimestamp(h0, tz=timezone.utc):%m-%d %H:%M} -> "
                      f"{_dt.fromtimestamp(h1, tz=timezone.utc):%m-%d %H:%M} UTC "
                      f"({fmin(h1 - h0)})")
        print(f"HOUSE {short}  ({alias})")
        print(f"  pico channels analyzed : {n_chan}")
        if medians:
            print(f"  median cadence range   : {medians[0]:.0f}s .. {medians[-1]:.0f}s"
                  f"  (median of medians {pctl(medians, 0.5):.0f}s)")
        print(f"  total gaps             : {tot_gaps}")
        if all_gap_durs:
            print(f"  gap duration (min)     : p50={fmin(pctl(all_gap_durs, 0.5))}"
                  f"  p95={fmin(pctl(all_gap_durs, 0.95))}"
                  f"  max={fmin(all_gap_durs[-1])}")
        print(f"  gapped time % of window: {gap_pct:.3f}%  "
              f"(sum {tot_gap_secs / 3600:.1f} ch-hours over {n_chan} ch x {WINDOW_DAYS} d)")
        print(f"  cross-channel overlap  : {100 * ovl:.0f}% of gaps overlap a gap on "
              f"another channel")
        print(f"  worst {WORST_N} channels (by gapped time):")
        print(f"    {'channel':38s} {'med_s':>6s} {'gaps':>5s} "
              f"{'gap_min':>8s} {'max_min':>8s} {'gap%':>6s}")
        for name, med, n, gc, gsecs, gmax, gpct in sorted(
                per_chan, key=lambda x: -x[4])[:WORST_N]:
            print(f"    {name:38s} {med:6.0f} {gc:5d} "
                  f"{gsecs / 60:8.1f} {gmax / 60:8.1f} {gpct:6.3f}")
        print()

        fleet_lines.append(
            f"  {short:12s} chans={n_chan:3d}  gaps={tot_gaps:4d}  "
            f"p50={fmin(pctl(all_gap_durs, 0.5)) if all_gap_durs else '-':>6s}m  "
            f"p95={fmin(pctl(all_gap_durs, 0.95)) if all_gap_durs else '-':>6s}m  "
            f"max={fmin(all_gap_durs[-1]) if all_gap_durs else '-':>7s}m  "
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
