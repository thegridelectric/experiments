# disentangle-dev-run, 2026-10-21

> What this is: OPS-473 run end to end on the laptop's `d1` stack before anything merges to `main`: a new
> house (cedar) enters the dev registry and a dev PII store with scrambled
> person data, its layout and operating status travel the dev broker into
> journalkeeper's projections, and web-backend serves them to the
> dashboard as `gw.house.summary`. Verdict: PASS for every unattended step
> and the two operator steps that ran here; the dashboard screenshots
> (step 8) are the one step still open. The logbook entry is the index
> record.

## Why

The unit suites of gw_data, journalkeeper and web-backend share a wall
clock and a backdoor transport: web-backend's tests seed `layouts` and
`house_operating_status` rows by hand, journalkeeper's tests call the
projections directly. None of them shows that a word sent on a broker
ends as a row the dashboard reads, that the house is keyed by the id the
registry minted, or that nothing about a person leaves the PII store. The
work of OPS-473 merges on this run.

## Setup

All on the laptop, nothing on a deployed box. Code under test:

| part | checkout | note |
|---|---|---|
| sema | `dev` @ `65f489b` | worktree in the session scratchpad |
| gridworks-data | `main` @ `32c8164` | 0.7.0; local `tsdb` migrated to `d4a7c9e1b2f3` |
| journalkeeper | `jm/house-status-projection` @ `b49c94e` | snapshot from sema `f8a5e50`, `--allow-staged` |
| web-backend | `jm/retire-installations`, uncommitted | summaries through the codec, `gw.house.summary`; API port and broker TLS settings added for this run |
| web-frontend | `jm/retire-installations`, uncommitted | `src/sema` mirrors of the two words |
| grid-node-registry | `main` | the `d1` instance already running (`gnr rabbit` since 2026-10-07), `gnr api` on 127.0.0.1:8000 for the bootstrap |
| gridworks-pii | `main` | dev store on `localhost:5441`, fresh migration |
| gridworks-scada | `jm/spruce-unlimbo` | the Nolan sim fixtures with the alias and TA id changed to cedar's, in a scratch config home |

Broker `gw-dev-rabbit`, vhost `d1__1`, as `smqPublic`; database the local
`gw-data-pg` on 5433. Journalkeeper and the backend used the creds in the
laptop's gjk `.env`; the backend's own `.env` (gitignored) points at the
dev broker without TLS and at port 8001, then 8000 for the frontend's
proxy once the scada was stopped.

## Found

**PASS, 15 of 15 harness checks plus the gateway seed and the
not-reporting step.** `logs/harness.json` has every check with what was
seen. The harness, rewritten to build and decode every word through the
vendored snapshot (`gw` envelope, `layout.lite` 012,
`gw.house.operating.status` 000, `gw.house.summary` 000 decoded
strictly), passed 15 of 15 again on the same stack
(`logs/harness-rerun.json`).

- **Registry and store (steps 1, 2).** `gnr create` entered cedar's LTN
  and TerminalAsset as Pending; the registry minted
  `1f1a7314-026b-4a25-a0fc-2cef257671f1` for the TA. `gwpii add-customer`
  took the scrambled household and minted `HH-382`; three change rows name
  the operator. Nothing about the person went over the broker.
- **Layout path (step 3).** A `layout.lite` 012 published as cedar's
  scada is journaled and projected into `layouts` keyed by the registry's
  TA id, `sent_at` equal to the word's `MessageCreatedMs`, `from_alias`
  the scada.
