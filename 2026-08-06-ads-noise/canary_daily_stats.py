#!/usr/bin/env python3
"""Daily spike statistics per zone channel from archived gw-microvolts
readings — the canary-in-the-coalmine view of ADS health.

Input: CSV from pull_readings.py raw mode (timestamp_et, channel, value)
on the zone*-gw-microvolts channels. A "spike" is a consecutive-reading
jump |dv| > 50,000 uV (~1.5 C) within 5 minutes — far above any real
zone-temperature slew, so each one is an electrical event the async
reporter happened to publish.

Usage: canary_daily_stats.py archive-zone-uv-<window>.csv
"""

import collections
import csv
import datetime
import sys

SPIKE_UV = 50_000
MAX_GAP_S = 300


def main(path: str) -> None:
    rows = collections.defaultdict(list)
    with open(path) as f:
        for r in csv.DictReader(f):
            t = datetime.datetime.fromisoformat(r["timestamp_et"])
            rows[r["channel"]].append((t, int(float(r["value"]))))
    for chan, series in sorted(rows.items()):
        series.sort()
        daily = collections.defaultdict(lambda: [0, 0, 0])  # n, spikes, max jump
        for (t0, v0), (t1, v1) in zip(series, series[1:]):
            d = daily[t1.date()]
            d[0] += 1
            jump = abs(v1 - v0)
            if jump > SPIKE_UV and (t1 - t0).total_seconds() < MAX_GAP_S:
                d[1] += 1
            d[2] = max(d[2], jump)
        print(f"\n{chan}: readings/day · spikes(|dv|>{SPIKE_UV}uV, <{MAX_GAP_S}s) · max |dv| uV")
        for day in sorted(daily):
            n, s, m = daily[day]
            flag = " <<<" if s else ""
            print(f"  {day}  n={n:5d}  spikes={s:3d}  maxjump={m:7d}{flag}")


if __name__ == "__main__":
    main(sys.argv[1])
