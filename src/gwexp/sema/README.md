# Sema vocabulary snapshot (GENERATED)

## ⚠ STAGING SNAPSHOT — PLEASE ONLY USE IN DEV

This snapshot contains STAGING vocabulary: mutable words that run on dev
brokers only. It MUST NOT be used against hybrid or production brokers.

Staging words in this snapshot:

- enum gpio.sense.mode:000
- enum gw.dashboard.role:000
- enum gw.dispatch.refusal.reason:000
- enum gw.experiment.verdict:000
- enum gw.primary.flow.source:000
- enum gw.primary.pump.owner:000
- enum gw.refrigerant.cycle:000
- enum gw.standby.posture:000
- enum gw.top.state:000
- enum gw.zone.emitter.type:000
- enum gw1.actor.class:014
- enum gw1.service.mode:000
- enum gw2.lc.top.state:000
- enum i2c.adc.channel
- enum i2c.adc.type:000
- enum i2c.dac.channel:000
- enum i2c.dac.type:000
- enum i2c.expander.type:000
- enum i2c.mux.type:000
- enum ta.validation.state:000
- enum thermostat.kind:000
- enum zone.setpoint.source:000
- type ads111x.based.device.type.gt:000
- type dac.output.config:000
- type data.channel.gt:004
- type derived.channel.gt:003
- type device.component.gt:000
- type egauge.register.config:000
- type electric.meter.channel.config:000
- type electric.meter.component.gt:001
- type electric.meter.device.type.gt:000
- type gpio.relay.component.gt:000
- type gpio.sensor.component.gt:000
- type gw.adc.waveform:000
- type gw.boiler.backup:000
- type gw.element.backup:000
- type gw.experiment.run:001
- type gw.house.operating.status:000
- type gw.house.summary:000
- type gw.hydronic:000
- type gw.native.gpio.pin:000
- type gw.nolan.layout:000
- type gw.readings:001
- type gw.water.store:000
- type gw1.hvac.zone:000
- type gw1.scada.device.type.gt:000
- type gw1.tank.temp.calibration.map:001
- type gw1.tank.temp.calibration:001
- type gw1.unit.quantity.projection:001
- type gw1.zone.call.circuit:000
- type gw1.zone.thermostat:000
- type hp.control.box.device.type.gt:000
- type hp.device.type.gt:000
- type i2c.bus:000
- type i2c.ct.interface.capability:000
- type i2c.dac.capability:000
- type i2c.dac.output.component.gt:000
- type i2c.expander:000
- type i2c.multichannel.dt.relay.component.gt:004
- type i2c.mux:000
- type i2c.relay.capability:000
- type i2c.relay.component.gt:000
- type i2c.thermistor.channel.config:000
- type i2c.thermistor.interface.capability:000
- type i2c.thermistor.reader.component.gt:000
- type layout.lite:013
- type pico.btu.meter.component.gt:000
- type pico.flow.module.component.gt:001
- type pico.tank.module.component.gt:012
- type relay.actor.config:003
- type relay.control.config:000
- type scada.board.component.gt:000
- type sim.pico.btu.meter.component.gt:000
- type sim.pico.flow.module.component.gt:000
- type sim.pico.tank.module.component.gt:001
- type sim.sensor.component.gt:000
- type spaceheat.node.gt:303
- type spaceheat.telemetry.quantity.projection:001
- type web.server.component.gt:001

When these words promote to published, rebuild without `--allow-staged` to
get a publication-grade snapshot (and this section disappears).

This directory is a **vendored Sema snapshot**: a self-contained, generated
subset of the Sema vocabulary. **Never hand-edit it.** To change it, edit the
seed (`../sema_seed_request.yaml`) or the definitions in the sema repo, then
re-run the repo's `scripts/regen_sema_snapshot.sh`.

## What Sema is

Sema is a vocabulary registry for structured messages exchanged between
independent systems. It defines versioned types, enums, and formats
expressed as JSON Schema; these act as boundary contracts, making the
structure and semantics of serialized messages explicit and mechanically
verifiable. Sema applies only at system boundaries — it governs the JSON
exchanged between applications, not runtime architecture, database design,
or internal object models. Every schema `$id` lives under the
`https://schemas.electricity.works` namespace; the canonical registry and
spec live in the sema repo (https://github.com/thegridelectric/sema — start
at `spec/primary.md`).

## Working with Sema-typed data (rules that fight default idiom)

- Construct and decode instances through the generated classes in this
  snapshot — never hand-built dicts.
- Dict/JSON keys are the PascalCase wire form; produce and consume them via
  `to_dict()` / `from_dict()`, never by spelling keys inline.
- Dispatch on decoded messages with `isinstance`, never `hasattr`.
- Narrow every codec decode (`expect=` or `assert isinstance`).
- Where a value is vocabulary-shaped, use its property format type, never
  bare `str`.
