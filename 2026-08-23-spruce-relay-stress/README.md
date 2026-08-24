# spruce-relay-stress, 2026-08-23

> What this is: does relay switching on the gw108's 0x21 expander provoke
> its power-on reset (the OPS-452 signature), and does command spacing
> mitigate it? Verdict: energizing the iso-valve relay with no other 0x21
> coil energized resets the chip about one toggle in three (B: 35/100); with
> one other coil on, rarely (2/30); with two or more, never (0/90 across
> three runs); the secondary-pump relay switching never does. Harness
> logs are the primary evidence.

## Why

On 2026-08-20 (on site) rapidly toggling the iso-valve relay by hand
repeatedly brought the classic 0x21 reset — config registers back to
inputs, pins floating, every cooling actuator dropped — apparently worse
with more 0x21 coils energized. Until now the reset looked spontaneous
(38 in the summer-hack log since 07-17; the postmortem's supply/decoupling
suspicion). Did some more investigating to evaluate if there is a pattern
of weakness and/or if we can replicate the on-site experiment, both for
continued operations of GW108 rev B and in case its useful for designing
rev C.

## Setup

`relay_stress.py` runs ON spruce, over ssh, with `spruce-summer-hack`
STOPPED for the window — single writer on 0x21 — and restarted on exit.
(The 08-23 runs used `~/relay_stress_v3.py` on the box, an scp'd copy of
this file as committed; the reproduction commands below run it from the
box's `~/experiments` checkout.) The store pump stays OFF and the elements
are never touched; the DAC is untouched (it holds the pump speed). Coils
that may be energized: secondary pump (wired; cooling continues while it
is on), hp-call (wired to the RIB; the Samsung runs its own schedule and
ignores the contact today), charge valve (wired 08-20; energized opens the
store path), and the five UNWIRED 0x21 positions (boiler-buffer-valve,
boiler-intercept, misc1, misc2, primary-pump) — energizing them moves
nothing in the house (JM, 2026-08-23). Toggle targets: iso valve (the
08-20 reproducer) and the secondary pump.

Runs A–D compare "every other safe coil ON" against "every other coil
OFF", for each of the two toggle targets (B runs 100 toggles to measure
the rate); E and F bracket the threshold (one, then two other coils on).
Charge valve OFF throughout. B and D run the pump off (~2.5 and ~1 min
without cooling).

A run = one phase of TOGGLES toggles at PERIOD seconds; after every write
the harness reads config regs 6/7 (POR signature = nonzero, confirmed by a
second read 0.3 s later; an i2c error on that read is the chip browning
out and counts as a reset), and on a reset logs CRITICAL with the full
register snapshot, waits 0.5 s, re-inits (clear-then-configure),
re-asserts posture + load, and keeps counting. A morning sweep of
exploratory runs (not kept) narrowed the question to these; its reading
that the charge-valve relay mattered was a confound — that relay happened
to be the second energized coil.

## Found

**The 0x21 reset is provoked by ENERGIZING the iso-valve relay while few
other coils on 0x21 are energized: ~1 toggle in 3 with none, rare with
one, never with two or more. The secondary-pump relay switching never
resets it. Command spacing is irrelevant. The hack's start sequence
resets the chip because it clears everything and then energizes iso
first, alone.**

All runs: `relay_stress.py` on spruce, charge-valve relay OFF, 1 s toggle
period; one "toggle" = one coil write (a transition), so 30 toggles = 15
on + 15 off.

| run | other coils during the run | toggled coil | toggles | resets | at iso→1 / iso→0 |
| --- | --- | --- | --- | --- | --- |
| A | secondary pump, hp-call, 5 unwired — all ON | iso valve | 30 | **0** | — |
| B | all OFF | iso valve | 100 | **35** | 33 / 2 |
| C | secondary pump, hp-call, 5 unwired — all ON | secondary pump | 30 | **0** | — |
| D | all OFF | secondary pump | 30 | **0** | — |
| E | secondary pump ON only | iso valve | 30 | **2** | 2 / 0 |
| F | secondary pump + hp-call ON | iso valve | 30 | **0** | — |

Reading:

- B: with nothing else energized, energizing the iso relay resets the
  chip 33 times in 50 energize writes (66 %); de-energizing it, 2 in 50.
  Nine of the 35 were caught in the act (the config read right after
  the write raised an i2c error — the chip not ACKing while it browned
  out; the harness retried and counted it).
- E → F → A: one other coil energized drops it to 2 in 15 energize
  writes; two other coils, 0 in 15; seven, 0 in 15. The threshold is two.
