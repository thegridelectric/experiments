# nolan-local-control-windows, 2026-10-09

> What this is: the beta windows of the spruce-unlimbo scada on the dev
> broker after the weather-provisioning rebuild: Nolan local control on
> spruce, Standby House0 on beech; one run section per window, the
> verdicts under each Found, the index record is the logbook line.

## Run 1 — spruce, morning (10:49–11:04 ET)

### Why

OPS-392 (spruce-unlimbo) lists ten claims about Nolan local control
(`wiki/gridworks-scada/executor/local-control.md`) that no box had
witnessed: the tests are in-process or against the sim. Its weather step
(the scada fills from the weather service's seasonal template) closes
only when a window scada boots off the template. This window is that boot: scada `97ea5806` on
`jm/spruce-unlimbo`, the first run on a box of the sema weather path
(bundle record, seasonal template and forecast pulled from the gwwf
facade at first boot and kept in the config dir) and of proactor
`v4.1.13+jm3`.

### Setup

- Box: spruce, window checkout `~/gridworks-scada-unlimbo` at `97ea5806`,
  window venv with proactor `v4.1.13+jm3`; window pair in
  `~/.config/gridworks/scada-experiment/` from tlayouts `jm/spruce`
  `output/spruce/` (hardware layout `65d13487bd0e`, ops params
  `d24d0cfcf6e6`, the current ops word: BufferOnly 90–130 F,
  AcceptsDispatch, UsesBackupWhenCold false, WeatherBundleName).
- Env `~/envs/dev.env`: real spruce identity, upstream link to the
  laptop's gw-dev-rabbit over the `ssh -R 1885` tunnel, weather from the
  production facade over HTTPS (`weather_api_url`, the default).
- Weather service: gwwf main at `4079314` on the forecast box, the
  Millinocket seasonal template minted 12:55Z the same morning.
- Protocol: `experiments/field-window-recipe.md` "A round", a 15-minute
  experiment window (it displaces the winter hack, so short); the box
  stops `spruce-winter-hack`, `gwspaceheat` and its restart timer and
  restarts them when the window scada exits for any reason. No LTN on
  the laptop: events persist on the box and `off` copies them.

### Found

**PASS on the boot claims; the call, the band and the blind band were
not exercised** (the heat pump never ran, buffer-depth3 sat at about
91 F just above the 90 F floor, no on-peak edge fell in the window).
Per claim of OPS-392's field check:

| Claim | Verdict | Evidence (boot log line / capture msg) |
| --- | --- | --- |
| Boots with the call open | PASS | L554–571: five zones `SwitchToWallThermostat`, `CloseValve to charge-valve-relay`, `OpenRelay to store-pump-relay`, `TurnOff to hp-boss`, `[lc] Boot: Initializing -> HpCallOff`; last snapshot 11:04:30 still HpCallOff |
| Call follows schedule and band | NOT EXERCISED | no `HpCallOn`; depth3 ≈ 91 F all window |
| Pump follows the heat pump | PASS, off side | L920 `[hp-watch] Unknown -> HpDetectedOff`, then L921–922 secondary pump open, iso valve closed; hp-odu-pwr 12–16 W all window. FLAG: 150 ms earlier, with the watch still Unknown, L569–570 commanded `CloseRelay to secondary-pump-relay` / `OpenValve to iso-valve-relay`: the pump is briefly commanded on at boot. Intended for Unknown? |
| Blind band is a state | NOT EXERCISED | no `ScadaBlind`; buffer channels kept reporting |
| Operating status is quiet | PASS, startup half | one `gw.house.operating.status` (msg 7); no field changed |
| Elements never close | PASS on commands | 0 `CloseRelay` to an element relay; `OpenRelay` to both at L557–558. Caveat: warm takeover of expanders 0x20/0x21 (L550–551), and at 10:49:58 nine `i2c-relay-drift` Warnings, both element relays included: register held 1 where RelayOpen expects 0, re-asserted |
| Weather from the facade | PASS | three sema files written to `scada-experiment/` at 10:49 (`…-gw.weather.forecast.bundle.gt-000.json`, `…-gw.weather.seasonal.template.gt-000.json`, `…-gw.weather.forecast-000.json`, seen by `ls` during the window), L930 `Got a Live forecast starting 2026-10-09 11:00:00`, no `WeatherProvisioningError`; the source's own `Pulled` INFO line does not reach the window log (the step-4 logger gap) |
| Startup announcements | PASS | msgs 5–8 at 10:49:39: `layout.lite`, `ta.deed`, `gw.house.operating.status`, `gw.scada.commit` with `97ea58061dda…` |

**Reports.** Three `report.event` persisted on the box (none on the
dev broker, no LTN): slots 10:45–10:50 (74 channels; depth1 and depth3
absent, no value yet while the picos rebooted), 10:50–10:55 and
10:55–11:00 (101 channels each; depth1/2/3 and both hp power channels
present). The first carries every machine's state; the next two only
the machines that changed in their slot, so the Nolan call state and
the hp-watch state appear once. No 11:00–11:05 report: the window
ended at 11:04:23.

**Capture, 51 messages:** 30 `snapshot.spaceheat` (one per 30 s), 11
`glitch`, 4 `power.watts`, one each `gridworks.ping`,
`heating.forecast`, `layout.lite`, `ta.deed`,
`gw.house.operating.status`, `gw.scada.commit`.

**To take forward, each a candidate for OPS-392's review list:**

1. One **Critical** glitch `i2c-expander-reset` at 10:50:38 (msg 21):
   "0x21 config regs 0xff/0xff — pins floating (the OPS-452
   signature). Re-initializing". A Critical pages on-call; on the dev
   broker nothing paged. The expander re-initialized and the window
   ran on.
