#!/usr/bin/env python3
"""One-shot CT1-vs-CT2 check on spruce with a verdict in under a minute.

Runs ON THE DEV MACHINE in the experiments venv. Over ssh it reads the
secondary pump relay bit, captures P1 (CT2) then P0 (CT1) with the box's
own capture.py (two seconds each), copies the instances back, folds both,
and prints one verdict line. The site step this reads is George lifting
CT1's two leads off the CT1 terminal pair; the clamp stays on the pipe.

    uv run python peek.py                        # tag defaults to peek<HHMMSS> ET
    uv run python peek.py --run lift1            # a named run
    uv run python peek.py --baseline             # pump off, just prove the pipeline (expect INCONCLUSIVE)

If the secondary pump relay is off, the script energizes it itself the
way jumper.py does: both services stopped, expander 0x21 register 3 bit 5
set, held 15 s, restored in a finally, services started again. With the
pump already running nothing on the box changes but the capture.

The verdict, from the two waveform rms figures:
  P1 under 20 mV            INCONCLUSIVE, no pump signal on CT2 (pump off?)
  P0/P1 under 0.1           P0 FLAT: the signal came in on CT1's own leads;
                            both clamps are on one conductor
  P0/P1 over 0.5            P0 STILL MIRRORS P1: the inputs are tied on the
                            gw108 (terminal strip or board)
  in between                PARTIAL, look at the fold pngs

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
BOX_DIR = "~/experiments/2026-09-07-adc-waveform-bench"
SCADA_PYTHON = "~/gridworks-scada/gw_spaceheat/venv/bin/python"
SERVICES = ("spruce-summer-hack.service", "gwspaceheat.service")
PUMP_BIT = 5
CHANNELS = ("P1", "P0")
FLAT_MV = 20.0
BAND = (59.5, 60.5)
BINS = 72

READ_BIT = f"{SCADA_PYTHON} -c 'import smbus2; print((smbus2.SMBus(1).read_byte_data(0x21, 3) >> {PUMP_BIT}) & 1)'"


class Reading(NamedTuple):
    """One channel's fold, the numbers the verdict is read from. No sema
    word yet; gw.adc.waveform.fold would carry these."""

    channel: str
    instance: Path
    bias_v: float
    waveform_rms_mv: float
    noise_rms_mv: float
    frequency_hz: float


def ssh(command: str, check: bool = True) -> str:
    result = subprocess.run(["ssh", HOST, command], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"ssh failed: {command}\n{result.stderr.strip()[-400:]}")
    return result.stdout.strip()


def set_pump_bit(value: int) -> None:
    script = (
        "import smbus2; b = smbus2.SMBus(1); r = b.read_byte_data(0x21, 3); "
        f"b.write_byte_data(0x21, 3, (r & ~(1 << {PUMP_BIT})) | ({value} << {PUMP_BIT})); "
        f"print((b.read_byte_data(0x21, 3) >> {PUMP_BIT}) & 1)"
    )
    got = ssh(f"{SCADA_PYTHON} -c '{script}'")
    if got != str(value):
        raise RuntimeError(f"pump bit did not read back as {value} (got {got!r})")


def capture(channel: str, run: str) -> str:
    out = ssh(
        f"cd {BOX_DIR} && {SCADA_PYTHON} capture.py --ta-alias {TA_ALIAS} --channel {channel} --seconds 2 --tag {run}"
    )
    last = out.splitlines()[-1]
    print(f"  capture {channel}: {last.split(' -> ')[0]}")
    return Path(last.rsplit("-> ", 1)[-1]).name


def collect(names: list[str]) -> list[Path]:
    remote = " ".join(f"{HOST}:{BOX_DIR}/instances/{n}" for n in names)
    subprocess.run(f"scp -q {remote} {HERE / 'instances'}/", shell=True, check=True)
    ssh(" && ".join(f"rm {BOX_DIR}/instances/{n}" for n in names))
    return [HERE / "instances" / n for n in names]


def read(channel: str, instance: Path) -> Reading:
    result = fold(load(instance), BAND, BINS)
    return Reading(channel, instance, result.bias_v, result.waveform_rms_v * 1000, result.noise_rms_v * 1000, result.frequency_hz)


def verdict(p1: Reading, p0: Reading) -> str:
    if p1.waveform_rms_mv < FLAT_MV:
        return "INCONCLUSIVE: no pump signal on CT2 (P1); is the secondary pump running?"
    ratio = p0.waveform_rms_mv / p1.waveform_rms_mv
    if ratio < 0.1:
        return f"P0 FLAT (P0/P1 = {ratio:.2f}): the signal came in on CT1's own leads; both clamps are on one conductor"
    if ratio > 0.5:
        return f"P0 STILL MIRRORS P1 (P0/P1 = {ratio:.2f}): the inputs are tied on the gw108, terminal strip or board"
    return f"PARTIAL (P0/P1 = {ratio:.2f}): look at the fold pngs"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", default=f"peek{datetime.now():%H%M%S}", help="run tag, lowercase alnum; names the instances p1.<run>, p0.<run> (default: peek<HHMMSS>)")
    parser.add_argument("--hold", type=int, default=15, help="seconds after energizing the pump before capturing")
    parser.add_argument("--baseline", action="store_true", help="pump off: capture anyway instead of energizing it (a flat/flat pipeline check)")
    args = parser.parse_args()
    t0 = time.monotonic()

    print(f"run {args.run}")
    pump = ssh(READ_BIT)
    print(f"secondary pump relay bit: {pump}")

    names: list[str] = []
    if pump == "0" and not args.baseline:
        ssh("sudo systemctl stop " + " ".join(SERVICES))
        print(f"stopped {', '.join(SERVICES)}")
        try:
            set_pump_bit(1)
            print(f"secondary pump ON, holding {args.hold}s")
            time.sleep(args.hold)
            names = [capture(ch, args.run) for ch in CHANNELS]
        finally:
            set_pump_bit(0)
            ssh("sudo systemctl start " + " ".join(SERVICES))
            print(f"pump bit restored to 0, started {', '.join(SERVICES)}")
    else:
        names = [capture(ch, args.run) for ch in CHANNELS]

    paths = collect(names)
    readings = [read(ch, p) for ch, p in zip(CHANNELS, paths)]
    print()
    print("| channel | bias V | waveform rms mV | noise rms mV | fold Hz |")
    print("| --- | --- | --- | --- | --- |")
    for r in readings:
        print(f"| {r.channel} | {r.bias_v:.3f} | {r.waveform_rms_mv:.1f} | {r.noise_rms_mv:.1f} | {r.frequency_hz:.3f} |")
    p1, p0 = readings
    print()
    print(f"VERDICT: {verdict(p1, p0)}")
    print(f"instances: {', '.join(p.name for p in paths)}  ({time.monotonic() - t0:.0f} s)")


if __name__ == "__main__":
    main()
