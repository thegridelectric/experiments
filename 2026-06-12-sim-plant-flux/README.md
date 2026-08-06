# 2026-06-12 — SimulatedPlant async-capture flux trigger · PASS

**Why:** the gwta plant's first piece — prove a `SimulatedPlant` emits
`sim.plant.flux` **only on async change** (the `AsyncCaptureDelta` semantics), not
every tick, before wiring the real broker + scada actors.

**Found (PASS):** a `SimulatedPlant` with a deliberately strange 1-channel
tank-temp inner model, stepped 200 ticks against a hard-coded async delta
(500 = 0.5 °C): emitted flux **30 times**, every emit ≥ delta from the prior,
async-gated (30 ≪ 200), matching an independent reference async filter, flux shape
correct (both timestamps). In-process, **no `sema/` edits, no broker** — the
`emit_cb` is the rabbit-publish seam.

**Not yet:** real broker publish (mosquitto, like `sim_sensor_experiment`); the
hard-coded async delta → bind to `ChannelConfig.AsyncCaptureDelta` from the
Component `ConfigList` when wired into a layout (TODO in the file,
`channel_config_base.py:14` / sema `channel.config/000`).

**Reproducer:** `sim-time-experiment/simulated_plant.py` (self-verifying PASS);
result in `sim_plant_out/result.json`.
