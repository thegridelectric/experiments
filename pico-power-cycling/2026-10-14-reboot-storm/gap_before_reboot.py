"""For each pico-cycler RelayOpening in a window: seconds since the last
microvolts post of each tank pico (depth1 channel), to test whether reboots
fire at exactly the 60 s missing threshold."""
import sys, datetime
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
import spot_check as sc
house, start, end = sys.argv[1:4]
reps = sc.fetch_reports(sc.KNOWN_HOUSES[house], sc.et_ms(start), sc.et_ms(end))
opens = []; posts = {}
for rep in reps:
    for s in rep.get("StateList", []):
        if s["StateEnum"] == "pico.cycler.state":
            for t, v in zip(s["UnixMsList"], s["StateList"]):
                if v == "RelayOpening": opens.append(t)
    for c in rep.get("ChannelReadingList", []):
        n = c["ChannelName"]
        if n.endswith("-depth1"):
            posts.setdefault(n, []).extend(c["ScadaReadTimeUnixMsList"])
opens = sorted(set(opens)); 
for n in posts: posts[n].sort()
def f(ms): return datetime.datetime.fromtimestamp(ms/1000, tz=sc.ET).strftime("%m-%d %H:%M:%S.%f")[:-3]
print(f"{house} {start}..{end}: {len(opens)} RelayOpening; tank channels {sorted(posts)}")
for o in opens:
    gaps = []
    for n in sorted(posts):
        prev = [t for t in posts[n] if t < o]
        if prev: gaps.append((round((o - prev[-1])/1000, 2), n.replace('-depth1','')))
    gaps.sort()
    print(f"  {f(o)}  min gap {gaps[0][0]:7.2f}s ({gaps[0][1]})   all: {' '.join(f'{g}:{n}' for g,n in gaps)}")
