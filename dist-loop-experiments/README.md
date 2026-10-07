# dist-loop-experiments

> What this is: the distribution loop of every house over the 2025–26
> heating season, reduced from the journal DB to hours and to minutes,
> and the analyses that read it: what comes back from the emitters at
> a given source temperature and call pattern, what the pump's speed
> does to it, and what a seldom-calling zone does when it joins. The
> first consumer is the mix-or-not whitepaper
> (`heating-system-design/mix-or-not.md`) and its three memos; each
> tested claim gets a verdict in "Found", carried by a
> `gw.experiment.run` instance. A dataset folder (undated, see the
> repo README): first pull 2026-10-06; the logbook entry is the index
> record.

## Why

The argument for sending store water to the emitters unmixed rests on
how much colder it comes back, and the argument for mixing rests on a
steady-state emitter temperature drop of about 20 °F. Both were stated
from memory and from single days at single houses. The usable energy
in a tank, and so how hot the store has to be charged, follows from
the return temperature, so the numbers have to come from every house
over a whole heating season.

## Setup

Observational: nothing was run on a house; every number is read from
the fleet's own reporting in the journal DB.

**Houses and window.** Beech, elm, fir, maple and oak, 2025-10-01 to
2026-05-01 Eastern (end exclusive). Spruce is left out: it has a
mixing valve, so its distribution source is not what the store holds.
Maple is treated as two distribution systems, `maple1` before its
panel heater and `maple2` after (dates in `houses.py`).

**Channels.** Every pull takes its channel words from the house's own
emitted `layout.lite`, the latest one at or before the end of the
week being pulled (`layout.lite` 004 through 012 over the season),
and converts each value by that word's encoding. The database's unit
column is never believed. The season-long pulls read `dist-swt`,
`dist-rwt` and `dist-flow` for every house; the beech minute pull adds
`dist-pump-pwr`, `dist-010v` and every `zone<n>-<name>-whitewire-pwr`;
the plot of one event adds the buffer and heat pump temperatures,
`hp-odu-pwr` and `primary-flow`.

**Grid.** Readings are reported on change, so each channel is
forward-filled onto a 10 s grid. A grid sample is valid while both
temperature channels have reported within 600 s; flow and the pump
channels are forward-filled without a limit inside that validity,
because a steady value reports rarely. One journal query spans one
week; a month-long query hits the DB's statement timeout.

**Reductions.** The hourly file keeps every hour with at least 95%
valid samples: the share of the hour the loop circulated (flow at or
above 0.5 gpm), the flow-weighted source and return over the
circulating samples, the mean flow and the heat delivered (500 x gpm
x drop BTU/h, water, summed over the hour, in kWh). The minute file
keeps every minute whose six samples are all valid: minute means of
flow, pump power, pump volts, source and return, the age of the oldest
temperature reading any of its samples used, and each zone's call
fraction (share of samples with the white wire above 10 W).

## Found

One line per tested claim; the numbers and the argument are in the
paper and the memos, the tables are in the output files named here.

- **Claim 2, a steady-state emitter drop of about 20 °F: FAIL as
  stated** at every house. In steady circulation (loop on 95% of the
  hour or more) the drop rises with source temperature and differs
  between houses by a factor of two at the same source; 20 °F is one
  point on each house's line. `steady-drop.txt`; the paper's claim 2.
- **Claim 3, shorter heat calls return colder water: PASS** at every
  house, 12 to 44 °F colder at a fixed source between hours with the
  loop on under 20% of the hour and steady hours. `return-temp.md`,
  `return-by-heat.md`, `maple-panel-heater.md`; the paper's claim 3
  and `heating-system-design/return-water-temperature-memo.md`.
- **Distribution pump speed against return at beech:** one speed per
  zone pattern all season, so the only within-pattern comparison is
  the 2026-01-24 hand test. `beech-2026-01-24-steps.txt`;
  `heating-system-design/beech-emitter-physics-mystery.md`.
