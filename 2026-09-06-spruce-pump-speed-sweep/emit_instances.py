#!/usr/bin/env python3
"""Emit the sema-typed instances for the spruce-pump-speed-sweep runs.

For every `sweep-<run>-results.json` in this folder (the driver's typed
result file, generated on spruce) emit `instances/<run>/`:

  <ta>-pump.speed.sweep.<run>-gw.readings-000.json
      the readings the driver recorded on the admin link (secondary-flow,
      secondary-010v and every other channel the snapshots carried), with
      their channel words taken from the archived spruce layout in this
      folder; a `-display.csv` sibling in natural units.
  gw.experiment.run-000.json
      the run's window, host and code ref.

Both are constructed THROUGH the vendored snapshot so schema and axioms
validate at construction. The steps and machine states stay in the results
file (kind-specific structure; the driver names the missing word).
Byte-stable: re-runs reproduce the files.

    uv run python emit_instances.py
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE.parent))

from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.types import (  # noqa: E402
    ChannelReadings,
    DataChannelGt,
    GwExperimentRun,
    GwReadings,
)
from naming import validate_lrd  # noqa: E402
from pull_readings import write_display_csv  # noqa: E402

SLUG = "spruce-pump-speed-sweep"
CONDITION = "pump.speed.sweep"
LAYOUT = HERE / "hw1.isone.me.versant.keene.spruce-gw.nolan.layout-000.json"
CODE_REF = "sweep.py"


def layout_facts(codec: SemaCodec) -> tuple[str, str, dict[str, DataChannelGt]]:
    """(ta alias, scada alias, channel words by name) from the archived layout."""
    raw = json.loads(LAYOUT.read_text())
    aliases = [g["Alias"] for g in raw["GNodes"]]
    ta = validate_lrd(next(a for a in aliases if a.endswith(".ta")))
    scada = validate_lrd(next(a for a in aliases if a.endswith(".scada")))
    words: dict[str, DataChannelGt] = {}
    for ch in raw["DataChannels"]:
        word = codec.from_dict(ch)
        assert isinstance(word, DataChannelGt)
        words[word.name] = word
    return ta, scada, words


def readings_instance(results: dict, ta: str, words: dict[str, DataChannelGt]) -> GwReadings:
    by_channel: dict[str, list[tuple[int, int]]] = {}
    for r in results["Readings"]:
        by_channel.setdefault(r["channel"], []).append((r["unix_ms"], r["value"]))
    channels, readings_list = [], []
    for name in sorted(by_channel):
        if name not in words:
            print(f"WARNING: no channel word for {name!r} in the archived layout; excluded")
            continue
        rows = sorted(by_channel[name])
        channels.append(words[name])
        readings_list.append(ChannelReadings(
            channel_name=name,
            value_list=[v for _, v in rows],
            scada_read_time_unix_ms_list=[t for t, _ in rows],
        ))
    return GwReadings(
        ta_alias=ta,
        start_unix_ms=results["StartUnixMs"],
        end_unix_ms=results["EndUnixMs"],
        channels=channels,
        channel_readings_list=readings_list,
    )


def run_instance(results: dict, scada: str) -> GwExperimentRun:
    return GwExperimentRun(
        experiment_slug=SLUG,
        host_g_node_alias=scada,
        start_unix_ms=results["StartUnixMs"],
        end_unix_ms=results["EndUnixMs"],
        code_ref=CODE_REF,
    )


def main() -> None:
    codec = SemaCodec()
    ta, scada, words = layout_facts(codec)
    for results_path in sorted(HERE.glob("sweep-*-results.json")):
        run = results_path.stem.removeprefix("sweep-").removesuffix("-results")
        results = json.loads(results_path.read_text())
        out_dir = HERE / "instances" / run
        out_dir.mkdir(parents=True, exist_ok=True)
        condition = validate_lrd(f"{CONDITION}.{run}")
        stem = f"{ta}-{condition}-gw.readings-000"
        readings = readings_instance(results, ta, words)
        (out_dir / f"{stem}.json").write_text(json.dumps(readings.to_dict(), indent=1) + "\n")
        write_display_csv(readings, out_dir / f"{stem}-display.csv")
        run_inst = run_instance(results, scada)
        (out_dir / "gw.experiment.run-000.json").write_text(json.dumps(run_inst.to_dict(), indent=1) + "\n")
        n = sum(len(r.value_list) for r in readings.channel_readings_list)
        print(f"wrote instances/{run}/ ({len(readings.channels)} channels, {n} readings; {results['Outcome']})")


if __name__ == "__main__":
    main()
