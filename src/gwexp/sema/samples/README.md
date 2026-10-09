# Samples

Canonical JSON instances, one per seeded **type** version that carries
an `examples:` block. Generated from the authored examples (never edited
by hand) and consumed by `roundtrip.py`. A type version without a sample
is silently untested by the round-trip, so its absence is recorded here.

Coverage: **59 of 72** seeded type versions have a sample.

Seeded type versions lacking a sample (no `examples:`):

- `fsm.full.report.001`
- `glitch.000`
- `gw.alert.000`
- `gw.experiment.run.001`
- `gw.opsgenie.alert.000`
- `gw.readings.000`
- `ha1.params.006`
- `heating.forecast.000`
- `layout.lite.013`
- `machine.states.000`
- `single.reading.000`
- `spaceheat.telemetry.quantity.projection.000`
- `synth.channel.gt.000`