2. The pump briefly commanded on at boot while the hp watch is Unknown
   (table row 3).
3. `[UnknownChannels]` every 15 s: `required-energy` and the five
   `zoneN-*-set` channels had no value all window; `transactive-power`,
   `usable-energy` and the five heat-call channels flap stale about two
   minutes after each 300 s publish, which reads as a staleness
   threshold shorter than the publish period.
4. `[cold-watch] No recorded setpoint for bedrooms/living-rm/upstairs`
   every minute (42 lines), and `Could not find latest temperature`
   for the same three at boot.
5. Glitch msg 1 `disabled-roster`: `buffer-cold-pipe, dist-pump-pwr,
   fancoil-depth3-device, pipes1-depth3-device, primary-pump-pwr,
   store-cold-pipe, store-hot-pipe, store-pump-pwr`; the snapshot's
   `fancoil-depth3-micro-v` and `pipes1-depth3-micro-v` read the rail
   (3.3 V), so those thermistors look open.

No Traceback, ERROR or WARNING line in the boot log.

### Timeline

- 10:48:53 ET — `put_layout.sh spruce nolan-window`: ops params put
  (pre-copy `operational-params.2026-10-09-pre-nolan-window.json`),
  hardware layout already identical.
- 10:49:22 — `spruce_window.sh on 15`; capture
  `broker-capture-20261009-104926.jsonl` on the dev broker; tunnel up;
  box stopped `spruce-winter-hack gwspaceheat gwspaceheat-restart.timer`.
- 10:49:37 — window scada up; weather provisioned; Nolan HpCallOff.
- 10:49:45 — pico cycler reboots the picos (60 s).
- ~10:59 — gwalert (the old alerts) pages NoData for spruce: the journal
  has had no spruce reports since the deployed scada stopped at 10:49.
- 11:04:23 — last timestamped log line; `== window done: 8/8 zone gw
  channels populated ==`; the bound ends the window and the box restarts
  `spruce-winter-hack gwspaceheat gwspaceheat-restart.timer`.
- 11:05:01 — `spruce_window.sh off`: boot log and 10 persisted events
  (3 report.event) copied to scratch; `status`: all three services
  active, window scada down, relays iso=0 store=0 secondary=0.
- 11:05 — `house_window.sh capture off`: 51 messages.

### Analysis notes

The old alerts (gwalert, the `alerts` login) DID page on spruce NoData
at about 10:59 ET: the deployed scada was stopped for the window and
the window scada reports to the dev broker, so the journal went quiet
past gwalert's threshold. Self-resolving when the bound restarts the
deployed scada.

