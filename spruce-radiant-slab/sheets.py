#!/usr/bin/env python3
"""Build the spruce radiant slab workbook from the folder's sema instances.

The model is per zone and needs neither slab area nor thickness: a
floor-to-room conductance G (kW per °F of floor sensor minus room air)
and a floor heat capacity C (kWh per °F of floor sensor). Heat into the
floor is the hot-side BTU meter (flow times distribution supply minus
return) shared among the slab zones calling. The workbook states the
model in cells, puts each zone's measured floor and air temperatures
beside the heat in, predicts the floor temperature step by step, and
compares actual with predicted over any window. The garage is left out
for now: its columns are not written and its calls do not enter the
share rule.

Inputs, all sema instances in this folder: the `gw.nolan.layout` word
(which zones are radiant slabs, and each one's floor, air and heat-call
channels) and one `gw.readings` instance per window, decoded through
the vendored snapshot; readings go to natural units through each
channel word's own encoding.
Output: `spruce-radiant-slab.xlsx` in this folder (gitignored; this
script is the regenerator).

    uv run python sheets.py
"""

import datetime as dt
import gzip
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from pydantic import TypeAdapter

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE.parent))

from gwexp.sema.codec import SemaCodec  # noqa: E402
from gwexp.sema.enums import GwZoneEmitterType  # noqa: E402
from gwexp.sema.property_format import LeftRightDot, SpaceheatName  # noqa: E402
from gwexp.sema.types import DerivedChannelGt, GwNolanLayout, GwReadings  # noqa: E402
from naming import validate_lrd  # noqa: E402
from unit_encodings import to_display, word_encoding  # noqa: E402

SH = TypeAdapter(SpaceheatName)
SCADA = validate_lrd("hw1.isone.me.versant.keene.spruce.scada")
TA = validate_lrd("hw1.isone.me.versant.keene.spruce.ta")
ET = ZoneInfo("America/New_York")
STEP_MIN = 10
BTU_PER_KWH = 3412.14
FONT = "Arial"
BLUE = Font(name=FONT, color="0000FF")
BLACK = Font(name=FONT)
BOLD = Font(name=FONT, bold=True)
ITALIC = Font(name=FONT, italic=True)
YELLOW = PatternFill("solid", fgColor="FFFF00")

# The distribution loop's BTU meter and the heat pump's power, by the
# channel names gw.nolan.layout fixes (axiom "RequiredSensing"); each is
# looked up in the layout word, never assumed present.
DIST_SWT = SH.validate_python("dist-swt")
DIST_RWT = SH.validate_python("dist-rwt")
DIST_FLOW = SH.validate_python("dist-flow")
FLOOR_SWT = SH.validate_python("floor-swt")
FLOOR_RWT = SH.validate_python("floor-rwt")
HP_ODU_PWR = SH.validate_python("hp-odu-pwr")
# A derived channel with this Strategy on a circuit's whitewire channel is
# the circuit's heat call (gw.nolan.layout axiom "CircuitHeatCallChannel").
HEAT_CALL = SH.validate_python("heat-call")
# The slab zones modelled, in Model-sheet order; the garage waits for a
# window of its own. Each must be a RadiantSlab zone in the layout word.
MODELLED_ZONES = [SH.validate_python("living-rm"), SH.validate_python("bedrooms")]
FIT_ZONE = MODELLED_ZONES[0]


class Window(NamedTuple):
    """One pulled window: sheet name, the pull's condition field, the
    free-float span for the Calibration sheet and the fit span (ET,
    inclusive start, exclusive end), or None when the window has none."""

    sheet: str
    condition: LeftRightDot
    calib_start: str | None
    calib_end: str | None
    fit_start: str | None
    fit_end: str | None


WINDOWS = [
    Window("Oct", validate_lrd("first.heat.oct"), "2026-10-07 19:00", "2026-10-08 02:00",
           "2026-10-07 02:00", "2026-10-08 12:00"),
    Window("Sep", validate_lrd("first.heat.sep"), None, None, None, None),
]


