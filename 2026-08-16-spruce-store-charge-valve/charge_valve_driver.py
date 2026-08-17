#!/usr/bin/env python3
"""Spruce charge-valve actuation driver — store-as-cool-storage groundwork.

Drives the gw108 flow-control manifold to answer two questions the Gw108
schematic cannot (it shows the relay drive, not the valve body's mechanical
fail-state):

  Leg 1  energized  = OPEN?    ISO closed, secondary pump on, charge valve
                               ENERGIZED. Flow through the store branch rises
                               => the valve opens when energized.
  Leg 2  de-energized = CLOSED? Keep ISO closed + pump on, DE-ENERGIZE the
                               charge valve. Flow collapses to ~0 as the valve
                               shuts and the store pump's one-way check valve
                               blocks the return => the valve fails closed.
                               Stop at the MINIMUM of (fresh flow < 0.5 GPM)
                               or 45 s, so the pump dead-heads only as long as
                               it takes to get the answer.

Charge valve = the relay silkscreened "DISCHARGE VALVE" (0x21 reg3 bit3); it is
the "Charge Valve" on the Nolan layout. Schematic (Gw108 RevB, fcm_outputs):
one SPDT relay, COM = valve actuator, NO = 24VAC_R (hot), NC = 24VAC_COM, no
failsafe relay. So energized -> powered, de-energized -> unpowered; the
single-relay 2-wire drive is the signature of a spring-return (fail-closed)
actuator, which this test confirms.

WITNESS DISCIPLINE (why this driver is not the arbiter). The secondary-btu
pico that feeds `secondary-flow` drops out for 13-14 min at a stretch (the
zombie-shake loop; see this folder's README and 2026-08-03-pico-gap-analysis
Finding 1). During a dropout the scada snapshot rebroadcasts the last value
with its stale ScadaReadTimeUnixMs (OPS-497). The FIRST run of this test
(2026-08-16 13:31:59-13:33:46 ET) fell inside such a dropout and read a frozen
7.42 GPM throughout -> inconclusive.

So this driver:
  1. GATES on true liveness before acting: it only starts when a secondary-flow
     reading's own ScadaReadTimeUnixMs is younger than FRESH_GATE_S (proving the
     pico is not mid-dropout). In --auto-wait it blocks until a clean window
     opens; otherwise it aborts.
  2. judges flow live ONLY on ScadaReadTimeUnixMs age, never receipt age.
  3. prints the exact actuation WINDOW (ET + unix ms) on exit. The AUTHORITATIVE
     verdict comes from a retrospective `gw.readings` pull over that window (see
     README) — the DB carries real read-times and cannot be fooled by a fossil.
     The live PASS/FAIL below is a convenience read, corroborated by the pull.

WHAT IT TOUCHES: only the 0x21 iso-valve / secondary-pump / charge-valve bits,
via read-modify-write, so the 0x20 zone holds are preserved bit-for-bit. It
never clears an expander and never writes the 0x20 relays. On the broker it
only SUBSCRIBES (reads snapshots) — no emissions.

PRECONDITION: run with the summer hack STOPPED (single writer on 0x21):
    sudo systemctl stop spruce-summer-hack
Leave the deployed scada RUNNING — we read its snapshots.

ALWAYS restores a safe posture on exit (success, error, Ctrl-C): charge valve
OFF, secondary pump OFF, ISO valve OPEN. Restarting the summer hack is a
separate step:
    sudo systemctl start spruce-summer-hack
"""

import argparse
import json
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import board
import smbus2
import adafruit_tca9548a
import adafruit_mcp4728

sys.path.insert(0, "/home/pi/starter-scripts")
from starter_settings import settings  # noqa: E402  (prod broker creds)

ET = ZoneInfo("America/New_York")

# -----------------------------
# Configuration
# -----------------------------
TEST_PUMP_PERCENT = 65.0     # secondary pump speed (matches prod)
RAW_PER_VOLT = 400           # DAC calibration (per spruce_summer_hack)
ISO_VALVE_OPEN_STATE = 1     # energized (1) = OPEN (field-verified 2026-07-16)
CHARGE_VALVE_OPEN_STATE = 1  # HYPOTHESIS under test: energized (1) = OPEN

FLOW_ON_MIN = 200            # GpmTimes100: leg 1 "flow present" (> 2.0 GPM)
FLOW_NEAR_ZERO = 50          # GpmTimes100: leg 2 "flow collapsed" (< 0.5 GPM)

