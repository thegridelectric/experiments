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
  thread).
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
