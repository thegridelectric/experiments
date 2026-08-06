#!/usr/bin/env python3
"""Read-only puller for the GridWorks analytics database (readings +
reading_channels). One tool, four modes — replaces the ad-hoc per-window
scripts this postmortem accreted.

Run with GJK_DB_URL set to the analytics postgres URL (psycopg required).

  # what channels exist (with coverage over the window)
  ./pull_readings.py inventory --like 'buffer%' --like 'hp-%'

  # 15-min bucket averages, CSV to stdout
  ./pull_readings.py buckets --channel hp-lwt --channel primary-flow \\
      --start '2026-07-26 00:00' --end '2026-08-03 00:00'

  # every raw reading in a window
  ./pull_readings.py raw --channel primary-flow \\
      --start '2026-07-29 15:00' --end '2026-07-29 15:40'

  # reporting gaps (interval > max(10 min, 3x median cadence))
  ./pull_readings.py gaps --channel secondary-flow \\
      --start '2026-07-26 00:00' --end '2026-08-03 00:00'

Times are America/New_York. Default terminal asset is spruce's; override
with --ta.
"""

import argparse
import os
import sys

import psycopg

DEFAULT_TA = "hw1.isone.me.versant.keene.spruce.ta"
TZ = "America/New_York"


def connect() -> psycopg.Connection:
    url = os.environ["GJK_DB_URL"].replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(url)


def channel_filter(args) -> tuple[str, list]:
    clauses, params = [], []
    for ch in args.channel or []:
        clauses.append("rc.name = %s")
        params.append(ch)
    for pat in args.like or []:
        clauses.append("rc.name LIKE %s")
        params.append(pat)
    where = f"({' OR '.join(clauses)})" if clauses else "TRUE"
    return where, params


def window_filter(args) -> tuple[str, list]:
    clauses, params = [], []
    if args.start:
        clauses.append("r.timestamp >= %s::timestamp AT TIME ZONE %s")
        params += [args.start, TZ]
    if args.end:
        clauses.append("r.timestamp < %s::timestamp AT TIME ZONE %s")
        params += [args.end, TZ]
    return " AND ".join(clauses) or "TRUE", params


def run(sql: str, params: list) -> list[tuple]:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["inventory", "buckets", "raw", "gaps"])
    ap.add_argument("--ta", default=DEFAULT_TA)
    ap.add_argument("--channel", action="append")
    ap.add_argument("--like", action="append")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--bucket", default="15 minutes")
    args = ap.parse_args()

    chw, chp = channel_filter(args)
    ww, wp = window_filter(args)
    base_where = f"rc.terminal_asset_alias = %s AND {chw}"
    base_params = [args.ta] + chp

    if args.mode == "inventory":
        rows = run(
            f"""
            SELECT rc.name, rc.unit, count(r.value),
                   min(r.timestamp) AT TIME ZONE %s,
                   max(r.timestamp) AT TIME ZONE %s
            FROM gridworks.reading_channels rc
            LEFT JOIN gridworks.readings r ON r.channel_id = rc.id AND {ww}
            WHERE {base_where}
            GROUP BY rc.name, rc.unit ORDER BY rc.name
            """,
            [TZ, TZ] + wp + base_params,
        )
        print("channel,unit,n,first_et,last_et")
        for r in rows:
            print(",".join(str(x) for x in r))
    elif args.mode == "buckets":
        rows = run(
            f"""
            SELECT time_bucket(%s, r.timestamp) AT TIME ZONE %s AS bucket_et,
                   rc.name, round(avg(r.value), 1), max(r.value), count(*)
            FROM gridworks.readings r
            JOIN gridworks.reading_channels rc ON rc.id = r.channel_id
            WHERE {base_where} AND {ww}
            GROUP BY bucket_et, rc.name ORDER BY bucket_et, rc.name
            """,
            [args.bucket, TZ] + base_params + wp,
        )
        print("bucket_et,channel,avg,max,n")
        for r in rows:
            print(",".join(str(x) for x in r))
    elif args.mode == "raw":
        rows = run(
            f"""
            SELECT r.timestamp AT TIME ZONE %s, rc.name, r.value
            FROM gridworks.readings r
            JOIN gridworks.reading_channels rc ON rc.id = r.channel_id
            WHERE {base_where} AND {ww}
            ORDER BY r.timestamp
            """,
            [TZ] + base_params + wp,
        )
        print("timestamp_et,channel,value")
        for r in rows:
            print(",".join(str(x) for x in r))
    elif args.mode == "gaps":
        rows = run(
            f"""
            WITH t AS (
                SELECT rc.name, r.timestamp AS ts,
                       lag(r.timestamp) OVER (PARTITION BY rc.name ORDER BY r.timestamp) AS prev
                FROM gridworks.readings r
                JOIN gridworks.reading_channels rc ON rc.id = r.channel_id
                WHERE {base_where} AND {ww}
            ),
            med AS (
                SELECT name,
                       percentile_cont(0.5) WITHIN GROUP (
                           ORDER BY extract(epoch FROM ts - prev)) AS med_s
                FROM t WHERE prev IS NOT NULL GROUP BY name
            )
            SELECT t.name, t.prev AT TIME ZONE %s, t.ts AT TIME ZONE %s,
                   round((extract(epoch FROM t.ts - t.prev) / 60)::numeric, 1)
            FROM t JOIN med ON med.name = t.name
            WHERE t.prev IS NOT NULL
              AND extract(epoch FROM t.ts - t.prev)
                  > greatest(600, 3 * med.med_s)
            ORDER BY t.prev
            """,
            base_params + wp + [TZ, TZ],
        )
        print("channel,gap_start_et,gap_end_et,gap_minutes")
        for r in rows:
            print(",".join(str(x) for x in r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
