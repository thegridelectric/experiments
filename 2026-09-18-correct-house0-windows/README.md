# correct-house0-windows, 2026-09-18

> What this is: the closing rung of the correct-house0 work (OPS-539) —
> the unlimbo scada run in a bounded window on spruce and on beech
> against the layout pairs tlayouts generates, read two ways (the log
> and the data). Verdicts per claim in "Found"; the logbook entry is the
> index record.

## Why

The correct-house0 work rewrote how a layout is generated, decoded and
acted on. Every check up to here was the suite, the sim driver and the
tlayouts twins: a simulator agrees with a layout by construction, so
none of it says the real houses boot on the generated pair, that the
actors that need hardware start, or that the control code the layout
selects is the control code the house should have in September.

Two houses cover the two families. Spruce runs the Nolan layout with
`ActuationAuthority` Active, so it exercises the control path that will
actuate. Beech runs the House0 layout with `ActuationAuthority` Standby,
which is the shape the three Millinocket installs arrive in this fall.
Beech also carries the siegenthaler loop, and a loop left fully closed
while the heat pump runs overheats the heat pump and trips it, so the
relay positions the window drives have to be checked against the bus,
not just against the log.

## Setup

**Code under test.** gridworks-scada `jm/spruce-unlimbo` at `cd34f5ef`
("layout twins check every circuit's whitewire channel and heat call").
Both boxes' `~/gridworks-scada-unlimbo` checkouts were fast-forwarded to
it before the run, and both boxes' `~/experiments` clones to `5c30b84`.

**The window script.** `experiments/house_window.sh <house> on|off|status`,
called by `spruce_window.sh` and `beech_window.sh`. `on` refuses unless
the box's window pair in `~/.config/gridworks/scada-experiment/` is
byte-identical to `tlayouts/output/<house>/` and the box's unlimbo
checkout is at the laptop's pushed scada head. It records which of the
house's plant services are running, stops those, and the box starts
exactly those again when the window scada exits — the minutes bound, a
crash, or `off`. It never writes a layout; `put_layout.sh` does.

The `on` gate printed the pairs it checked (`spruce-on.log`,
`beech-on.log`):

    hardware-layout.json: identical to the gen output (f826ad8ed1c5)
    operational-params.json: identical to the gen output (4bc47aa64bea)

for spruce, and `49bb38b5cfa6` / `2bece511c7cf` for beech. The services
stopped were `spruce-winter-hack gwspaceheat gwspaceheat-restart.timer`
on spruce and `gwspaceheat gwspaceheat-restart.timer` on beech.

**Boot.** `~/experiments/2026-08-10-ads-declared-rate/window_boot.py`
from `~/envs/dev.env`: the upstream link is `localhost:1885`, the
`ssh -R` tunnel to the laptop's `gw-dev-rabbit`, for observation only;
the admin link is the box's own mosquitto at `localhost:1883`.

**No broker-side capture.** The laptop `mosquitto_sub` against the dev
broker was refused — `Connection error: Connection Refused: bad user
name or password`; the scada user in the laptop `.env` is not a valid
user on the dev rabbit (`broker-capture-failed.log`). Both windows'
upstream links reached `awaiting_peer` and stayed there, there being no
LTN on the dev broker:

    2026-09-18 19:10:39.526 gridworks_mqtt:  awaiting_setup_and_peer -- mqtt_suback --> awaiting_peer

So every report stayed on its box under `scada-experiment/event/`, and
those files are the data half of this record.

## Found

### spruce

**a. The generated pair boots and selects the Nolan control. PASS.**
951 log lines, zero tracebacks, zero `ERROR` lines, no decode failures.

    2026-09-18 19:10:39.324 [lc] Starting Nolan Local Control in Normal (TOU cooling; ops ActuationAuthority Active, ServiceMode Heating)
    2026-09-18 19:10:39.406 [lc] Nolan: actuators left at their adopted states; nothing commanded

