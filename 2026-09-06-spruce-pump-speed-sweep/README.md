# spruce-pump-speed-sweep, 2026-09-06

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
secondary pump ON (`secondary-pump-relay`), store pump off, so the
secondary loop circulates on its own and the only variable is the DAC
level. The heat-pump call relay is left where the hack left it unless
`--hp-off` is given (the Samsung ignores the contact today, 08-23). All
relays are commanded through admin the same way the DAC is, pump
before iso valve: energizing the iso relay with no other 0x21 coil
energized resets that expander about one toggle in three
(`2026-08-23-spruce-relay-stress/`).

**What is measured, and from where:**

- `secondary-flow` (GpmTimes100, the secondary BTU pico) is the speed
  proxy: an ECM circulator's flow at fixed head tracks speed. The
  window scada reports it in the snapshots it answers on its admin
  link; the driver records every snapshot.
- `secondary-010v` (VoltsTimesTen) as reported by the outputer: the
  commanded level as the actor saw it, forwarded on the admin link.
- Relay states from the snapshots' machine-state list, so a relay or
  valve moving mid-sweep is on the record (it invalidates the points
  around it, see Analysis notes).
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
   upstream host the localhost tunnel, never hw1 credentials). The
   admin link rides the box's own mosquitto with the local link's
   credentials (step 3 below).
3. Paths-structural: boot through the window harness
   (`WindowScadaApp`, `../2026-08-10-ads-declared-rate/window_boot.py`),
   whose paths root is `~/.config/gridworks/scada-experiment/`;
   env-only path overrides are discarded.

