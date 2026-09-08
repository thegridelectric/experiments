#!/usr/bin/env python3
"""Burden-jumper check on CT1 (store pump): capture P0 and P1 with the
store pump off, then on, so the burdened CT1 can be read against the
unburdened mirror from `pump1` and against CT2 on the secondary pump.

Runs ON THE PI from the box's ~/experiments clone with the starter-scripts
venv (smbus2 is there); calls capture.py under the scada venv. Bus 1,
expander 0x21 register 3: store pump bit 4, secondary pump bit 5, the
positions spruce_summer_hack.py and ladder.py use.

The summer hack MUST be stopped first and no scada may be running (the
window scada holds the expander and would fight the bits); this driver
refuses to run while either is up. The DAC is left where it is.

Window: secondary pump relay ON (read-modify-write like the hack), then
phase `storeoff`: capture P0 then P1; store pump bit ON, hold; phase
`storeon`: capture P0 then P1. Restore: both bits back to what they were
at entry. Phases and instance names go to <run>-phases.json beside this.

    ~/starter-scripts/venv/bin/python jumper.py --run jump1
"""

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).resolve().parent
TA_ALIAS = "hw1.isone.me.versant.keene.spruce.ta"
SCADA_PYTHON = Path("/home/pi/gridworks-scada/gw_spaceheat/venv/bin/python")
HACK_SERVICE = "spruce-summer-hack.service"
ADDR, REG = 0x21, 3
STORE_BIT = 4
PUMP_BIT = 5
CHANNELS = ("P0", "P1")


class Phase(NamedTuple):
    """One phase of the window: its name, the store pump bit during it,
    and the instance written for each channel."""

    phase: str
    store_bit: int
    instances: dict[str, str]


def hack_active() -> bool:
    return subprocess.run(["systemctl", "is-active", "--quiet", HACK_SERVICE]).returncode == 0


def scada_running() -> bool:
    return subprocess.run(["pgrep", "-f", "[w]indow_boot.py|gwspaceheat|gw_spaceheat/gws"], capture_output=True).returncode == 0


def capture(channel: str, phase: str, run: str) -> str:
    tag = f"{phase}.{run}"
    result = subprocess.run(
        [str(SCADA_PYTHON), str(HERE / "capture.py"), "--ta-alias", TA_ALIAS, "--channel", channel, "--seconds", "2", "--tag", tag],
        capture_output=True,
        text=True,
    )
    last = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else result.stderr.strip()[-200:]
    print(f"  capture {channel}: {last}")
    if result.returncode != 0:
        raise RuntimeError(f"capture failed on {channel} in {phase}: {last}")
    return Path(last.rsplit("-> ", 1)[-1]).name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", required=True, help="run name, e.g. jump1; tags the instances and the phases file")
    parser.add_argument("--hold", type=int, default=20, help="seconds after the store pump bit changes before capturing")
    parser.add_argument("--dry-run", action="store_true", help="print the plan; touch nothing")
    args = parser.parse_args()
    print(f"plan {args.run}: pump bit {PUMP_BIT} on; storeoff {CHANNELS}; store bit {STORE_BIT} on, hold {args.hold}s; storeon {CHANNELS}; restore both bits")
    if args.dry_run:
        return
    if hack_active():
        raise SystemExit(f"ABORT: {HACK_SERVICE} is active; stop it first")
    if scada_running():
        raise SystemExit("ABORT: a scada is running; stop it first")

    import smbus2

    bus = smbus2.SMBus(1)
    entry_reg = bus.read_byte_data(ADDR, REG)
    entry_pump = (entry_reg >> PUMP_BIT) & 1
    entry_store = (entry_reg >> STORE_BIT) & 1
    print(f"at entry: pump bit {entry_pump}, store bit {entry_store}, reg 0x{entry_reg:02x}")
    phases: list[Phase] = []

    def set_bit(bit: int, value: int) -> None:
        current = bus.read_byte_data(ADDR, REG)
        bus.write_byte_data(ADDR, REG, (current & ~(1 << bit)) | (value << bit))
        if (bus.read_byte_data(ADDR, REG) >> bit) & 1 != value:
            raise RuntimeError(f"bit {bit} did not read back as {value}")

    try:
        set_bit(PUMP_BIT, 1)
        print("secondary pump relay ON")
        time.sleep(args.hold)
        print("phase storeoff")
        phases.append(Phase("storeoff", 0, {ch: capture(ch, "storeoff", args.run) for ch in CHANNELS}))
        set_bit(STORE_BIT, 1)
        print(f"store pump relay ON, holding {args.hold}s")
        time.sleep(args.hold)
        print("phase storeon")
        phases.append(Phase("storeon", 1, {ch: capture(ch, "storeon", args.run) for ch in CHANNELS}))
    finally:
        set_bit(STORE_BIT, entry_store)
        set_bit(PUMP_BIT, entry_pump)
        print(f"restored: store bit {entry_store}, pump bit {entry_pump}")
    out = HERE / f"{args.run}-phases.json"
    out.write_text(json.dumps([p._asdict() for p in phases], indent=2) + "\n")
    print(f"PASS {len(phases)} phases -> {out}")


if __name__ == "__main__":
    main()
