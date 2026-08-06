# STAGING SNAPSHOT — PLEASE ONLY USE IN DEV

This snapshot contains STAGING vocabulary: mutable words that run on dev
brokers only. It MUST NOT be used against hybrid or production brokers.

Staging words in this snapshot:

- enum i2c.adc.channel
- type gw.channel.jump.stats:000
- type gw.experiment.run:000
- type i2c.thermistor.channel.config:001
- type i2c.thermistor.channel.config:002
- type i2c.thermistor.reader.component.gt:001
- type i2c.thermistor.reader.component.gt:002
- type i2c.thermistor.reader.component.gt:003

When these words promote to published, rebuild without `--allow-staged` to
get a publication-grade snapshot (and this file disappears).
