#!/usr/bin/env python3
"""Emit sema-typed instances for the spruce no-cool postmortem.

  instances/gw.experiment.run-000.json                       the analysis window
  instances/<channel>-gw.channel.jump.stats-000.json x4      zone-channel jump
                                                             stats over the window

Everything derives from the folder's own gw.readings instance, decoded
through the vendored snapshot: the channel words come from it typed
(never re-read as dicts), and the microvolt readings the jump stats are
computed from are its channel.readings. Run via
`uv run python emit_instances.py` from the repo env.
"""

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE.parent))

from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.types import (  # noqa: E402
    GwChannelJumpStats,
    GwExperimentRun,
    GwReadings,
)
from naming import spaceheat_name_to_lrd_token  # noqa: E402

PULL_PATH = HERE / "hw1.isone.me.versant.keene.spruce.ta-gw.readings-000.json"

# HAND-CODED because no deployed sema layout declares zone sensing
# modality yet: spruce's thermistor-sensed zones (zone5-living-rm-fancoil
# is opto-only — no thermistor, no ADS channel — and deliberately absent).
# When the sema layout (gw.nolan.layout / gw1.hvac.zone) deploys with
# per-zone sensing declared, replace this list with a layout query.
THERMISTOR_ZONE_CHANNELS = [
    "zone1-bedrooms-gw-microvolts",
    "zone2-living-rm-gw-microvolts",
    "zone3-upstairs-gw-microvolts",
    "zone4-garage-gw-microvolts",
]

JUMP_THRESHOLD_UV = 50_000
MAX_GAP_S = 300


def load_pull() -> GwReadings:
    return SemaCodec().from_dict(json.loads(PULL_PATH.read_text()),
                                 expect=GwReadings)


def run_instance(pull: GwReadings) -> GwExperimentRun:
    return GwExperimentRun(
        experiment_slug="spruce-no-cool-postmortem",
        host_g_node_alias=pull.ta_alias.removesuffix(".ta") + ".scada",
        start_unix_ms=pull.start_unix_ms,
        end_unix_ms=pull.end_unix_ms,
        code_ref="pull_readings.py",
    )


def jump_stats(pull: GwReadings, name: str) -> GwChannelJumpStats:
    """Jump statistics for one channel over the pull's window: count
    consecutive-reading jumps above JUMP_THRESHOLD_UV (ignoring pairs
    more than MAX_GAP_S apart — a jump across a reporting gap is a gap
    artifact, not a spike). The stats pair with the channel's own word
    from the pull (ChannelTypeName/ChannelVersion) and speak its
    serialized units."""
    word = next(c for c in pull.channels if c.name == name)
    readings = next(r for r in pull.channel_readings_list
                    if r.channel_name == name)
    pairs = list(zip(readings.scada_read_time_unix_ms_list,
                     readings.value_list))
    jumps = [abs(v1 - v0) for (t0, v0), (t1, v1) in zip(pairs, pairs[1:])
             if (t1 - t0) / 1000 < MAX_GAP_S]
    return GwChannelJumpStats(
        channel_name=name,
        channel_type_name=word.type_name,
        channel_version=word.version,
        window_start_unix_ms=pull.start_unix_ms,
        window_end_unix_ms=pull.end_unix_ms,
        num_readings=len(pairs),
        jump_threshold=JUMP_THRESHOLD_UV,
        max_gap_s=MAX_GAP_S,
        spike_count=sum(1 for j in jumps if j > JUMP_THRESHOLD_UV),
        max_abs_jump=max(jumps) if jumps else 0,
        median_abs_jump=float(statistics.median(jumps)) if jumps else 0.0,
    )


def write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj.to_dict(), indent=1) + "\n")
    print(f"wrote {path.relative_to(HERE)}")


def main() -> None:
    pull = load_pull()
    write(HERE / "instances/gw.experiment.run-000.json", run_instance(pull))
    # FRAGILE INFERENCE, documented: nothing semantic marks a channel as
    # ADS-thermistor-backed — the "-gw-microvolts" name suffix is a
    # naming convention, and THERMISTOR_ZONE_CHANNELS (top of file)
    # rests on it. A sema layout with per-zone sensing retires both.
    for name in THERMISTOR_ZONE_CHANNELS:
        j = jump_stats(pull, name)
        write(HERE / f"instances/{spaceheat_name_to_lrd_token(j.channel_name)}-gw.channel.jump.stats-000.json", j)


if __name__ == "__main__":
    main()
