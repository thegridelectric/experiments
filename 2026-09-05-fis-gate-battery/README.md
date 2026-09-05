# fis-gate-battery, 2026-09-05

> What this is: stand-up-fis step 8 (OPS-422), the whole connect-time gate
> run against a real RabbitMQ 4.1.8 carrying rmqbot's gate overlay, on the
> dev universe (`d1__1`, every hop through localhost). Does the Fleet Index
> Service hold its five `/auth/user` verdicts, the vhost and topic rules,
> and single-writer supersession against a real broker, and stay fast
> under a reconnect storm? Verdict in "Found"; the logbook line is the
> index record. Nothing here touches prod. Only the staging run (step 9)
> counts as verification; this rung catches mechanical failures cheaply.

## Why

FIS's handler tests drive the endpoints in-process with a fake
connection-killer, so they cannot see the broker: how
`rabbitmq_auth_backend_http` encodes its calls, what the GridWorks SASL
mechanism hands over, whether the kill that enforces single-writer
(executor invariant 1) really closes the predecessor before the successor
is admitted, or what a hundred simultaneous connects cost inside the
broker's 10 s handshake timeout. Every one of those is a way the gate can
be green in pytest and wrong on a box. The battery drives the done-when
list from the design with real clients: gwbase's own credentials class and
claims word on AMQP, a cert-bearing paho client on MQTT, each verdict
witnessed twice, by the client's outcome and by the `auth_events` row FIS
recorded for it.

### Claims (the design's done-when list)

1. Allow for a valid active instance; deny for an unknown or suspended
   principal, a revoked instance, an alias or class claim that does not
   match the registry, a run outside the universe.
2. Run-claim ≠ vhost → deny at `/auth/vhost`.
3. Two instances racing → ordered supersession: the predecessor's
   connections are closed before the successor is admitted; management
   API down → the successor is denied (fail closed).
4. Clean restart (nothing to kill) → admitted without delay.
5. A stale-alias publish is denied at `/auth/topic`; a forged
   `user_id` is refused by the broker itself.
6. Auth stays fast under 100 concurrent connects.

## Setup

Isolation: a second broker container (`fis-gate-broker`) beside
`gw-dev-rabbit`, on its own ports (TLS-only 5671 and 8883, management
15673); a throwaway CA and client certs that never leave `certs/out/`; the
dev FIS database on `fis-postgres` (5437), which the battery truncates on
every FIS boot; the local grid-node-registry façade on 8000 as the mirror
source. No prod credential, host, or broker is referenced anywhere.

- **Code under test:** gridworks-fleet-index-service `jm/stand-up-fis`
  `4d7e6d6`; gridworks-infra `jm/fis-gate-conf` `4c1fc1e` (the gate
  overlay and the mechanism source); gridworks-base `dev` `409e36b` (the
  claims credentials class and the `d1` definitions); grid-node-registry
  `dev` `274b974` (the dev universe the identities come from).
- **Broker:** stock `rabbitmq:4.1.8-management`, `rabbitmq.conf` here
  (listeners, TLS, definitions, the `ssl_options` tightening a staging box
  carries from day one), plus the SAME `fis-gate.conf`, `enabled_plugins`
  and mechanism `.ez` a box mounts through `compose.gate.yaml`, mounted
  file by file from `../../gridworks-infra/rmqbot/`. One harness-only
  fragment, `40-dev-fis-url.conf`, repoints the gate's localhost auth URLs
  at the host, where FIS runs.
- **Identities:** the dev universe's `d1.isone.me.weather` (a GNode
  service), the beech scada and its LTN (GNodes with registry aliases),
  `STORM` service principals for the storm, and one never-minted id for
  the unknown-principal case. `setup.sh` resolves the GNode ids through
  the gnr façade, `mint.py` mints the principal rows on the dev FIS
  database, `certs/gen_certs.sh` cuts one client cert per identity with
  the principal id as CN.
- **Clients:** `battery.py` (pika over TLS with gwbase's
  `GridworksClaimsCredentials` for AMQP; paho for MQTT) and `storm.py`
  (N pika connects at once). `battery.py` starts and stops the FIS
  process itself, so it can run legs with a wrong management password.

### Runbook (build → services → rig → battery → read → teardown)