class SlabZone(NamedTuple):
    """One radiant-slab zone as the layout word states it: the zone, the
    circuit serving it, and the three channels the fit reads. Built from
    gw.nolan.layout Hydronic.ZoneCallCircuits (EmitterType RadiantSlab);
    the label is the zone name for sheet headers."""

    zone: SpaceheatName
    label: str
    circuit: SpaceheatName
    floor: SpaceheatName
    air: SpaceheatName
    call: SpaceheatName


class OtherCall(NamedTuple):
    """A circuit that is not a modelled slab: its heat call (so slab-only
    hours can be told apart) and its air channel when it has one."""

    circuit: SpaceheatName
    label: str
    call: SpaceheatName
    air: SpaceheatName | None


class SlabFit(NamedTuple):
    """The fitted pair for one slab zone. No sema word states a slab
    zone's floor-to-room conductance and heat capacity yet; the word
    that retires this record is a per-zone slab parameter beside
    gw1.hvac.zone KwhPerDegF, the room-side analogue."""

    zone: SpaceheatName
    g_kw_per_f: float
    c_kwh_per_f: float


class Roles(NamedTuple):
    """What the layout word says about the house for this fit: the
    modelled slab zones in Model-sheet order and every other circuit's
    call."""

    slabs: list[SlabZone]
    others: list[OtherCall]

    def by_zone(self, zone: SpaceheatName) -> SlabZone:
        return next(s for s in self.slabs if s.zone == zone)


def load_roles(codec: SemaCodec) -> Roles:
    """The folder's gw.nolan.layout instance, reduced to the channels the
    fit reads. Every name is looked up in the word; a zone the layout
    does not declare as a radiant slab, or a channel the layout does not
    have, is an error here, not a blank column later."""
    path = HERE / f"{SCADA}-gw.nolan.layout-000.json"
    layout = codec.from_dict(json.loads(path.read_text()), expect=GwNolanLayout)
    names = {c.name for c in layout.data_channels} | {c.name for c in layout.derived_channels}
    for n in (DIST_SWT, DIST_RWT, DIST_FLOW, FLOOR_SWT, FLOOR_RWT, HP_ODU_PWR):
        assert n in names, f"{n} is not a channel in the layout word"
    calls: dict[SpaceheatName, SpaceheatName] = {}
    for d in layout.derived_channels:
        assert isinstance(d, DerivedChannelGt)
        if d.strategy == HEAT_CALL:
            (whitewire,) = d.input_channel_names
            calls[whitewire] = d.name
    slabs: list[SlabZone] = []
    others: list[OtherCall] = []
    for c in layout.hydronic.zone_call_circuits:
        label = c.name.replace("-", " ")
        if c.emitter_type == GwZoneEmitterType.RadiantSlab and c.serves_zone in MODELLED_ZONES:
            assert c.floor_temp_channel_name is not None and c.temp_channel_name is not None, c.name
            slabs.append(SlabZone(c.serves_zone, c.serves_zone.replace("-", " "), c.name,
                                  c.floor_temp_channel_name, c.temp_channel_name, calls[c.whitewire_channel_name]))
        elif c.emitter_type == GwZoneEmitterType.FanCoil:
            if "fancoil" not in c.name:
                label += " (fan coil)"
            others.append(OtherCall(c.name, label, calls[c.whitewire_channel_name], c.temp_channel_name))
    slabs.sort(key=lambda s: MODELLED_ZONES.index(s.zone))
    assert [s.zone for s in slabs] == MODELLED_ZONES, "a modelled zone is not a RadiantSlab circuit in the layout"
    return Roles(slabs, others)