FRESH_GATE_S = 360           # pre-gate: secondary-flow read younger than this
                             # (< one full 13-14 min dropout) => pico is live
FLOW_FRESH_S = 75            # during legs: a reading older than this is not
                             # trusted as "current" (true age, from read-time)
GATE_WAIT_MAX_S = 1200       # --auto-wait: give up after this long with no window

LEG_SECONDS = 45             # max duration of each leg
POLL_S = 2                   # loop cadence
ISO_TRAVEL_S = 12            # let the motorized ISO valve finish closing
SETTLE_BEFORE_EXIT_S = 4     # leg 2: min time before honoring the near-0 exit
STEP_PAUSE_S = 2             # pause between sequenced actuations

# gw108 expander bits: (label, i2c address, register, bit) — per gw108_test_code
ISO_VALVE = ("iso-valve", 0x21, 3, 2)
SECONDARY_PUMP = ("secondary-pump", 0x21, 3, 5)
CHARGE_VALVE = ("charge-valve", 0x21, 3, 3)  # silk "DISCHARGE VALVE"

WITNESS_CHANNEL = "secondary-flow"

# -----------------------------
# i2c relays (0x21 only; read-modify-write)
# -----------------------------
bus = smbus2.SMBus(1)


def set_bit(relay, value: int) -> None:
    _, addr, reg, bit = relay
    status = bus.read_byte_data(addr, reg)
    status = status | (1 << bit) if value else status & ~(1 << bit)
    bus.write_byte_data(addr, reg, status)


def config_healthy() -> bool:
    """0x21 config regs (6,7) == 0 => pins are outputs (not POR / reset)."""
    return bus.read_byte_data(0x21, 6) == 0 and bus.read_byte_data(0x21, 7) == 0


# Secondary pump 0-10V speed on dac2 (mux ch2) channel_c — the Z6 zone output,
# per spruce_summer_hack after the 2026-08-10 rewire off dead dac3. Optional:
# on signal loss the UPMS 20-78 runs at minimum speed (enough to see a path).
try:
    _i2c = board.I2C()
    _tca = adafruit_tca9548a.TCA9548A(_i2c)
    dac2 = adafruit_mcp4728.MCP4728(_tca[2])
    dac2.channel_c.vref = adafruit_mcp4728.Vref.INTERNAL
    dac2.channel_c.gain = 1
except Exception as _e:  # noqa: BLE001
    dac2 = None
    print(f"WARN: DAC init failed ({_e}) — pump runs at minimum speed")


def set_secondary_speed(percent: float) -> None:
    if dac2 is None:
        return
    pct = max(0.0, min(100.0, percent))
    volts = 3.0 + (pct / 100.0) * 7.0  # UPMS 20-78: 3V min .. 10V max, linear
    try:
        dac2.channel_c.raw_value = max(0, min(4095, round(volts * RAW_PER_VOLT)))
    except Exception as e:  # noqa: BLE001
        print(f"WARN: DAC write failed ({e}) — pump at minimum speed")


# -----------------------------
# Snapshot listener — TRUE age from ScadaReadTimeUnixMs
# -----------------------------
_flow = {}  # {"value": int, "read_ms": int}


def _on_message(client, userdata, msg):
    if "spruce" not in msg.topic:
        return
    try:
        p = json.loads(msg.payload).get("Payload", {})
        if p.get("TypeName") != "snapshot.spaceheat":
            return
        for x in p.get("LatestReadingList", []):
            if x.get("ChannelName") == WITNESS_CHANNEL and x.get("Value") is not None:
                _flow["value"] = int(x["Value"])
                _flow["read_ms"] = int(x["ScadaReadTimeUnixMs"])
    except Exception:  # noqa: BLE001
        pass


def start_listener():
    import paho.mqtt.client as mqtt
    c = mqtt.Client()
    c.username_pw_set(settings.mqtt_username, settings.mqtt_password.get_secret_value())
    c.on_message = _on_message
    c.connect(settings.mqtt_host, settings.mqtt_port, keepalive=60)
    c.subscribe("gw/+/to/+/snapshot-spaceheat")
    c.loop_start()
    return c


