#!/usr/bin/env python3
"""Quick spot-check on fleet journal data — report back, leave no trace.

A spot-check answers a fast question about a house ("did the sieg loop go to
full send every time the heat pump turned on last night?") straight from the
journal DB. Unlike an experiment, a spot-check produces NOTHING durable in
this repo: no folder, no instance, no logbook line, no changelog. This script
and the recipe beside it (spot-check-recipe.md) are the only committed
artifacts; every run just prints to your terminal.

Why this reads report.event and not pull_readings.py: the state machines you
usually care about (gw1.sieg.control.state, gw1.hp.boss.state, relay states)
are NOT a journaled message type of their own — they ride inside report.event
payloads (Report.StateList), alongside the numeric channels
(Report.ChannelReadingList). One query gets both. pull_readings.py pulls only
gridworks.readings (numeric), and applies natural-unit conversion; use it when
you want calibrated °F / gpm. This tool reports RAW wire-encoded values.

Env: GJK_DB_URL in experiments/.env (read-only credentials preferred).

Usage:
  # what states and channels exist in the window (default when neither
  # --states nor --channels is given):
  uv run python spot_check.py --house maple \
      --start '2026-09-21 18:00' --end '2026-09-22 08:00'

  # state-machine transitions (collapsed to change-points), ET timestamps:
  uv run python spot_check.py --house maple --start ... --end ... \
      --states gw1.sieg.control.state gw1.hp.boss.state

  # numeric channel summaries (--raw for every sample), RAW wire values:
  uv run python spot_check.py --house maple --start ... --end ... \
      --channels sieg-send hp-odu-pwr --raw

  # a house not in KNOWN_HOUSES: pass the full scada alias yourself.
  uv run python spot_check.py --scada d1.isone.ver.keene.elm.scada --start ... --end ...
"""
import argparse
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg

HERE = Path(__file__).parent
ET = ZoneInfo("America/New_York")

# The house -> scada-alias lookup the fleet otherwise lacks: no single
# canonical table exists; the authority is the per-house tlayouts/<house>_gen.py
# (each declares its own GNode aliases), so this map is the consolidated
# convenience. Universe is segment 0 (hw1 = production, d1 = dev/sim/bench).
# This map is the source of truth for the recipe's table — regenerate both from
# `grep -rhoE '"(hw1|d1)\.[a-z0-9.]+\.scada"' tlayouts/*_gen.py` when tlayouts
# gains a house. Membership here does NOT mean the box is currently emitting
# (a silent box just yields zero reports). For anything unlisted, pass --scada.
KNOWN_HOUSES = {
    # Keene production houses (hw1)
    "maple": "hw1.isone.me.versant.keene.maple.scada",
    "oak": "hw1.isone.me.versant.keene.oak.scada",
    "spruce": "hw1.isone.me.versant.keene.spruce.scada",
    "beech": "hw1.isone.me.versant.keene.beech.scada",
    "elm": "hw1.isone.me.versant.keene.elm.scada",
    "fir": "hw1.isone.me.versant.keene.fir.scada",
    # dev / sim / bench (d1)
    "spruce-sim": "d1.isone.me.versant.keene.spruce.scada",
    "honeysuckle": "d1.bench.honeysuckle.scada",
    "orange1": "d1.isone.ct.newhaven.orange1.scada",
    "willow1": "d1.isone.ct.newhaven.willow1.scada",
}


def db_url() -> str:
    for line in (HERE / ".env").read_text().splitlines():
        if line.startswith("GJK_DB_URL="):
            return (line.split("=", 1)[1].strip().strip("'\"")
                    .replace("postgresql+psycopg://", "postgresql://"))
    raise SystemExit("GJK_DB_URL not found in experiments/.env")


def et_ms(s: str) -> int:
    return int(datetime.datetime.fromisoformat(s).replace(tzinfo=ET).timestamp() * 1000)


def et_str(ms: int) -> str:
    return datetime.datetime.fromtimestamp(ms / 1000, tz=ET).strftime("%m-%d %H:%M:%S")


def collapse(series):
    """Sampled [(ms, value)] -> change-points only (first + each transition)."""
    out, last = [], object()
    for t, v in sorted(set(series)):
        if v != last:
            out.append((t, v))
            last = v
    return out


