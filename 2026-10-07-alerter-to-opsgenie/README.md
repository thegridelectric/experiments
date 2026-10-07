# alerter-to-opsgenie, 2026-10-07

> What this is: does a `gw.alert` the broker alerter raises open an
> Opsgenie alert through the tap, and does the alerter's `Resolved`
> record close it, with the alerter and tap restarted while the alert
> is open? PASS on 2026-10-07 on a run whose mock started late; see
> Found.

## Why

The broker-alerter design (OPS-545) pages through Opsgenie: the tap
(`gwalerter tap`) consumes the alerter's one `gw.alert` word off its
mic exchange, creates an Opsgenie alert aliased by the `AlertId`, and
closes that alias on `Resolved`. The tests prove the mapping against a
recording transport; this run is the witness against Opsgenie itself,
the bar before the tap runs on the alerts box.

## Setup

Laptop, `gw-dev-rabbit` on `localhost:5672` (vhost `d1__1`), the dev
registry (`gnr api` on `localhost:8000`, `gnr rabbit`) serving the
seeded `d1` universe, and an Opsgenie Alert API integration key plus
the id of the team the run pages (`OPSGENIE_API_KEY`,
`OPSGENIE_TEAM_ID` in the environment of `run.sh`; nothing in this
folder holds either).

Five processes from `run.sh`: the alerter (`gwalerter rabbit`, fresh
store under the run dir, `NO_DATA_SILENCE_S` 30, `DETECTOR_TICK_S` 2,
fleet root narrowed to the mocked spruce), the tap (`gwalerter tap`,
`TAP_RECONCILE_S` 20, same store), the mock scada from
`../2026-09-15-alerter-no-data/mock_scada.py` (talk 20 s, quiet 60 s,
resume 20 s), then a second alerter and a second tap started on the
same store while the alert is open. Nothing deployed is touched; the
alert pages whoever the team's policy pages.

## Protocol

1. Alerter and tap up; the alerter's log shows spruce tracked; the tap
   logs its bind and a first reconcile pass.
2. The mock goes quiet. Within 30 s plus a tick the alerter raises
   `Firing` `NoData`, the tap logs the create, and Opsgenie lists an
   open alert whose alias is the `AlertId`, message
   `[spruce] No data from …`, entity the house alias.
3. The mock resumes. The alerter sends `Resolved` with the same
   `AlertId`; the tap logs the close; Opsgenie lists the alert closed.
4. Between 2 and 3 the alerter and the tap are stopped and restarted on
   the same store: the second tap's first reconcile re-creates the open
   alert, Opsgenie's `count` on it goes to 2 and no second alert
   appears; the second alerter is the one that resolves.

PASS is all four.

## Found

**PASS** (2026-10-07), all four, with two deviations from the runbook
as written, both recorded here and neither weakening the witness. Code
under test: `gridworks-alerter` `jm/gw-alert` working tree on `f0064a6`
(the Opsgenie tap in `src/gwalerter/tap.py`, `Store.resolved_record`,
the three Opsgenie settings; committed after the run).

- The mock scada did not start on the first launch (`run.sh` lacked
  the `PYTHONPATH` line the 2026-09-30 runbook had; fixed in the file
  since), so spruce was silent from the alerter's boot: `Firing`
  `NoData` raised 11:01:14.368Z, 30.1 s after boot, on boot silence
  rather than on the mock's quiet phase. The run script stopped at the
  mock's exit with the second alerter and tap running; the mock was
  then started by hand (`mock-2.log`, talk 20 s) and the rest of the
  protocol ran on the same processes and store.
- Opsgenie listed the alert open within 36 s of the raise with alias
  `3f449ad4-…`, message `[spruce] No data from
  d1.isone.me.versant.keene.spruce.ta since 2026-10-07 11:00:44Z`,
  `count` 1 (`opsgenie-firing.txt`).
- The second tap, started 11:01:53Z with the alert open, logged
  `Reconcile: creating 3f449ad4-…` and Opsgenie took it (202); the
  final listing shows that alias once, `count` 2, no second alert
  (`opsgenie-resolved.txt`, `opsgenie-resolved.json`).
- `Resolved` with the same `AlertId` at 11:02:37.227Z, 7 ms after the
  first mock report, sent by the second alerter; the second tap logged
  the close; Opsgenie lists the alert `closed`, closed by `Alert API`.
- Two further alerts appear in the listing, both `closed`, message
  `[spruce] No data from spruce`, created 11:00:47Z: `gw.alert` words
  the repo's live-broker test had published on the dev broker's
  `alertsmic_tx` during the day's CI runs, held in the durable
  `d1.alerts-tap` queue that the 2026-09-30 run left bound. The first
  tap consumed them at boot and created both; its first reconcile pass
  20 s later closed both, since the store held neither. The reconcile
  did what it is for, and the two pages were real: the alerter's test
  fixture carries a real-looking word, and a durable queue on a dev
  broker outlives its run.

## Timeline

2026-10-07, EDT (the alerter's log and the alert words are UTC, four
hours later).

- 07:00:44 alerter 1 up, tracking spruce; 07:00:46 tap 1 bound,
  creates the two stale test alerts; mock 1 fails at import.
- 07:01:07 tap 1 reconciles: closes both stale alerts.
- 07:01:14 alerter 1 raises `Firing`; tap 1 creates it.
- 07:01:50 Opsgenie listing: one open, two closed; alerter 1 and tap 1
  stopped.
