# spruce-pump-speed-sweep, queued (first run TBD)

> What this is: phase two of the DAC output rung (spruce-unlimbo,
> `dac-output.md` step 5), on the real spruce secondary pump: with the
> iso valve open and the secondary pump on, drive the 0-10V output
> through its range, first linearly and then in jumps, and evaluate
> pump speed as a function of the commanded output. Verdict in "Found"
> once run; the logbook line is the index record.

## Why

The secondary pump on spruce is a Grundfos UPMS 20-78 F (team Drive,
"Grundfoss UPMS 20-78 F" folder: data booklet, section 10 "External
control mode and signals"), an ECM circulator whose speed follows a
0-10 V linear input. Spruce has only ever run it at the DAC's EEPROM
power-on level; the write path has never moved it. Two things hang on
the answer:

- **The actuator works on the deployed plant**, end to end: dispatch →
  `ZeroTenOutputer` → Multi-Write → the pump changes speed, witnessed
  on the secondary-loop flow. Phase one (`2026-09-05-dac-output-bench/`)
  proves the chip leg on honeysuckle; this proves the pump leg.
- **The speed-versus-output curve** the control code will need: where
  the pump starts (the booklet gives a stop band at the bottom of the
  0-10 V profile, page 21), whether flow is linear in volts across the
  range, how fast it settles after a step, and whether the response to
  a jump differs from the response to a ramp. That curve is what turns
  "secondary pump on" into a controllable flow.

## Setup

**Plant state for the sweep:** iso valve OPEN (`iso-valve-relay`) and
secondary pump ON (`secondary-pump-relay`), heat pump and store pump
off, so the secondary loop circulates on its own and the only variable
is the DAC level. Both relays are commanded through admin the same way
the DAC is.

**What is measured, and from where:**

- `secondary-flow` (gpm, the secondary BTU pico) is the speed proxy: an
  ECM circulator's flow at fixed head tracks speed. Recorded by the
  scada under test on its own broker (local mosquitto through the
  tunnel; see isolation), pulled from the run log and the window's
  reported readings.
- `secondary-010v` (VoltsTimesTen) as reported by the outputer: the
  commanded level as the actor saw it.
- Secondary pump electrical power is NOT available today: spruce's
  eGauge meters the dist pump but not the secondary pump; the gw108's
  CT 2 (the 20 A voltage-output CT) is on the secondary pump but the CT
  channel vocabulary does not exist yet (`spruce_sema_gen.py` comment,
  `unsorted.md` "CT measurement chain"). Record that gap; power
  arrives when that vocabulary lands.

**Isolation (all three layers of `dac-output.md` "Isolation checklist
for the spruce window" must hold):**

1. Status tier with teeth: the layout cluster is staging; the branch's
   `gwsproto_sema_conformance.py --release-gate` is red by design.
2. Credential-structural: the window scada keeps the spruce identity
   but boots from `~/envs/dev.env` (dev-broker credentials only,
   upstream host the localhost tunnel, never hw1 credentials).
3. Paths-structural: boot through the window harness
   (`WindowScadaApp`, `experiments/2026-08-10-ads-declared-rate/
   window_boot.py`), whose paths root is `~/.config/gridworks/
   scada-experiment/`; env-only path overrides are discarded.

Window protocol: stop `gwspaceheat-restart.timer`, `gwspaceheat`, and
`spruce-summer-hack` (the hack exits to failsafe); before the deployed
scada restarts, verify its event dir holds nothing window-born (the
08-12 window #1 leak). Stopping services, placing env files, and
restarting are JM's to run; the session preps commands and the
watch-list. Cooling stakes: none in September on a held-open loop, but
the sweep's top end runs the pump at full speed for minutes; keep the
window short and the pump within its duty range.

**Code under test:** gridworks-scada `jm/spruce-unlimbo` at the commit
the honeysuckle rung verified (or later); the spruce artifact pair from
tlayouts `spruce_sema_gen.py` (real identity, real eGauge, the DAC
output on Dac2 C).

### Protocol

Each dispatch is an `AdminAnalogDispatch` for `secondary-010v`
(`Value` in volts × 10, 0–100), sent from the dev machine with a copy
of `2026-09-05-dac-output-bench/bench_dispatch.py` pointed at the spruce
window broker; a driver script here sequences them.

1. **Baseline.** Relays set (iso open, secondary pump on), DAC at the
   power-on level (EEPROM code 3020 ≈ 7.55 V, reported as 76). Hold
   3 min; record flow.
2. **Linear ramp up.** 0 → 100 in steps of 10, hold 90 s per step
   (long enough for flow to settle and two reported readings).
3. **Linear ramp down.** 100 → 0, same steps and holds: hysteresis
   check.
4. **Jumps.** A fixed random sequence over the same levels, e.g. 20,
   80, 40, 100, 10, 60, 0, 90, 30, 70, 50, hold 90 s each: settling time
   after large steps, and whether the level reached depends on the path.
5. **Restore.** DAC back to 76 (code 3040), relays to the summer
   posture, window closed per the protocol above.

### Claims wanting silicon

1. The dispatch changes the pump: `secondary-flow` moves with
   `secondary-010v` on the deployed plant.
2. The curve: flow versus volts across 0–10 V, the stop band at the
   bottom, and the settling time after a step, with ramp and jump
   sequences agreeing at each level.

## Found

(pending the first run)

## Timeline

(pending the first run; ET, one bullet per event)

## Analysis notes

- Flow at fixed head is the speed proxy; head is fixed only if the
  loop geometry does not change during the sweep (no valve moves,
  heat pump off). Any relay or valve event in the log invalidates the
  points around it.
- Full scale is 2.048 V × gain 1 × the gw108's 5× stage = 10.24 V, so
  code = `round(V / 10.24 × 4096)` and the EEPROM's 3020 is 7.55 V,
  reported as 76 (volts × 10). A dispatch of 76 writes code 3040, not
  the exact 3020: the power-on code is held exactly only until the
  first dispatch, so after the restore the pump runs on 3040 until the
  next reboot re-asserts EEPROM. Record which one the pump is left on.

## Folder contents & experimental method

All data in this folder is GENERATED: readings reported by the window
scada on the spruce box to the dev machine through the tunnel, and the
scada's own log. The window scada publishes to the dev broker only, so
nothing here is in the journal DB or the S3 eventstore; a re-run
produces a new dataset. The experiment STOPS the deployed scada and
the summer hack for the window (one instrument master at a time) and
restarts them after.

- `README.md` — this record.
- `sweep.py` — (to write) the dev-machine driver: relays, the ramp and
  jump sequences, timing; no data.
- `<run>-readings.json` — the window's reported `secondary-flow` and
  `secondary-010v` readings as a sema instance (generated).
- `boot-<DATE>.log` — the window scada's log (generated).

Regenerate everything from scratch: the protocol above, in a new
window; there is no regeneration of a past run.