def fetch_reports(scada: str, start_ms: int, end_ms: int):
    with psycopg.connect(db_url()) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(
                """SELECT payload FROM gridworks.messages
                   WHERE from_alias = %s AND message_type_name = 'report.event'
                     AND timestamp >= to_timestamp(%s / 1000.0)
                     AND timestamp <  to_timestamp(%s / 1000.0)
                   ORDER BY timestamp""",
                (scada, start_ms, end_ms),
            )
            return [row[0]["Report"] for row in cur.fetchall()]


def main() -> None:
    ap = argparse.ArgumentParser(description="Quick fleet spot-check (prints only).")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--house", choices=sorted(KNOWN_HOUSES))
    g.add_argument("--scada", help="full scada GNode alias, for houses not in KNOWN_HOUSES")
    ap.add_argument("--list-houses", action="store_true",
                    help="print the KNOWN_HOUSES map and exit")
    ap.add_argument("--start", help="ET, e.g. '2026-09-21 18:00'")
    ap.add_argument("--end", help="ET")
    ap.add_argument("--states", nargs="*", metavar="ENUM",
                    help="state enums to print transitions for, or 'all'")
    ap.add_argument("--channels", nargs="*", metavar="NAME",
                    help="numeric channels to summarize, or 'all'")
    ap.add_argument("--raw", action="store_true",
                    help="with --channels: print every sample, not just a summary")
    args = ap.parse_args()

    if args.list_houses:
        print("KNOWN_HOUSES (nickname -> scada alias):")
        for name, alias in KNOWN_HOUSES.items():
            print(f"  {name:14s} {alias}")
        return

    scada = args.scada or (args.house and KNOWN_HOUSES[args.house])
    if not scada:
        ap.error("pass --house or --scada (or --list-houses)")
    if not args.start or not args.end:
        ap.error("--start and --end are required")
    start_ms, end_ms = et_ms(args.start), et_ms(args.end)

    reports = fetch_reports(scada, start_ms, end_ms)
    print(f"{scada}\n  {args.start} -> {args.end} ET   ({len(reports)} report.event)")
    if not reports:
        return

    # index states by enum, numerics by channel
    state_series: dict[tuple[str, str], list] = {}
    num_series: dict[str, list] = {}
    for rep in reports:
        for s in rep.get("StateList", []):
            key = (s["StateEnum"], s["MachineHandle"])
            state_series.setdefault(key, []).extend(
                zip(s["UnixMsList"], s["StateList"]))
        for c in rep.get("ChannelReadingList", []):
            num_series.setdefault(c["ChannelName"], []).extend(
                zip(c["ScadaReadTimeUnixMsList"], c["ValueList"]))

    want_states = args.states is not None
    want_channels = args.channels is not None
    if not want_states and not want_channels:  # default: list what's available
        print("\n== state machines (enum @ handle : transitions) ==")
        for (se, mh), pts in sorted(state_series.items()):
            print(f"  {len(collapse(pts)):4d}  {se} @ {mh}")
        print("\n== numeric channels (samples) ==")
        for ch, pts in sorted(num_series.items()):
            print(f"  {len(pts):5d}  {ch}")
        return

    if want_states:
        picks = (sorted(state_series) if args.states in ([], ["all"])
                 else [k for k in state_series if k[0] in args.states])
        for key in picks:
            se, mh = key
            print(f"\n== {se} @ {mh} : transitions ==")
            for t, v in collapse(state_series[key]):
                print(f"   {et_str(t)}  {v}")

    if want_channels:
        picks = (sorted(num_series) if args.channels in ([], ["all"]) else
                 [c for c in num_series if c in args.channels])
        for ch in picks:
            pts = sorted(num_series[ch])
            vals = [v for _, v in pts]
            print(f"\n== {ch} : {len(pts)} samples (RAW wire values) ==")
            print(f"   min={min(vals)} max={max(vals)} "
                  f"first={et_str(pts[0][0])}={pts[0][1]} "
                  f"last={et_str(pts[-1][0])}={pts[-1][1]}")
            if args.raw:
                for t, v in pts:
                    print(f"   {et_str(t)}  {v}")


if __name__ == "__main__":
    main()
