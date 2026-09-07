"""Rung 2 driver: the admin client turns the heat pump off and on through
hp-boss over the dev broker, on the spruce-sim Nolan layout."""
import asyncio, json, logging, time, uuid, sys
from gwproactor.config.mqtt import TLSInfo
from gwadmin.config import AdminMQTTClient, CurrentAdminConfig, ScadaConfig, AdminConfig
from gwadmin.watch.clients.admin_client import AdminClient, AdminClientCallbacks
from gwsproto.data_classes.house_0_names import H0N
from gwsproto.enums import TurnHpOnOff
from gwsproto.named_types import AdminDispatch, AdminReleaseControl, FsmEvent, SendSnap

SCADA = "d1.isone.me.versant.keene.spruce.scada"
log = open(sys.argv[1], "w")
def note(s):
    log.write(f"{time.strftime('%H:%M:%S')} {s}\n"); log.flush()

state = {"mqtt": None}
def on_state(old, new): state["mqtt"] = new; note(f"mqtt {old} -> {new}")
def on_msg(topic, payload):
    try:
        p = json.loads(payload)["Payload"]
        t = p.get("TypeName")
        if t == "single.machine.state":
            note(f"RX {t} {p.get('MachineHandle')} {p.get('StateEnum')}={p.get('State')}")
        elif t == "fsm.full.report":
            a = p.get("AtomicList", [{}])[0]
            note(f"RX {t} from={p.get('FromName')} {a.get('Event')} {a.get('FromState')}->{a.get('ToState')} {a.get('Handle')}")
        elif t == "snapshot.spaceheat":
            vals = {n: v for n, v in zip(p.get("LatestReadingList", []) and [r.get("ChannelName") for r in p["LatestReadingList"]], [r.get("Value") for r in p.get("LatestReadingList", [])]) if "hp-scada-ops" in n}
            note(f"RX snapshot hp-scada-ops-relay={vals}")
        elif t == "new.command.tree":
            hb = [n for n in p.get("ShNodes", []) if n.get("Name") in ("hp-boss", "hp-scada-ops-relay")]
            note(f"RX {t} " + " ".join(f"{n['Name']}@{n.get('Handle')}" for n in hb))
        else:
            note(f"RX {t}")
    except Exception as e:
        note(f"RX ? {topic} {e}")

cfg = CurrentAdminConfig(
    config=AdminConfig(scadas={"spruce-sim": ScadaConfig(long_name=SCADA, mqtt=AdminMQTTClient(
        host="localhost", port=1885, username="smqPublic", password="smqPublic", tls=TLSInfo(use_tls=False)))}),
    curr_scada="spruce-sim")
client = AdminClient(cfg, AdminClientCallbacks(mqtt_state_change_callback=on_state, mqtt_message_received_callback=on_msg))

def turn(name):
    ev = FsmEvent(FromHandle=H0N.admin, ToHandle=f"{H0N.admin}.{H0N.hp_boss}", EventType=TurnHpOnOff.enum_name(),
                  EventName=name, SendTimeUnixMs=int(time.time()*1000), TriggerId=str(uuid.uuid4()))
    note(f"TX admin.dispatch {name} -> {ev.ToHandle}")
    client.publish(AdminDispatch(DispatchTrigger=ev, TimeoutSeconds=120))

async def main():
    client.start()
    for _ in range(100):
        if state["mqtt"] == "active": break
        await asyncio.sleep(0.1)
    note(f"link {state['mqtt']}")
    await asyncio.sleep(2)
    turn(TurnHpOnOff.TurnOff); await asyncio.sleep(8)
    client.publish(SendSnap(FromGNodeAlias=H0N.admin)); await asyncio.sleep(4)
    turn(TurnHpOnOff.TurnOn); await asyncio.sleep(8)
    client.publish(SendSnap(FromGNodeAlias=H0N.admin)); await asyncio.sleep(4)
    note("TX admin.release.control"); client.publish(AdminReleaseControl()); await asyncio.sleep(6)
    client.stop(); note("done")
asyncio.run(main())
