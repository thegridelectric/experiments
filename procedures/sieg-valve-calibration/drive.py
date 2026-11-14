"""Drive a Siegenthaler valve calibration at a house through the admin path.

Runs from the laptop with the scada venv against the house's own mosquitto,
as `gwa watch` does (the entry in the laptop's admin config). Takes the tree,
keeps it alive, sets the plant up for a flow-only measurement (heat pump off,
primary pump on, store path chosen), homes the valve to full send, and then
runs the plan: full traverses and timed stops, each followed by a settle and
a re-home to send. Every dispatch and every sieg-loop state observed is
logged with a wall stamp; the motor's own timing is read afterwards from the
two valve relay channels in the journal (`positions.py`).

    ../../../gridworks-scada/gw_spaceheat/venv/bin/python drive.py beech \\
        plans/traverses.txt --log runs/2026-11-13-beech/drive.log

Plan lines (`#` starts a comment):
    traverse            MoveToFullKeep to FullyKeep, settle, MoveToFullSend
                        to FullySend, settle
    stop send <s>       from the send stop, MoveToFullKeep and StopValve
                        <s> seconds after the dispatch, settle, re-home
    stop keep <s>       MoveToFullKeep to FullyKeep, MoveToFullSend and
                        StopValve (keep stop - <s>) seconds after the
                        dispatch, settle, re-home; needs --keep-stop-s

Ctrl-C releases control and exits; local control then resumes from
wherever the valve stands.
"""
import argparse
import asyncio
import datetime
import logging
import sys
import threading
import time

from gwadmin.config import AdminConfig, AdminPaths, CurrentAdminConfig
from gwadmin.watch.clients.admin_client import AdminClient
from gwadmin.watch.clients.relay_client import RelayClientCallbacks, RelayWatchClient

SETTLE_S = 150.0        # meters settled before the next move
TRAVEL_TIMEOUT_S = 150  # a full run is about 104 s of motor on the scada's clock
KEEPALIVE_S = 120.0
TIMEOUT_S = 300
FLOW_ESTABLISH_S = 60.0
SIEG = "sieg-loop"
STORE = "charge-discharge-relay"
HP_BOSS = "hp-boss"
PRIMARY_PUMP_OPS = "primary-pump-scada-ops-relay"
PRIMARY_PUMP_FAILSAFE = "primary-pump-failsafe-relay"  # SwitchToScada routes the pump through the ops relay

log = logging.getLogger("drive")


def stamp() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]