**b. The Nolan control is not fit to run spruce in the heating season.
FAIL, and the window was closed early for it.** Thirty seconds after the
line that says nothing was commanded, the TOU-cooling logic took three
zones off their thermostats and shut the heat pump down, while
`ServiceMode` was Heating:

    2026-09-18 19:11:09.385 [lc] SwitchToScada to zone1-bedrooms-failsafe-relay
    2026-09-18 19:11:09.387 [lc] OpenRelay to zone1-bedrooms-ops-relay
    2026-09-18 19:11:09.388 [lc] SwitchToScada to zone2-living-rm-failsafe-relay
    2026-09-18 19:11:09.390 [lc] OpenRelay to zone2-living-rm-ops-relay
    2026-09-18 19:11:09.391 [lc] SwitchToScada to zone4-garage-failsafe-relay
    2026-09-18 19:11:09.392 [lc] OpenRelay to zone4-garage-ops-relay
    2026-09-18 19:11:09.394 [lc] TurnOff to hp-boss
    2026-09-18 19:11:24.397 [lc] OpenRelay to secondary-pump-relay

Taking the failsafe relay to scada while the ops relay is open removes
the zone's call. The heat pump was already idle (`hp-odu-pwr` 0 in the
report), so nothing was lost. The winter hack came back at 19:19:57 box
and put the house back on its thermostats two seconds later:

    Sep 18 19:19:59 spruce python[10072]: INFO ZONES RELEASED: all six failsafe relays de-energized, scada relays 0 — every zone on its own thermostat
    Sep 18 19:19:59 spruce python[10072]: INFO SECONDARY PUMP -> OFF (hp-odu 0 W)

Verdict: the winter hack stays spruce's plant controller. The Nolan
control needs its seasonal branch settled before it runs a real house.

**c. The silent spruce pico is floor1's, not the tank module. PASS on
identification, FAIL on the cycler's behaviour.** The cycler named it
and then rebooted every pico on the box roughly every 65 s for the rest
of the window:

    2026-09-18 19:13:09.445 [pico-cycler] floor1 pico_71156b flatlined
    2026-09-18 19:13:09.448 [pico-cycler] TRIGGERING PICO REBOOT! triggered by floor1 pico_71156b
    2026-09-18 19:14:14.490 [pico-cycler] TRIGGERING PICO REBOOT! Flatlined picos: ['pico_71156b']
    2026-09-18 19:15:19.523 [pico-cycler] TRIGGERING PICO REBOOT! Flatlined picos: ['pico_71156b']

The pico that stopped reporting after the 2026-09-15 reflash is floor1's.
One dead pico power-cycles the healthy ones continuously — the reboot is
a bank-wide vdc cut, so every pico on the box pays for one that will not
come back.

**d. Data: one report, 71 channels, all carrying values.** The window
produced a single `report.event` (19:15 box) before it was closed. The
window layout declares 86 `DataChannels` and 25 `DerivedChannels`; 71
appear in the report and none has an empty value list. The 40 absent
names split three ways.

Twenty are relay-state channels, which the report carries in `StateList`
rather than as readings — expected, not a gap:
`buffer-bottom-elt-relay`, `buffer-top-elt-relay`, `charge-valve-relay`,
`hp-scada-ops-relay`, `iso-valve-relay`, `secondary-pump-relay`,
`store-pump-relay`, `tank1-bottom-elt-relay`, `tank1-top-elt-relay`,
`vdc-relay`, and the five zones' `*-failsafe-relay` / `*-ops-relay` pairs.

Six are floor1's, the pico from (c): `floor1-depth1-device`,
`floor1-depth1-micro-v`, `floor1-depth2-device`, `floor1-depth2-micro-v`,
`floor1-depth3-device`, `floor1-depth3-micro-v`.

The rest are the real gap. Zones 1 and 2 have no `*-opto-input` and no
`*-heat-call` in the report while zones 3, 4 and 5 have both
(`zone3-upstairs-opto-input` 1, `zone3-upstairs-heat-call` 0, and the
same for zone4-garage and zone5-living-rm-fancoil). The log shows the
same split from the other side — the periodic heat-call pass names only
zones 3, 4 and 5:

    2026-09-18 19:15:00.831 [derived-generator] [HeatCall periodic] zone3-upstairs-heat-call now=1789773300.8 next=1789773300 period=300

