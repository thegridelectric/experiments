#!/usr/bin/env python3
"""charge_valve_polarity — which drive state OPENS the gw108 charge valve?

The 2026-08-23 charge_store runs proved the iso-closed + charge-ENERGIZED
posture dead-heads the secondary pump completely (secondary side stagnant,
store branch untouched). Either the valve opens DE-energized (polarity
inverted from the working belief), or it is not passing water in any state
(wiring/actuator). Two legs decide it, no heat pump involvement needed —
the pump alone gives the signature:

  Per leg: set the charge-valve drive state, SOAK for SOAK_S (3 min) with
  iso OPEN and the pump running — the actuator is slow (George: possibly
  30 s before it even starts to move), so it gets its full travel time
  with no dead-head — then close iso and judge for up to LEG_S.
  Leg E  charge ENERGIZED first, then Leg D  charge DE-ENERGIZED.

Verdict per leg, from witnesses that do not depend on the flow meter's
placement: if the circuit flows, `secondary-lwt`/`secondary-ewt` move
toward store temperature (~59 F vs the loop's ~51 F) within minutes and
`store-hot-pipe` moves; if it dead-heads, everything stays flat.
`secondary-flow` is logged too (fresh readings only, judged on the pico's
own read time). A DEAD-HEAD GUARD ends a leg early: fresh flow below
FLOW_ZERO_GPM for FLOW_ZERO_HOLD_S after FLOW_GRACE_S — no long
dead-heads.

Coil ordering (relay-stress finding): the iso relay is only ENERGIZED with
two other 0x21 coils already on; between legs and on exit the sequence is
charge->1, hp->1, iso->1 (open), then hp->0, charge->per-leg/0. The POR
check runs after every write; a reset is repaired and logged.

Runs ON spruce (copy to ~/), summer hack STOPPED:
    sudo systemctl stop spruce-summer-hack
    ~/starter-scripts/venv/bin/python ~/charge_valve_polarity.py --yes
    sudo systemctl start spruce-summer-hack
Writes charge-valve-polarity.log + charge-valve-polarity-results.json to
/home/pi/relay-stress-runs/ and prints the actuation window for the pull.
"""

import argparse
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import NamedTuple
from zoneinfo import ZoneInfo

import paho.mqtt.client as mqtt
import smbus2

sys.path.insert(0, "/home/pi/starter-scripts")
from starter_settings import settings  # noqa: E402

LEG_S = float(os.environ.get("LEG_S", "300"))
SOAK_S = float(os.environ.get("SOAK_S", "180"))   # valve-travel soak, iso open, pump on
LEGS = os.environ.get("LEGS", "E,D").split(",")   # which legs, in order
POLL_S = 10
FLOW_ZERO_GPM = 0.5
FLOW_GRACE_S = 90
FLOW_ZERO_HOLD_S = 60
SNAPSHOT_MAX_AGE_S = 300
STEP_PAUSE_S = 2
ISO_TRAVEL_S = 12
OUT_DIR = Path(os.environ.get("OUT_DIR", "/home/pi/relay-stress-runs"))
ET = ZoneInfo("America/New_York")

HP_CALL = ("hp-call", 2, 0)
ISO_VALVE = ("iso-valve", 3, 2)
CHARGE_VALVE = ("charge-valve", 3, 3)
STORE_PUMP = ("store-pump", 3, 4)
SECONDARY_PUMP = ("secondary-pump", 3, 5)
EXPANDER = 0x21

WATCH = ("secondary-flow", "secondary-ewt", "secondary-lwt", "store-hot-pipe",
         "tank1-depth1", "tank1-depth2", "hp-odu-pwr")


class Sample(NamedTuple):
    """One witness sample within a leg (kind-specific record; no word —
    same note as relay_stress.PhaseResult). Values are wire units
    (temps C x1000 except tank1 F x100; flow GPM x100; power W); None =
    no fresh reading (own read time older than SNAPSHOT_MAX_AGE_S)."""
    leg: str
    t_s: float
    secondary_flow: int | None
    secondary_ewt: int | None
    secondary_lwt: int | None
    store_hot_pipe: int | None
    tank1_depth1: int | None
    hp_odu_pwr: int | None


logger = logging.getLogger("charge-valve-polarity")
logger.setLevel(logging.INFO)
OUT_DIR.mkdir(parents=True, exist_ok=True)
_fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
for _h in (logging.StreamHandler(),
           logging.FileHandler(OUT_DIR / "charge-valve-polarity.log")):
    _h.setFormatter(_fmt)
    logger.addHandler(_h)

