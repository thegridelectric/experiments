"""Drive a scada under admin from the laptop: a scripted sequence of admin
dispatches over the real gwadmin client, so the wire shape is the TUI's.

Written for `jm/spruce-unlimbo`, whose node names live in `gwsproto.names`
(`CoreNodeNames.admin`, `HydronicSpaceheatNodeNames.hp_boss`,
`NolanNodeNames.iso_valve_relay`). Against a `main` scada the same names
come from `gwsproto.data_classes.house_0_names` (`H0N.admin`,
`H0N.hp_boss`); swap the three imports below, nothing else changes.

The target is an entry of the laptop's gwa config
(`~/.config/gridworks/admin/admin-config.json`), so the broker, port and
credentials come from there, never from this file. Run with the scada venv,
which has gwadmin and gwsproto; the experiments venv has neither:

  ../gridworks-scada/gw_spaceheat/venv/bin/python admin_drive.py \\
      --scada spruce --log evidence/admin-drive.log STEP [STEP ...]

Steps, run in order; the first dispatch takes the tree, `release` hands it
back (always end with one, so local control re-boots its posture):

  hp:off | hp:on            TurnHpOnOff to hp-boss
  valve:<node>:close|open   ChangeValveState to a valve relay (`iso` = iso-valve-relay)
  relay:<node>:close|open   ChangeRelayState to a relay
  snap                      SendSnap (the reply is logged)
  sleep:<seconds>
  release                   AdminReleaseControl

Example, the 2026-10-22 iso-toggle reproducer:

  ... hp:off sleep:5 valve:iso:close sleep:5 valve:iso:open sleep:15 release

The log gets every TX and the RX lines that matter (machine states, fsm
reports, glitches, snapshots). Note that a glitch reaches the LTN on the
upstream link only; the admin link does not see it.
"""

import asyncio
import json
import sys
import time
import uuid
from argparse import ArgumentParser

from gwadmin.cli import get_admin_config
from gwadmin.watch.clients.admin_client import AdminClient, AdminClientCallbacks
from gwsproto.enums import ChangeRelayState, ChangeValveState, TurnHpOnOff
from gwsproto.named_types import AdminDispatch, AdminReleaseControl, FsmEvent, SendSnap
from gwsproto.names.core.node_names import CoreNodeNames
from gwsproto.names.hydronic_spaceheat.node_names import HydronicSpaceheatNodeNames
from gwsproto.names.nolan.node_names import NolanNodeNames

ADMIN = CoreNodeNames.admin
ALIASES = {"iso": NolanNodeNames.iso_valve_relay, "hp-boss": HydronicSpaceheatNodeNames.hp_boss}
TIMEOUT_S = 300


def parse():
    p = ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    p.add_argument("--scada", help="gwa config entry (default: the config's current scada)")
    p.add_argument("--log", required=True, help="log file; also echoed to stdout")
    p.add_argument("steps", nargs="+")
    return p.parse_args()


