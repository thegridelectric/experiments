"""Drive the keep-ratio runs at a house through the admin path the panel uses.

Runs from the laptop with the scada venv, against the house's own mosquitto
as `gwa watch` does (the admin config's scada entry). Takes the tree with
AdminKeepAlive and keeps it alive every KEEPALIVE_S, sends the panel's own
dispatches (MoveToFullKeep / MoveToFullSend / StopValve to sieg-loop,
ChargeStore / DischargeStore to charge-discharge-relay), times StopValve
from its own MoveTo dispatch, and logs every dispatch and every sieg-loop
state it observes with a wall stamp. The seconds the motor actually ran
are in the window scada's log; this log is the driver's side.

    venv/bin/python drive_keep_ratio.py maple runs.txt [--log FILE]

runs.txt: one run per line, `<from> <target_s> <store>`:
    send 36 charge      MoveToFullKeep from the send stop, stop at 36 s
    keep 36 discharge   MoveToFullKeep to FullyKeep, MoveToFullSend, stop
                        at (KEEP_STOP_S - 36) s
Lines starting with # are skipped. Ctrl-C releases control and exits;
the scada's strategy then resumes from wherever the valve stands.
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

KEEP_STOP_S = 94.0     # measured 2026-09-28; the from-keep stop counts down from here
FULL_RUN_S = 104.0     # FULL_RANGE_S 94 + OVERSHOOT_S 10 on scada b347d2f0
SETTLE_S = 150.0
KEEPALIVE_S = 120.0
TIMEOUT_S = 300
SIEG = "sieg-loop"
STORE = "charge-discharge-relay"

log = logging.getLogger("drive")


def stamp() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]


class Driver:
    def __init__(self, scada: str) -> None:
        paths = AdminPaths(name="admin")
        with paths.admin_config_path.open() as f:
            config = AdminConfig.model_validate_json(f.read())
        settings = CurrentAdminConfig(paths=paths, config=config, curr_scada=scada)
        self.states: dict[str, str] = {}
        self.state_event = threading.Event()
        self.relays = RelayWatchClient(callbacks=RelayClientCallbacks(
            relay_state_change_callback=self.on_state,
        ))
        self.admin = AdminClient(settings, subclients=[self.relays])

    def on_state(self, changes) -> None:
        for name, change in changes.items():
            self.states[name] = change.new_state.value
            log.info("%s observed %s -> %s", stamp(), name, change.new_state.value)
        self.state_event.set()

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

    async def stop_after(self, t_dispatch: float, seconds: float) -> None:
        await asyncio.sleep(max(0.0, t_dispatch + seconds - time.time()))
        t = self.send(SIEG, "StopValve")
        log.info("%s stop sent %.2f s after the move dispatch", stamp(), t - t_dispatch)

    async def run(self, origin: str, target: float, store: str) -> None:
        log.info("%s RUN from=%s target=%.1f store=%s", stamp(), origin, target, store)
        self.send(STORE, "ChargeStore" if store == "charge" else "DischargeStore")
        await asyncio.sleep(2)
        if origin == "send":
            await self.wait_state(SIEG, "FullySend", 5)
            t = self.send(SIEG, "MoveToFullKeep")
            await self.stop_after(t, target)
        else:
            self.send(SIEG, "MoveToFullKeep")
            await asyncio.sleep(FULL_RUN_S + 5)
            await self.wait_state(SIEG, "FullyKeep", 15)
            t = self.send(SIEG, "MoveToFullSend")
            await self.stop_after(t, KEEP_STOP_S - target)
        await asyncio.sleep(SETTLE_S)
        self.send(SIEG, "MoveToFullSend")
        await asyncio.sleep(FULL_RUN_S + 5)
        await self.wait_state(SIEG, "FullySend", 15)

    async def main(self, runs: list[tuple[str, float, str]]) -> None:
        await self.wait_ready()
        ka = asyncio.create_task(self.keepalive_loop())
        try:
            await asyncio.sleep(2)
            self.send(SIEG, "MoveToFullSend")  # home first
            await asyncio.sleep(FULL_RUN_S + 5)
            await self.wait_state(SIEG, "FullySend", 15)
            for i, (origin, target, store) in enumerate(runs, 1):
                log.info("%s ---- run %d of %d", stamp(), i, len(runs))
                await self.run(origin, target, store)
            log.info("%s all runs done", stamp())
        finally:
            ka.cancel()
            self.relays.send_release_control()
            log.info("%s released control", stamp())
            await asyncio.sleep(1)
            self.admin.stop()


def parse_runs(path: str) -> list[tuple[str, float, str]]:
    runs = []
    for line in open(path):
        line = line.split("#")[0].strip()
        if not line:
            continue
        origin, target, store = line.split()
        assert origin in ("send", "keep") and store in ("charge", "discharge"), line
        runs.append((origin, float(target), store))
    return runs


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("scada")
    ap.add_argument("runs")
    ap.add_argument("--log", default=None)
    a = ap.parse_args()
    handlers = [logging.StreamHandler(sys.stdout)]
    if a.log:
        handlers.append(logging.FileHandler(a.log))
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=handlers)
    asyncio.run(Driver(a.scada).main(parse_runs(a.runs)))
