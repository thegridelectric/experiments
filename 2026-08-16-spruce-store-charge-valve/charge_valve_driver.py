#!/usr/bin/env python3
"""Spruce charge-valve actuation driver — store-as-cool-storage groundwork.

Drives the gw108 flow-control manifold to answer two questions the Gw108
schematic cannot (it shows the relay drive, not the valve body's mechanical
fail-state). The sequence STARTS with the pump on and flow CONFIRMED, so a
later drop to 0 is meaningful (not a pump/pico artifact):

  Baseline  ISO OPEN, secondary pump ON. WAIT for secondary-flow to read a
            live, nonzero value (> BASELINE_MIN). This proves the pump runs,
            the pico is live, and gives a real baseline. ABORT if it never
            confirms within BASELINE_CONFIRM_MAX_S — never run the legs blind.
  Isolate   Close ISO (pump still on). Flow should collapse toward 0 — the
            pump now dead-heads (no path). Confirms isolation.
  Leg 1  energized  = OPEN?    Charge valve ENERGIZED. Flow RETURNS as the
                               store branch opens => the valve opens energized.
  Leg 2  de-energized = CLOSED? DE-ENERGIZE the charge valve. Flow collapses to
                               ~0 again as the valve shuts and the store pump's
                               one-way check valve blocks the return => fails
                               closed. Stop at the MINIMUM of (fresh flow <
                               0.5 GPM) or 45 s, dead-heading only as long as
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
  1. CONFIRMS a live, nonzero baseline before acting: pump on + ISO open, then
     wait until secondary-flow reads > BASELINE_MIN with a fresh read-time. A
     spin-down zero or a stale fossil never satisfies this; if it never confirms
     it ABORTS rather than running the legs blind (the first-run flaw: it started
     from a fresh-but-zero spin-down reading and manipulated into a pico gap).
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

FLOW_ON_MIN = 200            # GpmTimes100: "flow present" (> 2.0 GPM)
FLOW_NEAR_ZERO = 50          # GpmTimes100: "flow collapsed" (< 0.5 GPM)
BASELINE_MIN = 200           # GpmTimes100: baseline flow must exceed this (2 GPM)
                             # to confirm the pump runs + the pico is live

BASELINE_CONFIRM_MAX_S = 150  # abort if baseline flow never confirms in this long
FLOW_FRESH_S = 75            # a reading older than this (true age, by read-time)
                             # is not trusted as "current" — defeats stale fossils

LEG_SECONDS = 45             # max duration of each leg
DEADHEAD_OBSERVE_S = 30      # watch flow collapse after closing ISO
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
# Baseline confirmation + observation
# -----------------------------
def confirm_baseline_flow() -> int | None:
    """Poll until secondary-flow reads FRESH and > BASELINE_MIN — proving the
    pump runs, the pico is live, and there is real circulation (ISO open). A
    spin-down zero or a stale fossil never satisfies this. Returns the confirmed
    flow (GpmTimes100), or None on timeout (=> abort, do NOT run the legs)."""
    print(f"[{now_et()}] BASELINE: pump on + ISO open — waiting for live flow "
          f"> {gpm(BASELINE_MIN)} (up to {BASELINE_CONFIRM_MAX_S}s)...")
    deadline = time.monotonic() + BASELINE_CONFIRM_MAX_S
    while time.monotonic() < deadline:
        f = fresh_flow()
        if f is not None:
            v, age = f
            if v > BASELINE_MIN:
                print(f"[{now_et()}] BASELINE CONFIRMED: {gpm(v)} (read {age:.0f}s "
                      f"ago) — pump + pico live, proceeding.")
                return v
        time.sleep(POLL_S)
    print(f"[{now_et()}] BASELINE FAILED: no live flow > {gpm(BASELINE_MIN)} "
          f"within {BASELINE_CONFIRM_MAX_S}s. Aborting (pump off / pico down); "
          "retry later.")
    return None


def observe_flow(label: str, seconds: float):
    """Log fresh flow readings over a window; return the peak and last fresh
    values seen (GpmTimes100), or (None, None) if none arrived."""
    print(f"\n[{now_et()}] {label} — watching {seconds:.0f}s")
    end = time.monotonic() + seconds
    peak = last = None
    while time.monotonic() < end:
        f = fresh_flow()
        if f is not None:
            v, age = f
            print(f"    [{now_et()}] {WITNESS_CHANNEL} = {gpm(v)} (read {age:.0f}s ago)")
            last = v
            peak = v if peak is None else max(peak, v)
        time.sleep(POLL_S)
    return peak, last


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


def verdict(baseline, deadhead_last, leg1, leg2) -> None:
    leg1_peak, leg1_saw = leg1
    leg2_outcome, leg2_val, leg2_elapsed = leg2
    print("\n================= LIVE READ (corroborate with the DB pull) =================")
    print(f"BASELINE (ISO open, pump on): {gpm(baseline)} — pump + pico confirmed live.")
    if deadhead_last is None:
        print("ISOLATE (ISO closed): no fresh reading — can't confirm isolation.")
    elif deadhead_last < FLOW_NEAR_ZERO:
        print(f"ISOLATE (ISO closed): flow -> {gpm(deadhead_last)} — isolation confirmed "
              "(pump dead-heads with no store path).")
    else:
        print(f"ISOLATE (ISO closed): flow still {gpm(deadhead_last)} — ISO did NOT "
              "fully isolate (leak path or slow valve) — read leg 1 with care.")
    if not leg1_saw:
        print("LEG 1 (charge energized) NO DATA: no fresh reading — pico dropped; RETRY.")
    elif leg1_peak is not None and leg1_peak >= FLOW_ON_MIN:
        print(f"LEG 1 (charge energized) -> flow RETURNED to {gpm(leg1_peak)} "
              f"(>= {gpm(FLOW_ON_MIN)}): energized = OPEN.")
    else:
        print(f"LEG 1 (charge energized) -> flow stayed LOW ({gpm(leg1_peak) if leg1_peak is not None else 'n/a'}): "
              "energized did NOT open a store path — INVESTIGATE.")
    if leg2_outcome == "collapsed":
        print(f"LEG 2 (charge de-energized) -> flow collapsed to {gpm(leg2_val)} in "
              f"{leg2_elapsed:.0f}s: de-energized = CLOSED (spring-return fail-closed).")
    elif leg2_outcome == "still-flowing":
        print(f"LEG 2 (charge de-energized) -> flow still {gpm(leg2_val)} at {leg2_elapsed:.0f}s: "
              "did NOT close (bistable hold / normally-open) — INVESTIGATE.")
    else:
        print("LEG 2 (charge de-energized) NO DATA: no fresh reading — pico dropped; RETRY.")
    print("============================================================================")


# -----------------------------
# Main
# -----------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="spruce charge-valve actuation driver")
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
    baseline = None
    deadhead_last = None
    leg1 = (None, False)
    leg2 = ("no-fresh-reading", None, 0.0)
    try:
        # BASELINE: ISO open (normal path) + pump on, confirm live nonzero flow.
        set_bit(ISO_VALVE, ISO_VALVE_OPEN_STATE)
        set_secondary_speed(TEST_PUMP_PERCENT)
        set_bit(SECONDARY_PUMP, 1)
        print(f"[{now_et()}] iso-valve -> OPEN, secondary-pump -> ON at "
              f"{TEST_PUMP_PERCENT}%")
        baseline = confirm_baseline_flow()
        if baseline is None:
            return  # abort; finally restores safe posture

        window_start_ms = int(time.time() * 1000)

        # ISOLATE: close ISO, watch the pump dead-head toward 0.
        set_bit(ISO_VALVE, 0)
        print(f"[{now_et()}] iso-valve -> CLOSED; waiting {ISO_TRAVEL_S}s for travel")
        time.sleep(ISO_TRAVEL_S)
        _, deadhead_last = observe_flow(
            "ISOLATE: ISO CLOSED (expect flow -> 0, dead-head)", DEADHEAD_OBSERVE_S)

        leg1 = leg1_energized_open()
        leg2 = leg2_deenergized_closed()
        verdict(baseline, deadhead_last, leg1, leg2)
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
