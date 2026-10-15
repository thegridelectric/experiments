import sys, datetime
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
import spot_check as sc
scada = sc.KNOWN_HOUSES[sys.argv[1]]
reps = sc.fetch_reports(scada, sc.et_ms(sys.argv[2]), sc.et_ms(sys.argv[3]))
want = set(sys.argv[4:])
def f(ms): return datetime.datetime.fromtimestamp(ms/1000, tz=sc.ET).strftime("%H:%M:%S.%f")[:-3]
out = {}
for r in reps:
    for c in r.get("ChannelReadingList", []):
        if c["ChannelName"] in want:
            out.setdefault(c["ChannelName"], set()).update(c["ScadaReadTimeUnixMsList"])
    for s in r.get("StateList", []):
        if s["MachineHandle"] == "auto.pico-cycler":
            out.setdefault("cycler", set()).update(zip(s["UnixMsList"], s["StateList"]))
for k, v in out.items():
    print(f"== {k} ({len(v)})")
    for x in sorted(v):
        print("  ", f(x[0]) + " " + x[1] if isinstance(x, tuple) else f(x))
