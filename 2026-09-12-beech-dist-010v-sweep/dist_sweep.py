#!/usr/bin/env python3
"""dist_sweep — the beech dist-010v sweep driver (house0-zero-ten-outputs
witness).

Runs ON BEECH, from the box's `~/experiments` clone at a pushed SHA, with the
unlimbo checkout's venv, against the window scada's admin link on the box's
own mosquitto (the spruce sweep's reasons: a window that holds a real pump
must not depend on the laptop's tunnel).

    cd ~/experiments/2026-09-12-beech-dist-010v-sweep
    setsid nohup timeout 3600 ~/gridworks-scada-unlimbo/gw_spaceheat/venv/bin/python \
        dist_sweep.py --run 1 > /tmp/beech-dist-sweep/sweep-1.stdout 2>&1 < /dev/null &

What it does, in order (each phase selectable with --phases):
  call      admin takes the zone's failsafe relay (SwitchToScada) and closes
            its ops relay: a heat call, so the Caleffi zone box starts the
            distribution pump (about 40 s on beech, krida witness 09-11);
            then waits up to CALL_WAIT_S for a non-zero dist-flow reading
            (a verdict, not an abort: in the dev rung nothing flows).
  baseline  hold the DAC where it boots (the ops word's power-on level, beech
            35 = 3.5 V) for BASELINE_S; record flow and pump power.
  up        the plan's ramp, HOLD_S per level.
  down      the ramp reversed: hysteresis.
  jumps     a fixed pseudo-random sequence over the same levels.
  restore   ALWAYS runs, on success and on abort: the DAC back to the ops
            power-on level, the call released (OpenRelay, then
            SwitchToWallThermostat), admin released.

The wire shape is the admin TUI's, built from the gwsproto types directly
(AdminAnalogDispatch / AdminDispatch(FsmEvent) / SendSnap /
AdminReleaseControl in a gwproto Message envelope) — the spruce sweep's
driver on the House0 layout word. Relay event vocabulary and the expected
states come from the relay's own `relay.control.config` in the layout the
scada boots; the power-on level from the ops artifact beside it.

Liveness: every command waits for its echo on the admin link — the
outputer's VoltsTimesTen reading after an analog dispatch, a snapshot
showing the relay in its config's declared state after a relay dispatch.
No echo within ECHO_S aborts the sweep into restore.

Output (OUT_DIR, default /tmp/beech-dist-sweep — scp'd back by the runbook,
nothing stays in the pi's home dir):
  sweep-<run>.log            every command, echo, state change and snapshot
  sweep-<run>-results.json   typed records: steps, relay commands, readings,
                             machine states, knobs, the run window, the
                             artifacts' sha256
The results file is kind-specific structure (no sema word yet; the
`gw.readings` + `gw.experiment.run` instances are emitted on the dev
machine from it, as the spruce rung does). Missing word to retire the
record: a `gw.experiment.step` naming a commanded level and its hold.
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
from gwsproto.named_types import (
    AdminAnalogDispatch,
    AdminDispatch,
    AdminReleaseControl,
    AnalogDispatch,
    FsmEvent,
    House0Layout,
    House0OperationalParams,
    SendSnap,
    SingleReading,
    SnapshotSpaceheat,
)
from gwsproto.property_format import SpaceheatName
from pydantic import TypeAdapter

# ---- knobs -----------------------------------------------------------------

ADMIN = "admin"  # the admin link's peer name (H0N.admin)
DAC_NODE = "dist-010v"
FLOW_CHANNEL = "dist-flow"
POWER_CHANNEL = "dist-pump-pwr"
WATCHED = (DAC_NODE, FLOW_CHANNEL, POWER_CHANNEL)
DEFAULT_ZONE = "zone1-down"  # beech; the dev rung on the fixture uses zone1-main


class Plan(NamedTuple):
    """The levels a run visits: the ramp (up, then reversed for down), the
    jump sequence, and a one-line statement of what the plan is for."""

    ramp: list[int]
    jumps: list[int]
    note: str


PLANS = {
    "full": Plan(
        ramp=list(range(0, 101, 10)),
        jumps=[20, 80, 40, 100, 10, 60, 0, 90, 30, 70, 50],
        note="uniform 0-10 V at 1 V; the pump's stop band and range are unknown on beech",
    ),
    "short": Plan(
        ramp=[20, 50, 80, 100],
        jumps=[35],
        note="four levels and back to the deployed 3.5 V: a five-minute witness",
    ),
}
HOLD_S = 60
BASELINE_S = 120
CALL_WAIT_S = 90  # the Caleffi box started beech's dist pump ~32-40 s after the call (09-11)
RELAY_GAP_S = 5
SNAP_S = 30  # SendSnap cadence; the scada also pushes snapshots on its own
ECHO_S = 15  # no echo of a command within this = the scada is not listening
STATE_POLL_S = 3
ADMIN_TIMEOUT_S = 900  # renewed by every command; > the longest silent hold
CONNECT_S = 20
PHASES = ("call", "baseline", "up", "down", "jumps", "restore")

DEFAULT_ENV = Path("~/envs/dev.env").expanduser()
DEFAULT_LAYOUT = Path("~/.config/gridworks/scada-experiment/hardware-layout.json").expanduser()
DEFAULT_OPS = Path("~/.config/gridworks/scada-experiment/operational-params.json").expanduser()
DEFAULT_OUT = Path("/tmp/beech-dist-sweep")

_SPACEHEAT = TypeAdapter(SpaceheatName)

log = logging.getLogger("dist_sweep")


# ---- typed records ----------------------------------------------------------


class Reading(NamedTuple):
    """One reading the scada reported on the admin link (a snapshot entry or a
    forwarded SingleReading); the value is the channel word's wire encoding
    (VoltsTimesTen, GpmTimes100, PowerW)."""

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
    """A relay node's event vocabulary and the states each event lands in, as
    its `relay.control.config` declares them."""

    node: SpaceheatName
    event_type: str
    energizing: str
    energized_state: str
    de_energizing: str
    de_energized_state: str


class Provenance(NamedTuple):
    """The artifact pair the scada under test booted, by path and content
    hash, and the power-on level the ops word declares for the DAC node."""

    layout_path: str
    layout_sha256: str
    ops_path: str
    ops_sha256: str
    scada_alias: str
    power_on_volts_times_ten: int


# ---- layout facts -----------------------------------------------------------


def load_pair(layout_path: Path, ops_path: Path) -> tuple[House0Layout, Provenance]:
    raw = layout_path.read_bytes()
    layout = House0Layout.model_validate(json.loads(raw))
    ops_raw = ops_path.read_bytes()
    ops = House0OperationalParams.model_validate(json.loads(ops_raw))
    alias = next(g.Alias for g in layout.GNodes if g.Alias.endswith(".scada"))
    power_on = next(e.PowerOnVoltsTimesTen for e in ops.ZeroTenPowerOnList if e.NodeName == DAC_NODE)
    return layout, Provenance(
        str(layout_path), hashlib.sha256(raw).hexdigest(),
        str(ops_path), hashlib.sha256(ops_raw).hexdigest(),
        alias, power_on,
    )


def relay_events(layout: House0Layout, node_name: str) -> RelayEvents:
    node = next(n for n in layout.ShNodes if n.Name == node_name)
    component = next(c for c in layout.Components if c.ComponentId == node.ComponentId)
    config = next(c for c in component.ConfigList if c.ChannelName == node_name)
    return RelayEvents(
        node=_SPACEHEAT.validate_python(node_name),
        event_type=config.EventType,
        energizing=config.EnergizingEvent,
        energized_state=config.EnergizedState,
        de_energizing=config.DeEnergizingEvent,
        de_energized_state=config.DeEnergizedState,
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

    def __init__(self, host: str, port: int, username: str, password: str, scada_alias: str, relays: tuple[str, ...]):
        self.scada_alias = scada_alias
        self.relays = relays
        self.readings: list[Reading] = []
        self.states: list[MachineState] = []
        self.seen: set[tuple[str, int]] = set()
        self.lock = threading.Lock()
        self.connected = threading.Event()
        self.snapshots = 0
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"dist-sweep-{uuid.uuid4().hex[:8]}")
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
        relays = {s.MachineHandle: s.State for s in snap.LatestStateList if s.MachineHandle.split(".")[-1] in self.relays}
        log.info("snapshot %d: %d readings, %d states; relays %s", self.snapshots, len(snap.LatestReadingList), len(snap.LatestStateList), relays)

    def take(self, reading: Reading, source: str) -> None:
        key = (reading.channel, reading.unix_ms)
        with self.lock:
            if key in self.seen:
                return
            self.seen.add(key)
            self.readings.append(reading)
        if reading.channel in WATCHED:
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
        `node`, whatever its boss is at the moment."""
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
    def __init__(self, link: AdminLink, layout: House0Layout, plan: Plan, hold_s: int, baseline_s: int,
                 failsafe: str, ops_relay: str, restore_level: int):
        self.link = link
        self.layout = layout
        self.plan = plan
        self.hold_s = hold_s
        self.baseline_s = baseline_s
        self.failsafe = relay_events(layout, failsafe)
        self.ops_relay = relay_events(layout, ops_relay)
        self.restore_level = restore_level
        self.steps: list[Step] = []
        self.relay_commands: list[RelayCommand] = []
        self.verdicts: list[str] = []
        self.last_snap_request = 0.0

    def verdict(self, ok: bool, what: str) -> None:
        self.verdicts.append(f"{'PASS' if ok else 'FAIL'} {what}")
        log.info(self.verdicts[-1])

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

    def relay(self, ev: RelayEvents, energized: bool, label: str) -> None:
        event = ev.energizing if energized else ev.de_energizing
        expected = ev.energized_state if energized else ev.de_energized_state
        sent = now_ms()
        self.link.publish(
            AdminDispatch(
                DispatchTrigger=FsmEvent(
                    FromHandle=ADMIN,
                    ToHandle=f"{ADMIN}.{ev.node}",
                    EventType=ev.event_type,
                    EventName=event,
                    SendTimeUnixMs=sent,
                    TriggerId=str(uuid.uuid4()),
                ),
                TimeoutSeconds=ADMIN_TIMEOUT_S,
            )
        )
        echo = self.link.await_state(ev.node, expected)
        self.relay_commands.append(RelayCommand(ev.node, event, sent, echo))
        if echo is None:
            raise LinkDead(f"{label}: {ev.node} not {expected} after {event} within {ECHO_S}s")
        log.info("%s: %s %s -> %s seen after %.1fs", label, ev.node, event, expected, (echo - sent) / 1000)
        time.sleep(RELAY_GAP_S)

    def call(self) -> None:
        """The heat call: failsafe to scada, ops relay closed; then the pump."""
        self.relay(self.failsafe, True, "call")
        self.relay(self.ops_relay, True, "call")
        sent = now_ms()
        flow_at = self.await_flow(sent)
        self.verdict(flow_at is not None, f"{FLOW_CHANNEL} non-zero within {CALL_WAIT_S}s of the call"
                     + (f" ({(flow_at - sent) / 1000:.0f}s)" if flow_at else ""))

    def await_flow(self, after_ms: int) -> int | None:
        deadline = time.time() + CALL_WAIT_S
        while time.time() < deadline:
            if time.time() - self.last_snap_request >= STATE_POLL_S:
                self.link.request_snapshot()
                self.last_snap_request = time.time()
            r = self.link.latest(FLOW_CHANNEL)
            if r is not None and r.unix_ms >= after_ms and r.value > 0:
                return r.unix_ms
            time.sleep(0.5)
        return None

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
        if "call" in phases:
            self.call()
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

    def restore(self, release_call: bool) -> None:
        """Always runs, on success and on abort: the DAC back to the ops
        power-on level, the call released, admin released. Best effort;
        every failure is logged."""
        try:
            self.dispatch("restore", self.restore_level, 10)
        except Exception:
            log.exception("restore: the DAC dispatch did not echo; the pump may be off the power-on level")
        if release_call:
            for ev, label in ((self.ops_relay, "release"), (self.failsafe, "release")):
                try:
                    self.relay(ev, False, label)
                except Exception:
                    log.exception("restore: %s did not reach its de-energized state", ev.node)
        try:
            self.link.publish(AdminReleaseControl())
        except Exception:
            log.exception("restore: release did not publish")

    def to_jsonable(self, knobs: dict, provenance: Provenance, start_ms: int, end_ms: int, outcome: str) -> dict:
        return {
            "Outcome": outcome,
            "Verdicts": self.verdicts,
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
    p.add_argument("--ops", type=Path, default=DEFAULT_OPS, help="the operational params beside it")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--zone", default=DEFAULT_ZONE, help="the zone whose relays make the heat call")
    p.add_argument("--plan", choices=sorted(PLANS), default="full", help="which levels to visit; see PLANS")
    p.add_argument("--hold", type=int, default=HOLD_S)
    p.add_argument("--baseline", type=int, default=BASELINE_S)
    p.add_argument("--phases", default=",".join(PHASES), help=f"comma list from {PHASES}")
    p.add_argument("--dry-run", action="store_true", help="print the plan and the relay vocabulary; no broker")
    args = p.parse_args(argv)

    phases = tuple(x for x in args.phases.split(",") if x)
    unknown = set(phases) - set(PHASES)
    if unknown:
        p.error(f"unknown phases {sorted(unknown)}")
    failsafe, ops_relay = f"{args.zone}-failsafe-relay", f"{args.zone}-ops-relay"

    args.out.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(args.out / f"sweep-{args.run}.log"), logging.StreamHandler(sys.stdout)],
    )

    layout, provenance = load_pair(args.layout, args.ops)
    plan = PLANS[args.plan]
    knobs = {
        "Phases": list(phases), "HoldS": args.hold, "BaselineS": args.baseline, "CallWaitS": CALL_WAIT_S,
        "Plan": args.plan, "PlanNote": plan.note, "Ramp": plan.ramp, "Jumps": plan.jumps,
        "Zone": args.zone, "RestoreLevel": provenance.power_on_volts_times_ten,
        "EchoS": ECHO_S, "AdminTimeoutS": ADMIN_TIMEOUT_S,
    }
    log.info("plan: %s", json.dumps(knobs))
    log.info("layout: %s sha256 %s scada %s; ops sha256 %s power-on %d",
             provenance.layout_path, provenance.layout_sha256[:12], provenance.scada_alias,
             provenance.ops_sha256[:12], provenance.power_on_volts_times_ten)
    for node in (failsafe, ops_relay):
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

    link = AdminLink(host, port, username, password, provenance.scada_alias, (failsafe, ops_relay))
    sweep = Sweep(link, layout, plan, args.hold, args.baseline, failsafe, ops_relay, provenance.power_on_volts_times_ten)
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
            sweep.restore(release_call="call" in phases)
        end_ms = now_ms()
        link.stop()
        results = args.out / f"sweep-{args.run}-results.json"
        results.write_text(json.dumps(sweep.to_jsonable(knobs, provenance, start_ms, end_ms, outcome), indent=1) + "\n")
        log.info("%s; %d readings, %d steps; %s; wrote %s", outcome, len(link.readings), len(sweep.steps),
                 " | ".join(sweep.verdicts) or "no verdicts", results)
    return 0 if outcome == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