Zones 1 and 2 are the two on GPIO sensors (`[zone1-bedrooms-opto]
GpioSensor started on GPIO 17`, zone 2 on GPIO 27). Also absent:
`zone1-bedrooms-floor-temp`, `zone2-living-rm-floor-temp`,
`zone4-garage-floor-temp`, the four `*-set` setpoint channels, and the
three energy channels `required-energy`, `usable-energy`,
`transactive-power`.

**Plainly wrong values in that report.**

- `store-cold-pipe` n=71 last=14782 — 147.82 C, and 71 readings in a
  slot where its peers report 3. A chattering input, not a temperature.
- `fancoil-depth3` micro-v 3299998 / device -12620 and `pipes1-depth3`
  micro-v 3300000 / device -12986 — both sitting on the 3.3 V rail, the
  signature of an open thermistor input.
- Three `gridworks.event.problem` events, all the same:
  `Summary: "Volts to temp problem for pipes1-depth3"`,
  `Details: "... 0: <ZeroDivisionError>  <float division by zero>"`.
  The volts-to-temp conversion divides by zero at the rail instead of
  refusing the reading.

Everything else reads sane: zone `gw-temp` around 20 C, buffer and tank1
depths 18-19 C, and the derived F channels agree with their device
values (`buffer-depth1-device` 1934 cC ↔ `buffer-depth1` 6681, which is
66.81 F). `hp-odu-pwr` 0.

### beech

**e. The generated House0 pair boots and selects the Standby control.
PASS.** 949 log lines, zero tracebacks.

    2026-09-18 19:09:14.161 Creating LocalControl with actuation authority Standby and seasonal storage mode AllTanks, using actors.local_control.house0.standby.StandbyLocalControl

**f. Standby is not "nothing actuated".** At boot the control de-energized
most relays and then deliberately energized the ones that hold the plant
off, and the sieg loop started a move:

    2026-09-18 19:09:14.232 [lc] energizing key relays for keeping things off
    2026-09-18 19:09:14.233 [lc] auto.lc.n sending SwitchToScada to Hp Failsafe auto.lc.n.hp-failsafe-relay
    2026-09-18 19:09:14.233 [lc] auto.lc.n sending SwitchToScada to Aquastat Ctrl auto.lc.n.aquastat-ctrl-relay
    2026-09-18 19:09:14.234 [lc] TurnOff to hp-boss
    2026-09-18 19:09:14.235 [sieg-loop] Moving to full send
    2026-09-18 19:09:14.261 [sieg-loop] Task ae9b: move to send for 110 seconds

Standby means the control does not chase a heat call. It still drives
the plant to a known off state on the way in. Anyone planning a Standby
window on an installed house should expect relay motion at boot.

**g. Relay state agrees with the log: the window drove toward send, not
keep. PASS, with one part unverified.** `hp-loop-on-off-relay` and
`hp-loop-keep-send-relay` carry identical polarity in the deployed
layout (`~/.config/gridworks/scada/hardware-layout.json`, actors
`relay14` and `relay15`) and in the window layout — `NormallyClosed`
with `DeEnergizedState: RelayClosed` for the on/off relay, `DoubleThrow`
with `DeEnergizedState: SendMore` for the keep/send relay. The keep/send
relay was never energized during the window, so the valve was on the
SendMore side throughout. The on/off relay moved as the log says:

    2026-09-18 19:09:14.271 [sieg-loop] auto.lc.n.sieg-loop sending CloseRelay to HpLoopOnOff relay auto.lc.n.sieg-loop.hp-loop-on-off-relay
    2026-09-18 19:11:04.452 [sieg-loop] auto.lc.n.sieg-loop sending OpenRelay to HpLoopOnOff relay auto.lc.n.sieg-loop.hp-loop-on-off-relay

