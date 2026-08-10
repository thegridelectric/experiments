#!/usr/bin/env python3
"""Emit gw.channel.gap.stats instances for the floor2-removal windows.

The semafied successor to pico_gap_analysis.py's SQL pass, for the
floor2-removal before/after question: both windows were pulled from the
journal archive by ../pull_readings.py into validated gw.readings
instances (channel words from the scada's own layout.lite emission);
this emitter derives per-channel reporting-gap statistics from those
instances alone — no database access — and writes them as
gw.channel.gap.stats instances, one per channel per window, under
instances/<condition>/. The house-level roll-up (the verdict numbers)
is printed and lives in the README; it is derivable from the
instances.

Gap definition, unchanged from the first run: a channel's normal
cadence = median inter-report interval; a GAP = an interval >
max(10 min, 3 x median cadence). Windows where ALL pulled channels are
silent together (house / scada / pipeline outage — not pico data) are
excluded per channel and counted in ExcludedGapCount.

Deterministic: ci.sh checks the instances reproduce byte-for-byte.
"""

import json
import statistics
import sys
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE.parent))

from pydantic import TypeAdapter  # noqa: E402

from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.property_format import (  # noqa: E402
    LeftRightDot,
    SpaceheatName,
    UTCSeconds,
)
from gwexp.sema.types import (  # noqa: E402
    ChannelReadings,
    DataChannelGt,
    DerivedChannelGt,
    GwChannelGapStats,
    GwReadings,
)
from naming import spaceheat_name_to_lrd_token  # noqa: E402

_LRD = TypeAdapter(LeftRightDot)
_SPACEHEAT = TypeAdapter(SpaceheatName)
_UTC_S = TypeAdapter(UTCSeconds)

ABS_GAP_S = 600
MEDIAN_MULT = 3.0
HOUSE_OVERLAP_EXCL_FRAC = 0.6

TA = _LRD.validate_python("hw1.isone.me.versant.keene.spruce.ta")
# Filename condition fields, keying the per-window instance folders.
CONDITIONS: list[LeftRightDot] = [
    _LRD.validate_python("pre.floor2.removal"),
    _LRD.validate_python("post.floor2.removal")]
# The feedback loop's protagonist: the secondary-BTU pico's channels.
SECONDARY_BTU_CHANNELS: list[SpaceheatName] = [
    _SPACEHEAT.validate_python(n)
    for n in ("secondary-flow", "secondary-ewt",
              "secondary-lwt", "secondary-pump-ct")]


class HouseSilentWindow(NamedTuple):
    """One window where every pulled channel was silent together —
    a house / scada / pipeline outage, excluded from channel stats.
    Analysis-internal (no word: single consumer); bounds utc.seconds."""
    start_unix_s: UTCSeconds
    end_unix_s: UTCSeconds


def instance_path(condition: LeftRightDot) -> Path:
    return HERE / f"{TA}-{condition}-gw.readings-000.json"


def load_pull(path: Path) -> GwReadings:
    return SemaCodec().from_dict(json.loads(path.read_text()),
                                 expect=GwReadings)


def house_silent_windows(pull: GwReadings) -> list[HouseSilentWindow]:
    """Silences > ABS_GAP_S in the union of all channels' report times:
    everything quiet together is a house-level outage, not pico data."""
    all_ts = sorted({t for cr in pull.channel_readings_list
                     for t in cr.scada_read_time_unix_ms_list})
    return [HouseSilentWindow(start_unix_s=_UTC_S.validate_python(t0 // 1000),
                              end_unix_s=_UTC_S.validate_python(t1 // 1000))
            for t0, t1 in zip(all_ts, all_ts[1:])
            if (t1 - t0) > ABS_GAP_S * 1000]


def house_overlap_frac(gap_start: float, gap_dur: float,
                       hgaps: list[HouseSilentWindow]) -> float:
    """Fraction of a channel gap covered by house-silent windows."""
    g0, g1 = gap_start, gap_start + gap_dur
    cov = sum(max(0.0, min(g1, h.end_unix_s) - max(g0, h.start_unix_s))
              for h in hgaps)
    return cov / gap_dur if gap_dur > 0 else 0.0


def channel_gap_stats(pull: GwReadings, cr: ChannelReadings,
                      word: DataChannelGt | DerivedChannelGt,
                      hgaps: list[HouseSilentWindow]) -> GwChannelGapStats:
    ts = [t / 1000 for t in cr.scada_read_time_unix_ms_list]
    dts = [b - a for a, b in zip(ts, ts[1:])]
    median_dt = statistics.median(dts) if dts else 0.0
    threshold = max(float(ABS_GAP_S), MEDIAN_MULT * median_dt)
    gaps = [(a, dt) for a, dt in zip(ts, dts) if dt > threshold]
    kept = [(s, d) for s, d in gaps
            if house_overlap_frac(s, d, hgaps) < HOUSE_OVERLAP_EXCL_FRAC]
    return GwChannelGapStats(
        channel_name=cr.channel_name,
        channel_type_name=word.type_name,
        channel_version=word.version,
        window_start_unix_ms=pull.start_unix_ms,
        window_end_unix_ms=pull.end_unix_ms,
        num_readings=len(ts),
        abs_gap_s=ABS_GAP_S,
        median_mult=MEDIAN_MULT,
        median_cadence_s=round(median_dt, 1),
        gap_count=len(kept),
        excluded_gap_count=len(gaps) - len(kept),
        gapped_seconds=round(sum(d for _, d in kept), 1),
        max_gap_dur_s=round(max((d for _, d in kept), default=0.0), 1),
    )


def main() -> None:
    for cond in CONDITIONS:
        pull = load_pull(instance_path(cond))
        hgaps = house_silent_windows(pull)
        words = {c.name: c for c in pull.channels}
        out_dir = HERE / "instances" / cond
        out_dir.mkdir(parents=True, exist_ok=True)
        stats: list[GwChannelGapStats] = []
        for cr in pull.channel_readings_list:
            if not cr.value_list:
                continue
            s = channel_gap_stats(pull, cr, words[cr.channel_name], hgaps)
            stats.append(s)
            path = out_dir / (f"{spaceheat_name_to_lrd_token(s.channel_name)}"
                              f"-gw.channel.gap.stats-000.json")
            path.write_text(json.dumps(s.to_dict(), indent=1) + "\n")
        print(f"wrote {len(stats)} instances to "
              f"{out_dir.relative_to(HERE)}")

        days = (pull.end_unix_ms - pull.start_unix_ms) / 86_400_000
        total = sum(s.gap_count for s in stats)
        excl = sum(s.excluded_gap_count for s in stats)
        sec = sum(s.gap_count for s in stats
                  if s.channel_name in SECONDARY_BTU_CHANNELS)
        print(f"  {cond}: {days:.2f} d, {len(stats)} channels, "
              f"{sum(s.num_readings for s in stats)} readings")
        print(f"  house-silent windows: {len(hgaps)} "
              f"({excl} channel-gaps excluded)")
        print(f"  total gaps {total} ({total / days:.2f}/day); "
              f"secondary-BTU pico {sec} ({sec / days:.2f}/day)")


if __name__ == "__main__":
    main()
