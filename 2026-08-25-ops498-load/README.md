# ops498-load — EDD harness for the eventstore back-fill

What this is: the re-runnable reproducer behind the OPS-498 loading track.
It loads old S3 eventstore windows into a dev journal DB that already holds
**today's** channel state (copied from prod), then asserts the things a bulk
load into prod must not break. Built so that a load without the time-aware
channel sync, the era-row lookup, or the hourly refresh fails here first.

## Run

    ./edd_dev_run.sh            # full: reset → seed → snapshot → pass 1 → pass 2 → check

Needs: docker with `gw-data-pg` (port 5433, role `gw_journalkeeper`), AWS
credentials that can read `s3://gwdev`, `GJK_DB_URL` in `experiments/.env`
(prod, read-only `gw_visualizer`) for the seed. Override the dev URL with
`DEV_DB_URL`. Each run writes its importer summaries and check output under
`runs/<UTC stamp>/`.

## Steps

1. `reset_dev.sql` — empties messages / readings / reading_channels /
   cached_hourly_data in the dev DB and clears the `readings_1hr` cagg.
2. `seed_current_era.py` — copies every prod `reading_channels` row and the
   newest `layout.lite` messages row per house into dev. That is the prod
   shape the load will meet: live channels active, one newest layout per
   house for the sync guard to compare against.
3. `assert_dev_run.py snapshot` — records the active channel id per (TA, name).
4. Pass 1: `layout.lite` only, forward, over the windows (`--batch-size 500`, `--workers 8` throughout). Every layout is older
   than the seeded newest one, so each syncs add-only and lays down era rows.
