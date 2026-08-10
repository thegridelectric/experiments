#!/usr/bin/env python3
"""Pull GridWorks scada data from the journal archive as sema.

THE DATABASE IS STORAGE, NOT TRUTH. Three stages:

 1. CHANNELS AS WORDS — fetch the terminal asset's scada-emitted
    layout.lite from the journal DB (gridworks.messages, latest
    at-or-before the window end), decode it through the vendored
    snapshot codec, and take the channel words (data.channel.gt /
    derived.channel.gt) from it, upgraded to their current versions.
    The S3 eventstore (the deep archive, which also carries message
    types the journal does not) is consulted by hand only when the
    journal cannot answer.
 2. VALUES FROM THE DB — readings rows for those channels over the
    window: values and timestamps only. The DB's unit column is never
    believed; it is checked against each word as a drift tripwire.
 3. ASSEMBLY — one gw.readings instance per pull, written as
    <ta>-gw.readings-000.json (dash-separated fields, each internally
    LeftRightDot), plus a human CSV derived from the instance with
    natural-unit floats via display.py's single conversion mechanism.

Env: GJK_DB_URL in experiments/.env (use read-only credentials when
available).

Usage:
  uv run python pull_readings.py \
      --ta hw1.isone.me.versant.keene.spruce.ta \
      --like 'zone%gw-temp' --channel hp-lwt --channel primary-flow \
      --start '2026-07-26 00:00' --end '2026-08-03 00:00' \
      --out 2026-07-30-spruce-no-cool-postmortem
"""

import argparse
import csv
import datetime
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
from pydantic import TypeAdapter

sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent))

import unit_encodings  # noqa: E402
from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.property_format import (  # noqa: E402
    LeftRightDot,
    SpaceheatName,
    UTCMilliseconds,
)
from gwexp.sema.types import (  # noqa: E402
    ChannelReadings,
    DataChannelGt,
    DerivedChannelGt,
    GwReadings,
    LayoutLite,
)
from gwexp.sema.types.old_versions.layout_lite_012 import LayoutLite012  # noqa: E402
from naming import validate_lrd  # noqa: E402
from unit_encodings import word_encoding  # noqa: E402

_SPACEHEAT = TypeAdapter(SpaceheatName)

HERE = Path(__file__).parent

ET = ZoneInfo("America/New_York")


def db_url() -> str:
    for line in (HERE / ".env").read_text().splitlines():
        if line.startswith("GJK_DB_URL="):
            return line.split("=", 1)[1].strip().strip("'\"").replace(
                "postgresql+psycopg://", "postgresql://"
            )
    raise SystemExit("GJK_DB_URL not found in experiments/.env")


def et_ms(s: str) -> UTCMilliseconds:
    return int(
        datetime.datetime.fromisoformat(s).replace(tzinfo=ET).timestamp() * 1000
    )


