# lg-hydrokit-signatures

> What this is: the LG heat pump pair at beech and oak, the ARUM048GSS5
> Multi V outdoor unit (`hp-odu`) and the ARNH423K3A4 Hydro Kit indoor
> unit (`hp-idu`), read from the journal DB over 2025-10-01 to
> 2026-10-21 ET, and the analyses that read it: how the pair looks in
> the scada's channels while running, while idle and while defrosting.
> The consumer is the gridworks-scada executor's heat-pump signatures
> (running, idle and defrost spokes, LG sections). A dataset folder
> (undated, see the repo README): first pull not yet run; the plan
> below is for review before it runs. Each tested claim gets a verdict
> in "Found".

## Why

The LG's start-up is measured, but its running, idle and defrost
behaviour is not. Three things hang on them. Code that reads
`hp-odu-pwr` to judge the compressor stopped needs to know what the
outdoor unit draws on its own while idle: oak read a steady 204 W on
2026-10-20 with the heat pump commanded off, against a 26 W standby.
The local control judges an LG defrost by a sum of the two power
channels under 8.4 kW (`gridworks-scada`
`gw_spaceheat/actors/hp_boss/sensing.py` `DEFROST_SIGNATURES`, read
at `actors/hydronic/house0.py` `hp_in_defrost`), a line with no
measured defrost behind it. And the running band is what any
running/stopped or defrost line is set against.

## Setup

Observational: nothing is run on a house; every number is read from
the fleet's own reporting in the journal DB.

**Houses and window.** Beech and oak, 2025-10-01 to 2026-10-22 ET (end
exclusive): last heating season and this one to date. Both run the
same LG pair (`tlayouts/oak_gen.py:153`, `beech_gen.py:157`).

**Channels.** `hp-odu-pwr`, `hp-idu-pwr`, `hp-lwt`, `hp-ewt`,
`primary-flow`, `hp-scada-ops-relay6` (0 is closed, commanded on),
each week's words from the house's own `layout.lite` at or before the
week's end and each value converted by its word's encoding.
`forecast-oat` is in `gridworks.readings` for both houses but is no
channel word in either layout; it is hand-mapped (FahrenheitX100) and
is the only outdoor temperature both houses have across the window.

**Grid.** Readings are reported on change (power on a 300 W change,
with a 300 s periodic capture), so each channel is forward-filled
onto a 10 s grid (60 s for idle shares) and a sample is blank when its
reading is older than 330 s (3,700 s for the forecast).

**Reductions.** Three typed record files per house (`lg_records.py`):
compressor runs, idle episodes of the 200 W state, and mid-run
indoor-compressor dips classed defrost or stop.

## Claims to test

Each claim with its channels, window and method. Window is the folder
window unless named; thresholds are the constants in the scripts.

1. **Running band.** In steady running (runs of 30 min or more, from
   15 min after the start to 1 min before the end) `hp-odu-pwr` holds
   about 7.3 kW, `hp-idu-pwr` about 3 kW (the hydro kit's own
   compressor), their sum about 10 kW, with flow, lift and LWT bands
   per house. Channels: both powers, `primary-flow`, `hp-lwt`,
   `hp-ewt`, `forecast-oat`. Method: per-run medians from the runs
   file, p10 / median / p90 per house and season, by month and by
   10 °F forecast band (`running.py`).
2. **Hydro kit compressor timing.** `hp-idu-pwr` passes 1500 W a
   median of about 330 s after `hp-odu-pwr` passes 2000 W at a start.
   Channels: both powers, raw reports. Method: per-run lag in the runs
   file, quantiles (`running.py`).
3. **Standby.** With the compressor off `hp-odu-pwr` reads 26 W from
   November to March and 20 W in summer, and `hp-idu-pwr` 12 W.
   Verifies the 26 W in the start-up spoke. Channels: both powers.
   Method: 60 s grid, idle minutes under 60 W, quantiles by season
   (`idle.py`).
