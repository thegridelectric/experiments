"""Kept fraction of maple's primary flow per timed Siegenthaler valve stop.

One row per StopValve in the window log: the seconds the motor ran, the
actor's keep_seconds after the stop, and the median sieg-flow and
sieg-send-flow held-value sampled every 10 s from 60 to 150 s after the
stop, from the persisted report.events, with r = sieg / (sieg + send).
A steady flow posts no new reading (the picos report on change), so
each sample is the last reading at or before it; a sample whose reading
is older than MAX_AGE_MS is stale, and a run with any stale sample of
either meter is listed and excluded.
Rows are grouped by the actor's keep_seconds to the nearest ten and each
group's mean and standard deviation of r and of keep_seconds are printed.

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
    for line in open(log):
        m = STOP.match(line)
        if m:
            t = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=ET)
            yield int(t.timestamp() * 1000), float(m.group(2)), float(m.group(3))


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
    print("stop (ET)            ran_s  keep_s  sieg_gpm  send_gpm  r")
    for t0, ran, keep in stops(log):
        sieg, send = held(flows["sieg-flow"], t0), held(flows["sieg-send-flow"], t0)
        stamp = datetime.datetime.fromtimestamp(t0 / 1000, ET).strftime("%m-%d %H:%M:%S")
        if sieg is None or send is None:
            which = " ".join(n for n, v in (("sieg", sieg), ("send", send)) if v is None)
            print(f"{stamp}  {ran:5.1f}  {keep:5.1f}  DISCARDED: stale {which} reading in span")
            continue
        s, d = statistics.median(sieg), statistics.median(send)
        r = s / (s + d) if s + d else float("nan")
        rows.append((ran, keep, s, d, r))
        print(f"{stamp}  {ran:5.1f}  {keep:5.1f}  {s:7.2f}  {d:7.2f}  {r:5.3f}")
    groups = {}
    for ran, keep, s, d, r in rows:
        groups.setdefault(round(keep / 10) * 10, []).append((keep, r))
    print("\nkeep_s  n  keep_s mean/sd   r mean/sd")
    for target in sorted(groups):
        g = groups[target]
        rs, ss = [x[1] for x in g], [x[0] for x in g]
        sd = lambda v: statistics.stdev(v) if len(v) > 1 else 0.0
        print(f"{target:5d}  {len(g):2d}  {statistics.mean(ss):5.1f} / {sd(ss):4.2f}   {statistics.mean(rs):5.3f} / {sd(rs):5.3f}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
