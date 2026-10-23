#!/usr/bin/env python3
"""Stand in for an MQTT-native LTN: subscribe on the dev broker's MQTT face
to the maker's rjb latest.price topic and write each arrival as one JSON
line with the laptop's receive time. Run from the scada-main venv (paho).

    python mqtt_witness.py <topic> <out.jsonl> [--host localhost] [--port 1885]
"""
import argparse, json, sys, time
import paho.mqtt.client as mqtt

ap = argparse.ArgumentParser()
ap.add_argument("topic"); ap.add_argument("out")
ap.add_argument("--host", default="localhost"); ap.add_argument("--port", type=int, default=1885)
ap.add_argument("--user", default="smqPublic"); ap.add_argument("--password", default="smqPublic")
a = ap.parse_args()
out = open(a.out, "a", buffering=1)

def on_connect(c, u, flags, rc, props=None):
    print(f"connected rc={rc}; subscribing {a.topic}", flush=True); c.subscribe(a.topic, qos=0)
def on_subscribe(c, u, mid, rcs, props=None):
    print("subscribed", flush=True)
def on_message(c, u, m):
    rec = {"received_utc_s": time.time(), "topic": m.topic, "payload": json.loads(m.payload)}
    out.write(json.dumps(rec) + "\n"); print(f"heard {m.topic} at {rec['received_utc_s']:.3f}", flush=True)

c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)
c.username_pw_set(a.user, a.password)
c.on_connect = on_connect; c.on_subscribe = on_subscribe; c.on_message = on_message
c.connect(a.host, a.port, keepalive=60); c.loop_forever()
