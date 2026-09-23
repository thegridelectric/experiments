# Spot-check recipe

A **spot-check** answers a quick question about a house straight from the
journal DB — "did the sieg loop go to full send every time the heat pump
turned on last night?" — and reports the answer back to the person who asked.

**A spot-check leaves nothing in this repo.** No dated folder, no `gw.readings`
instance, no logbook line, no changelog. That is the line between a spot-check
and an experiment: an experiment is a re-runnable reproducer that backs a
Verified claim and archives its evidence (see `README.md`); a spot-check is a
throwaway look whose only output is the report to the human. The two durable
artifacts are this file and `spot_check.py`; individual runs print to the
terminal and stop there. A one-off analysis worth keeping is the signal that
the question was really an experiment — promote it to a folder instead.

## The three things every spot-check assembles

1. **House → scada alias.** The fleet has no single canonical lookup for this:
   the authority is the per-house `tlayouts/<house>_gen.py` (each declares its
   own GNode aliases). `spot_check.py`'s `KNOWN_HOUSES` is the consolidated
   convenience and the source of truth for the table below — `spot_check.py
   --list-houses` prints the live map, and both regenerate from
   `grep -rhoE '"(hw1|d1)\.[a-z0-9.]+\.scada"' tlayouts/*_gen.py` when tlayouts
   gains a house. Segment 0 is the universe (`hw1` production, `d1` dev/sim).
   Pass `--scada <alias>` for anything unlisted. Presence in the map does not
   mean the box is currently emitting — a silent box just yields zero reports.

   | nickname | scada alias |
   |---|---|
   | `maple` `oak` `spruce` `beech` `elm` `fir` | `hw1.isone.me.versant.keene.<h>.scada` |
   | `spruce-sim` | `d1.isone.me.versant.keene.spruce.scada` |
   | `honeysuckle` | `d1.bench.honeysuckle.scada` |
   | `orange1` `willow1` | `d1.isone.ct.newhaven.<h>.scada` |

2. **The window**, in ET.

3. **One query on `report.event`.** This is the key fact that saves a
   rediscovery: a scada's `report.event` payload carries *both*
   `Report.StateList` (every state machine — sieg control, HP boss, each relay)
   and `Report.ChannelReadingList` (every numeric channel — flows, powers,
   temps). The state machines are **not** a journaled message type of their own,
   so `pull_readings.py` (which reads only `gridworks.readings`) cannot see
   them. `spot_check.py` reads `report.event` and exposes both.

## The tool

```
# what states and channels exist in the window:
uv run python spot_check.py --house maple --start '2026-09-21 18:00' --end '2026-09-22 08:00'

# state-machine transitions (collapsed to change-points):
uv run python spot_check.py --house maple --start ... --end ... \
    --states gw1.sieg.control.state gw1.hp.boss.state

# numeric channel summaries (--raw for every sample):
uv run python spot_check.py --house maple --start ... --end ... \
    --channels sieg-send hp-odu-pwr --raw
```

`spot_check.py` prints **raw wire-encoded** values. When you need calibrated
°F / gpm, `pull_readings.py` applies natural-unit conversion (it writes a
`gw.readings` instance + display CSV — for a spot-check, point its `--out` at a
scratch dir so nothing lands in the repo).

## Worked example — maple sieg → full send (2026-09-22)

Question: did the sieg loop reach full send on every HP-on last night?
Standard: control state reaches a send state (`Blind` / `HpHasLift`) **and**
`sieg-send` flow rises. Method: `--states gw1.hp.boss.state
gw1.sieg.control.state` for the HP-on edges and the sieg path, plus
`--channels sieg-send hp-odu-pwr` for the physical confirmation. Result: all
five HP-on events reached full send, every one via `Blind` (never the designed
`HpHasLift`). The answer went to the human; nothing was written here.
