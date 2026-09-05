# dac-output-bench, 2026-09-05

> What this is: the DAC output actuator's bench rung (spruce-unlimbo,
> `dac-output.md` step 4): does `ZeroTenOutputer` on the real honeysuckle
> gw108 take a dispatched level, write it to the chip through `I2cBus`,
> report the VoltsTimesTen channel, and hold it across the 60 s
> re-assert? Verdict in "Found" below; the logbook line is the index record. Zero stakes: nothing is wired to the bench Z6 output.

## Why

The 0-10V write path has never run in reality: spruce's secondary pump
runs at the EEPROM power-on speed (`2026-08-12-spruce-witness-window`,
"the DAC write path was not exercised"), and the 08-12 bench witnessed
only the writer's boot verify and heartbeat, never a commanded level.
The actuator rebuilt on the relay pattern (scada `341c99de`, word gate
sema `d6f59e7`) is what the spruce window (step 5) will run; this rung
proves the dispatch leg on silicon first, and it gates the command-tree
matrix, which cannot be tested with an actuator missing from the tree.

### Claims wanting silicon

1. **Boot EEPROM verify on the output component** (not the retired
   writer): boot finds Dac2 channel C at the layout's PowerOn 3020 (the
   08-12 bench left it there) and verifies silently.
2. **Dispatch → Multi-Write**: an `AdminAnalogDispatch` for
   `secondary-010v` reaches the outputer through the admin tree, the
   chip's channel C input register reads the commanded code, and the
   actor reports `secondary-010v` at the commanded volts × 10.
3. **Heartbeat holds the commanded level**, not the power-on code: the
   60 s re-assert after the dispatch writes the last command; EEPROM is
   untouched (still 3020).

## Setup

Isolation: the pi's own mosquitto on localhost with the `bench` user, the
`d1.bench.honeysuckle` identity, no bridge, no prod credentials anywhere on
the box, no deployed scada or systemd scada unit; the one tunnel forwards the
dev machine INTO the pi's broker. The persister's 153 un-acked bench events
(July–August boots) are archived out of the event dir before the boot so
nothing replays.

- **Code under test:** gridworks-scada `jm/spruce-unlimbo` `5940d1b9`
  (push, then on the pi `git pull` in `~/gridworks-scada`; the pi holds
  `e551c2e1` from the 08-12 bench). Driver venv per `tools/mkenv-pi.sh`.
- **Artifacts:** the honeysuckle pair, emitted by tlayouts
  `honeysuckle_sema_gen.py` (tlayouts `56dbcd1`, the commit that gave
  honeysuckle its real eGauge identity). The generator writes them as
  `output/honeysuckle/gw.nolan.layout.json` and
  `gw.nolan.operational.params.json` (its word-named output convention);
  this folder archives the exact bytes under the sema on-disk grammar,
  `d1.bench.honeysuckle-gw.nolan.layout-000.json` and
  `d1.bench.honeysuckle-gw.nolan.operational.params-000.json`, so the
  subject is in the filename. The scada at this commit reads them from
  its config dir as `hardware-layout.json` and `operational-params.json`.
- **Broker:** the pi's mosquitto, `localhost:1883`, `bench` user. The
  scada's admin link is off by default; the runbook's step 6 enables it
  in the pi's `gw_spaceheat/.env` (non-repo box state, recorded there).
- **Dispatch sender:** `bench_dispatch.py` here, run on the dev machine
  through an ssh tunnel to the pi's broker; it uses the gridworks-admin
  client, so the wire shape is the admin TUI's.

### Runbook (backup → boot → dispatch → readback → restore)

Two machines take part. Commands under **dev machine** run from this
folder on the laptop. Commands under **honeysuckle** run in a shell on
the pi (`ssh honeysuckle`), one command per block, in order.

