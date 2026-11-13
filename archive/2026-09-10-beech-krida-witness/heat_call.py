"""Admin takes one beech zone and makes a heat call through the window
scada: SwitchToScada on the zone's failsafe relay, CloseRelay on its ops
relay, a hold while the Caleffi zone control box starts the distribution
pump (about 40 s), then the call released, the failsafe back to the wall
thermostat, admin released. Snapshots are requested every SNAP_EVERY_S
throughout and the distribution flow and pump power rows are logged, so
the hold is the observation. Runs on the laptop: the admin link is beech's
own mosquitto over tailscale, the scada's journal-bound reports are
captured off the laptop's gw-dev-rabbit (the window's upstream through
the ssh -R 1885 tunnel).

Usage: heat_call.py <drive.log> <broker-capture.jsonl>
Environment: HEAT_CALL_ZONE (default zone1-down), HOLD_S (default 180),
HEAT_CALL_SCADA (the scada alias), ADMIN_HOST/ADMIN_PORT/ADMIN_USER/
ADMIN_PASS (default beech's mosquitto over tailscale, creds from
~/.config/gridworks/admin/admin-config.json "beech"), DEV_BROKER_PORT
(default 1885). The dev rung runs the House0 sim fixture on the dev
broker with the admin link on the same broker:
  HEAT_CALL_SCADA=d1.isone.ct.newhaven.orange1.scada HEAT_CALL_ZONE=zone1-main \
  ADMIN_HOST=localhost ADMIN_PORT=1885 ADMIN_USER=smqPublic ADMIN_PASS=smqPublic
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import paho.mqtt.client as mqtt
from gwadmin.config import AdminConfig, AdminMQTTClient, CurrentAdminConfig, ScadaConfig
from gwadmin.watch.clients.admin_client import AdminClient, AdminClientCallbacks
from gwadmin.watch.clients.dispatch_replies import DispatchReply
from gwadmin.watch.clients.relay_client import RelayClientCallbacks, RelayWatchClient
from gwproactor.config.mqtt import TLSInfo
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.named_types import AdminDispatch, AdminReleaseControl, SendSnap

SCADA = os.environ.get("HEAT_CALL_SCADA", "hw1.isone.me.versant.keene.beech.scada")
ADMIN_HOST = os.environ.get("ADMIN_HOST", "100.100.103.111")
ADMIN_PORT = int(os.environ.get("ADMIN_PORT", "1883"))
DEV_BROKER_PORT = int(os.environ.get("DEV_BROKER_PORT", "1885"))
ZONE = os.environ.get("HEAT_CALL_ZONE", "zone1-down")
FAILSAFE = f"{ZONE}-failsafe-relay"
OPS = f"{ZONE}-ops-relay"
HOLD_S = int(os.environ.get("HOLD_S", "180"))
BOOT_WATCH_S = 60
SNAP_EVERY_S = 10
STEP_TIMEOUT_S = 60
DISPATCH_TIMEOUT_S = 900
WATCH_CHANNELS = ("dist-flow", "dist-flow2", "dist-pump-pwr", "dist-swt", "dist-rwt")

if "ADMIN_USER" in os.environ:
    ADMIN_USER = os.environ["ADMIN_USER"]
    ADMIN_PASS = os.environ["ADMIN_PASS"]
else:
    admin_cfg = json.loads((Path("~/.config/gridworks/admin/admin-config.json").expanduser()).read_text())
    ADMIN_USER = admin_cfg["scadas"]["beech"]["mqtt"]["username"]
    ADMIN_PASS = admin_cfg["scadas"]["beech"]["mqtt"]["password"]

log = open(sys.argv[1], "w")
capture = open(sys.argv[2], "w")


def note(s: str) -> None:
    log.write(f"{time.strftime('%H:%M:%S')} {s}\n")
    log.flush()


state = {"mqtt": None, "relays": {}, "channels": {}, "replies": [], "dispatches": []}


def on_state(old, new):
    state["mqtt"] = new
    note(f"mqtt {old} -> {new}")


def on_msg(topic, payload):
    try:
        p = json.loads(payload)["Payload"]
        t = p.get("TypeName")
        if t == "single.machine.state":
            h = p.get("MachineHandle", "")
            leaf = h.split(".")[-1]
            if leaf in (FAILSAFE, OPS):
                state["relays"][leaf] = p.get("State")
                note(f"RX {t} {h} {p.get('State')}")
        elif t == "snapshot.spaceheat":
            for m in p.get("LatestStateList", []):
                leaf = m["MachineHandle"].split(".")[-1]
                if leaf in (FAILSAFE, OPS):
                    state["relays"][leaf] = m["State"]
            rows = {r["ChannelName"]: r["Value"] for r in p.get("LatestReadingList", [])
                    if r.get("ChannelName") in WATCH_CHANNELS}
            state["channels"] = rows
            note(f"RX snapshot relays={state['relays']} {rows}")
        elif t in ("gw.dispatch.ack", "gw.dispatch.nack"):
            note(f"RX {t} {json.dumps(p)}")
        else:
            note(f"RX {t}")
    except Exception as e:  # noqa: BLE001
        note(f"RX ? {topic} {e}")


def on_reply(reply: DispatchReply) -> None:
    r = reply.reply
    state["replies"].append(r)
    label = reply.pending.label if reply.pending else "?"
    note(f"REPLY {r.TypeName} for {label} trigger={getattr(r, 'TriggerId', '?')} "
         f"{'reason=' + str(getattr(r, 'Reason', '')) if r.TypeName.endswith('nack') else ''}")


def on_broker(client, userdata, msg):
    capture.write(json.dumps({"t": time.time(), "topic": msg.topic, "payload": msg.payload.decode()}) + "\n")
    capture.flush()
    try:
        p = json.loads(msg.payload)["Payload"]
        if p.get("TypeName") == "report":
            rows = [f"{m['MachineHandle'].split('.')[-1]}={m['StateList']}" for m in p.get("StateList", [])
                    if m["MachineHandle"].split(".")[-1] in (FAILSAFE, OPS)]
            readings = [f"{c['ChannelName']}={c['ValueList']}" for c in p.get("ChannelReadingList", [])
                        if c.get("ChannelName") in WATCH_CHANNELS]
            note(f"BROKER report states={rows} readings={readings}")
    except Exception as e:  # noqa: BLE001
        note(f"BROKER ? {msg.topic} {e}")


cfg = CurrentAdminConfig(
    config=AdminConfig(scadas={"beech": ScadaConfig(long_name=SCADA, mqtt=AdminMQTTClient(
        host=ADMIN_HOST, port=ADMIN_PORT, username=ADMIN_USER, password=ADMIN_PASS,
        tls=TLSInfo(use_tls=False)))}),
    curr_scada="beech")
relay_client = RelayWatchClient(callbacks=RelayClientCallbacks(dispatch_reply_callback=on_reply))
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
broker.username_pw_set("smqPublic", os.environ.get("DEV_BROKER_PASS", "smqPublic"))
broker.on_message = on_broker
broker.connect("localhost", DEV_BROKER_PORT)
broker.subscribe("gw/#")
broker.loop_start()

verdicts: list[str] = []


def verdict(ok: bool, what: str) -> None:
    verdicts.append(f"{'PASS' if ok else 'FAIL'} {what}")
    note(verdicts[-1])


async def snap() -> None:
    client.publish(SendSnap(FromGNodeAlias=H0N.admin))
    await asyncio.sleep(2)


async def wait_for(what: str, cond, timeout_s: int = STEP_TIMEOUT_S) -> bool:
    for _ in range(timeout_s // 2):
        await snap()
        if cond():
            verdict(True, f"{what}: relays={state['relays']}")
            return True
    verdict(False, f"{what} within {timeout_s}s: relays={state['relays']}")
    return False


async def command(relay: str, event: str, expect_state: str, label: str) -> None:
    note(f"{label} {event} -> {relay}")
    n_replies = len(state["replies"])
    relay_client.send_command(relay, event, DISPATCH_TIMEOUT_S)
    await wait_for(f"{label} reply", lambda: len(state["replies"]) > n_replies, 30)
    await wait_for(f"{label} {relay} reads {expect_state}", lambda: state["relays"].get(relay) == expect_state)


async def main():
    client.start()
    for _ in range(100):
        if state["mqtt"] == "active":
            break
        await asyncio.sleep(0.1)
    note(f"link {state['mqtt']}")
    note(f"(1) watching {BOOT_WATCH_S}s for the boot and the first state reports")
    for _ in range(BOOT_WATCH_S // SNAP_EVERY_S):
        await snap()
        await asyncio.sleep(SNAP_EVERY_S - 2)
    verdict(FAILSAFE in relay_client._relays and OPS in relay_client._relays,
            f"(1) both {ZONE} relay rows present in scada.control.capabilities: {sorted(relay_client._relays)}")

    await command(FAILSAFE, "SwitchToScada", "Scada", "(2)")
    await command(OPS, "CloseRelay", "RelayClosed", "(2) heat call:")

    note(f"(3) holding the call {HOLD_S}s; the Caleffi box should start the dist pump in ~40 s")
    t0 = time.time()
    while time.time() - t0 < HOLD_S:
        await snap()
        await asyncio.sleep(SNAP_EVERY_S - 2)
    note(f"(3) end of hold: {state['channels']}")

    await command(OPS, "OpenRelay", "RelayOpen", "(4) call released:")
    await command(FAILSAFE, "SwitchToWallThermostat", "WallThermostat", "(4)")
    note("TX admin.release.control")
    client.publish(AdminReleaseControl())
    note("(5) 60s after release, snapshots for the standby control's posture")
    for _ in range(60 // SNAP_EVERY_S):
        await snap()
        await asyncio.sleep(SNAP_EVERY_S - 2)
    note("SUMMARY " + " | ".join(verdicts))
    print("\n".join(verdicts))


if __name__ == "__main__":
    asyncio.run(main())
