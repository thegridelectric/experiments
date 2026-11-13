"""Loop volume of maple's Siegenthaler loop from the closed starts of 2026-09-28.

Model: a closed loop at full keep with no losses and one unknown, its
water volume V. Over any interval, V x (rise in hp-lwt) = integral of
sieg-flow x (hp-lwt - hp-ewt) dt. The integral is a trapezoid sum over
the hp-lwt readings in each report.event, with hp-ewt interpolated to
each hp-lwt stamp and sieg-flow the last reading before it (5.0 to
5.1 gpm throughout). Chunks are disjoint 60 s windows that begin where
the lift (hp-lwt - hp-ewt) is 1.5 to 2.5 F, taken from the report.events
each window scada persisted (the maple-events-* folders here); the nine
below are the ones during a compressor run into the kept loop, the
others (a valve move, a cool-down) are listed by the finder but not fit.

    python loop_volume.py            # the nine chunks, V per chunk, mean
    python loop_volume.py --offset 0.65   # add the same-water sensor offset back to the lift
"""
import bisect
import datetime
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
F = lambda v: v / 100 * 1.8 + 32  # CelsiusTimes100 -> F
CHUNKS = [  # (events folder, chunk start, box clock ET)
    ("maple-events", "07:07:33"), ("maple-events", "07:08:36"),
    ("maple-events-130239", "12:53:17"), ("maple-events-130239", "12:55:57"),
    ("maple-events-143041", "14:22:41"), ("maple-events-143041", "14:23:41"), ("maple-events-143041", "14:24:42"),
    ("maple-events-145033", "14:44:38"), ("maple-events-145033", "14:45:39"),
]


def load(folder):
    rows = {"hp-lwt": [], "hp-ewt": [], "sieg-flow": []}
    for root, _, files in os.walk(HERE / folder):
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


def interp(series, t, max_gap_ms=60000):
    ts = [x[0] for x in series]
    i = bisect.bisect_left(ts, t)
    if i == 0 or i >= len(ts):
        return None
    (t0, v0), (t1, v1) = series[i - 1], series[i]
    return None if t1 - t0 > max_gap_ms else v0 + (v1 - v0) * (t - t0) / (t1 - t0)


def last_before(series, t):
    i = bisect.bisect_right([x[0] for x in series], t)
    return series[i - 1] if i else None


def fit(offset_f=0.0):
    data = {}
    out = []
    for folder, start in CHUNKS:
        r = data.setdefault(folder, load(folder))
        t0 = int(datetime.datetime.strptime("2026-09-28 " + start, "%Y-%m-%d %H:%M:%S").timestamp() * 1000)
        ewt = [(t, F(v)) for t, v in r["hp-ewt"]]
        flow = [(t, v / 100) for t, v in r["sieg-flow"]]
        pts = []
        for t, v in r["hp-lwt"]:
            if not t0 <= t <= t0 + 60000:
                continue
            e = interp(ewt, t)
            fl = last_before(flow, t)
            if e is not None and fl is not None:
                pts.append((t, F(v), e, fl[1]))
        integ = 0.0
        for (ta, va, ea, fa), (tb, vb, eb, fb) in zip(pts, pts[1:]):
            integ += 0.5 * (fa * (va - ea + offset_f) + fb * (vb - eb + offset_f)) * (tb - ta) / 60000
        rise = pts[-1][1] - pts[0][1]
        lift = sum(v - e for _, v, e, _ in pts) / len(pts)
        fmean = sum(f for *_, f in pts) / len(pts)
        out.append((start, pts[0][1], pts[-1][1], lift, fmean, integ, rise, integ / rise))
    return out


if __name__ == "__main__":
    offset = float(sys.argv[sys.argv.index("--offset") + 1]) if "--offset" in sys.argv else 0.0
    rows = fit(offset)
    print(f"offset added to lift: {offset:.2f} F")
    print("start     lwt F          lift F  gpm   int gal*F  rise F  V gal  transit s")
    for start, a, b, lift, fmean, integ, rise, V in rows:
        print(f"{start}  {a:5.1f}->{b:5.1f}   {lift:4.2f}   {fmean:4.2f}   {integ:6.2f}    {rise:5.1f}   {V:5.2f}   {V / fmean * 60:5.1f}")
    vs = sorted(V for *_, V in rows)
    print(f"V mean {sum(vs) / len(vs):.2f} gal, median {vs[len(vs) // 2]:.2f}, range {vs[0]:.2f}-{vs[-1]:.2f}")
