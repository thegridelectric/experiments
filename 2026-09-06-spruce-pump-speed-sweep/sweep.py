#!/usr/bin/env python3
"""sweep — the spruce pump-speed sweep driver (dac-output step 5).

Runs ON SPRUCE, from the box's `~/experiments` clone at a pushed SHA, with
the unlimbo checkout's venv, against the window scada's admin link on the
box's own broker. Never from the dev machine through a tunnel: honeysuckle
run 4 (2026-09-05) lost a dispatch to a tunnel that had died silently, and
a window that holds a real pump must not depend on the laptop's connection.

    cd ~/experiments/2026-09-06-spruce-pump-speed-sweep
    setsid nohup timeout 4200 ~/gridworks-scada-unlimbo/gw_spaceheat/venv/bin/python \
        sweep.py --run 1 > /tmp/spruce-pump-sweep/sweep-1.stdout 2>&1 < /dev/null &

What it does, in order (each phase selectable with --phases):
  posture   secondary pump ON, then iso valve OPEN (pump first: energizing
            the iso relay with no other 0x21 coil energized resets that
            expander about one toggle in three, 2026-08-23), then store
            pump OFF; the heat-pump call relay is left alone unless --hp-off.
  baseline  hold the DAC where it is (power-on 3020 ≈ 7.55 V, reported 76)
            for BASELINE_S; record flow.
  up        0 → 100 in steps of 10, HOLD_S per step.
  down      100 → 0, same steps: hysteresis.
  jumps     a fixed pseudo-random sequence over the same levels: settling
            after large steps, path dependence.
  restore   DAC back to RESTORE_LEVEL (76 → code 3040, not the exact
            power-on 3020; the next reboot re-asserts EEPROM), admin
            released. Relays stay in the sweep posture, which is the summer
            posture (iso open, pump on); the hack re-asserts it on restart.

The wire shape is the admin TUI's, built from the gwsproto types directly
(AdminAnalogDispatch / AdminDispatch(FsmEvent) / SendSnap /
AdminReleaseControl in a gwproto Message envelope) rather than through the
gwadmin client: the pi venv is built `no_admin`, and the gwadmin relay
client keys its event vocabulary off ScadaControlCapabilities, which a
Nolan scada cannot emit yet (`scada.control.capabilities/001` requires the
House0 Krida component). Relay event vocabulary comes from the box's own
layout file instead (the sema-typed record the scada under test boots).

Liveness: the admin link has no heartbeat (unsorted.md, 2026-09-05). Every
command here waits for its echo on the admin link — the outputer's
VoltsTimesTen reading after an analog dispatch, the relay's RelayState
reading after a relay dispatch. No echo within ECHO_S means the scada is
not listening (link dead, admin not awake, actor not routed): the sweep
aborts into restore rather than continuing blind.

Output (OUT_DIR, default /tmp/spruce-pump-sweep — scp'd back by the
runbook, nothing stays in the pi's home dir):
  sweep-<run>.log            every command, echo, state change and snapshot
  sweep-<run>-results.json   typed records: steps, readings, machine states
                             (relays included), knobs, the run window, the
                             layout's sha256
The results file is kind-specific structure (no sema word yet; the
`gw.readings` + `gw.experiment.run` instances are emitted on the dev
machine by emit_instances.py from it). Missing word to retire the record:
a `gw.experiment.step` naming a commanded level and its hold.
"""

import argparse
import hashlib
import json
import logging
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

import paho.mqtt.client as mqtt
from gwproto import Message, MQTTTopic
from gwsproto.enums import (
    ChangeRelayState,
    ChangeValveState,
    RelayClosedOrOpen,
    ValveOpenOrClosed,
)
from gwsproto.named_types import (
    AdminAnalogDispatch,
    AdminDispatch,
    AdminReleaseControl,
    AnalogDispatch,
    FsmEvent,
    NolanLayout,
    SendSnap,
    SingleReading,
    SnapshotSpaceheat,
)
from gwsproto.property_format import SpaceheatName
from pydantic import TypeAdapter

# ---- knobs -----------------------------------------------------------------