**1. Generate the honeysuckle pair (dev machine, in tlayouts).** The
layout is honeysuckle's own, from `honeysuckle_sema_gen.py`: the real
board, the site eGauge, and `secondary-010v` on Dac2 channel C. Ids are
stable, so the regen reproduces the archived bytes; the diff proves it.

    cd ../../../tlayouts

    ../gridworks-scada/gw_spaceheat/venv/bin/python honeysuckle_sema_gen.py

    diff output/honeysuckle/gw.nolan.layout.json ../experiments/future/dac-output-bench/d1.bench.honeysuckle-gw.nolan.layout-000.json

    diff output/honeysuckle/gw.nolan.operational.params.json ../experiments/future/dac-output-bench/d1.bench.honeysuckle-gw.nolan.operational.params-000.json

    cd ../experiments/future/dac-output-bench

**2. Ship the artifacts (dev machine).** The scada reads its layout as
`hardware-layout.json` and its operational params as
`operational-params.json`, both in the pi's scada config dir. The layout
lands under a side name first so the standing layout can be backed up
before it is replaced.

    scp d1.bench.honeysuckle-gw.nolan.layout-000.json honeysuckle:~/.config/gridworks/scada/hardware-layout.dac-output.json

    scp d1.bench.honeysuckle-gw.nolan.operational.params-000.json honeysuckle:~/.config/gridworks/scada/operational-params.json

**3. Back up the standing layout and swap in the bench pair
(honeysuckle).** The standing file is the 08-12 bench artifact (md5
`af75763f…`); it comes back at the end.

    cd ~/.config/gridworks/scada

    cp hardware-layout.json hardware-layout.standing.json

    cp hardware-layout.dac-output.json hardware-layout.json

**4. Bring the checkout to the code under test (honeysuckle).** The pi
holds `e551c2e1` from the 08-12 bench; the rung needs `5940d1b9`, which
carries the rebuilt actuator and the Nolan word mirror. The last command
prints the hash to confirm.

    cd ~/gridworks-scada

    git fetch

    git checkout jm/spruce-unlimbo

    git pull

    git log -1 --format=%h