- **Operating status (step 3).** With no status word from the scada,
  journalkeeper derived a `house_operating_status` row from the layout and
  the newest snapshot (`source = derived`). A `gw.house.operating.status`
  published as the scada replaced it (`source = scada`, `created_at` the
  word's `CreatedMs`); an older status word did not regress it.
- **Summaries (step 4).** `GET /api/v2/installations/*/summaries` returns
  `gw.house.summary` instances: cedar's `TaGNodeId` is the registry's,
  `DisplayName` the registry's, `Layout` the 012 verbatim,
  `OperatingStatus` the status word verbatim, `Role` `Admin`. No address,
  contact, hardware layout or params field.
- **Gateway seed (step 5).** Started with the scada stopped: "Seeded 1 of
  1 layouts rows"; `/gateway/health` shows cedar `layout_loaded` true,
  `snapshot_loaded` false, zero messages, a minute on.
- **Layout change (step 6).** A 012 with `SystemMode` Standby moved the
  row and the summary. The gateway's websocket status message was not
  captured.
- **Replay guard (step 7).** The step-3 body republished with its original
  stamp left the row unchanged; journalkeeper logged "send time … is
  older than the row's … — write skipped" (`logs/step7-gjk-skip-line.log`).
- **Not reporting (step 9).** The 24 h snapshot bound is fixed in the
  query, so cedar's snapshot messages were backdated two days in the dev
  database with the scada stopped: the summary keeps `Layout` and
  `OperatingStatus` and omits `LatestSnapshotTime`.
- **No person anywhere (step 10).** The scrambled name, street and email
  domain appear in no gw_data table, no API response and nowhere in the
  broker capture. Only the store has them.

Two gaps the run uncovered, both on the scada side of the status word:

1. **The sim scada on `jm/spruce-unlimbo` sends `layout.lite` 013.**
   Journalkeeper's snapshot is current at 012, so the message decodes
   degraded and no `layouts` row is written (`logs/gjk.log`, "Degraded
   decode for layout.lite v013"). The harness published a 012 to exercise
   the path. The summary word's `Layout` names 011 and 012; 013 enters the
   summary, journalkeeper and the gateway together when it is promoted.
2. **The scada sends `gw.house.operating.status` with `UnixMs`.** The
   word's field is `CreatedMs` since sema `f8a5e50`; journalkeeper logged
   "Validation failed … CreatedMs Field required" on the scada's own status
   at boot. The scada's snapshot regen is what makes the scada-sent path
   live; until then every house gets a derived row.

Step 8, the dashboard against the API, was left for a person: the dev
server is at `http://localhost:5174/gridworks-web-frontend/` with the dev-run login in `experiments/.env` (`DEVRUN_API_USER`,
`DEVRUN_API_PASSWORD`)
while the stack is up; the runbook restarts it.

## Timeline

All ET, 2026-10-21.

- 14:44 `gnr create` cedar LTN and TA (`logs/step1-gnr-create.log`).
- 14:45 `gwpii add-customer`, label HH-382 (`logs/step2-pii-add-customer.log`);
  broker capture started.
- 14:46 journalkeeper started; forest bootstrap projected 30 nodes from
  the dev registry's API; harness admin login seeded; API on 8001.
- 14:47 cedar sim scada started: snapshots, glitches, power, heating
  forecast journaled; the 013 layout and the UnixMs status refused.
- 14:49 summaries before any layout row: cedar listed, no `Layout`.
- 14:50:46 to 14:51:14 harness: steps 3, 4, 6, 7, 10, 15/15.
- 14:51 scada stopped; gateway started, seed line, health.
- 14:52 not-reporting step; API moved to 8000, frontend dev server up.
- 15:38 sema-typed harness against the API on 8000, after clearing
  cedar's `house_operating_status` row so step 3 starts from none: 15/15.

## Analysis notes

- The harness acts as cedar's scada: the envelope and routing keys are
  the ones the sim scada used, read off the capture
  (`gw.<hyphenated scada alias>.to.ltn.<type-with-dashes>` on
  `amq.topic`, which the dev broker binds into `ear_tx`).
- The API's role value comes from the roles table in lowercase and is
  served as the `gw.dashboard.role` enum (`Admin`); the frontend's role
  checks follow.
- `BACKEND_API_PORT` and `BACKEND_RABBIT_TLS` are the two settings the
  run needed in web-backend: the laptop keeps 8000 for the scada, and the
  dev broker speaks plain AMQP.

## Folder contents & experimental method

Every file here was GENERATED by this run on the laptop's dev stack; none
came from the immutable store, and no deployed service was touched. A
rerun produces a new dataset.

- `harness.py` — the unattended steps (3, 4, 6, 7, 10) as checks; prints
  one line per check and writes the result JSON. `logs/harness-rerun.json`
  is this script's; `logs/harness.json` is the 14:50 run's, from the
  harness before its sema rewrite.
- `runbook.md` — every command as run, in order, with the restore step.
- `captures/broker-capture-20261021-144514.jsonl` — every message on the
  dev broker from 14:45 to the scada's stop, from `capture_broker.py`.
  The evidence for step 10 and for the envelope the harness mirrors.
- `logs/` — one file per step and per service: the registry creates, the
  store record, the scada, journalkeeper, API, gateway and frontend
  stdout, the summaries before any layout, the gateway health, the
  journalkeeper skip line, the not-reporting check, the harness run.
- `instances/disentangle.dev.run-gw.experiment.run-001.json` — the run's
  verdict as a sema instance.

Regenerate from scratch: the runbook, top to bottom; the harness alone,
with the stack up:

    uv run python 2026-10-21-disentangle-dev-run/harness.py --db-url "$DEVRUN_DB_URL" --api-base http://127.0.0.1:8000 --out 2026-10-21-disentangle-dev-run/logs/harness-rerun.json

No `gw.readings` instance is in this folder; a display CSV does not apply.
Print the checks from the result:

    python3 -c "import json; [print(c['Passed'], c['Step'], c['Name']) for c in json.load(open('2026-10-21-disentangle-dev-run/logs/harness-rerun.json'))['Checks']]"