def fresh_flow():
    """(value_gpm_x100, true_age_s) if a reading exists AND its scada read-time
    is younger than FLOW_FRESH_S, else None. True age defeats snapshot fossils."""
    if "read_ms" not in _flow:
        return None
    age = time.time() - _flow["read_ms"] / 1000.0
    if age > FLOW_FRESH_S:
        return None
    return _flow["value"], age


def now_et() -> str:
    return datetime.now(ET).strftime("%H:%M:%S")


def gpm(v) -> str:
    return f"{v / 100.0:.2f} GPM"


# -----------------------------
# Liveness gate
# -----------------------------
def wait_for_live_pico(auto_wait: bool) -> bool:
    """True once secondary-flow's own read-time is younger than FRESH_GATE_S
    (the pico is not mid-dropout). In auto-wait, block up to GATE_WAIT_MAX_S."""
    deadline = time.monotonic() + (GATE_WAIT_MAX_S if auto_wait else 30)
    warned = False
    while time.monotonic() < deadline:
        if "read_ms" in _flow:
            age = time.time() - _flow["read_ms"] / 1000.0
            if age < FRESH_GATE_S:
                print(f"[{now_et()}] GATE OPEN: {WITNESS_CHANNEL} read {age:.0f}s "
                      f"ago (< {FRESH_GATE_S}s) — pico live, proceeding.")
                return True
            if not warned:
                print(f"[{now_et()}] GATE WAIT: {WITNESS_CHANNEL} last read "
                      f"{age:.0f}s ago (need < {FRESH_GATE_S}s) — pico may be "
                      f"mid-dropout.{' waiting...' if auto_wait else ''}")
                warned = True
        time.sleep(POLL_S)
    print(f"[{now_et()}] GATE FAILED: no live {WITNESS_CHANNEL} window within "
          f"{'the wait budget' if auto_wait else '30s'}. Aborting (retry later).")
    return False


# -----------------------------
# Legs
# -----------------------------
def leg1_energized_open():
    """Charge valve ENERGIZED; watch flow. Returns (peak_x100_or_None,
    saw_fresh)."""
    print(f"\n[{now_et()}] === LEG 1: charge valve ENERGIZED (expect flow = open) ===")
    set_bit(CHARGE_VALVE, CHARGE_VALVE_OPEN_STATE)
    peak = None
    saw = False
    end = time.monotonic() + LEG_SECONDS
    while time.monotonic() < end:
        f = fresh_flow()
        if f is not None:
            saw = True
            v, age = f
            print(f"    [{now_et()}] {WITNESS_CHANNEL} = {gpm(v)} (read {age:.0f}s ago)")
            if peak is None or v > peak:
                peak = v
        time.sleep(POLL_S)
    return peak, saw


def leg2_deenergized_closed():
    """Charge valve DE-ENERGIZED; poll until fresh flow < near-zero or
    LEG_SECONDS. Returns (outcome, last_value, elapsed_s). outcome in
    {'collapsed','still-flowing','no-fresh-reading'}."""
    print(f"\n[{now_et()}] === LEG 2: charge valve DE-ENERGIZED (expect flow -> 0) ===")
    set_bit(CHARGE_VALVE, 0)
    start = time.monotonic()
    last = None
    saw = False
    while True:
        elapsed = time.monotonic() - start
        f = fresh_flow()
        if f is not None:
            saw = True
            last, age = f
            print(f"    [{now_et()}] {WITNESS_CHANNEL} = {gpm(last)} "
                  f"(read {age:.0f}s ago, t+{elapsed:.0f}s)")
            if elapsed >= SETTLE_BEFORE_EXIT_S and last < FLOW_NEAR_ZERO:
                return "collapsed", last, elapsed
        if elapsed >= LEG_SECONDS:
            return ("still-flowing" if saw else "no-fresh-reading"), last, elapsed
        time.sleep(POLL_S)