- **A call from the idle zone during a steady call puts its loop's
  cold water through the return, the heat pump and the source: PASS**
  at beech, 45 events. `beech-bolus-recovery.txt`,
  `beech-bolus-recovery.png`;
  `heating-system-design/cold-zone-call-during-steady-heating-memo.md`.
- **The drop is back near its pre-call value within five minutes and
  nothing of the slug remains after that: PASS** at beech. Ten to
  thirty minutes after a call the drop sits more than 3 °F from its
  pre-call value in 56 to 80% of events, and in 69 to 84% of
  steady-call minutes with no idle-zone call in the previous half
  hour; the source's own movement explains it (0.23 °F of drop per °F
  of source at beech), and with that removed the median residual is
  within ±2 °F at every horizon, as at the control minutes.
  `beech-bolus-recovery.txt`; the memo's "Across the season".
- **Beech's upstairs loop comes back as about 4 gallons of
  room-temperature water:** the return's heat deficit over each call,
  as a volume at 65 °F, median 4.4 gal across the 45 calls, quartiles
  3.2 to 6.3; the valve adds a median 0.95 gpm while open.
  `beech-bolus-recovery.txt`; the memo's "How much water the upstairs
  loop holds".

## Timeline

- 2026-10-06 14:35 ET: one-day check on beech 2026-01-05 reproduces
  the paper's first look (16–17 °F at 130–138 °F source), decoded
  through sema.
- 14:36: six houses (spruce included) pulled in parallel with
  month-long queries; five hit the journal DB's statement timeout.
- 14:37–14:41: pulls rerun a week per query, one house at a time; all
  six complete.
- 15:25: spruce's files removed and the tables regenerated; it has a
  mixing valve.
- 2026-10-06, later: the return-temperature tables by circulation
  fraction and by heat delivered; maple split at its panel heater.
- 2026-10-07: beech's season pulled on the minute grid with the pump
  channels and zone calls; the 2026-01-24 hand test tabulated; the
  cold-zone-call events found and one plotted.
- 2026-10-07: scripts reorganised around `grid.py`, `records.py` and
  `houses.py`; every output regenerated byte-identical; instances
  re-emitted at `gw.experiment.run` 001 with verdicts.

## Analysis notes

- **Steady means the loop circulated, not that one zone called.** The
  hourly condition is flow at or above 0.5 gpm for 95% of the hour,
  which a single constant heat call and several overlapping ones both
  satisfy. It needs no per-house zone names.
- **Each week starts cold.** A channel has no value until its first
  reading of the week, so the first seconds of each week are invalid.
  Pulling elm a month per query against a week per query moved 3 of
  4,872 hours and one steady hour.
- **Temperatures are flow-weighted over circulating samples.** An hour
  with no circulation has no source or return temperature (`null`).
- **Layouts 004 to 006 (through 2026-01-08) carry their computed
  channels as `synth.channel.gt`**, which `gw.readings` does not
  hold, so those channels are not pullable for that period; data
  channels are. Nothing here needs a computed channel.
- **The minute file's 600 s validity is generous.** `TempAgeS` is the
  oldest temperature reading a minute used; an analysis that needs
  fresh data filters on it (the bolus search uses 120 s, the January
  24 table 90 s). The need showed on January 24: every channel
  stopped reporting 11:06:30–11:21:10, and the forward-filled minutes
  of the 6 V step passed as valid.
- **Beech's 0-10 V channel read 0 V for 2026-02-12 to 14 and 02-21 to
  26** while flow and power held; both stretches start and end where
  every reading freezes, so a restart artifact is the likely cause,
  unconfirmed.
- **A cold-zone-call event** is an idle-zone call (white wire on in
  consecutive minutes) with the steady zone calling alone, the loop
  circulating and both temperatures fresh for 10 minutes before and
  at least 10 after; recovery is the first minute after the call
  where the drop is within 5% of its pre-call mean for two minutes
  running. 28 of the 45 events never re-enter that band inside their
  window (a 5% band on a 19 °F drop is ±1 °F); the report also gives
  10% and the median excess by minute. The 5% band assumes a source
  that holds, and beech's source held within ±3 °F over minutes 3 to
  10 after only 4 of the 45 calls; so the report also removes the
  source's share through the house's steady line (drop against source
  fitted to its steady hours) and compares the result with control
  minutes: steady call, no idle-zone call for 30 minutes before, every
  fifth eligible minute.