def columns(roles: Roles) -> dict[SpaceheatName, str]:
    """Channel -> workbook column header, in sheet order."""
    cols: dict[SpaceheatName, str] = {
        DIST_SWT: "dist supply F", DIST_RWT: "dist return F", DIST_FLOW: "hot flow gpm",
        FLOOR_SWT: "floor supply F", FLOOR_RWT: "floor return F",
    }
    for s in sorted(roles.slabs, key=lambda s: s.circuit):
        cols[s.call] = f"call {s.label}"
    for o in roles.others:
        cols[o.call] = f"call {o.label}"
    for s in roles.slabs:
        cols[s.floor] = f"{s.label} floor F (actual)"
        cols[s.air] = f"{s.label} air F"
    for o in roles.others:
        if o.air is not None and o.air not in cols:
            cols[o.air] = f"{o.label.removesuffix(' (fan coil)')} air F"
    cols[HP_ODU_PWR] = "heat pump W"
    return cols


class Grid(NamedTuple):
    """The window on a STEP_MIN grid: bin start times (ET, naive) and, per
    channel, one value per bin (nan where nothing was read)."""

    times: list[dt.datetime]
    cols: dict[SpaceheatName, list[float]]

    def loc(self, start: str, end: str) -> "Grid":
        a, b = dt.datetime.fromisoformat(start), dt.datetime.fromisoformat(end)
        idx = [i for i, t in enumerate(self.times) if a <= t < b]
        return Grid([self.times[i] for i in idx], {c: [v[i] for i in idx] for c, v in self.cols.items()})


def load_grid(codec: SemaCodec, condition: LeftRightDot, wanted: list[SpaceheatName]) -> Grid:
    """The window's gw.readings instance reduced to a STEP_MIN grid: each
    channel's readings in natural units by its own word's encoding, bin
    means, then gaps forward-filled up to an hour so the step formulas
    never hit a blank. Heat calls are means over the bin (fraction of
    the bin calling)."""
    path = HERE / f"{TA}-{condition}-gw.readings-000.json.gz"
    pull = codec.from_dict(json.loads(gzip.decompress(path.read_bytes())), expect=GwReadings)
    words = {c.name: c for c in pull.channels}
    sums: dict[tuple[dt.datetime, SpaceheatName], list[float]] = defaultdict(list)
    for cr in pull.channel_readings_list:
        if cr.channel_name not in wanted:
            continue
        encoding = word_encoding(words[cr.channel_name])
        for t_ms, raw in zip(cr.scada_read_time_unix_ms_list, cr.value_list):
            t = dt.datetime.fromtimestamp(t_ms / 1000, tz=ET).replace(tzinfo=None)
            b = t.replace(minute=t.minute - t.minute % STEP_MIN, second=0, microsecond=0)
            value, _unit = to_display(raw, encoding)
            sums[(b, cr.channel_name)].append(value)
    t0 = min(b for b, _ in sums)
    t1 = max(b for b, _ in sums)
    times = []
    t = t0
    while t <= t1:
        times.append(t)
        t += dt.timedelta(minutes=STEP_MIN)
    cols: dict[SpaceheatName, list[float]] = {}
    for ch in wanted:
        vals = []
        last, age = math.nan, 99
        for b in times:
            xs = sums.get((b, ch))
            v = sum(xs) / len(xs) if xs else math.nan
            if ch == DIST_FLOW and v > 15:  # the flow meter's occasional nonsense spikes
                v = math.nan
            if math.isnan(v):
                age += 1
                v = last if age <= 60 // STEP_MIN else math.nan
            else:
                last, age = v, 0
            vals.append(v)
        cols[ch] = vals
    return Grid(times, cols)


def nz(v: float) -> float:
    return 0.0 if math.isnan(v) else v


