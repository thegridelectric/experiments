# disentangle-dev-run — runbook

The commands as run on 2026-10-21, from the umbrella dir unless a `cd`
says otherwise. Secrets come from the laptop's `.env` files and are not
in this file: `DEVRUN_DB_URL` is `GJK_DB_URL` from
`gridworks-journalkeeper/.env` in psycopg form: the local dev
`gw-data-pg` on port 5433, not the prod journal DB.

## Pre-flight

- `gw-dev-rabbit` up (`docker ps`), vhost `d1__1`, `ear_tx` present.
- `gw-data-pg` up on 5433: `docker start gw-data-pg`.
- The `d1` registry's write loop running (`pgrep -f "gnr rabbit"`), else
  `cd grid-node-registry && uv run gnr rabbit`.
- Port 8000 free for the scada; the registry's read API and the backend
  API take it only while the scada is stopped.
- sema checkout clean at `dev`, or a worktree of it for the regens.

## Stack

```sh
# local journal DB at head (gridworks-data main)
cd gridworks-data && GW_DATA_DB_URL="<admin creds>@localhost:5433/tsdb" uv run alembic upgrade head

# dev PII store
cd gridworks-pii && docker compose up -d
set -a; . ./.env; set +a    # GWPII_DB_URL, the dev store on 5441
uv run alembic upgrade head

# registry read API, for the forest bootstrap (loopback 8000)
cd grid-node-registry && uv run gnr api

# broker capture, before anything under observation
cd experiments && uv run python capture_broker.py 2026-10-21-disentangle-dev-run/captures

# journalkeeper on its own .env (dev broker, local DB), then the registry projection
cd gridworks-journalkeeper && uv run python run_journal_keeper.py
uv run python -m gjk.forest_bootstrap --api-base http://localhost:8000 d1.isone

# backend: .env with BACKEND_TSDB_URL on the local DB as asyncpg, the dev
# broker as smqPublic, BACKEND_RABBIT_TLS=false, BACKEND_API_PORT=8001
cd gridworks-web-backend && uv run python -m api
```

## Step 1 — registry

```sh
cd grid-node-registry
echo | GNR_WRITE_PROOF=devrun-no-gate GNR_SNAPSHOT_INTERVAL_S=86400 uv run gnr create d1.isone.me.versant.keene.cedar LeafTransactiveNode --display-name "Cedar LTN"
echo | GNR_WRITE_PROOF=devrun-no-gate GNR_SNAPSHOT_INTERVAL_S=86400 uv run gnr create d1.isone.me.versant.keene.cedar.ta TerminalAsset --display-name "Cedar"
```

The `echo` answers the publish confirmation; the proof is any value
when the target sets no `GNR_WRITE_PROOF_SHA256`; the interval is a
required setting the laptop `.env` lacks. Capture: `logs/step1-gnr-create.log`.

## Step 2 — store

```sh
cd gridworks-pii
set -a; . ./.env; set +a    # GWPII_DB_URL, the dev store on 5441
export GWPII_OPERATOR=devrun
uv run gwpii add-scheme ridgeline --prefix HH- --digits 3
printf 'Quillon\nFarrowby\nqfarrowby@larkspur-hollow-devrun.net\n207-555-0199\n418 Larkspur Hollow Rd\nKeene\nME\n04950\nUS\n\n\n\n\n' | uv run gwpii add-customer 1f1a7314-026b-4a25-a0fc-2cef257671f1 --partner ridgeline
uv run gwpii show 1f1a7314-026b-4a25-a0fc-2cef257671f1
```

Capture: `logs/step2-pii-add-customer.log`.

## Harness login

One admin role with a null `ta_g_node_id`, inserted with psycopg and
bcrypt with the dev-run login in `experiments/.env` (`DEVRUN_API_USER`,
`DEVRUN_API_PASSWORD`)
(`logs/harness-admin-login.log`).

## Step 3 — scada

Cedar's config: the Nolan fixtures from `gridworks-scada/tests/config/`
with `spruce` → `cedar` in the aliases and the deed's `TaId` set to the
registry's id, placed in a scratch XDG config home.

```sh
cd gridworks-scada
SCADA_PATHS__CONFIG_HOME=$S/config SCADA_PATHS__DATA_HOME=$S/data SCADA_PATHS__STATE_HOME=$S/state gw_spaceheat/venv/bin/gws run
```

Capture: `logs/scada.log`, `logs/step3-scada-start.log`.

## Steps 3, 4, 6, 7, 10 — harness

```sh
cd experiments
uv run python 2026-10-21-disentangle-dev-run/harness.py --db-url "$DEVRUN_DB_URL" --api-base http://127.0.0.1:8001 --out 2026-10-21-disentangle-dev-run/logs/harness.json
```

Rerun at 15:38 with the sema-typed harness, the API on 8000. Cedar's
status row from the first run is cleared first, so step 3 sees the
derived row again:

```sh
psql "$DEVRUN_DB_URL" -c "delete from gridworks.house_operating_status where terminal_asset_alias = 'd1.isone.me.versant.keene.cedar.ta'"
uv run python 2026-10-21-disentangle-dev-run/harness.py --db-url "$DEVRUN_DB_URL" --api-base http://127.0.0.1:8000 --out 2026-10-21-disentangle-dev-run/logs/harness-rerun.json
```

## Step 5 — gateway seed

```sh
pkill -f "gws run"
cd gridworks-web-backend && uv run python -m gateway
curl -s http://127.0.0.1:8100/gateway/health
```

## Step 9 — not reporting

With the scada stopped, backdate cedar's snapshot messages two days in
the dev DB and read the summaries (`logs/step9-not-reporting.log`).

## Step 8 — dashboard

```sh
pkill -f "gnr api"; pkill -f "python -m api"
cd gridworks-web-backend && BACKEND_API_PORT=8000 uv run python -m api
cd gridworks-web-frontend && node_modules/.bin/vite --port 5173
```

Open the URL vite prints, log in with the dev-run login in `experiments/.env` (`DEVRUN_API_USER`,
`DEVRUN_API_PASSWORD`).

## Restore

Stop the gateway, API, frontend dev server, journalkeeper, capture and
registry API; remove the sema worktree (`git -C sema worktree remove
<path>`). The scratch config home goes with the session scratchpad. The
dev databases keep cedar (registry, journal, store); the backdated
snapshot messages stay in the local `tsdb`. The backend `.env` is
gitignored and stays for the next run.
