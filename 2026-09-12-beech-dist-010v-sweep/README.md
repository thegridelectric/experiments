# beech-dist-010v-sweep, 2026-09-12

Status: Draft · Pass 0 · Updated 2026-09-13

> What this is: the hardware witness for House0's 0-10V outputs on
> per-output components (spruce-unlimbo, house0-zero-ten-outputs):
> a window scada on the real beech box, on the one-arm `ZeroTenOutputer`
> with the GP8403 write path, admin making the zone1-down heat call on
> the krida witness rig so the distribution pump runs, then sweeping
> `dist-010v` through its range with dist flow and pump power watched,
> the DAC restored, the call released, beech handed back. Verdict in
> "Found" once run; the logbook line is the index record.

## Why

Scada `17e277d3` moved House0's three `*-010v` outputs onto
`i2c.dac.output.component.gt` against the Krida board record (two
GP8403 modules at 94 and 95), gave `ZeroTenOutputer` one arm with the
chip branch in its write path (the GP8403 output register, code in bits
4-15, low byte first; the range register once at boot), and retired the
`I2cZeroTenMultiplexer` that used to write those modules through its
own smbus handle. The suite proves the arm against the sim board
(MCP4728s at the same addresses) and pins the GP8403 bytes to what the
multiplexer wrote; no simulated GP8403 exists by design. The design
reaches Verified only when a real GP8403 output moves a real pump from
the new path, through the bus actor, and the reported `VoltsTimesTen`
channel tracks each commanded level.

The only GP8403 modules are in the field. Beech's `dist-010v` drives
the distribution pump, which the Caleffi zone box starts under a heat
call (krida witness, 2026-09-11: `dist-flow` 0 → 196 about 32 s after
the call). With the call held, the DAC level is the only variable and
`dist-flow` (the dist-btu pico) is the speed proxy; `dist-pump-pwr`
(the eGauge, register 9010) is the second witness if the eGauge driver
produces readings this time (it did not on 09-11; scada `58ee6df7`
since fixed its construction on pyModbusTCP 0.3.0).

Two things hang on the answer:

- **The GP8403 arm works on a deployed plant**, end to end: admin
  dispatch → `ZeroTenOutputer` → `I2cWriteReg` through the bus actor →
  the module → the pump changes speed, witnessed on flow.
- **Beech's dist pump under 0-10 V**: where it starts, whether flow is
  linear in volts, how the deployed 3.5 V sits in its range. The
  deployed layout runs it at 3.5 V (`InitialVoltsTimes100` 35; primary
  62, store 65), levels the window pair carries as its ops power-on
  list so the outputs boot to what beech runs at today.

## Setup

**Code under test.** gridworks-scada `jm/spruce-unlimbo` at `17e277d3`
(House0's three 0-10V outputs on per-output components against the
Krida record; the GP8403 arm; the multiplexer retired), in the full
clone at `~/gridworks-scada-unlimbo` on beech (its own venv, admin
installed, no flo). The deployed service in `~/gridworks-scada`
(`main`) is stopped for the window and never touched. The box's
`~/experiments` clone must be at a pushed SHA carrying this folder.

**Layout pair.** `instances/beech-window-gw.house0.layout-000.json` +
`…operational.params-000.json`, derived by `derive_layout.py`: the
krida witness rung's derivation (beech identity, zone1 main → down,
zone2 up cloned on relays 19/20, `ActuationAuthority=Standby`, the real
eGauge and dist-btu pico) applied to the scada House0 fixture pair as
it stands after `17e277d3` (each `*-010v` node on a DAC-output
component against the Krida record's GP8403 entries; the multiplexer
gone), plus beech's deployed power-on levels in `ZeroTenPowerOnList`.
The pair decodes through gwsproto (`sema_to_dc.load_layout`: 64 nodes,
three `I2cDacOutputComponent`s, board DACs `Dfr1`/`Dfr2` at 94/95
`Gp8403`) and validates with `sema validate`. Placed on the box as
`~/.config/gridworks/scada-experiment/hardware-layout.json` +
`operational-params.json` by `beech_window.sh on`.