def simulate(grid: Grid, roles: Roles, zone: SpaceheatName, g_kw_per_f: float, c_kwh_per_f: float) -> list[float]:
    """The same recursion the sheet runs for one zone, for the fit."""
    step_h = STEP_MIN / 60
    g = grid.cols
    s = roles.by_zone(zone)
    actual = g[s.floor]
    air = g[s.air]
    seeds = [v for v in actual if not math.isnan(v)] or [v for v in air if not math.isnan(v)]
    t = seeds[0]
    pred = []
    for i in range(len(grid.times)):
        pred.append(t)
        q_in_kwh = 500 * nz(g[DIST_FLOW][i]) * nz(g[DIST_SWT][i] - g[DIST_RWT][i]) * step_h / BTU_PER_KWH
        calls = {z.zone: nz(g[z.call][i]) >= 0.5 for z in roles.slabs}
        share = (1 / max(1, sum(calls.values()))) if calls[zone] else 0.0
        a = air[i] if not math.isnan(air[i]) else t
        t = t + (q_in_kwh * share - g_kw_per_f * (t - a) * step_h) / c_kwh_per_f
    return pred


def sse_of(grid: Grid, roles: Roles, zone: SpaceheatName, gk: float, ck: float) -> float:
    pred = simulate(grid, roles, zone, gk, ck)
    actual = grid.cols[roles.by_zone(zone).floor]
    return sum((p - a) ** 2 for p, a in zip(pred, actual) if not math.isnan(a))


def fit_zone(grid: Grid, roles: Roles, zone: SpaceheatName, start: str, end: str) -> tuple[SlabFit, list[tuple[float, float, float]]]:
    """Joint grid search on G and C over a span with both a metered
    single-zone charge (fixes C) and a free float (fixes G over C); the
    prediction is re-seeded at the span's first actual. Returns the fit
    and its profile: the best G and RMS at each C, to show how sharply C
    is determined."""
    span = grid.loc(start, end)
    n = sum(1 for a in span.cols[roles.by_zone(zone).floor] if not math.isnan(a))
    profile = []
    best = (math.inf, 0.0, 0.0)
    for c10 in range(5, 61, 2):
        ck = c10 / 10
        best_c = (math.inf, 0.0)
        for g1000 in range(20, 801, 5):
            gk = g1000 / 1000
            sse = sse_of(span, roles, zone, gk, ck)
            if sse < best_c[0]:
                best_c = (sse, gk)
        profile.append((ck, best_c[1], math.sqrt(best_c[0] / n)))
        if best_c[0] < best[0]:
            best = (best_c[0], best_c[1], ck)
    return SlabFit(zone, best[1], best[2]), profile


