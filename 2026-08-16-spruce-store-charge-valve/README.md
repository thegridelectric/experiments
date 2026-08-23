# spruce-store-charge-valve, 2026-08-16

> What this is: does the gw108 charge valve open when energized and fail
> CLOSED when de-energized? Groundwork for using tank1 (the store) as summer
> cool storage. Verdict lands here and in the logbook; the authoritative data
> is a `gw.readings` pull over each actuation window.

## Why

The summer hack cools the house with the heat pump. We want to also charge
tank1 with cold water and later discharge it into the buffer — a four-state
flow-control manifold. The pivotal unknown is the **charge valve** (the relay
silkscreened "DISCHARGE VALVE", 0x21 reg3 bit3; the "Charge Valve" on the
Nolan layout): charging the store means store pump OFF + charge valve OPEN, so
the state machine leans on the valve's fail-state. Energized = open is the
working belief; whether de-energized = mechanically closed decides whether
"charge valve off" is a safe, self-closing rest state.

The Gw108 RevB schematic (`gridworks-hardware`, `fcm_outputs.kicad_sch`) shows
the charge valve is driven by **one SPDT relay** — COM = valve actuator, NO =
24VAC_R (hot), NC = 24VAC_COM, and (unlike the ISO valve) **no failsafe
relay**. So energized -> powered, de-energized -> unpowered, unambiguously.
The single-relay 2-wire drive is the signature of a spring-return (fail-closed)
actuator — but the board cannot show the valve *body's* mechanical fail-state.
That needs an experiment.

## Setup

`charge_valve_driver.py` runs ON spruce with the summer hack **stopped** (single
writer on 0x21); the deployed scada stays up so we read its snapshots. It STARTS
with the pump on and flow CONFIRMED, so a later drop to 0 is meaningful:

- **Baseline** — ISO OPEN, pump on. Wait for `secondary-flow` to read a live,
  nonzero value (> 2 GPM). Proves the pump runs, the pico is live, and sets a
  real baseline. **ABORT if it never confirms** (never run the legs blind).
- **Isolate** — close ISO (pump still on). Flow should collapse toward 0 — the
  pump now dead-heads with no path. Confirms isolation.
- **Leg 1** — charge valve ENERGIZED. Flow RETURNS as the store branch opens
  => opens energized.
