"""Read a Siegenthaler valve's positions out of the journal after a drive.

For every motor run in the window (the hp-loop-on-off relay channel leaving
its resting value and returning to it), the flow readings are held-value
sampled every second from the motor start to 200 s after the stop, the kept
fraction r is formed, and the seconds after the motor start at which r
leaves its starting plateau (onset), crosses one half (half) and reaches its
ending plateau (complete) are printed, with the direction read from the
flow itself and the keep-send relay value beside it.

The kept fraction is `sieg / total` where the house measures primary flow
(beech: --sieg sieg-flow --total primary-flow, the default), or
`sieg / (sieg + send)` where it measures the send line and derives the
total (maple: --sieg sieg-flow --send sieg-send-flow).

    uv run python positions.py --house beech \\
        --start '2026-11-13 15:00' --end '2026-11-13 16:00' [--lag-s 4]

Reads the journal through the repo's spot_check.py (DB_ANALYST_URL in
the repo's .env). --lag-s subtracts a meter answer lag from every crossing; the
lag itself comes from the stop runs (README "Reading the positions").
"""
import argparse
import bisect
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import spot_check  # noqa: E402

ON_OFF = "hp-loop-on-off-relay"
KEEP_SEND = "hp-loop-keep-send-relay"
TAIL_S = 200          # after the stop, cut short by the next motor start
LEAD_S = 1200         # readings pulled before the window so held values exist at its start
PLATEAU_BAND = 0.08  # r within this of a plateau counts as on it


def series(reports, names):
    rows = {n: [] for n in names}
    for rep in reports:
        for c in rep["ChannelReadingList"]:
            if c["ChannelName"] in rows:
                rows[c["ChannelName"]] += list(zip(c["ScadaReadTimeUnixMsList"], c["ValueList"]))
    return {k: sorted(set(v)) for k, v in rows.items()}


def held(s, t_ms):
    """Value of a sorted [(ms, v)] series held at t_ms; None before its first sample."""
    i = bisect.bisect_right([t for t, _ in s], t_ms)
    return None if i == 0 else s[i - 1][1]


def motor_runs(on_off):
    """[(start_ms, stop_ms_or_None)] from the on-off relay leaving its resting value."""
    pts = spot_check.collapse(on_off)
    if not pts:
        return []
    rest = statistics.mode(v for _, v in on_off)
    runs, start = [], None
    for t, v in pts:
        if v != rest and start is None:
            start = t
        elif v == rest and start is not None:
            runs.append((start, t))
            start = None
    if start is not None:
        runs.append((start, None))
    return runs


def kept_fraction(flows, args, t_ms):
    sieg = held(flows[args.sieg], t_ms)
    if sieg is None:
        return None
    if args.send:
        send = held(flows[args.send], t_ms)
        if send is None or sieg + send == 0:
            return None
        return sieg / (sieg + send)
    total = held(flows[args.total], t_ms)
    if not total:
        return None
    return min(1.0, sieg / total)


def crossings(r):
    """r: [(sec, value)]. Onset, half and complete in seconds, and the direction."""
    vals = [v for _, v in r if v is not None]
    if len(vals) < 5:
        return None
    r0, r1 = vals[0], vals[-1]
    if abs(r1 - r0) < 0.3:
        return None
    toward_keep = r1 > r0
    onset = half = complete = None
    for sec, v in r:
        if v is None:
            continue
        if onset is None and abs(v - r0) > PLATEAU_BAND:
            onset = sec
        if half is None and ((v >= 0.5) if toward_keep else (v <= 0.5)):
            half = sec
        if onset is not None and complete is None and abs(v - r1) <= PLATEAU_BAND:
            complete = sec
    return toward_keep, onset, half, complete, r0, r1


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--house", choices=sorted(spot_check.KNOWN_HOUSES))
    g.add_argument("--scada")
    ap.add_argument("--start", required=True, help="ET, 'YYYY-MM-DD HH:MM'")
    ap.add_argument("--end", required=True)
    ap.add_argument("--sieg", default="sieg-flow")
    ap.add_argument("--total", default="primary-flow", help="measured total flow channel")
    ap.add_argument("--send", default=None, help="measured send-line channel; the total is then sieg + send")
    ap.add_argument("--lag-s", type=float, default=0.0, help="meter answer lag taken off every crossing")
    args = ap.parse_args()
    scada = args.scada or spot_check.KNOWN_HOUSES[args.house]
    start_ms, end_ms = spot_check.et_ms(args.start), spot_check.et_ms(args.end)
    reports = spot_check.fetch_reports(scada, start_ms - LEAD_S * 1000, end_ms)
    names = [ON_OFF, KEEP_SEND, args.sieg] + ([args.send] if args.send else [args.total])
    s = series(reports, names)
    flows = {n: s[n] for n in names[2:]}
    runs = [r for r in motor_runs(s[ON_OFF]) if r[0] >= start_ms]
    print(f"{scada}  {args.start} -> {args.end} ET  {len(reports)} report.event  {len(runs)} motor runs")
    print(f"{'start ET':>17} {'ran s':>6} {'ks relay':>8} {'toward':>6} {'onset':>6} {'half':>6} {'complete':>8} {'r0':>5} {'r1':>5}")
    for i, (start, stop) in enumerate(runs):
        ran = None if stop is None else (stop - start) / 1000
        end = (stop if stop else start) + TAIL_S * 1000
        if i + 1 < len(runs):
            end = min(end, runs[i + 1][0] - 1000)
        r = [((t - start) / 1000 - args.lag_s, kept_fraction(flows, args, t)) for t in range(start, end + 1, 1000)]
        c = crossings(r)
        ks = held(s[KEEP_SEND], start + 500)
        if c is None:
            print(f"{spot_check.et_str(start):>17} {ran if ran is not None else '-':>6} {ks!s:>8}   (flow did not change)")
            continue
        toward_keep, onset, half, complete, r0, r1 = c
        fmt = lambda x: "-" if x is None else f"{x:.0f}"
        print(f"{spot_check.et_str(start):>17} {fmt(ran):>6} {ks!s:>8} {'keep' if toward_keep else 'send':>6} "
              f"{fmt(onset):>6} {fmt(half):>6} {fmt(complete):>8} {r0:5.2f} {r1:5.2f}")


if __name__ == "__main__":
    main()