class Drive:
    def __init__(self, scada: str | None, log_path: str) -> None:
        self.log = open(log_path, "w")
        cfg = get_admin_config()
        if scada:
            if scada not in cfg.config.scadas:
                raise SystemExit(f"no gwa entry '{scada}'; have {sorted(cfg.config.scadas)}")
            cfg.curr_scada = scada
        self.scada_name = cfg.curr_scada
        self.mqtt = None
        self.client = AdminClient(
            cfg, AdminClientCallbacks(mqtt_state_change_callback=self.on_state, mqtt_message_received_callback=self.on_msg)
        )

    def note(self, s: str) -> None:
        line = f"{time.strftime('%H:%M:%S')} {s}"
        self.log.write(line + "\n")
        self.log.flush()
        print(line, flush=True)

    def on_state(self, old, new) -> None:
        self.mqtt = new
        self.note(f"mqtt {old} -> {new}")

    def on_msg(self, topic, payload) -> None:
        try:
            p = json.loads(payload)["Payload"]
            t = p.get("TypeName")
            if t == "single.machine.state":
                self.note(f"RX {t} {p.get('MachineHandle')} {p.get('StateEnum')}={p.get('State')}")
            elif t == "fsm.full.report":
                a = p.get("AtomicList", [{}])[0]
                self.note(f"RX {t} from={p.get('FromName')} {a.get('Event')} {a.get('FromState')}->{a.get('ToState')} {a.get('Handle')}")
            elif t == "glitch":
                self.note(f"RX glitch {p.get('Type')} {p.get('Node')} {p.get('Summary')}: {str(p.get('Details'))[:160]}")
            elif t == "snapshot.spaceheat":
                states = {m["MachineHandle"]: m["State"] for m in p.get("LatestStateList", [])}
                self.note(f"RX snapshot states={states}")
            elif t == "new.command.tree":
                self.note(f"RX {t} " + " ".join(n.get("Handle", "?") for n in p.get("ShNodes", []) if "." in n.get("Handle", "")))
            else:
                self.note(f"RX {t}")
        except Exception as e:
            self.note(f"RX ? {topic} {e}")

    def dispatch(self, to_node: str, event_type: str, event_name: str) -> None:
        ev = FsmEvent(
            FromHandle=ADMIN,
            ToHandle=f"{ADMIN}.{to_node}",
            EventType=event_type,
            EventName=event_name,
            SendTimeUnixMs=int(time.time() * 1000),
            TriggerId=str(uuid.uuid4()),
        )
        self.note(f"TX admin.dispatch {event_name} -> {ev.ToHandle}")
        self.client.publish(AdminDispatch(DispatchTrigger=ev, TimeoutSeconds=TIMEOUT_S))

    async def step(self, token: str) -> None:
        parts = token.split(":")
        kind = parts[0]
        if kind == "sleep":
            await asyncio.sleep(float(parts[1]))
        elif kind == "hp":
            ev = {"on": TurnHpOnOff.TurnOn, "off": TurnHpOnOff.TurnOff}[parts[1]]
            self.dispatch(HydronicSpaceheatNodeNames.hp_boss, TurnHpOnOff.enum_name(), ev.value)
        elif kind == "valve":
            node = ALIASES.get(parts[1], parts[1])
            ev = {"open": ChangeValveState.OpenValve, "close": ChangeValveState.CloseValve}[parts[2]]
            self.dispatch(node, ChangeValveState.enum_name(), ev.value)
        elif kind == "relay":
            node = ALIASES.get(parts[1], parts[1])
            ev = {"open": ChangeRelayState.OpenRelay, "close": ChangeRelayState.CloseRelay}[parts[2]]
            self.dispatch(node, ChangeRelayState.enum_name(), ev.value)
        elif kind == "snap":
            self.note("TX send.snap")
            self.client.publish(SendSnap(FromGNodeAlias=ADMIN))
        elif kind == "release":
            self.note("TX admin.release.control")
            self.client.publish(AdminReleaseControl())
        else:
            raise SystemExit(f"unknown step '{token}'")

    async def run(self, steps: list[str]) -> None:
        for s in steps:  # validate the whole script before touching the broker
            kind = s.split(":")[0]
            if kind not in ("sleep", "hp", "valve", "relay", "snap", "release"):
                raise SystemExit(f"unknown step '{s}'")
        self.note(f"target {self.scada_name}; steps: {' '.join(steps)}")
        self.client.start()
        for _ in range(100):
            if self.mqtt == "active":
                break
            await asyncio.sleep(0.1)
        self.note(f"link {self.mqtt}")
        if self.mqtt != "active":
            self.note("no link; nothing sent")
            self.client.stop()
            return
        await asyncio.sleep(2)
        for s in steps:
            await self.step(s)
        await asyncio.sleep(6)  # let the release's reports arrive
        self.client.stop()
        self.note("done")


if __name__ == "__main__":
    args = parse()
    asyncio.run(Drive(args.scada, args.log).run(args.steps))
