#!/usr/bin/env python3
"""Hunt maple's journal readings for heat pump defrost events and profile
them.

A defrost is looked for as: the scada commanding the heat pump on
(`hp-scada-ops-relay6` de-energized), the heat pump having run with real
lift in the quarter hour before, and the lift (`hp-lwt` minus `hp-ewt`)
then falling to zero or below while the command stays on.

Two steps, so the pull can be re-run without the analysis and the reverse:

  uv run python defrost_hunt.py pull --start 2026-03-26 --end 2026-05-16 \
      --work <dir>
  uv run python defrost_hunt.py hunt --work <dir>

`pull` runs ../pull_readings.py one ET day at a time (a week in one query
runs into the journal DB's statement timeout) and writes one gw.readings
instance per day into --work. `hunt` decodes those instances through the
snapshot codec and writes maple-defrost-events.json here: every event with
its numbers, and the summary statistics the README's defrost profile quotes.
It also writes one short gw.readings instance per defrost (the hunt's
channels from a few minutes before the lift goes nonpositive until just
after it recovers) into <work>/defrost-signatures/, and copies a handful
here into defrost-signatures/ as examples: the defrosts at the
KEPT_QUANTILES of time spent with lift at or below zero.
"""

import argparse
import bisect
import datetime
import json
import statistics
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))

from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.enums import SpaceheatTelemetryName  # noqa: E402
from gwexp.sema.property_format import (  # noqa: E402
    LeftRightDot,
    SpaceheatName,
    UTCMilliseconds,
    UTCSeconds,
)
from gwexp.sema.types import ChannelReadings, DataChannelGt, GwReadings  # noqa: E402

ET = ZoneInfo("America/New_York")
TA: LeftRightDot = "hw1.isone.me.versant.keene.maple.ta"

HP_ODU_PWR: SpaceheatName = "hp-odu-pwr"
HP_LWT: SpaceheatName = "hp-lwt"
HP_EWT: SpaceheatName = "hp-ewt"
HP_SCADA_OPS_RELAY: SpaceheatName = "hp-scada-ops-relay6"
HP_FAILSAFE_RELAY: SpaceheatName = "hp-failsafe-relay5"
OAT: SpaceheatName = "oat"
CHANNELS: list[SpaceheatName] = [
    HP_ODU_PWR, HP_LWT, HP_EWT, HP_SCADA_OPS_RELAY, HP_FAILSAFE_RELAY, OAT,
]

RUNNING_LIFT_C = 2.0  # lift that counts as the heat pump making heat
RUNNING_PWR_W = 500  # power that counts as the compressor running
LOOKBACK_MS = 15 * 60 * 1000  # how far back "was running" is looked for
JOIN_GAP_MS = 90 * 1000  # lift<=0 samples closer than this are one event
RECOVERY_LIMIT_MS = 30 * 60 * 1000  # give up looking for recovery after this
OFF_THRESHOLDS_W = (100, 200, 500)  # candidate "heat pump is off" thresholds
SIGNATURE_LEAD_MS = 5 * 60 * 1000  # a signature starts this long before the event
SIGNATURE_TAIL_MS = 2 * 60 * 1000  # and runs this long past recovery
KEPT_QUANTILES = (0.0, 0.25, 0.5, 0.75, 1.0)  # of lift_nonpositive_s; the examples kept here

# The hunt's rule catches three different things. These bounds, read off the
# first pass over 2026-03-26 -> 05-16, separate them.
DEFROST_MAX_LIFT_C = -5.0  # a defrost pulls LWT well under EWT
DEFROST_MIN_S = 120  # and holds it there for minutes
DEFROST_MAX_DIP_W = 1000  # while the compressor stops to reverse
BLIP_MAX_S = 60  # a blip is over in under a minute at full power


