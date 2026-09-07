#!/usr/bin/env python3
"""Capture one burst of ADS1115 conversions on the gw108 and write it as a
gw.adc.waveform instance.

Runs ON THE PI from the box's ~/experiments clone with the scada venv's
python (smbus2 and pydantic are there). Bus 1, the CT ADC at 0x48, hard
coded: this is bench code, not the scada. Two sampling modes, because the
pi cannot see the chip's conversion-ready signal:

  single      one conversion per request: write the config with OS set,
              poll the config register until the chip reports done, read
              the code. Every code is exactly one conversion with its own
              host timestamp; the effective rate is what the bus allows.
  continuous  the chip free-runs at the data rate; the host polls the
              conversion register as fast as it can and keeps a code when
              it differs from the last one kept. Faster, but two equal
              consecutive conversions collapse into one, and a code read
              mid-slot carries the poll time, not the conversion time.

Which mode gives clean conversions at what rate is the bench question.

    venv/bin/python capture.py --mode single --seconds 2 --tag r1
    venv/bin/python capture.py --mode continuous --seconds 2 --tag r1

The instance lands in instances/ under the on-disk grammar
<ta>-<channel>.<mode>.<tag>-gw.adc.waveform-000.json; the last line printed
is the verdict (count, effective rate, largest gap).
"""

import argparse
import json
import sys
import time
import uuid
from itertools import pairwise
from pathlib import Path
from typing import NamedTuple

from smbus2 import SMBus

HERE = Path(__file__).resolve().parent
for candidate in (HERE.parent, HERE.parent.parent):
    if (candidate / "src" / "gwexp").is_dir():
        sys.path.insert(0, str(candidate / "src"))
        sys.path.insert(0, str(candidate))
        break

from gwexp.sema.enums import I2cAdcChannel, I2cAdcType  # noqa: E402
from gwexp.sema.types import GwAdcWaveform  # noqa: E402
from naming import validate_lrd  # noqa: E402

I2C_BUS = 1
ADS_ADDRESS = 0x48
REG_CONVERSION = 0x00
REG_CONFIG = 0x01

# ADS1115 config register fields (datasheet table 8).
MUX_SINGLE_ENDED = {
    I2cAdcChannel.P0: 0b100,
    I2cAdcChannel.P1: 0b101,
    I2cAdcChannel.P2: 0b110,
    I2cAdcChannel.P3: 0b111,
}
PGA_BY_FULL_SCALE_MV = {6144: 0b000, 4096: 0b001, 2048: 0b010, 1024: 0b011, 512: 0b100, 256: 0b101}
DR_BY_HZ = {8: 0b000, 16: 0b001, 32: 0b010, 64: 0b011, 128: 0b100, 250: 0b101, 475: 0b110, 860: 0b111}
COMPARATOR_DISABLED = 0b11
OS_BIT = 1 << 15
MODE_SINGLE_SHOT = 1 << 8


class Sample(NamedTuple):
    """One kept conversion: host time in perf_counter nanoseconds and the raw code."""

    host_ns: int
    code: int


def config_word(channel: I2cAdcChannel, full_scale_mv: int, rate_hz: int, single_shot: bool) -> int:
    word = (MUX_SINGLE_ENDED[channel] << 12) | (PGA_BY_FULL_SCALE_MV[full_scale_mv] << 9)
    word |= DR_BY_HZ[rate_hz] << 5
    word |= COMPARATOR_DISABLED
    if single_shot:
        word |= MODE_SINGLE_SHOT
    return word


def write_register(bus: SMBus, register: int, word: int) -> None:
    bus.write_i2c_block_data(ADS_ADDRESS, register, [(word >> 8) & 0xFF, word & 0xFF])


def read_register(bus: SMBus, register: int) -> int:
    hi, lo = bus.read_i2c_block_data(ADS_ADDRESS, register, 2)
    return (hi << 8) | lo


def read_code(bus: SMBus) -> int:
    raw = read_register(bus, REG_CONVERSION)
    return raw - 65536 if raw & 0x8000 else raw


def capture_single(bus: SMBus, base: int, seconds: float) -> list[Sample]:
    """One conversion per request; the OS bit reports completion."""
    samples: list[Sample] = []
    deadline = time.perf_counter_ns() + int(seconds * 1e9)
    while time.perf_counter_ns() < deadline:
        write_register(bus, REG_CONFIG, base | OS_BIT)
        while not read_register(bus, REG_CONFIG) & OS_BIT:
            pass
        samples.append(Sample(time.perf_counter_ns(), read_code(bus)))
    return samples


def capture_continuous(bus: SMBus, base: int, seconds: float) -> list[Sample]:
    """Free-running chip; keep a code whenever it differs from the last kept."""
    write_register(bus, REG_CONFIG, base)
    time.sleep(0.01)
    samples: list[Sample] = []
    last: int | None = None
    deadline = time.perf_counter_ns() + int(seconds * 1e9)
    while time.perf_counter_ns() < deadline:
        code = read_code(bus)
        if code != last:
            samples.append(Sample(time.perf_counter_ns(), code))
            last = code
    write_register(bus, REG_CONFIG, base | MODE_SINGLE_SHOT)
    return samples


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["single", "continuous"], required=True)
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--channel", type=I2cAdcChannel, choices=list(I2cAdcChannel), default=I2cAdcChannel.P0)
    parser.add_argument("--full-scale-mv", type=int, choices=sorted(PGA_BY_FULL_SCALE_MV), default=4096)
    parser.add_argument("--rate-hz", type=int, choices=sorted(DR_BY_HZ), default=860)
    parser.add_argument("--ta-alias", type=validate_lrd, default="d1.bench.honeysuckle.ta")
    parser.add_argument("--tag", required=True, help="run tag for the filename condition, e.g. r1")
    parser.add_argument("--out", type=Path, default=HERE / "instances")
    args = parser.parse_args()

    condition = validate_lrd(f"{args.channel.value.lower()}.{args.mode}.{args.tag}")
    base = config_word(args.channel, args.full_scale_mv, args.rate_hz, single_shot=args.mode == "single")
    with SMBus(I2C_BUS) as bus:
        start_unix_ms = int(time.time() * 1000)
        if args.mode == "single":
            samples = capture_single(bus, base, args.seconds)
        else:
            samples = capture_continuous(bus, base, args.seconds)
    if not samples:
        raise SystemExit("ABORT: no conversions read")

    first_ns = samples[0].host_ns
    waveform = GwAdcWaveform(
        ta_alias=args.ta_alias,
        message_id=str(uuid.uuid4()),
        message_created_ms=int(time.time() * 1000),
        adc_type=I2cAdcType.Ads1115,
        i2c_address=ADS_ADDRESS,
        adc_channel=args.channel,
        full_scale_millivolts=args.full_scale_mv,
        data_rate_hz=args.rate_hz,
        start_unix_ms=start_unix_ms,
        sample_offsets_us=[(s.host_ns - first_ns) // 1000 for s in samples],
        codes=[s.code for s in samples],
    )
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{args.ta_alias}-{condition}-gw.adc.waveform-000.json"
    path.write_text(json.dumps(waveform.to_dict(), indent=2) + "\n")

    offsets = waveform.sample_offsets_us
    span_s = offsets[-1] / 1e6 if len(offsets) > 1 else 0.0
    gaps = [b - a for a, b in pairwise(offsets)]
    rate = (len(offsets) - 1) / span_s if span_s else 0.0
    print(f"PASS {len(offsets)} conversions over {span_s:.3f} s, {rate:.0f}/s effective, largest gap {max(gaps) if gaps else 0} us -> {path}")


if __name__ == "__main__":
    main()
