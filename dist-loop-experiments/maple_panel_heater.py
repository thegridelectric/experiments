#!/usr/bin/env python3
"""Maple before and after its panel heater was added: return temperature
at the same heat delivered, and the emitters' output per degree.

Reads maple's hourly file through houses.systems(), which holds the
dates: before is `maple1`, after is `maple2`.

  uv run python maple_panel_heater.py > maple-panel-heater.md
"""

import sys
from pathlib import Path
from typing import NamedTuple

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from houses import systems  # noqa: E402
from records import HourRecord  # noqa: E402
from tables import Table  # noqa: E402

ROOM_F = 68.0  # assumed room temperature for the output-per-degree figure
KBTU_PER_KWH = 3.41214
HEAT_BINS = (5, 10, 15)
HEAT_BIN_KBTU = 5
SOURCE_BINS = range(130, 170, 10)
MIN_HOURS = 10
MIN_FRACTION = 0.3  # output per degree needs the loop circulating this much
PERIODS = (("before", "maple1"), ("after", "maple2"))


class ReturnCell(NamedTuple):
    """Maple hours in one period, heat bin and source bin."""

    period: str
    heat_lo_kbtu: int
    source_lo_f: int
    hours: int
    return_median_f: float
    circulation_median: float


class PerDegree(NamedTuple):
    """The emitters' output per degree of mean water over room, one period."""

    period: str
    hours: int
    median_btu_per_h_per_f: float


def period_hours() -> list[tuple[str, list[HourRecord]]]:
    by_name = {s.name: s.hours for s in systems()}
    return [(label, [h for h in by_name[name] if h.source_f is not None]) for label, name in PERIODS]


def return_cells() -> list[ReturnCell]:
    out = []
    for label, hours in period_hours():
        heat = np.array([h.heat_kwh for h in hours]) * KBTU_PER_KWH
        source = np.array([h.source_f for h in hours])
        ret = np.array([h.return_f for h in hours])
        frac = np.array([h.flowing_fraction for h in hours])
        for h_lo in HEAT_BINS:
            for s_lo in SOURCE_BINS:
                pick = ((heat >= h_lo) & (heat < h_lo + HEAT_BIN_KBTU)
                        & (source >= s_lo) & (source < s_lo + 10))
                if pick.sum() >= MIN_HOURS:
                    out.append(ReturnCell(label, h_lo, s_lo, int(pick.sum()),
                                          float(np.median(ret[pick])), float(np.median(frac[pick]))))
    return out


def per_degree() -> list[PerDegree]:
    out = []
    for label, hours in period_hours():
        heat = np.array([h.heat_kwh for h in hours]) * KBTU_PER_KWH
        source = np.array([h.source_f for h in hours])
        ret = np.array([h.return_f for h in hours])
        frac = np.array([h.flowing_fraction for h in hours])
        on = frac >= MIN_FRACTION
        value = heat[on] * 1000 / frac[on] / ((source[on] + ret[on]) / 2 - ROOM_F)
        out.append(PerDegree(label, int(on.sum()), float(np.median(value))))
    return out


def tables() -> list[Table]:
    return [
        Table("maple-panel-heater",
              "Maple hours before and after the panel heater, by heat delivered and source bin: median return and circulation share",
              ("Period", "HeatLoKbtuPerH", "HeatHiKbtuPerH", "SourceLoF", "SourceHiF", "Hours",
               "ReturnMedianF", "CirculationMedian"),
              [(c.period, c.heat_lo_kbtu, c.heat_lo_kbtu + HEAT_BIN_KBTU, c.source_lo_f, c.source_lo_f + 10,
                c.hours, round(c.return_median_f, 1), round(c.circulation_median, 3)) for c in return_cells()],
              "maple_panel_heater.py"),
        Table("maple-output-per-degree",
              f"Maple emitter output while circulating, BTU/h per °F of mean water temperature above {ROOM_F:.0f} °F room",
              ("Period", "Hours", "MedianBtuPerHPerF"),
              [(p.period, p.hours, round(p.median_btu_per_h_per_f)) for p in per_degree()],
              "maple_panel_heater.py"),
    ]


def main() -> None:
    found = {(c.heat_lo_kbtu, c.period, c.source_lo_f): c for c in return_cells()}
    print("# Maple: median return °F (share of the hour circulating)\n")
    print("| Heat kBTU/h | Panel heater | " + " | ".join(
        f"{lo}–{lo + 10} °F" for lo in SOURCE_BINS) + " |")
    print("|---|---|" + "---|" * len(SOURCE_BINS))
    for h_lo in HEAT_BINS:
        for name, _ in PERIODS:
            row = []
            for s_lo in SOURCE_BINS:
                c = found.get((h_lo, name, s_lo))
                row.append(f"{c.return_median_f:.0f} ({c.circulation_median * 100:.0f}%)" if c else "")
            print(f"| {h_lo}–{h_lo + HEAT_BIN_KBTU} | {name} | " + " | ".join(row) + " |")
    print("\n# Maple: emitter output while circulating, BTU/h per °F of "
          f"mean water temperature above {ROOM_F:.0f} °F\n")
    for p in per_degree():
        print(f"- {p.period}: median {p.median_btu_per_h_per_f:.0f} ({p.hours} hours)")


if __name__ == "__main__":
    main()