One machine. Every command runs from this folder unless the step says
otherwise; one command per block, in order. A full run takes about 90 s
after the rig is up.

**Preconditions.** Docker Desktop is up. `gw-dev-rabbit` may be running;
it owns 5672, 1885 and 15672 and is not touched. Ports 5671, 8883, 15673
and 8080 are free (nothing else serving FIS). `gnr-postgres` (5435) is up
and seeded with the dev universe (grid-node-registry README, "seed").

**1. Build the mechanism plugin (in gridworks-infra).** Compiles the
GridWorks SASL mechanism inside the pinned 4.1.8 image, so it needs
Docker; the `.ez` it writes is what the overlay mounts. Skip when the
file already exists for this image pin.

    cd ../../gridworks-infra/rmqbot/auth-mechanism

    ./build.sh

    ls -l rabbitmq_auth_mechanism_gridworks-0.1.0.ez

    cd ../../../experiments/2026-09-05-fis-gate-battery

**2. Start the registry façade (in grid-node-registry, its own
terminal).** The mirror source. Leave it running for the whole session.

    cd ../../grid-node-registry

    uv run gnr api

**3. Bring up the FIS database (in gridworks-fleet-index-service).**
`fis-postgres` on 5437, migrated to head. The battery truncates its
`leases`, `auth_events` and `g_nodes` tables on every FIS boot, so
nothing you want to keep belongs in this database.

    cd ../../gridworks-fleet-index-service

    docker compose up -d

    uv run alembic upgrade head

    cd ../experiments/2026-09-05-fis-gate-battery

**4. Check the façade answers.** The rig setup resolves ids by alias
through it; this is the call it makes first.

    curl -sf http://localhost:8000/gnr/g-node-by-alias/d1.isone.me.weather | head -c 200

**5. Mint principals and certs (once; idempotent).** Writes
`certs/out/ids.env` (NAME=principal-id lines), `g_node/weather.json` (the
weather GNode record the honest GridworksActor leg loads), and one
`certs/out/<name>.pem` per identity. `run.sh` runs this itself when
`ids.env` is missing; run it by hand to change the storm size.

    STORM=100 ./setup.sh

**6. Run the battery.** Brings the broker up (`docker compose up -d`
here), waits for it, prints the two gate plugins as `plugin:` lines, then
runs `battery.py` (which starts FIS, drives every case, stops FIS) and
`storm.py`. Evidence lands under `runs/<UTC stamp>/`.

    ./run.sh

**7. Read the result.** The last battery line is the tally; the storm
line is its own PASS/FAIL. Then the per-run folder: `battery.log` (one
line per case), `battery.json` (the same, structured), `fis.log` and
`fis-storm.log` (uvicorn plus the kill warnings), `storm.json` (connect
percentiles).

    tail -3 runs/$(ls runs | tail -1)/battery.log

    cat runs/$(ls runs | tail -1)/storm.json

**8. Keep the evidence.** A green run's log and storm summary are copied
beside this README under the date; a re-run makes a new dataset.

    cp runs/$(ls runs | tail -1)/battery.log battery-<DATE>.log

    cp runs/$(ls runs | tail -1)/storm.json storm-<DATE>.json

**9. Teardown.** Stops the harness broker (its runtime state is
disposable: users and topology reload from the definitions on the next
up). `gw-dev-rabbit`, `fis-postgres` and the gnr façade are left as they
were; stop the façade with Ctrl-C in its terminal.

    docker compose down

### Expected output

- `run.sh` prints `plugin: rabbitmq_auth_backend_http` and
  `plugin: rabbitmq_auth_mechanism_gridworks` before the cases.
- the battery ends with `26/26 cases pass`; two unscored lines appear in
  the middle, `KNOWN-GAP run_claim_vs_vhost_with_live_lease` and
  `KNOWN-LIMIT broker_wide_kill_closed_other_run: B closed=True`.
- the storm ends with `PASS  storm: 100/100 allowed, max connect <1s`.
- `supersession_predecessor_closed` reports `B allow in ~6s`, not
  sub-second: the battery's predecessor never answers the close (see
  Analysis notes). `clean_restart_admitted_fast` reports under 0.5 s.

## Found