| file | type | sha256 (first 16) |
| --- | --- | --- |
| `instances/beech-window-gw.house0.layout-000.json` | `gw.house0.layout/000` | `2d843c4cb4e48108` |
| `instances/beech-window-gw.house0.operational.params-000.json` | `gw.house0.operational.params/000` | `944b9a16497fe048` |

**Isolation.** As the krida witness: `~/envs/dev.env` on the box (real
beech identity, dev-broker creds only, upstream over the laptop's
`ssh -R 1885` tunnel, admin link on the box's own mosquitto), the
window booted through `../2026-08-10-ads-declared-rate/window_boot.py`
under `beech_window.sh`, events under the `scada-experiment` paths
root. The driver runs ON THE BOX (the spruce sweep's rule: a window
holding a real pump does not depend on the laptop's tunnel).

**What is measured, and from where.** `dist-010v` (VoltsTimesTen) as
the outputer reports it after each successful write, the commanded
level as the actor saw it; `dist-flow` (GpmTimes100, the dist-btu pico)
as the speed proxy; `dist-pump-pwr` (PowerW, eGauge 9010) if the
driver reports; the two zone relays' states from the snapshots.
Everything arrives on the admin link and is recorded by the driver.

**Plant state during the sweep.** The zone1-down heat call held by
admin (failsafe relay 17 to scada, ops relay 18 closed), as the krida
witness did; the standby local control actuates nothing on its own.
The window's other two outputs boot to beech's deployed levels and hold
them (the outputer's heartbeat), so the primary and store pumps are
where the deployed scada leaves them. Summer: no cooling stakes; the
sweep's top end runs the dist pump at full speed for a minute per
level.

**Driver.** `dist_sweep.py` here: the spruce sweep driver on the
House0 layout word, the heat call in front. Relay vocabulary and
expected states from each relay's `relay.control.config`; the restore
level from the ops artifact's `ZeroTenPowerOnList`; every command
echo-gated (15 s), an unanswered command aborts into restore.

**Protocol.**

1. Laptop: push `jm/spruce-unlimbo` and this repo; on beech
   `git -C ~/gridworks-scada-unlimbo pull` and `git -C ~/experiments pull`
   (pushed SHAs only). `./beech_window.sh on`: stops `gwspaceheat` and
   its restart timer, records both Krida port words, places the pair,
   boots the window scada (4 h safety bound). Boot cycles the vdc relay
   once, as every deployed restart does; the three outputs assert their
   power-on levels and the GP8403 range register.
2. On the box (ssh), the driver:

       cd ~/experiments/2026-09-12-beech-dist-010v-sweep
       mkdir -p /tmp/beech-dist-sweep
       setsid nohup timeout 3600 ~/gridworks-scada-unlimbo/gw_spaceheat/venv/bin/python \
           dist_sweep.py --run 1 > /tmp/beech-dist-sweep/sweep-1.stdout 2>&1 < /dev/null &
       tail -f /tmp/beech-dist-sweep/sweep-1.log

   Default plan `full` (0-10 V at 1 V up, down, eleven jumps, 60 s per
   level, about 40 min); `--plan short` is the five-minute version.
   Phases: call → baseline (120 s at 3.5 V) → up → down → jumps →
   restore (3.5 V, OpenRelay 18, SwitchToWallThermostat 17, admin
   released).
3. Laptop: `./beech_window.sh status` for the port words during the
   run (17 and 18 energized: `0x21: 0x3f`).
4. `scp beech:/tmp/beech-dist-sweep/sweep-1* .` then
   `ssh beech rm -rf /tmp/beech-dist-sweep`; `./beech_window.sh off`:
   port words after, boot log and the scada's pending report events
   copied here, the deployed service and timer restarted.
5. Afterwards: instances emitted from the results file, this README
   put in order (Found, Timeline, the data manifest), the spoke's
   witness line and the logbook line updated.

**The bar.** Every commanded level echoes on `dist-010v` within the
gate; `dist-flow` rises under the call, changes with the level across
the range and settles within each hold; restore returns the DAC to
3.5 V and the call is released with both relays in their de-energized
states; the deployed scada comes back with both port words as before.
No power cycle of the module: the GP8403 stores nothing, so the boot
range write and the first assert are the whole boot story.

**Dev rung (laptop, before beech).** The same driver against the sim
House0 fixture (orange1, one zone, `SimKridaDoubleRelayBoard16` with
two MCP4728s at 94/95) on the dev broker, scada `17e277d3`, `--plan
short --hold 20 --baseline 20 --zone zone1-main`; nothing flows in the
sim, so the flow verdict is expected FAIL there and every other check
PASS:

```sh
cd gridworks-scada && export PYTHONPATH=$PWD/gw_spaceheat
SCADA_PATHS__HARDWARE_LAYOUT=$PWD/tests/config/gw.house0.sim.layout.json \
SCADA_PATHS__OPERATIONAL_PARAMS=$PWD/tests/config/gw.house0.sim.operational.params.json \
SCADA_ADMIN__ENABLED=true SCADA_ADMIN__HOST=localhost SCADA_ADMIN__PORT=1885 \
SCADA_ADMIN__USERNAME=smqPublic SCADA_ADMIN__PASSWORD=smqPublic SCADA_SECONDS_PER_REPORT=60 \
  timeout 600 gw_spaceheat/venv/bin/gws run > ../experiments/2026-09-12-beech-dist-010v-sweep/dev-scada.log 2>&1 &
cd ../experiments/2026-09-12-beech-dist-010v-sweep
../../gridworks-scada/gw_spaceheat/venv/bin/python dist_sweep.py --run dev --env dev.env \
  --zone zone1-main --plan short --hold 20 --baseline 20 \
  --layout ../../gridworks-scada/tests/config/gw.house0.sim.layout.json \
  --ops ../../gridworks-scada/tests/config/gw.house0.sim.operational.params.json --out .
```

## Found

**Beech: not yet run.**

**Idle soak (2026-09-13 09:45–09:56 ET, scada `3f607f8c`): PASS.** The
sim House0 pair on the dev broker, no driver, 10 minutes to the
timeout's SIGTERM: three outputs ready at boot, no task died, the
derived generator's loop ran every minute through the tenth, no
missing channel or node. One boot-time finding: local control's
`initialize_actuators` (`tou_base.py:368`) calls `sieg_valve_hold` under
its own handle and the rights check refuses it (the relay's immediate
boss is sieg-loop), so the hold it intends never reaches the relay; it
is logged and harmless here, and it is the command-surface question of
the sieg loop. Log: `soak-idle-scada.log`.

**Driver soak (2026-09-13 09:56–10:07 ET, scada `3f607f8c`): PASS.** The
same pair, the sweep driver started 45 s after boot with the short
plan: all ten steps echoed on `dist-010v` (20, 50, 80, 100, 100, 80,
50, 20, 35, 20 volts times ten, each within the second), the heat call
acked and read back, restore and the two relay releases answered, the
driver's verdict PASS with the expected sim-only FAIL on dist flow (510
readings, 10 steps); the scada ran on after the release, through the
local control's re-wake, to the timeout's SIGTERM at 10:07 with no
task dead and no missing channel or node. Both soaks clean: the beech
window is no longer gated on the scada. Logs: `soak-driver-scada.log`,
`sweep-soak.log`, `sweep-soak-results.json`.

**Dev rung (2026-09-12 19:42–19:47 ET): the arm works; the run aborted
on an unrelated scada shutdown.** On the sim House0 fixture (scada
`17e277d3`, dev broker): all three outputs reported ready and the
scada counted 3/3; the local control set the ops-word defaults (0, 20,
40); the boot verify reprogrammed each sim MCP4728 once (fresh chips).
The driver's heat call went through (SwitchToScada acked and read
Scada, CloseRelay read RelayClosed); `dist-flow` stayed 0 (expected,
nothing flows in the sim). Levels 20 and 50 echoed on `dist-010v`
within the same second, through the real bus actor to the muxless
sim DAC at 94. Level 80 drew no echo: the scada had shut itself down
at 19:45:40 (`dev-scada.log`: the derived-generator task died at
19:43:33 on `'DerivedGenerator' object has no attribute
'latest_temps_f'`, and its watchdog stopped the proactor two minutes
later). Restore and the relay releases then found no scada. The
driver's abort-into-restore path ran as designed and logged each
failure. The derived-generator fault is in code this step did not
touch; it needs its own fix before the beech window, since the same
shutdown would end the window mid-sweep.

## Timeline

(ET)

- 2026-09-13 09:56:36 driver soak: scada booted; 09:59:25–10:02:31 ten steps echoed; 10:02:55 driver released admin, PASS; 10:07:05 SIGTERM, no fault.
- 2026-09-13 09:45:33 idle soak: sim House0 scada booted on the dev broker, three outputs ready the same second; 09:56:02 SIGTERM from the 630 s timeout, no fault.
- 2026-09-12 19:42:23 dev rung: sim House0 scada booted on the dev broker; three outputs ready 19:42:31.
- 19:43:00 driver started; 19:43:10 SwitchToScada and CloseRelay both acked and read back.
- 19:43:33 (scada) derived-generator task died; 19:44:48 driver: flow verdict FAIL (expected in the sim).
- 19:45:08 level 20 echoed; 19:45:29 level 50 echoed.
- 19:45:40 (scada) shutdown: derived-generator failed its watchdog.
- 19:46:04 level 80 no echo, ABORT; restore and releases unanswered; 19:46:51 driver done.

## Analysis notes

- `dist-010v` is the level the outputer wrote, not a measurement of the
  terminal; the pump's response is the measurement.
- The box clock ran about 70 s behind the laptop on 09-11; driver
  times are the box's when the driver runs there.
- `sema validate` on the window layout fails on a pre-existing
  `DataChannels.*.InPowerMetering` extra field inherited from the scada
  House0 fixture (the krida rung's pair fails the same way); the ops
  artifact validates. Fixture cleanup, not this rung's.

## Folder contents & experimental method

All data here is GENERATED by the window (readings and states the
window scada reports on its admin link, recorded by the driver on the
box; the scada's boot log and report events); nothing is pulled from
the journal or the eventstore. The experiment STOPS the deployed scada
for the window and restarts it after.

- `README.md` — this record.
- `derive_layout.py` — fixture pair → `instances/` (the krida
  derivation plus beech's power-on levels); reproducible:
  `python3 derive_layout.py`.
- `instances/` — the layout pair the window boots; after the run, the
  scada's report events and the emitted instances.
- `beech_window.sh` — on / off / status from the laptop (the krida
  rung's script pointed at this folder's instances).
- `dist_sweep.py` — the on-box driver.
- `dev.env` — the dev rung's admin-link block (dev broker, public creds).
- `dev-scada.log`, `sweep-dev.log`, `sweep-dev-results.json` — the dev
  rung on the sim House0 fixture.
- `soak-idle-scada.log`, `soak-driver-scada.log`, `sweep-soak.log`,
  `sweep-soak-results.json`, `soak-driver-console.log` — the 10-minute
  soaks on the sim House0 fixture (idle; with the driver in front).
- `sweep-<run>.log`, `sweep-<run>-results.json`, `boot-<stamp>.log` —
  (after the run) the driver's log and typed results from beech, the
  window scada's boot log.