bus = smbus2.SMBus(1)
samples: list[Sample] = []
resets = 0
wanted: dict[tuple, int] = {}   # every coil we command; re-asserted after a POR repair


def i2c_retry(fn, what, tries=4):
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except OSError as e:
            logger.critical(f"I2C ERROR during {what} ({attempt}/{tries}): {e}")
            if attempt == tries:
                raise
            time.sleep(1.0)


def write_bit(relay, value):
    _, reg, bit = relay

    def rmw():
        s = bus.read_byte_data(EXPANDER, reg)
        s = s | (1 << bit) if value else s & ~(1 << bit)
        bus.write_byte_data(EXPANDER, reg, s)
    i2c_retry(rmw, f"set {relay[0]}->{value}")


def set_bit(relay, value):
    write_bit(relay, value)
    wanted[relay] = value
    logger.info(f"  {relay[0]} -> {value}")
    check_reset(f"after {relay[0]}->{value}")


def cfg_nonzero():
    return (bus.read_byte_data(EXPANDER, 6) != 0
            or bus.read_byte_data(EXPANDER, 7) != 0)


def check_reset(context):
    global resets
    try:
        nz = cfg_nonzero()
    except OSError as e:
        logger.critical(f"I2C ERROR on POR check {context}: {e} — treating as reset")
        time.sleep(1.0)
        nz = True
    if not nz:
        return
    time.sleep(0.3)
    if not i2c_retry(cfg_nonzero, "confirm re-read"):
        return
    resets += 1
    logger.critical(f"0x21 RESET #{resets} {context} — re-init + re-assert")
    time.sleep(0.5)

    def clear():
        for reg in (2, 3, 6, 7):
            bus.write_byte_data(EXPANDER, reg, 0x00)
    i2c_retry(clear, "re-init")
    for relay, value in wanted.items():   # re-assert everything we command
        write_bit(relay, value)
    logger.info(f"  re-asserted: {[(r[0], v) for r, v in wanted.items()]}")


# --- snapshots ---------------------------------------------------------------
latest: dict[str, tuple[int, int]] = {}   # name -> (value, read_ms)
lock = threading.Lock()


def on_msg(client, userdata, msg):
    if "spruce" not in msg.topic:
        return
    try:
        p = json.loads(msg.payload).get("Payload", {})
    except Exception:
        return
    if p.get("TypeName") != "snapshot.spaceheat":
        return
    with lock:
        for x in p.get("LatestReadingList", []):
            n = x.get("ChannelName")
            if n in WATCH and x.get("Value") is not None and x.get("ScadaReadTimeUnixMs"):
                latest[n] = (int(x["Value"]), int(x["ScadaReadTimeUnixMs"]))


def fresh(name):
    with lock:
        r = latest.get(name)
    if r is None or time.time() * 1000 - r[1] > SNAPSHOT_MAX_AGE_S * 1000:
        return None
    return r[0]


def take_sample(leg, t_s):
    s = Sample(leg, round(t_s, 1), fresh("secondary-flow"), fresh("secondary-ewt"),
               fresh("secondary-lwt"), fresh("store-hot-pipe"),
               fresh("tank1-depth1"), fresh("hp-odu-pwr"))
    samples.append(s)
    def f(v, d): return "--" if v is None else round(v / d, 2)
    logger.info(f"  [{leg} t+{t_s:.0f}s] sec-flow={f(s.secondary_flow, 100)}gpm"
                f" sec-ewt={f(s.secondary_ewt, 1000)}C sec-lwt={f(s.secondary_lwt, 1000)}C"
                f" store-hot-pipe={f(s.store_hot_pipe, 1000)}C"
                f" tank1-top={f(s.tank1_depth1, 100)}F odu={s.hp_odu_pwr}W")
    return s


def open_iso_safely(charge_after: int) -> None:
    """Energize iso only with two other coils on (charge + hp), then settle."""
    set_bit(CHARGE_VALVE, 1)
    set_bit(HP_CALL, 1)
    time.sleep(STEP_PAUSE_S)
    set_bit(ISO_VALVE, 1)
    time.sleep(ISO_TRAVEL_S)
    set_bit(HP_CALL, 0)
    set_bit(CHARGE_VALVE, charge_after)


