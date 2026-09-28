# sieg-keep-ratio-map, queued

> What this is: two hand-driven windows at maple that measure the kept
> fraction of primary flow against the Siegenthaler valve's timed
> position (`keep_seconds`) across the span where it changes, from
> both directions and in both store relay states, and the meters'
> answer lag from the traverses. Found is open; the logbook line dates
> it on first run.

## Why

The loop's only knowledge of the valve is a timer: `keep_seconds`,
counted from the send stop, on a 100 s `FULL_RANGE_S` with a keep end
measured at or before 81 s (two admin stops on 2026-09-28 at 81.1 and
81.5 s with sieg-flow already at its full-keep 5.0 gpm). To reckon one
move on a start (basic-sieg change 6) the loop needs the map from
`keep_seconds` to the kept fraction, and it needs to know how
repeatable a timed move is, since the map is only as useful as the
scatter around it. The 2025–26 loop (`c55fe9eb`,
`gw_spaceheat/actors/sieg_loop.py` "flow_from_time_points") carried an
eleven-point table on a 70 s range, measured once, with 50 percent
keep near 22 s:

    (7, 0) (9, 8) (11.2, 11.4) (14.7, 24.1) (18.2, 39.0) (22.4, 51.7)
    (28.7, 66.6) (35.7, 75.2) (39.9, 80.6) (42.7, 83.7) (67.2, 100)

The branch's `t1 = 26` and `t2 = 82` come from nowhere written down.
This experiment replaces both with maple's own table, its standard
deviation, and the store-direction dependence, all from the two flow
meters maple already reports.

The traverses of the four 2026-09-28 windows already give the half
point (`half_point.py`, run over the logs and persisted reports of
`../../2026-09-28-maple-ecodan-start-in-full-keep/`). Toward keep from
the send stop, sieg-send-flow fell through half of the total 40 s
after the motor started, in all four such runs (07:00, 12:47, 14:16,
14:35), with the two meters at about 2.1 and 1.9 gpm at the crossing.
Toward send the crossing came 61 and 62 s after a start from the
mechanical keep stop (12:41, 12:57) and 48 and 49 s after a start from
the 81 s admin stop (14:26, 14:46). Those two fix the mechanical keep
stop at about 94 s of travel from the send stop; sieg-flow saturates
at 5 gpm by 81 s, twelve or so seconds before the valve reaches it.
The half point is then 40 s going toward keep and 32.5 s going toward
send by these crossings, which a valve with one speed both ways cannot
show; the six agree at about 36 s if every flow reading answers about
4 s after the motor. The onsets of change and the settling of the
other meter place keep onset at about 26 s and keep complete at about
56 s the same way.

## Setup

- Maple, a beta field window on the `jm/spruce-unlimbo` branch
  (`field-window-recipe.md`), heat pump off for the whole window, the
  primary pump running, admin holding the tree. The buffer and store
  see pump flow only, so the house's heat is not touched; the window
  displaces production for its length.
- The valve moves only through the three admin commands the panel
  offers: MoveToFullSend, MoveToFullKeep, StopValve. A position is
  reached by MoveToFullKeep from the send stop and StopValve after
  the target seconds on the panel clock. The seconds actually run are
  in the window log (`Motor stopped after X s: keep_seconds Y`), so the
  hand timing sets the target, not the measurement.
- Kept fraction `r = sieg-flow / (sieg-flow + sieg-send-flow)`. Maple
  measures these two and derives `primary-flow` as their sum
  (`tlayouts/maple_gen.py`), so there are exactly two independent
  meters: the sieg-btu pico (`sieg-flow`) and the send-line Hall pico
  (`sieg-send-flow`, async threshold 0.04 gpm). Both report in steps
  larger than 0.1 gpm at times, so each run's flows are the median of
  the readings between 60 and 150 s after the stop, never a single
  reading, and a run with fewer than three readings of either meter in
  that span is discarded, not padded.
- Each run also records the pump's primary flow at that posture
  (4.85 gpm at full keep and 4.13 gpm at full send on 2026-09-27, same
  pump command), since the split and the total both move with the
  valve.

## Protocol

The flow split changes only between keep onset (about 26 s) and keep
complete (about 56 s), so every stop lands in that 30 s span, and the
seconds actually run are read from the log, so a stop need not hit a
target: the design is a spread of at-rest points across the span, from
both directions, with the store relay alternating, and the map is a fit
to all of them. Each run also traverses the whole range once, and the
traverse is the same map read in motion, so the in-motion and at-rest
readings together measure the meters' answer lag directly.

One run, about five minutes:

- **From send.** At the send stop: MoveToFullKeep, StopValve at the
  target seconds, 150 s settled, then MoveToFullSend (a full re-home,
  and a traverse toward send).
- **From keep.** MoveToFullKeep to `FullyKeep` (a traverse toward keep),
  then MoveToFullSend, StopValve at (94 minus the target) seconds,
  150 s settled, then MoveToFullSend to re-home.

Runs alternate from-send and from-keep, and the store relay
(ChargeStore / DischargeStore) alternates every two runs. Targets
walk the span at 3 s steps, 24 to 60 s from send, in a shuffled order,
twice through: 26 stops, 13 from each direction, with each relay state
holding about half of each. About 130 minutes; two windows of `on 75`,
closed on the box clock after a report boundary. Between the two
windows nothing changes; the second continues the shuffled list.

What the analysis reads out (`keep_ratio.py` for the at-rest rows,
`half_point.py` for the traverses):

1. **The map.** r against seconds from send over all 26 stops, fit by
   a monotone curve; the residual standard deviation is the
   repeatability of a timed move, with the two meters' step sizes
   noted beside it. Three or more stops within 2 s of the half point
   give the scatter where the slope is steepest.
2. **Direction.** The from-keep stops against the from-send stops on
   the same curve. A shift is a keep-stop error (the 94 s), a speed
   difference between directions, or slack in the drive; its size says
   whether the loop may trust a position reached from either end or
   must re-home from one.
3. **Store relay.** The ChargeStore stops against the DischargeStore
   stops on the same curve. A shift means the send path's head enters
   the map, and the relay state becomes an input to it.
4. **The lag.** Each traverse gives r against seconds in motion; the
   shift that lays it on the at-rest curve is the meters' answer lag,
   read separately for the two directions and, through which meter
   moves first, for the two picos. This is the number the 2026-09-28
   crossings put at about 4 s.

## Found

Open.

## Timeline

Open.

## Analysis notes

- `r` uses the two measured meters only; the derived `primary-flow`
  adds nothing and is not read.
- A `sieg-flow` reading whose age passes a capture period while the
  pico is alive was seen once (399 s, 2026-09-27); the 300 s age cap
  on every sample is there so such a run drops out rather than passing
  on a stale value.
- The window log's `keep_seconds` after a stop is the actor's own
  count and carries its overshoot allowance; the seconds actually run
  (`Motor stopped after X s`) is the independent variable.

## Folder contents & experimental method

All data is GENERATED by the window: the window scada's log on the box
and the `report.event`s it persists (no LTN peer), copied by
`house_window.sh maple off`. Nothing comes from the journal DB. The
window stops the deployed plant services on both pis and restores
them at close.

- `keep_ratio.py` — reads the stops from the window log and the flows
  from the persisted reports, one row per run: seconds run,
  keep_seconds, median held sieg-flow and sieg-send-flow, r; groups by
  target and prints mean and standard deviation.

        python keep_ratio.py <window log> <events folder> [--from-keep]

- Window logs, `maple-events-*/` folders and `instances/` arrive on
  first run.
