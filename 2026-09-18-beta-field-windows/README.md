# beta-field-windows, since 2026-09-18

> What this is: the recurring field test of the `jm/spruce-unlimbo` scada.
> After roughly each spoke the branch runs in a bounded window on one house
> of each layout family. This README states what the rounds have
> established (**Known**) and what they have opened (**Mystery**, under
> Process); each round rewrites it, and the per-round narrative lives in git
> history and the logbook. Evidence files and `gw.experiment.run` instances
> accumulate in the folder, named by house and window stamp.

## Why

The unlimbo work rewrote how a layout is generated, decoded and acted on.
The suite, the sim driver and the tlayouts twins all agree with a layout by
construction, so none of them says a real house boots on the generated
pair, that the actors needing hardware start, or that the control code the
layout selects is the code the house should run this season. A window on a
real house is the only check that does.

One house per layout family per round: **spruce** for `gw.nolan.layout`
(`ActuationAuthority` Active, the path that actuates), **beech** for
`gw.house0.layout` (Standby, the shape the Millinocket installs arrive in),
and one of **fir / elm / oak** for `gw.house0.no.sieg` once that layout
ships. A round may skip a family the spoke could not have touched; the
logbook line says which families ran.

## Known

What the rounds have established about the unlimbo scada.

- **The generated pairs boot clean and select the right control.** Spruce
  boots the Nolan control (Active); beech boots House0 `StandbyLocalControl`
  (Standby). Zero tracebacks, no decode failures on either.
- **The Nolan control is unfit to run spruce in the heating season.** Its
  TOU-cooling branch takes zones off their thermostats and shuts the heat
  pump down while `ServiceMode` is Heating. The winter hack stays spruce's
  plant controller; the Nolan seasonal branch must be settled before it
  runs a real house.
- **Standby is not "nothing actuated".** At boot the control energizes the
  relays that hold the plant off and the sieg loop makes a move. Expect
  relay motion at boot on an installed Standby house.
- **The window's relay writes reach the Krida bus.** On beech the
  `vdc-relay` bit on the port word toggles on the bus exactly against the
  log's `OpenRelay` / `CloseRelay` pairs — the window drives real hardware,
  not just the log.
- **Relay state is carried in `StateList`, not as readings.** Relay-state
  channels are absent from `ChannelReadingList` because a report carries
  them in `StateList`; that absence is not missing data.
- **The scada announces its layout and deed once per run, on a real box.**
  When the upstream link first goes send-capable the scada sends its
  `layout.lite` to the LTN, then either the `ta.deed` if one is configured
  or a `no-ta-deed` Warning glitch naming the deed path if not. Both
  branches are witnessed on real houses, each exactly once per run: spruce
  sent its `ta.deed` (TaAlias `hw1.isone.me.versant.keene.spruce.ta`,
  `ValidatedRealAssetAndGps`), beech with no deed sent the glitch
  (`Details "No ta.deed at …/ta-deed.json"`).
- **A matching pico reports its identity at DEBUG, and the glitch rides the
  wire.** A pico posts its params to the scada at its own boot, and the
  scada checks the board and MicroPython version against the layout only
  inside that post; a match sends a Debug `pico-identity-matches` glitch
  that reaches the LTN, not just the box log. Witnessed on spruce for the
  four picos that posted (store-btu, buffer, tank1, secondary-btu), zero
  "differs from the layout" Warnings. A pico that posts no params is never
  checked.
- **The boot params post is a race any pico can lose.** On a power cycle
  some picos resume readings with no params post, a different set each
  boot, and whenever the post is sent its path, name and word are right
  (`../2026-09-19-spruce-pico-params/`). A pico that misses runs unchecked
  until its next boot.
- **The boot-time command tree matches each house's authority.** Both
  houses set `auto.lc.n` at boot and the flat-declared actuators answer
  under it (`auto.lc.n.hp-boss.hp-scada-ops-relay`); spruce then starts the
  Nolan control, beech's Standby control drives everything off.