4. **The 200 W idle state.** With the compressor off the outdoor unit
   steps to about 200 W (oak) or 214 W (beech) for about an hour, with
   `hp-idu-pwr` at standby and no flow. Channels: both powers,
   `primary-flow`. Method: idle episodes (consecutive raw reports at
   150–260 W outside runs) from the episodes file, level and length
   bounds; share of idle time by month (`idle.py`).
5. **The state follows a stop.** It begins 40–60 minutes after a
   compressor stop in most stops followed by a long idle, recurs about
   every 6–8 hours through a long idle, and is near absent above 65 °F
   forecast. Channels: `hp-odu-pwr`, `forecast-oat`. Method: share of
   idle minutes in the state by minutes since the stop and forecast
   band; share of stops followed by an episode 30–70 min later;
   start-to-start intervals of episodes more than 4 h after a stop
   (`idle.py`).
6. **Short episodes and relay 6.** Episodes under 15 minutes begin near
   a relay 6 change far more often than hour-long ones. Channels:
   `hp-odu-pwr`, `hp-scada-ops-relay6`. Method: count of episodes with
   a relay 6 change from 10 min before to 5 min after their first
   report (`idle.py`).
7. **Oak's 204 W, 2026-10-20 18:31–18:42 ET.** The reading is the 200 W
   state at oak's level, seen twice by window scadas between production
   journal readings of 22 W, off the long-idle cadence. Channels:
   `hp-odu-pwr`, `hp-scada-ops-relay6`. Method: the production journal
   for 2026-10-19 to -21 (episodes file), and the two window scadas'
   stdout read with `idle.py --window-log` (first window
   `GridWorks/scratch/oak-window-20261020-174659.log`; second window
   `beta-field-windows/runs/2026-10-20-1831-oak-second-window/oak-window-20261020-184437.log`).
   A check that scada restarts do not bring the state on: the first
   report after each 10–60 min journal gap (`idle.py`).
8. **Defrost signature.** In cold weather, mid-run, the outdoor unit
   falls from about 7.3 kW to under 1 kW and keeps running at 2–3 kW
   while the hydro kit's draw first rises and then falls under 800 W
   for about 5 minutes; lift goes a few °F under zero; flow continues;
   about 13 minutes from the fall to the sum back over 9 kW. Channels:
   both powers, `hp-lwt`, `hp-ewt`, `primary-flow`, relay 6,
   `forecast-oat`. Method: dips file, defrosts against stops,
   quantiles of each phase and field; one traced case read by hand from
   the grid (`defrost.py`, `events.py`).
9. **Defrost against a stop.** A defrost keeps `hp-odu-pwr` at or over
   350 W, so the LG's running/stopped rule (2000 W / 350 W) does not
   fire on it; dips that reach standby are upper-limit trips or
   cold-weather stops whose kind is open. Method: dips classed by that
   350 W test; the stops' LWT before and forecast (`defrost.py`). The
   class is defined by the test, so the verdict rests on the
   cold-weather dependence of both classes, which is reported beside
   it.
10. **Defrost frequency.** About 0.3 defrosts per running hour at
    forecast 40 °F and below, near none above. Method: defrosts and
    running hours by 10 °F forecast band (`defrost.py`).
11. **The 8.4 kW line.** The deployed sum under 8.4 kW catches every
    defrost but also fires in steady running in mild weather and near
    the upper limit; a sum under 6 kW, or `hp-idu-pwr` under 1.5 kW
    with the outdoor unit running, held 120 s, catches as many with a
    tenth of the mild-weather fires. Method: each line scored over
    steady running (15 min into a run, commanded on) at dwells 0, 120
    and 300 s; a fire inside a defrost window is a catch, any other is
    counted by forecast band, above 45 °F taken as not a defrost
    (`defrost.py`).
12. **The 20-minute defrost timeout.** The local control's
    `DEFROST_TIMEOUT_MINUTES = 20` covers most LG defrosts from start to
    recovery. Method: share of defrosts with total under 1,200 s
    (`defrost.py`).

