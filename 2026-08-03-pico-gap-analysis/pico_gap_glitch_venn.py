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
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import LiteralString, NamedTuple

import psycopg
from pydantic import TypeAdapter

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.property_format import (  # noqa: E402
    LeftRightDot,
    SpaceheatName,
    UTCSeconds,
)
from gwexp.sema.types import Glitch  # noqa: E402

_LRD = TypeAdapter(LeftRightDot)
_SPACEHEAT = TypeAdapter(SpaceheatName)
_UTC_S = TypeAdapter(UTCSeconds)

WINDOW_DAYS = int(os.environ.get("WINDOW_DAYS", "56"))
ABS_GAP_S = 600
MEDIAN_MULT = 3.0
PAD_S = 600
# list[LiteralString] keeps the composed SQL a LiteralString for psycopg.
NAME_PATTERNS: list[LiteralString] = [
    "%-flow%", "%-depth%", "%-lwt%", "%-ewt%", "%micro-v%", "%-pump-ct%"]

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
WHERE i.dt > GREATEST(%(abs_gap)s, %(med_mult)s * med.m)
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
SELECT ta, EXTRACT(EPOCH FROM ts) - dt, dt FROM hgaps WHERE dt > %(abs_gap)s
"""

GLITCH_SQL = """
SELECT m.payload
FROM gridworks.messages m
WHERE m.message_type_name = 'glitch'
  AND m.timestamp > now() - interval '1 day' * %(days)s
  AND m.payload->>'Summary' = 'pico-just-zombied'
"""


class GapEvent(NamedTuple):
    """One channel-gap event after house-window exclusion."""
    house: str
    channel: SpaceheatName
    start_unix_s: UTCSeconds
    end_unix_s: UTCSeconds


class HouseWindow(NamedTuple):
    """One whole-house silence (all pico channels quiet together)."""
    start_unix_s: UTCSeconds
    end_unix_s: UTCSeconds


class ZombieDecl(NamedTuple):
    """One pico-just-zombied event, derived from the decoded glitch
    word: `node` is the reporting actor, `unix_s` the word's CreatedMs
    (the reporting node's clock) coarsened to seconds for matching."""
    house: str
    node: SpaceheatName
    unix_s: UTCSeconds


def house_of(alias: LeftRightDot) -> str:
    """Display name only: the house segment of the alias."""
    m = re.search(r"keene\.([a-z0-9]+)", alias)
    return m.group(1) if m else alias


def main() -> int:
    url = os.environ["GJK_DB_URL"].replace("postgresql+psycopg://", "postgresql://")
    codec = SemaCodec()
    with psycopg.connect(url) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            params = {"days": WINDOW_DAYS, "abs_gap": ABS_GAP_S,
                      "med_mult": MEDIAN_MULT}
            cur.execute(GAP_SQL, params)
            gaps = [GapEvent(
                house=house_of(_LRD.validate_python(ta)),
                channel=_SPACEHEAT.validate_python(name),
                start_unix_s=_UTC_S.validate_python(int(s)),
                end_unix_s=_UTC_S.validate_python(int(float(s) + float(d))),
            ) for ta, name, s, d in cur.fetchall()]
            cur.execute(HOUSE_SQL, params)
            house_windows: dict[str, list[HouseWindow]] = {}
            for ta, gs, gd in cur.fetchall():
                house_windows.setdefault(
                    house_of(_LRD.validate_python(ta)), []).append(
                    HouseWindow(
                        start_unix_s=_UTC_S.validate_python(int(gs)),
                        end_unix_s=_UTC_S.validate_python(int(float(gs) + float(gd)))))
            cur.execute(GLITCH_SQL, {"days": WINDOW_DAYS})
            decl = []
            for (payload,) in cur.fetchall():
                g = codec.from_dict(payload, expect=Glitch)
                decl.append(ZombieDecl(
                    house=house_of(g.from_g_node_alias),
                    node=g.node,
                    unix_s=_UTC_S.validate_python(g.created_ms // 1000),
                ))

    def in_house_window(g: GapEvent) -> bool:
        cov = sum(max(0.0, min(g.end_unix_s, h.end_unix_s)
                      - max(g.start_unix_s, h.start_unix_s))
                  for h in house_windows.get(g.house, []))
        span = g.end_unix_s - g.start_unix_s
        return cov / span >= 0.6 if span > 0 else False

    n_before = len(gaps)
    gaps = [g for g in gaps if not in_house_window(g)]
    n_house_excluded = n_before - len(gaps)

    # gap -> any zombie declaration in-window at same house?
    tagged = 0
    untagged: list[GapEvent] = []
    for g in gaps:
        hit = any(z.house == g.house
                  and g.start_unix_s - PAD_S <= z.unix_s <= g.end_unix_s + PAD_S
                  for z in decl)
        if hit:
            tagged += 1
        else:
            untagged.append(g)

    # zombie declaration -> any overlapping gap at same house?
    z_tagged = 0
    z_untagged: list[ZombieDecl] = []
    for z in decl:
        hit = any(g.house == z.house
                  and g.start_unix_s - PAD_S <= z.unix_s <= g.end_unix_s + PAD_S
                  for g in gaps)
        if hit:
            z_tagged += 1
        else:
            z_untagged.append(z)

    def f(unix_s: UTCSeconds) -> str:
        return datetime.fromtimestamp(unix_s, tz=timezone.utc).strftime("%m-%d %H:%M")

    print(f"VENN over {WINDOW_DAYS} days — {len(gaps)} channel-gap events "
          f"({n_house_excluded} excluded as house/scada-down windows), "
          f"{len(decl)} zombie declarations\n")
    print(f"gaps tagged by a zombie declaration     : {tagged}")
    print(f"gaps NOT tagged (self-recovered/etc.)   : {len(untagged)}")
    print(f"zombies tagged by a gap                 : {z_tagged}")
    print(f"zombies NOT tagged (sub-threshold)      : {len(z_untagged)}\n")

    untagged_by_house: Counter[str] = Counter(g.house for g in untagged)
    total_by_house: Counter[str] = Counter(g.house for g in gaps)
    print("untagged gaps by house (untagged/total):")
    for h in sorted(total_by_house):
        print(f"  {h:8} {untagged_by_house.get(h, 0)}/{total_by_house[h]}")

    print("\nzombies with NO gap (house, node, time UTC):")
    for z in sorted(z_untagged, key=lambda z: z.unix_s):
        print(f"  {z.house:8} {z.node:14} {f(z.unix_s)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
