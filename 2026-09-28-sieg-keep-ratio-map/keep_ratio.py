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
each direction. The same rows go to `keep-ratio-<stamp>.csv` beside the
log, one number per cell, through the repo's tables.py.

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
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from tables import Table, write_csv  # noqa: E402

SPAN_MS = (60_000, 150_000)
STEP_MS = 10_000
MAX_AGE_MS = 300_000
STOP = re.compile(r"^(\S+ \S+) \[sieg-loop\] Motor stopped after ([0-9.]+) s: keep_seconds ([0-9.]+)")
START = re.compile(r"^\S+ \S+ \[sieg-loop\] Motor toward (keep|send) for")
KEEP_STOP_S = 94.0
FULL_RUN_S = 100.0
ET = datetime.timezone(datetime.timedelta(hours=-4))


class StopRow(NamedTuple):
    """One settled stop: where the valve was left and the kept fraction read there.
    No sema word holds a valve-position map; a word for it retires this."""

    stop_et: str
    toward: str  # the direction the motor ran before the stop
    ran_s: float
    position_s: float  # seconds from the send stop, nominal when approached from keep
    sieg_gpm: float
    send_gpm: float
    r: float


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


def settled(log, folder) -> list[StopRow]:
    """Every settled stop with fresh readings; a stale run is printed and left out."""
    flows = load(folder)
    rows = []
    for t0, direction, ran, pos in stops(log):
        sieg, send = held(flows["sieg-flow"], t0), held(flows["sieg-send-flow"], t0)
        stamp = datetime.datetime.fromtimestamp(t0 / 1000, ET).strftime("%m-%d %H:%M:%S")
        if sieg is None or send is None:
            which = " ".join(n for n, v in (("sieg", sieg), ("send", send)) if v is None)
            print(f"{stamp}  {direction:4s}   {ran:5.1f}  {pos:5.1f}  DISCARDED: stale {which} reading in span")
            continue
        s, d = statistics.median(sieg), statistics.median(send)
        r = s / (s + d) if s + d else float("nan")
        rows.append(StopRow(stamp, direction, ran, pos, s, d, r))
    return rows


def table(log, rows: list[StopRow]) -> Table:
    stamp = log.stem.rsplit("-", 2)[-2] + "-" + log.stem.rsplit("-", 1)[-1]
    return Table(f"keep-ratio-{stamp}", f"Maple, window {stamp}: each settled Siegenthaler valve stop, its position from the send stop and the kept fraction r at rest",
                 ("StopEt", "Toward", "RanS", "PositionS", "SiegGpm", "SendGpm", "R"),
                 [(x.stop_et, x.toward, round(x.ran_s, 1), round(x.position_s, 1), round(x.sieg_gpm, 2),
                   round(x.send_gpm, 2), round(x.r, 3)) for x in rows], "keep_ratio.py")


def main(log, folder):
    print("stop (ET)        toward  ran_s  pos_s  sieg_gpm  send_gpm  r")
    rows = settled(log, folder)
    for x in rows:
        print(f"{x.stop_et}  {x.toward:4s}   {x.ran_s:5.1f}  {x.position_s:5.1f}  {x.sieg_gpm:7.2f}  {x.send_gpm:7.2f}  {x.r:5.3f}")
    groups = {}
    for x in rows:
        groups.setdefault(round(x.position_s / 3) * 3, []).append((x.toward, x.r))
    print("\npos_s  n  toward keep / send   r mean/sd")
    for pos in sorted(groups):
        g = groups[pos]
        rs = [x[1] for x in g]
        nk = sum(1 for x in g if x[0] == "keep")
        sd = statistics.stdev(rs) if len(rs) > 1 else 0.0
        print(f"{pos:5.0f}  {len(g):2d}  {nk:2d} / {len(g) - nk:2d}           {statistics.mean(rs):5.3f} / {sd:5.3f}")
    print(f"\nwrote {write_csv(table(log, rows).check(), log.parent).name}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(Path(sys.argv[1]), Path(sys.argv[2]))
