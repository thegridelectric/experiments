# ops-457-regenesis, 2026-08-27

> What this is: the one-off populate path for a fresh registry instance —
> recreate every node from the seed store's latest forest snapshots through
> the production `gnr create` path — rehearsed locally against a scratch
> `hw1` registry before it runs against the Helsinki box (OPS-507). Verdict
> in Found; this README is the reproducer.

## Why

The registry moves box (OPS-507). Its durable content is the B2
`gw-seedstore` capture, but that stream spans three schema bumps
(`create.cmd/000`, `forest/000–002`) and the 16 position-point ids the
early creates carried are unwanted (nothing goes in `position_points`
until the TaValidator exists). What must survive is GNodeId ↔ alias
continuity with the production houses. So instead of a byte-faithful
replay, the new instance is populated by a **regenesis**: fresh
`create.cmd/001` per node, same identity, `Pending`, no position; the seed
ear witnesses the new epoch. The replay tool proper (`gnr rebuild
--seedstore`) is built and proven separately.

## Setup

- Source: the two latest per-root `g.node.forest` objects in B2
  (`hw1__1/eventstore/20260827/hw1.gnr-g.node.forest-1787846141199-…`
  root `hw1.isone`, 24 nodes; `…141519-…` root `hw1.time`, 1 node),
  pulled with the `gw-seedstore` AWS profile
  (`aws --profile gw-seedstore s3 cp s3://gw-seedstore/<key> .`).
  Independent witness: `pg_dump` of the old box taken the same day.
- Target (rehearsal): scratch DB `gnr_hw1` on the local `gnr-postgres`
  container (`alembic upgrade head` at `jm/ops-457-replay`), `gnr rabbit`
  + `gnr api` (:8002) run with `GNR_UNIVERSE=hw1`, `GNR_SERVICE_ALIAS=hw1.gnr`,
  on the dev broker `gw-dev-rabbit` vhost `d1__1`; no write-proof gate.
- Harness: `regenesis.py` (this folder) — decodes the snapshots through the
  gnr sema codec, walks nodes parents-first, shells `gnr create <alias>
  <class> --g-node-id … --display-name …` per node, answering its two
  prompts on stdin. Idempotent: an existing alias is reported `exists`.

## Run

    cd experiments/ops-457-regenesis
    export GNR_API_BASE=http://127.0.0.1:8002 \
           GNR_RABBIT__URL=amqp://…/d1__1 GNR_UNIVERSE=hw1 \
           GNR_SERVICE_ALIAS=hw1.gnregistrar GNR_SUPER_ALIAS=hw1.super \
           GNR_TIME_COORDINATOR_ALIAS=hw1.time   # + GNR_WRITE_PROOF, GNR_BROKER_CA_FILE for a gated target
    uv run --project ../../grid-node-registry python regenesis.py --dry-run <forest.json>…
    uv run --project ../../grid-node-registry python regenesis.py <forest.json>…

For the Helsinki run: same command, `GNR_API_BASE` = the new box's read
API, `GNR_RABBIT__URL` = the prod broker, proof + CA set, and the old gnr
consumer stopped first (two registries on one alias would split the queue).

## Found

**Production run 2026-08-27 20:32 UTC — PASS.** Target: the new Helsinki
box (`gnr.electricity.works` = 65.21.5.34, DNS already moved, old
registry consumer off — the prod broker showed only the seed ear on the
slice). 25/25 applied in 58 s; Helsinki `g_nodes` equals the old box's
dump field-for-field; `command_log` 25, `position_points` empty. B2 the
same minute: 25 creates + 25 acks + 25 forest broadcasts under
`hw1__1/eventstore/20260827/` — the second epoch, first create at
`persisted-ms` 1787862744356.

Rehearsal 2026-08-27 15:31 ET, local scratch registry — **PASS**.

- 25/25 applied in 19 s, parents-first; `g_nodes` equals the old box's
  dump on (id, alias, base_class, g_node_class, status, display_name) for
  every node; `command_log` = 25 × `g.node.create.cmd` version `001`;
  `position_points` empty, every `position_point_id` null.
- Second run: 25 × `exists`, nothing published.
- Both `forest/002` snapshots decode through the codec unchanged; the 16
  position ids they carry are dropped at the harness (printed as a note).

## Timeline (ET)

- 15:10 — dump of the old box's DB taken (`scratch/ops-457/`).
- 15:12 — whole `gw-seedstore` slice pulled (223 objects) and cross-checked
  against the dump: today's snapshots union to the 25 nodes.
- 15:27 — scratch `gnr_hw1` migrated to head; `gnr rabbit` + `gnr api` up.
- 15:31 — first real run: 25 applied. 15:33 — second run: 25 exists.

## Folder contents & experimental method

How the data was obtained: every input comes from an immutable store and
is re-pullable — the two forest snapshots from the B2 seed store (keys in
Setup) and the old box's `pg_dump` (the independent witness, kept in
`scratch/ops-457/`, not committed). The harness GENERATES nothing but
registry state on its target and the seed ear's capture of the new epoch
(which lands in B2, not here); its stdout is the run record, not kept —
a re-run against an already-populated registry reports `exists` for every
node. The production run touched the running system: it published 25
commands to the live registry over the prod broker.

- `README.md` — this record.
- `regenesis.py` — the harness (Setup). Code under test:
  `grid-node-registry` at `main` `e8779cc` (`gnr create` unchanged from
  the July deploy).

Regenerate from scratch (a fresh target registry; see Run for the env):

    aws --profile gw-seedstore s3 cp s3://gw-seedstore/hw1__1/eventstore/20260827/hw1.gnr-g.node.forest-1787846141199-hw1.gnr.ear.json .
    aws --profile gw-seedstore s3 cp s3://gw-seedstore/hw1__1/eventstore/20260827/hw1.gnr-g.node.forest-1787846141519-hw1.gnr.ear.json .
    uv run --project ../../grid-node-registry python regenesis.py --dry-run *g.node.forest*.json
    uv run --project ../../grid-node-registry python regenesis.py *g.node.forest*.json

No `gw.readings` instance here; no display CSV.