class Driver:
    def __init__(self, scada: str, keep_stop_s: float | None, store: str, setup: bool) -> None:
        paths = AdminPaths(name="admin")
        with paths.admin_config_path.open() as f:
            config = AdminConfig.model_validate_json(f.read())
        settings = CurrentAdminConfig(paths=paths, config=config, curr_scada=scada)
        self.keep_stop_s = keep_stop_s
        self.store = store
        self.setup = setup
        self.states: dict[str, str] = {}
        self.relays = RelayWatchClient(callbacks=RelayClientCallbacks(
            relay_state_change_callback=self.on_state,
        ))
        self.admin = AdminClient(settings, subclients=[self.relays])

    def on_state(self, changes) -> None:
        for name, change in changes.items():
            self.states[name] = change.new_state.value
            log.info("%s observed %s -> %s", stamp(), name, change.new_state.value)

    async def wait_ready(self) -> None:
        self.admin.start()
        t0 = time.time()
        while not (self.admin.ctrl_capabilities_received() and self.admin.snapshot_received()):
            if time.time() - t0 > 90:
                raise SystemExit("no control capabilities / snapshot from the scada in 90 s")
            await asyncio.sleep(1)
        log.info("%s ready: %s", stamp(), self.admin.curr_scada)

    def send(self, node: str, event: str) -> float:
        self.relays.send_command(node, event, timeout_seconds=TIMEOUT_S)
        t = time.time()
        log.info("%s dispatch %s -> %s", stamp(), event, node)
        return t

    async def keepalive_loop(self) -> None:
        while True:
            self.relays.send_keepalive(TIMEOUT_S)
            log.info("%s keepalive %ss", stamp(), TIMEOUT_S)
            await asyncio.sleep(KEEPALIVE_S)

    async def wait_state(self, node: str, state: str, timeout: float) -> bool:
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.states.get(node) == state:
                return True
            await asyncio.sleep(0.2)
        log.warning("%s %s did not reach %s in %.0f s (at %s)", stamp(), node, state, timeout, self.states.get(node))
        return False

    async def to_full_send(self) -> None:
        self.send(SIEG, "MoveToFullSend")
        await self.wait_state(SIEG, "FullySend", TRAVEL_TIMEOUT_S)

    async def to_full_keep(self) -> None:
        self.send(SIEG, "MoveToFullKeep")
        await self.wait_state(SIEG, "FullyKeep", TRAVEL_TIMEOUT_S)

    async def stop_after(self, t_dispatch: float, seconds: float) -> None:
        await asyncio.sleep(max(0.0, t_dispatch + seconds - time.time()))
        t = self.send(SIEG, "StopValve")
        log.info("%s stop sent %.2f s after the move dispatch", stamp(), t - t_dispatch)

    async def plant_setup(self) -> None:
        self.send(HP_BOSS, "TurnOff")
        await asyncio.sleep(3)
        self.send(STORE, "ChargeStore" if self.store == "charge" else "DischargeStore")
        await asyncio.sleep(3)
        self.send(PRIMARY_PUMP_FAILSAFE, "SwitchToScada")
        await asyncio.sleep(3)
        self.send(PRIMARY_PUMP_OPS, "CloseRelay")
        log.info("%s plant set: heat pump off, store %s, primary pump to scada and on; %.0f s for flow", stamp(), self.store, FLOW_ESTABLISH_S)
        await asyncio.sleep(FLOW_ESTABLISH_S)

    async def traverse(self) -> None:
        log.info("%s TRAVERSE", stamp())
        await self.to_full_keep()
        await asyncio.sleep(SETTLE_S)
        await self.to_full_send()
        await asyncio.sleep(SETTLE_S)

    async def stop_run(self, origin: str, target: float) -> None:
        log.info("%s STOP from=%s target=%.1f", stamp(), origin, target)
        if origin == "send":
            await self.wait_state(SIEG, "FullySend", 5)
            t = self.send(SIEG, "MoveToFullKeep")
            await self.stop_after(t, target)
        else:
            if self.keep_stop_s is None:
                raise SystemExit("a `stop keep` line needs --keep-stop-s")
            await self.to_full_keep()
            t = self.send(SIEG, "MoveToFullSend")
            await self.stop_after(t, self.keep_stop_s - target)
        await asyncio.sleep(SETTLE_S)
        await self.to_full_send()
        await asyncio.sleep(SETTLE_S)

    async def main(self, plan: list[tuple]) -> None:
        await self.wait_ready()
        ka = asyncio.create_task(self.keepalive_loop())
        try:
            await asyncio.sleep(2)
            if self.setup:
                await self.plant_setup()
            log.info("%s homing to full send", stamp())
            await self.to_full_send()
            await asyncio.sleep(SETTLE_S)
            for i, step in enumerate(plan, 1):
                log.info("%s ---- step %d of %d: %s", stamp(), i, len(plan), " ".join(str(x) for x in step))
                if step[0] == "traverse":
                    await self.traverse()
                else:
                    await self.stop_run(step[1], step[2])
            log.info("%s plan done", stamp())
        finally:
            ka.cancel()
            self.relays.send_release_control()
            log.info("%s released control", stamp())
            await asyncio.sleep(1)
            self.admin.stop()


def parse_plan(path: str) -> list[tuple]:
    plan: list[tuple] = []
    for line in open(path):
        line = line.split("#")[0].strip()
        if not line:
            continue
        parts = line.split()
        if parts == ["traverse"]:
            plan.append(("traverse",))
        elif len(parts) == 3 and parts[0] == "stop" and parts[1] in ("send", "keep"):
            plan.append(("stop", parts[1], float(parts[2])))
        else:
            raise SystemExit(f"bad plan line: {line!r}")
    return plan


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("scada", help="entry of the laptop's admin config, e.g. beech")
    ap.add_argument("plan")
    ap.add_argument("--log", default=None)
    ap.add_argument("--keep-stop-s", type=float, default=None, help="the valve's keep stop in motor seconds, for `stop keep` lines")
    ap.add_argument("--store", choices=("charge", "discharge"), default="charge", help="where send flow goes (default charge: the store)")
    ap.add_argument("--no-setup", action="store_true", help="skip heat pump off / store / primary pump on")
    a = ap.parse_args()
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if a.log:
        handlers.append(logging.FileHandler(a.log))
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=handlers)
    asyncio.run(Driver(a.scada, a.keep_stop_s, a.store, not a.no_setup).main(parse_plan(a.plan)))