def fetch_layout_channels(ta: LeftRightDot, end_ms: int, codec: SemaCodec):
    """Stage 1: channel words from the scada's own emitted layout.lite,
    latest at-or-before the window end, from the journal DB."""
    scada_alias = ta.removesuffix(".ta") + ".scada"
    with psycopg.connect(db_url()) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload,
                       (EXTRACT(EPOCH FROM timestamp) * 1000)::bigint
                FROM gridworks.messages
                WHERE message_type_name = 'layout.lite'
                  AND from_alias = %s
                  AND timestamp <= to_timestamp(%s / 1000.0)
                ORDER BY timestamp DESC LIMIT 1
                """,
                (scada_alias, end_ms),
            )
            row = cur.fetchone()
    if row is None:
        raise SystemExit(
            f"no layout.lite from {scada_alias} at-or-before the window end "
            f"in the journal DB. If the window predates journal retention "
            f"and the layout matters, fetch the emission from the S3 "
            f"eventstore by hand."
        )
    payload, emitted_ms = row
    layout = codec.from_dict(payload, auto_upgrade=False)
    assert isinstance(layout, (LayoutLite, LayoutLite012))
    words = {}
    for ch in list(layout.data_channels) + list(layout.derived_channels):
        current = codec.from_dict(ch.to_dict())  # upgrade to latest version
        assert isinstance(current, (DataChannelGt, DerivedChannelGt))
        words[current.name] = current
    emitted = datetime.datetime.fromtimestamp(emitted_ms / 1000, tz=ET)
    print(
        f"channels from {scada_alias} layout.lite emitted "
        f"{emitted:%Y-%m-%d %H:%M} ET\n"
        f"  ({payload['TypeName']}/{payload['Version']}, "
        f"{len(words)} channel words)"
    )
    return words


def fetch_readings(ta: LeftRightDot, names: list[SpaceheatName],
                   likes: list[str],  # SQL LIKE patterns ('%'), not names
                   start_ms: int, end_ms: int):
    """Stage 2: values + timestamps from the DB, nothing else."""
    clauses, params = [], []
    for n in names:
        clauses.append("rc.name = %s")
        params.append(n)
    for pat in likes:
        clauses.append("rc.name LIKE %s")
        params.append(pat)
    where = f"({' OR '.join(clauses)})" if clauses else "TRUE"
    q = f"""
        SELECT rc.name, rc.unit,
               (EXTRACT(EPOCH FROM r.timestamp) * 1000)::bigint, r.value
        FROM gridworks.readings r
        JOIN gridworks.reading_channels rc ON r.channel_id = rc.id
        WHERE rc.terminal_asset_alias = %s AND {where}
          AND r.timestamp >= to_timestamp(%s / 1000.0)
          AND r.timestamp <  to_timestamp(%s / 1000.0)
        ORDER BY rc.name, r.timestamp
    """
    rows_by_channel: dict[SpaceheatName, list[tuple[UTCMilliseconds, int]]] = {}
    db_units: dict[SpaceheatName, str] = {}  # the DB's unit column: an
    # untrusted string by design — checked against the word, never believed
    with psycopg.connect(db_url()) as conn, conn.cursor() as cur:
        cur.execute(q, [ta, *params, start_ms, end_ms])
        for name, unit, t_ms, value in cur:
            rows_by_channel.setdefault(name, []).append((t_ms, value))
            db_units[name] = unit
    return rows_by_channel, db_units


def write_display_csv(pull: GwReadings, csv_path: Path) -> None:
    """Stage 3: the human CSV, derived FROM the instance — natural-unit
    floats via display.py, encodings taken from the carried channel
    words. Needs nothing but the instance."""
    by_name = {c.name: c for c in pull.channels}
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp_et", "channel", "value", "display_unit"])
        for cr in pull.channel_readings_list:
            encoding = word_encoding(by_name[cr.channel_name])
            for t_ms, v in zip(cr.scada_read_time_unix_ms_list, cr.value_list):
                t = datetime.datetime.fromtimestamp(t_ms / 1000, tz=ET)
                value, unit = unit_encodings.to_display(v, encoding)
                w.writerow([t.strftime("%Y-%m-%d %H:%M:%S"), cr.channel_name,
                            value, unit])
    print(f"wrote {csv_path}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--display-from", metavar="INSTANCE_JSON",
                   help="regenerate the display CSV from an existing "
                        "gw.readings instance (no DB or S3 access)")
    p.add_argument("--ta")
    p.add_argument("--channel", action="append", default=[])
    p.add_argument("--like", action="append", default=[])
    p.add_argument("--start", help="ET, e.g. '2026-07-26 00:00'")
    p.add_argument("--end")
    p.add_argument("--out", help="output directory")
    p.add_argument("--condition", help="optional condition field for the "
                   "instance filename (LeftRightDot), e.g. 'pre.floor2.removal'")
    args = p.parse_args()

    if args.display_from:
        inst_path = Path(args.display_from)
        pull = SemaCodec().from_dict(json.loads(inst_path.read_text()),
                                     expect=GwReadings)
        write_display_csv(pull, inst_path.with_name(inst_path.stem + "-display.csv"))
        return
    for req in ("ta", "start", "end", "out"):
        if getattr(args, req) is None:
            p.error(f"--{req} is required unless --display-from is used")

    # Boundary validation: the TA is a LeftRightDot alias, the condition a
    # LeftRightDot filename field, each --channel a SpaceheatName; --like
    # values are SQL patterns and stay free-form.
    validate_lrd(args.ta)
    if args.condition:
        validate_lrd(args.condition)
    for name in args.channel:
        _SPACEHEAT.validate_python(name)

    start_ms, end_ms = et_ms(args.start), et_ms(args.end)
    codec = SemaCodec()

    words = fetch_layout_channels(args.ta, end_ms, codec)
    rows, db_units = fetch_readings(
        args.ta, args.channel, args.like, start_ms, end_ms
    )

    channels, readings_list = [], []
    for name in sorted(rows):
        if name not in words:
            print(f"WARNING: no channel word for {name!r} in the layout — "
                  f"excluded ({len(rows[name])} readings dropped)")
            continue
        word = words[name]
        expected = word_encoding(word)
        if db_units.get(name) != expected:
            print(f"WARNING: unit drift tripwire on {name!r}: DB says "
                  f"{db_units.get(name)!r}, the word says {expected!r}")
        channels.append(word)
        readings_list.append(ChannelReadings(
            channel_name=name,
            value_list=[v for _, v in rows[name]],
            scada_read_time_unix_ms_list=[t for t, _ in rows[name]],
        ))

    pull = GwReadings(
        ta_alias=args.ta,
        start_unix_ms=start_ms,
        end_unix_ms=end_ms,
        channels=channels,
        channel_readings_list=readings_list,
    )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    condition = f"{args.condition}-" if args.condition else ""
    stem = f"{args.ta}-{condition}gw.readings-000"
    inst_path = out_dir / f"{stem}.json"
    inst_path.write_text(json.dumps(pull.to_dict(), indent=1) + "\n")
    n = sum(len(r.value_list) for r in readings_list)
    print(f"wrote {inst_path} ({len(channels)} channels, {n} readings)")

    write_display_csv(pull, out_dir / f"{stem}-display.csv")


if __name__ == "__main__":
    main()