def model_sheet(wb: Workbook, roles: Roles, fit: SlabFit) -> dict[str, dict[str, str]]:
    """Per-zone inputs (blue) and a per-square-foot translation; returns
    zone -> {g, c} absolute refs plus the shared step and kWh refs."""
    ws = wb.active
    assert ws is not None
    ws.title = "Model"
    ws.column_dimensions["A"].width = 50
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 70
    ws["A1"] = "Spruce radiant slabs: a two-lump model per zone"
    ws["A1"].font = BOLD
    ws["A2"] = ("Each slab zone is a floor lump at its floor sensor (in PEX at tubing depth) and a room lump at "
                "its zone air sensor. Heat floor to room = G x (floor - air). Floor heat content = C x floor "
                "temperature. Heat in = the hot-side BTU meter before the mixing valve, flow x (dist supply - "
                "dist return) x 500 BTU/h per gpm per F, shared 1/n among the slab zones calling. Neither slab "
                "area nor thickness enters; both only translate G and C to per-square-foot numbers below.")
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells("A2:D2")
    ws.row_dimensions[2].height = 80
    ws["A3"] = "Blue cells are inputs; yellow are the fitted coefficients. Everything else is a formula."
    ws["A5"] = "Per-zone coefficients"
    ws["A5"].font = BOLD
    for j, s in enumerate(roles.slabs):
        ws.cell(row=5, column=2 + j, value=s.label).font = BOLD
    ws["A6"] = "G floor to room (kW per F of floor minus air)"
    ws["A7"] = "C floor heat capacity (kWh per F of floor sensor)"
    ws["A8"] = "G (BTU/h per F)"
    ws["A9"] = "C (BTU per F)"
    refs: dict[str, dict[str, str]] = {}
    for j, s in enumerate(roles.slabs):
        col = get_column_letter(2 + j)
        ws[f"{col}6"], ws[f"{col}7"] = fit.g_kw_per_f, fit.c_kwh_per_f
        if s.zone == fit.zone:
            ws[f"{col}6"].fill = YELLOW
            ws[f"{col}7"].fill = YELLOW
            ws[f"{col}6"].comment = Comment("Fitted jointly with C by least squares over Oct 7 02:00 to Oct 8 12:00: the living room charging alone, then the free float (sheets.py; the Fit sheet has the profile)", "sheets.py")
        else:
            ws[f"{col}6"].comment = Comment("Not yet fitted: no window with the bedrooms charging alone. The living room's values stand in", "sheets.py")
        for r in (6, 7):
            ws[f"{col}{r}"].font = BLUE
            ws[f"{col}{r}"].number_format = "0.000"
        ws[f"{col}8"] = f"={col}6*$B$14"
        ws[f"{col}9"] = f"={col}7*$B$14"
        ws[f"{col}8"].number_format = "#,##0"
        ws[f"{col}9"].number_format = "#,##0"
        refs[s.zone] = {"g": f"Model!${col}$6", "c": f"Model!${col}$7"}
    ws["A12"] = "Shared"
    ws["A12"].font = BOLD
    ws["A13"], ws["B13"] = "Step (hours)", STEP_MIN / 60
    ws["A14"], ws["B14"] = "BTU per kWh", BTU_PER_KWH
    ws["D13"] = "Rows are 10-minute bin means of the journal readings"
    for a in ("B13", "B14"):
        ws[a].font = BLUE
    ws["A17"] = "Translation to per square foot (reference only; assumptions in blue)"
    ws["A17"].font = BOLD
    ws["A18"], ws["B18"], ws["D18"] = "Assumed living rm slab area (sq ft)", 650, "Paced out 2026-10-15"
    ws["A19"], ws["B19"], ws["D19"] = "Concrete density (lb per cu ft)", 149.5, "From the whiteboard model"
    ws["A20"], ws["B20"], ws["D20"] = "Concrete specific heat (kWh per lb per F)", 0.0000631, "From the whiteboard model"
    for a in ("B18", "B19", "B20"):
        ws[a].font = BLUE
    ws["B20"].number_format = "0.0000000"
    ws["A21"], ws["B21"] = "U floor to room at that area (BTU/h per sq ft per F)", "=B8/B18"
    ws["A22"], ws["B22"] = "Participating concrete at that area (inches)", "=B7/(B18*B19*B20)*12"
    ws["D22"] = "The thickness whose heat content is C; a thicker pour whose lower part does not take part on a one-day timescale reads the same"
    ws["B21"].number_format = "0.00"
    ws["B22"].number_format = "0.0"
    for r in range(13, 23):
        if ws[f"D{r}"].value:
            ws[f"D{r}"].font = ITALIC
    refs["shared"] = {"step": "Model!$B$13", "kwh": "Model!$B$14"}
    return refs


def headers(roles: Roles, cols: dict[SpaceheatName, str]) -> list[str]:
    """Sheet columns in order: the loop, the calls, each slab zone's
    block, the free-float flag, then the other air and power columns."""
    hs = ["time (ET)", cols[DIST_SWT], cols[DIST_RWT], cols[DIST_FLOW],
          "heat in kW", "heat in kWh (step)", "heat in kWh (cum)", "heat in BTU/h",
          cols[FLOOR_SWT], cols[FLOOR_RWT]]
    hs += [cols[s.call] for s in sorted(roles.slabs, key=lambda s: s.circuit)]
    hs += [cols[o.call] for o in roles.others]
    hs.append("slab zones calling")
    for s in roles.slabs:
        hs += [f"{s.label} share", f"{s.label} heat in kWh (step)", f"{s.label} heat in kWh (cum)",
               cols[s.floor], cols[s.air], f"{s.label} floor F (predicted)",
               f"{s.label} heat to room kW (predicted)", f"{s.label} predicted minus actual F"]
    hs.append("free float (no heat in, no slab call)")
    hs += [h for ch, h in cols.items() if h not in hs]
    return hs