## Found

Open.

## Timeline

- 2026-10-21: plan written for review; no pull yet.

## Analysis notes

- `forecast-oat` reads ten times its FahrenheitX100 value from
  2026-01-09 02:00 UTC to 2026-05-30 at both houses (24 °F reads 24000
  against 2400 the day before). `pull.py` hand-maps that stretch
  (`FOAT_X1000`); it is a journal data defect to raise with the
  journal's owner.
- `forecast-oat` is a forecast for the hour, not a measurement. Beech's
  `oat` channel ends 2025-08 and oak's reads only late 2024, so neither
  covers the window.
- The vendored snapshot cannot decode `layout.lite` 003, which the
  houses emitted before 2025-10, so the 2024–25 season has no
  word-sourced encodings. It is outside this pull; a second pull with
  hand-mapped encodings, noted as such, would add beech's and oak's
  2024–25 winter.
- Beech's `primary-flow` reads 0 through every run from 2026-10-13
  while lift holds; flow there is excluded from this season's figures.
- Episode edges are known to five minutes: a step between standby and
  the 200 W state is under the 300 W report change and shows only at
  the periodic capture.

## Folder contents & experimental method

All data comes from the immutable store: `gridworks.readings` and the
`layout.lite` messages in the journal DB, re-pullable with the journal
login in `experiments/.env` (`DB_ANALYST_URL`). Nothing is generated by an
instrument of this experiment and no running system is touched. The
oak window stdout logs named in claim 7 are evidence recorded by
other runs, read as they are.

Three data files per house are kind-specific, not sema instances: no
word holds a heat pump operating interval reduced from channel
readings. They are typed records in `lg_records.py` with the note
naming the missing word, and each is committed (well under 2 MB). The
pull itself is regenerated and gitignored.

Support modules (imported, not run):

- `lg_common.py`: the houses, window, channels, staleness caps and run
  thresholds; loads the regen pull and puts it on a grid in natural
  units.
- `lg_records.py`: `Run`, `IdleEpisode` and `Dip`, the three committed
  files' shapes, with their dict form at the read/write boundary only.
- `../dist-loop-experiments/grid.py`: week chunks, ET midnights and
  conversion by each word's encoding, imported by `pull.py`.

Pull (journal DB):

- `pull.py`: one house's window, a week per query, to
  `<ta>-20251001.20261022-lg.readings-regen.npz` (NOT committed;
  gitignored by `*-regen.*`): per channel, reading times and values in
  natural units.
- `pull-<house>.log`: each week's `layout.lite` version and emission
  time, any channel a week lacks, and the reading counts.

Reductions (from the regen pull):

- `events.py`: compressor runs, idle episodes and dips, to
  `<ta>-20251001.20261022-lg.runs.json`,
  `<ta>-20251001.20261022-lg.idle.episodes.json` and
  `<ta>-20251001.20261022-lg.dips.json`.

Tables:

- `running.py`, `running.txt`: claims 1 and 2, from the runs files.
- `idle.py`, `idle.txt`: claims 3 to 7, from the episodes and runs
  files and, for standby and the time-since-stop shares, the regen
  pull; `--window-log` for claim 7.
- `defrost.py`, `defrost.txt`: claims 8 to 12, from the dips and runs
  files and, for the line scores, the regen pull.

Regenerate everything:

    uv run python pull.py --house beech > pull-beech.log
    uv run python pull.py --house oak > pull-oak.log
    uv run python events.py --house beech
    uv run python events.py --house oak
    uv run python running.py > running.txt
    uv run python idle.py > idle.txt
    uv run python idle.py --window-log ../../scratch/oak-window-20261020-174659.log --window-log ../beta-field-windows/runs/2026-10-20-1831-oak-second-window/oak-window-20261020-184437.log >> idle.txt
    uv run python defrost.py > defrost.txt

No `gw.readings` instance is written here, so there is no display CSV
step; the committed record files are read directly by the table
scripts.
