# sim-boot through from_word — real-broker verification

Status: Draft · Pass 0 · Updated 2026-08-15

> What this is: the dev-broker boot that verifies the word-native
> `HydronicLayout.from_word` and the sim-component-in-layout-union change,
> end to end. Reproducer: `gw_spaceheat/sim_boot.py` (bounded ScadaApp boot).
> Code under test: gridworks-scada working tree (from_word + semafy + sim
> unions); sema `jm/sim-in-layout-unions`.

## Why

Two changes needed real-broker confidence, not just the in-process suite:
1. `HydronicLayout` was rebuilt to hold its sema word and construct via
   `from_word` (no dict round-trip). The hub's EDD bar is a bench/box/dev-broker
   boot, not pytest.
2. `sim.sensor.component.gt` / `sim.relay.component.gt` were added to both
   layout words' Component unions so a simulated layout is *simulated by
   construction* (design direction: remove `is_simulated`, derive it).

## Setup

`gw-dev-rabbit` up (MQTT 1885, TLS off). `sim_boot.py` loads the nolan
authored pair, runs `simulate_sensors` (pico-fed sensor nodes → `SimSensorActor`
+ `sim.sensor.component.gt`, aliases dev-ified to `d1`), decodes through
`gw.nolan.layout`, loads via `from_word`, and boots a standalone `ScadaApp`
(no LTN parent → LocalControl) bounded to 8s. `is_simulated=True` is still set
transitionally for the relay/bus side (no `SimRelayActor` yet).

    cd gw_spaceheat && ./venv/bin/python sim_boot.py

## Found — PASS (2026-08-15)

    == boot gw.nolan.layout.json for 8s on gw-dev-rabbit (simulated) ==
      layout: 60 nodes
      latest_channel_values: 59 channels, 35 non-null
      BOOT OK

- `from_word` built the runtime layout and the whole actor tree instantiated
  (LocalControl → NolanLocalControl; i2c bus/relays, gw108 thermistor reader,
  gpio opto sensors, DAC writer, pico-cycler).
- 3 pico-fed sensors decoded as `sim.sensor.component.gt` and self-generated
  (zone temps ~12362, microvolts 200000); relays logged "Simulated relay
  actuation; skipping GPIO".
- derived-generator pulled a real weather forecast and computed usable/required
  energy.

## Scope of the claim

Verified on a real broker: from_word boots a real scada end to end, and a
sim-sensor-swapped layout decodes through the widened union and self-generates.
NOT verified: sim actuation (no `SimRelayActor` yet — relays ride the
transitional `is_simulated` no-op), and the House0 pair (conftest/sim_boot
default is the Nolan pair; House0 boot is the "Test House0" queue item).