def window_sheet(wb: Workbook, w: Window, grid: Grid, roles: Roles, cols: dict[SpaceheatName, str],
                 refs: dict[str, dict[str, str]]) -> dict[str, str]:
    """One sheet per window; returns header -> column letter."""
    hs = headers(roles, cols)
    col = {h: get_column_letter(i + 1) for i, h in enumerate(hs)}
    ws = wb.create_sheet(w.sheet)
    for j, h in enumerate(hs, start=1):
        c = ws.cell(row=1, column=j, value=h)
        c.font = BOLD
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.column_dimensions[get_column_letter(j)].width = 13
    ws.column_dimensions["A"].width = 17
    ws.row_dimensions[1].height = 58
    ws.freeze_panes = "B2"
    n = len(grid.times)
    step, kwh = refs["shared"]["step"], refs["shared"]["kwh"]
    first_actual = {s.zone: next((i for i, v in enumerate(grid.cols[s.floor]) if not math.isnan(v)), None) for s in roles.slabs}
    for k, ts in enumerate(grid.times):
        r = k + 2
        C = lambda h: f"{col[h]}{r}"  # noqa: E731
        P = lambda h: f"{col[h]}{r - 1}"  # noqa: E731

        def put(h, v, fmt=None, font=BLACK):
            cell = ws[C(h)]
            cell.value = None if (isinstance(v, float) and math.isnan(v)) else v
            cell.font = font
            if fmt:
                cell.number_format = fmt
        put("time (ET)", ts, "yyyy-mm-dd hh:mm")
        for ch, h in cols.items():
            put(h, grid.cols[ch][k], "0.00" if "call" in h else "0.0", BLUE)
        put("heat in BTU/h", f"=IF(OR({C(cols[DIST_FLOW])}=\"\",{C(cols[DIST_SWT])}=\"\",{C(cols[DIST_RWT])}=\"\"),0,500*{C(cols[DIST_FLOW])}*({C(cols[DIST_SWT])}-{C(cols[DIST_RWT])}))", "#,##0")
        put("heat in kW", f"={C('heat in BTU/h')}/{kwh}", "0.00")
        put("heat in kWh (step)", f"={C('heat in kW')}*{step}", "0.000")
        put("heat in kWh (cum)", f"={C('heat in kWh (step)')}" if r == 2 else f"={P('heat in kWh (cum)')}+{C('heat in kWh (step)')}", "0.00")
        put("slab zones calling", "=" + "+".join(f"({C(cols[s.call])}>=0.5)" for s in roles.slabs), "0")
        for s in roles.slabs:
            label = s.label
            g, c = refs[s.zone]["g"], refs[s.zone]["c"]
            share, qin, qcum = f"{label} share", f"{label} heat in kWh (step)", f"{label} heat in kWh (cum)"
            act, air, pred = cols[s.floor], cols[s.air], f"{label} floor F (predicted)"
            put(share, f"=IF({C(cols[s.call])}>=0.5,1/MAX(1,{C('slab zones calling')}),0)", "0.00")
            put(qin, f"={C('heat in kWh (step)')}*{C(share)}", "0.000")
            put(qcum, f"={C(qin)}" if r == 2 else f"={P(qcum)}+{C(qin)}", "0.00")
            if r == 2:
                fa = first_actual[s.zone]
                put(pred, f"={col[act]}{2 + fa}" if fa is not None else f"={C(air)}", "0.00")
                ws[C(pred)].comment = Comment("Seed: the first actual floor reading in the window"
                                              + ("" if fa is not None else " (none: seeded from the air temperature, so this prediction is only a shape)"), "sheets.py")
            else:
                air_prev = f"IF({P(air)}=\"\",{P(pred)},{P(air)})"
                put(pred, f"={P(pred)}+({P(qin)}-{g}*({P(pred)}-{air_prev})*{step})/{c}", "0.00")
            put(f"{label} heat to room kW (predicted)", f"=IF({C(air)}=\"\",\"\",{g}*({C(pred)}-{C(air)}))", "0.00")
            put(f"{label} predicted minus actual F", f"=IF({C(act)}=\"\",\"\",{C(pred)}-{C(act)})", "0.00")
        put("free float (no heat in, no slab call)", f"=IF(AND({C('heat in kWh (step)')}<0.015,{C('slab zones calling')}=0),1,0)", "0")
    ws.auto_filter.ref = f"A1:{get_column_letter(len(hs))}{n + 1}"
    return col