- **A zone already calling at boot is invisible until the capture
  boundary.** `GpioSensor` starts `latest_value` at 0 and publishes on
  change or at the `CapturePeriodS` boundary (300 s). The spruce optos are
  `DigitalZeroIsActive`, so a calling zone reads 0, equals the initial
  value and publishes nothing: no `-opto-input` and no `-heat-call` for up
  to five minutes after boot. Spruce zones 1 and 2 were calling through
  both rounds' windows, which is why they reported nothing while the idle
  zones 3–5 did.
- **A whitewire house derives no heat calls.** The derived generator emits
  a zone `heat-call` only when a reading for its input channel is sent to
  it. Beech's inputs are the `-whitewire-pwr` channels the power meter
  captures, and the power meter sends its readings to the scada only, so
  beech's `heat-call` channels never get a value and `dist_pump_monitor`
  reads nothing. The sim pairs feed heat calls through the sim sensor, so
  the suite does not see it.
- **The open-thermistor `ZeroDivisionError` channels feed nothing.** Spruce
  `fancoil-depth3` and `pipes1-depth3` sit at the 3.3 V rail; neither is an
  input to a derived channel, the store pass or the buffer predicates.
- **Both real heat pumps have a defrost signature.** Spruce's hp-odu is
  `SamsungAE055FCYDCG`, beech's `LGARUM048GSS5`; both are keys in
  `DEFROST_SIGNATURES`.

## Process

Temporary while the branch is off `main`; removed when the deployment spoke
completes. The window-open hook prints this section before any
`_window.sh on`, so a round cannot start without reading it.

**A round.**

1. Read the current mysteries below. Pick the ones this round can shed
   light on and decide what evidence would do it, before anything is
   switched on.
2. Pre-flight — `./<house>_window.sh status` on each house. Push the scada
   head and pull it on the box; regenerate the window pair if the spoke
   changed a gen and place it with `./put_layout.sh <house> <change>`. `on`
   refuses when the box checkout or the window pair is behind — a refusal
   is the pre-flight doing its job.
3. Open the windows. `on` starts `capture_broker.py` on the laptop's dev
   broker if none is running and refuses to open a window without a
   proven capture; a bus-side capture (port samples, register reads) is
   still started by hand, before `on`, and runs past the last expected
   actuation. `--debug` puts the scada's loggers at DEBUG; `--ltn` runs
   the LTN on the laptop against the target's layout. `dev` is the
   laptop's scada checkout on its sim pair, the rehearsal for a house:

        ./house_window.sh dev on 5 --debug --ltn
        ./beech_window.sh on 30 --debug
        ./spruce_window.sh on 30 --debug
        ../gridworks-scada/gw_spaceheat/venv/bin/gwa watch <house>

4. Close with `off` if the bound has not already closed it; check `status`
   shows the recorded plant services running again; stop the capture after
   the last window:

        ./spruce_window.sh off
        ./beech_window.sh off
        ./house_window.sh capture off

5. Record in the same sitting: a `gw.experiment.run` instance per house
   (`uv run python emit_instances.py`), evidence files with provenance
   headers, a logbook line, and this README brought current. Window logs,
   the LTN log and the broker capture (`broker-capture-<stamp>.jsonl` with
   its provenance sidecar) arrive in `../scratch/`; event files and window layouts are
   pulled off the boxes read-only with `scp` from
   `~/.local/share/gridworks/scada-experiment/event/` and
   `~/.config/gridworks/scada-experiment/`.

**Distillation rule.** A mystery a round resolves leaves the list and its
answer joins **Known**; how the understanding got there stays in git
history and the logbook. Route a defect to the spoke that owns the code, or
to the odds-and-ends spoke when none does; an executor claim a round
verifies gets its `Reviewed` pointer here.

**Current mysteries.**

