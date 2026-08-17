# Experiments logbook

Chronological index of GridWorks real-condition experiments — one line
per run, newest first. The CANONICAL record of each experiment (why,
setup, findings, data manifest, code-under-test commit) is the README in
its `<date>-<slug>/` folder; this file only orders and points.

Genres share the one namespace, marked in the slug tail: unmarked =
designed experiment (Why / Setup / Found / data manifest);
`-analysis` = observational study; `-postmortem` = incident
investigation (impact, timeline, contributing causes, action items —
leading with what went well). Queued experiments live in
`future/<slug>/` and sit at the top here as **queued** until their
first run dates them.

- **queued · [pico-rejoin](future/pico-rejoin/)** — trace
  `wlan.status()` timing across power cycles. Why the spruce
  secondary pico's stereotyped 13–14 min post-shake silence — deployed
  firmware has no retry (one connect, wait forever), so the schedule
  lives in the driver/DHCP/router stack; baseline at home, then the
  sick pico onsite.
- **2026-08-16 · [spruce-store-charge-valve](2026-08-16-spruce-store-charge-valve/)**
  — does the gw108 charge valve open energized and fail CLOSED de-energized?
  Groundwork for tank1-as-cool-storage. First (starter-scripts) run
  INCONCLUSIVE: fell inside a 13-min secondary-btu pico dropout (tank1 zombied
  13:29:23 → VDC shake) and read a frozen snapshot 7.42 GPM through both legs —
  drove OPS-497 (snapshot conveys stale pico data as live). Driver rebuilt with
  a true-liveness gate (ScadaReadTimeUnixMs age) + retrospective gw.readings
  pull as the arbiter; definitive run PENDING a clean pico window.