`CloseRelay` de-energizes a `NormallyClosed` relay, which powers the
motor; `OpenRelay` energizes it and the motor stops. The 110 seconds
between them is the move.

The bus samples in `beech-port-samples.txt` start at box 19:16:11, after
the move, so they cannot witness it. What they do show is the resting
word `0x20: 0xf2 0xdf` for 140 of 150 samples: byte 0 `0xf2` has bits 3,
2 and 0 low, which by the board record is Relay5 (hp-failsafe), Relay6
(hp-scada-ops) and Relay8 (aquastat-ctrl) energized — exactly the three
"energizing key relays for keeping things off" named in the log. Byte 1
`0xdf` has bit 5 low, which is Relay14 energized, the motor off, the
state the 19:11:04 `OpenRelay` put it in.

**The samples do prove the window's writes reach the Krida.** Bit 7 of
byte 0 is Relay1, the vdc relay. It goes low for exactly five samples at
each pico-cycler pair:

    19:17:04 0x72 0xdf  ... 19:17:08 0x72 0xdf
    19:18:10 0x72 0xdf  ... 19:18:14 0x72 0xdf

against the log's `19:17:04.344 OpenRelay to vdc-relay` /
`19:17:09.365 CloseRelay to vdc-relay` and the same pair a minute later.

**h. Open oddity, not resolved here.** The sieg loop began from an
assumed `FullyKeep` (the state machine initialized Blind) and a full-send
move of 110 s ended in `SteadyBlend`, not in a fully-send state, and
reported itself as zero seconds long:

    2026-09-18 19:09:14.235 [sieg-loop] DoneInitializingBlind: Initializing -> Blind
    2026-09-18 19:09:14.271 [sieg-loop] StartKeepingLess: FullyKeep -> KeepingLess
    2026-09-18 19:11:04.453 [sieg-loop] StopKeepingLess: KeepingLess -> SteadyBlend
    2026-09-18 19:11:04.453 [sieg-loop] Movement ae9b completed: 0 seconds, state SteadyBlend

The loop then sat in `Engaging brain, control state is Blind, hp boss
state is HpOff` every 30 s for the rest of the window. This has to be
understood before any actuating (BufferOnly / TOU) run on beech.

**i. Beech's picos never reported anything usable. FAIL.** The cycler
lost them in waves across the half hour and re-triggered a bank reboot
about every 65 s, 17 triggers in all:

    2026-09-18 19:10:32.385 [pico-cycler] sieg-flow pico_4e6e35 flatlined
    2026-09-18 19:13:44.273 [pico-cycler] buffer pico_72a121 flatlined
    2026-09-18 19:13:44.281 [pico-cycler] tank1 pico_0efd3c flatlined
    2026-09-18 19:13:44.290 [pico-cycler] tank2 pico_319230 flatlined
    2026-09-18 19:13:44.299 [pico-cycler] tank3 pico_742221 flatlined
    2026-09-18 19:14:58.016 [pico-cycler] Sending problem event for zombies [' pico_4e6e35 [sieg-flow]']
    2026-09-18 19:17:04.340 [pico-cycler] dist2-flow pico_2a7e22 flatlined
    2026-09-18 19:21:09.339 [pico-cycler] store-flow pico_6d5039 flatlined
    2026-09-18 19:24:44.434 [pico-cycler] primary-btu pico_7a4d2b flatlined
    2026-09-18 19:24:44.443 [pico-cycler] dist-btu pico_47352a flatlined

No pico recovered. The window's own closing line says the same thing
about the zone sensors: `== window done: 0/2 zone gw channels populated ==`.

**Beech data.** Six `report.event` files (19:10 through 19:35 box), 11 to
13 channels each, 13 distinct channels across all six, against 73
`DataChannels` and 18 `DerivedChannels` declared. What reported:
`dist-010v`, `primary-010v`, `store-010v` (the 0-10V readbacks),
`dist-pump-pwr`, `primary-pump-pwr`, `store-pump-pwr`, `hp-idu-pwr`,
`hp-odu-pwr`, `oil-boiler-pwr`, `zone1-down-whitewire-pwr`,
`zone2-up-whitewire-pwr` (all eGauge), and `dist2-flow` / `dist2-flow-hz`
once in the first report and never again. Values are plausible:
`hp-odu-pwr` steady at 22 W, `hp-idu-pwr` 12-14 W, every pump 0 or 1 W,
`dist-010v` 35, `primary-010v` 62, `store-010v` 65.