Window protocol: stop `gwspaceheat-restart.timer`, `gwspaceheat`, and
`spruce-summer-hack` (the hack exits to failsafe); before the deployed
scada restarts, verify its event dir holds nothing window-born (the
08-12 window #1 leak). Stopping services, placing env files, and
restarting are JM's to run; the session preps commands and the
watch-list. Cooling stakes: none in September on a held-open loop, but
the sweep's top end runs the pump at full speed for minutes; keep the
window short and the pump within its duty range.

**Code under test:** gridworks-scada `jm/spruce-unlimbo` at
`ba2c9883` or later (the commit honeysuckle run 4 verified); the spruce
artifact pair from tlayouts `spruce_sema_gen.py` (real identity, real
eGauge, the DAC output on Dac2 C), archived here under the sema
on-disk grammar.

**Driver:** `sweep.py` here, run ON the box (see Protocol). It speaks
the admin TUI's wire shape through the gwsproto types directly
(AdminAnalogDispatch, AdminDispatch(FsmEvent), SendSnap,
AdminReleaseControl) over paho, because the pi venv is built
`no_admin` and the gwadmin relay client keys its event vocabulary off
ScadaControlCapabilities, which a Nolan scada cannot emit yet
(`dac-output.md` failures item 1). Relay event vocabulary is read from
the layout file the scada boots. Every command waits for its echo
(the outputer's reading, or a snapshot showing the relay in the
expected state); no echo within 15 s aborts the sweep into restore
rather than continuing blind, since the admin link has no heartbeat
(`unsorted.md`).

**Rehearsed 2026-09-06 on the laptop** against a sim Nolan scada
(`tests/config/gw.nolan.*`, local mosquitto, admin link on): 34
levels, every one echoed within a second; all four relays confirmed
under admin (pump close, iso open, store open, hp open); restore and
release clean. Two rehearsal findings, both filed in the design (below),
none blocking the driver.

### Before the window: one prerequisite and a housekeeping item

1. **The spruce artifact boots on the branch (fixed 2026-09-06).**
   Rehearsing the window harness on the laptop against the regenerated
   spruce pair had failed in `DerivedGenerator`: the four affine depth
   channels carried `linear.one.dimensional.calibration` Version `001`
   (a hand-built dict in tlayouts, at a version sema squashed away on
   2026-08-13) while gwsproto pins `000`. The word sits outside the
   layout closure (`derived.channel.gt/002` types `Parameters` as a
   bare object), so no conformance check saw it and the Nolan fixture,
   with no affine channel, could not trip on it. tlayouts now seeds the
   word into its snapshot and builds the calibration through its class,
   the sim pair carries the calibration, the scada closure copy carries
   the word, and the pair archived here is the regenerated one
   (tlayouts commit pending at writing).
2. **The window scada's admin link.** `~/envs/dev.env` on spruce needs
   the admin block the honeysuckle bench used, pointed at the box's own
   mosquitto with the local link's user (non-repo box state; record it
   in spruce's `~/README.md`):

       SCADA_ADMIN__ENABLED=true
       SCADA_ADMIN__HOST=localhost
       SCADA_ADMIN__PORT=1883
       SCADA_ADMIN__USERNAME=<the SCADA_LOCAL_MQTT__USERNAME value>
       SCADA_ADMIN__PASSWORD=<the SCADA_LOCAL_MQTT__PASSWORD value>

3. **Home-dir leftovers.** Spruce's home dir holds leftovers from summer
   windows that its `~/README.md` does not record:
   `~/gridworks-scada-unlimbo`, `~/__pycache__`, `~/egauge.py`,
   `~/i2c.sh`. The second checkout STAYS: the window harness boots from
   it (`window_boot.py` `SCADA_GW`) and the driver runs in its venv;
   give it its `~/README.md` entry alongside `~/experiments`. Remove
   or record the rest with Jessica before the window.

### Protocol

Each dispatch is an `AdminAnalogDispatch` for `secondary-010v`
(`Value` in volts × 10, 0–100). The driver runs on the spruce box from
the `~/experiments` clone at a pushed SHA, launched over ssh with
`timeout` + `setsid nohup` so it survives the ssh session. The tunnel
stays only for observation (the LTN link to the dev broker), where a
drop costs data, not control.

Sequence (`sweep.py` phases; timing knobs on the command line). The
levels a run visits come from `--plan`; run 1 used `full`, the plan
below. Two follow-on plans sample against the booklet's input bands
(page 21, profile R: below 0.5 V minimum speed, 0.5-1 V stopped, 1-2 V
hysteresis, 2-3 V minimum speed, 3-10 V minimum to maximum):

- `bands` (run 2, ~19 min): one level per band, 0, 7, 15, 25, 40,
  entered from below on the way up and from above on the way down, no
  jumps. What it settles: the pump stops at 7, whether 15 keeps the
  previous state (hysteresis) in each direction, whether 0 and 25 both
  give the minimum flow.
- `linear` (run 3, ~65 min at 90 s holds): the speed band only, 30 to
  100 in steps of 5, up, down, and jumps 40, 90, 55, 100, 35, 75, 30,
  95, 45, 80, 60. The curve at twice run 1's resolution, none of it
  spent below the band. Use `--hold 60` (~45 min) if run 1 shows flow
  settling well inside 60 s.

1. **Posture.** Secondary pump ON, iso valve OPEN, store pump OFF, each
   confirmed in a snapshot before the next.
2. **Baseline.** DAC at the power-on level (EEPROM code 3020 ≈ 7.55 V,
   reported as 76). Hold 3 min; record flow.
3. **Linear ramp up.** 0 → 100 in steps of 10, hold 90 s per step
   (long enough for flow to settle and two or three snapshots).
4. **Linear ramp down.** 100 → 0, same steps and holds: hysteresis
   check.
5. **Jumps.** A fixed sequence over the same levels, 20, 80, 40, 100,
   10, 60, 0, 90, 30, 70, 50, hold 90 s each: settling time after
   large steps, and whether the level reached depends on the path.
6. **Restore.** DAC back to 76 (code 3040), admin released; relays stay
   in the sweep posture, which is the summer posture; window closed per
   the protocol above.

About 55 minutes end to end for `full`.

### Runbook

Commands under **dev machine** run from this folder; commands under
**spruce** run in a shell on the pi (`ssh spruce`).

**1. Regenerate and archive the spruce pair (dev machine, in tlayouts).** Ids come from the box's uploaded record,
so the regen reproduces the archived bytes; the diff proves it.

    cd ../../../tlayouts

    ../gridworks-scada/gw_spaceheat/venv/bin/python spruce_sema_gen.py

    cp output/spruce/gw.nolan.layout.json ../experiments/2026-09-06-spruce-pump-speed-sweep/hw1.isone.me.versant.keene.spruce-gw.nolan.layout-000.json

    cp output/spruce/gw.nolan.operational.params.json ../experiments/2026-09-06-spruce-pump-speed-sweep/hw1.isone.me.versant.keene.spruce-gw.nolan.operational.params-000.json

    cd ../experiments/2026-09-06-spruce-pump-speed-sweep

Then commit + push experiments (the archived pair and this README), so
the box pulls the exact bytes.

**2. Bring the box to the pushed state (spruce).**

    cd ~/experiments && git pull && git log -1 --format=%h

    cd ~/gridworks-scada-unlimbo && git fetch && git checkout jm/spruce-unlimbo && git pull && git log -1 --format=%h

    cd ~/gridworks-scada-unlimbo && gw_spaceheat/venv/bin/pip show gridworks-proactor | grep Version

If the proactor version is below `4.1.13+jm2`, refresh it as in the
honeysuckle runbook step 4b.

**3. Place the window artifacts (spruce).** The window scada reads
its pair from the experiment paths root.

    mkdir -p ~/.config/gridworks/scada-experiment

    cp ~/experiments/2026-09-06-spruce-pump-speed-sweep/hw1.isone.me.versant.keene.spruce-gw.nolan.layout-000.json ~/.config/gridworks/scada-experiment/hardware-layout.json

    cp ~/experiments/2026-09-06-spruce-pump-speed-sweep/hw1.isone.me.versant.keene.spruce-gw.nolan.operational.params-000.json ~/.config/gridworks/scada-experiment/operational-params.json

    grep -c SCADA_ADMIN__ ~/envs/dev.env

The last line must print 5 (blocker 2).

**4. Dry-run the driver (spruce).** Reads the layout, prints the plan
and the relay vocabulary, touches no broker.

    cd ~/experiments/2026-09-06-spruce-pump-speed-sweep

    ~/gridworks-scada-unlimbo/gw_spaceheat/venv/bin/python sweep.py --run dry --dry-run

**5. Open the observation tunnel (dev machine).** Reverse-forwards the
laptop's dev broker into the pi's 1885 for the LTN link. Optional for
control; without it the window's LTN link stays `awaiting_peer` and
its events wait under `scada-experiment/`.

    ssh -f -N -o ExitOnForwardFailure=yes -R 1885:localhost:1885 spruce

**6. Stop everything on the bus (spruce, JM).**

    sudo systemctl stop gwspaceheat-restart.timer gwspaceheat spruce-summer-hack

**7. Boot the window scada (spruce).** Bounded at 3900 s; the boot
asserts the paths-root isolation before running.

    mkdir -p /tmp/spruce-pump-sweep

    cd ~/gridworks-scada-unlimbo/gw_spaceheat && setsid nohup timeout 3960 venv/bin/python ~/experiments/2026-08-10-ads-declared-rate/window_boot.py 3900 ~/envs/dev.env > /tmp/spruce-pump-sweep/boot.log 2>&1 < /dev/null &

    grep -n "window boot\|isolation\|i2c-bus-init-failed\|admin:" /tmp/spruce-pump-sweep/boot.log

Wait for `admin:  awaiting_setup_and_peer -- mqtt_suback --> awaiting_peer`
and the DAC boot verify line before step 8.

**8. Run the sweep (spruce).** Watch `sweep-1.log` (line-flushed), not
the stdout file (block-buffered under redirection). Runs 2 and 3 are
the same line with `--run 2 --plan bands` and `--run 3 --plan linear`
(and their own log names); the window scada from step 7 serves all
three if its 3900 s budget allows, else boot it again first.

    cd ~/experiments/2026-09-06-spruce-pump-speed-sweep && setsid nohup timeout 3800 ~/gridworks-scada-unlimbo/gw_spaceheat/venv/bin/python sweep.py --run 1 > /tmp/spruce-pump-sweep/sweep-1.stdout 2>&1 < /dev/null &

    tail -f /tmp/spruce-pump-sweep/sweep-1.log

The last line is `PASS; …` or `ABORT: …`; either way the driver has
run restore (DAC 76, admin released) before it prints it.

**9. Collect (dev machine).** After the sweep's last line and the
boot log's `window done` line.

    scp spruce:/tmp/spruce-pump-sweep/sweep-1.log sweep-1.log

    scp spruce:/tmp/spruce-pump-sweep/sweep-1-results.json sweep-1-results.json

    scp spruce:/tmp/spruce-pump-sweep/boot.log boot-2026-09-06.log

    uv run python emit_instances.py

**10. Restore the box (spruce, JM).** Verify the deployed event dir
holds nothing window-born, then restart the services; remove what the
window placed.

    ls -la ~/.local/share/gridworks/scada/event/ | tail

    sudo systemctl start spruce-summer-hack gwspaceheat gwspaceheat-restart.timer

    rm -rf /tmp/spruce-pump-sweep

The window artifacts under `~/.config/gridworks/scada-experiment/`
stay (the experiment paths root, recorded in `~/README.md` since 08-12).

### Claims wanting silicon

1. The dispatch changes the pump: `secondary-flow` moves with
   `secondary-010v` on the deployed plant.
2. The curve: flow versus volts across 0–10 V, the stop band at the
   bottom, and the settling time after a step, with ramp and jump
   sequences agreeing at each level.

## Found

- **The ramp ignores the pump's input bands (2026-09-06, noticed during
  run 1).** Data booklet page 21, 0-10 VDC profile R: below 0.5 V the
  pump runs at minimum speed (signal-fail behaviour); 0.5-1 V standby
  (stopped); 1-2 V hysteresis; 2-3 V minimum speed; 3-10 V speed from
  minimum to maximum. Levels 0, 10 and 20 therefore sit outside the
  speed band (0 minimum speed, 10 stopped, 20 minimum speed at the
  hysteresis edge) and the speed range is sampled at only eight points
  at 1 V spacing. Read the low points of run 1 as a check of the bands
  on the real pump, not as curve points. A follow-on run should sample
  3-10 V, denser where the pump starts moving.

