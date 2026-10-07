#!/usr/bin/env python3
"""Return temperature from distribution against supply temperature at a
fixed hourly heat delivery, per distribution system: how hot the water
comes back when the same amount of heat is delivered with hotter or
cooler supply.

Reads every hourly file in this folder through houses.systems(). Each
system gets one grid, rows by heat delivered to distribution in the
hour and columns by flow-weighted supply temperature. The first grid's
cells are the median flow-weighted return temperature and the number
of hours; the second gives the median share of the hour the loop
circulated in the same cells.

  uv run python return_by_heat.py > return-by-heat.md
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from houses import systems  # noqa: E402

KBTU_PER_KWH = 3.41214
HEAT_BIN_KBTU = 5
HEAT_BINS = range(0, 40, HEAT_BIN_KBTU)
SUPPLY_BIN_F = 10
SUPPLY_BINS = range(110, 180, SUPPLY_BIN_F)
MIN_HOURS = 10  # cells with fewer hours are left empty


def grid(heat: np.ndarray, supply: np.ndarray, value: np.ndarray,
         percent: bool) -> list[str]:
    lines = ["| Heat kBTU/h | " + " | ".join(
        f"{lo}–{lo + SUPPLY_BIN_F} °F" for lo in SUPPLY_BINS) + " |",
             "|---|" + "---|" * len(SUPPLY_BINS)]
    for h_lo in HEAT_BINS:
        cells = []
        for s_lo in SUPPLY_BINS:
            pick = ((heat >= h_lo) & (heat < h_lo + HEAT_BIN_KBTU)
                    & (supply >= s_lo) & (supply < s_lo + SUPPLY_BIN_F))
            if pick.sum() < MIN_HOURS:
                cells.append("")
                continue
            mid = np.median(value[pick])
            cells.append(f"{mid * 100:.0f}%" if percent
                         else f"{mid:.0f} ({pick.sum()})")
        if any(cells):
            lines.append(f"| {h_lo}–{h_lo + HEAT_BIN_KBTU} | " + " | ".join(cells) + " |")
    return lines


def main() -> None:
    for percent, title in (
        (False, "Median return °F (hours)"),
        (True, "Median share of the hour the loop circulated"),
    ):
        print(f"# {title}\n")
        print("Rows: heat delivered to distribution in the hour. Columns: "
              "flow-weighted supply temperature.\n")
        for system in systems():
            hours = [h for h in system.hours if h.supply_f is not None]
            heat = np.array([h.heat_kwh for h in hours]) * KBTU_PER_KWH
            supply = np.array([h.supply_f for h in hours])
            value = np.array([h.flowing_fraction if percent else h.return_f
                              for h in hours])
            print(f"**{system.name}**\n")
            print("\n".join(grid(heat, supply, value, percent)) + "\n")


if __name__ == "__main__":
    main()