- **2026-08-15 · [living-room-thermostat-deadband](2026-08-15-living-room-thermostat-deadband/)**
  — analysis: a week of the living-room air temp (zone2-living-rm-gw-temp)
  vs the zone-5 fan-coil call, via Thomas's falling-edge method. Deadband is
  too tight to resolve at the room sensor — per-cycle swing ~0.09F, the stat
  short-cycled ~every 32 min holding ~71.5F (tighter than Thomas's 2F
  assumption; ~1.5F warmer than our replacement's 70F target). It STOPPED
  2026-08-11 19:18 ET (a long final call, then dead ~92 h); the room reached
  76F, +4.4F past its call point, with no call — the failure George reported.
- **2026-08-15 · [spruce-fancoil-dist-test](2026-08-15-spruce-fancoil-dist-test/)**
  — incident probe: George's living-room (zone 5) fan-coil thermostat
  "wasn't working". Forced the zone-5 call at the scada relay (hack stopped,
  zone 3 held off, deployed scada left publishing). dist-flow jumped
  0.06 → 1.56 GPM within ~26 s and held — downstream (relay → Caleffi →
  valve → fan-coil) WORKS, so the fault is the wall thermostat / whitewire
  (matches the zone-5 opto reading idle). Open: dist-pump-pwr stayed ~0 W
  while flow rose — flow likely primary-loop-driven, or the pump is below
  the 5 W async threshold. Zones restored to thermostat, hack restarted.
- **2026-08-15 · [sim-boot-from-word](2026-08-15-sim-boot-from-word/)**
  — PASS: a real ScadaApp booted on gw-dev-rabbit through the new
  word-native `HydronicLayout.from_word` (nolan pair), with `simulate_sensors`
  swapping 3 pico sensors → SimSensorActor + `sim.sensor.component.gt`
  (simulated by construction, decoding through the layout word's newly-widened
  Component union). 60 nodes, 59 channels, 35 non-null; NolanLocalControl
  resolved, sim sensors self-generated, relays no-op'd. Verifies from_word +
  the sema sim-in-union change end to end on a real broker (the owed EDD boot).
- **2026-08-15 · [gwsproto-sema-layover](2026-08-15-gwsproto-sema-layover/)**
  — PASS: a fieldless, config-less `GwsprotoSemaType` base gives all 145
  gwsproto words `type_name_value()` with the discriminated union
  byte-identical and the suite green (193/1). Also pins WHY the sema
  runtime can't be adopted as-is: gwproto discovery keys on a field
  literally named `TypeName`, so sema's snake `type_name` + alias is
  invisible to it while still passing `sema validate`.
- **2026-08-12 · [dac-bus-bench](2026-08-12-dac-bus-bench/)** — the DAC
  leg's bench rung on honeysuckle (scada `e551c2e1`): mux select +
  Multi-Write + bare EEPROM read all through the I2cBus single owner on
  the real TCA9548A/MCP4728, zero write failures. Boot #1 converged the
  bench EEPROM to the layout PowerOn values but needed 3 heartbeat
  passes — the chip's ~50 ms EEPROM write cycle returns stale reads, so
  the immediate re-verify failed; boot #2 verified clean first-pass
  (Multi-Write provably EEPROM-free). PASS with finding; settle fix +
  sim busy model landed same day.
- **2026-08-12 · [spruce-witness-window](2026-08-12-spruce-witness-window/)**
  — first witnessed scada actuation on spruce (NolanLocalControl scripted
  witness, on-peak windows). #1 FAIL: a third ConfigList-walker bug spun
  the event loop (420k log lines, no snapshots, witness never ran); one
  generic shutdown event leaked to prod/S3 via a silently-discarded
  paths override — found, archived, deleted; no staging words escaped.
  #2 PASS after fixes: 6 pin-confirmed actuations, 0 glitches;
  dist response through the Caleffi box ≤29 s (off ~5 s);
  secondary-flow 7.46 GPM in seconds at the 65% EEPROM default
  (off ~4 s). Warm takeover witnessed ×2; holds never moved.
- **2026-08-11 · [gwwf-scheduler-witness](2026-08-11-gwwf-scheduler-witness/)**
  — OPS-436 build step 3 witness: the record-driven scheduler ran a
  full scenario on gw-dev-rabbit at second-scale record schedules (no
  time mocking) — observation slots, a silent slot, an interpolated
  replay, per-channel forecasts on a non-uniform slice grid, and a
  fidelity-downgrade glitch, all decoded via the snapshot. PASS.
- **2026-08-11 · [nws-updatetime-probe](2026-08-11-nws-updatetime-probe/)**
  — RUNNING: 5-min poll of the CAR/60,114 hourly product's stamps for
  a day or two, quantifying `updateTime` freshness at :30 (the gwwf
  forecast broadcast phase, OPS-436). First poll already showed
  `updateTime` ~7 h behind a fresh-looking `generatedAt`.
- **2026-08-11 · [gwwf-obs-roundtrip](2026-08-11-gwwf-obs-roundtrip/)**
  — OPS-436 build step 1 witness: gwwf's publish path broadcast one
  `gw.weather.observation` on gw-dev-rabbit with radio channel =
  location alias; a slug-only tap received it and decoded byte-equal
  through the vendored staging snapshot. PASS. Pinned: the
  radio-channel tail keeps its dots (per-segment wildcards work).
  Bonus: boot validation rejects pre-0.5.x all-zeros dev GNodeIds.
- **2026-08-10 · [hp-snafu-and-pico-blackout-postmortem](2026-08-10-hp-snafu-and-pico-blackout-postmortem/)**
  — all six layout picos flatlined ~17:04 ET and stayed zombie; root
  cause pinned to the GridWorks SSID's 2.4 GHz radio going off the air
  (the pi's own wlan0 lost the same network at 17:04:29; router still
  wired-reachable and beaconing 5 GHz; every wired channel healthy).
  5 VDC bus exonerated for this incident, its shared-rail coupling to
  the board's sick corner documented from the RevC schematic. Second
  thread OPEN: the Samsung ignored a readback-verified 20:00 cool call
  — ODU rose to normal standby on its own schedule 19:58–21:30, no
  pump, no compressor, the 07-29 soft-off shape. Recovery pending: a
  router power-cycle (owner call or site visit).
- **2026-08-10 · [ads-declared-rate](2026-08-10-ads-declared-rate/)**
  — the unlimbo scada's reader→bus path at the LAYOUT-DECLARED ADS
  rate. Bench rung (08-10), both pairings PASS: gated reads 137 ms at
  8 SPS vs 75 ms at 16 SPS with the readback gate green throughout
  (the declared rate demonstrably reaches silicon), bus-path overhead
  ~12–13 ms — the 16 SPS @ 2 Hz fallback exactly at the sweep axiom's
  proposed 0.6 bound. Spruce window (08-11), PASS: real thermistors on
  the box, zero i2c errors, zero readback mismatches, all four zones
  publishing real temperatures, noise floors in the 8 SPS band
  (garage modestly above). The pre-promote gate for the hardware
  words is met. Window catches: unlimbo LocalControl's ScadaBlind
  path crashes on the Nolan layout (hard-coded House0
  store-pump-failsafe node), and the experiment env shared the
  deployed scada's event persister (archived + cleaned; future
  windows use their own paths name).
