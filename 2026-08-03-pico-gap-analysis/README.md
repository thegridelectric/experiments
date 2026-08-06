# Pico reliability by house — gaps, glitches, and their Venn

Genre: observational analysis. First run 2026-08-03; extended 08-05
(56-day window, glitch angle, Venn, timing structure). Reproducers, all
read-only against the analytics DB (`GJK_DB_URL`; `WINDOW_DAYS` env
knob):

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
the mechanism predicts with one zombie still standing. Discriminating
test pending: revive or de-layout floor2's pico → shakes stop →
dropouts should collapse without touching the secondary pico. Residual
question if confirmed: why this one pico rejoins in 13–14 min
(signal/placement/DHCP). Design question for the scada backlog: back
off shaking long-dead zombies.

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
