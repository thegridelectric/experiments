"""The box-side snapshot watcher this window ran (from /tmp, not from the
~/experiments clone; kept here as the script that produced flow.log).
Subscribes to the window scada's snapshots on the box mosquitto and prints
the four flow channels and three relay states per snapshot. Hand-parses
the snapshot dict instead of decoding SnapshotSpaceheat, against the sema
maxim, and prints each state's enum type name instead of its value (the
"states:" column in flow.log is wrong for that reason). Superseded by
extract_window.py over the scada's report events; flow.log remains the
only record of the 10:29:37 OpenValve recovery, after the last report.
"""
import json, os, sys, time
import paho.mqtt.client as mqtt
pw = [l.split("=",1)[1].strip().strip(chr(34)) for l in open(os.path.expanduser("~/envs/dev.env")) if l.startswith("SCADA_LOCAL_MQTT__PASSWORD")][0]
def on_msg(c, u, m):
    try:
        d = json.loads(m.payload)
        d = d.get("Payload", d)
        snap = d.get("Snapshot", d)
        readings = snap.get("LatestReadingList", [])
        want = {r["ChannelName"]: (r["Value"], r["ScadaReadTimeUnixMs"]) for r in readings if r.get("ChannelName") in ("secondary-flow","primary-flow","store-flow","dist-flow")}
        states = {s["MachineHandle"].split(".")[-1]: s["StateEnum"] if "StateEnum" in s else s.get("State") for s in snap.get("LatestStateList", []) if any(k in s.get("MachineHandle","") for k in ("secondary-pump","iso-valve","vdc"))}
        print(time.strftime("%H:%M:%S"), "flow:", {k: v[0] for k, v in want.items()}, "states:", states, flush=True)
    except Exception as e:
        print("parse err", e, m.topic, flush=True)
c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
c.username_pw_set("sara", pw); c.on_message = on_msg
c.connect("localhost", 1883, 60); c.subscribe("gw/+/to/+/snapshot-spaceheat"); c.loop_forever()