class Series(NamedTuple):
    """One channel's readings over the whole hunt, time-ordered.
    `times_ms` are scada read times; `values` are the wire integers
    converted once to natural units (W, deg C, or the relay's 0/1)."""

    times_ms: list[UTCMilliseconds]
    values: list[float]

    def at(self, t_ms: int) -> float | None:
        """Last value at or before t_ms (readings report on change)."""
        i = bisect.bisect_right(self.times_ms, t_ms) - 1
        return self.values[i] if i >= 0 else None

    def between(self, lo_ms: int, hi_ms: int) -> list[float]:
        """Values read in [lo_ms, hi_ms], preceded by the value in force
        at lo_ms when there is one."""
        i = bisect.bisect_left(self.times_ms, lo_ms)
        j = bisect.bisect_right(self.times_ms, hi_ms)
        held = self.at(lo_ms)
        return ([] if held is None else [held]) + self.values[i:j]


class DefrostEvent(NamedTuple):
    """One stretch with the heat pump commanded on, lift at or below zero,
    after the heat pump had been running with lift.
    No sema word covers a derived plant event; the word that retires this
    record is a heat pump defrost event word (none in the registry)."""

    kind: str  # "defrost" | "blip" | "other", see classify()
    start_s: UTCSeconds  # first lift <= 0 sample
    start_et: str  # the same, ET wall clock, for reading
    lift_nonpositive_s: int  # first to last lift <= 0 sample
    recovery_s: int | None  # start until lift is back to RUNNING_LIFT_C
    min_lift_c: float
    pwr_before_w: int  # mean hp-odu-pwr over the 5 min before start
    min_pwr_w: int  # lowest hp-odu-pwr from start to recovery
    mean_pwr_w: int  # mean hp-odu-pwr from start to recovery
    s_under_w: dict[int, int]  # per OFF_THRESHOLDS_W: longest stretch under it
    lwt_before_c: float
    min_lwt_c: float
    oat_c: float | None
    scada_has_failsafe: bool | None  # hp-failsafe-relay5 energized at start
    since_prev_min: int | None  # start to start, same run of the heat pump

    def to_jsonable(self) -> dict:
        d = self._asdict()
        d["s_under_w"] = {str(k): v for k, v in self.s_under_w.items()}
        return d


def to_natural(word: DataChannelGt, raw: int) -> float:
    """Wire integer to W, deg C or relay 0/1, by the channel word's own
    telemetry name. Refuses an encoding this hunt has no rule for."""
    tn = word.telemetry_name
    if tn in (SpaceheatTelemetryName.WaterTempCTimes1000,
              SpaceheatTelemetryName.AirTempCTimes1000):
        return raw / 1000
    if tn in (SpaceheatTelemetryName.WaterTempFTimes1000,
              SpaceheatTelemetryName.AirTempFTimes1000):
        return (raw / 1000 - 32) * 5 / 9
    if tn in (SpaceheatTelemetryName.PowerW, SpaceheatTelemetryName.RelayState):
        return float(raw)
    raise ValueError(f"{word.name}: no rule for telemetry name {tn}")


def classify(lift_nonpositive_s: int, min_lift_c: float, min_pwr_w: int) -> str:
    """defrost: deep negative lift held for minutes with a power dip.
    blip: a sub-minute negative lift at full power (a sensor transient,
    not a change in what the heat pump is doing). other: everything else,
    mostly the heat pump stopping its compressor while commanded on."""
    if (min_lift_c <= DEFROST_MAX_LIFT_C and lift_nonpositive_s >= DEFROST_MIN_S
            and min_pwr_w < DEFROST_MAX_DIP_W):
        return "defrost"
    if lift_nonpositive_s < BLIP_MAX_S and min_pwr_w >= DEFROST_MAX_DIP_W:
        return "blip"
    return "other"


def day_condition(day: datetime.date) -> LeftRightDot:
    return f"d{day:%Y%m%d}"