Everything else is absent — every tank and buffer thermistor channel
(`*-device`, `*-micro-v` and the derived depths for buffer and tanks 1-3),
every flow and BTU channel (`dist-flow`, `primary-flow`, `store-flow`,
`sieg-flow`, `store-flow-hz`, `sieg-flow-hz`, `sieg-send-flow`), the
water temperatures (`hp-ewt`, `hp-lwt`, `buffer-hot-pipe`, `buffer-well`,
`store-hot-pipe`, `store-cold-pipe`, `sieg-cold`), both zones'
temperature and setpoint and heat-call channels (`zone1-down-temp`,
`zone1-down-gw-temp`, `zone1-down-set`, `zone1-down-heat-call` and the
zone2 equivalents), the ten relay-state channels, and
`required-energy` / `usable-energy` / `transactive-power`. The thermistor
and flow absences are (i); the zone-temperature absence is the same
0/2 line.

### Not run

The beech BufferOnly / TOU actuating step did not run. It waits on (h)
and on the beech pico ingestion question in (i).

## Timeline

Laptop clock, ET. The box clocks run about 70 s behind it (measured
19:36:14 laptop against 19:35:03 spruce), so a box stamp of 19:09:14
is 19:10:2x on the laptop.

- 19:10:07 — `mosquitto_sub` against the dev broker refused on
  credentials. No broker-side capture exists for this run.
- 19:10:12 — `./beech_window.sh on 30`. Layout pair matched the gen
  output, tunnel up, `gwspaceheat` and its restart timer stopped.
- 19:10:2x (box 19:09:14) — beech window scada boots, Standby control,
  key relays energized, sieg loop starts a 110 s send move.
- 19:11:38 — `./spruce_window.sh on 30`. Layout pair matched, winter
  hack and `gwspaceheat` and its restart timer stopped.
- 19:11:4x (box 19:10:39) — spruce window scada boots, Nolan control,
  nothing commanded.
- 19:12:1x (box 19:11:04) — beech sieg move ends in `SteadyBlend`.
- 19:12:2x (box 19:11:09) — spruce TOU-cooling logic takes zones 1, 2
  and 4 off their thermostats and turns the heat pump off; at box
  19:11:24 it opens the secondary pump relay.
- 19:14:1x (box 19:13:09) — spruce cycler names `floor1 pico_71156b`
  and starts rebooting the bank every ~65 s.
- 19:14:5x (box 19:13:44) — beech loses buffer and tanks 1-3.
- 19:16:1x (box 19:15:00) — spruce's only `report.event`.
- 19:17:2x - 19:19:5x (box) — the beech port-word sampler runs at 1 Hz.
- 19:21:01 — `./spruce_window.sh off`, closed early on the zone holds.
- 19:21:0x (box 19:19:57) — winter hack back; two seconds later all six
  zones released and the secondary pump off at `hp-odu` 0 W.
- 19:40:3x — the beech window reached its 30-minute bound and exited;
  the box restarted `gwspaceheat`.
- 19:41:06 — `./beech_window.sh off`; beech window log copied to
  `../scratch/`.

## Analysis notes

- **Clocks.** Every stamp inside a log or an event filename is the box
  clock; the timeline above is the laptop clock. Event filenames are UTC,
  log lines are box-local ET.
- **Krida reading key.** A PCF8575 read returns pin levels, so a LOW bit
  is an energized relay. Byte 0 is reversed (Relay1 = bit 7 down to
  Relay8 = bit 0); byte 1 runs Relay9 = bit 0 up to Relay14 = bit 5 and
  Relay15 = bit 6. The board record `KridaDoubleRelayBoard16` in the
  window layout is the source for that mapping; nothing here hardcodes it.
