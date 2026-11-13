#!/usr/bin/env python3
"""Spruce living-room fan-coil -> distribution-pump test (2026-08-15).

George reports the living-room (zone 5) fan-coil thermostat "wasn't
working". This forces the zone-5 cool call via the scada relay, bypassing
the wall thermostat, and watches the distribution pump. If the pump runs on
a forced call, the fault is UPSTREAM (thermostat / whitewire); if it does
not, the fault is DOWNSTREAM (relay -> Caleffi -> dist pump -> fan-coil).

Zones 3 (upstairs fan-coil) and 5 (living-room fan-coil) share the
distribution pump, so we take control of BOTH, hold 3 OFF, and toggle 5 to
isolate zone 5's effect on the pump.

WHAT IT TOUCHES: only the 0x20 zone-3 and zone-5 relays (read-modify-write,
so the 1/2/4 floor holds are preserved bit-for-bit). It never writes 0x21
(hp call / secondary pump / iso valve) or the DAC/mux. On the broker it only
SUBSCRIBES (reads snapshots) — no emissions.

PRECONDITION: run with the summer hack STOPPED (nothing else drives 0x20).
Leave the deployed actual-spruce scada RUNNING — we read its snapshots.

ALWAYS restores zones 3 & 5 to thermostat control on exit (success, error,
or Ctrl-C), the safe failsafe direction. Restarting the summer hack is a
separate step outside this script.

Channels watched (from the actual-spruce layout):
  dist-pump-pwr  PowerW        async, 5 W delta, 1 s poll (the pump itself)
  dist-flow      GpmTimes100   async on-change (distribution flow)
  secondary-flow GpmTimes100   context (HX side; off while hack stopped)
  primary-flow   GpmTimes100   context
"""

import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

import paho.mqtt.client as mqtt
import smbus2

sys.path.insert(0, "/home/pi/starter-scripts")
from starter_settings import settings  # noqa: E402  (prod broker creds)

ET = ZoneInfo("America/New_York")

# --- i2c: gw108 zone expander 0x20 -----------------------------------------
# Zone n failsafe relay = reg2 bit(n-1) (1 = scada takes the zone from the
# stat); zone n scada/ops relay = reg3 bit(n-1) (1 = call asserted). Input
# reg0 mirrors output reg2; input reg1 mirrors reg3 (physical pin readback).
ZONE_ADDR = 0x20
ZONES = {3: "upstairs-fancoil", 5: "living-room-fancoil"}
ALLOWED_BITS = {z - 1 for z in ZONES}  # bits 2 and 4 only — hard guard

bus = smbus2.SMBus(1)


def _set(reg: int, bit: int, val: int) -> None:
    assert reg in (2, 3), f"refuse to write 0x20 reg {reg}"
    assert bit in ALLOWED_BITS, f"refuse to touch 0x20 bit {bit} (not zone 3/5)"
    cur = bus.read_byte_data(ZONE_ADDR, reg)
    new = cur | (1 << bit) if val else cur & ~(1 << bit)
    bus.write_byte_data(ZONE_ADDR, reg, new)  # read-modify-write: floors preserved


def failsafe(z: int, val: int) -> None:
    _set(2, z - 1, val)


def call(z: int, val: int) -> None:
    _set(3, z - 1, val)


def read_zone(z: int) -> tuple[int, int]:
    bit = z - 1
    f = (bus.read_byte_data(ZONE_ADDR, 0) >> bit) & 1  # input reg0 = failsafe pin
    s = (bus.read_byte_data(ZONE_ADDR, 1) >> bit) & 1  # input reg1 = scada pin
    return f, s


def zone_tag(f: int, s: int) -> str:
    if f == 1 and s == 1:
        return "SCADA-CALL(on)"
    if f == 1 and s == 0:
        return "SCADA-hold(off)"
    return "thermostat"


def print_zone(z: int) -> None:
    f, s = read_zone(z)
    print(f"    zone{z} {ZONES[z]:<20} failsafe={f} scada={s} -> {zone_tag(f, s)}")


def config_healthy() -> bool:
    return bus.read_byte_data(ZONE_ADDR, 6) == 0 and bus.read_byte_data(ZONE_ADDR, 7) == 0


# --- snapshot listener -----------------------------------------------------
WATCH = ("dist-pump-pwr", "dist-flow", "secondary-flow", "primary-flow")
readings: dict[str, list[tuple[float, float]]] = defaultdict(list)  # name -> [(mono,value)]


