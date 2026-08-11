#!/usr/bin/env python3
"""Emit sema-typed instances for the 2026-08-11 spruce window.

Instances:
  instances/2026-08-11-spruce-window/gw.experiment.run-000.json
  instances/2026-08-11-spruce-window/<channel>-spruce.window.8sps.1hz-gw.channel.noise.stats-000.json
      x8 — the four zone -gw-microvolts and four -gw-temp channels,
      computed from the per-sample series in the window's report.event

Instances are constructed THROUGH the generated sema snapshot
(src/gwexp/sema) so schema and axioms validate at construction — never
as hand-built dicts. Source is the archived persister events in
events-2026-08-11/ (the window scada's own record, copied verbatim off
the box): the startup event opens the run, the last comm event closes
it (a wait_for-bounded stop raises no shutdown event — the 07-30
postmortem-style SIGTERM path never runs), and the single report.event
carries the per-sample series. The deployed scada's own 09:39 shutdown
event in the same archive is excluded by its pre-startup timestamp.
"""

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE.parent))

from gwexp.sema.types import GwChannelNoiseStats, GwExperimentRun  # noqa: E402
from naming import spaceheat_name_to_lrd_token  # noqa: E402

EVENTS = HERE / "events-2026-08-11"
OUT = HERE / "instances" / "2026-08-11-spruce-window"
CONDITION = "spruce-window-8sps-1hz"
# the spruce layout's zone channels are data.channel.gt/003
# (output/spruce/gw.nolan.layout.json in tlayouts)
CHANNEL_TYPE, CHANNEL_VERSION = "data.channel.gt", "003"


def load_events() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(EVENTS.glob("*.json"))]


def window_bounds(events: list[dict]) -> tuple[int, int]:
    start = next(
        e["TimeCreatedMs"] for e in events
        if e["TypeName"] == "gridworks.event.startup"
    )
    end = max(e["TimeCreatedMs"] for e in events if e["TimeCreatedMs"] >= start)
    return start, end


def zone_series(events: list[dict]) -> dict[str, list[tuple[int, int]]]:
    series: dict[str, list[tuple[int, int]]] = {}
    for e in events:
        if e["TypeName"] != "report.event":
            continue
        for ch in e["Report"]["ChannelReadingList"]:
            name = ch["ChannelName"]
            if not (name.startswith("zone") and "-gw-" in name):
                continue
            pts = series.setdefault(name, [])
            pts += zip(ch["ScadaReadTimeUnixMsList"], ch["ValueList"])
    return {k: sorted(v) for k, v in series.items()}


def write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj.to_dict(), indent=1) + "\n")
    print(f"wrote {path.relative_to(HERE)}")


def main() -> None:
    events = load_events()
    start, end = window_bounds(events)
    run = GwExperimentRun(
        experiment_slug="ads-declared-rate",
        host_g_node_alias="hw1.isone.me.versant.keene.spruce.scada",
        start_unix_ms=start,
        end_unix_ms=end,
        code_ref="window_boot.py",
    )
    write(OUT / "gw.experiment.run-000.json", run)

    condition_token = spaceheat_name_to_lrd_token(CONDITION)
    for name, pts in sorted(zone_series(events).items()):
        vals = [v for _, v in pts]
        stats = GwChannelNoiseStats(
            channel_name=name,
            channel_type_name=CHANNEL_TYPE,
            channel_version=CHANNEL_VERSION,
            condition_label=CONDITION,
            window_start_unix_ms=pts[0][0],
            window_end_unix_ms=pts[-1][0],
            num_samples=len(vals),
            mean=round(statistics.mean(vals), 1),
            sd=round(statistics.stdev(vals), 1),
            p2p=float(max(vals) - min(vals)),
        )
        token = spaceheat_name_to_lrd_token(name)
        write(
            OUT / f"{token}-{condition_token}-gw.channel.noise.stats-000.json",
            stats,
        )


if __name__ == "__main__":
    main()
