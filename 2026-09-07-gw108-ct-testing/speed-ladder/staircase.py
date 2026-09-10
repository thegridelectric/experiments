#!/usr/bin/env python3
"""Draw a ladder run as a staircase: five cycles of the folded waveform at each
drive level, laid end to end in rising DAC order on one time axis.

Laptop side, from this folder. Each level's segment is its fold composite
(fold.py) repeated CYCLES times at the fitted frequency, so the segment is
the periodic waveform, not the raw burst; the level's pump drive and flow
label the segment. Writes <run>-staircase.png beside this script (committed, embedded in the README).

    uv run python staircase.py --run ladder1 [--show]
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))  # fold.py lives in the parent folder

from fold import Fold, fold, load  # noqa: E402
from ladder import Level  # noqa: E402

CYCLES = 5


def describe(level: Level) -> str:
    flow = "no fresh flow" if level.flow_gpm_x100 is None else f"secondary-flow {level.flow_gpm_x100 / 100:.2f} gpm"
    return f"pump drive {level.volts_x10 / 10:.1f} V (DAC {level.dac_code}), {flow}"



def levels(run: str) -> list[Level]:
    entries = json.loads((HERE / f"{run}-levels.json").read_text())
    return sorted((Level(**e) for e in entries), key=lambda lv: lv.volts_x10)


def segment(result: Fold) -> tuple[np.ndarray, np.ndarray]:
    """CYCLES periods of the composite, in seconds from the segment start."""
    period = 1 / result.frequency_hz
    t = np.concatenate([(result.bin_centers + k) * period for k in range(CYCLES)])
    v = np.tile(result.composite_v, CYCLES)
    return t, v


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run", required=True)
    parser.add_argument("--band", type=float, nargs=2, default=(59.5, 60.5))
    parser.add_argument("--bins", type=int, default=72)
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()

    import matplotlib

    if not args.show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(16, 6))
    start = 0.0
    run_levels = levels(args.run)
    if not run_levels:
        raise SystemExit(f"no levels for run {args.run}")
    for level in run_levels:
        waveform = load(HERE / "instances" / level.instance)
        result = fold(waveform, (args.band[0], args.band[1]), args.bins)
        t, v = segment(result)
        ax.plot((start + t) * 1000, v, "-", lw=1.2)
        width = CYCLES / result.frequency_hz
        ax.axvline((start + width) * 1000, color="0.8", lw=0.8)
        flow = "no flow reading" if level.flow_gpm_x100 is None else f"{level.flow_gpm_x100 / 100:.2f} gpm"
        ax.text(
            (start + width / 2) * 1000,
            1.0,
            f"{level.volts_x10 / 10:.1f} V\n{flow}\n{result.waveform_rms_v * 1000:.0f} mV rms",
            transform=ax.get_xaxis_transform(),
            ha="center",
            va="bottom",
            fontsize=9,
        )
        print(describe(level))
        start += width
    ax.set_xlabel(f"ms ({CYCLES} cycles of the fold composite per level, levels laid end to end)")
    ax.set_ylabel("V")
    ax.set_title(f"{args.run}: CT2 waveform vs secondary pump drive, {load(HERE / "instances" / run_levels[0].instance).ta_alias}", pad=44)
    fig.tight_layout()
    out = HERE / f"{args.run}-staircase.png"
    fig.savefig(out, dpi=120)
    print(f"plot -> {out}")
    if args.show:
        plt.show()


if __name__ == "__main__":
    main()
