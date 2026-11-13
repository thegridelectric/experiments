#!/usr/bin/env python3
"""One-shot CT1-vs-CT2 check on spruce, one pump at a time, verdict in about a minute.

Runs ON THE DEV MACHINE in the experiments venv. Over ssh it stops the
summer hack and the scada, holds the iso valve open, and runs two phases
on the gw108's 0x21 relays: `sec` (secondary pump on, store pump off)
and `store` (store pump on, secondary pump off). In each phase it
captures P1 (CT2) then P0 (CT1) with the box's own capture.py (two
seconds each), copies the instances back, folds them, and prints a
verdict per phase. Relays and services are restored in a finally.

    uv run python peek.py                        # tag defaults to peek<HHMMSS> ET
    uv run python peek.py --run lift1            # a named run
    uv run python peek.py --dry-run              # print the plan; touch nothing
    uv run python peek.py --baseline             # nothing energized, services untouched; expect flat/flat

The site step this reads is George lifting CT1's two leads off the CT1
terminal pair (clamp stays on the pipe); with the leads still on it
reads which conductor each clamp is on.

The verdict, per phase, from the two waveform rms figures. The phase's
own channel is the one whose CT is meant to sit on the driven pump
(CT2/P1 for the secondary, CT1/P0 for the store); the other channel is
the mirror:
  own under 20 mV           INCONCLUSIVE, no signal from the driven pump
  other/own under 0.1       CLEAN: only the pump's own CT sees it
  other/own over 0.5        MIRRORED: the other channel carries the same
                            signal (shared conductor or tied inputs)
  in between                PARTIAL, look at the fold pngs

Hazard carried from 2026-08-23-gw108-relay-stress: energizing the iso
relay with no other 0x21 coil on resets the expander about one toggle in
three. The valve is expected open already (the summer posture); if it is
not, it is energized only after the secondary pump coil is on, and every
write is followed by the power-on-reset check (config registers 6 and 7
read nonzero after a reset). A reset aborts the run; the restore still
runs and the deployed scada re-initializes the chip at boot.

The box's instance copies are removed at the end; the laptop copies are
the evidence.
"""

import argparse
import subprocess
from datetime import datetime
import sys
import time
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from fold import fold, load  # noqa: E402

HOST = "spruce"
TA_ALIAS = "hw1.isone.me.versant.keene.spruce.ta"
BOX_DIR = "~/experiments/2026-09-07-gw108-ct-testing"
SCADA_PYTHON = "~/gridworks-scada/gw_spaceheat/venv/bin/python"
SERVICES = ("spruce-summer-hack.service", "gwspaceheat.service")
# gw108 expander 0x21 register 3 bits (the store_common.py table).
ISO_BIT = 2  # energized = valve OPEN
STORE_BIT = 4
SEC_BIT = 5
CHANNELS = ("P1", "P0")
FLAT_MV = 20.0
BAND = (59.5, 60.5)
BINS = 72


class Phase(NamedTuple):
    """One pump running alone: the phase name, the register-3 bit that
    drives it, and the channel whose CT is meant to be on that pump."""

    name: str
    bit: int
    own: str


PHASES = (Phase("sec", SEC_BIT, "P1"), Phase("store", STORE_BIT, "P0"))


class Reading(NamedTuple):
    """One channel's fold, the numbers the verdict is read from. No sema
    word yet; gw.adc.waveform.fold would carry these."""

    phase: str
    channel: str
    instance: Path
    bias_v: float
    waveform_rms_mv: float
    noise_rms_mv: float
    frequency_hz: float


