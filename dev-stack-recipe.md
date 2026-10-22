# Dev-stack recipe

How to stand up more than one GridWorks service on the laptop for a dev
run, as the stack is today. This is the hand version; the tool that
replaces it is OPS-614. Everything below is about the `d1` universe on
the laptop and touches nothing deployed.

The first full use was `2026-10-21-disentangle-dev-run/`; its `runbook.md`
has every command as run, and this file is that runbook with the
experiment taken out.

## Before anything

- **Port 8000 is the scada's.** A sim scada on the Nolan layout binds it
  and shuts itself down if it cannot. Everything else takes another port:
  the registry read API 8010 (`GNR_API_PORT` in the registry's
  `template.env`), web-backend's API 8001 (`BACKEND_API_PORT`) except
  while the frontend needs it on 8000, the gateway 8100.
- **One `.env` per repo, the repo's own prefix.** Nothing on a command
  line, nothing exported shell-wide. The dev broker is plain AMQP, so a
  service that defaults to TLS needs its switch (`BACKEND_RABBIT_TLS=false`).
- **Check the branch in every repo you start** with
  `git -C <repo> branch --show-current`. Other sessions move checkouts.
- **Record as you go**: wall clock per step, the commands as run, stdout to
  a file per service under the experiment folder's `logs/`.

## The stack, in start order

| part | where | start | ready when |
|---|---|---|---|
| broker `gw-dev-rabbit` | gridworks-base | `./arm.sh` (fresh data dir each run) | `docker ps` shows it; mgmt UI on 15672; vhost `d1__1` |
| journal DB `gw-data-pg` | docker, port 5433 | `docker start gw-data-pg`; schema `cd gridworks-data && uv run alembic upgrade head` on `main` | `alembic current` is head |
| registry `d1` | grid-node-registry | `uv run gnr rabbit` (write loop, forest broadcasts); `uv run gnr api` (read façade, 8010) | `curl localhost:8010/docs` is 200 |
| registry dev state | grid-node-registry | `uv run gnr seed-dev` on an empty registry (`--wipe` to replace the `d1` nodes) | `✓ seeded N d1 GNodes` |
| PII store | gridworks-pii | `docker compose up -d`; `uv run alembic upgrade head` | store on 5441 |
| broker capture | experiments | `uv run python capture_broker.py <folder>/captures` | prints `capturing` |
| journalkeeper | gridworks-journalkeeper | `uv run python run_journal_keeper.py`; then `uv run python -m gjk.forest_bootstrap --api-base http://127.0.0.1:8010 d1.isone` | `g_nodes` rows in `gridworks.g_nodes` |
| web-backend API | gridworks-web-backend | `uv run python -m api` | `POST /api/v2/sessions` answers |
| web-backend gateway | gridworks-web-backend | `uv run python -m gateway` | `curl localhost:8100/gateway/health` |
| frontend | gridworks-web-frontend | `node_modules/.bin/vite --port 5173 --strictPort` | the URL vite prints |
| sim scada | gridworks-scada | the Nolan fixture layout with the alias changed, in a scratch config home (`experiments/put_layout.sh dev`) | its first `layout.lite` is journaled |

Start the capture before anything under observation. Start the gateway
after the scada you want it to seed from has stopped, if the seed path is
what you are testing.

## Things that bit

- **The frontend's real-time page dials its own origin.** Vite proxies
  only `/api`, so the gateway websocket needs
  `VITE_GRIDWORKS_WS_BASE_URL=ws://localhost:8100` in the frontend's
  gitignored `.env` before vite starts.
- **The frontend proxies `/api` to 8000.** For a dashboard check the
  backend API moves to 8000, which means the sim scada is stopped first.
- **A service that died stays dead quietly.** Before a check, list what is
  listening: `lsof -nP -iTCP -sTCP:LISTEN | grep -E '8000|8001|8010|8100|5173'`.
- **The registry's forest broadcast is daily.** A change in the registry
  reaches journalkeeper's `g_nodes` on the next broadcast or on a rerun of
  the forest bootstrap against the read API.
- **The web-backend dev login is seeded by hand.** One admin role with a
  null `ta_g_node_id` (`DEVRUN_API_USER` / `DEVRUN_API_PASSWORD` in
  `experiments/.env`); the dev-run runbook has the insert.
- **A snapshot that lags the scada decodes degraded.** If the scada sends
  a word version the consumer's snapshot lacks, the row is not written
  and the log says `Degraded decode`. Publish the version the consumer has,
  or regenerate the consumer first.

## Taking it down

Stop the frontend, gateway, API, journalkeeper, capture and read API.
Leave the broker, the databases and `gnr rabbit` up; they are the laptop's
standing dev state. The experiment's runbook ends with its own restore
step for anything it placed.

## Leaving it better

A session that uses this recipe and finds a step missing, a port
colliding or a readiness check absent fixes the smallest piece in the
repo that owns it and notes the item on OPS-614, which is the contract
every service is converging on.
