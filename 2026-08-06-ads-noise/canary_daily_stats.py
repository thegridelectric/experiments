#!/usr/bin/env python3
"""Daily spike statistics per zone channel from archived readings — the
canary-in-the-coalmine view of ADS health.

Input: this folder's gw.readings instance (channel words + readings,
decoded through the vendored snapshot). A "spike" is a
consecutive-reading jump |dv| > 50,000 uV (~1.5 C) within 5 minutes —
far above any real zone-temperature slew, so each one is an electrical
event the async reporter happened to publish.

Usage: uv run python canary_daily_stats.py
"""

import collections
import datetime
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.types import GwReadings  # noqa: E402

ET = ZoneInfo("America/New_York")
PULL_PATH = HERE / "hw1.isone.me.versant.keene.spruce.ta-gw.readings-000.json"

SPIKE_UV = 50_000
MAX_GAP_S = 300


def main() -> None:
    pull = SemaCodec().from_dict(json.loads(PULL_PATH.read_text()),
                                 expect=GwReadings)
    for cr in pull.channel_readings_list:
        pairs = list(zip(cr.scada_read_time_unix_ms_list, cr.value_list))
        daily = collections.defaultdict(lambda: [0, 0, 0])  # n, spikes, max jump
        for (t0, v0), (t1, v1) in zip(pairs, pairs[1:]):
            day = datetime.datetime.fromtimestamp(t1 / 1000, tz=ET).date()
            d = daily[day]
            d[0] += 1
            jump = abs(v1 - v0)
            if jump > SPIKE_UV and (t1 - t0) / 1000 < MAX_GAP_S:
                d[1] += 1
            d[2] = max(d[2], jump)
        print(f"\n{cr.channel_name}: readings/day · "
              f"spikes(|dv|>{SPIKE_UV}uV, <{MAX_GAP_S}s) · max |dv| uV")
        for day in sorted(daily):
            n, s, m = daily[day]
            flag = " <<<" if s else ""
            print(f"  {day}  n={n:5d}  spikes={s:3d}  maxjump={m:7d}{flag}")


if __name__ == "__main__":
    main()