- **Leg 2** — charge valve DE-ENERGIZED. Flow collapses to ~0 again (valve
  shuts; the store pump's one-way check valve blocks the return) => fails
  closed. Stops at the MINIMUM of (fresh flow < 0.5 GPM) or 45 s.

The first run (see Found) failed because it started from pump-OFF / zero flow and
manipulated into a pico gap — the baseline-confirm step is the fix. The driver
touches only the 0x21 iso/pump/charge bits (read-modify-write; the 0x20 zone
holds are preserved) and always restores charge OFF / pump OFF / ISO OPEN.

**Witness discipline.** `secondary-flow` is fed by the secondary-btu pico, which
drops out for 13-14 min at a stretch (the zombie-shake loop; 2026-08-03-pico-gap-
analysis Finding 1). During a dropout the scada snapshot rebroadcasts the last
value with a stale read-time (OPS-497). So the driver (1) GATES on true
liveness — it acts only when a `secondary-flow` reading's own
`ScadaReadTimeUnixMs` is younger than 6 min — and (2) judges flow on that true
read-time, never receipt time. The **authoritative** verdict is a retrospective
`gw.readings` pull over the actuation window (the DB carries real read-times and
cannot be fooled by a fossil); the driver's live PASS/FAIL only corroborates.

## Found

**Superseded on site 2026-08-20.** The charge-valve relay had NOT been
wired to the valve actuator during both runs below, so neither leg could
move the valve. Wired on 08-20: energized = flow through the store tank,
witnessed by hand and in the journal DB — tank1 depth1 fell 62.4 → 57.4 °F
in steps matching the 17:16–17:43 ET `secondary-flow`/`store-flow` bursts,
then sat flat and has warmed ~0.4 °F/day since with the relay de-energized
(so de-energized passes no meaningful flow; the clean de-energize →
flow-stops transition itself was not captured). The 08-16 findings below
stand only as the record of what the unwired runs showed.


**With ISO closed and the secondary pump running, no secondary flow appeared in
any charge-valve state.** The charge-valve question is NOT resolved by the
secondary flow meter — the next step is on-site.

- **Run 2 (2026-08-16 21:17:18-21:19:44 ET), `charge_valve_driver.py`, clean
  methodology.** Authoritative `gw.readings` pull
  (`…-charge.valve.run-gw.readings-000.json`):
  - BASELINE (ISO open, pump on): `secondary-flow = 7.49 GPM` at 21:17:21 —
    pump + pico confirmed live.
  - ISOLATE (ISO closed, charge de-energized): flow `7.49 -> 5.05 -> 0.00` by
    21:17:36 as ISO travelled shut — **directly captured**. Dead-head confirmed.
  - LEG 1 (charge ENERGIZED) and LEG 2 (charge DE-ENERGIZED): `secondary-flow`
    produced no further reading, while its sibling channels on the same pico
    (`secondary-ewt` 21:18:47, `secondary-lwt` 21:19:02) kept reporting. Flow is
    an on-change channel, so a live pico with no capture means the value did not
    change from 0. **Flow stayed 0 in both legs.**
  - Net: the secondary pump dead-headed with ISO closed regardless of charge-
    valve state. Flow never returned after ISO closed.
- **This does NOT by itself mean the charge valve is broken.** Leading
  possibilities, to resolve on-site:
  1. **Meter placement** — the secondary-btu flow meter may sit DOWNSTREAM of
     the pipe split to the store, so charge-direction flow into the store would
     bypass it and read 0 even if the valve opened. Would fully explain the
     result with a working valve.
  2. The charge valve isn't actuating (stuck / relay not moving it).
  3. `energized = closed`, not open (power-to-close spring valve) — we would
     never see the open state this way.
  4. The charging loop needs more than charge-open + store-pump-off (the
     secondary pump can't drive the store branch in this configuration).
- **Run 1 (13:31:59-13:33:46 ET), `starter-scripts/charge_valve_test.py`:
  INCONCLUSIVE.** Read a frozen `secondary-flow` 7.42 GPM through both legs; the
  channel had NO readings 13:27:27-13:40:18 — the tank1 pico zombied at 13:29:23,
  the shared-VDC shake knocked out the secondary-btu pico, and the snapshot
  rebroadcast the 9-min-old value. A pico-dropout + snapshot-staleness artifact,
  not a valve result. Drove OPS-497 and the baseline-confirm gate.

## Timeline

- 2026-08-16 13:31:59-13:33:46 ET — run 1 (starter-scripts), entirely inside a
  `secondary-flow` dropout (13:27:27-13:40:18; tank1 zombied 13:29:23 -> VDC
  shake). Inconclusive; drove OPS-497.
- 21:17:18 — run 2: pump on, ISO open. 21:17:21 baseline 7.49 GPM (live).
- 21:17:25 — ISO closed; flow captured collapsing to 0.00 by 21:17:36.
- 21:18:12-21:18:57 — LEG 1 charge energized; no flow capture (pico alive).
- 21:18:58-21:19:43 — LEG 2 charge de-energized; no flow capture (pico alive).
- 21:19:44 — restore (charge off, pump off, ISO open); summer hack restarted.

## Analysis notes

- **Trust the live-pico inference.** When the secondary-btu pico is reporting on
  its other channels (`secondary-ewt`/`lwt`), `secondary-flow`'s silence means no
  change — flow is an on-change channel and captured every 1 s transition during
  spin-up/collapse. A steady-0 state simply produces no reading until the ~5 min
  periodic tick; that absence is the signal, not a gap. (Do NOT hold a state for
  minutes just to force a periodic reading — the inference suffices, and we don't
  dead-head the pump that long.)
- Trust `secondary-flow` for a window ONLY if the pico had no gap across it —
  confirm from the pulled instance's read-times. Run 1 failed exactly here.
- `secondary-pump-ct` is NOT an independent witness — it is another channel of
  the same secondary-btu pico and drops out with the flow.
- **Meter placement is unverified.** If the secondary-btu flow meter is
  downstream of the store split, it cannot witness charge-direction flow at all —
  the whole approach of witnessing charging via `secondary-flow` would be void.
  Resolve on-site before the next software run.
- Legs dead-head the Grundfos UPMS 20-78; safe for the < 45 s used here.

## Next step

On-site. Physically verify (1) where the secondary-btu flow meter sits relative
to the store split, (2) whether the charge valve actuator moves when energized,
and (3) the charge-direction flow path. Software runs resume only once the
plumbing is understood.

## Folder contents & experimental method

HOW THE DATA IS OBTAINED. Two sources. (1) The **driver** actuates the manifold
and reads live snapshots — it takes no stored measurement of its own; its console
log is an operator aid, not the record. (2) The **witness** is pulled from the
immutable **journal DB** after the run: `secondary-flow` plus the secondary temps
over the actuation window, assembled into one `gw.readings` instance — re-pullable
by anyone with DB access. The driver touches the running system (stops the summer
hack, drives 0x21 relays, holds the pump); the pull touches nothing.

- `charge_valve_driver.py` — the on-box actuation driver (the reproducer). Run it
  on spruce (summer hack stopped):

      # on spruce, from a copy of this script:
      sudo systemctl stop spruce-summer-hack
      /home/pi/starter-scripts/venv/bin/python charge_valve_driver.py
      sudo systemctl start spruce-summer-hack

  It prints the exact ACTUATION WINDOW (ET + unix ms) on exit; feed that to the
  pull below (widen ~1 min each side to catch settling flow).

- `<ta>-<condition>-gw.readings-000.json` — the authoritative witness for a run,
  pulled after actuation (one per successful run, `condition` = the leg or run
  tag). Regenerate from the journal DB:

      uv run python ../pull_readings.py \
          --ta hw1.isone.me.versant.keene.spruce.ta \
          --channel secondary-flow --channel secondary-ewt --channel secondary-lwt \
          --start '<window start ET>' --end '<window end ET>' \
          --condition charge.valve.run1 --out .

  Regenerate the display CSV from an existing instance (no DB access):

      uv run python ../pull_readings.py --display-from \
          hw1.isone.me.versant.keene.spruce.ta-charge.valve.run1-gw.readings-000.json

---

**From the instance to the display CSV.** The `*-gw.readings-000.json` file is
the canonical record: the channel words together with their readings, validating
against the sema registry. The `-display.csv` sibling is presentation only — the
same readings as natural-unit floats (flows gpm, temperatures °F), converted per
each channel word's own encoding. Regenerate it any time, with no database or S3
access:

    uv run python ../pull_readings.py --display-from <instance>.json
