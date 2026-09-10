# pico-state-journal-dev-rung, 2026-09-10

> What this is: does the journalkeeper turn the pico-cycler's per-pico
> `machine.states` rows into `<node>-pico-state` channel readings, on the
> dev broker, before the house line is pulled onto spruce? PASS for the
> channels and the Alive → Flatlined flip; two side findings below.

## Why

The pico-cycler on `actual-spruce` (`69d5d6ec`) reports each pico's
`single.pico.state` through `machine.states`, and the journalkeeper on
`dev` (`3a8bc57`) gives every pico-backed node a `<node>-pico-state`
channel and projects those rows into it. Neither had been run against
the other outside pytest. The spruce pull is the next step, and a
report that arrives before the journalkeeper knows the channels only
tallies dropped rows, so the pairing had to be seen working here first.

## Setup

Laptop, all local. Dev broker `gw-dev-rabbit` (AMQP 5672 vhost `d1__1`,
MQTT 1885, TLS off; `amq.topic` is bound to `ear_tx` with `#`, so the
scada's MQTT traffic reaches an AMQP tap). A fresh database
`tsdb_devrung` in the `gw-data-pg` container (timescaledb extension,
`gridworks` schema, gridworks-data alembic head `a7f151e8163f`); the
existing `tsdb` there holds the OPS-498 back-fill and was left alone.
Journalkeeper `3a8bc57` from `run_journal_keeper.py` with `GJK_DB_URL`
pointed at the fresh database, everything else from the repo `.env`
(alias `d1.journal`).

Scada `gridworks-scada` at `actual-spruce` `69d5d6ec` in the main
checkout, layout `tests/config/nolan-layout.json` (two
`sim.pico.tank.module.component.gt` tanks, alias
`d1.isone.ct.newhaven.orange1.scada`), `SCADA_IS_SIMULATED=true` (the
house line imports the Pi relay driver otherwise), cycler state logging
on, `seconds_per_report` 60. An LTN from the same checkout (`gws ltn
run`, same layout) as the scada's upstream peer, because the scada
sends `layout.lite` on link activation and uploads its `report.event`s
only over an active link; without a peer the link sits in
`awaiting_peer` and nothing the journal needs crosses (the 09-07 and
09-08 dev runs collected reports from the scada's disk for that
reason).

A first attempt used the `jm/spruce-unlimbo` scada (the panel commit, since squashed to `ca53f6d2`) and
went nowhere for two reasons worth keeping: that line emits
`layout.lite` 013, which is staging, and the journalkeeper's seed pins
the published set ending at 012; and it ran without an LTN. The
actual-spruce line emits 012.

## Found

**PASS.** From the scada's `layout.lite` 012 the journalkeeper created
`buffer-pico-state` and `tank1-pico-state` (unit type
`single.pico.state`, terminal asset `d1.isone.ct.newhaven.orange1.ta`).
The readings, in time order: both picos Alive (0) at 15:36:33 UTC,
the cycler's start-up roster; both Flatlined (1) at 15:37:33 UTC. No
dropped-reading line in the journalkeeper log.

- **The cycler's own state is not a channel.** The pass condition
  named "the flatline row before the cycler's own state row", but the
  journalkeeper creates no `pico-cycler` state channel from this
  layout, so there is no such row to order against. In the scada log
  the cycle came first: the tank actors' `PicoMissing` moved the cycler
  `PicosLive → RelayOpening` at 15:36:36 UTC, and the Flatlined rows are
  the cycler's 60 s wait expiring at 15:37:33. `vdc-relay` has a
  channel and no readings in the window.
- **"No dropped tally" is not readable from the live path.** The live
  persistor keeps a `dropped_readings` counter but only the S3 importer
  prints it; the live log says nothing either way. The channels
  existing and the four readings being there is the evidence.
- **Sim picos on actual-spruce never post.** That line accepts the sim
  component but has no sim pico loop, so the roster goes Alive →
  Flatlined once and stays; a re-post after the cycle (Alive again) is
  not producible here. The unlimbo line's sim picos do post.
- **Laptop noise, not spruce's.** The scada event directory on this
  laptop held 90 stale event files from earlier runs (2026-03-30,
  04-23, 09-06 to 09-10, including the morning's unlimbo scada
  `report.event` 004s). The actual-spruce scada uploaded them all on
  link-active. The journalkeeper logged 35 "degraded report.event
  (v004), not persisting" warnings and persisted the 002/003 ones; the
  LTN's `gwproto` decoder failed on 004, so the link flapped
  active/awaiting_peer every 5 s on response timeout while the reports
  kept crossing. A box runs one scada and has no such backlog.

## Timeline

ET, 2026-09-10.

- 11:06 unlimbo sim scada up on the dev broker for the panel
  test-drive; no journalkeeper yet.
- 11:26 journalkeeper up on `tsdb_devrung`; unlimbo scada restarted
  11:26:42 so its boot-time layout would be seen. Only
  `single.machine.state`, `snapshot.spaceheat`, `single.reading` cross
  (capture 1); link `awaiting_peer`; `report.event` files accumulate on
  disk, one a minute.
- 11:33 unlimbo scada stopped; main checkout moved to `actual-spruce`.
- 11:36:02 LTN up. 11:36:03 scada exits on `No module named 'RPi'`.
  11:36:32 scada up with `SCADA_IS_SIMULATED=true`; link active at
  11:36:48; Alive rows at 11:36:33; `PicoMissing` cycle at 11:36:36;
  Flatlined rows at 11:37:33.
- 11:38 to 11:40 capture 2: `layout.lite` 012, `report.event` 002/003/
  004, `gridworks.event.comm.peer.active`, acks and pings crossing.
- 11:45 LTN, scada and journalkeeper stopped. The database stays.

## Analysis notes

Timestamps in `journal-readback.txt` are the scada's own (`UnixMsList`
of the `machine.states` row), UTC. The laptop clock is about a minute
ahead of the boxes (2026-09-06 check), irrelevant here since nothing
else was correlated. The value encoding is the enum index: Alive 0,
Flatlined 1, Zombie 2.

