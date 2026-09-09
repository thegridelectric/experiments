"""A dev admin drives five-v-boss on the sim Nolan scada over the dev broker:
TurnOff, a hold past the picos' would-be flatline, TurnOn, TurnOff again,
then admin release, while a plain gw/# subscription captures the scada's
journal-bound reports.
Usage: five_v_boss_hold.py <drive.log> <broker-capture.jsonl>
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
from gwadmin.watch.clients.dispatch_replies import DispatchReply
from gwadmin.watch.clients.relay_client import RelayClientCallbacks, RelayWatchClient
from gwproactor.config.mqtt import TLSInfo
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.named_types import AdminDispatch, AdminReleaseControl, SendSnap

SCADA = os.environ.get("PICO_DRIVE_SCADA", "d1.isone.me.versant.keene.spruce.scada")
PORT = int(os.environ.get("PICO_DRIVE_PORT", "1885"))
USER = os.environ.get("PICO_DRIVE_USER", "smqPublic")
PASS = os.environ.get("PICO_DRIVE_PASS", "smqPublic")
BOOT_WATCH_S = 150      # the boot cycle + the sim picos' first posts
HOLD_S = 150            # past SimLifeS 120: a would-be flatline
STEP_TIMEOUT_S = 90     # a transition that has not shown by then is a miss
DISPATCH_TIMEOUT_S = 900  # keep the admin timeout out of the hold's way
BOSS = "five-v-boss"

log = open(sys.argv[1], "w")
capture = open(sys.argv[2], "w")
INTEREST = ("five-v-boss", "pico-cycler", "vdc-relay", "buffer", "tank1")


def note(s: str) -> None:
    log.write(f"{time.strftime('%H:%M:%S')} {s}\n")
    log.flush()


state = {"mqtt": None, "boss": None, "cycler": None, "relay": None, "tree": {}, "replies": [], "dispatches": []}


def on_state(old, new):
    state["mqtt"] = new
    note(f"mqtt {old} -> {new}")


def track(handle: str, value: str) -> None:
    for key, leaf in (("boss", "five-v-boss"), ("cycler", "pico-cycler"), ("relay", "vdc-relay")):
        if handle.endswith(leaf):
            state[key] = value


def on_msg(topic, payload):
    try:
        p = json.loads(payload)["Payload"]
        t = p.get("TypeName")
        if t == "single.machine.state":
            h = p.get("MachineHandle", "")
            if h.endswith(INTEREST):
                note(f"RX {t} {h} {p.get('StateEnum')}={p.get('State')}")
                track(h, p.get("State"))
        elif t == "fsm.full.report":
            a = p.get("AtomicList", [{}])
            note(f"RX {t} from={p.get('FromName')} trigger={p.get('TriggerId')} "
                 + " ".join(f"{x.get('Event')}:{x.get('FromState')}->{x.get('ToState')}" for x in a))
        elif t == "snapshot.spaceheat":
            states = {m["MachineHandle"]: m["State"] for m in p.get("LatestStateList", [])
                      if m["MachineHandle"].endswith(INTEREST)}
            for h, s in states.items():
                track(h, s)
                # The snapshot's machine handles show a node's handle as of its
                # last state row (stale after a reparent until it reports
                # again); new.command.tree on gw/# is the authority, the
                # snapshot only fills a leaf the tree has not named yet.
                for leaf in ("five-v-boss", "pico-cycler", "vdc-relay"):
                    if h.endswith(leaf):
                        state["tree"].setdefault(leaf, h)
            note(f"RX snapshot {states}")
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
        if p.get("TypeName") == "new.command.tree":
            # The tree rides the gridworks link (to the LTN), not the admin link.
            tree = {n["Name"]: n.get("Handle") for n in p.get("ShNodes", [])
                    if n.get("Name") in ("five-v-boss", "pico-cycler", "vdc-relay")}
            state["tree"] = tree
            note(f"BROKER new.command.tree {tree}")
        elif p.get("TypeName") == "report":
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
broker.username_pw_set(USER, PASS)
broker.on_message = on_broker
broker.connect("localhost", PORT)
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
            verdict(True, f"{what}: boss={state['boss']} cycler={state['cycler']} relay={state['relay']} tree={state['tree']}")
            return True
    verdict(False, f"{what} within {timeout_s}s: boss={state['boss']} cycler={state['cycler']} relay={state['relay']} tree={state['tree']}")
    return False


def relay_under(owner: str) -> bool:
    h = state["tree"].get("vdc-relay", "")
    return h.split(".")[-2:-1] == [owner]


async def main():
    client.start()
    for _ in range(100):
        if state["mqtt"] == "active":
            break
        await asyncio.sleep(0.1)
    note(f"link {state['mqtt']}")
    note(f"(1) watching {BOOT_WATCH_S}s for the boot cycle and the sim picos' posts")
    await asyncio.sleep(BOOT_WATCH_S)
    await snap()
    verdict(BOSS in relay_client._relays, f"(2) five-v-boss row present in scada.control.capabilities: {sorted(relay_client._relays)}")
    verdict(state["boss"] == "PicoCycler", f"(2) five-v-boss reads PicoCycler at rest: {state['boss']}")

    note("(2) TurnOff")
    n_replies = len(state["replies"])
    relay_client.send_command(BOSS, "TurnOff", DISPATCH_TIMEOUT_S)
    off_id = state["dispatches"][-1]
    await wait_for("(2) TurnOff reply", lambda: len(state["replies"]) > n_replies, 30)
    await wait_for("(2) FiveVOff, relay under five-v-boss + RelayOpen, cycler Dormant",
                   lambda: state["boss"] == "FiveVOff" and relay_under(BOSS)
                   and state["relay"] == "RelayOpen" and state["cycler"] == "Dormant")

    note(f"(3) holding {HOLD_S}s past a would-be flatline (SimLifeS 120)")
    relay_before, cycler_before = state["relay"], state["cycler"]
    t0 = time.time()
    while time.time() - t0 < HOLD_S:
        await snap()
        await asyncio.sleep(8)
    verdict(state["relay"] == relay_before and state["cycler"] == cycler_before and state["boss"] == "FiveVOff",
            f"(3) hold: no relay event, no cycler transition: boss={state['boss']} relay={state['relay']} cycler={state['cycler']}")

    note("(4) TurnOn")
    n_replies = len(state["replies"])
    relay_client.send_command(BOSS, "TurnOn", DISPATCH_TIMEOUT_S)
    on_id = state["dispatches"][-1]
    await wait_for("(4) TurnOn reply", lambda: len(state["replies"]) > n_replies, 30)
    await wait_for("(4) PicoCycler, relay back under the cycler + RelayClosed, cycler PicosLive",
                   lambda: state["boss"] == "PicoCycler" and relay_under("pico-cycler")
                   and state["relay"] == "RelayClosed" and state["cycler"] == "PicosLive")
    note("(4) waiting 40s for the picos to re-POST")
    await asyncio.sleep(40)
    await snap()

    note("(5) TurnOff again, then release admin")
    n_replies = len(state["replies"])
    relay_client.send_command(BOSS, "TurnOff", DISPATCH_TIMEOUT_S)
    off2_id = state["dispatches"][-1]
    await wait_for("(5) second TurnOff reply", lambda: len(state["replies"]) > n_replies, 30)
    await wait_for("(5) FiveVOff again", lambda: state["boss"] == "FiveVOff" and state["relay"] == "RelayOpen")
    note("TX admin.release.control")
    client.publish(AdminReleaseControl())
    await wait_for("(5) after release: AutoWakesUp restores PicoCycler + RelayClosed + PicosLive",
                   lambda: state["boss"] == "PicoCycler" and state["relay"] == "RelayClosed"
                   and state["cycler"] == "PicosLive" and relay_under("pico-cycler"))
    note("waiting 70s for the next journal-bound report")
    await asyncio.sleep(70)
    note(f"ids: off={off_id} on={on_id} off2={off2_id}")
    note("SUMMARY " + " | ".join(verdicts))
    client.stop()
    broker.loop_stop()
    note("done")


asyncio.run(main())