- C vs D: the pump relay switching does not reset the chip in either
  condition — the transient is specific to the iso valve (the motorized
  actuator's inrush as it starts to open, or that relay position), not
  relay switching in general.
- Hack start: `init_expander` clears both ports (every coil off), then
  the state change energizes **iso first**, alone — run B's condition —
  and the chip reset within seconds of both of today's restarts
  (12:23:48, 14:19:30; auto-repaired at the first enforce pass each
  time). That is the "resets within seconds of every service start" of
  the July postmortem and 08-20 17:01. Mitigation to test in the hack
  (not yet done): skip the clear when the chip is healthy at start, and
  order the state change pump → hp-call → iso last, so iso energizes with
  two coils already on. The store charge/discharge scripts already follow
  that rule.
- Not closed: which rail/regulator — board electrical work for Joe
  (relay-supply regulation / decoupling at U18 — his existing TODO — or
  the iso relay position). What the software side now knows: never
  energize the iso relay with fewer than two other 0x21 coils energized.

Side observations: the Samsung, on its own schedule, short-cycled twice
during the morning (~3 min on, hp-lwt down to 40.7 °F) while iso was
being toggled with the charge valve open; `sick_spruce.py` clearing 0x21
while it was ALREADY in POR (no coils energized, nothing switching) did
not re-trip it (12:31:14).

## Timeline (ET)

- 12:08–12:38 morning exploratory sweep (hack stopped; cooling kept
  alive); two hack restarts in it (12:23:48, 12:38) — the first reset
  within ~8 s and auto-repaired 12:28:53, the second was clean.
- 14:15:07 hack stopped. A 14:15:07–14:15:38 (0/30). A 10-toggle
  precursor of B 14:16:00–14:17:33 (5 resets in 10; its first attempt
  died on Errno 121 during a repair — retries added to the harness; not
  kept, subsumed by B). C 14:17:56–14:18:27 (0/30). D 14:18:49–14:19:20
  (0/30).
- 14:19:30 hack restarted; reset within seconds (start sequence = run
  B's condition); auto-repaired 14:24:36.
- 14:29:40 hack stopped. B 14:29:49–14:32:21 (35/100; box label
  `B100`). E 14:32:29–14:33:14 (2/30). F 14:33:23–14:34:07 (0/30).
  14:34:10 hack restarted.

## Analysis notes

- The 0x21 expander's 3.3 V comes solely from the primary pi (OPS-452
  schematic finding); the relay coils switch on the board's relay supply.
  A reset on an iso energize says the transient reaches the chip's VDD;
  it does not by itself say which rail.
- Relay addresses are hand-coded from `starter-scripts/gw108_test_code.py`
  (the authored board map); the deployed spruce layout has no gw108 relay
  nodes yet (missing words: the `i2c.relay.component.gt` nodes the
  spruce-unlimbo relay port emits).
- The iso valve is a motorized actuator; 1 s toggling reverses it
  mid-travel. Same thing was done by hand on 08-20.
- `secondary-pump-ct` in the gw.readings pull does not show the 5-min
  pump outage after the 12:23 reset (four readings in 40 min, all
  167–170) — that channel is not a usable pump witness at this cadence.

## Folder contents & experimental method

HOW THE DATA IS OBTAINED. Two sources. (1) GENERATED by the harness: the
reset counts come from the harness's own config-register reads on the
box after every write — not in any store; a re-run is a NEW dataset. The
harness touches the running system (stops the summer hack, drives 0x21
relays, runs the secondary pump off for B and D). (2) Immutable store: a
`gw.readings` pull over the morning window (`secondary-flow`,
`secondary-pump-ct`, `hp-odu-pwr`, `primary-flow`, `hp-lwt`,
`store-flow`, `tank1-depth1`) records what the plant did while the bus
was being exercised; the reset counts do not depend on it.

- `relay_stress.py` — the harness. Every run is named with `--run <label>`,
  which names its two output files in `/home/pi/relay-stress-runs/` on the
  box: `relay-stress-<label>.log` and `relay-stress-<label>-results.json`.
  Knobs (env): `TARGET` (comma list of iso/hp/charge/pump to toggle),
  `PERIODS`, `LOADS` (how many of the 5 unwired coils are energized),
  `SPACINGS`, `TOGGLES`, `MAX_RESETS`, and the posture of the coils NOT
  toggled: `CHARGE_POSTURE`, `PUMP_POSTURE`, `HP_POSTURE` (1/0). A re-run
  of a label overwrites the box files — relabel (A2, …) when repeating.

  **To reproduce the runs, one command per box.** The box's
  `~/experiments` checkout must carry this harness (`git -C ~/experiments
  pull` on the box first). Log on:

      ssh spruce

  Stop the summer hack (single writer on 0x21 for the window):

      sudo systemctl stop spruce-summer-hack

  Go to the harness:

      cd ~/experiments/2026-08-23-spruce-relay-stress

  Run A — iso toggled, every other safe coil ON:

      CHARGE_POSTURE=0 PUMP_POSTURE=1 HP_POSTURE=1 LOADS=5 TARGET=iso PERIODS=1 TOGGLES=30 MAX_RESETS=1000 ~/starter-scripts/venv/bin/python relay_stress.py --run A --yes

  Run B — iso toggled, every other coil OFF, 100 toggles (pump off ≈ 2.5 min):

      CHARGE_POSTURE=0 PUMP_POSTURE=0 HP_POSTURE=0 LOADS=0 TARGET=iso PERIODS=1 TOGGLES=100 MAX_RESETS=1000 ~/starter-scripts/venv/bin/python relay_stress.py --run B --yes

  Run C — secondary pump toggled, every other safe coil ON:

      CHARGE_POSTURE=0 PUMP_POSTURE=1 HP_POSTURE=1 LOADS=5 TARGET=pump PERIODS=1 TOGGLES=30 MAX_RESETS=1000 ~/starter-scripts/venv/bin/python relay_stress.py --run C --yes

  Run D — secondary pump toggled, every other coil OFF (pump off ≈ 1 min):

      CHARGE_POSTURE=0 PUMP_POSTURE=0 HP_POSTURE=0 LOADS=0 TARGET=pump PERIODS=1 TOGGLES=30 MAX_RESETS=1000 ~/starter-scripts/venv/bin/python relay_stress.py --run D --yes

  Run E — iso toggled, only the secondary pump ON:

      CHARGE_POSTURE=0 PUMP_POSTURE=1 HP_POSTURE=0 LOADS=0 TARGET=iso PERIODS=1 TOGGLES=30 MAX_RESETS=1000 ~/starter-scripts/venv/bin/python relay_stress.py --run E --yes

  Run F — iso toggled, secondary pump + hp-call ON:

      CHARGE_POSTURE=0 PUMP_POSTURE=1 HP_POSTURE=1 LOADS=0 TARGET=iso PERIODS=1 TOGGLES=30 MAX_RESETS=1000 ~/starter-scripts/venv/bin/python relay_stress.py --run F --yes

  Restart the summer hack (it re-asserts the schedule state; expect it to
  reset 0x21 once at start and self-repair at its first 5-min enforce
  pass — that is the finding):

      sudo systemctl start spruce-summer-hack

  Leave the box:

      exit

  From this folder on the laptop, fetch the run files:

      scp 'spruce:~/relay-stress-runs/relay-stress-*' .

  (The 08-23 D used `MAX_RESETS=5`; the boxes above use 1000 so a re-run
  always goes the full length. The 08-23 run B was labelled `B100` on the
  box, so its files here are `relay-stress-B100.*`.)

- `relay-stress-<run>.log` — GENERATED: the harness log, verbatim (every
  write, every reset with its register snapshot, the actuation window).
- `relay-stress-<run>-results.json` — GENERATED per run: typed
  `PhaseResult` records + knobs + posture + window (kind-specific plain
  result file, no word). Runs kept: A, B (files labelled `B100`), C, D,
  E, F.
- `instances/<run>/gw.experiment.run-000.json` — emitted from every
  results file: `uv run python emit_instances.py` (run from this folder).
- `hw1.isone.me.versant.keene.spruce.ta-relay.stress.2026.08.23-gw.readings-000.json`
  — the immutable-store witness over the morning window (12:05–12:45 ET;
  1089 readings). Pulled with:

      uv run python ../pull_readings.py \
          --ta hw1.isone.me.versant.keene.spruce.ta \
          --channel secondary-flow --channel secondary-pump-ct --channel hp-odu-pwr \
          --channel primary-flow --channel hp-lwt --channel store-flow --channel tank1-depth1 \
          --start '2026-08-23 12:05' --end '2026-08-23 12:45' \
          --condition relay.stress.2026.08.23 --out .

  Display CSV from the instance (no DB access):

      uv run python ../pull_readings.py --display-from \
          hw1.isone.me.versant.keene.spruce.ta-relay.stress.2026.08.23-gw.readings-000.json

---

**From the instance to the display CSV.** The `*-gw.readings-000.json`
file is the canonical record: the channel words together with their
readings, validating against the sema registry. The `-display.csv`
sibling is presentation only — the same readings as natural-unit floats
(temperatures °F, flows gpm), converted per each channel word's own
encoding. Regenerate it any time, with no database or S3 access:

    uv run python ../pull_readings.py --display-from <instance>.json