- **The beech sieg loop's initialization.** It initializes Blind, assumes
  `FullyKeep`, runs a 110 s full-send move that ends in `SteadyBlend`
  reporting itself zero seconds long, then sits "Engaging brain, control
  state Blind, hp boss HpOff". Must be understood before any actuating
  (BufferOnly / TOU) run on beech.
- **Pico ingestion on both boxes.** One dead pico (spruce floor1) triggers
  a bank-wide vdc-cut reboot every ~65 s, so every healthy pico pays for
  the dead one. On beech every pico flatlined in waves and none recovered
  (`0/2 zone gw channels populated`); in a 70 s beech window only
  `dist2-flow` delivered data, and store-flow, sieg-flow and dist2-flow were
  reported `PicoMissing`. Why they flatline en masse, and whether the
  bank-wide reboot is the right response, are both open.
- **Beech's pico params are unwitnessed.** No beech pico posted params in
  either round, so neither the identity check nor the older-firmware
  `TankModuleParams` the current word is expected to reject has been seen.
  Needs a beech window long enough to hold a pico-cycler reboot.
- **A Warning glitch the scada sends is not in the box log.** Beech's
  `no-ta-deed` shows only as an outbound `Glitch` line; the
  `ShNodeActor` senders log `Warning Glitch: …` but the announcement builds
  its `Glitch` directly. Someone reading the box log alone does not see it.
- **Volts-to-temp divides by zero at the rail.** An open thermistor sits on
  the 3.3 V rail and the conversion raises `ZeroDivisionError` (a
  `gridworks.event.problem`) instead of refusing the reading. Seen on spruce
  `fancoil-depth3` and `pipes1-depth3`, once each per window.
- **Beech report starvation.** Only the eGauge power channels and the
  0-10V readbacks reported; every thermistor, flow, BTU, water-temp and
  zone channel was absent. Confirm this is all downstream of the pico
  ingestion mystery.

## Folder contents & experimental method

All data here was GENERATED by this experiment — nothing from the journal
DB or the S3 eventstore. Each window ran with its upstream link pointed at
a dev broker with no consumer on it, so the reports and events never left
the boxes; a re-run produces a new dataset, none of this regenerates. The
experiment touches the running system: each box's plant services (and on
spruce the winter hack) are stopped for the window and restarted by the box
afterward.

Round one (2026-09-18):

- `spruce-window-*.log`, `beech-window-*.log` — each window scada's stdout,
  copied off the box by `house_window.sh <house> off`, with provenance
  sidecars. EXTERNAL EVIDENCE.
- `beech-port-samples.txt` — the Krida port word at 0x20 read off the bus
  once a second, with its provenance sidecar. EXTERNAL EVIDENCE.
- `spruce-on.log`, `beech-on.log` — each `on` console record, carrying the
  layout sha256 prefixes the gate checked and the services it stopped.
  EXTERNAL EVIDENCE.
- `broker-capture-failed.log` — the one-line `mosquitto_sub` refusal, kept
  as evidence that no broker-side capture of round one exists. EXTERNAL
  EVIDENCE.
- `instances/` — the window-born event files from each box's
  `~/.local/share/gridworks/scada-experiment/event/`, copied untouched and
  renamed to the dash-separated convention
  `<house>-<HHMMSSmmm UTC>[-<subject>]-<type.name>-<version>.json`, plus the
  two `gw.experiment.run` instances this folder emits.
- `emit_instances.py` — builds `instances/<house>-gw.experiment.run-000.json`
  from the first and last stamped line of each window log, constructing
  through the gwexp snapshot class and reading the written file back through
  the codec.

Round two (2026-09-19), dev rehearsal of the startup announcements:

Two one-minute dev windows on the scada change `dfc35644`
(`jm/spruce-unlimbo`), each `./house_window.sh dev on 1 --debug` with
no LTN, to see whether the scada announces itself on its own when the
upstream link first becomes send-capable. Both wrote to one broker capture,
`../scratch/broker-capture-20260919-132924.jsonl`, 163 messages over the two
windows.

