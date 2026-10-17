#!/usr/bin/env python3
"""Build the spruce radiant slab workbook from the folder's sema instances.

The model is per zone and needs neither slab area nor thickness: a
floor-to-room conductance G (kW per °F of floor sensor minus room air)
and a floor heat capacity C (kWh per °F of floor sensor). Heat into the
floor is the hot-side BTU meter (flow times distribution supply minus
return) shared among the slab zones calling. The workbook states the
model in cells, puts each zone's measured floor and air temperatures
beside the heat in, predicts the floor temperature step by step, and
compares actual with predicted over any window. G and C are fitted in
two stages, each a least-squares slope through the origin: the free
float (no heat in, no slab zone and no fan coil calling) gives G over C
from the floor's fall against floor minus air; the charge gives C from
the metered heat in against the floor's rise plus what left for the
room at that ratio. The garage is left out for now: its columns are not
written and its calls do not enter the share rule.

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
    charge span (one slab zone charging alone, through its settle) and
    the free-float span that follows (ET, inclusive start, exclusive
    end), or None when the window has neither."""

    sheet: str
    condition: LeftRightDot
    charge_start: str | None
    charge_end: str | None
    float_start: str | None
    float_end: str | None


WINDOWS = [
    Window("Oct", validate_lrd("first.heat.oct"), "2026-10-07 02:00", "2026-10-07 19:00",
           "2026-10-07 19:00", "2026-10-08 02:00"),
    Window("Sep", validate_lrd("first.heat.sep"), None, None, None, None),
]
FREE_FLOAT_KWH = 0.015  # heat in per step below this counts as none


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


class StageRow(NamedTuple):
    """One row of a least-squares stage: the bin, its regressor x and
    its response y; the stage's slope is sum(xy) over sum(xx)."""

    time: dt.datetime
    x: float
    y: float


class TwoStageFit(NamedTuple):
    """How a SlabFit was reached. Stage 1, over the free float: x is
    floor minus air (F), y the floor's fall per hour (F/h); the slope is
    G over C (per hour). Stage 2, over the charge: x is the floor's rise
    since the span start plus (G over C) times the accumulated floor
    minus air hours, y the accumulated heat in to the zone (kWh); the
    slope is C. G is the product. The RMS is predicted minus actual
    floor F over charge and float together, re-seeded at the span's
    first reading."""

    fit: SlabFit
    g_over_c_per_h: float
    stage1: list[StageRow]
    stage2: list[StageRow]
    rms_f: float


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


def slope(rows: list[StageRow]) -> float:
    """Least squares through the origin."""
    return sum(r.x * r.y for r in rows) / sum(r.x * r.x for r in rows)


def heat_in_kwh(grid: Grid, i: int) -> float:
    step_h = STEP_MIN / 60
    g = grid.cols
    return 500 * nz(g[DIST_FLOW][i]) * nz(g[DIST_SWT][i] - g[DIST_RWT][i]) * step_h / BTU_PER_KWH


def calling(grid: Grid, chans: list[SpaceheatName], i: int) -> int:
    return sum(nz(grid.cols[ch][i]) >= 0.5 for ch in chans)