ADMIN = "admin"  # the admin link's peer name (H0N.admin)
DAC_NODE = "secondary-010v"
FLOW_CHANNEL = "secondary-flow"
PUMP_RELAY = "secondary-pump-relay"
ISO_RELAY = "iso-valve-relay"
STORE_PUMP_RELAY = "store-pump-relay"
HP_RELAY = "hp-scada-ops-relay"
RELAYS = (PUMP_RELAY, ISO_RELAY, STORE_PUMP_RELAY, HP_RELAY)



class Plan(NamedTuple):
    """The levels a run visits: the ramp (up, then reversed for down), the
    jump sequence, and a one-line statement of what the plan is for."""

    ramp: list[int]
    jumps: list[int]
    note: str


# The Grundfos UPMS booklet (page 21, 0-10 VDC profile R) puts the pump in
# bands by input volts: below 0.5 V minimum speed (signal-fail behaviour),
# 0.5-1 V stopped, 1-2 V hysteresis, 2-3 V minimum speed, 3-10 V speed from
# minimum to maximum. The plans sample against those bands.
PLANS = {
    "full": Plan(
        ramp=list(range(0, 101, 10)),
        jumps=[20, 80, 40, 100, 10, 60, 0, 90, 30, 70, 50],
        note="uniform 0-10 V at 1 V; run 1's plan, three points below the speed band",
    ),
    "bands": Plan(
        ramp=[0, 7, 15, 25, 40],
        jumps=[],
        note="one level per booklet band, entered from below (up) then from above (down): "
        "the hysteresis band is the point of the two directions",
    ),
    "linear": Plan(
        ramp=list(range(30, 101, 5)),
        jumps=[40, 90, 55, 100, 35, 75, 30, 95, 45, 80, 60],
        note="the 3-10 V speed band at 0.5 V, up, down and jumps",
    ),
}
RESTORE_LEVEL = 76  # volts x 10; the EEPROM power-on 3020 is 7.55 V
HOLD_S = 90
BASELINE_S = 180
RELAY_GAP_S = 5  # between relay commands; the 0x21 finding is about ordering, not spacing
SNAP_S = 30  # SendSnap cadence; the scada also pushes snapshots on its own
ECHO_S = 15  # no echo of a command within this = the scada is not listening
STATE_POLL_S = 3  # SendSnap cadence while waiting for a relay's state echo

# Relay state is reported as a machine state (the snapshot's LatestStateList),
# not as a reading, so a relay echo is the state the event lands in. The
# relay FSMs are the scada's; this is the wire vocabulary of their outcomes.
EXPECTED_STATE = {
    (ChangeRelayState.enum_name(), ChangeRelayState.CloseRelay.value): RelayClosedOrOpen.RelayClosed.value,
    (ChangeRelayState.enum_name(), ChangeRelayState.OpenRelay.value): RelayClosedOrOpen.RelayOpen.value,
    (ChangeValveState.enum_name(), ChangeValveState.OpenValve.value): ValveOpenOrClosed.ValveOpen.value,
    (ChangeValveState.enum_name(), ChangeValveState.CloseValve.value): ValveOpenOrClosed.ValveClosed.value,
}
ADMIN_TIMEOUT_S = 900  # renewed by every command; > the longest silent hold
CONNECT_S = 20
PHASES = ("posture", "baseline", "up", "down", "jumps", "restore")

DEFAULT_ENV = Path("~/envs/dev.env").expanduser()
DEFAULT_LAYOUT = Path("~/.config/gridworks/scada-experiment/hardware-layout.json").expanduser()
DEFAULT_OUT = Path("/tmp/spruce-pump-sweep")

_SPACEHEAT = TypeAdapter(SpaceheatName)

log = logging.getLogger("sweep")


# ---- typed records ----------------------------------------------------------


class Reading(NamedTuple):
    """One reading the scada reported on the admin link (a snapshot entry or a
    forwarded SingleReading); the value is the channel word's wire encoding
    (VoltsTimesTen, GpmTimes100, RelayState)."""

    channel: SpaceheatName
    value: int
    unix_ms: int


class Step(NamedTuple):
    """One commanded level: which phase asked for it, the level in volts x 10,
    when the dispatch was published, when the outputer's echo arrived (None =
    never), and how long the level was held."""

    phase: str
    level: int
    sent_unix_ms: int
    echo_unix_ms: int | None
    hold_s: int