def run_leg(name: str, charge_state: int) -> str:
    drive = "ENERGIZED" if charge_state else "DE-ENERGIZED"
    logger.info(f"=== LEG {name}: charge-valve {drive}; soak {SOAK_S:.0f}s with iso"
                f" OPEN + pump ON (slow actuator), then iso CLOSED for up to {LEG_S:.0f}s ===")
    set_bit(CHARGE_VALVE, charge_state)
    t_soak = time.monotonic()
    while time.monotonic() - t_soak < SOAK_S:
        take_sample(name + "-soak", time.monotonic() - t_soak)
        check_reset(f"[{name} soak]")
        time.sleep(30)
    set_bit(ISO_VALVE, 0)          # de-energize: benign direction
    time.sleep(ISO_TRAVEL_S)       # let the iso valve travel shut
    t0 = time.monotonic()
    flow_zero_since = None
    verdict = "ran full leg"
    while time.monotonic() - t0 < LEG_S:
        t_s = time.monotonic() - t0
        s = take_sample(name, t_s)
        flow = None if s.secondary_flow is None else s.secondary_flow / 100.0
        if flow is not None and flow < FLOW_ZERO_GPM and t_s > FLOW_GRACE_S:
            if flow_zero_since is None:
                flow_zero_since = time.monotonic()
            elif time.monotonic() - flow_zero_since >= FLOW_ZERO_HOLD_S:
                logger.critical(f"DEAD-HEAD GUARD [{name}]: fresh secondary-flow"
                                f" {flow:.2f} gpm for {FLOW_ZERO_HOLD_S}s — ending leg")
                verdict = "dead-head guard"
                break
        elif flow is not None and flow >= FLOW_ZERO_GPM:
            flow_zero_since = None
        check_reset(f"[{name} poll]")
        time.sleep(POLL_S)
    logger.info(f"LEG {name} ended: {verdict}")
    # back to a safe intermediate: iso open (safely), pump stays on
    open_iso_safely(charge_after=0)
    take_sample(name + "-post", 0.0)
    return verdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()
    if not args.yes:
        if input("Confirm spruce-summer-hack is STOPPED [type yes]: ").strip() != "yes":
            return
    start_ms = int(time.time() * 1000)
    bus.write_byte_data(EXPANDER, 6, 0x00)   # direction only
    bus.write_byte_data(EXPANDER, 7, 0x00)
    client = mqtt.Client()
    client.username_pw_set(settings.mqtt_username, settings.mqtt_password.get_secret_value())
    client.on_message = on_msg
    client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=60)
    client.subscribe("gw/+/to/+/snapshot-spaceheat")
    client.loop_start()
    logger.info("waiting up to 60s for a first snapshot...")
    t0 = time.monotonic()
    while not latest and time.monotonic() - t0 < 60:
        time.sleep(1)
    verdicts = {}
    try:
        set_bit(STORE_PUMP, 0)
        set_bit(SECONDARY_PUMP, 1)
        set_bit(HP_CALL, 0)
        take_sample("baseline", 0.0)
        for leg in LEGS:
            verdicts[leg] = run_leg(leg, charge_state=1 if leg == "E" else 0)
    except KeyboardInterrupt:
        logger.info("interrupted")
    finally:
        open_iso_safely(charge_after=0)
        set_bit(SECONDARY_PUMP, 1)
        set_bit(HP_CALL, 0)
        end_ms = int(time.time() * 1000)
        out = OUT_DIR / "charge-valve-polarity-results.json"
        out.write_text(json.dumps({
            "StartUnixMs": start_ms, "EndUnixMs": end_ms,
            "Knobs": {"LEG_S": LEG_S, "SOAK_S": SOAK_S, "LEGS": LEGS,
                      "FLOW_ZERO_GPM": FLOW_ZERO_GPM,
                      "FLOW_GRACE_S": FLOW_GRACE_S, "FLOW_ZERO_HOLD_S": FLOW_ZERO_HOLD_S},
            "Verdicts": verdicts, "Resets": resets,
            "Samples": [s._asdict() for s in samples],
        }, indent=2))
        client.loop_stop()
        fmt = lambda ms: datetime.fromtimestamp(ms / 1000, ET).strftime("%Y-%m-%d %H:%M:%S %Z")
        logger.info(f"exit posture: iso OPEN, pump ON, hp 0, charge 0. Results -> {out}."
                    f" ACTUATION WINDOW: {fmt(start_ms)} -> {fmt(end_ms)}"
                    f" ({start_ms} -> {end_ms} unix ms). Restart the hack:"
                    " sudo systemctl start spruce-summer-hack")


if __name__ == "__main__":
    main()