def pull(start: datetime.date, end: datetime.date, work: Path) -> None:
    work.mkdir(parents=True, exist_ok=True)
    day = start
    while day < end:
        nxt = day + datetime.timedelta(days=1)
        out = work / f"{TA}-{day_condition(day)}-gw.readings-000.json"
        if not out.exists():
            cmd = [sys.executable, str(HERE.parent / "pull_readings.py"),
                   "--ta", TA, "--start", f"{day} 00:00", "--end", f"{nxt} 00:00",
                   "--condition", day_condition(day), "--out", str(work)]
            for ch in CHANNELS:
                cmd += ["--channel", ch]
            r = subprocess.run(cmd, capture_output=True, text=True)
            status = "ok" if r.returncode == 0 else f"FAILED: {r.stderr.strip().splitlines()[-1]}"
            print(f"{day} {status}")
        day = nxt


def load(work: Path) -> tuple[dict[SpaceheatName, Series], dict[LeftRightDot, GwReadings]]:
    codec = SemaCodec()
    acc: dict[SpaceheatName, list[tuple[UTCMilliseconds, float]]] = {c: [] for c in CHANNELS}
    days: dict[LeftRightDot, GwReadings] = {}
    for path in sorted(work.glob(f"{TA}-d*-gw.readings-000.json")):
        inst = codec.from_dict(json.loads(path.read_text()), expect=GwReadings)
        days[path.name.split("-")[1]] = inst
        words = {w.name: w for w in inst.channels}
        for cr in inst.channel_readings_list:
            word = words[cr.channel_name]
            assert isinstance(word, DataChannelGt)
            acc[cr.channel_name] += [
                (t, to_natural(word, v))
                for t, v in zip(cr.scada_read_time_unix_ms_list, cr.value_list)
            ]
    series = {}
    for name, pairs in acc.items():
        pairs.sort()
        series[name] = Series([t for t, _ in pairs], [v for _, v in pairs])
    return series, days


def signature(event: DefrostEvent, days: dict[LeftRightDot, GwReadings]) -> GwReadings:
    """The event's readings as their own gw.readings instance: every
    reading of the hunt's channels from SIGNATURE_LEAD_MS before the event
    starts to SIGNATURE_TAIL_MS after it recovers (or, with no recovery,
    after its last lift <= 0 sample). A channel with no reading in the
    window is left out."""
    span_s = event.recovery_s if event.recovery_s is not None else event.lift_nonpositive_s
    lo_ms = event.start_s * 1000 - SIGNATURE_LEAD_MS
    hi_ms = (event.start_s + span_s) * 1000 + SIGNATURE_TAIL_MS
    words: dict[SpaceheatName, DataChannelGt] = {}
    rows: dict[SpaceheatName, list[tuple[UTCMilliseconds, int]]] = {}
    touched = {day_condition(datetime.datetime.fromtimestamp(t / 1000, ET).date())
               for t in (lo_ms, hi_ms)}
    for d in sorted(touched & days.keys()):
        by_name = {w.name: w for w in days[d].channels}
        for cr in days[d].channel_readings_list:
            kept = [(t, v) for t, v in zip(cr.scada_read_time_unix_ms_list, cr.value_list)
                    if lo_ms <= t <= hi_ms]
            if not kept:
                continue
            word = by_name[cr.channel_name]
            assert isinstance(word, DataChannelGt)
            words[cr.channel_name] = word
            rows.setdefault(cr.channel_name, []).extend(kept)
    return GwReadings(
        ta_alias=TA,
        start_unix_ms=lo_ms,
        end_unix_ms=hi_ms,
        channels=[words[n] for n in CHANNELS if n in words],
        channel_readings_list=[
            ChannelReadings(
                channel_name=n,
                value_list=[v for _, v in sorted(rows[n])],
                scada_read_time_unix_ms_list=[t for t, _ in sorted(rows[n])],
            )
            for n in CHANNELS if n in rows
        ],
    )


def signature_condition(event: DefrostEvent) -> LeftRightDot:
    start = datetime.datetime.fromtimestamp(event.start_s, ET)
    return f"defrost.d{start:%Y%m%d}.t{start:%H%M%S}"