- The first window (13:29:26 ET) ran with no deed in the dev config dir. It
  sent one `to.ltn.layout-lite` at +1.0 s and one Warning glitch at +1.0 s
  with Summary `no-ta-deed` and Details "No ta.deed at
  tests/config/ta-deed.json". Neither repeated for the rest of the window.
- The second window (13:30:28 ET) ran with `SCADA_PATHS__TADEED` pointed at
  `tests/config/gw.nolan.ta.deed.json`, and the env reaches the scada
  process: one `to.ltn.layout-lite` at +1.0 s, one `to.ltn.ta-deed` at
  +1.0 s carrying TaAlias `d1.isone.me.versant.keene.spruce.ta`,
  ValidationState `ValidatedSimulatedAsset`, ValidatorAlias
  `d1.validator.gridworks`, and no `no-ta-deed` glitch.

Both branches of the announcement are witnessed, each exactly once per run,
with no LTN on the broker. The capture is the only evidence of this round;
it stays in `../scratch/` and no instance is emitted for a dev window.

Round three (2026-09-19), the announcement and the pico identity on real
houses:

Two 5-minute `--debug` windows on scada `dfc35644` (`jm/spruce-unlimbo`, the
head that adds the announcement and the DEBUG pico-identity glitch; both
boxes fast-forwarded to it first), one target each, no LTN. Both windows
wrote to one capture, `broker-capture-20260919-141154.jsonl`, 21 messages.

- **beech — the no-deed announcement.** `./beech_window.sh on 5 --debug`.
  With no deed in the box config dir, the scada sent one `layout.lite` (85
  ShNodes) to the LTN and one Warning glitch, Summary `no-ta-deed`, Details
  `No ta.deed at /home/pi/.config/gridworks/scada-experiment/ta-deed.json`,
  Node `s`, from `hw1.isone.me.versant.keene.beech.scada`. Each once.
- **spruce — the deed announcement and the pico identity at DEBUG.**
  `./spruce_window.sh on 5 --debug`, closed after ~2.5 min to restore the
  winter hack. One `layout.lite` (98 ShNodes, `ActuationAuthority` Active)
  and one `ta.deed`, each once. One pico-cycler reboot, after which four of
  the nine pico-fed actors (store-btu, buffer, tank1, secondary-btu) posted
  params and each sent a Debug `pico-identity-matches` glitch; all four
  reached the capture as `Type Debug` messages. No "differs from the
  layout" Warning. Two `gridworks.event.problem` (`fancoil-depth3`,
  `pipes1-depth3`).

The capture's 21 messages: beech `power.watts`, `gridworks.ping`, the two
forecasts, `layout.lite`, the glitch and two snapshots; spruce the same
four openers, `layout.lite`, `ta.deed`, the four Debug glitches and three
snapshots. Capture stamps are the laptop clock, about 72 s ahead of the
boxes. The collector was running about 7 s before beech's first log line;
its sidecar records neither the scada SHA nor the probe result, and the SHA
is in the window-log sidecars.

Evidence in the folder: the capture and the beech window log, whole, and
`spruce-window-20260919-141515.excerpt.log`, 85 lines cut from the 1.6 MB
DEBUG trace by the patterns its sidecar lists (the announcement, the
identity glitches, the cycler cycle, the problem events, the command tree,
the GPIO sensor starts, first and last stamped line). Each has a provenance
sidecar. `instances/{beech,spruce}-gw.experiment.run-000.json` are this
round's (round one's are in git history); the excerpt keeps the first and
last stamps, so the spruce instance regenerates from it unchanged.

Regenerate the instances from the logs already here:

    cd ~/GridWorks/experiments/2026-09-18-beta-field-windows
    uv run python emit_instances.py

Read a committed instance back through the snapshot codec:

    uv run python -c "from gwexp.sema.codec import default_codec; from pathlib import Path; print(default_codec.from_bytes(Path('instances/beech-gw.experiment.run-000.json').read_bytes()))"

No `gw.readings` instance lives here, so there is no display CSV.
