"""NWS gridpoint updateTime probe — one JSONL line per poll.

Polls the CAR/60,114 hourly product every 5 minutes and records the
three stamps that matter to the gwwf emission design: `updateTime`
(the underlying-data stamp gwwf binds to ForecastCreated),
`generatedAt` (the per-render stamp), and the first period start.
The analysis question: how fresh is updateTime at :30 past each hour
— the planned forecast broadcast phase?

Runs in the gwwf venv (imports its snapshot's property formats):

    cd ~/GridWorks/gridworks-weather-forecast
    nohup uv run python \
      ../experiments/2026-08-11-nws-updatetime-probe/probe.py \
      >> ../experiments/2026-08-11-nws-updatetime-probe/probe.jsonl 2>> \
      ../experiments/2026-08-11-nws-updatetime-probe/probe.err &

Stop after a day or two: kill the pid in probe.pid.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import requests

from gwwf.sema.property_format import UtcIso8601Seconds

URL = "https://api.weather.gov/gridpoints/CAR/60,114/forecast/hourly"
USER_AGENT = "gridworks-weather-forecast (gridworks@gridworks-consulting.com)"
PERIOD_S = 300


class ProbePoll(NamedTuple):
    """One poll of the hourly product's time stamps.

    ``polled_at`` is the probe's own clock (UTC, second resolution).
    ``update_time`` / ``generated_at`` / ``first_period_start`` are the
    product's stamps VERBATIM (offset form — raw evidence, normalized
    only at analysis). ``status`` is the HTTP status, None when the
    request itself failed; ``error`` then carries the repr. NOTE:
    analysis intermediate with no sema word; it retires into the
    experiment's distilled instances at analysis time.
    """

    polled_at: UtcIso8601Seconds
    status: int | None = None
    update_time: str | None = None
    generated_at: str | None = None
    first_period_start: str | None = None
    error: str | None = None

    def to_jsonable(self) -> dict[str, str | int | None]:
        """The one dict rendering, at the JSONL boundary; None keys drop."""
        return {k: v for k, v in self._asdict().items() if v is not None}


def poll() -> ProbePoll:
    polled_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        response = requests.get(URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    except Exception as e:  # noqa: BLE001 -- probe must survive anything
        return ProbePoll(polled_at=polled_at, error=repr(e))
    if response.status_code != 200:
        return ProbePoll(polled_at=polled_at, status=response.status_code)
    try:
        properties = response.json().get("properties", {})
        periods = properties.get("periods", [])
        return ProbePoll(
            polled_at=polled_at,
            status=response.status_code,
            update_time=properties.get("updateTime"),
            generated_at=properties.get("generatedAt"),
            first_period_start=periods[0]["startTime"] if periods else None,
        )
    except Exception as e:  # noqa: BLE001 -- probe must survive anything
        return ProbePoll(
            polled_at=polled_at, status=response.status_code, error=repr(e)
        )


def main() -> None:
    Path(__file__).with_name("probe.pid").write_text(f"{os.getpid()}\n")
    once = "--once" in sys.argv
    while True:
        print(json.dumps(poll().to_jsonable()), flush=True)
        if once:
            return
        time.sleep(PERIOD_S)


if __name__ == "__main__":
    main()
