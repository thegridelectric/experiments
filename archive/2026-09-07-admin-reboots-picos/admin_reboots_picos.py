"""The admin client asks the pico-cycler to reboot the picos on the sim Nolan
scada over the dev broker, while a plain subscription on gw/# captures the
scada's gridworks-link traffic (the journal-bound reports).
Usage: admin_reboots_picos.py <drive.log> <broker-capture.jsonl>
Environment (defaults are the dev broker): PICO_DRIVE_SCADA, PICO_DRIVE_PORT,
PICO_DRIVE_USER, PICO_DRIVE_PASS."""
import asyncio
import json
import os
import sys
import time

import paho.mqtt.client as mqtt
from gwadmin.config import AdminConfig, AdminMQTTClient, CurrentAdminConfig, ScadaConfig
from gwadmin.watch.clients.admin_client import AdminClient, AdminClientCallbacks
from gwadmin.watch.clients.relay_client import RelayWatchClient
from gwproactor.config.mqtt import TLSInfo
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.named_types import AdminDispatch, AdminReleaseControl, SendSnap

SCADA = os.environ.get("PICO_DRIVE_SCADA", "d1.isone.me.versant.keene.spruce.scada")
PORT = int(os.environ.get("PICO_DRIVE_PORT", "1885"))
USER = os.environ.get("PICO_DRIVE_USER", "smqPublic")
PASS = os.environ.get("PICO_DRIVE_PASS", "smqPublic")
WATCH_S = 180
RETRY_S = 90
MAX_TRIES = 3

log = open(sys.argv[1], "w")
capture = open(sys.argv[2], "w")
INTEREST = ("pico-cycler", "vdc-relay", "buffer", "tank1")


def note(s: str) -> None:
    log.write(f"{time.strftime('%H:%M:%S')} {s}\n")
    log.flush()


state = {"mqtt": None, "cycler": None, "full_reports": [], "dispatches": []}


def on_state(old, new):
    state["mqtt"] = new
    note(f"mqtt {old} -> {new}")


def on_msg(topic, payload):
    try:
        p = json.loads(payload)["Payload"]
        t = p.get("TypeName")
        if t == "single.machine.state":
            if p.get("MachineHandle", "").endswith(INTEREST):
                note(f"RX {t} {p.get('MachineHandle')} {p.get('StateEnum')}={p.get('State')}")
                if p.get("MachineHandle", "").endswith("pico-cycler"):
                    state["cycler"] = p.get("State")
        elif t == "fsm.full.report":
            a = p.get("AtomicList", [{}])
            note(f"RX {t} from={p.get('FromName')} trigger={p.get('TriggerId')} "
                 + " ".join(f"{x.get('Event')}:{x.get('FromState')}->{x.get('ToState')}" for x in a))
            state["full_reports"].append(p)
        elif t == "snapshot.spaceheat":
            states = {m["MachineHandle"]: (m["State"], m["UnixMs"]) for m in p.get("LatestStateList", [])
                      if m["MachineHandle"].endswith(INTEREST)}
            for h, (s, _) in states.items():
                if h.endswith("pico-cycler"):
                    state["cycler"] = s
            note(f"RX snapshot {states}")
        elif t == "new.command.tree":
            hb = [n for n in p.get("ShNodes", []) if n.get("Name") in ("pico-cycler", "vdc-relay")]
            note(f"RX {t} " + " ".join(f"{n['Name']}@{n.get('Handle')}" for n in hb))
        else:
            note(f"RX {t}")
    except Exception as e:  # noqa: BLE001
        note(f"RX ? {topic} {e}")


def on_broker(client, userdata, msg):
    capture.write(json.dumps({"t": time.time(), "topic": msg.topic, "payload": msg.payload.decode()}) + "\n")
    capture.flush()
    try:
        p = json.loads(msg.payload)["Payload"]
        if p.get("TypeName") == "report":
            rows = [f"{m['MachineHandle'].split('.')[-1]}={m['StateList']}" for m in p.get("StateList", [])
                    if m["MachineHandle"].endswith(INTEREST)]
            fsm = [f"{r['FromName']}:{r['TriggerId'][:8]}:" + ",".join(a['Event'] for a in r['AtomicList'])
                   for r in p.get("FsmReportList", [])]
            note(f"BROKER report states={rows} fsm={fsm}")
    except Exception as e:  # noqa: BLE001
        note(f"BROKER ? {msg.topic} {e}")


cfg = CurrentAdminConfig(
    config=AdminConfig(scadas={"spruce-sim": ScadaConfig(long_name=SCADA, mqtt=AdminMQTTClient(
        host="localhost", port=PORT, username=USER, password=PASS, tls=TLSInfo(use_tls=False)))}),
    curr_scada="spruce-sim")
relay_client = RelayWatchClient()
client = AdminClient(
    cfg,
    AdminClientCallbacks(mqtt_state_change_callback=on_state, mqtt_message_received_callback=on_msg),
    subclients=[relay_client],
)
orig_publish = client.publish


def publish(payload):
    if isinstance(payload, AdminDispatch):
        state["dispatches"].append(payload.DispatchTrigger.TriggerId)
        note(f"TX admin.dispatch {payload.DispatchTrigger.EventName} -> {payload.DispatchTrigger.ToHandle} "
             f"trigger={payload.DispatchTrigger.TriggerId}")
    return orig_publish(payload)


client.publish = publish

broker = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
broker.username_pw_set(USER, PASS)
broker.on_message = on_broker
broker.connect("localhost", PORT)
broker.subscribe("gw/#")
broker.loop_start()


async def main():
    client.start()
    for _ in range(100):
        if state["mqtt"] == "active":
            break
        await asyncio.sleep(0.1)
    note(f"link {state['mqtt']}")
    note(f"watching {WATCH_S}s for the self-provoked cycle")
    await asyncio.sleep(WATCH_S)
    client.publish(SendSnap(FromGNodeAlias=H0N.admin))
    await asyncio.sleep(3)
    # The cycler's own fsm.full.report rides the journal-bound report stream,
    # not the admin link, so a command is judged taken on the admin side by
    # the cycler's snapshot state leaving PicosLive and coming back; the id
    # is checked afterwards in the persisted report events (collect_events.py).
    # A command sent mid-cycle is ignored by design; re-send after RETRY_S.
    taken = None
    for i in range(MAX_TRIES):
        relay_client.send_reboot_picos(300)
        sent_id = state["dispatches"][-1]
        left_live = False
        for _ in range(RETRY_S // 2):
            client.publish(SendSnap(FromGNodeAlias=H0N.admin))
            await asyncio.sleep(2)
            if state["cycler"] != "PicosLive":
                left_live = True
            elif left_live:
                taken = sent_id
                break
        note(f"try {i + 1}: {'taken, cycle complete' if taken else 'not taken, re-sending'}")
        if taken:
            break
    if taken:
        note(f"PASS(a, admin side): commanded cycle ran to PicosLive; dispatch {taken}")
    else:
        note("FAIL(a, admin side): no commanded cycle observed")
    client.publish(SendSnap(FromGNodeAlias=H0N.admin))
    await asyncio.sleep(4)
    note("TX admin.release.control")
    client.publish(AdminReleaseControl())
    await asyncio.sleep(70)
    client.stop()
    broker.loop_stop()
    note("done")


asyncio.run(main())