def fit_two_stage(grid: Grid, roles: Roles, zone: SpaceheatName, w: Window) -> TwoStageFit:
    """The two-stage least-squares fit of G and C for one zone; see
    TwoStageFit. The free float is taken row by row: a row with heat in,
    a slab zone calling or a fan coil calling is left out of stage 1.
    The charge span must have no fan coil calling, because the 1/n share
    of the metered heat among the slab zones calling does not know what
    a fan coil took."""
    assert w.charge_start and w.charge_end and w.float_start and w.float_end
    step_h = STEP_MIN / 60
    s = roles.by_zone(zone)
    slab_calls = [z.call for z in roles.slabs]
    fan_calls = [o.call for o in roles.others]
    fl = grid.loc(w.float_start, w.float_end)
    stage1: list[StageRow] = []
    for i in range(len(fl.times) - 1):
        t0, t1, a = fl.cols[s.floor][i], fl.cols[s.floor][i + 1], fl.cols[s.air][i]
        if any(math.isnan(v) for v in (t0, t1, a)):
            continue
        if heat_in_kwh(fl, i) >= FREE_FLOAT_KWH or calling(fl, slab_calls, i) or calling(fl, fan_calls, i):
            continue
        stage1.append(StageRow(fl.times[i], t0 - a, -(t1 - t0) / step_h))
    k = slope(stage1)
    ch = grid.loc(w.charge_start, w.charge_end)
    assert not any(calling(ch, fan_calls, i) for i in range(len(ch.times))), "a fan coil called during the charge span"
    first = next(i for i, v in enumerate(ch.cols[s.floor]) if not math.isnan(v))
    t_start = ch.cols[s.floor][first]
    loss_fh, q_kwh = 0.0, 0.0
    stage2: list[StageRow] = []
    for i in range(first, len(ch.times)):
        t, a = ch.cols[s.floor][i], ch.cols[s.air][i]
        n = calling(ch, slab_calls, i)
        share = (1 / n) if (n and nz(ch.cols[s.call][i]) >= 0.5) else 0.0
        if not math.isnan(t):
            stage2.append(StageRow(ch.times[i], (t - t_start) + k * loss_fh, q_kwh))
        q_kwh += heat_in_kwh(ch, i) * share
        if not (math.isnan(t) or math.isnan(a)):
            loss_fh += (t - a) * step_h
    c = slope(stage2)
    fit = SlabFit(zone, k * c, c)
    span = grid.loc(w.charge_start, w.float_end)
    pred = simulate(span, roles, zone, fit.g_kw_per_f, fit.c_kwh_per_f)
    pairs = [(p, a) for p, a in zip(pred, span.cols[s.floor]) if not math.isnan(a)]
    rms = math.sqrt(sum((p - a) ** 2 for p, a in pairs) / len(pairs))
    return TwoStageFit(fit, k, stage1, stage2, rms)


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
                "area nor thickness enters.")
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
            ws[f"{col}6"].comment = Comment("Fitted in two stages (sheets.py; the Fit sheet has both): G over C from the Oct 7 night free float, C from the Oct 7 charge", "sheets.py")
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
    hs += ["slab zones calling", "fan coils calling"]
    for s in roles.slabs:
        hs += [f"{s.label} share", f"{s.label} heat in kWh (step)", f"{s.label} heat in kWh (cum)",
               cols[s.floor], cols[s.air], f"{s.label} floor F (predicted)",
               f"{s.label} heat to room kW (predicted)", f"{s.label} predicted minus actual F"]
    hs.append("free float (no heat in, no slab or fan coil call)")
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
        put("fan coils calling", "=" + "+".join(f"({C(cols[o.call])}>=0.5)" for o in roles.others), "0")
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
        put("free float (no heat in, no slab or fan coil call)", f"=IF(AND({C('heat in kWh (step)')}<{FREE_FLOAT_KWH},{C('slab zones calling')}=0,{C('fan coils calling')}=0),1,0)", "0")
    ws.auto_filter.ref = f"A1:{get_column_letter(len(hs))}{n + 1}"
    return col


