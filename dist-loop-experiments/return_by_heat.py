#!/usr/bin/env python3
"""Return temperature from distribution against source temperature at a
fixed hourly heat delivery, per distribution system: how hot the water
comes back when the same amount of heat is delivered with hotter or
cooler source water.

Reads every hourly file in this folder through houses.systems(). Each
system gets one grid, rows by heat delivered to distribution in the
hour and columns by flow-weighted source temperature. The first grid's
cells are the median flow-weighted return temperature and the number
of hours; the second gives the median share of the hour the loop
circulated in the same cells.

  uv run python return_by_heat.py > return-by-heat.md
"""

import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from houses import System, systems  # noqa: E402
from tables import Table  # noqa: E402

KBTU_PER_KWH = 3.41214
HEAT_BIN_KBTU = 5
HEAT_BINS = range(0, 40, HEAT_BIN_KBTU)
SOURCE_BIN_F = 10
SOURCE_BINS = range(110, 180, SOURCE_BIN_F)
MIN_HOURS = 10  # cells with fewer hours are left empty


class HeatCell(NamedTuple):
    """Hours of one system in one heat bin and one source bin."""

    heat_lo_kbtu: int
    source_lo_f: int
    hours: int
    return_median_f: float
    circulation_median: float


def cells(system: System) -> list[HeatCell]:
    hours = [h for h in system.hours if h.source_f is not None]
    heat = np.array([h.heat_kwh for h in hours]) * KBTU_PER_KWH
    source = np.array([h.source_f for h in hours])
    ret = np.array([h.return_f for h in hours])
    frac = np.array([h.flowing_fraction for h in hours])
    out = []
    for h_lo in HEAT_BINS:
        for s_lo in SOURCE_BINS:
            pick = ((heat >= h_lo) & (heat < h_lo + HEAT_BIN_KBTU)
                    & (source >= s_lo) & (source < s_lo + SOURCE_BIN_F))
            if pick.sum() < MIN_HOURS:
                continue
            out.append(HeatCell(h_lo, s_lo, int(pick.sum()),
                                float(np.median(ret[pick])), float(np.median(frac[pick]))))
    return out


def grid(found: list[HeatCell], percent: bool) -> list[str]:
    lines = ["| Heat kBTU/h | " + " | ".join(
        f"{lo}–{lo + SOURCE_BIN_F} °F" for lo in SOURCE_BINS) + " |",
             "|---|" + "---|" * len(SOURCE_BINS)]
    by_key = {(c.heat_lo_kbtu, c.source_lo_f): c for c in found}
    for h_lo in sorted({c.heat_lo_kbtu for c in found}):
        row = []
        for s_lo in SOURCE_BINS:
            c = by_key.get((h_lo, s_lo))
            if c is None:
                row.append("")
            elif percent:
                row.append(f"{c.circulation_median * 100:.0f}%")
            else:
                row.append(f"{c.return_median_f:.0f} ({c.hours})")
        lines.append(f"| {h_lo}–{h_lo + HEAT_BIN_KBTU} | " + " | ".join(row) + " |")
    return lines


def tables() -> list[Table]:
    rows = [(s.name, c.heat_lo_kbtu, c.heat_lo_kbtu + HEAT_BIN_KBTU, c.source_lo_f,
             c.source_lo_f + SOURCE_BIN_F, c.hours, round(c.return_median_f, 1),
             round(c.circulation_median, 3))
            for s in systems() for c in cells(s)]
    return [Table("return-by-heat",
                  "Hours by heat delivered and source temperature bin: median return and median circulation share",
                  ("System", "HeatLoKbtuPerH", "HeatHiKbtuPerH", "SourceLoF", "SourceHiF", "Hours",
                   "ReturnMedianF", "CirculationMedian"), rows, "return_by_heat.py")]


def main() -> None:
    for percent, title in (
        (False, "Median return °F (hours)"),
        (True, "Median share of the hour the loop circulated"),
    ):
        print(f"# {title}\n")
        print("Rows: heat delivered to distribution in the hour. Columns: "
              "flow-weighted source temperature.\n")
        for system in systems():
            print(f"**{system.name}**\n")
            print("\n".join(grid(cells(system), percent)) + "\n")


if __name__ == "__main__":
    main()
