"""Subscribe to everything on the dev broker's MQTT face for a while and
tally (topic, TypeName, Version) so we see what the sim scada emits."""
import json, sys, time, collections
import paho.mqtt.client as mqtt
tally = collections.Counter()
def on_msg(c, u, m):
    try:
        d = json.loads(m.payload)
        p = d.get("Payload", d)
        tally[(m.topic.split("/")[0] + "/" + m.topic.split("/")[-1], p.get("TypeName"), p.get("Version"))] += 1
    except Exception as e:
        tally[(m.topic, "unparsed", str(e)[:30])] += 1
c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2) if hasattr(mqtt, "CallbackAPIVersion") else mqtt.Client()
c.username_pw_set("smqPublic", "smqPublic"); c.on_message = on_msg
c.connect("localhost", 1885); c.subscribe("#"); c.loop_start(); time.sleep(int(sys.argv[1])); c.loop_stop()
for k, v in sorted(tally.items(), key=lambda kv: -kv[1]): print(v, *k)
