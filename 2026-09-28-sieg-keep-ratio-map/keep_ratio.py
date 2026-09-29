"""Kept fraction of maple's primary flow per timed Siegenthaler valve stop.

One row per StopValve in the window log (a stop whose run was shorter
than a full travel): the direction the motor was running, the seconds it
ran, its position in seconds from the send stop (the seconds run toward
keep, or KEEP_STOP_S minus the seconds run toward send), and the median sieg-flow and
sieg-send-flow held-value sampled every 10 s from 60 to 150 s after the
stop, from the persisted report.events, with r = sieg / (sieg + send).
A steady flow posts no new reading (the picos report on change), so
each sample is the last reading at or before it; a sample whose reading
is older than MAX_AGE_MS is stale, and a run with any stale sample of
either meter is listed and excluded.
Rows are grouped by position to the nearest three seconds and each
group's mean and standard deviation of r are printed with the count from
each direction.

    python keep_ratio.py maple-window-<stamp>.log maple-events-<stamp>/
"""
import bisect
import datetime
import json
import os
import re
import statistics
import sys
from pathlib import Path

SPAN_MS = (60_000, 150_000)
STEP_MS = 10_000
MAX_AGE_MS = 300_000
STOP = re.compile(r"^(\S+ \S+) \[sieg-loop\] Motor stopped after ([0-9.]+) s: keep_seconds ([0-9.]+)")
START = re.compile(r"^\S+ \S+ \[sieg-loop\] Motor toward (keep|send) for")
KEEP_STOP_S = 94.0
FULL_RUN_S = 100.0
ET = datetime.timezone(datetime.timedelta(hours=-4))


def load(folder):
    rows = {"sieg-flow": [], "sieg-send-flow": []}
    for root, _, files in os.walk(folder):
        for fn in files:
            try:
                x = json.load(open(os.path.join(root, fn)))
            except Exception:
                continue
            pl = x.get("Payload", x)
            if pl.get("TypeName") != "report.event":
                continue
            for c in pl.get("Report", pl)["ChannelReadingList"]:
                if c["ChannelName"] in rows:
                    rows[c["ChannelName"]] += list(zip(c["ScadaReadTimeUnixMsList"], c["ValueList"]))
    return {k: sorted(set(v)) for k, v in rows.items()}


def stops(log):
    """(stop ms, direction, seconds run, position from send) for each StopValve."""
    direction = None
    for line in open(log):
        m = START.match(line)
        if m:
            direction = m.group(1)
            continue
        m = STOP.match(line)
        if m and direction and float(m.group(2)) < FULL_RUN_S:
            t = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=ET)
            ran = float(m.group(2))
            pos = ran if direction == "keep" else KEEP_STOP_S - ran
            yield int(t.timestamp() * 1000), direction, ran, pos


def held(series, t0):
    """Held gpm at each sample time in the span, or None if any sample is stale."""
    ts = [x[0] for x in series]
    out = []
    for t in range(t0 + SPAN_MS[0], t0 + SPAN_MS[1] + 1, STEP_MS):
        i = bisect.bisect_right(ts, t)
        if i == 0 or t - series[i - 1][0] > MAX_AGE_MS:
            return None
        out.append(series[i - 1][1] / 100)  # GpmTimes100 -> gpm
    return out


def main(log, folder):
    flows = load(folder)
    rows = []
    print("stop (ET)        toward  ran_s  pos_s  sieg_gpm  send_gpm  r")
    for t0, direction, ran, pos in stops(log):
        sieg, send = held(flows["sieg-flow"], t0), held(flows["sieg-send-flow"], t0)
        stamp = datetime.datetime.fromtimestamp(t0 / 1000, ET).strftime("%m-%d %H:%M:%S")
        if sieg is None or send is None:
            which = " ".join(n for n, v in (("sieg", sieg), ("send", send)) if v is None)
            print(f"{stamp}  {direction:4s}   {ran:5.1f}  {pos:5.1f}  DISCARDED: stale {which} reading in span")
            continue
        s, d = statistics.median(sieg), statistics.median(send)
        r = s / (s + d) if s + d else float("nan")
        rows.append((direction, pos, s, d, r))
        print(f"{stamp}  {direction:4s}   {ran:5.1f}  {pos:5.1f}  {s:7.2f}  {d:7.2f}  {r:5.3f}")
    groups = {}
    for direction, pos, s, d, r in rows:
        groups.setdefault(round(pos / 3) * 3, []).append((direction, r))
    print("\npos_s  n  toward keep / send   r mean/sd")
    for pos in sorted(groups):
        g = groups[pos]
        rs = [x[1] for x in g]
        nk = sum(1 for x in g if x[0] == "keep")
        sd = statistics.stdev(rs) if len(rs) > 1 else 0.0
        print(f"{pos:5.0f}  {len(g):2d}  {nk:2d} / {len(g) - nk:2d}           {statistics.mean(rs):5.3f} / {sd:5.3f}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
