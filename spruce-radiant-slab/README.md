# spruce-radiant-slab

> What this is: the radiant slab at spruce, read from the journal DB, fitted
> to a two-lump floor-and-room model so the Knife's Edge homes can be sized
> and controlled from measured numbers rather than a rule of thumb. A dataset
> folder (undated, see the repo README): first pull not yet made; the logbook
> entry is the index record once it is.

## Why

Matt Polstein's Knife's Edge development (14 homes in Millinocket, then
100) puts the thermal store in concrete under a radiant floor. Every sizing
and control question about those homes turns on two numbers that are
currently rules of thumb: how fast heat moves from a warm slab into the
room per square foot per degree, and how much heat the slab and the house
each hold per degree. Spruce has three radiant-slab zones with floor
temperature sensors, a BTU meter on the distribution loop, and zone
thermostats reporting heat calls, so those numbers can be measured.

The model to fit is the one on the whiteboard:

- Heat flow floor to room: `U_floor` in BTU/h per sq ft per °F, prior 2
  (or 1).
- Floor heat content: concrete at 0.0000631 kWh/lb/°F, prior 9.4 kWh/°F
  for 1000 sq ft a foot deep.
- House heat content: prior 4 kWh/°F.
- House heat loss on the design day: prior 4 kW.

Each prior gets a measured value, a confidence interval and the window it
came from, in "Found".

**The model is per zone, and needs neither slab area nor thickness.**
Each slab zone is two lumps: a floor at its floor sensor's temperature
(the sensor sits in PEX at tubing depth) and a room at its zone air
sensor's temperature. Two named coefficients per zone:

- **G, floor to room**, in kW per °F of (floor minus air): the heat the
  slab gives the room is G times that difference.
- **C, floor heat capacity**, in kWh per °F of floor sensor.

Heat into the floor is the hot-side BTU meter, flow times (distribution
supply minus return), shared among the slab zones calling. Each step:
floor rises by (heat in minus G times (floor minus air) times step) over
C. Slab area and thickness do not enter, and neither is known for spruce.
G and C are fitted in two least-squares stages, each a slope through the
origin: the free float (no heat in, no slab zone and no fan coil calling)
gives G over C from the floor's fall per hour against floor minus air;
the metered single-zone charge then gives C from the accumulated heat in
against the floor's rise plus G over C times the accumulated
floor-minus-air hours; G is the product. The charge is taken whole,
through its settle, because at tubing depth the sensor warms ahead of
the slab's mean. Refinements wait on a residual:
the delta-T dependence of the surface film, the gradient inside the slab.
A per-zone G and C are the shape of a named house parameter; the layout's
placeholder `zone_kwh_per_deg_f_list` is the room-side analogue.

## Setup

Observational: nothing was run on the house; every number is read from
spruce's own reporting in the journal DB (`DB_ANALYST_URL` in `../.env`), the
scada alias `hw1.isone.me.versant.keene.spruce.scada`, terminal asset
`hw1.isone.me.versant.keene.spruce.ta`.

**Zones.** Spruce's `gw.nolan.layout` word (the folder's
`…spruce.scada-gw.nolan.layout-000.json`, imported from the tlayouts
generator's output by `import_layout.py`; spruce emits only `layout.lite`
to the journal, which has no zone circuits) declares four thermal zones
served by five call circuits. `sheets.py` reads the roles below from the
word: a circuit's `EmitterType`, `ServesZone`, `FloorTempChannelName`
and `TempChannelName`, and its heat call as the derived channel on its
`WhitewireChannelName`. Three circuits are radiant slab, two are fan
coils; a slab-only analysis uses hours when neither fan coil calls.

| circuit | zone | emitter | floor temp channel |
|---|---|---|---|
| zone1-bedrooms | bedrooms | RadiantSlab | zone1-bedrooms-floor-temp |
| zone2-living-rm | living-rm | RadiantSlab | zone2-living-rm-floor-temp |
| zone3-upstairs | upstairs | FanCoil | |
| zone4-garage | garage | RadiantSlab | zone4-garage-floor-temp |
| zone5-living-rm-fancoil | living-rm | FanCoil | |

