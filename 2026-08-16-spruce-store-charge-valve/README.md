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
writer on 0x21); the deployed scada stays up so we read its snapshots. Two legs,
ISO valve closed throughout to isolate the buffer/house so the store branch is
the pump's only path:

- **Leg 1** — charge valve ENERGIZED, secondary pump on. Flow rises => opens.
- **Leg 2** — charge valve DE-ENERGIZED. Flow collapses to ~0 (valve shuts; the
  store pump's one-way check valve blocks the return) => fails closed. Stops at
  the MINIMUM of (fresh flow < 0.5 GPM) or 45 s, dead-heading the pump only as
  long as needed.

The driver touches only the 0x21 iso/pump/charge bits (read-modify-write; the
0x20 zone holds are preserved) and always restores charge OFF / pump OFF / ISO
OPEN on exit.

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

PENDING a clean run. The definitive `gw.readings` pull is not yet taken.

- **First run (2026-08-16 13:31:59-13:33:46 ET), from `starter-scripts/
  charge_valve_test.py`: INCONCLUSIVE.** It read a frozen `secondary-flow`
  7.42 GPM through both legs. The DB showed why: the channel had NO readings
  from 13:27:27 to 13:40:18 — the tank1 pico zombied at 13:29:23, the shared-VDC
  shake knocked out the secondary-btu pico, and the snapshot rebroadcast the
  9-min-old value the whole time. Not a valve result; a pico-dropout + snapshot-
  staleness artifact. This drove OPS-497 and the liveness gate here.

## Timeline

- 2026-08-16 13:14-13:19 ET — secondary-btu / tank1 picos flatline (inferred
  from the 13:29:23 zombie declaration, which fires only after ~3 VDC cycles).
- 13:27:27 -> 13:40:18 — `secondary-flow` dropout #1 (12.9 min).
- 13:29:23 — scada glitch `pico-just-zombied` node=tank1.
- 13:31:59 -> 13:33:46 — first (starter-scripts) run, entirely inside the gap.
- 13:50:00 -> 14:03:54 — `secondary-flow` dropout #2 (13.9 min).
- 14:03:56 — scada glitch `Zombie tank1 recovered!`; both picos live again.

## Analysis notes

- Trust `secondary-flow` for a window ONLY if the pico had no gap across it —
  confirm from the pulled instance's read-times (consecutive gaps > ~6 min mean
  a dropout; discard and re-run). The routine cadence is ~5 min between async
  captures when flow is steady; a real flow change triggers a rapid burst.
- `secondary-pump-ct` is NOT an independent witness — it is another channel of
  the same secondary-btu pico and drops out with the flow.
- Leg-2 dead-heads the Grundfos UPMS 20-78; safe for the < 45 s used here.

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
      /home/pi/starter-scripts/venv/bin/python charge_valve_driver.py --auto-wait
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