- **Heat per hour** is 500 x gpm x drop BTU/h summed over the hour,
  for water with no glycol correction.

## Folder contents & experimental method

All data came from the immutable store: `gridworks.readings` and the
`layout.lite` messages in the journal DB, re-pullable by anyone with
the journal login in `experiments/.env` (`GJK_DB_URL`; which login
and where its credentials live is in
`gridworks-infra/databases/journaldb.md`). Nothing was generated by an
instrument of this experiment and no running system was touched. A
re-pull of the same window reproduces the same files unless the
journal's retention has since dropped the window.

Two data files are kind-specific, not sema instances: no word holds
an hourly or minute aggregate of a channel yet. They are typed
records in `records.py` with the note naming the missing word. The
hourly files are committed, since every table reads them and a season
re-pull takes minutes per house; the minute file is gitignored
(`*-minute.pump.json`, 14 MB a house) and regenerated by its pull.

Support modules (imported, not run):

- `grid.py`: the step every pull shares: channel words from the
  layout.lite at the window end, readings for the window, the 10 s
  grid, forward fill with the age of each sample's reading, and
  conversion to natural units by each word's encoding (°F, gpm, W,
  V). The W and V tables live here until `../unit_encodings.py`
  takes them.
- `records.py`: `HourRecord` / `HourlyFile` and `MinuteColumns` /
  `MinuteFile`, the two data files' shapes, with their dict form at
  the read/write boundary only.
- `houses.py`: the terminal asset alias by house name, the
  distribution systems the hourly files hold (maple split at its
  panel heater), and `ZONE_PAIRS`, the steady and idle zone of each
  house pulled on the minute grid (beech).

Pulls (journal DB):

- `emitter_drop.py`: one house's window to its hourly file, a week
  per query.
- `hw1.isone.me.versant.keene.<house>.ta-20251001.20260501-hourly.dist.json`:
  one record per valid hour (fields on `HourRecord`). About 4,900
  hours per house.
- `pull-<house>.log`: the pull's own output: each week's `layout.lite`
  version and emission time, and any week skipped.
- `pump_speed.py`: one house's window to its minute file, a week per
  query.
- `hw1.isone.me.versant.keene.beech.ta-20251001.20260501-minute.pump.json`
  (NOT committed; gitignored): column lists keyed by name (fields on
  `MinuteColumns`), one entry per valid minute; 14 MB. Beech only so
  far. Regenerate it with the `pump_speed.py` line below before
  `bolus_recovery.py`.
- `pull-beech-pump.log`: as above for the minute pull.
- `beech_jan24_steps.py`, `beech-2026-01-24-steps.txt`: the
  2026-01-24 hand test, one row per 0-10 V step, straight from the
  journal DB with a 90 s freshness rule and ten minutes clear of an
  upstairs call. The step times are in the script.

Tables from the hourly files (no DB):

- `steady_drop.py`, `steady-drop.txt`: drop by source temperature in
  steady hours, quartiles and counts, per system.
- `return_temp.py`, `return-temp.md`: per system, return temperature
  with source temperature in rows and circulation fraction in columns;
  medians with hour counts, then quartiles.
- `return_by_heat.py`, `return-by-heat.md`: per system, return
  temperature with heat delivered in rows and source temperature in
  columns, then the circulation share in the same cells.
- `maple_panel_heater.py`, `maple-panel-heater.md`: maple's return at
  the same heat delivered before and after its panel heater, and the
  emitters' output per degree in each stretch.

From the minute file:

