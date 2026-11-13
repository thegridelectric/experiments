#!/usr/bin/env python3
"""Living-room fan-coil thermostat: deadband + when-it-stopped analysis.

George reported the living-room (zone-5) fan-coil thermostat "wasn't
working". This reads a week of the living-room air temperature
(zone2-living-rm-gw-temp — the same-room thermistor) alongside the fan-coil
call (zone5-living-rm-fancoil-heat-call, 1 = calling) and answers two things:

  1. How large is the thermostat's deadband? Following Thomas's falling-edge
     idea (derived_generator.py, simple-falling-edge-setpoint: the setpoint is
     the zone temp at the FALLING edge of a call), we read the air temp at
     every call ON (rising) and OFF (falling) edge over the working period.
     For a COOLING fan-coil the call starts warm and ends cool, so the swing
     between the two edge-temperature clusters IS the deadband, and the
     setpoint sits between them.

  2. When did it stop? The last rising/falling edge dates the last real call;
     everything after is the dead interval. We report how warm the room got
     during it with no call — the proof the thermostat isn't responding.

Data: living_room_week.csv (unix_s, channel, value), pulled read-only from
the journal for [now-8d, 2026-08-15 15:00 ET] — the window ends before the
2026-08-15 scada intervention so the calls here are the WALL thermostat's.
Reproduce: see README.
"""

import csv
import statistics
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
HERE = Path(__file__).parent
TEMP_CH = "zone2-living-rm-gw-temp"        # CelsiusTimes100
CALL_CH = "zone5-living-rm-fancoil-heat-call"  # 1 = calling
EDGE_TEMP_TOL_S = 150   # match a temp reading within this of an edge
MIN_DWELL_S = 120       # ignore call flips that don't persist this long


def load():
    temps: list[tuple[int, float]] = []   # (unix_s, deg_f)
    calls: list[tuple[int, int]] = []     # (unix_s, 0/1)
    with open(HERE / "living_room_week.csv") as f:
        for unix_s, name, value in csv.reader(f):
            if not unix_s:
                continue
            t, v = int(unix_s), float(value)
            if name == TEMP_CH:
                temps.append((t, v / 100.0 * 9 / 5 + 32))
            elif name == CALL_CH:
                calls.append((t, int(v)))
    temps.sort()
    calls.sort()
    return temps, calls


def temp_at(temps, t):
    """Nearest temp reading to time t, within EDGE_TEMP_TOL_S."""
    best = min(temps, key=lambda x: abs(x[0] - t))
    return best[1] if abs(best[0] - t) <= EDGE_TEMP_TOL_S else None


def edges(calls):
    """Debounced call transitions: [(unix_s, 'ON'|'OFF')]. A transition counts
    only if the new state persists >= MIN_DWELL_S (drops single-sample blips)."""
    out = []
    prev = None
    for i, (t, v) in enumerate(calls):
        if prev is None:
            prev = v
            continue
        if v != prev:
            # persistence check: does v hold for MIN_DWELL_S?
            held = all(calls[j][1] == v for j in range(i, len(calls))
                       if calls[j][0] - t < MIN_DWELL_S)
            if held:
                out.append((t, "ON" if v == 1 else "OFF"))
                prev = v
    return out


def et(t):
    return datetime.fromtimestamp(t, timezone.utc).astimezone(ET).strftime("%m-%d %H:%M")


def main():
    temps, calls = load()
    ev = edges(calls)
    on_temps = [temp_at(temps, t) for t, k in ev if k == "ON"]
    off_temps = [temp_at(temps, t) for t, k in ev if k == "OFF"]
    on_temps = [x for x in on_temps if x is not None]
    off_temps = [x for x in off_temps if x is not None]

    print(f"window: {et(temps[0][0])} .. {et(temps[-1][0])} ET  "
          f"({len(temps)} temps, {len(calls)} call readings)")
    on_ev = [t for t, k in ev if k == "ON"]
    off_ev = [t for t, k in ev if k == "OFF"]
    print(f"call cycles: {len(on_ev)} ON edges, {len(off_ev)} OFF edges")
    if on_ev:
        print(f"first call ON:  {et(min(on_ev))} ET")
        print(f"last call ON:   {et(max(on_ev))} ET")
    if off_ev:
        print(f"last call OFF:  {et(max(off_ev))} ET  <- last time it worked")

    print("\n--- (1) DEADBAND ---")
    if on_temps:
        print(f"call ON  edge temps: median {statistics.median(on_temps):.1f}F "
              f"range {min(on_temps):.1f}-{max(on_temps):.1f}F  n={len(on_temps)}")
    if off_temps:
        print(f"call OFF edge temps: median {statistics.median(off_temps):.1f}F "
              f"range {min(off_temps):.1f}-{max(off_temps):.1f}F  n={len(off_temps)}")

    # Per-cycle swing controls for setpoint drift: pair each ON edge with the
    # next OFF edge and read the air-temp change across that single call.
    swings = []
    off_after = [t for t, k in ev if k == "OFF"]
    for t_on, k in ev:
        if k != "ON":
            continue
        nxt = next((o for o in off_after if o > t_on), None)
        if nxt is None:
            continue
        a, b = temp_at(temps, t_on), temp_at(temps, nxt)
        if a is not None and b is not None:
            swings.append(a - b)  # cooling: warm at ON, cool at OFF -> positive
    if swings:
        swings.sort()
        print(f"per-cycle swing (ON temp - OFF temp): median {statistics.median(swings):.2f}F, "
              f"p10 {swings[len(swings)//10]:.2f} / p90 {swings[9*len(swings)//10]:.2f}F, n={len(swings)}")

    # Cycle frequency
    on_ts = sorted(on_ev)
    periods = [(on_ts[i+1] - on_ts[i]) / 60 for i in range(len(on_ts) - 1)]
    if periods:
        periods.sort()
        print(f"cycle period (ON->next ON): median {statistics.median(periods):.0f} min "
              f"({len(on_ts)} calls over the working span => short-cycling)")
    print("cross-check: Thomas's SetpointThresholdFX100 = 2.0F (his assumed tolerance)")

    print("\n--- (2) WHEN IT STOPPED ---")
    if off_ev:
        last = max(off_ev)
        dead = [tf for t, tf in temps if t > last]
        hrs = (temps[-1][0] - last) / 3600
        print(f"last call ended {et(last)} ET; DEAD for {hrs:.1f} h since "
              f"(through {et(temps[-1][0])} ET)")
        if dead and on_temps:
            thresh = statistics.median(on_temps)
            over = max(dead) - thresh
            print(f"during the dead interval the room reached {max(dead):.1f}F "
                  f"— {over:+.1f}F past the ~{thresh:.1f}F it used to call at, "
                  f"with NO call. That is the thermostat not responding.")


if __name__ == "__main__":
    main()