- **Run 1 (`full`, 2026-09-06 16:43-17:37 ET): PASS, 34 steps, 2525
  readings.** Flow versus level (volts x 10), settled value, same on
  the way up, down and in jumps to within 0.05 gpm: 30 -> 0.6, 40 ->
  2.3, 50 -> 3.7, 60 -> 5.2, 70 -> 6.6, 80 -> 8.0, 90 -> 9.0, 100 ->
  9.0 gpm. Linear from 3 V to 9 V at about 1.4 gpm per volt; the pump
  is at maximum by 9 V. 10 and 20 stop the pump; 0 runs it at 0.8 gpm
  (the booklet's signal-fail minimum speed), slightly above the 0.6 at
  30. Every DAC dispatch echoed within 0.1 s; the four relays held
  their posture throughout. Settling time is below the flow channel's
  reporting cadence (one reading per 45-90 s), so 90 s holds stay.
  `instances/1/`.
- **Run 2 (`bands`, 17:49-18:08 ET): PASS on the wire, no flow data.**
  The window boot's pico power-cycle did not bring the secondary BTU
  pico back; the pico-cycler, dormant under admin, logged it
  flatlined at 18:00 and could not cycle it, so `secondary-flow` is
  absent for the whole run (54 of 55 channels present). Every level
  echoed. The cycler woke on admin release and cycled the picos. The
  bands plan wants re-running once the cycler runs under admin
  (scada design: pico-cycler command). `instances/2/`.
- **Run 2b (`bands`, 19:44-20:03 ET, scada `829038b2` with the cycler
  kept awake under admin): PASS, 11 steps, flow present throughout.**
  Up from below: 0 -> 0.79 gpm (minimum speed), 7 -> 0.71 (still
  running: the stop band's lower edge on this pump is above 0.7 V, not
  the booklet's 0.5 V), 15 -> 0.08 (stopped), 25 -> no change
  (stopped), 40 -> 2.31. Down from above: 25 -> 0.00, 15 -> 0.00, 7 ->
  0.00 (all stopped), 0 -> 0.69 (minimum speed again). So the pump's
  stop behaviour is path dependent across 0.7-2.5 V: entered from
  below it runs at 0.7 V and stops at 1.5 V; entered from above it
  stays stopped down to 0.7 V and only 0 V restarts it. The booklet's
  "2-3 V minimum speed" band does not appear: 2.5 V leaves the pump
  wherever it was. Brief flow spikes (3.6-5.6 gpm, one reading each)
  appear at the minimum-speed levels; they are in the raw readings and
  not in the settled values. `instances/2b/`.
- **Run 3 (`linear`, 20:07-21:06 ET, 60 s baseline, 85 s holds):
  PASS, 42 steps, 2412 readings.** The curve at 0.5 V steps, settled
  gpm, up / down / jump agreeing to within 0.06 at every level:
  30 -> 0.63, 35 -> 1.57, 40 -> 2.3, 45 -> 3.05, 50 -> 3.76, 55 -> 4.5,
  60 -> 5.2, 65 -> 5.9, 70 -> 6.61, 75 -> 7.3, 80 -> 8.01, 85 -> 8.68,
  90 -> 8.99, 95 -> 9.0, 100 -> 8.98. Linear from 3.5 V to 8.5 V at
  1.45 gpm per volt (about 0.72 per step), the knee to maximum between
  8.5 and 9 V, flat above 9 V. Every dispatch echoed within 0.1 s; the
  relays held posture throughout. A first attempt at run 3 was
  interrupted after one step to fit the window scada's budget
  (`sweep-3a.*`, `instances/3a/`, ABORT: interrupted; restore ran).
  `instances/3/`.

## Timeline

- 16:42 deployed scada, restart timer and summer hack stopped; window
  scada booted, admin link up, DAC EEPROM verified.
- 16:43 run 1 started; posture 16:44; baseline to 16:47; up to 17:04;
  down to 17:20; jumps to 17:37; PASS, DAC restored to 76.
- 17:47 window scada's 3900 s budget ended; fresh window scada booted
  (pico power-cycle at 17:48).
- 17:49 run 2 started; 18:00 secondary BTU pico flatlined (cycler
  dormant); 18:08 PASS, admin released, cycler woke.
- 18:09 window scada stopped (SIGINT); deployed event dir held only
  its own 16:42 shutdown event; services restarted; window /tmp
  removed.
- 19:42 second window: scada `829038b2` pulled (cycler awake under
  admin), services stopped, window scada booted, pico reboot at
  19:42:23, flow back by 19:43:12.
- 19:44 run 2b (bands) started; 20:03 PASS.
- 20:03 fresh window scada for run 3; 20:04 run 3 started, interrupted
  at 20:07 (would outlast the budget); 20:07 run 3 restarted with 60 s
  baseline and 85 s holds; up to 20:30; down to 20:51; jumps to 21:06;
  PASS.
- 21:07 window scada stopped; deployed event dir held only its own
  19:42 shutdown event; services restarted; window /tmp removed.

## Analysis notes

- Flow at fixed head is the speed proxy; head is fixed only if the
  loop geometry does not change during the sweep (no valve moves,
  heat pump off). Any relay or valve state change in the results'
  `States` list invalidates the points around it.
- Full scale is 2.048 V × gain 1 × the gw108's 5× stage = 10.24 V, so
  code = `round(V / 10.24 × 4096)` and the EEPROM's 3020 is 7.55 V,
  reported as 76 (volts × 10). A dispatch of 76 writes code 3040, not
  the exact 3020: the power-on code is held exactly only until the
  first dispatch, so after the restore the pump runs on 3040 until the
  next reboot re-asserts EEPROM. Record which one the pump is left on.
- Snapshot cadence bounds the flow resolution (the scada answers a
  SendSnap every 30 s from the driver and pushes its own); the
  `secondary-010v` echo is immediate (forwarded SingleReading).

## Folder contents & experimental method

All data in this folder is GENERATED: readings and machine states the
window scada reported on its admin link on the spruce box, recorded by
the driver there and scp'd back, plus the scada's own log. The window
scada publishes to the dev broker only (and its admin link to the box's
own mosquitto), so nothing here is in the journal DB or the S3
eventstore; a re-run produces a new dataset. The experiment STOPS the
deployed scada and the summer hack for the window (one instrument
master at a time) and restarts them after.

- `README.md` — this record.
- `sweep.py` — the on-box driver: posture relays, the ramp and jump
  sequences, echo-gated timing, restore; harness code, no data.
- `emit_instances.py` — dev-machine emitter: from a
  `sweep-<run>-results.json` builds `instances/<run>/` holding the
  `gw.readings` instance (channel words from the archived layout,
  readings the driver recorded) and the `gw.experiment.run` instance,
  through the vendored snapshot so they validate at construction.
- `hw1.isone.me.versant.keene.spruce-gw.nolan.layout-000.json`,
  `hw1.isone.me.versant.keene.spruce-gw.nolan.operational.params-000.json`
  — the spruce pair from tlayouts `spruce_sema_gen.py` (tlayouts
  `56dbcd1`, renamed from `output/spruce/` to the sema on-disk grammar).
  Regenerated 2026-09-06 after the calibration-version fix (item 1
  above); runbook step 1 reproduces them.
- `sweep-<run>.log`, `sweep-<run>-results.json` — (after the run) the
  driver's log and typed results, generated on spruce.
- `boot-<DATE>.log` — (after the run) the window scada's log.
- `instances/<run>/` — (after the run) the sema instances emitted from
  the results file.

Regenerate everything from scratch: the runbook above, in a new
window; there is no regeneration of a past run. Instances from an
existing results file:

    uv run python emit_instances.py

Display CSV from an existing instance:

    uv run python ../pull_readings.py --display-from instances/1/hw1.isone.me.versant.keene.spruce.ta-pump.speed.sweep.1-gw.readings-000.json

---

**From the instance to the display CSV.** The `*-gw.readings-000.json`
file is the canonical record: the channel words together with their
readings, validating against the sema registry. The `-display.csv`
sibling is presentation only — the same readings as natural-unit floats
(temperatures °F, flows gpm), converted per each channel word's own
encoding. Regenerate it any time, with no database or S3 access:

    uv run python ../pull_readings.py --display-from <instance>.json