- `bolus_recovery.py`, `beech-bolus-recovery.txt`,
  `beech-bolus-recovery.png`: the cold-zone-call events, the
  recovery of the drop after each, and the drop's later movement
  against control minutes with the source's share removed, and the
  idle loop's cold water as a volume from the return's heat deficit; the PNG is one representative
  event (the recovered event at the median recovery time) with the
  buffer and heat pump temperatures pulled from the journal DB for
  that window. Reads the minute file, so the `pump_speed.py` pull
  comes first; `--plot` reaches the DB again for the event's window.

For spreadsheet readers:

- `sheets.py`, `<document>.xlsx`, `csv/`: one workbook per document
  in the heating-system-design repo, holding only the tables that
  document's text draws on: a Summary tab in front naming each tab
  with what its rows are, then one tab per table and the records the
  tables were made from, with one number per cell (a statistic with a
  spread is three columns, a mean with a range is three). Each
  script's `tables()` builds its rows through the repo's `tables.py`,
  and its printed text or markdown is a rendering of the same cells.
  `beech-emitter-physics-mystery.xlsx` carries the January 24 steps,
  the minute trace under them (09:00 to 12:30 ET), beech's steady-hour
  bins, beech's idle-zone calls with their recovery, and beech's hourly
  records. `csv/` gets every table plus the minute grid. The workbooks
  and `csv/` are gitignored and regenerate with one command.
  `--minute-tabs` adds the season's minute grid to the workbook (about
  300,000 rows); `--no-db` leaves out the tables that reach the
  journal DB (the January 24 steps).

Instances:

- `emit_instances.py`, `instances/`: one `gw.experiment.run` 001 per
  house and tested claim, subject the house's scada alias, condition
  the claim (`claim2`, `claim3`, `cold.zone.call`), with the verdict
  and the script whose output carries it.

Prerequisites: `uv` and this repo's `.venv` (`uv sync` at the repo
top), `experiments/.env` with `GJK_DB_URL`, and for validation a
sibling `sema` checkout.

Regenerate everything from scratch, from this folder, one house at a
time (a season pull is 31 weekly queries per house):

    for h in beech elm fir maple oak; do uv run python emitter_drop.py --house $h --start 2025-10-01 --end 2026-05-01 > pull-$h.log; done
    uv run python pump_speed.py --house beech --start 2025-10-01 --end 2026-05-01 > pull-beech-pump.log
    uv run python steady_drop.py > steady-drop.txt
    uv run python return_temp.py > return-temp.md
    uv run python return_by_heat.py > return-by-heat.md
    uv run python maple_panel_heater.py > maple-panel-heater.md
    uv run python beech_jan24_steps.py > beech-2026-01-24-steps.txt
    uv run python bolus_recovery.py --house beech --plot
    uv run python emit_instances.py
    uv run python sheets.py beech-emitter-physics-mystery

The four tables and the instances regenerate from the committed
hourly files alone. The bolus report needs the minute file, which only
the `pump_speed.py` pull makes. The three pulls, the January 24 table
and `--plot` reach the journal DB. Check a regeneration with
`git diff --stat` in this folder: a clean tree means every output
reproduced (a re-pull reproduces the same files while the journal
still holds the window).

Validate an instance against the registry (from the sema checkout):

    uv run sema validate ../experiments/dist-loop-experiments/instances/hw1.isone.me.versant.keene.beech.scada-claim2-gw.experiment.run-001.json

Read an instance back through the snapshot:

    uv run python -c "from gwexp.sema.codec import default_codec; from pathlib import Path; print(default_codec.from_bytes(Path('instances/hw1.isone.me.versant.keene.beech.scada-claim2-gw.experiment.run-001.json').read_bytes()))"

The folder holds no `gw.readings` instance: a season of raw readings
for one house is several million values. A display CSV for any
window comes from a pull into a scratch folder:

    uv run python ../pull_readings.py --ta hw1.isone.me.versant.keene.beech.ta --channel dist-swt --channel dist-rwt --channel dist-flow --start '2026-01-26 00:00' --end '2026-01-27 00:00' --out /tmp/beech-jan26
