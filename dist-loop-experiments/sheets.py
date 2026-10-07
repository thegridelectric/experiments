#!/usr/bin/env python3
"""Every table this folder produces, and the data behind them, as one
workbook and a folder of CSV files for people who read spreadsheets.

`dist-loop-experiments.xlsx` opens on a Summary tab naming every other
tab; then the analysis tables (one tab each, one number per cell),
then the hourly records per house. The minute grid is written as CSV
only unless --minute-tabs is given: a season is about 300,000 rows a
house. The January 24 step table reaches the journal DB; --no-db
leaves it out. The folder's .gitignore keeps the workbook and csv/
out of git; this script regenerates them.

  uv run python sheets.py [--no-db] [--minute-tabs]
"""

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

import beech_jan24_steps  # noqa: E402
import bolus_recovery  # noqa: E402
import maple_panel_heater  # noqa: E402
import return_by_heat  # noqa: E402
import return_temp  # noqa: E402
import steady_drop  # noqa: E402
from houses import ZONE_PAIRS, hourly_files, minute_file  # noqa: E402
from tables import Table, write_csv, write_workbook  # noqa: E402

EXPERIMENT = "dist-loop-experiments"
ABOUT = ("The fleet's distribution loops over the 2025-26 heating season: source and return "
         "temperatures, flow and heat delivered, hourly for five houses and by the minute for beech. "
         "Every cell is one number; the README in this folder says how each table was made.")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--no-db", action="store_true", help="skip the tables that pull from the journal DB")
    p.add_argument("--minute-tabs", action="store_true", help="also put the minute grid in the workbook")
    args = p.parse_args()
    tables: list[Table] = []
    tables += steady_drop.tables()
    tables += return_temp.tables()
    tables += return_by_heat.tables()
    tables += maple_panel_heater.tables()
    if not args.no_db:
        tables += beech_jan24_steps.tables()
    for house in sorted(ZONE_PAIRS):
        tables += bolus_recovery.tables(house)
    tables += [f.table() for f in hourly_files()]
    minute_tables = [minute_file(house).table() for house in sorted(ZONE_PAIRS)]
    csv_dir = HERE / "csv"
    for t in tables + minute_tables:
        write_csv(t.check(), csv_dir)
    book = write_workbook(tables + (minute_tables if args.minute_tabs else []),
                          HERE / f"{EXPERIMENT}.xlsx", EXPERIMENT, ABOUT)
    print(f"wrote {book.name} ({len(tables) + (len(minute_tables) if args.minute_tabs else 0)} tabs) "
          f"and {len(tables) + len(minute_tables)} files in csv/")


if __name__ == "__main__":
    main()