- 07:01:51 alerter 2 and 07:01:53 tap 2 started on the same store; tap
  2 reconciles, re-creates the open alert (count 2).
- 07:02:36 mock 2 started by hand, talks; 07:02:37 alerter 2 sends
  `Resolved`; tap 2 closes.
- 07:03 Opsgenie listing: all three closed; everything stopped.

## Analysis notes

- Opsgenie's `GET /v2/alerts/{alias}?identifierType=alias` answers
  404 for a closed alert (`opsgenie-alert-3f449ad4.json`); the alias is
  an open-alert identity. The listing by `source` finds closed ones.
- The notifier's view of each alert (open or closed, count, closed by)
  is read off Opsgenie's listing through `notifier_view.py` into
  `gw.opsgenie.alert` words, one per alert the run touched. The
  verdict's facts are in those three instances and in the two
  `gw.alert` instances; the README states them.
- The reconcile pass is the tap's only memory across a restart, and
  it both re-creates and closes: an alert Opsgenie holds that the
  store does not is closed, which is right for a missed `Resolved` and
  was right here for test words, and would also close an alert whose
  store was replaced under a running tap. The store and the tap share
  one sqlite on purpose.
- Opsgenie deduplicates the re-create by alias (`count` 2) and sends
  no second page for it, so a tap restart does not re-page.
- The alerter's `last heard` restarts from boot time, so a tracked
  house silent since boot raises `NoData` after the threshold with no
  message ever received; the mock's absence is what showed it.
- Timing is sped up; the rule and the tap read every threshold from
  settings, so the run exercises the deployed code path at another
  scale.

## Folder contents & experimental method

All data here is GENERATED by this experiment on the laptop (dev
broker, dev registry) against the Opsgenie account the fleet pages
through; nothing from the journal DB or S3; a re-run produces a new
dataset and pages the team again. No deployed service was touched.

- `README.md`: this record.
- `run.sh`: the runbook; starts the alerter, tap and mock, captures
  logs to a run dir it prints, saves Opsgenie's raw listing twice and
  prints the typed view of each. The credentials come from the
  environment (`OPSGENIE_API_KEY`, `OPSGENIE_TEAM_ID`); nothing in this
  folder holds them. The evidence of 2026-10-07 came from the sequence
  `evidence/2026-10-07/provenance.txt` describes (the day's script
  exited early and the mock was started by hand), not from this fixed
  script in one pass.
- `notifier_view.py`: reads an Opsgenie listing into `gw.opsgenie.alert`
  words (alias, status, count, created, closed by, message, …) and
  prints one line each; what `opsgenie-*.txt` is derived from.
- `emit_instances.py`: writes `instances/` from the evidence: the two
  `gw.alert` records out of the archived store, the `gw.opsgenie.alert`
  words out of the saved listing, and the run record from the alerter
  file log's window.
- `evidence/2026-10-07/provenance.txt`: where each file came from, the
  sequence as run, the clocks, the redaction.
- `evidence/2026-10-07/`: the run's logs as captured (`run-stdout.log`,
  `tap-1.log`, `tap-2.log`, `alerter-1.log`, `alerter-2.log`,
  `d1.alerts.log` the alerter's file log, `mock.log` the failed first
  mock, `mock-2.log` the hand-started one), broker credentials
  redacted by pattern and nothing else changed; `opsgenie-firing.txt`,
  the firing listing as the day's script printed it (its raw JSON was
  not saved; the script saves it now), `opsgenie-resolved.json` the
  listing after the resume as Opsgenie returned it and
  `opsgenie-resolved.txt` its typed view; `opsgenie-alert-3f449ad4.json`
  the 404 by alias; `alerter.sqlite`, the alerter's store as the run
  left it.
- `instances/<house>-firing-gw.alert-000.json` and
  `instances/<house>-resolved-gw.alert-000.json`: the alert's two
  transitions, as the alerter recorded them.
- `instances/d1.alerts-tiny<N>-gw.opsgenie.alert-000.json`: each alert
  the run touched as Opsgenie listed it after the resume (the witnessed
  alert, tiny id 1250, `Closed`, count 2, closed by `Alert API`; the
  two stale test alerts, 1248 and 1249, count 1). Subject is the
  alerter's alias the listing was queried by, condition Opsgenie's tiny
  id, the number its console shows.
- `instances/gw.experiment.run-001.json`: the run record, `Verdict`
  Pass, `Claim` the executor's "The tap" section.

Run (gw-dev-rabbit, the dev registry and the alerter's `.env` in place):

    cd ~/GridWorks/experiments/2026-10-07-alerter-to-opsgenie
    OPSGENIE_API_KEY=… OPSGENIE_TEAM_ID=… ./run.sh
    # copy the run dir's logs and store into evidence/<date>/ (redact the
    # broker URL by pattern), then:
    uv run python emit_instances.py evidence/<date>

The notifier's view from a saved listing (no Opsgenie access needed):

    uv run python notifier_view.py evidence/2026-10-07/opsgenie-resolved.json

Read an instance back through the snapshot (no broker needed; prints
the word's fields, evidence included):

    uv run python -c "from gwexp.sema.codec import default_codec; from pathlib import Path; print(default_codec.from_bytes(Path('instances/d1.isone.me.versant.keene.spruce.ta-resolved-gw.alert-000.json').read_bytes()))"

No `gw.readings` instance lives here; there is no display CSV.
