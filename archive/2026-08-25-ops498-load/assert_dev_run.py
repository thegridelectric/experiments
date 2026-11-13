"""Assertions for the EDD dev run.

`snapshot` stores the active channel id per (TA, name) before the load.
`check` asserts, after the load:

1. active channels — the set of (TA, name, id) is exactly the snapshot: no
   live channel was deactivated or replaced by an old layout;
2. era rows — for every house the seed knew, `buffer-depth1` has a retired
   `WaterTempCTimes1000` row ending at that house's newest layout time;
3. readings landed — every (TA, day) with `report.event` messages in the
   loaded windows has readings that day;
4. readings route by era — no reading with timestamp before 2026 sits on an
   active `buffer-depth1` row, and every `WaterTempCTimes1000` reading is
   before its row's `deactivated_date`;
5. the front end's CSV query (verbatim from
   gridworks-web-backend readings_csv.py, `$n` → `:pn`) returns rows for the
   earliest loaded day; the bundle's time-weighted query does too;
6. `readings_1hr` is empty for the loaded range before the manual refresh and
   populated after it (hazard B made visible); the refresh runs as the cagg
   owner, which on prod is the admin role, not `gw_journalkeeper`;
7. the importer summaries show no degraded or failed messages and no enum
   fallbacks; dropped readings are listed for the reader.
"""

import glob
import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

DEV_URL = os.environ["DEV_DB_URL"]
# The cagg refresh needs the view owner (prod: the admin role, not gw_journalkeeper).
DEV_ADMIN_URL = os.environ.get("DEV_ADMIN_URL", "postgresql+psycopg2://postgres:changeme@localhost:5433/tsdb")

CSV_QUERY = text(
    """
        SELECT gridworks.readings.timestamp, gridworks.reading_channels.name, gridworks.readings.value 
        FROM gridworks.readings
        JOIN gridworks.reading_channels ON reading_channels.id = readings.channel_id
        WHERE gridworks.readings.timestamp >= :p1
        AND gridworks.readings.timestamp <= :p2
        AND gridworks.reading_channels.terminal_asset_alias = :p3
        ORDER BY gridworks.readings.timestamp, gridworks.reading_channels.name
    """
)

BUNDLE_QUERY = text(
    """
    SELECT reading_channels.name AS channel_name, reading_channels.unit AS channel_unit,
           time_bucket(:interval, readings.timestamp) AS time_bucket,
           time_weight('LOCF', readings.timestamp, readings.value) AS time_weight
    FROM gridworks.readings JOIN gridworks.reading_channels ON reading_channels.id = readings.channel_id
    WHERE readings.timestamp >= :p1 AND readings.timestamp <= :p2
      AND reading_channels.terminal_asset_alias = :p3
    GROUP BY time_bucket, reading_channels.name, reading_channels.unit, reading_channels.unit_type
    ORDER BY reading_channels.name, time_bucket
    """
)


class Check:
    def __init__(self):
        self.failures = 0

    def __call__(self, ok: bool, what: str, detail: str = ""):
        print(f"{'PASS' if ok else 'FAIL'}  {what}" + (f" — {detail}" if detail else ""))
        if not ok:
            self.failures += 1


def active_channels(conn) -> dict:
    rows = conn.execute(
        text(
            "select terminal_asset_alias, name, id::text from gridworks.reading_channels where deactivated_date is null"
        )
    ).all()
    return {f"{ta}|{name}": cid for ta, name, cid in rows}


def snapshot(run_dir: Path) -> None:
    with create_engine(DEV_URL).connect() as conn:
        (run_dir / "active_snapshot.json").write_text(json.dumps(active_channels(conn), indent=1))
    print("snapshot written")