**The garage is left out for now**: its columns are not in the workbook
and its calls do not enter the share rule (it called a few hours on the
Oct 6 evening, so that evening's split is approximate). Each zone's
floor sensor is in a piece of PEX at the same depth as the rest of the
tubing, so it reads the slab at tubing depth, not the surface. All three
radiant floors are bare concrete, no finish layer; their area and depth
are not known and nothing here assumes them.

**Heat into the floor.** `dist-flow` with `dist-swt` and `dist-rwt` is the
BTU meter on the distribution loop; it serves every circuit, so heat into
the slabs is attributable only in hours when no fan coil runs.

**The mixing valve.** The distribution flow meter is on the hot water
before the mixing valve (confirmed on site). A thermostatic mixing valve
holds the water into the floor at about 108 °F: in the Oct 6 to 7 data,
whenever the distribution supply is above 108 °F, `floor-swt` (the pipe
sensor on the pipes1 pico, journaled as FahrenheitX100) sits at 107 to
108 °F, and when the source cools below that the floor supply follows it
down. The hot flow moves the other way: 0.4 gpm with a 130 °F source and
1.7 to 2.9 gpm once the source is below the target, the valve opening as
the source cools. So `dist-flow` is the hot water the valve admits, not
the water circulating through the slab tubing, and the metered pump
(`dist-pump-pwr`) runs only with the heat pump while flow through the
valve continues with it off; the floor circulator is an unmetered pump.
Two consequences:

- Heat into the floor loop is `dist-flow` times (`dist-swt` minus
  `dist-rwt`) times 500 BTU/h per gpm per °F, valid whatever the valve is
  doing, because the hot water enters at the supply temperature and the
  same mass returns to the source at the floor's return temperature.
- The slab's boundary temperatures are `floor-swt` and `floor-rwt`, not
  the distribution pair, which reads about 20 °F hotter on the supply
  side.

The hours with the floor supply pinned at 108 °F are the constant-input
hours for the fit (Oct 7 02:30 to 05:00 and 13:00 to 16:00, living room
alone).

## Found

One line per fitted parameter or tested claim; the numbers are in the
workbook (`spruce-radiant-slab.xlsx`, regenerated by `sheets.py`).

- **Living room: G 0.191 kW per °F, C 2.59 kWh per °F**, fitted in two
  stages. Stage 1, the Oct 7 night free float 19:00 to 02:00 (41 rows
  with no heat in, no slab zone and no fan coil calling): G over C
  0.0735 per hour. Stage 2, the Oct 7 charge 02:00 to 19:00, the living
  room alone with heat in metered (102 rows): C 2.59 kWh per °F. RMS of
  the recursion with that pair over charge and float, 0.42 °F. The joint
  grid search this replaced gave 0.220 and 2.3 (RMS 0.45), so two
  readings of the same data agree to about 15 % on each coefficient.
  `instances/…floor.to.room.coefficient…`: PASS.
- **The free float fixes only G over C**, which is why the charge is
  needed to separate them; over the seven-hour night the slab gave the
  room about 4 kWh.
- **Heat in, Oct 6 00:00 to Oct 8 12:00: 91 kWh metered on the hot side,
  56 kWh of it to the living room slab** by the share rule (1/n of the
  slab zones calling, garage excluded).
- **Bedrooms: not yet fitted.** No window has the bedrooms charging
  alone; the living room's G and C stand in on the Model sheet and the
  bedrooms prediction is a shape to compare against, not a fit.
- **Prediction against actual, continuous from Oct 6 00:00 with the
  fitted inputs: RMS 2.1 °F** over the whole window, 0.8 °F over its
  free-float rows. The excess is the Oct 6 evening, when both slabs
  charged and the 1/n share rule decides the split. A bedrooms fit
  replaces the rule with a check: each zone's heat in against its own
  floor rise.

## Timeline

- 2026-10-15: data inventory (the table below) and candidate windows found;
  folder opened.
- 2026-10-15: first pull (Sep 21 to 25, Oct 6 to 8); the model workbook
  built; the model restated per zone as G and C, fitted in two stages
  for the living room (G over C from the free float, C from its charge
  alone); the garage set aside; the mixing valve, the hot-side meter and
  bare concrete confirmed on site.

## Analysis notes

**What the journal holds for spruce, by period** (ET; from a per-channel
first/last sweep on 2026-10-15; the two dead weeks are Jan 26 to Feb 1 and
Mar 16 to Mar 29).

| What | Recorded from | Note |
|---|---|---|
| Floor BTU meter (dist-swt, dist-rwt, dist-flow) | 2026-01-23 | continuous to today |
| Heat calls zones 1, 2, 4 | 2026-01-28 | opto-input channel re-declared Unknown to BinaryState on Mar 31 (metadata only; the derived heat-call row is unbroken and the inversion opto 0 = call 1 is the same on both sides) |
| Heat call zone 3 (upstairs fan coil) | 2026-07-08 | no upstairs zone before July |
| Heat call zone 5 (living-rm fan coil) | 2026-07-08 | |
| Element power (buffer top/bottom, store top/bottom) | 2026-01-23 | |
| Zone air temps (gw-temp zones 1, 2, 4) | 2026-03-30 | nothing before; zone 3 from Jul 8 |
| Floor surface sensors (bedrooms, living-rm, garage) | Feb 6 to Mar 10 | the only floor-surface window in spring |
| Derived floor temps (zone1/2/4-floor-temp) | Mar 30 to May 18; Jul 8 to Aug 10; Sep 9 to 15; Sep 23 on | absent over the Sep 21 first-heat event |
| Floor supply/return in °F (floor-swt, floor-rwt) | Feb 6 to May 18, then as the floor temps | same sensors as dist-swt/rwt |
| Zone setpoints | 2026-05-22 | |
| Heat pump power, LWT/EWT, primary flow | Jul 8 / Aug 3 | no heat-pump data in spring |
| Buffer tank depths | 2026-01-23 | |
| Forecast outdoor temp and wind | 2026-01-23 | the only outdoor temperature |

**Spring 2026 heating, weekly.** Supply averaged about 130 °F, return near
88 °F, flow when running mostly under 1.5 gpm (a low-flow, high-delta-T
regime, roughly 20 kBTU/h while flowing). Zone 2 called 0.76 to 0.83 of
the time in early February; calls thinned through March and April and
heating ended Apr 27. Room temperatures exist only from Mar 30. The flow
meter shows occasional spikes (54 and 108 gpm in April and May) that need a
sanity filter.

**Fall 2026 events.**

- First floor heating, Sep 21 16:00 to Sep 22 07:00: zones 1 and 2 called
  continuously for about 14 h; supply rose to 130 °F by 22:00, return 93 to
  97 °F, flow 1 to 2.8 gpm. The garage (not calling) rose from 66 to 76 °F.
  Then every zone free-floated for two days at 72 to 75 °F with no call:
  the slab-plus-house time constant in the open. No floor temps in this
  window; 09:00 to 15:00 on Sep 21 is missing entirely.
- Hours with a slab zone calling continuously, both fan coils silent and
  floor temps present (Sep 9 to Oct 15, hourly, call fraction at or above
  0.95):

  | window (ET) | calling | floor temps | loop |
  |---|---|---|---|
  | Sep 9 13:00 to Sep 15 16:00, four runs of 19 to 95 h | zones 1 and 2 | flat at 65 to 66 °F | flow 0, supply 65 °F: calls with no heat delivered |
  | Oct 6 16:00 to Oct 7 16:00 (25 h) | zone 2 | zone 2 floor 68 to 79 °F; zone 1 68 to 72 | flow 1.6 gpm, supply 104 °F |
  | Oct 14 07:00 to 09:00 (3 h) | zone 2 | zone 2 floor 68 to 69 °F | flow 1.2 gpm, supply 102 °F |

  Oct 6 to 7 is the one clean slab-charging run with floor temps so far.
  The Sep 9 to 15 runs are a thermostat calling into a dead loop, useful
  only as evidence of that.

- The garage sat at 74 to 76 °F most days from Sep 22 to Oct 15 without
  calling. Something heats it continuously; check before treating it as a
  slab zone in the fit.
- On Sep 23 at 11:00 every zone temp drops 4 to 5 °F in one hour with a
  short call, more likely a scada restart or sensor swap than physics.

## Folder contents & experimental method

All data in this folder is from the immutable store (the journal DB), the
fleet's own reporting; anyone can re-pull it. Nothing was generated and the
running system was not touched. The two pulls cover Sep 21 00:00 to Sep 25
00:00 and Oct 6 00:00 to Oct 8 12:00 ET: every `zone*`, `dist-*`, `floor*`
and `pipes1*` channel plus `forecast-oat` and `hp-odu-pwr` (the pico-state
pseudo channels have no layout word and are dropped, see the pull logs).

- `hw1.…spruce.ta-first.heat.sep-gw.readings-000.json.gz`,
  `…-first.heat.oct-gw.readings-000.json.gz`: the two `gw.readings`
  instances, gzipped under the 2 MB cap, bytes intact. `pull-sep.log`,
  `pull-oct.log`: what each pull wrote and dropped.
- `hw1.…spruce.scada-gw.nolan.layout-000.json`: spruce's layout word, the
  tlayouts generator's output for the house (`tlayouts` branch `jm/spruce`
  at `0e01a2c`), each nested word upgraded through the codec to the
  binding the vendored snapshot was built from. `import_layout.py` is the
  regenerator; re-run it when the house's layout changes.