class RelayCommand(NamedTuple):
    """One relay dispatch: node, the FsmEvent name sent, publish time, and
    when a snapshot first showed the relay in the expected state (None =
    never)."""

    node: SpaceheatName
    event: str
    sent_unix_ms: int
    echo_unix_ms: int | None


class MachineState(NamedTuple):
    """One entry of a snapshot's LatestStateList: a state machine's handle at
    that moment, its state, and the state's own timestamp."""

    handle: str
    state: str
    unix_ms: int


class RelayEvents(NamedTuple):
    """A relay node's event vocabulary as its layout config declares it."""

    node: SpaceheatName
    event_type: str
    energizing: str
    de_energizing: str


class Provenance(NamedTuple):
    """The artifact the scada under test booted, by path and content hash."""

    layout_path: str
    layout_sha256: str
    scada_alias: str


# ---- layout facts -----------------------------------------------------------


def load_layout(path: Path) -> tuple[NolanLayout, Provenance]:
    raw = path.read_bytes()
    layout = NolanLayout.model_validate(json.loads(raw))
    alias = next(g.Alias for g in layout.GNodes if g.Alias.endswith(".scada"))
    return layout, Provenance(str(path), hashlib.sha256(raw).hexdigest(), alias)


def relay_events(layout: NolanLayout, node_name: str) -> RelayEvents:
    node = next(n for n in layout.ShNodes if n.Name == node_name)
    component = next(c for c in layout.Components if c.ComponentId == node.ComponentId)
    config = next(c for c in component.ConfigList if c.ChannelName == node_name)
    return RelayEvents(
        node=_SPACEHEAT.validate_python(node_name),
        event_type=config.EventType,
        energizing=config.EnergizingEvent,
        de_energizing=config.DeEnergizingEvent,
    )


def read_env(path: Path) -> dict[str, str]:
    """KEY=VALUE lines of the scada's env file; the admin link's credentials
    come from here so they are never on a command line."""
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


# ---- the admin-link client --------------------------------------------------


