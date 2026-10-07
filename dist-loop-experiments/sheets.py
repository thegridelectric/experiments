#!/usr/bin/env python3
"""The tables behind one document in the heating-system-design repo, as
a workbook for people who read spreadsheets, plus every table this
folder produces as CSV files.

Each document gets its own workbook, `<document>.xlsx`, holding only
the tables its text draws on: a Summary tab naming every other tab,
then one tab per table, then the records the tables were made from.
The minute grid is written as CSV only unless --minute-tabs is given:
a season is about 300,000 rows a house. Tables that reach the journal
DB are left out with --no-db. The folder's .gitignore keeps the
workbooks and csv/ out of git; this script regenerates them.

  uv run python sheets.py beech-emitter-physics-mystery [--no-db] [--minute-tabs]
"""

import argparse
import datetime
import sys
from pathlib import Path
from typing import Callable, NamedTuple
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

import beech_jan24_steps  # noqa: E402
import bolus_recovery  # noqa: E402
import emitter_theory  # noqa: E402
import steady_drop  # noqa: E402
from houses import ZONE_PAIRS, hourly_files, minute_file  # noqa: E402
from tables import Table, write_csv, write_workbook  # noqa: E402


class Options(NamedTuple):
    """What the command line allows a document's table list to include."""

    db: bool  # tables that reach the journal DB
    minute_tabs: bool  # the minute grid as workbook tabs


class Document(NamedTuple):
    """One document in heating-system-design and the tables its text draws on."""

    slug: str  # the document's file name without .md; the workbook's name
    about: str  # one or two lines for the Summary tab
    tables: Callable[[Options], list[Table]]


def rows_where(table: Table, name: str, column: str, keep: Callable[[object], bool], title: str) -> Table:
    """The rows of a table whose value in one column passes, as a new table."""
    i = table.columns.index(column)
    return table._replace(name=name, title=title, rows=[r for r in table.rows if keep(r[i])])


def has_formulas(table: Table) -> bool:
    """A table of live Excel formulas has no CSV form; its Python twin does."""
    return any(isinstance(c, str) and c.startswith("=") for r in table.rows for c in r)


def mystery_tables(opt: Options) -> list[Table]:
    house = "beech"
    out: list[Table] = []
    if opt.db:
        out += beech_jan24_steps.tables()
    minute = minute_file(house).table()
    start_s, end_s = beech_jan24_steps.ms("09:00") // 1000, beech_jan24_steps.ms("12:30") // 1000
    out.append(rows_where(minute, f"{house}-2026-01-24-minutes", "MinuteStartS",
                          lambda s: start_s <= s < end_s,  # type: ignore[operator]
                          f"Beech {beech_jan24_steps.DAY}, 09:00 to 12:30 ET: the minute trace under the hand-set 0-10 V steps"))
    (steady,) = steady_drop.tables()
    out.append(rows_where(steady, f"{house}-steady-drop", "System", lambda s: s == house,
                          "Beech steady-circulation hours by source temperature bin: drop quartiles, median flow, median heat"))
    events, _, _ = bolus_recovery.tables(house)
    out.append(events)
    out += emitter_theory.tables()
    out += [f.table() for f in hourly_files() if f.house == house]
    if opt.minute_tabs:
        out.append(minute)
    return out


ET = ZoneInfo("America/New_York")


def et_s(day: datetime.date, hhmm: str) -> int:
    h, m = (int(x) for x in hhmm.split(":"))
    return int(datetime.datetime(day.year, day.month, day.day, h, m, tzinfo=ET).timestamp())


def memo_tables(opt: Options) -> list[Table]:
    house = "beech"
    day = datetime.date(2026, 1, 26)
    minute = minute_file(house).table()
    start_s, end_s = et_s(day, "05:45"), et_s(day, "07:15")
    out: list[Table] = [rows_where(minute, f"{house}-2026-01-26-minutes", "MinuteStartS",
                                   lambda s: start_s <= s < end_s,  # type: ignore[operator]
                                   f"Beech {day}, 05:45 to 07:15 ET: the minute trace around the 06:17 upstairs call")]
    out += bolus_recovery.tables(house)
    (steady,) = steady_drop.tables()
    out.append(rows_where(steady, f"{house}-steady-drop", "System", lambda s: s == house,
                          "Beech steady-circulation hours by source temperature bin: drop quartiles, median flow, median heat"))
    if opt.minute_tabs:
        out.append(minute)
    return out


DOCUMENTS = {d.slug: d for d in [
    Document("beech-emitter-physics-mystery",
             "Beech's distribution loop on 2026-01-24, when the pump's 0-10 V output was stepped by hand with the "
             "downstairs zone calling: each step over its counted minutes, the minute trace under the steps, the season's "
             "steady hours for comparison, the upstairs calls whose recovery sets the ten-minute exclusion, and the hourly "
             "records. Every cell is one number; the README in the experiments folder says how each table was made.",
             mystery_tables),
    Document("cold-zone-call-during-steady-heating-memo",
             "Beech's distribution loop when an idle zone calls inside a steady call: the minute trace around the "
             "2026-01-26 06:17 call, the season's 45 such calls with their recovery and the cold water each returned, "
             "the drop's later movement against control minutes, the slug as a volume, and the steady hours the "
             "source-drop line comes from. Every cell is one number; the README in the experiments folder says how "
             "each table was made.",
             memo_tables),
]}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("document", choices=sorted(DOCUMENTS))
    p.add_argument("--no-db", action="store_true", help="skip the tables that pull from the journal DB")
    p.add_argument("--minute-tabs", action="store_true", help="also put the minute grid in the workbook")
    args = p.parse_args()
    opt = Options(db=not args.no_db, minute_tabs=args.minute_tabs)
    doc = DOCUMENTS[args.document]
    tables = [t.check() for t in doc.tables(opt)]
    csv_dir = HERE / "csv"
    for t in tables + [minute_file(h).table() for h in sorted(ZONE_PAIRS)]:
        if not has_formulas(t):
            write_csv(t.check(), csv_dir)
    book = write_workbook(tables, HERE / f"{doc.slug}.xlsx", doc.slug, doc.about)
    print(f"wrote {book.name} ({len(tables)} tabs) and {len(list(csv_dir.glob('*.csv')))} files in csv/")


if __name__ == "__main__":
    main()