- `sheets.py`: builds `spruce-radiant-slab.xlsx` (gitignored) from the
  layout word and the two `gw.readings` instances, each reading taken to
  natural units by its channel word's encoding: 10-minute bin means; a
  Model sheet with G and C per zone (blue inputs, the fitted pair
  yellow); one sheet per window with heat in (kW, kWh and BTU/h, per
  step and cumulative), each zone's share, heat in, actual and predicted
  floor temperature, predicted heat to room and error, and the
  free-float flag (no heat in, no slab zone or fan coil calling); a Fit
  sheet with both least-squares stages as tables, their slopes as cell
  formulas, and the RMS of prediction against actual. The script fits
  the living room's G over C and C and writes G and C to the Model
  sheet.
- `emit_instances.py` → `instances/`: one `gw.experiment.run` per tested
  claim.
- `hw1.…spruce.ta-no.charge.{apr,may,fall}-gw.readings-000.json.gz`: the
  floor, room, heat-call and distribution-flow channels over the spring
  and fall spans in which no slab zone was charged, three more
  `gw.readings` instances; `pull-no.charge.*.log` beside each.
  `no-charge-spans.md` lists the spans.
- `irradiance-kmemilli18.csv.gz`: external evidence, the five-minute
  reports of the Weather Underground station KMEMILLI18 in Millinocket
  (solar high, temperature, humidity, wind) over the three windows in
  `pull_irradiance.py`, from the weather.com history API with a
  provenance header; `pull-irradiance.log` has the per-day counts and
  gaps. No sema word covers a station irradiance series yet; the script
  names the word that retires the CSV.