**All six claims PASS on the green run (15:16 ET): 26/26 verdicts, storm
100/100 allowed with connect p50 0.43 s and max 0.63 s.** Five runs today;
the first found the blocking defect below and the middle three measured
two candidate fixes that failed in different ways. Evidence:
`battery-2026-09-05.log`, `storm-2026-09-05.json`.

1. **Claim 1, the five user verdicts: PASS.** Allow, unknown principal,
   suspended principal, revoked instance, alias mismatch, class mismatch,
   run outside the universe, each with the matching `auth_events` reason.
2. **Claim 2, run-claim vs vhost: PASS for a fresh principal, KNOWN-GAP
   for a principal already leased on the vhost** (unscored). The vhost
   call carries only `username`+`vhost`+`ip`, so FIS answers it by "does
   this principal hold an active lease on this vhost". A principal with a
   live lease there opens the vhost even though this connection claimed a
   different run at `/auth/user`. The executor's rule holds only when the
   principal has no lease on the vhost. Reported for OPS-422; the fix is a
   design decision (teach the vhost path the claimed run), not a battery
   bug.
3. **Claim 3, ordered supersession: PASS, after a defect and two dead
   ends.** The 12:24 run failed it (`weather live now=2`): FIS found and
   confirmed the predecessor's connections through `GET /api/connections`,
   which the broker serves from its stats database, refreshed every
   `collect_statistics_interval` (5 s). A predecessor younger than the
   last tick was unlisted, so the kill closed nothing, confirmed "empty",
   and admitted the successor beside it. The shipped fix: one
   `DELETE /api/connections/username/<id>` (live state, no enumerate
   step) and a confirm that polls `GET /api/connections/username/<id>`,
   which the broker serves from its connection-tracking table: it lists a
   connection the stats listing cannot see yet, answers in milliseconds,
   and holds MQTT connections too. Two confirms tried first were not
   usable: `rabbitmqctl list_connections` asks every reader process for
   its info, and the successor's own reader is blocked mid-handshake
   waiting on FIS, so against an 8 s auth hang the listing returned after
   6.5 s (a circular wait); `rabbitmqctl eval` on the tracking table
   answered in 0.4 s but boots an Erlang VM per call, and the storm then
   pushed every connect past 9 s of the 10 s handshake. Fail-closed
   with a wrong management password: PASS.
4. **Claim 4, clean restart: PASS** at 0.05 s. The 12:24 run failed it
   at 4.2 s for the mirror-image reason: a just-closed connection lingered
   in the stats listing.
5. **Claim 5, topic and user_id: PASS** on AMQP and MQTT (own alias ok,
   stale alias closed 403, forged `user_id` closed 406, non-uuid MQTT
   client_id refused, no-cert TLS refused).
6. **Claim 6, the storm: PASS** at max 0.63 s.

**A predecessor that never answers the close stays tracked.** The broker
sends `Connection.Close` and waits for `Close-Ok`; the battery's idle pika
client (a stand-in for a wedged actor) never answers, so its reader sat in
the closing state, routing nothing, and its tracking row stayed for 20 s
and counting. A second close on a reader already closing forces it down
at once, so the kill is two-phase: close, 1 s grace, close again, confirm.
Even forced, the reader then lingers 5 s in the TLS socket close (OTP's
wait for a close_notify the peer never sends), so the confirm budget is
8 s: a wedged predecessor's successor is admitted in one connect at about
6.5 s, a responsive one's in well under a second.

**KNOWN-LIMIT, broker-wide kill** (unscored). close-by-username is
broker-wide for the identity, so the `d1__2` attempt in claim 2 also
closes weather's `d1__1` connection. Exact while a broker hosts one run
(the staging and prod posture); the dev broker hosts both. A vhost-scoped
kill would read the tracking table's per-connection vhost and pid.

## Timeline

Times ET. Runs are named by their UTC stamp under `runs/`.

- 12:01–12:20 rig shakedown (six runs): form-encoded auth params,
  AMQP service principals denied `NotInRegistry`, the `.ez` mount. Fixed
  in FIS `7280642`.
- 12:24 first full run, 24/26: supersession admits beside a live
  predecessor, clean restart denied at 4.2 s. Finding A recorded in the
  design.
- 15:00 run with close-by-username and a `rabbitmqctl list_connections`
  confirm: every supersession denied `KillUnconfirmed` at 5 s. Probe
  against an 8 s auth hang: listing 6.5 s, tracking table 0.4 s.
