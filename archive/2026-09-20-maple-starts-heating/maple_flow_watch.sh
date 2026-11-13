#!/bin/bash
# Watch maple's admin snapshots for the sieg valve move. One line per snapshot.
# Runs mosquitto_sub on the box (creds read from the box .env, never printed)
# and formats on the laptop. Snapshots only flow while an admin is connected
# (gwa watch). Appends to snapshots.log beside this script.
# Usage: maple_flow_watch.sh [count]   (default: until ctrl-c)
COUNT_ARG=""
[ -n "$1" ] && COUNT_ARG="-C $1"
ssh -o BatchMode=yes maple 'getv(){ grep -E "^$1 *=" ~/gridworks-scada/.env | head -1 | sed -E "s/^[^=]*= *//; s/^\"//; s/\"$//"; }
mosquitto_sub -h localhost -p 1883 -u "$(getv SCADA_LOCAL_MQTT__USERNAME)" -P "$(getv SCADA_LOCAL_MQTT__PASSWORD)" -t "gw/+/to/admin/snapshot-spaceheat" '"$COUNT_ARG" |
python3 -u -c '
import json, sys, time
GPM = ("sieg-flow", "sieg-send", "primary-flow", "dist-flow", "store-flow")
RAW = ("hp-loop-on-off-relay14", "hp-loop-keep-send-relay15",
       "primary-pump-scada-ops-relay11", "primary-pump-failsafe-relay12", "vdc-relay1", "hp-scada-ops-relay6",
       "primary-pump-pwr", "hp-odu-pwr")
TEMP = ("hp-lwt", "hp-ewt", "sieg-cold", "sieg-hot")
BUF = ("buffer-depth1", "buffer-depth2", "buffer-depth3")
print("time(ET)  | gpm(age s): " + " ".join(GPM) + " | r14 r15 r11 r12 vdc r6 pumpW oduW | degC: " + " ".join(TEMP))
for line in sys.stdin:
    try:
        p = json.loads(line)["Payload"]
    except Exception:
        continue
    now = p["SnapshotTimeUnixMs"] / 1000
    r = {x["ChannelName"]: x for x in p["LatestReadingList"]}
    def cell(name, scale, fmt):
        x = r.get(name)
        if x is None:
            return "--"
        age = int(now - x["ScadaReadTimeUnixMs"] / 1000)
        return fmt.format(x["Value"] / scale) + f"({age})"
    print(time.strftime("%H:%M:%S", time.localtime(now)), "|",
          " ".join(cell(n, 100, "{:.2f}") for n in GPM), "|",
          " ".join(cell(n, 1, "{:.0f}") for n in RAW), "|",
          " ".join(cell(n, 1000, "{:.1f}") for n in TEMP), "|",
          " ".join(cell(n, 100, "{:.1f}") for n in BUF), flush=True)
' | tee -a "$(dirname "$0")/snapshots.log"
