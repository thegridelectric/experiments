"""Record everything the window scada sends the dev broker (reports every
5 min, events) as one JSON line per message: {"t": receipt UTC s, "topic",
"payload"}. Raw capture only; readers decode through gwsproto. Creds are
the scada's dev-broker pair from gridworks-scada/.env.

    ../../gridworks-scada/gw_spaceheat/venv/bin/python rig_record.py rig-log/dev-broker.jsonl
"""
import json
import sys
import time
from pathlib import Path

import paho.mqtt.client as mqtt

env = {}
for line in (Path(__file__).parents[2] / "gridworks-scada" / ".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
out = open(sys.argv[1], "a")


def on_msg(c, u, m):
    out.write(json.dumps({"t": time.time(), "topic": m.topic, "payload": m.payload.decode()}) + "\n")
    out.flush()


c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
c.username_pw_set(env["SCADA_GRIDWORKS_MQTT__USERNAME"], env["SCADA_GRIDWORKS_MQTT__PASSWORD"])
c.on_message = on_msg
c.connect("localhost", 1885, 60)
c.subscribe("gw/#")
c.loop_forever()
