#!/usr/bin/env python3
"""Write a synthetic gw.adc.waveform instance for the fold's dry run.

A 60.02 Hz sinusoid of 100 mV rms around the 1.65 V mid-rail, 0.5 mV rms
noise, quantised to ADS1115 codes at 4096 mV full scale, sampled for two
seconds at roughly 600 conversions per second with jittered timing (the
single-shot path's shape). The fold must recover the frequency, the bias
and the amplitude from it before the harness goes near the chip. Not a
measurement: the alias says synthetic.

    uv run python synth.py
    uv run python fold.py instances/d1.bench.synthetic.ta-p0.synth.60hz-gw.adc.waveform-000.json
"""

import json
import sys
import uuid
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
for candidate in (HERE.parent, HERE.parent.parent):
    if (candidate / "src" / "gwexp").is_dir():
        sys.path.insert(0, str(candidate / "src"))
        sys.path.insert(0, str(candidate))
        break

from gwexp.sema.enums import I2cAdcChannel, I2cAdcType  # noqa: E402
from gwexp.sema.types import GwAdcWaveform  # noqa: E402
from naming import validate_lrd  # noqa: E402

TA_ALIAS = validate_lrd("d1.bench.synthetic.ta")
CONDITION = validate_lrd("p0.synth.60hz")
FREQUENCY_HZ = 60.02
RMS_MV = 100.0
BIAS_V = 1.65
NOISE_RMS_MV = 0.5
FULL_SCALE_MV = 4096
SECONDS = 2.0
MEAN_INTERVAL_US = 1650
JITTER_US = 300
START_UNIX_MS = 1788784500000


def main() -> None:
    rng = np.random.default_rng(7)
    intervals = rng.integers(MEAN_INTERVAL_US - JITTER_US, MEAN_INTERVAL_US + JITTER_US, size=int(SECONDS * 1e6 / MEAN_INTERVAL_US))
    offsets_us = np.concatenate([[0], np.cumsum(intervals)])
    t = offsets_us / 1e6
    v = BIAS_V + RMS_MV * np.sqrt(2) / 1000 * np.sin(2 * np.pi * FREQUENCY_HZ * t + 0.4)
    v += rng.normal(0, NOISE_RMS_MV / 1000, size=t.size)
    codes = np.clip(np.round(v * 1000 / FULL_SCALE_MV * 32768), -32768, 32767).astype(int)
    waveform = GwAdcWaveform(
        ta_alias=TA_ALIAS,
        message_id=str(uuid.uuid4()),
        message_created_ms=START_UNIX_MS + int(SECONDS * 1000) + 100,
        adc_type=I2cAdcType.Ads1115,
        i2c_address=72,
        adc_channel=I2cAdcChannel.P0,
        full_scale_millivolts=FULL_SCALE_MV,
        data_rate_hz=860,
        start_unix_ms=START_UNIX_MS,
        sample_offsets_us=[int(o) for o in offsets_us],
        codes=[int(c) for c in codes],
    )
    out = HERE / "instances" / f"{TA_ALIAS}-{CONDITION}-gw.adc.waveform-000.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(waveform.to_dict(), indent=2) + "\n")
    print(f"{len(codes)} codes at {FREQUENCY_HZ} Hz, {RMS_MV} mV rms -> {out}")


if __name__ == "__main__":
    main()