- **2026-08-06 · [ads-noise](2026-08-06-ads-noise/)** — re-run,
  two windows. Run 1 invalidated: the gwspaceheat-restart watchdog
  fired 35 s into the window and restarted the scada under the
  harness — the two-masters-on-one-ADS signature (mux-swapped
  readbacks, paired ±100–150 mV cross-channel spikes, reads stretched
  4× by contention) is kept as a reference. Run 2 (watchdog stopped,
  pi-side failsafe): 0 errors, no spikes — **board healthy**; elevated
  sd vs 07-30 is real air movement (EMA output sd ≈ raw sd), zone3
  reads its fan-coil neighbor (heat-call archive corroborates: the
  window fell in the zone3 off-phase and its mean rose 0.25 °C — the
  post-call recovery ramp). Verdict revised: **8 SPS at 1 Hz is the
  choice** — ~40 % quieter electrically AND catches real drift;
  gated-read cost 16 ms ⇒ ~16 Hz 4-ch ceiling at 128 SPS. Archive canary
  (zone*-gw-microvolts): first spikes 07-26, three days pre-incident —
  canary datasets picked: 07-22 clean · 07-26 evening · run 2. Harness
  de-hacked: board facts from the box's layout (5k6 per the Gw108
  schematic, not the hardcoded 5.65), provenance in results. Folder
  carries the 07-30 first run's record too.
- **2026-08-05 · [registry-projection-rig](2026-08-05-registry-projection-rig/)**
  — OPS-443's dev-universe experiment, all four legs PASS: gjk bootstrap
  via the read API (28/28 nodes), MarketMaker re-parent → projection
  re-alias + full ear slice capture (cmd/ack/forest, SendTimeMs →
  created_at), snapshot heals a corrupted row. Edge projection not
  wire-exercised (no seeded edge).
- **2026-08-05 · [pico-link-census](2026-08-05-pico-link-census/)** —
  analysis, NEGATIVE result: MAC OUI cannot discriminate wired vs wifi
  picos (ethernet firmware sets no WIZnet MAC). Ground truth is each
  pico's comms_config.json; right fix is firmware self-report.
- **2026-08-03 · [pico-gap-analysis](2026-08-03-pico-gap-analysis/)** —
  gaps + glitches + their Venn, 56 d: fir/oak/maple tied clean (router
  pick free to rest on other criteria); spruce's "flaky pico" is a
  FEEDBACK LOOP (permanent zombie → half-hourly VDC shakes → one
  slow-rejoining pico logs a dropout each shake); beech has an
  unexplained HOURLY disturbance. 08-10 semafied re-run CONFIRMED the
  loop via the floor2-removal discriminator: spruce gaps 104 → 17/day,
  secondary-BTU pico 21.4 → 3.7/day per channel, ~30 min spacing
  signature gone; residual is the pico's own slow rejoins (pico-rejoin
  thread). 08-15 wifi-herd-reduction re-run CONFIRMED the residual was
  congestion too: after removing 3 more wifi picos (fancoil/pipes1/
  floor1, 08-10 deploy), secondary-BTU gaps 14.0 → 2.25/day, mean gap
  duration ~halved, the 165-min outlier gone.
- **2026-07-30 · [spruce-no-cool-postmortem](2026-07-30-spruce-no-cool-postmortem/)**
  — heat pump soft-OFF overnight + two gw108 chip failures (0x21
  expander per-start brownouts; dac3 i2c death).
- **2026-06-12 · [sim-plant-flux](2026-06-12-sim-plant-flux/)** — PASS:
  SimulatedPlant emits flux async-gated (30 of 200 ticks), matching a
  reference filter.
- **2026-06-11 · [sim-time-bridge](2026-06-11-sim-time-bridge/)** —
  VERIFIED (scoped): sim.timestep crosses AMQP→MQTT to scada-side
  listeners.
- **2026-06-11 · [sim-sensor](2026-06-11-sim-sensor/)** — PASS: generic
  SimSensor publishes 20/20 expected channels, witnessed on a broker.
- **2026-06-11 · [stale-layout-migration](2026-06-11-stale-layout-migration/)**
  — accidental sema teaching story: sema-typed migration = lookup;
  dangling names = archaeology.
