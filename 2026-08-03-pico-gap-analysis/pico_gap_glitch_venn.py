#!/usr/bin/env python3
"""Venn of the two pico-health angles (READ-ONLY): which reporting GAPS
were never tagged by a zombie GLITCH, and which zombie glitches have no
corresponding gap. Matching: same house, glitch declaration within
[gap_start - 10 min, gap_end + 10 min]; node identity shown for reading.

WINDOW_DAYS=56 ./pico_gap_glitch_venn.py   (GJK_DB_URL required)
"""

import os
import re
import sys
from collections import defaultdict

import psycopg

WINDOW_DAYS = int(os.environ.get("WINDOW_DAYS", "56"))
ABS_GAP_S = 600
MEDIAN_MULT = 3.0
PAD_S = 600
NAME_PATTERNS = ["%-flow%", "%-depth%", "%-lwt%", "%-ewt%", "%micro-v%", "%-pump-ct%"]

GAP_SQL = f"""
WITH pico_channels AS (
    SELECT id, name, terminal_asset_alias
    FROM gridworks.reading_channels
    WHERE {" OR ".join("name LIKE '" + p.replace("%", "%%") + "'" for p in NAME_PATTERNS)}
),
intervals AS MATERIALIZED (
    SELECT r.channel_id, r."timestamp" AS ts,
           EXTRACT(EPOCH FROM r."timestamp" - lag(r."timestamp") OVER
               (PARTITION BY r.channel_id ORDER BY r."timestamp")) AS dt
    FROM gridworks.readings r
    JOIN pico_channels c ON c.id = r.channel_id
    WHERE r."timestamp" > now() - interval '1 day' * %(days)s
),
med AS (
    SELECT channel_id, percentile_cont(0.5) WITHIN GROUP (ORDER BY dt) AS m
    FROM intervals WHERE dt IS NOT NULL GROUP BY channel_id
)
SELECT c.terminal_asset_alias, c.name,
       EXTRACT(EPOCH FROM i.ts) - i.dt AS gap_start, i.dt AS gap_dur
FROM intervals i
JOIN med USING (channel_id)
JOIN pico_channels c ON c.id = i.channel_id
WHERE i.dt > GREATEST({ABS_GAP_S}, {MEDIAN_MULT} * med.m)
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
    WHERE r."timestamp" > now() - interval '1 day' * %(days)s
),
hgaps AS (
    SELECT ta, ts, EXTRACT(EPOCH FROM ts - lag(ts) OVER
        (PARTITION BY ta ORDER BY ts)) AS dt
    FROM house_ts
)
SELECT ta, EXTRACT(EPOCH FROM ts) - dt, dt FROM hgaps WHERE dt > {ABS_GAP_S}
"""

GLITCH_SQL = """
SELECT m.from_alias, m.payload->>'Summary', m.payload->>'Node',
       m.payload->>'Details', EXTRACT(EPOCH FROM m.timestamp)
FROM gridworks.messages m
WHERE m.message_type_name = 'glitch'
  AND m.timestamp > now() - interval '1 day' * %(days)s
  AND (m.payload->>'Summary' = 'pico-just-zombied'
       OR m.payload->>'Summary' LIKE 'Zombie%%recovered%%')
"""


def house_of(alias: str) -> str:
    m = re.search(r"keene\.([a-z0-9]+)", alias or "")
    return m.group(1) if m else (alias or "?")


def main() -> int:
    url = os.environ["GJK_DB_URL"].replace("postgresql+psycopg://", "postgresql://")
    conn = psycopg.connect(url)
    cur = conn.cursor()
    cur.execute(GAP_SQL, {"days": WINDOW_DAYS})
    gaps = [(house_of(ta), name, float(s), float(s) + float(d))
            for ta, name, s, d in cur.fetchall()]
    cur.execute(HOUSE_SQL, {"days": WINDOW_DAYS})
    house_windows = defaultdict(list)
    for ta, gs, gd in cur.fetchall():
        house_windows[house_of(ta)].append((float(gs), float(gs) + float(gd)))
    def in_house_window(h, g0, g1):
        cov = sum(max(0.0, min(g1, h1) - max(g0, h0))
                  for h0, h1 in house_windows.get(h, []))
        return cov / (g1 - g0) >= 0.6 if g1 > g0 else False
    n_before = len(gaps)
    gaps = [(h, name, g0, g1) for h, name, g0, g1 in gaps
            if not in_house_window(h, g0, g1)]
    n_house_excluded = n_before - len(gaps)

    cur.execute(GLITCH_SQL, {"days": WINDOW_DAYS})
    zombies = [(house_of(a), su, no, de, float(ts)) for a, su, no, de, ts in cur.fetchall()]
    conn.close()

    decl = [(h, no, ts) for h, su, no, de, ts in zombies if su == "pico-just-zombied"]

    # gap -> any zombie declaration in-window at same house?
    tagged, untagged = 0, []
    for h, name, g0, g1 in gaps:
        hit = any(hz == h and g0 - PAD_S <= ts <= g1 + PAD_S for hz, _, ts in decl)
        if hit:
            tagged += 1
        else:
            untagged.append((h, name, g0, g1))

    # zombie declaration -> any overlapping gap at same house?
    z_tagged, z_untagged = 0, []
    for h, node, ts in decl:
        hit = any(hg == h and g0 - PAD_S <= ts <= g1 + PAD_S for hg, _, g0, g1 in gaps)
        if hit:
            z_tagged += 1
        else:
            z_untagged.append((h, node, ts))

    from datetime import datetime, timezone
    def f(ts):
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%m-%d %H:%M")

    print(f"VENN over {WINDOW_DAYS} days — {len(gaps)} channel-gap events "
          f"({n_house_excluded} excluded as house/scada-down windows), "
          f"{len(decl)} zombie declarations\n")
    print(f"gaps tagged by a zombie declaration     : {tagged}")
    print(f"gaps NOT tagged (self-recovered/etc.)   : {len(untagged)}")
    print(f"zombies tagged by a gap                 : {z_tagged}")
    print(f"zombies NOT tagged (sub-threshold)      : {len(z_untagged)}\n")

    byh = defaultdict(lambda: [0, 0])
    for h, *_ in untagged:
        byh[h][0] += 1
    for h, name, g0, g1 in gaps:
        byh[h][1] += 1
    print("untagged gaps by house (untagged/total):")
    for h in sorted(byh):
        print(f"  {h:8} {byh[h][0]}/{byh[h][1]}")

    print("\nzombies with NO gap (house, node, time UTC):")
    for h, node, ts in sorted(z_untagged, key=lambda x: x[2]):
        print(f"  {h:8} {node:14} {f(ts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
