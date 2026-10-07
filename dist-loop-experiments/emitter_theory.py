#!/usr/bin/env python3
"""What the emitter characteristic says the January 24 steps at beech
should have delivered, and the heat the fast steps stored in the iron,
twice over: once as numbers computed here, once as live Excel formulas
over the same inputs, so the two can be read side by side.

Output = K x (mean water temperature - room)^n for a fixed set of
emitters (EN 442; ASHRAE radiator chapter), with the water side
500 x gpm x drop. The 3.5 V step calibrates K. At another flow and
source the return is the fixed point of
    R = S - K x ((S + R) / 2 - room)^n / (500 x gpm),
reached here by iteration from the calibration return; each Excel
column is one iteration, and seven are more than enough (the map
contracts by about 0.15 a step). The infinite-flow row is the ceiling:
return equal to source.

The fast steps' excess of measured over theory, times the minutes
held, is heat that stayed in the distribution system; divided by the
return's rise over the step it is the thermal mass that took it.

  uv run python emitter_theory.py
"""

import sys
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from tables import Table  # noqa: E402

ROOM_F = 69.0
EXPONENT = 1.3  # n for cast-iron radiators and fin-tube baseboard
BTU_PER_HR_PER_GPM_F = 500.0
ITERATIONS = 7
INPUTS = "theory-inputs"  # the tab the formulas read


class Step(NamedTuple):
    """One January 24 step as the paper's theory table takes it. No sema
    word holds an emitter-theory row; a word for it retires this."""

    volts: float
    gpm: float
    source_f: float
    measured_kbtu_per_h: float


CALIBRATION = Step(3.5, 1.98, 168.0, 21.0)
CALIBRATION_RETURN_F = 146.0
STEPS = [CALIBRATION, Step(6.0, 3.16, 171.0, 32.0), Step(8.0, 4.12, 173.0, 38.0)]


class FastStep(NamedTuple):
    """A step the iron charged during: its return at start and end and how long it was held."""

    volts: float
    return_start_f: float
    return_end_f: float
    held_min: int


FAST_STEPS = [FastStep(8.0, 132.0, 155.0, 30), FastStep(6.0, 141.0, 152.0, 23)]


def calibration_kbtu_per_h() -> float:
    return BTU_PER_HR_PER_GPM_F * CALIBRATION.gpm * (CALIBRATION.source_f - CALIBRATION_RETURN_F) / 1000


def k() -> float:
    mean = (CALIBRATION.source_f + CALIBRATION_RETURN_F) / 2
    return calibration_kbtu_per_h() * 1000 / (mean - ROOM_F) ** EXPONENT


def iterate(gpm: float, source_f: float) -> list[float]:
    """The return after each iteration from the calibration return."""
    out = [CALIBRATION_RETURN_F]
    for _ in range(ITERATIONS):
        r = out[-1]
        out.append(source_f - k() * ((source_f + r) / 2 - ROOM_F) ** EXPONENT / (BTU_PER_HR_PER_GPM_F * gpm))
    return out


class TheoryRow(NamedTuple):
    gpm: float | None  # None is infinite flow
    source_f: float
    theory_return_f: float
    theory_drop_f: float
    theory_kbtu_per_h: float
    measured_kbtu_per_h: float | None


def theory_rows() -> list[TheoryRow]:
    rows = []
    for s in STEPS:
        r = iterate(s.gpm, s.source_f)[-1]
        rows.append(TheoryRow(s.gpm, s.source_f, r, s.source_f - r,
                              BTU_PER_HR_PER_GPM_F * s.gpm * (s.source_f - r) / 1000, s.measured_kbtu_per_h))
    s = CALIBRATION.source_f
    rows.append(TheoryRow(None, s, s, 0.0, k() * (s - ROOM_F) ** EXPONENT / 1000, None))
    return rows


