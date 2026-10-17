"""Pull measured solar irradiance near spruce from a Weather Underground
personal weather station, for the floor cool-down windows.

Source: the weather.com PWS history API that the wunderground.com station
dashboard reads (the same data gridworks-house-parameters/weather_scraper.py
scrapes off the rendered page). Station KMEMILLI18 is in Millinocket at
45.665 N, 68.72 W and reports a 5-minute solar radiation high in W/m2
(horizontal pyranometer on a consumer station; treat the level as
indicative and the shape as good).

Writes `irradiance-kmemilli18.csv` (provenance header, one row per
station observation; committed gzipped under the 2 MB cap) and
`pull-irradiance.log` (per-day counts and gaps over 30 min). Raw per-day
JSON is cached under `raw/` (gitignored) so a re-run does not re-fetch.
`read_observations` is the reader the fit uses; it opens either form.

Run from the experiments repo root: `uv run python
spruce-radiant-slab/pull_irradiance.py`.
"""

import csv
import gzip
import json
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

STATION = "KMEMILLI18"
# Public key the wunderground.com dashboard itself sends; not a secret.
API_KEY = "e1f10a1e78da46f5b10a1e78da96f525"
URL = (
    "https://api.weather.com/v2/pws/history/all?stationId={station}"
    "&format=json&units=e&numericPrecision=decimal&date={day}&apiKey={key}"
)
# Floor-surface sensor window, spring no-charge windows, fall no-charge window.
WINDOWS = [
    (date(2026, 2, 6), date(2026, 3, 10)),
    (date(2026, 3, 30), date(2026, 5, 17)),
    (date(2026, 9, 23), date(2026, 10, 15)),
]
HERE = Path(__file__).resolve().parent
RAW_DIR = HERE / "raw"
OUT_CSV = HERE / "irradiance-kmemilli18.csv"
OUT_LOG = HERE / "pull-irradiance.log"
GAP_MIN = 30


class StationObservation(NamedTuple):
    """One five-minute report from the personal weather station, as the
    history API serves it: `obs_time_local` is America/New_York,
    `solar_w_m2_high` the station's five-minute high of horizontal
    irradiance, the rest the station's five-minute averages. A field
    the station did not report is None.
    No sema word: gw.weather.observation 000 is temperature and wind
    only, and gw.readings cannot hold an irradiance channel (its
    channel word's quantity projection has none). An observation word
    with irradiance, or a weather readings series word, retires this."""

    obs_time_utc: str
    obs_time_local: str
    epoch: int
    solar_w_m2_high: float | None
    uv_high: float | None
    temp_f_avg: float | None
    humidity_avg: float | None
    windspeed_mph_avg: float | None
    winddir_avg: float | None


def read_observations() -> list[StationObservation]:
    """The evidence file back as records, plain or gzipped."""
    gz = OUT_CSV.with_suffix(".csv.gz")
    opened = (
        OUT_CSV.open(newline="")
        if OUT_CSV.exists()
        else gzip.open(gz, "rt", newline="")
    )
    with opened as f:
        rows = csv.DictReader(line for line in f if not line.startswith("#"))
        return [
            StationObservation(
                obs_time_utc=r["obs_time_utc"],
                obs_time_local=r["obs_time_local"],
                epoch=int(r["epoch"]),
                **{
                    k: (None if r[k] in ("", "None") else float(r[k]))
                    for k in StationObservation._fields[3:]
                },
            )
            for r in rows
        ]


def days() -> list[date]:
    out: list[date] = []
    for a, b in WINDOWS:
        d = a
        while d <= b:
            out.append(d)
            d += timedelta(days=1)
    return out


def fetch(day: date) -> list[dict]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw = RAW_DIR / f"{STATION}-{day.isoformat()}.json"
    if not raw.exists():
        req = urllib.request.Request(
            URL.format(station=STATION, day=day.strftime("%Y%m%d"), key=API_KEY),
            headers={"User-Agent": "Mozilla/5.0"},
        )
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    raw.write_bytes(r.read())
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 3:
                    raise
                print(f"{day}: retry after {e}", file=sys.stderr)
                time.sleep(3 * (attempt + 1))
        time.sleep(0.5)
    body = json.loads(raw.read_text())
    obs = body.get("observations") or []
    return [o for o in obs if o.get("stationID") == STATION]


def main() -> None:
    rows: list[StationObservation] = []
    log: list[str] = [
        f"pull_irradiance.py {datetime.now(timezone.utc):%Y-%m-%d %H:%MZ} "
        f"station {STATION}",
    ]
    for day in days():
        obs = fetch(day)
        obs.sort(key=lambda o: o["epoch"])
        gaps: list[str] = []
        prev = None
        for o in obs:
            if prev is not None and o["epoch"] - prev["epoch"] > GAP_MIN * 60:
                gaps.append(
                    f"{prev['obsTimeLocal'][11:16]}-{o['obsTimeLocal'][11:16]}"
                )
            prev = o
            imp = o["imperial"]
            rows.append(
                StationObservation(
                    obs_time_utc=o["obsTimeUtc"],
                    obs_time_local=o["obsTimeLocal"],
                    epoch=o["epoch"],
                    solar_w_m2_high=o.get("solarRadiationHigh"),
                    uv_high=o.get("uvHigh"),
                    temp_f_avg=imp.get("tempAvg"),
                    humidity_avg=o.get("humidityAvg"),
                    windspeed_mph_avg=imp.get("windspeedAvg"),
                    winddir_avg=o.get("winddirAvg"),
                )
            )
        line = f"{day}: {len(obs)} obs"
        if not obs:
            line += "  NO DATA"
        elif gaps:
            line += "  gaps>30min: " + ", ".join(gaps)
        log.append(line)
        print(line)

    with OUT_CSV.open("w", newline="") as f:
        f.write(
            f"# Solar irradiance and weather at PWS {STATION} (Millinocket, "
            "45.665N 68.72W), from the weather.com PWS history API behind the\n"
            "# wunderground.com station dashboard; pulled by pull_irradiance.py "
            f"on {datetime.now(timezone.utc):%Y-%m-%d}. solar_w_m2_high is the\n"
            "# station's 5-minute high of horizontal irradiance in W/m2; "
            "obs_time_local is America/New_York. Windows: "
            + ", ".join(f"{a} to {b}" for a, b in WINDOWS)
            + ".\n"
        )
        w = csv.writer(f)
        w.writerow(StationObservation._fields)
        w.writerows(rows)
    OUT_LOG.write_text("\n".join(log) + "\n")
    print(f"wrote {OUT_CSV.name} ({len(rows)} rows) and {OUT_LOG.name}")


if __name__ == "__main__":
    main()
