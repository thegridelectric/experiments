# Pico reliability by house — gaps, glitches, and their Venn

Genre: observational analysis. First run 2026-08-03; extended 08-05
(56-day window, glitch angle, Venn, timing structure); floor2-removal
verification re-run 2026-08-10, semafied (archive pull → `gw.readings`
instances → `emit_instances.py`, no DB access — see "Floor2 removal" and
"Folder contents"). First-run reproducers, all read-only against the
analytics DB (`GJK_DB_URL`; `WINDOW_DAYS` env knob; pre-date the
experiment vocabulary):

- `pico_gap_analysis.py` — reporting-gap statistics per channel,
  aggregated by house. A GAP = inter-report interval > max(10 min, 3×
  the channel's median cadence). Windows where ALL of a house's pico
  channels are silent together (house / scada / pipeline outage — not
  pico data) are detected and EXCLUDED from the stats, reported
  separately.
- `pico_glitch_analysis.py` — what the scadas themselves reported:
  `glitch` messages in `gridworks.messages`. `pico-just-zombied` fires
  ONCE when a pico stays silent through the pico-cycler's full rescue
  (missing-detection + 3 VDC power-cycles ≈ 10–15 min); the
  `pico-zombies` roster then re-emits HOURLY while any zombie remains —
  so transitions ≈ incident count, roster mentions ≈ hours-in-zombie-
  state (duration-weighted).
- `pico_gap_glitch_venn.py` — event-level match of the two angles
  (same house, zombie declaration within ±10 min of a gap window).

## Fleet summary — 56 days to 2026-08-05, house outages excluded

| house | gaps | zombie transitions | reading |
|-------|------|--------------------|---------|
| fir   | 0    | 4  | clean — four sub-10-min flatlines, all VDC-rescued |
| oak   | 0    | 0  | clean |
| maple | 1    | 1  | clean |
| elm   | 2    | 4  | clean — its only blemish was one ~33 h house outage |
| beech | 71   | 109 | one systematic HOURLY disturbance (finding 2) |
| spruce| 2,438| 218 | dropouts manufactured by a feedback loop (finding 1) |

**Router verdict** (the question that started this): fir, oak, and
maple are tied at clean on both independent metrics — reliability data
cannot rank them; choose on other criteria. Spruce's noise is
self-inflicted (below), not router evidence.

## Finding 1 — the spruce dropout feedback loop

The secondary-BTU pico's 552 dropouts have mechanical timing:
inter-dropout spacing peaks at **~30 min** (cluster 29–35, harmonics at
60–65/95), uniform across hours and days; duration stereotyped at
**13–14 min**. Mechanism: `PicoCycler.SHAKE_ZOMBIE_HR = 0.5` — while
any zombie exists, the cycler power-cycles the SHARED VDC bus every
30 min. Spruce has carried permanent zombies (floor2's dead pico;
old-tank1 until 08-03), so every pico rebooted ~48×/day. Siblings
rejoin wifi under the 10-min floor (invisible); the secondary-BTU
pico's rejoin is 13–14 min — just over — so each shake logs a
"dropout."

Tested: after the 08-03 deploy removed tank1's zombie (floor2 remains),
timing is UNCHANGED (19.4/day vs 19.9; same spacing and durations) — as
the mechanism predicts with one zombie still standing. The
discriminating test — de-layout floor2's pico → shakes stop → dropouts
collapse without touching the secondary pico — ran 08-05 and CONFIRMED
the mechanism (see "Floor2 removal" below). Residual question, now
live: why this one pico rejoins in 13–14 min (signal/placement/DHCP) —
the `future/pico-rejoin` experiment's territory. Design question
for the scada backlog: back off shaking long-dead zombies.

## Floor2 removal — the discriminating test, CONFIRMED (2026-08-10)

Floor2's dead pico left the layout in the 08-05 19:18 ET deploy,
breaking the shake loop's precondition (a permanent zombie). Before/
after windows of ~4.7 d each (pre: 08-01 00:00 → 08-05 19:15; post:
08-05 19:30 → 08-10 11:00 ET), pulled from the journal archive as
`gw.readings` instances; `emit_instances.py` derives per-channel
`gw.channel.gap.stats` instances from them (`instances/<condition>/`,
the machine-readable record behind this table):

| metric | pre | post |
|--------|-----|------|
| spruce gaps/day, all 43 pico channels | 104.1 | 17.0 |
| secondary-BTU pico gaps/day (4 channels) | 85.4 | 14.0 |
| per-channel gaps/day, fixed >10 min cut | 21.4 | 3.7 |
| 13–15 min gaps per channel (the rejoin signature) | 18–33 | 2–3 |
| inter-gap spacing, secondary-flow p50 | 51 min | 365 min |

The ~30 min spacing signature is gone; the collapse is not a threshold
artifact (the fixed-cut row holds it at 83%). The residual ~3.7/day
gaps are irregular, mostly 16–20 min long — the secondary pico's
organic drops, each still paying its slow-rejoin toll (plus one
solo ~165 min outage 08-08 12:29 ET). PASS: the dropouts were
manufactured by the zombie-shake feedback loop, not by the pico's
radio environment alone.

## Ongoing — wifi-herd reduction (2026-08-10)

The fancoil, pipes1, and floor1 picos are DISCONNECTED (temporarily)
and left the layout in the 08-10 13:45 ET deploy: fewer wifi picos at
spruce, same router, to see whether the secondary-BTU pico's residual
gap rate (~3.7/day per channel post-floor2, table above — the
baseline for this comparison) changes. If the residual is
herd/congestion (association/DHCP contention among wifi clients) it
should fall; if it is the pico's own radio/placement it should not.
Setup verified against the live layout emission: the disconnected
picos are OUT of the layout, so no permanent zombies and no cycler
shakes — the confound Finding 1 documents is absent by construction.

Analysis note for future windows: fancoil-/pipes1-/floor1- channels
have no readings after 08-10 ~13:45 ET. Pulls spanning the boundary
carry them as declared-then-absent, not as dropouts, and per-channel
gap stats for them cover only the pre-disconnect span.

## Finding 2 — beech's hourly disturbance

Beech's zombie transitions are PERIODIC: sieg-flow declared at :50 past
the hour (47×, recovery ~minutes later), tanks/buffer at :52–:54,
across many days — long enough to fail three VDC cycles, short enough
to stay under the 10-min gap floor (hence 109 transitions but only 71
gaps). The Device Registry adds a decisive fact: beech's tank picos are
WIRED (Wiznet), so the hourly event silences wired and wifi devices
alike — it is common infrastructure (whole router/switch, pi/LAN, or an
hourly scada-side stall starving pico posts), not a wifi phenomenon.
Unexplained; deserves its own investigation before beech's router is
taken as a standardization model.

## Finding 3 — what each metric can and cannot see

Gaps threshold on silence DURATION; zombie transitions threshold on
RESCUE RESISTANCE. Neither subsumes the other:

- *Gap, no glitch* (spruce's ~1,500): dropouts > 10 min that recover
  before the third VDC cycle.
- *Glitch, no gap* (fir's 4; beech's hourly events): flatlines that
  resist three cycles inside 10 minutes.
- *Permanent death is a GAP BLIND SPOT*: a gap needs a closing reading,
  so an unrevived pico logs at most one gap per revival and zero if it
  never returns. The hourly roster is the only detector for this class
  — read roster persistence as "still dead," and treat roster counts
  from long-dead picos (floor2 ×701, old-tank1 ×650) as layout-hygiene
  signals, not flakiness.
- *Scada-down windows are neither*: excluded from gaps by construction
  (not pico data), and no glitch can be emitted (nobody home).

## Venn — 56 d, event-level (house outages excluded)

2,512 channel-gap events · 336 zombie declarations. Gaps tagged by a
zombie: 969; untagged: 1,543 (spruce 1,535 — the loop; beech 5, elm 2,
maple 1). Zombies tagged by a gap: 220; untagged: 116 (fir's rescues,
beech's hourly events, and spruce work-session artifacts from the 07-30
pico swap).

## Folder contents & experimental method

All data in this folder comes from the journal DB — readings, and the
scada's own `layout.lite` emissions (one per window end, from
`gridworks.messages`) — and is re-pullable by anyone with DB access;
nothing here was generated by experiment instrumentation, and nothing
touched the running system. The first run
(fleet summary, findings 1–3, Venn) read the DB directly via the three
`pico_*.py` scripts above; the 08-10 re-run reads only this folder's
`gw.readings` instances.

- `hw1.…spruce.ta-pre.floor2.removal-gw.readings-000.json` /
  `…-post.floor2.removal-…` — the two archive pulls (43 spruce
  pico-fed channels each: flow / depth / lwt / ewt / micro-v /
  pump-ct patterns; channel words from the layout.lite current at
  each window's end). Regenerate both from scratch:

      uv run python ../pull_readings.py \
          --ta hw1.isone.me.versant.keene.spruce.ta \
          --like '%-flow%' --like '%-depth%' --like '%-lwt%' \
          --like '%-ewt%' --like '%micro-v%' --like '%-pump-ct%' \
          --start '2026-08-01 00:00' --end '2026-08-05 19:15' \
          --condition pre.floor2.removal --out .

      uv run python ../pull_readings.py \
          --ta hw1.isone.me.versant.keene.spruce.ta \
          --like '%-flow%' --like '%-depth%' --like '%-lwt%' \
          --like '%-ewt%' --like '%micro-v%' --like '%-pump-ct%' \
          --start '2026-08-05 19:30' --end '2026-08-10 11:00' \
          --condition post.floor2.removal --out .

- `instances/<condition>/<channel>-gw.channel.gap.stats-000.json` —
  per-channel reporting-gap statistics (43 per window), derived
  deterministically from the two `gw.readings` instances:

      uv run python emit_instances.py

- `emit_instances.py` — the emitter (gap definition unchanged from the
  first run: > max(10 min, 3× median cadence), whole-house silences
  excluded per channel into ExcludedGapCount). The house-level
  roll-up in the verdict table is derivable from the instances.
- `pico_gap_analysis.py`, `pico_glitch_analysis.py`,
  `pico_gap_glitch_venn.py` — the first run's DB-direct reproducers
  behind the 56-day fleet numbers; they print reports rather than
  emit instances (fleet-scale gap statistics stay in SQL). Interiors
  follow the sema-gravity discipline: typed records, property formats
  on aliases / channel names / timestamps, and glitch payloads decoded
  through the vendored `glitch` word (event times from its CreatedMs,
  the reporting node's clock), never read by jsonb key.

---

**From the instance to the display CSV.** The `*-gw.readings-000.json`
files are the canonical record: the channel words together with their
readings, validating against the sema registry. The `-display.csv`
siblings are presentation only — the same readings as natural-unit
floats, converted per each channel word's own encoding. Regenerate any
time, with no database or S3 access:

    uv run python ../pull_readings.py --display-from \
        hw1.isone.me.versant.keene.spruce.ta-pre.floor2.removal-gw.readings-000.json
