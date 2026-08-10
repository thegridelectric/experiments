#!/usr/bin/env python3
"""Wire-unit encodings: how a channel's serialized values are encoded,
and their interim conversion to human-natural display units.

A channel's wire encoding comes from its own sema word — a data
channel's TelemetryName, a derived channel's OutputUnit — extracted
here by type dispatch (word_encoding). The conversion tables below map
those encodings to natural floats (temperatures F, flows gpm, voltage
mV); they mirror scada's gwsproto/conversions shape and are INTERIM:
delete them the day harmonize-units (affine metadata on unit values +
generated convert()/display()) ships.

As a script, converts a pull-style CSV with a `# units:` header (or
suffix-labeled columns) to a `-readable.csv` sibling:

  ./unit_encodings.py <file.csv>
"""

import ast
import csv
import sys
from pathlib import Path
from typing import Callable, TypeAlias

sys.path.insert(0, str(Path(__file__).parent / "src"))

from gwexp.sema.enums import Gw1Unit, SpaceheatTelemetryName  # noqa: E402
from gwexp.sema.types import DataChannelGt, DerivedChannelGt  # noqa: E402

def word_encoding(
    word: DataChannelGt | DerivedChannelGt,
) -> SpaceheatTelemetryName | Gw1Unit:
    """The channel's wire encoding, dispatched on the word's type.
    Both enums are str subclasses whose members equal their wire
    strings, so the return value drops into string keyed tables while
    keeping its type. Refuses any other word rather than guessing."""
    if isinstance(word, DataChannelGt):
        return word.telemetry_name
    if isinstance(word, DerivedChannelGt):
        return word.output_unit
    raise TypeError(
        f"no wire-encoding rule for {word.type_name}/{word.version}"
    )



# Conversion tables keyed by the ENUM MEMBERS themselves: a typo is an
# AttributeError at import, and because the generated enums are str
# subclasses, encodings arriving as plain strings (e.g. from a CSV
# `# units:` header) still hit these keys.
Encoding: TypeAlias = SpaceheatTelemetryName | Gw1Unit

# Tables are keyed by enum members; the value type says lookups may use
# any Encoding-or-string (str-subclass hash equality makes that sound).
TEMP_TO_F: dict[Encoding | str, "Callable[[float], float]"] = {
    Gw1Unit.FahrenheitX100: lambda raw: raw / 100,
    SpaceheatTelemetryName.WaterTempFTimes1000: lambda raw: raw / 1000,
    SpaceheatTelemetryName.AirTempFTimes1000: lambda raw: raw / 1000,
    SpaceheatTelemetryName.CelsiusTimes100: lambda raw: raw / 100 * 9 / 5 + 32,
    SpaceheatTelemetryName.WaterTempCTimes1000: lambda raw: raw / 1000 * 9 / 5 + 32,
    SpaceheatTelemetryName.AirTempCTimes1000: lambda raw: raw / 1000 * 9 / 5 + 32,
}
FLOW_TO_GPM: dict[Encoding | str, "Callable[[float], float]"] = {
    SpaceheatTelemetryName.GpmTimes100: lambda raw: raw / 100,
    Gw1Unit.GpmX100: lambda raw: raw / 100,
}
VOLTAGE_TO_MV: dict[Encoding | str, "Callable[[float], float]"] = {
    SpaceheatTelemetryName.MicroVolts: lambda raw: raw / 1000,
}


def convert_temp_to_f(raw: float, encoding: Encoding) -> float:
    if encoding not in TEMP_TO_F:
        raise ValueError(f"Unknown temperature encoding: {encoding}")
    return TEMP_TO_F[encoding](raw)


def to_display(raw: float, encoding: Encoding | str) -> tuple[float, str]:
    """(value, display-unit label) — temps to F, flows to gpm, voltage
    to mV, anything else unchanged with its encoding as the label.
    Accepts a typed encoding from word_encoding, or a plain string when
    the encoding came from a file header (untrusted input, resolved by
    the str-subclass key equality above)."""
    if encoding in TEMP_TO_F:
        return round(TEMP_TO_F[encoding](raw), 2), "F"
    if encoding in FLOW_TO_GPM:
        return round(FLOW_TO_GPM[encoding](raw), 2), "gpm"
    if encoding in VOLTAGE_TO_MV:
        return round(VOLTAGE_TO_MV[encoding](raw), 3), "mV"
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
    if reader.fieldnames is None:
        raise SystemExit(f"{path}: empty CSV")
    renames = {}
    for col in reader.fieldnames:
        for suffix, (fn, label) in COLUMN_SUFFIXES.items():
            if col.endswith(f"_{suffix}"):
                renames[col] = (col.removesuffix(f"_{suffix}") + f"_{label}", fn)
    if not renames:
        raise SystemExit(f"{path}: no '# units:' header and no known column suffixes")
    out_path = path.with_name(path.stem + "-readable.csv")
    fieldnames = [renames.get(c, (c,))[0] for c in reader.fieldnames]  # guarded above
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
    if reader.fieldnames is None:
        raise SystemExit(f"{path}: empty CSV")
    out_path = path.with_name(path.stem + "-readable.csv")
    value_cols = [c for c in reader.fieldnames if c.endswith("_value")]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[*(reader.fieldnames or []), "display_unit"])
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