- `star-model.md`, `star_fit.py` → `star-fit.xlsx` (gitignored): the
  one-lump star model (room branch, ground branch, solar gain) fitted by
  cumulative-integral least squares over every no-charge span at once,
  checked by forward simulation, one sheet per span.

Regenerate everything from scratch:

    uv run python ../pull_readings.py --ta hw1.isone.me.versant.keene.spruce.ta \
        --like 'zone%' --like 'dist-%' --like 'floor%' --like 'pipes1%' \
        --channel forecast-oat --channel hp-odu-pwr \
        --start '2026-09-21 00:00' --end '2026-09-25 00:00' \
        --condition first.heat.sep --out . > pull-sep.log
    uv run python ../pull_readings.py --ta hw1.isone.me.versant.keene.spruce.ta \
        --like 'zone%' --like 'dist-%' --like 'floor%' --like 'pipes1%' \
        --channel forecast-oat --channel hp-odu-pwr \
        --start '2026-10-06 00:00' --end '2026-10-08 12:00' \
        --condition first.heat.oct --out . > pull-oct.log
    gzip -9 *-gw.readings-000.json
    uv run python import_layout.py ../../tlayouts/output/spruce/gw.nolan.layout.json
    uv run python sheets.py
    uv run python emit_instances.py
    uv run python pull_irradiance.py && gzip -9 irradiance-kmemilli18.csv
    uv run python star_fit.py

Display CSVs from the committed instances (for a human to browse; nothing
in the folder reads them), no database access:

    uv run python ../pull_readings.py --display-from hw1.isone.me.versant.keene.spruce.ta-first.heat.oct-gw.readings-000.json.gz
    uv run python ../pull_readings.py --display-from hw1.isone.me.versant.keene.spruce.ta-first.heat.sep-gw.readings-000.json.gz

---

**From the instance to the display CSV.** The `*-gw.readings-000.json`
file is the canonical record: the channel words together with their
readings, validating against the sema registry. The `-display.csv`
sibling is presentation only, the same readings as natural-unit floats
(temperatures °F, flows gpm), converted per each channel word's own
encoding. Regenerate it any time, with no database or S3 access:

    uv run python ../pull_readings.py --display-from <instance>.json
