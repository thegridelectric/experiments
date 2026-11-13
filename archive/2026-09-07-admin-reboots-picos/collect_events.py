"""Copy the scada's persisted report events for a window into instances/ and
print the pico-cycler evidence they carry: the roster rows, the cycler and
vdc-relay state rows, and every fsm.full.report with its TriggerId.
Usage: collect_events.py <start ET HH:MM> <end ET HH:MM> [event-dir]"""
import glob
import json
import os
import shutil
import sys
from datetime import date, datetime, timedelta, timezone

start, end = sys.argv[1], sys.argv[2]
ET = timezone(timedelta(hours=-4))
today = date.today()
lo = datetime.combine(today, datetime.strptime(start, "%H:%M").time(), ET).astimezone(timezone.utc)
hi = datetime.combine(today, datetime.strptime(end, "%H:%M").time(), ET).astimezone(timezone.utc)
event_dir = sys.argv[3] if len(sys.argv) > 3 else os.path.expanduser(
    f"~/.local/share/gridworks/scada/event/{today.isoformat()}T00:00:00+00:00")
here = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(here, "instances"), exist_ok=True)
NAMES = ("pico-cycler", "vdc-relay", "buffer", "tank1")
for f in sorted(glob.glob(os.path.join(event_dir, "*.json"))):
    stamp = datetime.fromisoformat(os.path.basename(f)[:32])
    if not lo <= stamp <= hi:
        continue
    e = json.load(open(f))
    if e.get("TypeName") != "report.event":
        continue
    r = e["Report"]
    dst = os.path.join(here, "instances", f"{stamp.astimezone(ET).strftime('%H%M')}-report.event-{e['Version']}.json")
    shutil.copyfile(f, dst)
    print(f"== {stamp.astimezone(ET).strftime('%H:%M:%S')} ET  slot {r['SlotStartUnixS']}  -> {os.path.relpath(dst, here)}")
    for m in r["StateList"]:
        name = m["MachineHandle"].split(".")[-1]
        if name in NAMES:
            times = [datetime.fromtimestamp(u / 1000, ET).strftime("%H:%M:%S.%f")[:-3] for u in m["UnixMsList"]]
            print(f"   {m['MachineHandle']:36} {list(zip(m['StateList'], times))}")
    for x in r["FsmReportList"]:
        print(f"   fsm.full.report {x['FromName']} trigger={x['TriggerId']} "
              + " ".join(f"{a['Event']}:{a['FromState']}->{a['ToState']}" for a in x["AtomicList"]))
