# spruce-store-charge-valve, 2026-08-23

> What this is: which drive state OPENS the gw108 charge valve (the relay
> silkscreened "DISCHARGE VALVE", 0x21 port1 bit3), and does the iso-closed
> charge circuit actually flow? Groundwork for tank1 as summer cool
> storage. (Originally run 2026-08-16, but the relay was not wired to the
> valve then — those runs were void; this folder's date is the first real
> run.)

## Why

Charging the store means: charge valve OPEN + iso valve CLOSED + secondary
pump ON, so the pump pushes HX water through the store instead of the
house (iso open = the buffer/house path — the summer hack's cooling
posture). The working belief since the 08-20 on-site session was
energized = open. The first real charge attempts (2026-08-23 15:20–15:38,
`charge_store.py`, iso closed + charge ENERGIZED + pump on) falsified
something: the secondary side was completely stagnant — `secondary-ewt`/
`lwt` drifted up together, `store-hot-pipe` never moved, tank1 flat
through two compressor bursts, and the HP short-cycled to its ~42 °F LWT
floor recirculating its own primary volume. So either the polarity is
inverted (energized = CLOSED — the Gw108 schematic only proves energized
= powered, not which way the valve body strokes), or the valve is not
passing water in any state (field wiring / actuator). Supporting the
polarity suspicion: on 08-20 16:45–16:50, when `store-hot-pipe`
demonstrably chilled 16.8 → 13.2 °C, the summer hack was still running —
and the hack never touches that relay, so it was DE-energized.

## Setup

`charge_valve_polarity.py` runs ON spruce (copied to `~/`), summer hack
STOPPED (single writer on 0x21), no heat-pump involvement — the secondary
pump alone gives the signature. Actuator timing (George): the valve starts
CLOSING almost immediately but waits 30–60 s before it starts OPENING —
and it may not open at all against dead-head pressure. So each leg SOAKS
the drive state for 3 min with iso OPEN and the pump circulating (the
valve travels with no pressure fight), and only then closes iso and
judges for up to 5 min:

- **Leg E** — charge valve ENERGIZED, soak, then iso closed.
- **Leg D** — charge valve DE-ENERGIZED, soak, then iso closed.

The first attempt of this experiment (run 1, 15:54–16:01) gave the valve
only ~2 s between the drive change and iso closing — void for the same
reason the 15:20–15:38 charge_store runs were: the valve was never given
a chance to open before being asked to hold back the pump.