class StoredRow(NamedTuple):
    volts: float
    return_start_f: float
    return_end_f: float
    measured_kbtu_per_h: float
    theory_kbtu_per_h: float
    excess_kbtu_per_h: float
    held_min: int
    stored_kbtu: float
    implied_mass_btu_per_f: float


def stored_rows() -> list[StoredRow]:
    theory = {s.volts: t for s, t in zip(STEPS, theory_rows())}
    out = []
    for f in FAST_STEPS:
        t = theory[f.volts]
        assert t.measured_kbtu_per_h is not None
        excess = t.measured_kbtu_per_h - t.theory_kbtu_per_h
        stored = excess * f.held_min / 60
        out.append(StoredRow(f.volts, f.return_start_f, f.return_end_f, t.measured_kbtu_per_h, t.theory_kbtu_per_h,
                             excess, f.held_min, stored, stored * 1000 / (f.return_end_f - f.return_start_f)))
    return out


THEORY_COLUMNS = ("Gpm", "SourceF", "TheoryReturnF", "TheoryDropF", "TheoryKbtuPerH", "MeasuredKbtuPerH")
STORED_COLUMNS = ("Volts", "ReturnStartF", "ReturnEndF", "MeasuredKbtuPerH", "TheoryKbtuPerH", "ExcessKbtuPerH",
                  "HeldMin", "StoredKbtu", "ImpliedMassBtuPerF")


def python_tables() -> list[Table]:
    return [
        Table("emitter-theory-python", "The paper's theory table computed in Python from the inputs on theory-inputs: "
              "the return each flow settles to under the emitter characteristic, the drop and heat that implies, against the measured heat",
              THEORY_COLUMNS,
              [("infinite" if t.gpm is None else t.gpm, t.source_f, round(t.theory_return_f, 1), round(t.theory_drop_f, 1),
                round(t.theory_kbtu_per_h, 1), t.measured_kbtu_per_h) for t in theory_rows()], "emitter_theory.py"),
        Table("stored-heat-python", "The two fast steps' excess of measured over theory heat as heat stored in the iron, "
              "and the thermal mass that rise in return implies, computed in Python",
              STORED_COLUMNS,
              [(r.volts, r.return_start_f, r.return_end_f, r.measured_kbtu_per_h, round(r.theory_kbtu_per_h, 1),
                round(r.excess_kbtu_per_h, 1), r.held_min, round(r.stored_kbtu, 1), round(r.implied_mass_btu_per_f))
               for r in stored_rows()], "emitter_theory.py"),
    ]


