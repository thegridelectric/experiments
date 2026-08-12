"""Distill probe.jsonl — the updateTime freshness analysis.

Reads the raw polls and prints: poll coverage (with suspension gaps),
the revision inventory (each distinct updateTime, when it appeared and
how long it held), lag statistics, and the design question — how old
updateTime is at each :30 past the hour (the planned forecast
broadcast phase), with the fraction of :30s under candidate freshness
thresholds. Prints only; the distilled verdict goes into this folder's
README "Found" by hand.

Run any time (probe may keep running):

    cd ~/GridWorks/gridworks-weather-forecast
    uv run python ../experiments/2026-08-11-nws-updatetime-probe/analyze.py
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
PERIOD_S = 300
JSONL = Path(__file__).with_name("probe.jsonl")


def parse(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp)


def main() -> None:
    polls = []
    misses = 0
    for line in JSONL.read_text().splitlines():
        record = json.loads(line)
        if record.get("status") == 200 and record.get("update_time"):
            polls.append(
                (parse(record["polled_at"]), parse(record["update_time"]))
            )
        else:
            misses += 1
    polls.sort()
    if not polls:
        print("no successful polls")
        return

    first, last = polls[0][0], polls[-1][0]
    print(f"polls: {len(polls)} ok, {misses} misses")
    print(f"window: {first} → {last} ({(last - first).total_seconds() / 3600:.1f} h)")
    print("\nsuspension gaps (> 2× period — probe/machine asleep, not NWS):")
    for (t0, _), (t1, _) in zip(polls, polls[1:]):
        if (t1 - t0).total_seconds() > 2 * PERIOD_S:
            print(f"  {t0} → {t1}  ({(t1 - t0).total_seconds() / 60:.0f} min)")

    print("\nrevision inventory (updateTime · first seen · held through):")
    revisions: list[tuple[datetime, datetime, datetime]] = []
    for polled, update_time in polls:
        if revisions and revisions[-1][0] == update_time:
            revisions[-1] = (update_time, revisions[-1][1], polled)
        else:
            revisions.append((update_time, polled, polled))
    for update_time, seen, held in revisions:
        span_h = (held - seen).total_seconds() / 3600
        print(f"  {update_time}  seen {seen}  held ≥{span_h:.1f} h")

    lags = [(polled - update_time).total_seconds() / 60 for polled, update_time in polls]
    print(
        f"\nupdateTime lag over all polls (min): "
        f"min {min(lags):.0f} · median {statistics.median(lags):.0f} · "
        f"max {max(lags):.0f}"
    )

    print("\nlag at each :30 ET (nearest poll within ±5 min):")
    half_hours: list[float] = []
    cursor = first.astimezone(ET).replace(minute=30, second=0, microsecond=0)
    if cursor < first.astimezone(ET):
        cursor += timedelta(hours=1)
    while cursor <= last.astimezone(ET):
        nearest = min(polls, key=lambda p: abs((p[0] - cursor).total_seconds()))
        if abs((nearest[0] - cursor).total_seconds()) <= 300:
            lag_min = (nearest[0] - nearest[1]).total_seconds() / 60
            half_hours.append(lag_min)
            print(f"  {cursor:%Y-%m-%d %H:%M} ET  lag {lag_min:6.0f} min")
        else:
            print(f"  {cursor:%Y-%m-%d %H:%M} ET  (no poll — suspended)")
        cursor += timedelta(hours=1)
    if half_hours:
        for threshold in (30, 60, 120):
            fraction = sum(lag <= threshold for lag in half_hours) / len(half_hours)
            print(
                f"  :30s with updateTime ≤ {threshold} min old: "
                f"{fraction:.0%} ({sum(lag <= threshold for lag in half_hours)}"
                f"/{len(half_hours)})"
            )


if __name__ == "__main__":
    main()
