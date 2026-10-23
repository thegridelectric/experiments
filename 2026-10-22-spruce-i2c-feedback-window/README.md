# spruce-i2c-feedback-window, 2026-10-22

> What this is: one bounded spruce window of `jm/spruce-unlimbo` at
> `aa3b0709`, with the iso-valve relay toggled under admin to provoke the
> expander 0x21 reset and witness the new I2C fault feedback. The verdict
> is in "Found"; the logbook entry is the index record.

## Why

In the 2026-10-21 window (`../2026-10-21-spruce-pump-on-power-window/`)
expander 0x21 reset during the boot posture and the scada took a minute
to notice (the bus actor's 60 s heartbeat was the only detector) and the
secondary-pump relay forty seconds to recover (the 300 s verify pass was
the only retry). Commit `aa3b0709` makes a failed actuation ask the bus
actor to check its expander at once, retries the command at 2 s and
10 s, and keeps the bus error text and register forensics in the
Critical. The claim: a reset met by an actuation raises its Critical
within a second and has the relay back within ten.

The 2026-08-23 relay stress run (`../2026-08-23-gw108-relay-stress/`)
found that energizing the iso-valve relay with no other 0x21 coil on
resets the chip about one toggle in three, so toggling the iso under
admin is the reproducer.

## Setup

- Spruce, the window scada `~/gridworks-scada-unlimbo` pulled to
  `aa3b0709` before run 1, the window pair in `scada-experiment/`
  identical to `tlayouts/output/spruce/`. The winter hack and the
  production scada stopped for the window and restored by the box at
  its end.
- `./spruce_window.sh on 11`, then the admin driver from the laptop
  over the box's mosquitto (the `gwa` spruce entry): admin takes the
  tree, TurnOff to hp-boss, six CloseValve/OpenValve pairs to
  `iso-valve-relay` 5 s apart, release. The heat pump off or winding
  down throughout, so a closed iso dead-heads nothing.
- The commands: `runbook.sh`, run twice. Both windows ran through a
  subagent on the runbook; nothing else was run on the box.

## Found

**Run 1 (07:57 ET) tested nothing.** The driver crashed on an import
before sending anything (it was built from the 2026-09-07 hp-boss drive
and kept that script's `house_0_names` import, a module `main` has and
this branch does not), so no admin dispatch reached the box. The boot
was a warm takeover and the eleven minutes passed with no `i2c-` glitch
and no CRITICAL. Its log is not kept.

**Run 2 (08:11 ET): PASS on the repair, the Critical unobserved.**
Twelve iso actuations under admin, five expander 0x21 resets. Four
came on the iso energize (`OpenValve`), as the stress run predicted,
and each was repaired with the relay confirmed back 1.15 s after the
dispatch: the write, the 0.5 s readback confirm, the requested check's
0.5 s confirm, clear-then-configure, the re-assert. The fifth followed
a `CloseValve` and was repaired 3.6 s after it, the relay's 2 s retry
meeting it. Before `aa3b0709` the same reset waited up to 60 s for the
heartbeat and the relay up to 300 s for the verify pass.

| # | dispatch | 0x21 re-initialized | iso confirmed back |
|---|---|---|---|
| 1 | OpenValve 08:13:20.370 | +1.059 s | +1.150 s |
| 2 | OpenValve 08:13:30.371 | +1.061 s | +1.141 s |
| 3 | OpenValve 08:13:40.350 | +1.060 s | +1.158 s |
| 4 | OpenValve 08:13:50.395 | +1.069 s | +1.150 s |
| 5 | CloseValve 08:13:55.364 | +3.619 s | driver saw `ValveClosed` again at 08:13:59 |

No Critical was observed anywhere: not in the box log, not in the
persisted events, not at the admin client. A glitch is forwarded by
the scada to the LTN on the upstream link and nothing else
(`actors/scada.py`, the `Glitch` case), and this window's upstream
link was refused for its whole length (`gridworks.event.problem`
"Connection refused" every 2 to 128 s; the broker capture was empty).
The 10-21 window's Criticals came off the broker capture. So the
"Critical within a second" half of the claim is unobserved here, and
nothing refutes it; the next window runs with `--ltn` or `--cert` to
see it.

## Timeline

- 07:57:48 ET run 1 `on 11`; 07:58:03 boot posture, warm takeover;
  07:59:22 driver crashed; 08:09:24 bound closed the window; 08:09:40
  `off`, services active; 08:10:02 `capture off`.
- 08:11:44 run 2 `on 11`; 08:11:58 boot posture (0x20 warm takeover
  logged, no 0x21 line); 08:13:08 admin link active; 08:13:10 TurnOff
  to hp-boss; 08:13:15 to 08:14:10 six CloseValve/OpenValve pairs,
  five 0x21 resets repaired as tabled; 08:14:30 admin released, local
  control re-booted its posture with the iso open; 08:23:21 bound
  closed the window; 08:23:37 `off`, services active; 08:23:54
  `capture off`.

## Analysis notes

- The box log stamps are the box clock in ET; the driver log stamps
  are the laptop clock (the two agreed to the second this morning).
- A glitch goes to the LTN on the upstream link only; it is not logged
  on the box and not persisted as an event. With that link down a
  Critical leaves no trace, which is why this folder has none.
- "OpenValve confirmed on verify-pass retry" is the relay's re-assert
  on `ExpanderReinitialized` finding its pending command confirmed; the
  attempt that met the reset failed its readback silently in the log,
  since its Critical was the only report.
- The repair table above is hand-read from the box log. No sema word
  covers a per-actuation repair latency (`i2c.result` reports one bus
  operation, `glitch` the Critical that was not seen); the table is the
  record until a word for an expander reset and its repair exists.

## Folder contents & experimental method

All data here was GENERATED by this run: the window scada's own log on
the box and the admin driver's log on the laptop. The run stopped the
house's plant services for the window and drove relays through the
window scada; nothing was read from the immutable store. A re-run
produces a new dataset. Pruned after the run: run 1's box log (nothing
tested), the two broker captures (four weather messages, then empty),
the 31 persisted events (problem events for the refused upstream link
and `report.event`s whose states the box log also has) and a grep of
the run 2 log.

- `runbook.sh`: the commands as run, from `experiments/` on the laptop,
  with the admin sequence as the `admin_drive.py` line a re-run uses.
- `evidence/spruce-window-20261022-082343.log`: the run 2 window
  scada's log, copied by `off` from the box's
  `/tmp/spruce-window/boot.log`; provenance header at the top. The
  repair table is read from its `[i2c-bus]` and `[iso-valve-relay]`
  lines around 08:13.
- `evidence/admin-drive.log`: the driver's log of what it sent and the
  iso states it received (run 2); provenance header at the top.
- `instances/gw.experiment.run-001.json`: the window as a
  `gw.experiment.run`, emitted by `emit_instances.py` from the box
  log's first and last stamps.

Regenerate the instance:

    uv run python 2026-10-22-spruce-i2c-feedback-window/emit_instances.py

Display view of the run word:

    uv run python -c "import json;d=json.load(open('2026-10-22-spruce-i2c-feedback-window/instances/gw.experiment.run-001.json'));print(','.join(d))"

No `gw.readings` instance in this folder.