## Folder contents & experimental method

All data here was GENERATED by this experiment on the laptop: a plain
MQTT subscription on the dev broker, and the fresh local database the
journalkeeper wrote during the run, read back as rows and as the wire
messages it stored. None of it is in the production journal DB or the
S3 eventstore; a re-run produces a new dataset. No deployed service was
touched.

The typed record is `instances/`: the scada's `layout.lite` 012 as the
journalkeeper received it, and the three `report.event` 003 messages of
the run, each decoded through the vendored snapshot at its own version
before being written (the layout's 012 → latest upgrade needs the
source layout context, so decoding is at 012). The first report's
`StateList` carries the two Alive rows, the second the two Flatlined
rows, both under `StateEnum` `single.pico.state`; the third carries no
roster row. There is no `gw.readings` instance: `pull_readings.py`
builds one from the channel words in the scada's `layout.lite`, and the
pico-state channels are journalkeeper pseudo channels the layout does
not declare, so the tool drops them. That gap is noted, not worked
around; the readings are in the reports.

- `README.md` — this record.
- `mqtt_types.py` — the capture harness: subscribes to `#` on
  `localhost:1885` for N seconds and tallies (topic tail, TypeName,
  Version).
- `capture1-unlimbo-scada-types.txt` — 130 s tally with the unlimbo
  scada and no LTN (nothing the journal needs crosses).
- `capture2-actual-spruce-types.txt` — 90 s tally with the actual-spruce
  scada and the LTN peer.
- `journal-readback.txt` — the pico-state readings, the channels, the
  persisted message counts by type and version, and the journalkeeper
  log counts, with the query in the header. Re-run the query while
  `tsdb_devrung` exists.
- `instances/<scada alias>-devrung-layout.lite-012.json` — the layout
  the journalkeeper built the channels from, from
  `gridworks.messages` in `tsdb_devrung`.
- `instances/<scada alias>-devrung.<HHMM UTC>-report.event-003.json`
  (three) — the run's reports, from the same table, the roster rows in
  `Report.StateList`.

Regenerate from scratch (the database bootstrap once; four terminals
from the scada repo with `PYTHONPATH=$PWD/gw_spaceheat`, on
`actual-spruce`):

    docker exec gw-data-pg psql -U postgres -c "CREATE DATABASE tsdb_devrung OWNER gw_admin;"
    docker exec gw-data-pg psql -U postgres -d tsdb_devrung -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
    docker exec gw-data-pg psql -U gw_admin -d tsdb_devrung -c "CREATE SCHEMA gridworks; GRANT USAGE ON SCHEMA gridworks TO gw_journalkeeper;"
    (cd ../gridworks-data && GW_DATA_DB_URL=postgresql+psycopg://gw_admin:<pw>@localhost:5433/tsdb_devrung uv run alembic upgrade head)
    (cd ../gridworks-journalkeeper && GJK_DB_URL=postgresql+psycopg2://gw_admin:<pw>@localhost:5433/tsdb_devrung uv run python run_journal_keeper.py)
    LTN_PATHS__HARDWARE_LAYOUT=tests/config/nolan-layout.json gw_spaceheat/venv/bin/gws ltn run
    SCADA_IS_SIMULATED=true SCADA_PATHS__HARDWARE_LAYOUT=tests/config/nolan-layout.json SCADA_PICO_CYCLER_STATE_LOGGING=true SCADA_SECONDS_PER_REPORT=60 gw_spaceheat/venv/bin/gws run
    gw_spaceheat/venv/bin/python ../experiments/2026-09-10-pico-state-journal-dev-rung/mqtt_types.py 90 > capture.txt

Then the query in `journal-readback.txt`'s header against
`tsdb_devrung`, and the instances come from `gridworks.messages` there
(`from_alias` the scada's, `message_type_name` `layout.lite` or
`report.event`), decoded with `SemaCodec().from_dict(payload,
auto_upgrade=False)` before writing. No display CSV: the folder holds
no `gw.readings` instance.
