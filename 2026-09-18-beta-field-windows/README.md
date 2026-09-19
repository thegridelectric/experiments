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
3. Start the captures first, bracketing the actuation (begin before `on`,
   run past the last expected actuation), and prove the broker-side
   subscriber connects before `on`. Then:

        ./beech_window.sh on 30
        ./spruce_window.sh on 30
        ../gridworks-scada/gw_spaceheat/venv/bin/gwa watch <house>

4. Close with `off` if the bound has not already closed it; check `status`
   shows the recorded plant services running again:

        ./spruce_window.sh off
        ./beech_window.sh off

5. Record in the same sitting: a `gw.experiment.run` instance per house
   (`uv run python emit_instances.py`), evidence files with provenance
   headers, a logbook line, and this README brought current. Window logs
   arrive in `../scratch/` from `off`; event files and window layouts are
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
  (`0/2 zone gw channels populated`). Why they flatline en masse, and
  whether the bank-wide reboot is the right response, are both open.
- **Volts-to-temp divides by zero at the rail.** An open thermistor sits on
  the 3.3 V rail and the conversion raises `ZeroDivisionError` (a
  `gridworks.event.problem`) instead of refusing the reading.
- **Zones 1 & 2 report nothing.** The two zones on GPIO opto sensors
  produce no `*-opto-input`, `*-heat-call` or `*-floor-temp` while zones
  3–5 do. Whether the GPIO sensor path reaches the report is open.
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

Regenerate the instances from the logs already here:

    cd ~/GridWorks/experiments/2026-09-18-beta-field-windows
    uv run python emit_instances.py

Read a committed instance back through the snapshot codec:

    uv run python -c "from gwexp.sema.codec import default_codec; from pathlib import Path; print(default_codec.from_bytes(Path('instances/beech-gw.experiment.run-000.json').read_bytes()))"

No `gw.readings` instance lives here, so there is no display CSV.