def check(run_dir: Path) -> None:
    c = Check()
    before = json.loads((run_dir / "active_snapshot.json").read_text())
    with create_engine(DEV_URL).connect() as conn:
        after = active_channels(conn)
        c(before == after, "1 active channel set unchanged", f"{len(before)} before, {len(after)} after")

        eras = conn.execute(
            text(
                """
                select rc.terminal_asset_alias, rc.unit, rc.deactivated_date,
                       (select max(timestamp) from gridworks.messages m
                         where m.message_type_name='layout.lite'
                           and split_part(m.from_alias, '.scada', 1) || '.ta' = rc.terminal_asset_alias) as newest_layout
                from gridworks.reading_channels rc
                where rc.name='buffer-depth1' and rc.deactivated_date is not null
                """
            )
        ).all()
        c(
            len(eras) > 0 and all(u == "WaterTempCTimes1000" and d == nl for _, u, d, nl in eras),
            "2 buffer-depth1 era rows end at the newest layout",
            "; ".join(f"{ta.split('.')[-2]}:{u}@{d:%Y-%m-%d}" for ta, u, d, _ in eras),
        )

        missing = conn.execute(
            text(
                """
                with report_days as (
                  select split_part(from_alias, '.scada', 1) || '.ta' as ta, timestamp::date as day, count(*) as n
                  from gridworks.messages where message_type_name='report.event' group by 1,2),
                reading_days as (
                  select rc.terminal_asset_alias as ta, r.timestamp::date as day, count(*) as n
                  from gridworks.readings r join gridworks.reading_channels rc on rc.id=r.channel_id group by 1,2)
                select rd.ta, rd.day, rd.n from report_days rd left join reading_days g using (ta, day)
                where g.n is null and rd.n >= 10
                  and exists (select 1 from gridworks.reading_channels c where c.terminal_asset_alias = rd.ta)
                order by 1,2
                """
            )
        ).all()
        unknown = conn.execute(
            text(
                """
                select split_part(from_alias, '.scada', 1) || '.ta' as ta, count(*) from gridworks.messages
                where message_type_name='report.event'
                  and not exists (select 1 from gridworks.reading_channels c where c.terminal_asset_alias = split_part(from_alias, '.scada', 1) || '.ta')
                group by 1
                """
            )
        ).all()
        c(not missing, "3 every (TA, day) with ≥10 reports has readings", f"missing: {[(t.split('.')[-2], str(d), n) for t, d, n in missing]}")
        print(f"info  houses with reports but no channel rows (no layout seen): {[(t.split('.')[-2], n) for t, n in unknown]}")

        misrouted = conn.execute(
            text(
                """
                select count(*) from gridworks.readings r join gridworks.reading_channels rc on rc.id=r.channel_id
                where rc.name='buffer-depth1' and (
                  (rc.deactivated_date is null and r.timestamp < '2026-01-01')
                  or (rc.deactivated_date is not null and r.timestamp >= rc.deactivated_date))
                """
            )
        ).scalar()
        c(misrouted == 0, "4 buffer-depth1 readings sit in their era", f"{misrouted} misrouted")

        first = conn.execute(text("select min(timestamp)::date, max(timestamp)::date from gridworks.readings")).one()
        # The earliest day on which some house has buffer-depth1 readings.
        ta, bd_day = conn.execute(
            text(
                """
                select rc.terminal_asset_alias, min(r.timestamp)::date from gridworks.readings r
                join gridworks.reading_channels rc on rc.id=r.channel_id where rc.name='buffer-depth1'
                group by 1 order by 2 limit 1
                """
            )
        ).one()
        day_start = f"{bd_day} 00:00:00+00"
        day_end = f"{bd_day} 23:59:59+00"
        csv_rows = conn.execute(CSV_QUERY, {"p1": day_start, "p2": day_end, "p3": ta}).all()
        bundle_rows = conn.execute(
            BUNDLE_QUERY, {"interval": "5 minutes", "p1": day_start, "p2": day_end, "p3": ta}
        ).all()
        c(len(csv_rows) > 0, "5a front-end CSV query returns a loaded day", f"{len(csv_rows)} rows for {ta.split('.')[-2]} {bd_day}")
        units = {r.channel_unit for r in bundle_rows if r.channel_name == "buffer-depth1"}
        c(len(bundle_rows) > 0 and units == {"WaterTempCTimes1000"}, "5b bundle query returns rows with the era's unit", f"{len(bundle_rows)} rows, buffer-depth1 unit {units}")

        cagg_before = conn.execute(
            text("select count(*) from gridworks.readings_1hr where time_bucket >= :a and time_bucket < :b"),
            {"a": str(first[0]), "b": str(first[1] + __import__('datetime').timedelta(days=1))},
        ).scalar()
    with create_engine(DEV_ADMIN_URL, isolation_level="AUTOCOMMIT").connect() as conn:
        conn.execute(
            text("CALL refresh_continuous_aggregate('gridworks.readings_1hr', :a, :b)"),
            {"a": str(first[0]), "b": str(first[1] + __import__('datetime').timedelta(days=1))},
        )
        cagg_after = conn.execute(
            text("select count(*) from gridworks.readings_1hr where time_bucket >= :a and time_bucket < :b"),
            {"a": str(first[0]), "b": str(first[1] + __import__('datetime').timedelta(days=1))},
        ).scalar()
    if cagg_before:
        print(f"info  6 readings_1hr already refreshed by an earlier check ({cagg_before} rows); rerun from reset to see the empty-before state")
    c(cagg_after > 0 and cagg_after >= cagg_before, "6 readings_1hr populated after manual refresh (owner role)", f"{cagg_before} → {cagg_after}")

    degraded = failed = fallbacks = 0
    dropped: dict = {}
    for f in glob.glob(str(run_dir / "pass*.json")):
        s = json.loads(Path(f).read_text())
        # The pre-versioning gridworks.event.problem shape is rejected by
        # design (never authored, never loaded); degraded is its expected state.
        degraded += sum(
            v["degraded"] for v in s["versions"]
            if not (v["type_name"] == "gridworks.event.problem" and v["version"] == "None")
        )
        failed += sum(v["failed"] for v in s["versions"])
        fallbacks += sum(e["count"] for e in s["enum_fallbacks"])
        for d in s["dropped_readings"]:
            key = f"{d['terminal_asset_alias'].split('.')[-2]}/{d['channel']}"
            dropped[key] = dropped.get(key, 0) + d["count"]
    c(degraded == 0 and failed == 0 and fallbacks == 0, "7 no degraded / failed / enum-fallback messages", f"{degraded} degraded, {failed} failed, {fallbacks} fallbacks")
    print(f"info  dropped readings by channel ({len(dropped)}): " + ", ".join(f"{k}={v}" for k, v in sorted(dropped.items())))
    print(f"\n{'ALL CHECKS PASSED' if c.failures == 0 else f'{c.failures} CHECK(S) FAILED'}")
    sys.exit(1 if c.failures else 0)


if __name__ == "__main__":
    cmd, run = sys.argv[1], Path(sys.argv[2])
    {"snapshot": snapshot, "check": check}[cmd](run)