class AdminLink:
    """Publishes admin commands to the scada and records what comes back."""

    def __init__(self, host: str, port: int, username: str, password: str, scada_alias: str):
        self.scada_alias = scada_alias
        self.readings: list[Reading] = []
        self.states: list[MachineState] = []
        self.seen: set[tuple[str, int]] = set()
        self.lock = threading.Lock()
        self.connected = threading.Event()
        self.snapshots = 0
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sweep-{uuid.uuid4().hex[:8]}")
        self.client.username_pw_set(username, password)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        self.host, self.port = host, port

    # paho callbacks (paho thread)

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            log.error("CONNACK refused: %s", reason_code)
            return
        topic = MQTTTopic.encode(Message.type_name(), self.scada_alias, ADMIN, "#")
        client.subscribe(topic, qos=1)
        log.info("connected to %s:%s, subscribed %s", self.host, self.port, topic)
        self.connected.set()

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        log.warning("disconnected: %s", reason_code)
        self.connected.clear()

    def on_message(self, client, userdata, msg):
        try:
            message_type = MQTTTopic.decode(msg.topic).message_type
            if message_type == SnapshotSpaceheat.model_fields["TypeName"].default:
                snap = Message[SnapshotSpaceheat].model_validate_json(msg.payload).Payload
                self.take_snapshot(snap)
            elif message_type == SingleReading.model_fields["TypeName"].default:
                reading = Message[SingleReading].model_validate_json(msg.payload).Payload
                self.take(Reading(reading.ChannelName, reading.Value, reading.ScadaReadTimeUnixMs), "single")
            else:
                log.info("admin link: %s", message_type)
        except Exception:
            log.exception("bad message on %s", msg.topic)

    def take_snapshot(self, snap: SnapshotSpaceheat) -> None:
        self.snapshots += 1
        for r in snap.LatestReadingList:
            self.take(Reading(r.ChannelName, r.Value, r.ScadaReadTimeUnixMs), "snap")
        with self.lock:
            for s in snap.LatestStateList:
                obs = MachineState(s.MachineHandle, s.State, s.UnixMs)
                if obs not in self.states:
                    self.states.append(obs)
        relays = {s.MachineHandle: s.State for s in snap.LatestStateList if s.MachineHandle.split(".")[-1] in RELAYS}
        log.info("snapshot %d: %d readings, %d states; relays %s", self.snapshots, len(snap.LatestReadingList), len(snap.LatestStateList), relays)

    def take(self, reading: Reading, source: str) -> None:
        key = (reading.channel, reading.unix_ms)
        with self.lock:
            if key in self.seen:
                return
            self.seen.add(key)
            self.readings.append(reading)
        if reading.channel in (DAC_NODE, FLOW_CHANNEL):
            log.info("%s %s = %d @ %s", source, reading.channel, reading.value, iso(reading.unix_ms))

    # driving

    def start(self) -> None:
        self.client.connect(self.host, self.port, keepalive=30)
        self.client.loop_start()
        if not self.connected.wait(CONNECT_S):
            raise SystemExit(f"no broker connection within {CONNECT_S}s")

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()

    def publish(self, payload) -> None:
        message = Message[type(payload)](Src=ADMIN, Dst=self.scada_alias, Payload=payload)
        info = self.client.publish(message.mqtt_topic(), message.model_dump_json().encode(), qos=1)
        info.wait_for_publish(5)
        log.info("sent %s", payload.TypeName)

    def request_snapshot(self) -> None:
        self.publish(SendSnap(FromGNodeAlias=ADMIN))

    def latest(self, channel: str) -> Reading | None:
        with self.lock:
            hits = [r for r in self.readings if r.channel == channel]
        return max(hits, key=lambda r: r.unix_ms) if hits else None

    def state_of(self, node: str) -> MachineState | None:
        """The latest snapshot state of the machine whose handle ends in
        `node`, whatever its boss is at the moment (auto.lc.n… or admin…)."""
        with self.lock:
            hits = [s for s in self.states if s.handle.split(".")[-1] == node]
        return max(hits, key=lambda s: s.unix_ms) if hits else None

    def await_state(self, node: str, expected: str) -> int | None:
        """Snapshots requested every STATE_POLL_S until one shows `node` in
        `expected`, within ECHO_S; returns the wall time of that snapshot."""
        deadline = time.time() + ECHO_S
        next_poll = 0.0
        while time.time() < deadline:
            if time.time() >= next_poll:
                self.request_snapshot()
                next_poll = time.time() + STATE_POLL_S
            s = self.state_of(node)
            if s is not None and s.state == expected:
                return now_ms()
            time.sleep(0.5)
        return None

    def await_echo(self, channel: str, after_ms: int, predicate) -> int | None:
        """A reading on `channel` timed after the command and satisfying
        `predicate`, within ECHO_S; None when none arrives."""
        deadline = time.time() + ECHO_S
        while time.time() < deadline:
            r = self.latest(channel)
            if r is not None and r.unix_ms >= after_ms and predicate(r.value):
                return r.unix_ms
            time.sleep(0.5)
        return None


# ---- the sweep --------------------------------------------------------------


def now_ms() -> int:
    return int(time.time() * 1000)


def iso(unix_ms: int) -> str:
    return datetime.fromtimestamp(unix_ms / 1000, tz=timezone.utc).strftime("%H:%M:%S.%f")[:-3] + "Z"


class LinkDead(RuntimeError):
    """A command drew no echo: the scada is not under our control."""