def longest_under(pwr: Series, lo_ms: int, hi_ms: int, threshold_w: int) -> int:
    """Longest continuous stretch, in seconds, with power under the
    threshold inside [lo_ms, hi_ms]."""
    i = bisect.bisect_left(pwr.times_ms, lo_ms)
    j = bisect.bisect_right(pwr.times_ms, hi_ms)
    times = [lo_ms] + pwr.times_ms[i:j] + [hi_ms]
    held = pwr.at(lo_ms)
    values = [held if held is not None else float("inf")] + pwr.values[i:j]
    best = run_start = 0
    under = False
    for k, v in enumerate(values):
        if v < threshold_w and not under:
            under, run_start = True, times[k]
        if under and (v >= threshold_w):
            under = False
            best = max(best, times[k] - run_start)
    if under:
        best = max(best, times[-1] - run_start)
    return best // 1000


def hunt(series: dict[SpaceheatName, Series]) -> list[DefrostEvent]:
    lwt, ewt, pwr = series[HP_LWT], series[HP_EWT], series[HP_ODU_PWR]
    relay, failsafe, oat = series[HP_SCADA_OPS_RELAY], series[HP_FAILSAFE_RELAY], series[OAT]
    sample_times = sorted(set(lwt.times_ms) | set(ewt.times_ms))

    def lift(t: int) -> float | None:
        a, b = lwt.at(t), ewt.at(t)
        return None if a is None or b is None else a - b

    def commanded_on(lo: int, hi: int) -> bool:
        vals = relay.between(lo, hi)
        return bool(vals) and all(v == 0 for v in vals)

    runs: list[list[int]] = []
    for t in sample_times:
        lf = lift(t)
        if lf is None or lf > 0 or relay.at(t) != 0:
            continue
        if runs and t - runs[-1][-1] <= JOIN_GAP_MS:
            runs[-1].append(t)
        else:
            runs.append([t])

    events: list[DefrostEvent] = []
    for run in runs:
        start, last = run[0], run[-1]
        before = [t for t in sample_times if start - LOOKBACK_MS <= t < start]
        was_running = any(
            (lift(t) or 0) >= RUNNING_LIFT_C and (pwr.at(t) or 0) >= RUNNING_PWR_W
            for t in before
        )
        if not was_running or not commanded_on(start - LOOKBACK_MS, last):
            continue
        recovered = next(
            (t for t in sample_times
             if last < t <= start + RECOVERY_LIMIT_MS and (lift(t) or 0) >= RUNNING_LIFT_C),
            None,
        )
        end = recovered if recovered is not None else last
        during = pwr.between(start, end)
        before_pwr = pwr.between(start - 5 * 60 * 1000, start)
        lwt_before = lwt.at(start - 60 * 1000)
        prev = events[-1] if events else None
        since_prev = None
        if prev is not None and commanded_on(prev.start_s * 1000, start):
            since_prev = (start // 1000 - prev.start_s) // 60
        fs = failsafe.at(start)
        oat_c = oat.at(start)
        min_lift_c = round(min(lf for t in run if (lf := lift(t)) is not None), 2)
        min_pwr_w = round(min(during)) if during else 0
        events.append(DefrostEvent(
            kind=classify((last - start) // 1000, min_lift_c, min_pwr_w),
            start_s=start // 1000,
            start_et=f"{datetime.datetime.fromtimestamp(start / 1000, ET):%Y-%m-%d %H:%M:%S}",
            lift_nonpositive_s=(last - start) // 1000,
            recovery_s=None if recovered is None else (recovered - start) // 1000,
            min_lift_c=min_lift_c,
            pwr_before_w=round(statistics.fmean(before_pwr)) if before_pwr else 0,
            min_pwr_w=min_pwr_w,
            mean_pwr_w=round(statistics.fmean(during)) if during else 0,
            s_under_w={w: longest_under(pwr, start, end, w) for w in OFF_THRESHOLDS_W},
            lwt_before_c=round(lwt_before, 1) if lwt_before is not None else float("nan"),
            min_lwt_c=round(min(lwt.between(start, end)), 1),
            oat_c=None if oat_c is None else round(oat_c, 1),
            scada_has_failsafe=None if fs is None else fs == 1,
            since_prev_min=since_prev,
        ))
    return events


def summarize(events: list[DefrostEvent]) -> dict:
    def q(vals: list[float]) -> dict:
        vals = sorted(vals)
        if not vals:
            return {}
        return {"n": len(vals), "min": vals[0], "median": statistics.median(vals),
                "p90": vals[min(len(vals) - 1, int(0.9 * len(vals)))], "max": vals[-1]}

    return {
        "events": len(events),
        "hours_of_day_et": dict(sorted(
            (h, sum(1 for e in events if int(e.start_et[11:13]) == h))
            for h in {int(e.start_et[11:13]) for e in events})),
        "mean_pwr_w": q([e.mean_pwr_w for e in events]),
        "lwt_drop_c": q([round(e.lwt_before_c - e.min_lwt_c, 1) for e in events]),
        "lift_nonpositive_s": q([e.lift_nonpositive_s for e in events]),
        "recovery_s": q([e.recovery_s for e in events if e.recovery_s is not None]),
        "min_lift_c": q([e.min_lift_c for e in events]),
        "pwr_before_w": q([e.pwr_before_w for e in events]),
        "min_pwr_w": q([e.min_pwr_w for e in events]),
        "oat_c": q([e.oat_c for e in events if e.oat_c is not None]),
        "since_prev_min": q([e.since_prev_min for e in events if e.since_prev_min is not None]),
        **{f"s_under_{w}w": q([e.s_under_w[w] for e in events]) for w in OFF_THRESHOLDS_W},
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Hunt maple readings for defrosts.")
    sub = p.add_subparsers(dest="step", required=True)
    pp = sub.add_parser("pull")
    pp.add_argument("--start", required=True, type=datetime.date.fromisoformat)
    pp.add_argument("--end", required=True, type=datetime.date.fromisoformat)
    pp.add_argument("--work", required=True, type=Path)
    hp = sub.add_parser("hunt")
    hp.add_argument("--work", required=True, type=Path)
    args = p.parse_args()

    if args.step == "pull":
        pull(args.start, args.end, args.work)
        return

    series, days = load(args.work)
    events = hunt(series)
    defrosts = [e for e in events if e.kind == "defrost"]
    summary = {
        "kinds": {k: sum(1 for e in events if e.kind == k) for k in ("defrost", "blip", "other")},
        "defrost": summarize(defrosts),
    }
    out = HERE / "maple-defrost-events.json"
    out.write_text(json.dumps({
        "TaAlias": TA,
        "DaysSearched": sorted(days),
        "Rule": {"RunningLiftC": RUNNING_LIFT_C, "RunningPwrW": RUNNING_PWR_W,
                 "LookbackS": LOOKBACK_MS // 1000, "JoinGapS": JOIN_GAP_MS // 1000},
        "Summary": summary,
        "Events": [e.to_jsonable() for e in events],
    }, indent=1) + "\n")
    by_length = sorted(defrosts, key=lambda e: (e.lift_nonpositive_s, e.start_s))
    kept = {by_length[round(q * (len(by_length) - 1))].start_s for q in KEPT_QUANTILES} if by_length else set()
    every, keep = args.work / "defrost-signatures", HERE / "defrost-signatures"
    for folder in (every, keep):
        folder.mkdir(exist_ok=True)
        for old in folder.glob(f"{TA}-defrost.*-gw.readings-000.json"):
            old.unlink()
    for e in defrosts:
        name = f"{TA}-{signature_condition(e)}-gw.readings-000.json"
        text = json.dumps(signature(e, days).to_dict(), indent=1) + "\n"
        (every / name).write_text(text)
        if e.start_s in kept:
            (keep / name).write_text(text)
    print(f"{len(days)} days, {len(events)} events, {len(defrosts)} defrosts "
          f"-> {out.name}; {len(kept)} signatures here, all in {every}")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