Reading key for the boot log: `[lc]` is the Nolan local control,
`[hp-watch]` the heat-pump watch, `[derived-generator]` the weather
consumer; stamps are the box clock in ET.

## Run 2 — spruce and beech, afternoon (15:29–15:59 ET)

### Why

Run 1 was entirely on-peak, so the call never opened. The band wanted
charge all day (depth1 about 132 F against the 90 F floor, depth3 about
91 F against 130 F), so an off-peak window before 16:00 exercises the
call, the hp watch's on side and the pump following it. Beech is the
first window of the same scada on a House0 Standby layout, on both
pis, after last week's pico work (dist tank module, dist hall flow,
the sieg tank module declared but disabled).

### Setup

Same scada `97ea5806` and window kit as run 1. Beech: window pair from
tlayouts `jm/spruce` `output/beech/` placed on beech and beech2 by
`put_layout.sh beech standby-cold-watch` (hardware layout `a6c29bbd87de`,
ops `0a211043ff0e`: Standby, posture NoHeatingOrCooling, energized
aquastat-ctrl and hp-failsafe, AcceptsDispatch false); both window
checkouts pulled to `97ea5806`; the box `~/experiments` clones pulled to
`1e5bd72` (the first beech `on` failed on a stale clone with no
`window_boot.py`, and `on` ended it on both pis). A 5 V pico bus census
on beech at 15:20 (scada stopped by the census script, restarted by it):
9 of 10 posted, only `pico_605430` (the disabled sieg module) silent.

### Found

**Spruce: PASS on the full call cycle** (`instances/gw.experiment.run-002.json`).
Off-peak with the band wanting charge, the window ran the call on and
off once, against OPS-392's field check:

| Claim | Verdict | Evidence (`evidence/run2/spruce-window-boot.log`) |
| --- | --- | --- |
| Boots with the call open | PASS | 15:29:25 `Boot: Initializing -> HpCallOff`, zones to thermostats, elements `OpenRelay`, hp-boss `TurnOff` |
| Call follows schedule and band | PASS, both edges | 15:30:25 `CallOn: HpCallOff -> HpCallOn` (off-peak, band wanting charge); 15:36:25 `buffer full: depth3 130.2 F; call held open`, `CallOff: HpCallOn -> HpCallOff`. The 120 s pre-peak edge (15:58) fell after the 15:54 bound: still open |
| Pump follows the heat pump | PASS, both sides | 15:30:57 `[hp-watch] HpDetectedOff -> HpDetectedOn`, secondary pump `CloseRelay` + iso valve `OpenValve` 3 ms later; 15:37:32 `HpDetectedOn -> HpDetectedOff`, pump `OpenRelay`, valve `CloseValve` |
| Every stop reaches HpDetectedOff | PASS | 67 s from the call closing to `HpDetectedOff` |
| Elements never close | PASS | no `CloseRelay` to an element relay |
| Weather from the facade | PASS | records already in `scada-experiment/`, read from disk, no `WeatherProvisioningError` |

To carry forward: expander 0x21 re-initialized twice (15:30:26, 0.5 s
after `CloseRelay to hp-scada-ops-relay`, and 15:38:27, 55 s after the
pump/valve change), each a Critical `i2c-expander-reset` glitch on the
capture plus nine `i2c-relay-drift` Warnings. With the morning's reset at
boot that is three resets in two windows, each near a relay transition
on 0x21. The `required-energy` and zone setpoint no-value lines and the
cold-watch setpoint misses continue as in run 1.

**Beech: PASS on the Standby boot, both pis**
(`instances/gw.experiment.run-003.json`, the full 20-minute run 2b;
run 2a was closed by hand at six minutes, my misread of the clock, and
its log is kept). `evidence/run2/beech-window-boot.log`: 15:38 `Set
auto.lc.standby command tree`, `Starting standby local control, posture
NoHeatingOrCooling`, `[sieg-loop] Running HoldFullSend` then `Moving to
full send`, `Standby posture set: 11 relays under auto.lc.standby,
energized ['aquastat-ctrl-relay', 'hp-failsafe-relay'], hp-boss told
TurnOff`. beech2's scada2 booted on the window pair and reuploaded its
events. No Traceback or ERROR on either pi. Four `report.event` on
beech, 52 snapshots on the capture.

