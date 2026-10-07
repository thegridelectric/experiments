#!/usr/bin/env python3
"""Return temperature from distribution against BOTH source temperature
and how much of the hour the loop circulated, per distribution system:
the tables behind the question of how hot the water comes back when
hot water is sent.

Reads every hourly file in this folder through houses.systems(). Each
system gets one grid, rows by flow-weighted source temperature and
columns by circulation fraction. The first grid's cells are the median
flow-weighted return temperature and the number of hours; the second
adds the quartiles.

  uv run python return_temp.py > return-temp.md
"""

import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from houses import System, systems  # noqa: E402
from tables import Table  # noqa: E402

BIN_F = 10
FIRST_BIN_F = 100
MIN_HOURS = 10  # cells with fewer hours are left empty
# circulation-fraction bands: label, lower bound (inclusive), upper bound
BANDS = (("under 20%", 0.02, 0.20), ("20–40%", 0.20, 0.40),
         ("40–60%", 0.40, 0.60), ("60–80%", 0.60, 0.80),
         ("80–95%", 0.80, 0.95), ("95–100%", 0.95, 1.01))


class GridCell(NamedTuple):
    """Hours of one system in one source bin and one circulation band."""

    source_lo_f: int
    band: str
    band_lo: float
    band_hi: float
    hours: int
    return_q25_f: float
    return_median_f: float
    return_q75_f: float


def cells(system: System) -> list[GridCell]:
    hours = [h for h in system.hours if h.source_f is not None]
    frac = np.array([h.flowing_fraction for h in hours])
    source = np.array([h.source_f for h in hours])
    ret = np.array([h.return_f for h in hours])
    out = []
    for lo in range(FIRST_BIN_F, 200, BIN_F):
        for label, f_lo, f_hi in BANDS:
            pick = (source >= lo) & (source < lo + BIN_F) & (frac >= f_lo) & (frac < f_hi)
            if pick.sum() < MIN_HOURS:
                continue
            q25, q50, q75 = np.percentile(ret[pick], [25, 50, 75])
            out.append(GridCell(lo, label, f_lo, min(f_hi, 1.0), int(pick.sum()),
                                float(q25), float(q50), float(q75)))
    return out


def grid(found: list[GridCell], quartiles: bool) -> list[str]:
    lines = ["| Source °F | " + " | ".join(label for label, _, _ in BANDS) + " |",
             "|---|" + "---|" * len(BANDS)]
    by_key = {(c.source_lo_f, c.band): c for c in found}
    for lo in sorted({c.source_lo_f for c in found}):
        row = []
        for label, _, _ in BANDS:
            c = by_key.get((lo, label))
            if c is None:
                row.append("")
            elif quartiles:
                row.append(f"{c.return_q25_f:.0f} / {c.return_median_f:.0f} / {c.return_q75_f:.0f}")
            else:
                row.append(f"{c.return_median_f:.0f} ({c.hours})")
        lines.append(f"| {lo}–{lo + BIN_F} | " + " | ".join(row) + " |")
    return lines


def tables() -> list[Table]:
    rows = [(s.name, c.source_lo_f, c.source_lo_f + BIN_F, c.band, c.band_lo, c.band_hi, c.hours,
             round(c.return_q25_f, 1), round(c.return_median_f, 1), round(c.return_q75_f, 1))
            for s in systems() for c in cells(s)]
    return [Table("return-by-circulation",
                  "Hours by source temperature bin and share of the hour the loop circulated: return quartiles",
                  ("System", "SourceLoF", "SourceHiF", "CirculationBand", "CirculationLo", "CirculationHi",
                   "Hours", "ReturnQ25F", "ReturnMedianF", "ReturnQ75F"), rows, "return_temp.py")]


def main() -> None:
    for quartiles, title in (
        (False, "Median return °F (hours)"),
        (True, "Return °F, p25 / median / p75"),
    ):
        print(f"# {title}\n")
        print("Rows: flow-weighted source temperature. Columns: share of the "
              "hour the distribution loop circulated.\n")
        for system in systems():
            print(f"**{system.name}**\n")
            print("\n".join(grid(cells(system), quartiles)) + "\n")


if __name__ == "__main__":
    main()
