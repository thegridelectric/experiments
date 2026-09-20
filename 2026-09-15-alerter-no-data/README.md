# alerter-no-data, 2026-09-15

> What this is: does the broker alerter's NoData rule send one `gw.alert`
> in state `Firing` when a tracked house goes quiet past the threshold,
> and one `gw.alert` in state `Resolved` with the same id when its data
> resumes, on a real broker with real (sped-up) timing? Not yet run
> against `gw.alert`; see Found.

## Why

gwalert's no-data check reads the journal DB and its house list is
whatever its 2 h query returned, so a house with no reading in the window
is never checked (OPS-543). The broker alerter (`gridworks-alerter`,
OPS-545) replaces that with a rule over the store's last-heard, evaluated
on a detector thread, with open-alert state in sqlite and transitions
broadcast on the alerter's mic exchange. The unit tests drive the rule
with a fixed clock; this experiment is the first time the rule, the
detector thread, the broadcast path and a real consumer run together
against the dev broker. It is the EDD bar for the design's "Do this
next" step 3, and the shape of every later detector's witness.

## Setup

Laptop, `gw-dev-rabbit` on `localhost:5672` (vhost `d1__1`, the 0.5.13
hybrid definitions with `alerts_tx` / `alertsmic_tx`), the dev registry
(`gnr api` on `localhost:8000`, `gnr rabbit`) serving the seeded `d1`
universe. Prerequisites, each from its repo's top level:

    # gridworks-base: the dev broker
    ./arm.sh                      # or ./x86.sh
    # grid-node-registry: seeded dev registry, read API and broadcaster
    uv run python -c "from gnr.db.session import SessionLocal; from gnr.dev_universe import seed_dev_universe; s = SessionLocal(); seed_dev_universe(s)"
    uv run gnr api &  uv run gnr rabbit &
    # gridworks-alerter: venv and .env (gitignored; broker URL from the
    # registry's .env, same dev broker)
    uv sync && cp template.env .env    # then set GWALERTER_RABBIT__URL

The harness scripts import gwbase and pika, which this repo does not
carry, so they run in the alerter's venv
(`uv run --project ../../gridworks-alerter`) with this repo's sema
snapshot on the path (`PYTHONPATH=../src`); the alert words they decode
are the ones in `src/gwexp/sema_seed_request.yaml`. Four processes from
`run.sh`:

- `watcher.py`: an exclusive queue bound `#` on `ear_tx`; every
  `gw.alert` on the bus is decoded
  through the alerter's vendored snapshot, printed with the routing key,
  and written to `instances/` as a sema instance.
- the alerter, `gwalerter rabbit`, with a fresh store (`XDG_DATA_HOME`
  in the run dir) and sped-up timing: `GWALERTER_NO_DATA_SILENCE_S=30`,
  `GWALERTER_DETECTOR_TICK_S=2`, and `GWALERTER_FLEET_ROOTS` narrowed to
  the one mocked house so no other dev house pages.
- the alerter again, started on the same store while the alert is open,
  so the restart rule is witnessed in the same run.
- `mock_scada.py`: publishes a wrapped `report.event` as
  `d1.isone.me.versant.keene.spruce.scada` on `amq.topic` every 5 s for
  20 s, goes quiet for 60 s, then resumes for 20 s. Each report is built
  through the snapshot classes: one channel, one reading at the current
  time, in the current 5 min slot.

Nothing deployed is touched. Logs go to the run dir, not the folder.

## Protocol

1. `./run.sh` starts the watcher, the alerter, then the mock scada
   (talk 0 to 20 s, quiet 20 to 80 s, resume 80 to 100 s). At 65 s,
   with the alert open, it stops the alerter and starts a second one on
   the same store; after the mock ends it stops everything.
2. PASS is exactly one `gw.alert` with `State=Firing`, `Kind=NoData`,
   about `d1.isone.me.versant.keene.spruce.ta`, `RaisedMs` no earlier
   than 30 s after the mock's last talking-phase report and before its
   first resume report, and exactly one `gw.alert` with `State=Resolved`
   and the same `AlertId`, `ResolvedMs` at the first resume report,
   `Evidence` holding that report's channel readings. The second alerter
   sends nothing while the alert is open (the open alert is in the
   store) and is the one that resolves it. Any second firing word, any
   word about another house, or a missing resolved word is FAIL.

## Found

Not run against `gw.alert`. No verdict and no instances until it is.
Before the run, confirm the alerter checkout under test sends `gw.alert`
and record its branch and commit here as the code under test.

## Analysis notes

- `run.sh` stops its background jobs with SIGTERM, children first, and
  stops the alerter four seconds after the mock ends. SIGINT does not
  work: a background job of a non-interactive shell ignores it (POSIX;
  python inherits the ignore). An alerter left running past the mock
  correctly raises a second alert 30 s after the last resume report.
- Timing is sped up (30 s threshold, 2 s tick) against the deployed
  10 min / 10 s; the rule reads both from settings, so the run exercises
  the same code path at a different scale.
- The alerter's clock is the laptop's wall clock; `RaisedMs` and
  `ResolvedMs` are the alerter's arrival times, not the scada's read
  times.

## Folder contents & experimental method

All data here is GENERATED by this experiment on the laptop's dev broker
(nothing from the journal DB or S3); a re-run produces a new dataset. No
deployed service was touched.

- `README.md`: this record.
- `run.sh`: the runbook; starts the three processes and captures logs to
  a run dir it prints.
- `mock_scada.py`: the mocked scada (talk / quiet / resume phases).
- `watcher.py`: the bus tap that writes the alert words to `instances/`.
- `instances/<house>-firing-gw.alert-000.json` and
  `instances/<house>-resolved-gw.alert-000.json`: written by the run, the
  alert's two transitions as witnessed on the bus (sema instances;
  filename grammar `<subject>-<condition>-<type.name>-<version>.json`,
  subject = the house alias, condition = the alert's state).

Run (prerequisites above up):

    cd ~/GridWorks/experiments/2026-09-15-alerter-no-data
    ./run.sh

Read an instance back through the snapshot (no broker needed;
prints the word's fields, evidence included):

    cd ~/GridWorks/experiments/2026-09-15-alerter-no-data
    uv run python -c "from gwexp.sema.codec import default_codec; from pathlib import Path; print(default_codec.from_bytes(Path('instances/d1.isone.me.versant.keene.spruce.ta-resolved-gw.alert-000.json').read_bytes()))"

No `gw.readings` instance lives here; there is no display CSV.
