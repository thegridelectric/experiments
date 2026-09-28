"""Half point of maple's Siegenthaler valve from the traverses already run.

For every motor start in a window log (`Motor toward keep|send for X s
from keep_seconds Y`) and the stop that ends it, the sieg-flow and
sieg-send-flow readings from the persisted report.events are held-value
sampled every second from the start until 200 s after the stop, and the
first second at which sieg-send-flow crosses half of (sieg-flow +
sieg-send-flow) is printed with the seconds since the motor started,
the direction, and how the move ended (a full run or a stop).

    python half_point.py <window log> <events folder>
"""
import bisect
import datetime
import json
import os
import re
import sys

ET = datetime.timezone(datetime.timedelta(hours=-4))
START = re.compile(r"^(\S+ \S+) \[sieg-loop\] Motor toward (keep|send) for ([0-9.]+) s from keep_seconds ([0-9.]+)")
STOP = re.compile(r"^(\S+ \S+) \[sieg-loop\] Motor stopped after ([0-9.]+) s: keep_seconds ([0-9.]+)")


def ms(stamp):
    return int(datetime.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=ET).timestamp() * 1000)


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


def held(series, t):
    i = bisect.bisect_right([x[0] for x in series], t)
    return None if i == 0 else (series[i - 1][1] / 100, t - series[i - 1][0])


def moves(log):
    start = None
    for line in open(log):
        m = START.match(line)
        if m:
            start = (ms(m.group(1)), m.group(2), float(m.group(4)))
            continue
        m = STOP.match(line)
        if m and start:
            yield start + (ms(m.group(1)), float(m.group(2)), float(m.group(3)))
            start = None


def main(log, folder):
    flows = load(folder)
    print("start (ET)        dir   from_keep_s  ran_s  to_keep_s  ended    half at +s   sieg/send gpm at crossing")
    for t0, d, k0, t1, ran, k1 in moves(log):
        ended = "full" if ran >= 100 else f"stop@{ran:.1f}"
        found = "no crossing"
        prev = None
        for t in range(t0, t1 + 200_000, 1000):
            s, e = held(flows["sieg-flow"], t), held(flows["sieg-send-flow"], t)
            if s is None or e is None:
                continue
            tot = s[0] + e[0]
            if tot < 1:
                continue
            frac = e[0] / tot
            if prev is not None and (prev - 0.5) * (frac - 0.5) <= 0 and prev != frac:
                found = f"{(t - t0) / 1000:6.0f}     {s[0]:.2f}/{e[0]:.2f} (ages {s[1] // 1000}s/{e[1] // 1000}s)"
                break
            prev = frac
        stamp = datetime.datetime.fromtimestamp(t0 / 1000, ET).strftime("%m-%d %H:%M:%S")
        print(f"{stamp}  {d:4s}  {k0:9.1f}  {ran:6.1f}  {k1:8.1f}   {ended:9s}  {found}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
