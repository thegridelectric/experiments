#!/usr/bin/env python3
"""Return temperature from distribution against BOTH supply temperature
and how much of the hour the loop circulated, per distribution system:
the tables behind the question of how hot the water comes back when
hot water is sent.

Reads every hourly file in this folder through houses.systems(). Each
system gets one grid, rows by flow-weighted supply temperature and
columns by circulation fraction. The first grid's cells are the median
flow-weighted return temperature and the number of hours; the second
adds the quartiles.

  uv run python return_temp.py > return-temp.md
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from houses import systems  # noqa: E402

BIN_F = 10
FIRST_BIN_F = 100
MIN_HOURS = 10  # cells with fewer hours are left empty
# circulation-fraction bands: label, lower bound (inclusive), upper bound
BANDS = (("under 20%", 0.02, 0.20), ("20–40%", 0.20, 0.40),
         ("40–60%", 0.40, 0.60), ("60–80%", 0.60, 0.80),
         ("80–95%", 0.80, 0.95), ("95–100%", 0.95, 1.01))


def grid(supply: np.ndarray, frac: np.ndarray, ret: np.ndarray,
         quartiles: bool) -> list[str]:
    lines = ["| Supply °F | " + " | ".join(label for label, _, _ in BANDS) + " |",
             "|---|" + "---|" * len(BANDS)]
    for lo in range(FIRST_BIN_F, 200, BIN_F):
        cells = []
        for _, f_lo, f_hi in BANDS:
            pick = ((supply >= lo) & (supply < lo + BIN_F)
                    & (frac >= f_lo) & (frac < f_hi))
            if pick.sum() < MIN_HOURS:
                cells.append("")
                continue
            q25, q50, q75 = np.percentile(ret[pick], [25, 50, 75])
            cells.append(f"{q25:.0f} / {q50:.0f} / {q75:.0f}" if quartiles
                         else f"{q50:.0f} ({pick.sum()})")
        if any(cells):
            lines.append(f"| {lo}–{lo + BIN_F} | " + " | ".join(cells) + " |")
    return lines


def main() -> None:
    for quartiles, title in (
        (False, "Median return °F (hours)"),
        (True, "Return °F, p25 / median / p75"),
    ):
        print(f"# {title}\n")
        print("Rows: flow-weighted supply temperature. Columns: share of the "
              "hour the distribution loop circulated.\n")
        for system in systems():
            hours = [h for h in system.hours if h.supply_f is not None]
            frac = np.array([h.flowing_fraction for h in hours])
            supply = np.array([h.supply_f for h in hours])
            ret = np.array([h.return_f for h in hours])
            print(f"**{system.name}**\n")
            print("\n".join(grid(supply, frac, ret, quartiles)) + "\n")


if __name__ == "__main__":
    main()