Witnesses, chosen so the verdict does not depend on the flow meter's
placement: if the circuit flows, `secondary-lwt`/`secondary-ewt` move
toward store temperature (~59 °F vs the loop's ~51 °F) within minutes and
`store-hot-pipe` moves; if it dead-heads, everything stays flat.
`secondary-flow` is logged as the third witness (fresh readings only,
judged on the pico's own read time — OPS-497). A DEAD-HEAD GUARD ends a
leg early (fresh flow < 0.5 gpm for 60 s after a 90 s grace), so the pump
never dead-heads for long. Coil ordering per the relay-stress finding:
the iso relay is energized only with two other coils on (charge + hp
momentarily); POR check after every write, auto-repaired.

## Found

**With iso closed and the secondary pump running, the store circuit does
not flow in EITHER charge-valve drive state — the polarity hypothesis is
dead, and the break is physical.** Both legs (D de-energized, E
energized): fresh `secondary-flow` 0, `secondary-ewt`/`lwt` and
`store-hot-pipe` flat, tank1 unmoved; the dead-head guard ended each leg
at ~2.5 min. The Samsung (running on its own schedule at leg D's start,
1356 W) tripped itself off within a minute of iso closing, as in every
iso-closed window today. Remaining suspects, on-site to resolve: the
field wiring landed 08-20 (still landed?), the actuator not stroking, or
no return path for the store branch (the store pump's check valve). The
08-20 16:45–16:50 `store-hot-pipe` chill (16.8 → 13.2 °C, hack running,
relay de-energized, hack pump OFF at on-peak) remains the one moment cold
demonstrably reached the branch — reconstructing what was true then is
the key on-site question.

**Soak run (18:04–18:21, the definitive version).** After George noted the
actuator is slow (starts closing at once; waits 30–60 s before starting to
open) and may plausibly not open against dead-head pressure, the protocol
gained a SOAK: charge valve ENERGIZED at 18:05:00 and held with iso OPEN
and the pump circulating at 7.41 GPM — twelve minutes of unpressured
travel time (intended 2–3 min; a long soak is a superset). Iso then closed
(18:15:50, by hand mid-soak): flow 7.42 → 0.00 within ~90 s and the
secondary side went stagnant — `secondary-ewt`/`lwt` drifting up toward
ambient together, `store-hot-pipe` flat at 16.2 °C, tank1 flat at
59.77 °F, for six further minutes. So the timing/pressure excuses are
excluded too: the charge valve passes no water, period. Stopped by hand
18:21:47, exit posture clean, hack restarted healthy.

Also observed: one 0x21 reset during leg D's first poll (iso had just
de-energized with only the pump coil on — consistent with the
relay-stress finding's edge cases), auto-repaired with re-assert; the
first attempt at this run (15:50) was VOID — a driver bug repaired a
reset without re-asserting, leaving the pump off (fixed: `wanted` map +
re-assert; the void log is not kept).

## Timeline (ET)

- 2026-08-16 — original runs, relay not wired to the valve: VOID (details
  in git history at `1d5b816` and before).
- 2026-08-23 15:20–15:38 — `charge_store.py` runs establish the iso-closed
  + energized posture is fully stagnant (the trigger for this re-run).
- 2026-08-23 15:50 — first attempt VOID (reset repaired without
  re-assert left the pump off); driver fixed.
- 2026-08-23 15:54:41–16:01:11 — run 1 (no soak): legs D (15:55:00,
  guard at t+151 s) and E (15:57:59, guard at t+164 s); exit clean; hack
  restarted 16:01. Void for the same drive-timing reason as the
  charge_store runs (~2 s between drive change and iso close).
- 2026-08-23 17:59–18:03 — run 2 (3-min soak version) started; stopped by
  hand at 60 s past iso-close (protocol discussion); not judged.
- 2026-08-23 18:04:38–18:21:47 — soak run (leg E only): charge energized
  18:05:00, 12 min unpressured soak (iso open, pump 7.41 gpm), iso closed
  by hand 18:15:50, flow 0 by 18:17:30, stagnant thereafter; stopped
  18:21:47, exit posture clean, hack restarted, healthy.

## Analysis notes

- `hp-lwt`/`hp-ewt` are PRIMARY-side sensors: with the secondary
  dead-headed they plunge together while the Samsung recirculates its
  captive volume — not evidence of secondary flow.
- Relay addresses hand-coded from `starter-scripts/gw108_test_code.py`
  (no gw108 relay nodes in the deployed layout yet; missing words: the
  `i2c.relay.component.gt` nodes of the spruce-unlimbo relay port).
- Whether the secondary flow meter witnesses store-path flow is itself
  open; this experiment's temperature witnesses close the question either
  way, and settle whether `charge_store.py`'s dead-head guard can keep
  using the meter.

## Folder contents & experimental method

HOW THE DATA IS OBTAINED. (1) GENERATED by the driver: witness samples
every 10 s from the scada's live snapshots, relay actions, POR checks —
not in any store; a re-run is a new dataset. The driver touches the
running system (hack stopped, drives 0x21, dead-heads the pump briefly).
(2) Immutable store: a `gw.readings` pull over the actuation window is
the authoritative record of the same channels.

- `charge_valve_polarity.py` — the driver (reproducer). One command per
  box:

      ssh spruce

  Load the starter-scripts venv (`st` = `source
  ~/starter-scripts/venv/bin/activate && cd ~/starter-scripts`; alias in
  `starter-scripts/bash_aliases_spruce`):

      st

      sudo systemctl stop spruce-summer-hack

      python ~/charge_valve_polarity.py --yes

      sudo systemctl start spruce-summer-hack

      exit

  Then from this folder: fetch the run files and pull the witness
  (window from the driver's closing ACTUATION WINDOW line):

      scp spruce:~/relay-stress-runs/charge-valve-polarity.log spruce:~/relay-stress-runs/charge-valve-polarity-results.json .

      uv run python ../pull_readings.py \
          --ta hw1.isone.me.versant.keene.spruce.ta \
          --channel secondary-flow --channel secondary-ewt --channel secondary-lwt \
          --channel store-hot-pipe --channel tank1-depth1 --channel tank1-depth2 \
          --start '<window start ET>' --end '<window end ET>' \
          --condition charge.valve.polarity --out .

- `charge-valve-polarity.log` / `-results.json` — GENERATED: run 1
  (no-soak legs D + E): driver log verbatim; typed `Sample` records +
  knobs + per-leg verdicts + window (kind-specific plain result files,
  no word).
- `charge-valve-polarity-soak.log` / `-soak-results.json` — GENERATED:
  the soak run (leg E, 12-min soak, iso closed by hand mid-soak at
  18:15:50 — so its samples through t+1020 s are labelled `E-soak`; the
  driver was stopped before its own scripted close).
- `instances/gw.experiment.run-000.json` — emitted from the results file
  by `emit_instances.py`.
- `hw1.isone.me.versant.keene.spruce.ta-charge.valve.polarity-gw.readings-000.json`
  — the immutable-store witness, 15:53–16:03 ET (6 channels, 53 readings).

---

**From the instance to the display CSV.** The `*-gw.readings-000.json`
file is the canonical record: the channel words together with their
readings, validating against the sema registry. The `-display.csv`
sibling is presentation only — the same readings as natural-unit floats
(temperatures °F, flows gpm), converted per each channel word's own
encoding. Regenerate it any time, with no database or S3 access:

    uv run python ../pull_readings.py --display-from <instance>.json
