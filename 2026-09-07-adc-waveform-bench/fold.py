#!/usr/bin/env python3
"""Fold a gw.adc.waveform instance onto one mains period and plot the composite.

Laptop side. The samples are irregular in time (host-timed offsets), so the
frequency is fitted with a periodogram over a narrow band around 60 Hz
rather than an FFT, then every sample is placed by phase on one period and
the composite is the per-bin mean. A burst of one to two seconds at a few
hundred samples per second gives hundreds of points per cycle.

    uv run python fold.py instances/<instance>.json [--band 59.5 60.5] [--bins 72] [--show | --no-plot]

Prints the fitted frequency, the bias, the fundamental's amplitude, the
composite waveform's rms and the noise about the composite; writes <instance>-fold.png beside the instance (generated,
gitignored). A ladder instance (listed in a <run>-levels.json beside this
script) gets its pump drive level and flow printed and in the plot title. --show also opens the interactive matplotlib window (zoom,
pan, cursor readout) and blocks until it is closed. On a channel with no
CT the fit is a noise fit: the amplitude reported is the largest spectral
line in the band, not a signal.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np

HERE = Path(__file__).resolve().parent
for candidate in (HERE.parent, HERE.parent.parent):
    if (candidate / "src" / "gwexp").is_dir():
        sys.path.insert(0, str(candidate / "src"))
        break

from gwexp.sema.types import GwAdcWaveform  # noqa: E402
from ladder import Level  # noqa: E402

ADS_CODES_PER_FULL_SCALE = 32768


class Fold(NamedTuple):
    """The fold of one burst. No sema word yet; gw.adc.waveform.fold would carry
    these facts when a scada emits them.

    frequency_hz: the periodogram peak in the band.
    bias_v: the mean of the burst (the 1.65 V mid-rail on a CT channel).
    amplitude_v: peak amplitude of the fundamental sinusoid at frequency_hz.
    waveform_rms_v: rms of the composite about the bias, the waveform's
        true rms including harmonics (a pump's current is not a sine).
    noise_rms_v: rms of the samples about the composite, what is not
        periodic at frequency_hz.
    phase: each sample's position on one period, in [0, 1).
    bin_centers, composite_v: the per-bin mean waveform.
    """

    frequency_hz: float
    bias_v: float
    amplitude_v: float
    waveform_rms_v: float
    noise_rms_v: float
    phase: np.ndarray
    bin_centers: np.ndarray
    composite_v: np.ndarray


def load(path: Path) -> GwAdcWaveform:
    return GwAdcWaveform.from_dict(json.loads(path.read_text()))


def level_for(instance: Path) -> Level | None:
    """The ladder rung that captured this instance, from any <run>-levels.json
    beside this script; None for a burst that was not a ladder step."""
    for levels in sorted(HERE.glob("*-levels.json")):
        for entry in json.loads(levels.read_text()):
            level = Level(**entry)
            if level.instance == instance.name:
                return level
    return None


def describe(level: Level | None) -> str:
    if level is None:
        return ""
    flow = "no fresh flow" if level.flow_gpm_x100 is None else f"secondary-flow {level.flow_gpm_x100 / 100:.2f} gpm"
    return f"pump drive {level.volts_x10 / 10:.1f} V (DAC {level.dac_code}), {flow}"


def volts(waveform: GwAdcWaveform) -> np.ndarray:
    scale = waveform.full_scale_millivolts / 1000 / ADS_CODES_PER_FULL_SCALE
    return np.asarray(waveform.codes, dtype=float) * scale


def seconds(waveform: GwAdcWaveform) -> np.ndarray:
    return np.asarray(waveform.sample_offsets_us, dtype=float) / 1e6


def fold(waveform: GwAdcWaveform, band: tuple[float, float], bins: int) -> Fold:
    t = seconds(waveform)
    v = volts(waveform)
    bias = float(v.mean())
    x = v - bias
    frequencies = np.arange(band[0], band[1], 0.001)
    spectrum = np.array([abs(np.sum(x * np.exp(-2j * np.pi * f * t))) for f in frequencies])
    f_star = float(frequencies[int(spectrum.argmax())])
    coefficient = np.sum(x * np.exp(-2j * np.pi * f_star * t)) * 2 / len(x)
    amplitude = float(abs(coefficient))
    phase = (t * f_star) % 1.0
    edges = np.linspace(0, 1, bins + 1)
    which = np.clip(np.digitize(phase, edges) - 1, 0, bins - 1)
    composite = np.array([v[which == b].mean() if np.any(which == b) else np.nan for b in range(bins)])
    waveform_rms = float(np.sqrt(np.nanmean((composite - bias) ** 2)))
    noise_rms = float(np.sqrt(np.mean((v - composite[which]) ** 2)))
    return Fold(f_star, bias, amplitude, waveform_rms, noise_rms, phase, (edges[:-1] + edges[1:]) / 2, composite)


def plot(waveform: GwAdcWaveform, result: Fold, level: Level | None, out: Path, show: bool) -> None:
    import matplotlib

    if not show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = seconds(waveform)
    v = volts(waveform)
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(10, 7))
    window = t <= 0.1
    top.plot(t[window] * 1000, v[window], ".-", ms=3, lw=0.5)
    top.set_xlabel("ms from first conversion")
    top.set_ylabel("V")
    heading = f"{waveform.ta_alias} {waveform.adc_channel.value}: first 100 ms, {len(t)} conversions in {t[-1]:.2f} s"
    if level is not None:
        heading = f"{describe(level)}\n{heading}"
    top.set_title(heading)
    bottom.plot(result.phase, v, ".", ms=2, alpha=0.3, label="samples")
    bottom.plot(result.bin_centers, result.composite_v, "-", lw=2, label="composite")
    bottom.set_xlabel(f"phase at {result.frequency_hz:.3f} Hz")
    bottom.set_ylabel("V")
    bottom.set_title(
        f"bias {result.bias_v:.4f} V, fundamental {result.amplitude_v * 1000:.2f} mV pk, "
        f"waveform {result.waveform_rms_v * 1000:.2f} mV rms, noise {result.noise_rms_v * 1000:.2f} mV rms"
    )
    bottom.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    if show:
        plt.show()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("instance", type=Path)
    parser.add_argument("--band", type=float, nargs=2, default=(59.5, 60.5))
    parser.add_argument("--bins", type=int, default=72)
    parser.add_argument("--no-plot", action="store_true")
    parser.add_argument("--show", action="store_true", help="open the interactive window as well as writing the png")
    args = parser.parse_args()

    waveform = load(args.instance)
    level = level_for(args.instance)
    result = fold(waveform, (args.band[0], args.band[1]), args.bins)
    if level is not None:
        print(describe(level))
    print(
        f"f={result.frequency_hz:.3f} Hz bias={result.bias_v:.4f} V "
        f"fundamental={result.amplitude_v * 1000:.2f} mV pk "
        f"waveform_rms={result.waveform_rms_v * 1000:.2f} mV noise_rms={result.noise_rms_v * 1000:.2f} mV "
        f"n={len(waveform.codes)}"
    )
    if not args.no_plot:
        out = args.instance.with_name(args.instance.stem + "-fold.png")
        print(f"plot -> {out}")
        plot(waveform, result, level, out, show=args.show)


if __name__ == "__main__":
    main()
