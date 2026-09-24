# beta-field-windows

> Only the **last run** is kept. Opening a new window **deletes the previous
> run's artifacts first** (logs, captures, pulled instances) — git history and
> the logbook carry what a past round taught, so nothing durable is lost.
> `emit_instances.py` is the only code that persists between runs.

The how-to for running a window — the two window kinds, the box layouts, the
`put_layout.sh` gate, the tunnel, running a round, and the On Tap list — is
`../field-window-recipe.md`. This folder is just the tool and the last run.

## Last run — round four (2026-09-23)

Two 5-minute windows on scada `847d9ca9` (`jm/spruce-unlimbo`), the first
run of the window pairs generated at the layout-word axiom tables
(`gw.nolan.layout` for spruce, `gw.house0.layout` for beech, both with
`DisabledChannelNames`); no `--debug`, no LTN; one broker capture (34
messages: spruce 10 snapshots, beech 10).

- **Both** booted on the new pairs and announced `layout.lite` then
  `ta.deed` once; snapshots every 30 s with every state machine present;
  both closed on their bound and the box restarted the recorded services.
- **beech** — every tank-module pico (`tank1`, `tank2`, `tank3`, `buffer`)
  posts `tank.module.params` `110` and the scada accepts only `200`
  (`PicoBoardVariant`, `MicropythonVersion` required): one
  `gridworks.event.problem` per pico per minute, 16 in the window; the
  readings still arrive. The two Hubitat zone channels never populated
  (`0/2 zone gw channels`; `zone1-down-temp`/`-set`, `zone2-up-temp`/`-set`
  had no value all window). The UnknownChannels logger lists the four
  declared-disabled channels (`dist-flow`, `dist-swt`, `dist-rwt`,
  `sieg-hot`) as having no value.
- **spruce** — `8/8 zone gw channels`; one Warning glitch
  (`fancoil` `open-thermistor`: `fancoil-depth3` at the 3.3 V rail); the
  Nolan LocalControl left actuators at their adopted states and turned the
  heat pump off; no problem events.
- **Both** — `store-hot-pipe` / `store-cold-pipe` (spruce: `store-btu`;
  beech: `analog-temp`) and beech `buffer-hot-pipe` / `buffer-well` never
  read a value in the window. Relay channels sit in the UnknownChannels
  list too, which is expected: relay state rides `StateList`, not a
  reading. Beech `ActuationAuthority` is `Standby`, spruce `Active`; both
  deeds on the boxes match the announced `ta.deed` (`…spruce.ta` issued
  2026-09-08, `…beech.ta` issued 2026-09-21, both
  `ValidatedRealAssetAndGps`).
- **Round-four checklist from the spoke** — spruce zones publish
  `-opto-input` and `-heat-call` in the first snapshot (19:43:42, ~80 s
  after boot); one pico-cycler reboot at startup and none after;
  `fancoil-depth3` gave one `open-thermistor` Warning and `pipes1-depth3`
  none; beech `zone1-down-heat-call` / `zone2-up-heat-call` carry 0 from
  the power meter; beech no longer lacks a deed; the beech tank picos do
  post params and the older-firmware `TankModuleParams` is refused.

Files: `broker-capture-20260923-194329.jsonl`, `spruce-window-…195122.log`,
`beech-window-…195134.log`, each with a provenance sidecar;
`instances/{beech,spruce}-gw.experiment.run-000.json`. Capture stamps are the
laptop clock, ~70 s ahead of the boxes.

## emit_instances.py

Builds `instances/<house>-gw.experiment.run-000.json` from the first and last
stamped line of each window log, constructing through the gwexp snapshot class
and reading the written file back through the codec. Regenerate the two instances from the logs in this folder:

    uv run python emit_instances.py

Read a committed instance back through the codec:

    uv run python -c "from gwexp.sema.codec import default_codec; from pathlib import Path; print(default_codec.from_bytes(Path('instances/beech-gw.experiment.run-000.json').read_bytes()))"