def ssh(command: str) -> str:
    result = subprocess.run(["ssh", HOST, command], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ssh failed: {command}\n{result.stderr.strip()[-400:]}")
    return result.stdout.strip()


def box_python(script: str) -> str:
    return ssh(f"{SCADA_PYTHON} -c '{script}'")


def read_reg3() -> int:
    return int(box_python("import smbus2; print(smbus2.SMBus(1).read_byte_data(0x21, 3))"))


def bit(reg: int, b: int) -> int:
    return (reg >> b) & 1


def set_bit(b: int, value: int) -> None:
    """Read-modify-write one register-3 bit, read it back, then the
    power-on-reset check: config registers 6 and 7 read 0 unless the chip
    reset (0.3 s later, the way store_common.py confirms it)."""
    script = (
        "import smbus2, time; bus = smbus2.SMBus(1); r = bus.read_byte_data(0x21, 3); "
        f"bus.write_byte_data(0x21, 3, (r & ~(1 << {b})) | ({value} << {b})); "
        f"got = (bus.read_byte_data(0x21, 3) >> {b}) & 1; time.sleep(0.3); "
        "por = bus.read_byte_data(0x21, 6) != 0 or bus.read_byte_data(0x21, 7) != 0; "
        "print(got, int(por))"
    )
    got, por = box_python(script).split()
    if got != str(value):
        raise RuntimeError(f"bit {b} did not read back as {value} (got {got!r})")
    if por == "1":
        raise RuntimeError(f"0x21 RESET after writing bit {b} to {value}; aborting, restore follows")


def capture(channel: str, phase: str, run: str) -> str:
    out = ssh(
        f"cd {BOX_DIR} && {SCADA_PYTHON} capture.py --ta-alias {TA_ALIAS} --channel {channel} --seconds 2 --tag {phase}.{run}"
    )
    last = out.splitlines()[-1]
    print(f"  capture {channel}: {last.split(' -> ')[0]}")
    return Path(last.rsplit("-> ", 1)[-1]).name


def collect(names: list[str]) -> list[Path]:
    remote = " ".join(f"{HOST}:{BOX_DIR}/instances/{n}" for n in names)
    subprocess.run(f"scp -q {remote} {HERE / 'instances'}/", shell=True, check=True)
    ssh(" && ".join(f"rm {BOX_DIR}/instances/{n}" for n in names))
    return [HERE / "instances" / n for n in names]


def read(phase: str, channel: str, instance: Path) -> Reading:
    result = fold(load(instance), BAND, BINS)
    return Reading(
        phase, channel, instance, result.bias_v, result.waveform_rms_v * 1000, result.noise_rms_v * 1000, result.frequency_hz
    )


def verdict(phase: Phase, readings: dict[str, Reading]) -> str:
    own = readings[phase.own]
    other = readings[next(ch for ch in CHANNELS if ch != phase.own)]
    if own.waveform_rms_mv < FLAT_MV:
        return f"{phase.name}: INCONCLUSIVE, no signal on {own.channel} from the {phase.name} pump (did it run?)"
    ratio = other.waveform_rms_mv / own.waveform_rms_mv
    if ratio < 0.1:
        return f"{phase.name}: CLEAN ({other.channel}/{own.channel} = {ratio:.2f}), only {own.channel}'s CT sees the {phase.name} pump"
    if ratio > 0.5:
        return f"{phase.name}: MIRRORED ({other.channel}/{own.channel} = {ratio:.2f}), {other.channel} carries the same signal"
    return f"{phase.name}: PARTIAL ({other.channel}/{own.channel} = {ratio:.2f}), look at the fold pngs"


def run_phases(run: str, hold: int, dry_run: bool) -> dict[str, dict[str, str]]:
    """Both phases under one stop/restore. Returns instance names by phase
    and channel."""
    entry = read_reg3()
    print(f"at entry: reg3 0x{entry:02x}, iso {bit(entry, ISO_BIT)}, store {bit(entry, STORE_BIT)}, secondary {bit(entry, SEC_BIT)}")
    plan = [f"{p.name}: bit {p.bit} on, hold {hold}s, capture {CHANNELS}" for p in PHASES]
    print("plan: stop services; iso open (after the secondary coil if it is closed); " + "; ".join(plan) + "; restore")
    if dry_run:
        return {}
    names: dict[str, dict[str, str]] = {}
    ssh("sudo systemctl stop " + " ".join(SERVICES))
    print(f"stopped {', '.join(SERVICES)}")
    try:
        for phase in PHASES:
            set_bit(SEC_BIT, 1 if phase.bit == SEC_BIT else 0)
            if bit(entry, ISO_BIT) != 1 and phase is PHASES[0]:
                set_bit(ISO_BIT, 1)
                print("iso valve energized OPEN")
            set_bit(STORE_BIT, 1 if phase.bit == STORE_BIT else 0)
            print(f"{phase.name} pump ON alone, holding {hold}s")
            time.sleep(hold)
            names[phase.name] = {ch: capture(ch, phase.name, run) for ch in CHANNELS}
    finally:
        for b in (STORE_BIT, SEC_BIT, ISO_BIT):
            set_bit(b, bit(entry, b))
        ssh("sudo systemctl start " + " ".join(SERVICES))
        print(f"relays restored to reg3 0x{entry:02x}, started {', '.join(SERVICES)}")
    return names


def main() -> None:
    global CHANNELS, PHASES
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", default=f"peek{datetime.now():%H%M%S}", help="run tag, lowercase alnum; names the instances p<n>.<phase>.<run> (default: peek<HHMMSS>)")
    parser.add_argument("--hold", type=int, default=15, help="seconds after a pump comes on alone before capturing")
    parser.add_argument("--baseline", action="store_true", help="energize nothing, services untouched: one 'base' phase (a flat/flat pipeline check)")
    parser.add_argument("--dry-run", action="store_true", help="print the entry bits and the plan; touch nothing")
    parser.add_argument("--channels", default=",".join(CHANNELS), help="two ADC inputs, the secondary pump's own CT first, the store pump's second (default P1,P0; P3,P0 once CT2 moves to the fourth connector)")
    args = parser.parse_args()
    CHANNELS = tuple(args.channels.upper().split(","))
    if len(CHANNELS) != 2 or not all(ch in ("P0", "P1", "P2", "P3") for ch in CHANNELS):
        parser.error("--channels takes two of P0..P3, e.g. P3,P0")
    PHASES = (Phase("sec", SEC_BIT, CHANNELS[0]), Phase("store", STORE_BIT, CHANNELS[1]))
    t0 = time.monotonic()
    print(f"run {args.run}")

    if args.baseline:
        names = {"base": {ch: capture(ch, "base", args.run) for ch in CHANNELS}}
    else:
        names = run_phases(args.run, args.hold, args.dry_run)
    if not names:
        return

    readings: dict[str, dict[str, Reading]] = {}
    for phase_name, by_channel in names.items():
        paths = collect([by_channel[ch] for ch in CHANNELS])
        readings[phase_name] = {ch: read(phase_name, ch, p) for ch, p in zip(CHANNELS, paths)}
    print()
    print("| phase | channel | bias V | waveform rms mV | noise rms mV | fold Hz |")
    print("| --- | --- | --- | --- | --- | --- |")
    for by_channel in readings.values():
        for r in by_channel.values():
            print(f"| {r.phase} | {r.channel} | {r.bias_v:.3f} | {r.waveform_rms_mv:.1f} | {r.noise_rms_mv:.1f} | {r.frequency_hz:.3f} |")
    print()
    for phase in PHASES:
        if phase.name in readings:
            print(f"VERDICT {verdict(phase, readings[phase.name])}")
    if "base" in readings:
        loud = [r.channel for r in readings["base"].values() if r.waveform_rms_mv >= FLAT_MV]
        print("VERDICT base: " + (f"signal on {loud} with nothing energized" if loud else "flat/flat, pipeline ok"))
    instances = [r.instance.name for by_channel in readings.values() for r in by_channel.values()]
    print(f"instances: {', '.join(instances)}  ({time.monotonic() - t0:.0f} s)")


if __name__ == "__main__":
    main()