- **What the port samples cannot say.** They start at box 19:16:11 and
  run 150 s. The sieg move at box 19:09:14-19:11:04 is outside them, so
  the motor-powered word during the move is not witnessed on the bus;
  the log and the resting word after the move are the evidence for (g).
- **Spruce's gw108 bits were not sampled.** The secondary pump relay
  command at box 19:11:24 is in the log, but no bus-side read of the
  gw108 register was captured during the spruce window, so the bit
  transition itself is not in this folder.
- **The beech zombie problem event did not persist.** The log line at
  box 19:14:58 says the cycler sent a problem event for `pico_4e6e35`,
  but beech's window event dir holds no `gridworks.event.problem` file.
  Only the seven boot events and the six reports are there.
- **Relay channels are not readings.** Both houses' relay-state channels
  are absent from `ChannelReadingList` because the report carries relay
  state in `StateList` (spruce's report carries 36 `machine.states`
  entries). Do not read those absences as missing data.
- **Counts.** "86 channels" for spruce is the `DataChannels` count; the
  layout also declares 25 `DerivedChannels`, so 111 names in total
  against 71 reported.
- **No report is a fleet record.** Neither window's events reached the
  journal DB or S3 — the upstream link never found a peer. These files
  exist only on the boxes and in this folder.

## Folder contents & experimental method

All data here was GENERATED by this experiment. Nothing came from the
journal DB or the S3 eventstore: the windows ran with their upstream
link pointed at a dev broker with no consumer on it, so the reports and
events never left the boxes. A re-run produces a new dataset; none of
this regenerates. The experiment did touch the running system — on each
box the deployed plant services (and on spruce the winter hack) were
stopped for the window and restarted by the box afterwards.

- `spruce-window-20260918-192107.log` — the spruce window scada's stdout,
  copied off the box by `house_window.sh spruce off`. Provenance in
  `spruce-window-20260918-192107.provenance.txt`. EXTERNAL EVIDENCE.
- `beech-window-20260918-194106.log` — the same for beech, with
  `beech-window-20260918-194106.provenance.txt`. EXTERNAL EVIDENCE.
- `beech-port-samples.txt` — the Krida port word at 0x20 read off the bus
  once a second from box 19:16:11 to 19:18:46, with
  `beech-port-samples.provenance.txt`. EXTERNAL EVIDENCE.
- `spruce-on.log`, `beech-on.log` — the console record of each
  `./<house>_window.sh on 30`, carrying the layout sha256 prefixes the
  gate checked and the services it stopped. Provenance sidecars beside
  each. EXTERNAL EVIDENCE.
- `broker-capture-failed.log` — the one-line refusal from the laptop
  `mosquitto_sub`, kept as the evidence that no broker-side capture of
  this run exists. EXTERNAL EVIDENCE.
- `instances/` — the window-born event files from each box's
  `~/.local/share/gridworks/scada-experiment/event/`, copied untouched
  and renamed to the dash-separated convention
  `<house>-<HHMMSSmmm UTC>[-<subject>]-<type.name>-<version>.json`; plus
  the two `gw.experiment.run` instances.
- `runbook.md` — the commands that ran, re-runnable.
- `emit_instances.py` — builds `instances/<house>-gw.experiment.run-000.json`
  from the first and last stamped line of each window log, through the
  gwexp snapshot class, reading the written file back through the codec.

Regenerate the instances from the logs already here:

    cd ~/GridWorks/experiments/2026-09-18-correct-house0-windows
    uv run python emit_instances.py

Read a committed instance back through the snapshot codec:

    cd ~/GridWorks/experiments/2026-09-18-correct-house0-windows
    uv run python -c "from gwexp.sema.codec import default_codec; from pathlib import Path; print(default_codec.from_bytes(Path('instances/beech-gw.experiment.run-000.json').read_bytes()))"

Re-running the windows themselves (this stops each house's plant
services for the duration) is in `runbook.md`.

No `gw.readings` instance lives here, so there is no display CSV.