5. Pass 2: everything but `layout.lite`, forward, over the windows.
6. `assert_dev_run.py check` — the assertions (see the script's docstring).

## Windows

Chosen to cross every channel era on the way up: Oct 2024 (report.event
v000, before any layout exists on the wire), Nov 28 2024 (layout.lite v001,
pass 1 only), Dec 2024 (v002), Feb 2025 (v004), Dec 2025 (v006). The
Dec 30 2024 – Jan 18 2025 problem-event flap is avoided on purpose.

## Logbook

(append one line per run: date, windows, outcome, pointer to runs/…)
- 2026-08-25 — run `runs/20260825T2008/`: windows Oct 13–15 2024, Dec 10–12
  2024, Feb 15–17 2025, Dec 20–22 2025 (pass 1 all five incl. Nov 28–30, which
  was empty: v001's wire birth is Dec 1). First two pass-2 windows unbatched
  (17 msg/s), rest with `--batch-size 500` (39 msg/s from the laptop; Dec 2025: 76,087 msgs in 44 min). All 7
  checks pass. Observations: `orange` (a house absent from prod) has reports
  but no layout in the windows → 898 readings dropped, tallied; oak dropped
  18,157 `oat` readings (no layout in the windows defines it — watch in the
  full-span prod pass 1); spruce has no `buffer-depth1` era row in these
  windows; the cagg refresh needs the view owner. 14 degraded = the rejected
  pre-versioning `gridworks.event.problem` shape from `ng` beachrose.

## Prod runbook (the "go")

1. Land and push the JK branch (`jm/ops-498-load`); the box runs the pushed SHA.
2. Box: throw-away EC2 in **us-east-1**, 2 vCPU / 4 GB is plenty, instance
   role with `s3:GetObject` + `s3:ListBucket` on `gwdev`. Install `uv`,
   `git clone` gridworks-journalkeeper at the pushed `main` SHA, `uv sync`. Put
   `GJK_DB_URL` (prod **writer**, from 1Password) in the environment only —
   no `.env` in the checkout. `psql` for the floors query.
3. The driver is `scripts/s3_bulk_load.sh` **in the JK repo** — the box runs
   only committed code. Dry-run one week first: `DRY=1 scripts/s3_bulk_load.sh`
   (lists, decodes, writes summaries, persists nothing). Then
   `nohup scripts/s3_bulk_load.sh &` under tmux.
   Watch `runs/prod-*/…log` and the summary JSONs; a `PARSE_FAIL` or a new
   dropped-readings channel is the thing to look at.
4. After the load, as the **admin** role (the cagg owner):
   `CALL refresh_continuous_aggregate('gridworks.readings_1hr', '2024-10-13', '2026-01-10')`,
   then rebuild `cached_hourly_data` for the same range delete-then-insert
   (the stock `refresh_all_cached_hourly_data.py` appends).
5. `scripts/replay_flo_params.py` (in the JK repo) against prod (writer
   URL) for the Jan–Mar 2026 v004–006 pseudo-readings.
6. Reconcile: per-day counts in the summary JSONs vs `messages` by
   `(from_alias, type, day)`; `readings` per day vs `report.event` per day.
7. Terminate the box. Record the run here.
- 2026-08-25 22:16 UTC — **prod load started** on `ops498-loader`
  (`i-005da05cec87777a9`, 18.232.137.165, us-east-1a, t3.medium, role
  `ops498-loader`), JK `main` @ `730ae05`, run dir `~/runs/prod-20260825/`
  on the box (`driver.log` + per-window logs/JSON). Dry run of Oct 13–19 2024
  first: 84,286 msgs in 7m53s (178/s, no DB). Terminate the box when done and
  copy `~/runs/` back here.
- 2026-08-25 22:35 UTC — **stopped** after pass-1 window 2024-11-03..09: the
  driver on the box was an scp'd script, not committed code. Driver and
  replay script moved into the JK repo (`scripts/s3_bulk_load.sh`,
  `scripts/replay_flo_params.py`), with pass 2b grouped by floor date and
  `gw.weather.*` skipped. Restart from `main` once landed; pass 1 windows
  already done are idempotent.
- 2026-08-25 evening — runs c/d/e on the box. **c** (`main` @ `9f5664f`,
  from the checkout): pass 1 reached 2025-06-07 and surfaced three
  `layout.lite` decode failures the one-sample scan had missed → stopped;
  two fixed in sema `371514d` (`MaxEwtF` optional on `ha1.params:000`,
  `StateType` optional on `relay.actor.config:002`), one kept as a
  rejection (142 axiom-4 layouts, Jan 25 – Feb 4 2025). **d**: restart
  skipped pass 1 because the driver re-derived floors from a DB that now
  held back-filled layouts → stopped within a minute; fixed in `fb68393`
  (`FLOORS=<file>`). **e** (`main` @ `1c57bd4`): pass 1 from 2024-12-01 with
  `FLOORS=~/runs/prod-20260825/floors.txt` (the pristine capture). Expect
  exactly 142 `PARSE_FAIL` in pass 1.
- 2026-08-26 02:20 UTC — run e stopped by the monitor at 2025-12-05 (pass 1,
  52 weeks): one **corrupt S3 object**, not a mismatch — oak `layout.lite`
  2025-11-23 13:06 UTC (`…-layout.lite-1763900815569-…`) is spliced at byte
  76,156 with a fragment of another MQTT frame; its two siblings that day
  are intact. Skipped (counted `PARSE_FAIL`). Run **f** restarted from
  2024-12-01 with the stop rule narrowed to sema-shaped failures; corrupt
  objects are counted and reported by shape.
- 2026-08-26 ~03:00 UTC — run f **stopped by the stop rule** at pass 1
  week Dec 7–13 2025 (54 weeks done, 2024-12-01 → 2025-12-13 layouts
  loaded; corrupt oak object counted). 14 `layout.lite` messages on
  2025-12-11/12 (beech, elm, maple; 5 × v005, 9 × v006) carry
  `TankModuleComponents` at `pico.tank.module.component.gt:010` while
  005/006 pin `:011` only — deploy lag after `:011` (Dec 5). Proposed sema
  fix: `oneOf[010, 011]` on layout.lite 005 and 006 (in place, back-fill
  era, deps add `:010`); awaiting sanction. Box idle.
- 2026-08-26 — sema `61fe3ef` (pico.tank 010/011 union on layout.lite
  005/006), JK `77c5ef6` (snapshot + `PASS2_START`). Run **g** on `main` @
  `77c5ef6`: pass 1 resumes at 2025-12-07, pass 2a from 2024-12-01, recorded
  floors. Prod evidence that re-loads dedupe: 5,149 layout rows Dec 2024 →
  Dec 2025 after three loads, 5,149 distinct ids.
- 2026-08-26 — run g (main `77c5ef6`) finished pass 1 through 2026-01-08 and
  was stopped as pass 2a began, to land the de-dupe change first: JK
  `be04325`/`38bd6e5` — uuid5 ids from the payload's created time, S3
  import refuses receipt-time-keyed types (`power.watts`, `atn.bid`,
  `latest.price`, `gw.weather.*` cmd/obs/records), `hw1.` aliases only. Run
  d's 461 leftover rows on 2024-12-01 deleted from prod. Run **h** (main
  `38bd6e5`): `PASS1=0 PASS2_START=2024-12-01`, recorded floors. Pass 1 in
  run g also skipped 1 `d1.` sim-house layout (2026-01-08, sim tanks) —
  now excluded by alias.
- 2026-08-26 ~13:00 UTC — run h (single driver) measured 14 msg/s in pass
  2a with the box idle: the cost is per-message DB insert work, and the DB
  is in-region. A second importer alongside ran at 31 msg/s with no effect
  on the first → the DB has headroom, the serial process was the ceiling.
  JK `96c832e` adds `PASS2_END`; run **p1–p6**: six drivers on disjoint
  spans (Oct 13–Nov 30 2024; Dec 2024–Mar 2025; Apr–Jun; Jul–Sep; Oct–Dec
  2025; Jan 1–8 2026 uncapped, owns pass 2b), `WORKERS=8` each.
- 2026-08-26 — throughput scaling. 6 drivers on the t3.medium (2 vCPU) →
  77 msg/s at 27% CPU (DB has headroom); 12 drivers → 76 msg/s at 91% CPU
  (box CPU is the ceiling, not the DB — decode+persist is CPU-bound in
  Python). Resized the loader in place to **c7i.4xlarge (16 vCPU)** and ran
  24 drivers on ~18-day spans (r1–r24, r24 uncapped owns pass 2b),
  WORKERS=6 each. New public IP 44.203.82.96 (no EIP; EBS/env/host-key
  survive the stop/start). Resize is fine to drive directly — throw-away
  loader, not a prod service.
- 2026-08-26 — SCOPE CUT. 24 writers on the c7i box locked the DB (12
  lock-waits, SELECT 1 at 0.18s); backed to 8 writers (~100 msg/s, DB
  clean). Then found the per-type floor pulled snapshot.spaceheat to
  2026-07-09 (not journaled live until July 2026) — a 6-month production
  gap, not the historical archive. Decision: cap ALL types at 2026-01-08,
  and skip snapshot.spaceheat entirely (no readings, ~90% of volume).
  Relaunched t1-t8 via the committed importer directly (no driver edit, no
  commit): `--message-types '~layout.lite,gridworks.event.problem,snapshot.spaceheat'
  --end 2026-01-08`. Denominator drops from ~10-15M to ~1-1.5M messages.
  OPEN: 316k snapshot rows already loaded (< 2026-01-09) — delete for a
  clean no-snapshot archive? And the Jan-Jul 2026 un-journaled gaps are a
  separate decision.
- 2026-08-26 — writer tuning + completeness. Snapshot-free run at 8 writers
  = 0 lock-waits, ~16-19 msg/s; 16 writers = steady ~5 lock-waits, select1
  up to 0.19s; settled at **12 writers** = ~4 lock-waits, select1 ~0.10s
  (near baseline). Spans are 12 contiguous slices of 2024-10-13 → 2026-01-08,
  verified no gaps/overlaps (453 days == expected). **Completion check
  (run on the box at the end):** union of `Completed messages for <day>`
  across all `runs/prod-20260826v*/import.log` must equal the full 453-day
  set; any missing day = a crashed span to relaunch. Each span also ends
  with a `RUN SUMMARY`. This rides on the single contiguous v-run finishing;
  earlier writer-count layouts (8/16/24) were idempotent supersets.

## COMPLETE — 2026-08-28 03:21 ET

Full back-fill verified: **453/453 days** scanned (2024-10-13 → 2026-01-08),
all spans ended with a clean RUN SUMMARY (0 degraded, 0 persist-fail). The
only rejects in the entire load: **3 `flo.params.house0` messages, oak,
2025-03-28** (fractional InitialTopTempF where the type — and gwsproto —
declare integer; the int-vs-float design question). Keys in
`rejects-oak-flo-20250328.jsonl`; the authoritative `rejects-all.jsonl` (3
keys, deduped from 6 log lines) is on the stopped box's EBS at
`~/runs/rejects-all.jsonl`, to copy on next restart. Also known but outside
the rejects log: 1 corrupt S3 object (oak layout 2025-11-23) and 18
new.command.tree Axiom-1 rejections (beech handle-migration, 2 dates) — both
characterized earlier, correct rejections.

Box (c7i.4xlarge, i-005da05cec87777a9) **stopped** (not terminated) at 03:23
ET — EBS preserved. PENDING (wait for Jessica in the morning): snapshot
cleanup (~330k stray rows), and the flo int-vs-float decision.