**5. Archive the persister's old events (honeysuckle).** The event dir
holds 153 un-acked events from the July and August bench boots. On
link-up the persister replays every file there to the broker it
connects to. That broker is the pi's own mosquitto, which forwards
nowhere, so this is hygiene rather than containment: the run's log then
shows only this boot's events.

    cd ~/.local/share/gridworks/scada

    mkdir -p event-archive

    mv event/* event-archive/

    ls event-archive | wc -l

**6. Enable the scada's admin link (honeysuckle, once).** The admin
link is off by default. These lines go at the end of
`~/gridworks-scada/gw_spaceheat/.env`, pointing the link at the pi's own
broker with the same `bench` user the other two links use (copy the
password from the `SCADA_LOCAL_MQTT__PASSWORD` line already in the file).
Non-repo box state, recorded here.

    SCADA_ADMIN__ENABLED=true
    SCADA_ADMIN__HOST=localhost
    SCADA_ADMIN__PORT=1883
    SCADA_ADMIN__USERNAME=bench
    SCADA_ADMIN__PASSWORD=<same as SCADA_LOCAL_MQTT__PASSWORD>

**7. Open the tunnel (dev machine).** The dispatch sender publishes to
the pi's broker as if it were local. This forwards the laptop's port
1884 into the pi's 1883; nothing on the pi gains a route outward. Leave
it up for the run.

    ssh -f -N -L 1884:localhost:1883 honeysuckle

**8. Boot the scada (honeysuckle).** Backgrounded with a four-minute
timeout so the run ends on its own; stdout and stderr go to one log.
Boot verify runs first (the EEPROM check against the layout's PowerOn
values), then the first heartbeat at about 60 s.

    cd ~/gridworks-scada/gw_spaceheat

    nohup timeout 240 venv/bin/python cli.py run > /tmp/dac-output-boot.log 2>&1 &

**9. Dispatch 5.5 V (dev machine).** Wait about 40 s after the boot for
the verify to complete. The sender connects through the tunnel,
requests the scada's control capabilities, and publishes an
`AdminAnalogDispatch` for `secondary-010v` with `Value=55` (volts × 10).
The scada wakes into Admin, rewrites the command tree so admin is the
boss of every actuator, and forwards the dispatch to the outputer,
which Multi-Writes code 2200 to Dac2 channel C and reports the channel.
The `HONEYSUCKLE_MQTT_PASS` value is the pi's `bench` broker password
(its `SCADA_LOCAL_MQTT__PASSWORD`).

    HONEYSUCKLE_MQTT_PASS=... ../../../gridworks-scada/gw_spaceheat/venv/bin/python bench_dispatch.py 55

**10. Read the chip (honeysuckle).** Wait past the next heartbeat (60 s
after the dispatch) so the re-assert has run. With the scada still up,
select mux channel 2 on the TCA9548A and read the MCP4728's 24 bytes.
Decode per the paragraph below; save the output as `chip-<DATE>.txt`.

    /usr/sbin/i2ctransfer -y 1 w1@0x70 0x04

    /usr/sbin/i2ctransfer -y 1 r24@0x60

**11. Release admin (dev machine).** Hands the scada back to Auto; the
timeout then ends the run.

    HONEYSUCKLE_MQTT_PASS=... ../../../gridworks-scada/gw_spaceheat/venv/bin/python bench_dispatch.py release

**12. Collect the log (dev machine).**

    scp honeysuckle:/tmp/dac-output-boot.log boot-<DATE>.log

**13. Restore the standing layout (honeysuckle).** The bench pair
stays under its side name; the standing 08-12 artifact is the deployed
bench layout again.

    cd ~/.config/gridworks/scada

    cp hardware-layout.standing.json hardware-layout.json

**Chip readback decode.** `w1@0x70 0x04` selects mux channel 2 (Dac2 per
the board record: TCA9548A at 0x70, MCP4728 at 0x60). The 24-byte read
is four channels × (3 input-register bytes + 3 EEPROM bytes). Channel C
is bytes 12–17: input code = `((b13 & 0x0F) << 8) | b14`, EEPROM code =
`((b16 & 0x0F) << 8) | b17`. Expected after the dispatch: input code =
`round(5.5 / (2.048 × 1 × 5) × 4096)` = 2200 (internal 2.048 V ref, gain
1, the gw108's 5× output stage), EEPROM code 3020 unchanged.

### Expected log lines

- boot: `secondary-010v: EEPROM verified against layout PowerOn values`
- dispatch: `About name is secondary-010v` (scada), then a
  `secondary-010v` channel reading at 55 from the outputer
- no `i2c-dac-write-failed` / `i2c-dac-eeprom-verify-failed` glitches

## Found

**Two of three claims not reached; one real finding on each leg, and
the reproducer stands.** Two boots (pi clock, ~1 min behind ET):
boot 1 07:45–07:49, boot 2 07:54–07:59.

- **Claim 1, boot verify: FAIL as stated, with a finding.** Both boots
  raised `i2c-dac-eeprom-reprogrammed`, yet the chip's EEPROM for
  Dac2 channel C read `0x8b 0xcc` before and after (`chip-2026-09-05.txt`):
  code 3020, VREF internal, gain 1, exactly the layout's PowerOn
  values. `verify_eeprom` therefore reports a mismatch on bytes that
  match and reprograms every boot; the reprogram path works (the
  glitch clears, the bytes stay right), but the "verifies silently"
  outcome never happens. Suspect `read_eeprom_mismatch`'s comparison,
  not the chip.
- **Claim 2, dispatch → Multi-Write: FAIL, with a finding.** The
  admin dispatch reached the scada (`Message from Admin!`, `Admin Wakes
  Up`, `About name is secondary-010v`, boot 2 at 07:55:50), the scada
  went to Admin and forwarded through `process_analog_dispatch`, and
  then nothing: no outputer log line and the chip's channel C input
  register still 3020 ninety seconds later, past a heartbeat. Every
  rejection branch in `ZeroTenOutputer.process_analog_dispatch` logs,
  so the message most likely never reached the actor. `Scada._send_to`
  routes by communicator name and has no final `else`: a node whose
  communicator is not registered under its name is dropped silently.
  That, or the boss-handle rewrite under Admin, is where the next
  session looks first (test candidate: `_send_to` to a ZeroTenOutputer
  node on the Nolan sim fixture, asserting the actor receives it).
- **Claim 3, heartbeat holds the commanded level: not reached** (no
  commanded level was written).
- **Side findings.** (a) The scada's admin link takes the password
  from `SCADA_ADMIN__PASSWORD`; boot 1 ran with a `_PASS` key and the
  link connected and dropped every backoff cycle (fixed before boot
  2). (b) `Trouble with SendLayout: 'NoneType' object has no attribute
  'component'` on every admin link-up: a House0 relay-multiplexer
  lookup on a Nolan layout; the admin client never receives
  ScadaControlCapabilities, so the admin TUI cannot watch a Nolan
  scada until that is fixed. (c) The eGauge component boots against
  the real meter with no errors in the log.
- **Isolation held:** every link on the pi's own broker; the 153
  archived events stayed archived; nothing left the box.

## Timeline

- 07:45:11 boot 1 (pi clock); 07:45:17 `i2c-dac-eeprom-reprogrammed`;
  admin link connect/disconnect cycling from 07:45:18.
- 07:48 dispatch attempts from the dev machine fail to connect (TLS
  default on in the sender; fixed) and then reach a scada whose admin
  link is down.
- 07:49:11 boot 1 ends on its timeout; log not preserved (overwritten
  by boot 2; its content is quoted above from the session record).
- 07:54:55 boot 2; admin link `awaiting_peer` at 07:54:55, `active` at
  07:55:42 on the sender's first message; `i2c-dac-eeprom-reprogrammed`
  again.
- 07:55:50 dispatch 55 received and forwarded by the scada; no
  outputer activity follows.
- 07:57:19 chip read: channel C input 3020, EEPROM 3020.
- 07:57:29 admin releases control; 07:59:51 boot 2 ends; standing
  layout restored (md5 `af75763f…`).
## Analysis notes

- `AnalogDispatch.Value` is volts × 10 (0–100); the chip code is
  `round(V / (2.048 × gain × 5) × 4096)` with the gw108's 5× output
  stage, so 55 → 2200. The power-on code 3020 is held exactly (not
  rounded through volts × 10) until the first dispatch.
- The readback is taken with the scada running, between heartbeats;
  the mux stays on channel 2 after the scada's last op, and a bare
  `i2ctransfer` read does not disturb the MCP4728's registers.

## Folder contents & experimental method

All data in this folder is GENERATED by the experiment's own harness
on the bench pi; none of it is in the journal DB or the S3 eventstore
(the bench scada talks only to the pi's own broker). A re-run produces
a new log, never a regeneration. The experiment stops nothing: no
service runs on the pi; the scada under test is started by the runbook
and ends on its own timeout.

- `README.md` — this record.
- `bench_dispatch.py` — dev-machine dispatch sender (gridworks-admin
  client over the ssh tunnel); harness code, no data.
- `d1.bench.honeysuckle-gw.nolan.layout-000.json`,
  `d1.bench.honeysuckle-gw.nolan.operational.params-000.json` — the
  exact artifact bytes booted: honeysuckle's own pair from tlayouts
  `honeysuckle_sema_gen.py` at tlayouts `56dbcd1`, renamed from the
  generator's `output/honeysuckle/` word-named files to the sema on-disk
  grammar. Regenerate: runbook step 1 (ids are stable, so the regen
  reproduces these bytes).
- `boot2-2026-09-05.log` — the scada's stdout/stderr for boot 2
  (generated, copied from the pi's `/tmp/dac-output-boot.log`); boot 1's
  log was overwritten, see Timeline.
- `chip-2026-09-05.txt` — the 24-byte `i2ctransfer` readback after the
  boot-2 dispatch plus the log trail at that moment (generated).

Regenerate everything from scratch: the runbook above, top to bottom.
No `gw.readings` instance: the evidence is the log and the chip read.