class Sweep:
    def __init__(self, link: AdminLink, layout: NolanLayout, plan: Plan, hold_s: int, baseline_s: int, hp_off: bool):
        self.link = link
        self.layout = layout
        self.plan = plan
        self.hold_s = hold_s
        self.baseline_s = baseline_s
        self.hp_off = hp_off
        self.steps: list[Step] = []
        self.relay_commands: list[RelayCommand] = []
        self.last_snap_request = 0.0

    def hold(self, seconds: int) -> None:
        end = time.time() + seconds
        while time.time() < end:
            if time.time() - self.last_snap_request >= SNAP_S:
                self.link.request_snapshot()
                self.last_snap_request = time.time()
            time.sleep(1)

    def dispatch(self, phase: str, level: int, hold_s: int) -> None:
        if not 0 <= level <= 100:
            raise ValueError("level is volts x 10, 0..100")
        sent = now_ms()
        self.link.publish(
            AdminAnalogDispatch(
                Dispatch=AnalogDispatch(
                    FromGNodeAlias=None,
                    FromHandle=ADMIN,
                    ToHandle=f"{ADMIN}.{DAC_NODE}",
                    AboutName=DAC_NODE,
                    Value=level,
                    TriggerId=str(uuid.uuid4()),
                    UnixTimeMs=sent,
                ),
                TimeoutSeconds=ADMIN_TIMEOUT_S,
            )
        )
        echo = self.link.await_echo(DAC_NODE, sent, lambda v: v == level)
        self.steps.append(Step(phase, level, sent, echo, hold_s))
        if echo is None:
            raise LinkDead(f"{phase}: no {DAC_NODE} echo of {level} within {ECHO_S}s")
        log.info("%s: level %d echoed after %.1fs; holding %ds", phase, level, (echo - sent) / 1000, hold_s)
        self.hold(hold_s)

    def relay(self, node: str, energized: bool) -> None:
        ev = relay_events(self.layout, node)
        event = ev.energizing if energized else ev.de_energizing
        sent = now_ms()
        self.link.publish(
            AdminDispatch(
                DispatchTrigger=FsmEvent(
                    FromHandle=ADMIN,
                    ToHandle=f"{ADMIN}.{node}",
                    EventType=ev.event_type,
                    EventName=event,
                    SendTimeUnixMs=sent,
                    TriggerId=str(uuid.uuid4()),
                ),
                TimeoutSeconds=ADMIN_TIMEOUT_S,
            )
        )
        expected = EXPECTED_STATE[(ev.event_type, event)]
        echo = self.link.await_state(node, expected)
        self.relay_commands.append(RelayCommand(_SPACEHEAT.validate_python(node), event, sent, echo))
        if echo is None:
            raise LinkDead(f"posture: {node} not {expected} after {event} within {ECHO_S}s")
        log.info("posture: %s %s -> %s seen after %.1fs", node, event, expected, (echo - sent) / 1000)
        time.sleep(RELAY_GAP_S)

    def posture(self) -> None:
        self.relay(PUMP_RELAY, True)
        self.relay(ISO_RELAY, True)
        self.relay(STORE_PUMP_RELAY, False)
        if self.hp_off:
            self.relay(HP_RELAY, False)

    def run(self, phases: tuple[str, ...]) -> None:
        # Wake admin with a request that costs nothing, then require a
        # snapshot before touching anything: no snapshot, no window.
        self.link.request_snapshot()
        self.last_snap_request = time.time()
        deadline = time.time() + ECHO_S
        while self.link.snapshots == 0 and time.time() < deadline:
            time.sleep(0.5)
        if self.link.snapshots == 0:
            raise LinkDead("no snapshot answered the first SendSnap")
        if "posture" in phases:
            self.posture()
        if "baseline" in phases:
            current = self.link.latest(DAC_NODE)
            log.info("baseline: DAC reported %s; holding %ds", current.value if current else "nothing yet", self.baseline_s)
            self.hold(self.baseline_s)
        if "up" in phases:
            for level in self.plan.ramp:
                self.dispatch("up", level, self.hold_s)
        if "down" in phases:
            for level in reversed(self.plan.ramp):
                self.dispatch("down", level, self.hold_s)
        if "jumps" in phases:
            for level in self.plan.jumps:
                self.dispatch("jumps", level, self.hold_s)

    def restore(self) -> None:
        """Always runs, on success and on abort: the DAC back to the summer
        level, admin released. Best effort; every failure is logged."""
        try:
            self.dispatch("restore", RESTORE_LEVEL, 10)
        except Exception:
            log.exception("restore: the DAC dispatch did not echo; the pump may be off the summer level")
        try:
            self.link.publish(AdminReleaseControl())
        except Exception:
            log.exception("restore: release did not publish")

    def to_jsonable(self, knobs: dict, provenance: Provenance, start_ms: int, end_ms: int, outcome: str) -> dict:
        return {
            "Outcome": outcome,
            "StartUnixMs": start_ms,
            "EndUnixMs": end_ms,
            "Knobs": knobs,
            "Provenance": provenance._asdict(),
            "Steps": [s._asdict() for s in self.steps],
            "RelayCommands": [c._asdict() for c in self.relay_commands],
            "States": [s._asdict() for s in sorted(self.link.states, key=lambda s: (s.handle, s.unix_ms))],
            "Readings": [r._asdict() for r in sorted(self.link.readings, key=lambda r: (r.channel, r.unix_ms))],
        }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run", required=True, help="run name; names the log and results files")
    p.add_argument("--env", type=Path, default=DEFAULT_ENV, help="the window scada's env file (SCADA_ADMIN__* creds)")
    p.add_argument("--layout", type=Path, default=DEFAULT_LAYOUT, help="the layout the window scada boots")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--plan", choices=sorted(PLANS), default="full", help="which levels to visit; see PLANS")
    p.add_argument("--hold", type=int, default=HOLD_S)
    p.add_argument("--baseline", type=int, default=BASELINE_S)
    p.add_argument("--phases", default=",".join(PHASES), help=f"comma list from {PHASES}")
    p.add_argument("--hp-off", action="store_true", help="also de-energize the heat-pump call relay in the posture")
    p.add_argument("--dry-run", action="store_true", help="print the plan and the relay vocabulary; no broker")
    args = p.parse_args(argv)

    phases = tuple(x for x in args.phases.split(",") if x)
    unknown = set(phases) - set(PHASES)
    if unknown:
        p.error(f"unknown phases {sorted(unknown)}")

    args.out.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(args.out / f"sweep-{args.run}.log"), logging.StreamHandler(sys.stdout)],
    )

    layout, provenance = load_layout(args.layout)
    plan = PLANS[args.plan]
    knobs = {
        "Phases": list(phases), "HoldS": args.hold, "BaselineS": args.baseline, "Plan": args.plan,
        "PlanNote": plan.note, "Ramp": plan.ramp,
        "Jumps": plan.jumps, "RestoreLevel": RESTORE_LEVEL, "HpOff": args.hp_off,
        "EchoS": ECHO_S, "AdminTimeoutS": ADMIN_TIMEOUT_S,
    }
    log.info("plan: %s", json.dumps(knobs))
    log.info("layout: %s sha256 %s scada %s", provenance.layout_path, provenance.layout_sha256[:12], provenance.scada_alias)
    for node in (PUMP_RELAY, ISO_RELAY, STORE_PUMP_RELAY, HP_RELAY):
        log.info("relay vocabulary: %s", relay_events(layout, node))
    if args.dry_run:
        return 0

    env = read_env(args.env)
    try:
        host = env.get("SCADA_ADMIN__HOST", "localhost")
        port = int(env.get("SCADA_ADMIN__PORT", "1883"))
        username, password = env["SCADA_ADMIN__USERNAME"], env["SCADA_ADMIN__PASSWORD"]
    except KeyError as e:
        raise SystemExit(f"{args.env} lacks {e}: the window scada's admin link must be enabled there") from None
    if env.get("SCADA_ADMIN__ENABLED", "").lower() != "true":
        raise SystemExit(f"{args.env}: SCADA_ADMIN__ENABLED is not true; the window scada has no admin link")

    link = AdminLink(host, port, username, password, provenance.scada_alias)
    sweep = Sweep(link, layout, plan, args.hold, args.baseline, args.hp_off)
    start_ms = now_ms()
    outcome = "PASS"
    link.start()
    try:
        sweep.run(phases)
    except LinkDead as e:
        outcome = f"ABORT: {e}"
        log.error("%s", outcome)
    except KeyboardInterrupt:
        outcome = "ABORT: interrupted"
        log.error("%s", outcome)
    except Exception as e:
        outcome = f"ABORT: {type(e).__name__}: {e}"
        log.exception("%s", outcome)
    finally:
        if "restore" in phases:
            sweep.restore()
        end_ms = now_ms()
        link.stop()
        results = args.out / f"sweep-{args.run}-results.json"
        results.write_text(json.dumps(sweep.to_jsonable(knobs, provenance, start_ms, end_ms, outcome), indent=1) + "\n")
        log.info("%s; %d readings, %d steps; wrote %s", outcome, len(link.readings), len(sweep.steps), results)
    return 0 if outcome == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
