# gw108-relay-stress, 2026-08-23 onward

> What this is: the one harness and every run of it, asking whether
> switching a relay on the gw108's 0x21 expander resets the chip, under
> what coil posture, and whether the cause is the board or what hangs on
> its contacts. Each run has a dated subfolder with its own README
> (Why, Setup, Found, Timeline); the logbook line per run is the index
> record. The harness stays at the top so every run is the same
> reproducer.

## The harness

`relay_stress.py` runs ON a box from its `~/experiments` clone at a
pushed SHA and needs only smbus2. Knobs are env vars on the launch line
(`TARGET`, `PERIODS`, `LOADS`, `TOGGLES`, `MAX_RESETS`, the three
`*_POSTURE` coils); every run is named (`--run <label>`) and writes
`relay-stress-<label>.log` + `-results.json` to `/home/pi/relay-stress-runs/`,
which the run's README copies into its subfolder and removes from the
box. The harness is the single writer on 0x21 for its window: on a
deployed box the services that own the expander stop first. Register
and bit map are the harness's own constants, the same on every gw108.

## Runs

| subfolder | box | board | B (iso, no other coil) | guards (two+ coils on) |
| --- | --- | --- | --- | --- |
| `2026-08-23-spruce/` | spruce | original | 35 / 100, at energize | 0 / 90 |
| `2026-09-08-spruce-board2/` | spruce | replaced 2026-09-08 | 17 / 100, at de-energize | 0 / 60 |
| `2026-09-08-honeysuckle/` | honeysuckle (bench) | bench, nothing on the contacts | 0 / 100 | 0 / 60 |

Standing rule from run 1, held by run 2: never switch the iso relay
with fewer than two other 0x21 coils energized. Run 3 places the cause
on the house side of the contacts, not the board.