def fit_sheet(wb: Workbook, w: Window, roles: Roles, cols: dict[SpaceheatName, str],
              col: dict[str, str], two: TwoStageFit) -> None:
    """Both stages as tables with their slopes computed in cells, then
    the fit quality against the window sheet."""
    s = roles.by_zone(two.fit.zone)
    ws = wb.create_sheet("Fit")
    for c, width in (("A", 60), ("B", 24), ("C", 26), ("E", 20), ("F", 30), ("G", 28)):
        ws.column_dimensions[c].width = width
    ws["A1"] = f"Two-stage least-squares fit of G and C, {s.label}"
    ws["A1"].font = BOLD
    ws["A2"] = (f"Stage 1, the free float {w.float_start} to {w.float_end} ET, rows with no heat in, no slab zone and no "
                "fan coil calling: the floor's fall per hour against floor minus air; the slope through the origin is "
                f"G over C (per hour). Stage 2, the charge {w.charge_start} to {w.charge_end} ET: the heat in to the zone, "
                "accumulated, against the floor's rise since the start plus G over C times the accumulated floor-minus-air "
                "hours; the slope is C. G is the product. Rows are from the window sheet; slopes are formulas.")
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells("A2:G2")
    ws.row_dimensions[2].height = 90
    tables = (("A", "Stage 1: free float", "floor minus air (F)", "floor fall (F per hour)", two.stage1),
              ("E", "Stage 2: charge", "rise + (G/C) x loss hours (F)", "heat in to zone (kWh)", two.stage2))
    n: dict[str, int] = {}
    for c0, title, xh, yh, rows in tables:
        c1, c2 = get_column_letter(ord(c0) - 64 + 1), get_column_letter(ord(c0) - 64 + 2)
        ws[f"{c0}4"] = title
        ws[f"{c0}4"].font = BOLD
        for cc, h in ((c0, "time (ET)"), (c1, xh), (c2, yh)):
            ws[f"{cc}5"] = h
            ws[f"{cc}5"].font = BOLD
        for i, r in enumerate(rows, start=6):
            ws[f"{c0}{i}"] = r.time
            ws[f"{c0}{i}"].number_format = "yyyy-mm-dd hh:mm"
            ws[f"{c1}{i}"], ws[f"{c2}{i}"] = r.x, r.y
            for cc in (c1, c2):
                ws[f"{cc}{i}"].font = BLUE
                ws[f"{cc}{i}"].number_format = "0.000"
        n[c0] = len(rows)

    def rng(c0: str, off: int) -> str:
        cc = get_column_letter(ord(c0) - 64 + off)
        return f"${cc}$6:${cc}${5 + n[c0]}"

    r1 = 6 + max(n.values()) + 1
    ws[f"A{r1}"], ws[f"B{r1}"] = "G over C (per hour) = sum(xy) / sum(xx)", f"=SUMPRODUCT({rng('A', 1)},{rng('A', 2)})/SUMSQ({rng('A', 1)})"
    ws[f"A{r1 + 1}"], ws[f"B{r1 + 1}"] = "rows", n["A"]
    ws[f"E{r1}"], ws[f"F{r1}"] = "C (kWh per F) = sum(xy) / sum(xx)", f"=SUMPRODUCT({rng('E', 1)},{rng('E', 2)})/SUMSQ({rng('E', 1)})"
    ws[f"E{r1 + 1}"], ws[f"F{r1 + 1}"] = "G (kW per F) = (G over C) x C", f"=B{r1}*F{r1}"
    for a in (f"B{r1}", f"F{r1}", f"F{r1 + 1}"):
        ws[a].number_format = "0.000"
        ws[a].fill = YELLOW
    ws[f"A{r1 + 2}"] = (f"sheets.py: G over C {two.g_over_c_per_h:.4f} per hour, C {two.fit.c_kwh_per_f:.3f} kWh per F, "
                        f"G {two.fit.g_kw_per_f:.3f} kW per F")
    ws[f"A{r1 + 2}"].font = ITALIC
    sheet = w.sheet
    last = wb[sheet].max_row
    fl = f"{sheet}!${col[cols[s.floor]]}$2:${col[cols[s.floor]]}${last}"
    pred_h, ff_h = f"{s.label} floor F (predicted)", "free float (no heat in, no slab or fan coil call)"
    pred = f"{sheet}!${col[pred_h]}$2:${col[pred_h]}${last}"
    ff = f"{sheet}!${col[ff_h]}$2:${col[ff_h]}${last}"
    r = r1 + 4
    ws[f"A{r}"] = f"Fit quality with the Model inputs, {s.label}, over the whole {sheet} sheet"
    ws[f"A{r}"].font = BOLD
    ws[f"A{r + 1}"], ws[f"B{r + 1}"] = "RMS (predicted - actual) F, free-float rows", f"=SQRT(SUMPRODUCT(({ff}=1)*({fl}<>\"\")*({pred}-{fl})^2)/MAX(1,SUMPRODUCT(({ff}=1)*({fl}<>\"\"))))"
    ws[f"A{r + 2}"], ws[f"B{r + 2}"] = "RMS (predicted - actual) F, all rows with an actual", f"=SQRT(SUMPRODUCT(({fl}<>\"\")*({pred}-{fl})^2)/MAX(1,SUMPRODUCT(({fl}<>\"\")*1)))"
    ws[f"A{r + 3}"], ws[f"B{r + 3}"] = "sheets.py RMS over charge and float, re-seeded at the span start (F)", round(two.rms_f, 3)
    for a in (f"B{r + 1}", f"B{r + 2}", f"B{r + 3}"):
        ws[a].number_format = "0.00"


def main() -> None:
    codec = SemaCodec()
    roles = load_roles(codec)
    cols = columns(roles)
    wanted = list(cols)
    grids = {w.sheet: load_grid(codec, w.condition, wanted) for w in WINDOWS}
    cal = WINDOWS[0]
    two = fit_two_stage(grids[cal.sheet], roles, FIT_ZONE, cal)
    print(f"{roles.by_zone(FIT_ZONE).label}: stage 1 (free float {cal.float_start} to {cal.float_end}, {len(two.stage1)} rows) "
          f"G/C = {two.g_over_c_per_h:.4f} per hour; stage 2 (charge {cal.charge_start} to {cal.charge_end}, "
          f"{len(two.stage2)} rows) C = {two.fit.c_kwh_per_f:.3f} kWh/F; G = {two.fit.g_kw_per_f:.3f} kW/F; "
          f"RMS over both {two.rms_f:.2f} F")
    wb = Workbook()
    refs = model_sheet(wb, roles, two.fit)
    col: dict[str, str] = {}
    for w in WINDOWS:
        col = window_sheet(wb, w, grids[w.sheet], roles, cols, refs)
    fit_sheet(wb, cal, roles, cols, col, two)
    out = HERE / "spruce-radiant-slab.xlsx"
    wb.save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