def calibration_sheet(wb: Workbook, w: Window, roles: Roles, cols: dict[SpaceheatName, str],
                      col: dict[str, str], refs: dict[str, dict[str, str]]) -> None:
    assert w.calib_start and w.calib_end
    s = roles.by_zone(FIT_ZONE)
    ws = wb.create_sheet("Calibration")
    ws.column_dimensions["A"].width = 56
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 62
    sheet = w.sheet
    last = wb[sheet].max_row
    rng = lambda h: f"{sheet}!${col[h]}$2:${col[h]}${last}"  # noqa: E731
    fl, air = rng(cols[s.floor]), rng(cols[s.air])
    pred, ff, qin = rng(f"{s.label} floor F (predicted)"), rng("free float (no heat in, no slab call)"), rng(f"{s.label} heat in kWh (step)")
    tm = f"{sheet}!$A$2:$A${last}"
    g, c = refs[FIT_ZONE]["g"], refs[FIT_ZONE]["c"]
    rows = [
        (f"Calibration catch: the Oct 7 night free float, {s.label}", None, None, BOLD),
        ("No heat into the slab and no slab zone calling, so the floor's fall is heat leaving it: "
         "G = C x (floor drop per hour) / mean(floor - air). This fixes only G/C; the Fit sheet's "
         "joint fit over the charge as well is what separates them.", None, None, BLACK),
        ("Start (ET)", dt.datetime.fromisoformat(w.calib_start), "Inputs: move the span and the numbers below follow", BLUE),
        ("End (ET, exclusive)", dt.datetime.fromisoformat(w.calib_end), None, BLUE),
        ("Hours in span", "=(B4-B3)*24", None, BLACK),
        ("Floor F at start", f"=INDEX({fl},MATCH(B3,{tm},0))", None, BLACK),
        ("Floor F at end", f"=INDEX({fl},MATCH(B4,{tm},0))", None, BLACK),
        ("Mean (floor - air) F over span", f"=AVERAGEIFS({fl},{tm},\">=\"&B3,{tm},\"<\"&B4)-AVERAGEIFS({air},{tm},\">=\"&B3,{tm},\"<\"&B4)", None, BLACK),
        ("G from the decay at the Model's C (kW per F)", f"={c}*(B6-B7)/B5/B8", f"Hand check of the {s.label} G on Model", BLACK),
        (f"Heat into the {s.label} slab over span (kWh)", f"=SUMIFS({qin},{tm},\">=\"&B3,{tm},\"<\"&B4)", "Should be near zero for a clean free float", BLACK),
        ("Heat from slab to room over span (kWh)", f"={c}*(B6-B7)", "What the slab gave the room overnight", BLACK),
        (None, None, None, BLACK),
        (f"Fit quality with the current Model inputs, {s.label}", None, None, BOLD),
        ("RMS (predicted - actual) F, free-float rows", f"=SQRT(SUMPRODUCT(({ff}=1)*({fl}<>\"\")*({pred}-{fl})^2)/MAX(1,SUMPRODUCT(({ff}=1)*({fl}<>\"\"))))", "Over the whole Oct sheet, prediction run continuously from its first row", BLACK),
        ("RMS (predicted - actual) F, all rows with an actual", f"=SQRT(SUMPRODUCT(({fl}<>\"\")*({pred}-{fl})^2)/MAX(1,SUMPRODUCT(({fl}<>\"\")*1)))", "Includes the Oct 6 evening when both slabs charged and the 1/n share rule decides the split", BLACK),
    ]
    for i, (a, b, cmt, font) in enumerate(rows, start=1):
        ws.cell(row=i, column=1, value=a).font = font
        if b is not None:
            cell = ws.cell(row=i, column=2, value=b)
            cell.font = font if not isinstance(b, str) else BLACK
            if isinstance(b, dt.datetime):
                cell.number_format = "yyyy-mm-dd hh:mm"
        if cmt:
            ws.cell(row=i, column=3, value=cmt).font = ITALIC
    for addr in ("B5", "B6", "B7", "B8", "B10", "B11", "B14", "B15"):
        ws[addr].number_format = "0.00"
    ws["B9"].number_format = "0.000"
    ws["B9"].fill = YELLOW