def _on_message(client, userdata, msg):
    if b"spruce" not in msg.topic.encode() and "spruce" not in msg.topic:
        return  # prod broker carries every house; keep only spruce
    try:
        p = json.loads(msg.payload).get("Payload", {})
        if p.get("TypeName") != "snapshot.spaceheat":
            return
        for x in p.get("LatestReadingList", []):
            name = x.get("ChannelName")
            if name in WATCH and x.get("Value") is not None:
                readings[name].append((time.monotonic(), float(x["Value"])))
    except Exception:
        pass


def start_listener() -> mqtt.Client:
    c = mqtt.Client()
    c.username_pw_set(settings.mqtt_username, settings.mqtt_password.get_secret_value())
    c.on_message = _on_message
    c.connect(settings.mqtt_host, settings.mqtt_port, keepalive=60)
    c.subscribe("gw/+/to/+/snapshot-spaceheat")
    c.loop_start()
    return c


def now_et() -> str:
    return datetime.now(ET).strftime("%H:%M:%S")


def latest(name: str) -> str:
    vals = readings.get(name, [])
    if not vals:
        return f"{name}: (no snapshot yet)"
    mono, v = vals[-1]
    age = int(time.monotonic() - mono)
    scale = 100.0 if "flow" in name else 1.0
    unit = "GPM" if "flow" in name else "W"
    return f"{name}: {v/scale:.2f} {unit} ({age}s ago)"


def observe(label: str, seconds: int) -> None:
    print(f"\n[{now_et()}] {label} — watching {seconds}s")
    end = time.monotonic() + seconds
    seen = {n: len(readings[n]) for n in WATCH}
    while time.monotonic() < end:
        time.sleep(2)
        for n in WATCH:
            if len(readings[n]) > seen[n]:
                for mono, v in readings[n][seen[n]:]:
                    scale = 100.0 if "flow" in n else 1.0
                    unit = "GPM" if "flow" in n else "W"
                    print(f"    [{now_et()}] {n} = {v/scale:.2f} {unit}")
                seen[n] = len(readings[n])


def summarize(name: str, since_mono: float) -> str:
    vals = [v for m, v in readings.get(name, []) if m >= since_mono]
    if not vals:
        return "no data"
    scale = 100.0 if "flow" in name else 1.0
    unit = "GPM" if "flow" in name else "W"
    return f"min {min(vals)/scale:.2f} / max {max(vals)/scale:.2f} {unit} (n={len(vals)})"


def main() -> None:
    print(f"=== spruce fan-coil -> dist-pump test  {datetime.now(ET):%Y-%m-%d %H:%M:%S %Z} ===")
    if not config_healthy():
        print("ABORT: 0x20 config registers nonzero (expander in reset / POR). "
              "Not fighting a reset — restart the summer hack to re-init, then retry.")
        return

    print("\n[baseline] zone pins before the test:")
    for z in (1, 2, 3, 4, 5):
        f, s = read_zone(z)
        print(f"    zone{z}: failsafe={f} scada={s} -> {zone_tag(f, s)}")

    client = start_listener()
    try:
        # Take control of BOTH fan-coils, hold both OFF.
        print(f"\n[{now_et()}] taking control of zones 3 & 5, both calls OFF")
        for z in (3, 5):
            failsafe(z, 1)
            call(z, 0)
        for z in (3, 5):
            print_zone(z)

        observe("PHASE A: both fan-coils OFF (baseline)", 60)
        base_mono = time.monotonic()

        # Force ONLY zone 5 on.
        print(f"\n[{now_et()}] forcing zone 5 (living-room fan-coil) call ON")
        call(5, 1)
        print_zone(3)
        print_zone(5)
        on_mono = time.monotonic()

        observe("PHASE B: zone 5 CALLING, zone 3 held off", 120)

        print("\n=== RESULT ===")
        print(f"  dist-pump-pwr  baseline(A): {summarize('dist-pump-pwr', base_mono - 60)}")
        print(f"  dist-pump-pwr  zone5-on(B): {summarize('dist-pump-pwr', on_mono)}")
        print(f"  dist-flow      baseline(A): {summarize('dist-flow', base_mono - 60)}")
        print(f"  dist-flow      zone5-on(B): {summarize('dist-flow', on_mono)}")
        print(f"  secondary-flow zone5-on(B): {summarize('secondary-flow', on_mono)}")
        print(f"  primary-flow   zone5-on(B): {summarize('primary-flow', on_mono)}")
    finally:
        print(f"\n[{now_et()}] RESTORE: releasing zones 3 & 5 back to their thermostats")
        for z in (3, 5):
            call(z, 0)
            failsafe(z, 0)
        for z in (3, 5):
            print_zone(z)
        client.loop_stop()
        client.disconnect()
        print("done. (summer hack restart is a separate step)")


if __name__ == "__main__":
    main()
