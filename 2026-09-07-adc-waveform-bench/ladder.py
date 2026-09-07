#!/usr/bin/env python3
"""Step the secondary pump's 0-10 V level and capture a CT2 waveform at each.

Runs ON THE PI from ~/experiments with the starter-scripts venv (it drives
the DAC and the pump relay the way spruce_summer_hack.py does, with the same
libraries) and shells out to capture.py under the scada venv for each burst.
The summer hack MUST be stopped first (it re-asserts the DAC every 300 s and
its exit failsafe drops the pump relay); this driver refuses to run while
the service is active.

Window: pump relay ON (0x21 reg 3 bit 5, read-modify-write like the hack),
then for each level: DAC code = volts x 400 on Dac2 channel C behind mux
channel 2, hold, record the freshest secondary-flow from the scada snapshot,
capture P1. Restore: DAC back to the hack's 7.55 V (code 3020) and the pump
relay to the bit it had at entry. The relay restore leaves the pump where the
hack's failsafe put it (off); restarting the hack re-asserts posture.

    ~/starter-scripts/venv/bin/python ladder.py --run ladder1
    ~/starter-scripts/venv/bin/python ladder.py --run ladder1 --dry-run   # no hardware, no broker

Instance tags are p1.dac<volts x10, 3 digits>.<run>; the level table lands
in <run>-levels.json beside this file (no sema word yet: gw.adc.waveform has
no field for the drive level or the flow, the CT component vocabulary spoke
retires this sidecar).
"""

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, "/home/pi/starter-scripts")

TA_ALIAS = "hw1.isone.me.versant.keene.spruce.ta"
SCADA_PYTHON = Path("/home/pi/gridworks-scada/gw_spaceheat/venv/bin/python")
HACK_SERVICE = "spruce-summer-hack.service"
LEVELS_V10 = (30, 45, 60, 75, 90, 100)  # volts x 10; 75 ~ the hack's 7.55 V
RESTORE_CODE = 3020  # the hack's 65 % = 7.55 V, RAW_PER_VOLT 400
RAW_PER_VOLT = 400
PUMP_ADDR, PUMP_REG, PUMP_BIT = 0x21, 3, 5
MUX_CHANNEL = 2
FLOW_CHANNEL = "secondary-flow"
FLOW_FRESH_S = 120


class Level(NamedTuple):
    """One rung of the ladder: the drive level, what the pico said the flow
    was (GpmTimes100, None if no fresh reading landed), and the burst."""

    volts_x10: int
    dac_code: int
    flow_gpm_x100: int | None
    flow_age_s: int | None
    instance: str


class FlowWatch:
    """Keeps the latest secondary-flow reading from the scada's snapshots."""

    def __init__(self) -> None:
        self.value: int | None = None
        self.read_unix_s: float | None = None

    def start(self) -> None:
        import paho.mqtt.client as mqtt
        from starter_settings import settings

        def on_message(client, userdata, msg):
            try:
                payload = json.loads(msg.payload).get("Payload", {})
            except Exception:
                return
            for reading in payload.get("LatestReadingList", []):
                if reading.get("ChannelName") == FLOW_CHANNEL:
                    self.value = reading["Value"]
                    self.read_unix_s = reading["ScadaReadTimeUnixMs"] / 1000

        client = mqtt.Client()
        client.username_pw_set(settings.mqtt_username, settings.mqtt_password.get_secret_value())
        client.on_message = on_message
        client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=60)
        client.subscribe("gw/+/to/+/snapshot-spaceheat")
        threading.Thread(target=client.loop_forever, daemon=True).start()

    def fresh(self) -> tuple[int | None, int | None]:
        if self.read_unix_s is None:
            return None, None
        age = int(time.time() - self.read_unix_s)
        return (self.value, age) if age <= FLOW_FRESH_S else (None, age)


def hack_active() -> bool:
    return subprocess.run(["systemctl", "is-active", "--quiet", HACK_SERVICE]).returncode == 0


def capture(volts_x10: int, run: str) -> str:
    tag = f"dac{volts_x10:03d}.{run}"
    result = subprocess.run(
        [str(SCADA_PYTHON), str(HERE / "capture.py"), "--ta-alias", TA_ALIAS, "--channel", "P1", "--seconds", "2", "--tag", tag],
        capture_output=True,
        text=True,
    )
    last = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else result.stderr.strip()[-200:]
    print(f"  capture: {last}")
    if result.returncode != 0:
        raise RuntimeError(f"capture failed at {volts_x10}: {last}")
    return last.rsplit("-> ", 1)[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", required=True, help="run name, e.g. ladder1; tags the instances and the levels file")
    parser.add_argument("--hold", type=int, default=60, help="seconds at each level before the capture")
    parser.add_argument("--levels", default=",".join(str(v) for v in LEVELS_V10), help="comma list of volts x 10")
    parser.add_argument("--dry-run", action="store_true", help="print the plan; touch nothing")
    args = parser.parse_args()
    levels = [int(v) for v in args.levels.split(",")]
    plan = [(v, round(v / 10 * RAW_PER_VOLT)) for v in levels]
    print(f"plan {args.run}: {plan}, hold {args.hold}s, restore code {RESTORE_CODE}")
    if args.dry_run:
        return
    if hack_active():
        raise SystemExit(f"ABORT: {HACK_SERVICE} is active; stop it first")

    import adafruit_mcp4728
    import adafruit_tca9548a
    import board
    import smbus2

    bus = smbus2.SMBus(1)
    dac = adafruit_mcp4728.MCP4728(adafruit_tca9548a.TCA9548A(board.I2C())[MUX_CHANNEL])
    dac.channel_c.vref = adafruit_mcp4728.Vref.INTERNAL
    dac.channel_c.gain = 1
    entry_reg = bus.read_byte_data(PUMP_ADDR, PUMP_REG)
    entry_bit = (entry_reg >> PUMP_BIT) & 1
    print(f"pump relay bit at entry: {entry_bit}")
    flow = FlowWatch()
    flow.start()
    rows: list[Level] = []
    try:
        bus.write_byte_data(PUMP_ADDR, PUMP_REG, entry_reg | (1 << PUMP_BIT))
        if not (bus.read_byte_data(PUMP_ADDR, PUMP_REG) >> PUMP_BIT) & 1:
            raise RuntimeError("pump relay bit did not read back as 1")
        print("pump relay ON")
        for volts_x10, code in plan:
            dac.channel_c.raw_value = code
            print(f"level {volts_x10 / 10:.1f} V (code {code}), holding {args.hold}s")
            time.sleep(args.hold)
            value, age = flow.fresh()
            print(f"  {FLOW_CHANNEL}: {value} age {age}s")
            instance = capture(volts_x10, args.run)
            rows.append(Level(volts_x10, code, value, age, Path(instance).name))
    finally:
        dac.channel_c.raw_value = RESTORE_CODE
        current = bus.read_byte_data(PUMP_ADDR, PUMP_REG)
        bus.write_byte_data(PUMP_ADDR, PUMP_REG, (current & ~(1 << PUMP_BIT)) | (entry_bit << PUMP_BIT))
        print(f"restored: DAC code {RESTORE_CODE}, pump relay bit {entry_bit}")
    out = HERE / f"{args.run}-levels.json"
    out.write_text(json.dumps([row._asdict() for row in rows], indent=2) + "\n")
    print(f"PASS {len(rows)} levels -> {out}")


if __name__ == "__main__":
    main()