def verdict(leg1_peak, leg1_saw, leg2_outcome, leg2_val, leg2_elapsed) -> None:
    print("\n================= LIVE READ (corroborate with the DB pull) =================")
    if not leg1_saw:
        print("LEG 1 NO DATA: no fresh flow reading — pico dropped mid-leg; RETRY.")
    elif leg1_peak is not None and leg1_peak >= FLOW_ON_MIN:
        print(f"LEG 1 -> energized = OPEN. Peak {gpm(leg1_peak)} (>= {gpm(FLOW_ON_MIN)}).")
    else:
        print(f"LEG 1 -> LOW/NO FLOW ({gpm(leg1_peak) if leg1_peak is not None else 'n/a'}). "
              "Either energized != open, ISO didn't isolate, or no store path — INVESTIGATE.")
    if leg2_outcome == "collapsed":
        print(f"LEG 2 -> de-energized = CLOSED. Flow collapsed to {gpm(leg2_val)} "
              f"in {leg2_elapsed:.0f}s (spring-return fail-closed).")
    elif leg2_outcome == "still-flowing":
        print(f"LEG 2 -> DID NOT CLOSE. Flow still {gpm(leg2_val)} at {leg2_elapsed:.0f}s "
              "(bistable hold or plumbed normally-open) — INVESTIGATE.")
    else:
        print("LEG 2 NO DATA: no fresh flow reading — pico dropped mid-leg; RETRY.")
    print("============================================================================")


# -----------------------------
# Main
# -----------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="spruce charge-valve actuation driver")
    ap.add_argument("--auto-wait", action="store_true",
                    help=f"block up to {GATE_WAIT_MAX_S}s for a live pico window "
                         "(default: abort if not live within 30s)")
    ap.add_argument("--yes", action="store_true",
                    help="skip the 'summer hack stopped?' confirmation")
    args = ap.parse_args()

    print(f"=== spruce charge-valve driver  {datetime.now(ET):%Y-%m-%d %H:%M:%S %Z} ===")
    if not args.yes:
        print("Stop the summer hack first:  sudo systemctl stop spruce-summer-hack")
        if input("Confirm spruce-summer-hack is STOPPED [type yes]: ").strip() != "yes":
            print("Aborted.")
            return

    if not config_healthy():
        print("ABORT: 0x21 config registers nonzero (expander in reset/POR). "
              "Restart the summer hack to re-init, then retry.")
        return

    # Ensure 0x21 pins are outputs (direction only; no value change).
    bus.write_byte_data(0x21, 6, 0x00)
    bus.write_byte_data(0x21, 7, 0x00)

    client = start_listener()
    window_start_ms = None
    leg1 = (None, False)
    leg2 = ("no-fresh-reading", None, 0.0)
    try:
        if not wait_for_live_pico(args.auto_wait):
            return

        # Isolate: ISO CLOSED, let it travel.
        set_bit(ISO_VALVE, 0)
        print(f"[{now_et()}] iso-valve -> CLOSED; waiting {ISO_TRAVEL_S}s for travel")
        time.sleep(ISO_TRAVEL_S)

        # Secondary pump ON at test speed.
        set_secondary_speed(TEST_PUMP_PERCENT)
        set_bit(SECONDARY_PUMP, 1)
        print(f"[{now_et()}] secondary-pump -> ON at {TEST_PUMP_PERCENT}%")
        time.sleep(STEP_PAUSE_S)

        window_start_ms = int(time.time() * 1000)
        leg1 = leg1_energized_open()
        leg2 = leg2_deenergized_closed()
        verdict(leg1[0], leg1[1], *leg2)
    finally:
        set_bit(CHARGE_VALVE, 0)
        set_bit(SECONDARY_PUMP, 0)
        set_bit(ISO_VALVE, ISO_VALVE_OPEN_STATE)
        window_end_ms = int(time.time() * 1000)
        print(f"\n[{now_et()}] RESTORE: charge-valve OFF, secondary-pump OFF, "
              "iso-valve OPEN.")
        if window_start_ms is not None:
            s = datetime.fromtimestamp(window_start_ms / 1000, ET)
            e = datetime.fromtimestamp(window_end_ms / 1000, ET)
            # a little padding each side helps the DB pull catch settling flow
            print("\n>>> ACTUATION WINDOW for the authoritative gw.readings pull:")
            print(f"      --start '{(s).strftime('%Y-%m-%d %H:%M')}' "
                  f"--end '{(e).strftime('%Y-%m-%d %H:%M')}'  "
                  f"(exact: {s:%H:%M:%S} -> {e:%H:%M:%S} ET;  "
                  f"unix ms {window_start_ms}..{window_end_ms})")
            print("    (widen by a minute each side; see README for the full command)")
        client.loop_stop()
        client.disconnect()
        print("done. (summer hack restart is a separate step)")


if __name__ == "__main__":
    main()
