"""The scada's persisted report.events for a window, as sema instances
under the instance grammar (<scada alias>-<run>.<HHMM>-report.event-<ver>.json),
and the five-v-boss digest they carry: the boss, cycler, roster and
vdc-relay state rows, and every fsm.full.report with its TriggerId.
Every file is decoded through the gwexp sema snapshot; the digest reads
typed fields.

    uv run python collect_events.py collect <run> <start ET HH:MM> <end ET HH:MM> <event-dir>
    uv run python collect_events.py digest instances/*.json

<event-dir> is a local copy of the scada's pending-event dir for the day
(`~/.local/share/gridworks/<paths root>/event/<date>T00:00:00+00:00/`;
from a box, scp it to the laptop first).
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.types import ReportEvent  # noqa: E402

ET = timezone(timedelta(hours=-4))
NAMES = ("five-v-boss", "pico-cycler", "vdc-relay", "buffer", "tank1", "fancoil", "floor1", "pipes1")


def digest(event: ReportEvent, label: str) -> None:
    stamp = datetime.fromtimestamp(event.time_created_ms / 1000, ET)
    print(f"== {stamp:%H:%M:%S} ET  slot {event.report.slot_start_unix_s}  {label}")
    for m in event.report.state_list:
        if m.machine_handle.split(".")[-1] in NAMES:
            times = [f"{datetime.fromtimestamp(u / 1000, ET):%H:%M:%S.%f}"[:-3] for u in m.unix_ms_list]
            print(f"   {m.machine_handle:36} {list(zip(m.state_list, times))}")
    for x in event.report.fsm_report_list:
        print(f"   fsm.full.report {x.from_name} trigger={x.trigger_id} "
              + " ".join(f"{a.event}:{a.from_state}->{a.to_state}" for a in x.atomic_list))


def collect(codec: SemaCodec, run: str, start: str, end: str, event_dir: Path) -> None:
    day = date.today()
    lo = datetime.combine(day, datetime.strptime(start, "%H:%M").time(), ET).astimezone(timezone.utc)
    hi = datetime.combine(day, datetime.strptime(end, "%H:%M").time(), ET).astimezone(timezone.utc)
    out = HERE / "instances"
    out.mkdir(exist_ok=True)
    for f in sorted(event_dir.glob("*.json")):
        stamp = datetime.fromisoformat(f.name[:32])
        if not lo <= stamp <= hi:
            continue
        decoded = codec.from_file(f)
        if not isinstance(decoded, ReportEvent):
            continue
        dst = out / f"{decoded.src}-{run}.{stamp.astimezone(ET):%H%M}-report.event-{decoded.version}.json"
        dst.write_text(json.dumps(decoded.to_dict()))
        digest(decoded, str(dst.relative_to(HERE)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)
    c = sub.add_parser("collect")
    c.add_argument("run")
    c.add_argument("start")
    c.add_argument("end")
    c.add_argument("event_dir", type=Path)
    d = sub.add_parser("digest")
    d.add_argument("instances", nargs="+", type=Path)
    args = parser.parse_args()
    codec = SemaCodec()
    if args.mode == "digest":
        for p in args.instances:
            digest(codec.from_file(p, expect=ReportEvent), str(p))
    else:
        collect(codec, args.run, args.start, args.end, args.event_dir)


if __name__ == "__main__":
    main()
