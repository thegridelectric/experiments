# fis-gate-battery — the FIS gate on the dev universe

What this is: the re-runnable witness for stand-up-fis step 8 (OPS-422) — the
whole connect-time gate run against a real broker on the dev universe
(`d1__1`, all comms through localhost). It stands up a stock `rabbitmq:4.1.8`
carrying rmqbot's gate overlay (the SAME `fis-gate.conf`, plugin list and
mechanism `.ez` a staging or prod box mounts through `compose.gate.yaml`,
only the auth URLs repointed at the host), a real FIS against a local
Postgres and the local grid-node-registry mirror, and drives every done-when
verdict with real clients: gwbase's own credentials class and claims word on
AMQP, a plain cert-bearing paho client on MQTT.

Each verdict is witnessed twice — by the client's connect/publish outcome and
by the `auth_events` row FIS recorded for it.

Everything runs locally; nothing touches prod. This is the dev rung, which
catches mechanical failures cheaply; only the staging run (step 9) counts as
verification.

## Run

```shell
(cd ../../gridworks-infra/rmqbot/auth-mechanism && ./build.sh)   # the .ez the overlay mounts
(cd ../../grid-node-registry && uv run gnr api &)                # the mirror source on :8000
(cd ../../gridworks-fleet-index-service && docker compose up -d && uv run alembic upgrade head)
./run.sh          # setup (principals + certs) → broker up → battery → storm
```

`run.sh` writes evidence under `runs/<UTC stamp>/`: `battery.json` (every
case), `battery.log`, `storm.json`, and the FIS logs. `setup.sh` mints the
principals on the dev FIS db and cuts a throwaway client cert per identity
(CN = the principal id FIS gates on); it is idempotent.

## What it covers

The gate's five `/auth/user` verdicts (allow, unknown/suspended principal,
revoked instance, run-outside-universe, alias/class claim mismatch), the
`/auth/vhost` run cross-check, `/auth/topic` alias pinning (own-alias write
allowed, stale-alias write denied 403) on both AMQP and MQTT, the broker's
`validated-user-id` enforcement (own id ok, forged id refused 406), the
no-cert TLS refusal, the service-principal path (no registry alias), the
MQTT scada shape (client_id = instance id; a non-uuid client_id refused),
fail-closed when the management API is unreachable, and a 100-connection
reconnect storm (client-side connect latency well inside the broker's 10 s
handshake budget).

## Found

Two gaps the in-process tests could not see (they drive the handlers
directly and use a fake connection-killer), both in the run-scoped
supersession path, both reported for OPS-422:

1. **Supersession is not authoritative (single-writer, invariant 1).** FIS
   both finds the predecessor's connections and confirms none remain through
   the broker's **management HTTP listing** (`GET /api/connections`), which
   is served from the eventually-consistent stats database (refreshed every
   `collect_statistics_interval`, 5 s default). A predecessor younger than
   the last stats tick is **not listed**, so the kill targets nothing,
   confirms "empty", and admits the successor while the predecessor stays
   live — two authorized instances at once (`supersession_predecessor_closed`
   fails with `weather live now=2`). The same lag runs the other way on
   removal: a just-closed connection lingers in the listing, so a **clean
   restart** (nothing to kill) is denied `KillUnconfirmed` until the listing
   catches up (`clean_restart_admitted_fast` fails at ~4 s). The management
   listing is a monitoring view, not a real-time authority; the fix is a
   design decision (see OPS-422) — a vhost-scoped authoritative source such
   as `rabbitmqctl`, which crosses the FIS/broker container boundary that the
   HTTP API was chosen to avoid, or close-by-username
   (`DELETE /api/connections/username/<u>`, real-time and authoritative but
   broker-wide, so it would evict the identity's connections on other runs
   and break simultaneous multi-run leases).

2. **`/auth/vhost` cannot see the claimed run when a live lease exists**
   (`run_claim_vs_vhost_with_live_lease`, logged as KNOWN-GAP, unscored).
   The vhost call carries only `username`+`vhost`+`ip`, so FIS answers it by
   "does this principal hold an active lease on this vhost". When the
   principal already holds a lease on the opened vhost (a legitimate
   same-identity connection on another run), a second connection that
   *claimed* a different run at `/auth/user` opens the vhost anyway. The
   executor's rule ("run-claim ≠ vhost → deny") holds only when the
   principal has no lease on the vhost.

## Files

- `docker-compose.yml` — the stock 4.1.8 broker + the rmqbot gate overlay,
  mounted from `../../gridworks-infra/rmqbot/`, plus `40-dev-fis-url.conf`
  (harness-only: repoints the gate's localhost auth URLs at the host, where
  FIS runs). TLS-only 5671/8883; management 15673; beside `gw-dev-rabbit`.
- `rabbitmq.conf` — the box's own conf (listeners, TLS, definitions) with the
  `ssl_options` tightening a staging box carries from day one; the gate
  itself rides `conf.d` from the overlay.
- `setup.sh` / `mint.py` / `certs/gen_certs.sh` — principals, ids, certs.
- `battery.py` — the verdict battery; `storm.py` — the reconnect storm.
- `runs/` — per-run evidence (gitignored except this note keeps the folder).