To carry forward: four Warning glitches `<node> pico PicoBoardVariant
differs from the layout`, twice each (runs 2a and 2b): buffer, tank2
and tank3 post `PicoWiznetEth2040` and tank1 `PicoRaspberryWifi2040`,
while the layout says `PicoWiznetEth2350` for all four
(`tlayouts/beech_gen.py` TankSpec rows). A tlayouts fix. The sieg tank
module `pico_605430` is disabled in the layout and stayed silent in the
census.

**Capture, 166 messages** (`evidence/run2/capture.jsonl.gz`, both houses
on one dev-broker capture): spruce 50 snapshots, 17 power.watts, 12
glitches (2 Critical `i2c-expander-reset`, 9 `i2c-relay-drift`, 1
`disabled-roster`); beech 52 snapshots, 7 power.watts, 10 glitches (the
board-variant four twice, `disabled-roster` twice), the startup
announcements twice (runs 2a and 2b).

### Timeline

- 15:20 ET — beech pico census (`pico_cycle_census.sh 240`): 9 of 10
  posted.
- 15:29:22 — `spruce_window.sh on 25`; capture
  `broker-capture-20261009-152918.jsonl`; box stops the winter hack and
  gwspaceheat.
- 15:29:55 — `beech_window.sh on 20` refused on beech (stale
  `~/experiments` clone, no `window_boot.py`); ended on both; clones
  pulled on both pis.
- 15:30:25 — spruce CallOn; 15:30:57 HpDetectedOn.
- 15:31:04 — beech run 2a up on both pis.
- 15:36:25 — spruce buffer full, CallOff; 15:37:32 HpDetectedOff.
- 15:37:14 — beech run 2a closed by hand (early); 15:37:54 run 2b up on
  both pis.
- 15:54:22 — spruce bound; box restarts the winter hack and gwspaceheat.
- 15:58 — beech bound; both pis restart their scadas.
- 15:59:21 / 15:59:40 — `spruce_window.sh off`, `beech_window.sh off`:
  logs and events copied (spruce 12 events, 5 report.event; beech 18
  events, 4 report.event); `capture off`: 166 messages.

## Folder contents & experimental method

All data here was GENERATED by this window: the box's boot log and its
persisted events (copied by `off`), and the laptop's broker capture of
the dev broker; none of it is in a store, a re-run makes a new dataset.
The window stopped the deployed plant control on spruce for its length.

- `README.md` — this record.
- `runbook.sh` — the commands as run, in order.
- `evidence/spruce-window-boot.log` — the window scada's boot log, as
  `off` copied it (provenance header at the top). EXTERNAL EVIDENCE.
- `evidence/capture.jsonl` — the dev-broker capture for the window.
  EXTERNAL EVIDENCE.
- `evidence/events/` — the events the window scada persisted on the box
  (10 files, 3 `report.event`), as `off` pulled them. EXTERNAL EVIDENCE.
- `evidence/run2/` — the afternoon run: `spruce-window-boot.log`,
  `beech-window-boot.log`, `beech2-window-boot.log`,
  `beech-window-boot-2a-early-close.log`, `capture.jsonl.gz` (both
  houses; gzipped with the bytes intact, since the plain file is over
  the 2 MB cap), `events-spruce/`, `events-beech/`, `events-beech-2a/`.
  EXTERNAL EVIDENCE.
- `evidence/PROVENANCE.md` — where each evidence file came from.
- `instances/gw.experiment.run-00N.json` — one run per window (Verdict,
  and the executor Claim it stamps), emitted by `emit_instances.py` from
  each boot log's first and last stamps: 001 spruce morning, 002 spruce
  afternoon, 003 beech.
- `views.py` — the display CSVs below, decoded through the codec.

Regenerate the instances from the evidence (the evidence itself cannot
be regenerated; a new window makes a new dataset):

    uv run python emit_instances.py

The three windows, one row per `gw.experiment.run` instance, with ET
bounds, length, verdict and claim (`runs-display.csv`):

    uv run python views.py runs

Every glitch the window scadas published, from both captures, in time
order (`glitches-display.csv`):

    uv run python views.py glitches