def fit_sheet(wb: Workbook, w: Window, roles: Roles, profile: list[tuple[float, float, float]]) -> None:
    s = roles.by_zone(FIT_ZONE)
    ws = wb.create_sheet("Fit")
    for c, width in (("A", 26), ("B", 30), ("C", 28)):
        ws.column_dimensions[c].width = width
    ws["A1"] = f"Joint fit of G and C, {s.label}"
    ws["A1"].font = BOLD
    ws["A2"] = (f"Span {w.fit_start} to {w.fit_end} ET: the {s.label} charging alone, then the free float. "
                "For each C, the best G and the RMS of predicted minus actual floor F over the span (prediction "
                "re-seeded at the span's first reading). The lowest RMS is the fit; how fast the RMS rises either "
                "side is how well the data pin C. Values from sheets.py.")
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells("A2:C2")
    ws.row_dimensions[2].height = 75
    for j, h in enumerate(("C (kWh per F)", "best G (kW per F)", "RMS predicted - actual (F)"), start=1):
        ws.cell(row=4, column=j, value=h).font = BOLD
    for i, (ck, gk, rms) in enumerate(profile, start=5):
        ws.cell(row=i, column=1, value=ck).font = BLUE
        ws.cell(row=i, column=2, value=gk).font = BLUE
        ws.cell(row=i, column=3, value=round(rms, 3)).font = BLUE
    best = min(profile, key=lambda p: p[2])
    ws.cell(row=5 + profile.index(best), column=3).fill = YELLOW


def main() -> None:
    codec = SemaCodec()
    roles = load_roles(codec)
    cols = columns(roles)
    wanted = list(cols)
    grids = {w.sheet: load_grid(codec, w.condition, wanted) for w in WINDOWS}
    cal = WINDOWS[0]
    assert cal.fit_start and cal.fit_end
    fit, profile = fit_zone(grids[cal.sheet], roles, FIT_ZONE, cal.fit_start, cal.fit_end)
    print(f"{roles.by_zone(FIT_ZONE).label} joint fit over {cal.fit_start} to {cal.fit_end}: "
          f"G = {fit.g_kw_per_f:.3f} kW/F, C = {fit.c_kwh_per_f:.1f} kWh/F")
    for c_, g_, rms in profile:
        print(f"  C {c_:4.1f}  G {g_:.3f}  RMS {rms:.3f}")
    wb = Workbook()
    refs = model_sheet(wb, roles, fit)
    col: dict[str, str] = {}
    for w in WINDOWS:
        col = window_sheet(wb, w, grids[w.sheet], roles, cols, refs)
    calibration_sheet(wb, cal, roles, cols, col, refs)
    fit_sheet(wb, cal, roles, profile)
    out = HERE / "spruce-radiant-slab.xlsx"
    wb.save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
