# Registry projection + ear capture — the dev-universe rig

2026-08-05 · the OPS-443 experiment (design EDD bar): a re-parent published
on the bus must land in the `gw_data` projection and in the raw capture,
unprompted — plus the bootstrap leg (strand 1 step 3) and snapshot
anti-entropy. First fleet-level dev-universe experiment; a template for
more.

## Setup (all localhost, vhost `d1__1`)

- **Broker:** `gw-dev-rabbit` (`gridworks-base/./arm.sh`;
  `dev_definitions.json` already carries `gnr_ear_tx` + bindings).
- **gnr** (`jm/forest-send-time` @ `c021791`): compose Postgres :5435,
  `alembic upgrade head`, dev universe seeded (28 nodes, willow Pending);
  `uv run gnr rabbit` (write loop) + `uv run gnr api` on **:8001** — a
  stale pre-branch `gnr api` held :8000 and serves 000 forests without
  `SendTimeMs`; that process is drift, restart it.
- **gjk** (`jm/forest-snapshot` @ `a822c77` + `forest_bootstrap`, pending
  commit "forest bootstrap: pull the registry forest via the read API"):
  `timescale/timescaledb-ha:pg16` container on :5433 (`journaldb_dev`),
  gw_data schema via `Base.metadata.create_all`;
  `run_journal_keeper.py` with `GJK_DB_URL` / `GJK_RABBIT__URL` overrides.
- **ear:** `EAR_SERVICE_ALIAS=d1.gnr.ear EAR_CONSUME_EXCHANGE=gnr_ear_tx
  EAR_S3__ENDPOINT_URL=http://localhost:1 uv run ear listen` — the dead
  endpoint makes every put fall back to the local retry cache
  (`~/.local/share/gridworks/ear/output/need_to_put/`), so the capture
  grammar is witnessed locally with no cloud writes; the S3/B2 sink path
  is prod-proven separately (B2 proof, 2026-08-05).

## Found — all four legs PASS

1. **Boot** — all three consumers live on the broker (`d1.gnr`,
   `d1.journal`, `d1.gnr.ear`).
2. **Bootstrap** — `uv run python -m gjk.forest_bootstrap --api-base
   http://localhost:8001 d1.isone d1.time` projected **28/28** nodes
   (willow home Pending as seeded; `position_point_id`s NULL pending
   OPS-488's table drop).
3. **Re-parent** — `rig_reparent.py` published `g.node.reparent.cmd` as
   the keene MarketMaker. The registry broadcast `g.node.forest/001`
   (SendTimeMs stamped) on channel keene; gjk re-aliased the beech
   subtree under `keene.sub` (29 rows) and persisted the forest message
   with `created_at == SendTimeMs` (23:12:51.502Z); the ear captured
   **command + `g.node.cmd.ack` + broadcast** under
   `d1__1/<from>-<type>-<ms>-d1.gnr.ear` — the full slice, unprompted.
4. **Anti-entropy** — corrupted the projected beech row
   (status→Suspended, display_name→CORRUPTED-BY-RIG);
   `uv run gnr snapshot d1.isone` healed it.

Not exercised on the wire: connectivity-edge projection (this seed
carries no edge; the upsert path is unit-covered in gjk's
`test_g_node_forest_persistor.py`).

## Manifest

- `rig_reparent.py` — the leg-3 MarketMaker publisher (legs 2 and 4 are
  the one-line commands above).