def excel_tables() -> list[Table]:
    """The same tables as live formulas. Cell addresses follow write_workbook's
    layout: headers in row 1, the first data row is row 2."""
    inp = f"'{INPUTS}'!$B$"
    room, n, btu, cal_gpm, cal_s, cal_r, cal_kbtu, kk = (inp + str(i) for i in range(2, 10))
    inputs = Table(INPUTS, "The inputs every formula on the excel tabs reads; change one and the tabs follow",
                   ("Input", "Value", "Unit"), [
                       ("RoomF", ROOM_F, "F"),
                       ("Exponent", EXPONENT, "n in output = K x (mean water - room)^n"),
                       ("BtuPerHPerGpmF", BTU_PER_HR_PER_GPM_F, "water side: 8.33 lb/gal x 60 min/h x 1 BTU/lb F"),
                       ("CalibrationGpm", CALIBRATION.gpm, "gpm, the 3.5 V step"),
                       ("CalibrationSourceF", CALIBRATION.source_f, "F"),
                       ("CalibrationReturnF", CALIBRATION_RETURN_F, "F"),
                       ("CalibrationKbtuPerH", f"={cal_gpm}*{btu}*({cal_s}-{cal_r})/1000", "kBTU/h, from the three above"),
                       ("K", f"={cal_kbtu}*1000/(({cal_s}+{cal_r})/2-{room})^{n}", "BTU/h per F^n, fixes the emitters"),
                   ], "emitter_theory.py")
    iters = tuple(f"Return{i}F" for i in range(ITERATIONS + 1))
    cols = ("Gpm", "SourceF", *iters, "TheoryReturnF", "TheoryDropF", "TheoryKbtuPerH", "MeasuredKbtuPerH")
    col = {name: chr(ord("A") + i) for i, name in enumerate(cols)}
    rows: list[tuple] = []
    for i, s in enumerate(STEPS):
        r = i + 2
        cells: list = [s.gpm, s.source_f, f"={cal_r}"]
        for j in range(1, ITERATIONS + 1):
            prev = f"{col[iters[j - 1]]}{r}"
            cells.append(f"=$B{r}-{kk}*(($B{r}+{prev})/2-{room})^{n}/({btu}*$A{r})")
        last = f"{col[iters[-1]]}{r}"
        cells += [f"={last}", f"=B{r}-{col['TheoryReturnF']}{r}",
                  f"={btu}*A{r}*{col['TheoryDropF']}{r}/1000", s.measured_kbtu_per_h]
        rows.append(tuple(cells))
    r = len(STEPS) + 2
    rows.append(("infinite", CALIBRATION.source_f, *([None] * (ITERATIONS + 1)), f"=B{r}", 0,
                 f"={kk}*(B{r}-{room})^{n}/1000", None))
    theory = Table("emitter-theory-excel", "The paper's theory table as formulas over theory-inputs: Return0F is the calibration return, "
                   "each ReturnNF one iteration of R = S - K x ((S + R)/2 - room)^n / (500 x gpm); the last is the theory return",
                   cols, rows, "emitter_theory.py")
    theory_row = {s.volts: i + 2 for i, s in enumerate(STEPS)}
    scol = {name: chr(ord("A") + i) for i, name in enumerate(STORED_COLUMNS)}
    srows = []
    for i, f in enumerate(FAST_STEPS):
        r, tr = i + 2, theory_row[f.volts]
        srows.append((f.volts, f.return_start_f, f.return_end_f,
                      f"='emitter-theory-excel'!{col['MeasuredKbtuPerH']}{tr}",
                      f"='emitter-theory-excel'!{col['TheoryKbtuPerH']}{tr}",
                      f"={scol['MeasuredKbtuPerH']}{r}-{scol['TheoryKbtuPerH']}{r}", f.held_min,
                      f"={scol['ExcessKbtuPerH']}{r}*{scol['HeldMin']}{r}/60",
                      f"={scol['StoredKbtu']}{r}*1000/({scol['ReturnEndF']}{r}-{scol['ReturnStartF']}{r})"))
    stored = Table("stored-heat-excel", "The two fast steps' stored heat and implied thermal mass as formulas over emitter-theory-excel",
                   STORED_COLUMNS, srows, "emitter_theory.py")
    return [inputs, theory, stored]


def tables() -> list[Table]:
    return python_tables() + excel_tables()


def main() -> None:
    print(f"K = {k():.1f} BTU/h per F^{EXPONENT}; calibration {calibration_kbtu_per_h():.1f} kBTU/h")
    print("gpm     source  return  drop  theory  measured")
    for t in theory_rows():
        g = "inf " if t.gpm is None else f"{t.gpm:4.2f}"
        m = "" if t.measured_kbtu_per_h is None else f"{t.measured_kbtu_per_h:5.0f}"
        print(f"{g}    {t.source_f:5.0f}   {t.theory_return_f:5.1f}  {t.theory_drop_f:4.1f}  {t.theory_kbtu_per_h:5.1f}  {m}")
    print("\nV    return     excess  held  stored  mass BTU/F")
    for r in stored_rows():
        print(f"{r.volts:3.0f}  {r.return_start_f:3.0f}->{r.return_end_f:3.0f}  {r.excess_kbtu_per_h:5.1f}  {r.held_min:3d}  "
              f"{r.stored_kbtu:5.1f}  {r.implied_mass_btu_per_f:5.0f}")


if __name__ == "__main__":
    main()
