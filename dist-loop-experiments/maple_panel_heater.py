#!/usr/bin/env python3
"""Maple before and after its panel heater was added: return temperature
at the same heat delivered, and the emitters' output per degree.

Reads maple's hourly file through houses.systems(), which holds the
dates: before is `maple1`, after is `maple2`.

  uv run python maple_panel_heater.py > maple-panel-heater.md
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from houses import systems  # noqa: E402

ROOM_F = 68.0  # assumed room temperature for the output-per-degree figure
KBTU_PER_KWH = 3.41214
HEAT_BINS = (5, 10, 15)
HEAT_BIN_KBTU = 5
SUPPLY_BINS = range(130, 170, 10)
MIN_HOURS = 10
MIN_FRACTION = 0.3  # output per degree needs the loop circulating this much


def main() -> None:
    by_name = {s.name: s.hours for s in systems()}
    period_hours = [(label, [h for h in by_name[name] if h.supply_f is not None])
                    for label, name in (("before", "maple1"), ("after", "maple2"))]
    hours = [h for _, part in period_hours for h in part]
    heat = np.array([h.heat_kwh for h in hours]) * KBTU_PER_KWH
    supply = np.array([h.supply_f for h in hours])
    ret = np.array([h.return_f for h in hours])
    frac = np.array([h.flowing_fraction for h in hours])
    n_before = len(period_hours[0][1])
    index = np.arange(len(hours))
    periods = (("before", index < n_before), ("after", index >= n_before))

    print("# Maple: median return °F (share of the hour circulating)\n")
    print("| Heat kBTU/h | Panel heater | " + " | ".join(
        f"{lo}–{lo + 10} °F" for lo in SUPPLY_BINS) + " |")
    print("|---|---|" + "---|" * len(SUPPLY_BINS))
    for h_lo in HEAT_BINS:
        for name, in_period in periods:
            cells = []
            for s_lo in SUPPLY_BINS:
                pick = (in_period & (heat >= h_lo) & (heat < h_lo + HEAT_BIN_KBTU)
                        & (supply >= s_lo) & (supply < s_lo + 10))
                cells.append(
                    f"{np.median(ret[pick]):.0f} ({np.median(frac[pick]) * 100:.0f}%)"
                    if pick.sum() >= MIN_HOURS else "")
            print(f"| {h_lo}–{h_lo + HEAT_BIN_KBTU} | {name} | " + " | ".join(cells) + " |")

    print("\n# Maple: emitter output while circulating, BTU/h per °F of "
          f"mean water temperature above {ROOM_F:.0f} °F\n")
    on = frac >= MIN_FRACTION
    per_degree = heat * 1000 / np.where(on, frac, 1) / ((supply + ret) / 2 - ROOM_F)
    for name, in_period in periods:
        pick = in_period & on
        print(f"- {name}: median {np.median(per_degree[pick]):.0f} "
              f"({pick.sum()} hours)")


if __name__ == "__main__":
    main()
