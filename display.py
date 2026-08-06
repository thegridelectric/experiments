#!/usr/bin/env python3
"""Interim display conversion for experiment CSVs — wire encodings to
human-readable floats (temperatures in F, flows in gpm).

The shape mirrors scada's gwsproto/conversions/temperature.py
(convert_temp_to_f), standalone here because experiment scripts don't
import fleet repos. Encodings are the wire-encoding names carried by
gw1.unit and spaceheat.telemetry.name; conversions are written from
those enums' descriptions. DELETE this module the day harmonize-units
(affine metadata on unit values + generated convert()/display()) ships.

As a script, converts a pull_readings.py-style CSV in place-adjacent
form: the CSV's own `# units:` header names each channel's encoding, so
the output needs no extra arguments.

  ./display.py spruce_incident_data.csv   # writes *-readable.csv
"""

import ast
import csv
import sys
from pathlib import Path

TEMP_TO_F = {
    # encoding -> raw-to-F conversion
    "FahrenheitX100": lambda raw: raw / 100,
    "WaterTempFTimes1000": lambda raw: raw / 1000,
    "AirTempFTimes1000": lambda raw: raw / 1000,
    "CelsiusTimes100": lambda raw: raw / 100 * 9 / 5 + 32,
    "WaterTempCTimes1000": lambda raw: raw / 1000 * 9 / 5 + 32,
    "AirTempCTimes1000": lambda raw: raw / 1000 * 9 / 5 + 32,
}
FLOW_TO_GPM = {
    "GpmTimes100": lambda raw: raw / 100,
    "GpmX100": lambda raw: raw / 100,
}


def convert_temp_to_f(raw: float, encoding: str) -> float:
    if encoding not in TEMP_TO_F:
        raise ValueError(f"Unknown temperature encoding: {encoding}")
    return TEMP_TO_F[encoding](raw)


def to_display(raw: float, encoding: str) -> tuple[float, str]:
    """(value, unit label) — temps to F, flows to gpm, else unchanged."""
    if encoding in TEMP_TO_F:
        return round(TEMP_TO_F[encoding](raw), 2), "F"
    if encoding in FLOW_TO_GPM:
        return round(FLOW_TO_GPM[encoding](raw), 2), "gpm"
    return raw, encoding


# Fallback for CSVs whose columns self-label their encoding by suffix
# (e.g. avg_gpm100) instead of carrying a `# units:` header.
COLUMN_SUFFIXES = {
    "gpm100": (lambda raw: round(raw / 100, 2), "gpm"),
    "fx100": (lambda raw: round(raw / 100, 2), "f"),
}


def convert_suffix_csv(path: Path) -> Path:
    lines = path.read_text().splitlines()
    reader = csv.DictReader(lines)
    renames = {}
    for col in reader.fieldnames:
        for suffix, (fn, label) in COLUMN_SUFFIXES.items():
            if col.endswith(f"_{suffix}"):
                renames[col] = (col.removesuffix(f"_{suffix}") + f"_{label}", fn)
    if not renames:
        raise SystemExit(f"{path}: no '# units:' header and no known column suffixes")
    out_path = path.with_name(path.stem + "-readable.csv")
    fieldnames = [renames.get(c, (c,))[0] for c in reader.fieldnames]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            out = {}
            for col, val in row.items():
                if col in renames and val != "":
                    new_col, fn = renames[col]
                    out[new_col] = fn(float(val))
                else:
                    out[renames.get(col, (col,))[0]] = val
            writer.writerow(out)
    return out_path


def convert_csv(path: Path) -> Path:
    """Convert a pull_readings-style CSV (with a `# units:` header) to a
    -readable sibling: value columns become display floats, and a
    display unit column is appended."""
    lines = path.read_text().splitlines()
    if not lines[0].startswith("# units:"):
        return convert_suffix_csv(path)
    units = ast.literal_eval(lines[0].removeprefix("# units:").strip())
    reader = csv.DictReader(lines[1:])
    out_path = path.with_name(path.stem + "-readable.csv")
    value_cols = [c for c in reader.fieldnames if c.endswith("_value")]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[*reader.fieldnames, "display_unit"])
        writer.writeheader()
        for row in reader:
            encoding = units[row["channel"]][0]
            unit_label = encoding
            for col in value_cols:
                if row[col] != "":
                    value, unit_label = to_display(float(row[col]), encoding)
                    row[col] = value
            row["display_unit"] = unit_label
            writer.writerow(row)
    return out_path


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(convert_csv(Path(arg)))