- 15:04 confirm moved to `rabbitmqctl eval` on the tracking table:
  26/27, the one failure being the broker-wide kill closing the `d1__1`
  connection on the `d1__2` leg; supersession admitted only on the
  client's retry at 10.5 s (the idle predecessor).
- 15:09 two-phase close added: the forced close drops the reader at once,
  the row lingers 5 s more (TLS close wait); case 12 crashed on a
  connection the fail-closed leg had already killed.
- 15:11 budget 8 s, grace 1 s: 27/27, storm 100/100 but p50 9.3 s, max
  9.9 s, every confirm an Erlang VM.
- 15:16 confirm moved to `GET /api/connections/username/<id>` after the
  probe showed it tracking-backed and non-blocking: 26/26, storm max
  0.63 s. Green.

## Analysis notes

- `allow in N s` on a supersession case is one client connect that
  includes the whole kill: close, grace, forced close, and the broker's
  5 s TLS close wait for a peer that is not reading. The battery's
  predecessor is a pika `BlockingConnection` that nobody services, so it
  never answers `Connection.Close` or the close_notify; a live actor
  answers both in milliseconds and its successor connects in under a
  second. About 6.5 s is the wedged-predecessor figure, by design.
- KNOWN-GAP and KNOWN-LIMIT lines are logged, not scored; the tally
  counts `case(...)` lines only. There are 26 of them.
- A `deny-user` outcome is pika's `ProbableAuthenticationError`,
  `deny-vhost` its `ProbableAccessDeniedError`; a `closed 403`/`406` is
  the channel or connection closed by the broker on publish.
- The storm's bar is every connect allowed and max under 5 s; the
  broker's `handshake_timeout` is 10 s and the http backend's
  `request_timeout` 15 s, so an auth call slower than 10 s fails the
  handshake before the backend gives up.
- The FIS process runs on the host under `uv run --project`, so its
  `.env` is not read; `battery.py` passes the rig's settings as
  environment (`FIS_RABBIT_MGMT_URL=http://localhost:15673`, the
  `smqPublic` administrator from the dev definitions, the gnr URL).

## Folder contents & experimental method

All data in this folder is GENERATED by the harness on the dev machine;
none of it is in the journal DB or the S3 eventstore (the harness broker
forwards nowhere and FIS joins no broker). A re-run produces a new
dataset under `runs/`, never a regeneration. The experiment stops no
service: it starts its own broker and its own FIS process and ends them
itself; `gw-dev-rabbit`, `fis-postgres` and the gnr façade are used as
found. The one running-system side effect is the truncation of the dev
FIS database's `leases`, `auth_events` and `g_nodes` tables at each FIS
boot.

- `README.md` — this record.
- `docker-compose.yml` — the harness broker: stock 4.1.8 with gwbase's
  `dev_definitions.json` and the rmqbot overlay files mounted from
  `../../gridworks-infra/rmqbot/`, plus `40-dev-fis-url.conf`.
- `rabbitmq.conf` — the box-side conf the overlay layers on (listeners,
  TLS, definitions, the `ssl_options` tightening).
- `40-dev-fis-url.conf` — harness-only conf.d fragment repointing the
  four auth URLs at `host.docker.internal:8080`.
- `run.sh` — the whole run: rig check, broker up, battery, storm.
- `setup.sh`, `mint.py`, `certs/gen_certs.sh` — identities: id lookup
  through the gnr façade, principal rows on the dev FIS database, the
  throwaway CA and per-identity client certs. Outputs (`certs/out/`,
  `g_node/`) are gitignored: keys, and a registry record re-pulled on
  every setup.
- `battery.py` — the verdict battery; `storm.py` — the reconnect storm.
  Harness code, no data.
- `battery-2026-09-05.log`, `storm-2026-09-05.json` — the green run's
  case log and storm summary (generated; copied from
  `runs/20260905T1916/`). Earlier runs' evidence stays local under
  `runs/`, gitignored.
- `runs/` — per-run evidence, gitignored (`.gitkeep` holds the folder).

Regenerate everything from scratch: the runbook above, steps 1 to 6.
No `gw.readings` instance: the evidence is the case log, the storm
summary, and FIS's `auth_events` rows on the dev database.
