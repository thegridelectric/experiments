# oak-starts-heating, 2026-10-17

> What this is: three screenshots of the dashboard's real-time view of
> oak on the morning it started heating, kept for one question: does
> the view draw the flow at the buffer the right way round when the
> primary pump runs slower than the distribution pump? The logbook entry
> is the index record.

## Why

Oak started heating on 2026-10-17 with its upstairs zone 8 to 9 F under
its 64 F setpoint. The real-time view is what a person reads to see
which way water moves through the buffer, so a wrong arrow there leads
straight to a wrong reading of the plant.

## Setup

Nothing was run. The screenshots were taken from the dashboard's
real-time view of oak while the house heated, between the 10:20 and the
11:00 ET snapshots. No service was touched.

## Found

- **The buffer-bottom arrow points the wrong way.** At 10:20 the primary
  pump read 4.3 gpm and the distribution pump 4.6 gpm. With distribution
  faster than primary, the extra distribution water returns into the
  buffer bottom; the animation showed water flowing out of it. The
  annotation on `real-time.oak.2026-10-17.10_20_00.png` marks both
  buffer-side arrows as wrong.
- **At 11:00 the distribution pump ran at 6.4 gpm** against 4.2 gpm
  primary (`faster-distribution.png`), and the house drop had grown from
  6.0 F to 12.2 F.

No bar was set, so there is no PASS or FAIL.

## Timeline

All ET, 2026-10-17.

- 10:20 snapshot: heat pump 9.67 kW, lift 34.3 F; primary 4.3 gpm,
  distribution 4.6 gpm; buffer 92.4 / 75.4 / 77.1 F top to bottom;
  zone4-upstairs 56 F calling (`real-time.oak.2026-10-17.10_20_00.png`,
  annotated).
- Snapshot time not shown: primary 4.1 gpm, distribution 4.6 gpm;
  zone4-upstairs 57 F (`flow-confusion.png`).
- 11:00 snapshot: heat pump 9.93 kW; primary 4.2 gpm, distribution
  6.4 gpm; buffer 113.3 / 105.5 / 109.1 F; zone4-upstairs 58 F
  (`faster-distribution.png`).

## Analysis notes

- The screenshots show the view as drawn, which is the point. Read the
  readings from the journal for any number that matters.
- The time of `flow-confusion.png` is not on the image; its upstairs
  temperature puts it between the other two.

## Folder contents & experimental method

The screenshots are external evidence: images of the dashboard taken
by a person, in no store. The readings they show are the fleet's own
reporting and are in the journal DB, re-pullable by anyone.

- `real-time.oak.2026-10-17.10_20_00.png` — the 10:20 view, annotated
  with the expected flow direction. EXTERNAL EVIDENCE.
- `flow-confusion.png` — a later view, time not shown. EXTERNAL
  EVIDENCE.
- `faster-distribution.png` — the 11:00 view. EXTERNAL EVIDENCE.

The screenshots cannot be regenerated. The readings behind them, from
the experiments folder:

    uv run python spot_check.py --house oak --start '2026-10-17 10:00' --end '2026-10-17 11:10' --channels primary-flow dist-flow zone4-upstairs-temp

No `gw.readings` instance is in this folder; a display CSV does not
apply.
