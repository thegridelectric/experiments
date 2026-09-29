# sieg-keep-ratio-map, 2026-09-28

> What this is: two hand-driven windows at maple that measure the kept
> fraction of primary flow against the Siegenthaler valve's timed
> position (`keep_seconds`) across the span where it changes, from
> both directions and in both store relay states, and the meters'
> answer lag from the traverses. Ran 2026-09-28 in two windows,
> 18:23 to 19:39 and 19:40 to 21:07 ET, 26 settled stops.

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
holding about half of each. A run from send takes five minutes and a
run from keep seven, since it first makes a full travel to the keep
stop, so 26 runs are about 160 minutes: two windows of `on 90`, closed
on the box clock after a report boundary. Between the two windows
nothing changes; the second continues the shuffled list.

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

All 26 stops settled and read (the 13th of window 1 was cut by the
bound and repeated first in window 2). Positions are motor seconds
from the send stop; for a stop approached from keep the position is
the nominal one, 94 minus the seconds run toward send.

1. **The map, approached from send.** r at rest:

   | s from send | 24 | 27 | 30 | 33 | 36 | 42 | 45 | 51 | 54 | 57 | 60 |
   | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
   | r | 0.00 | 0.00 | 0.16 | 0.32 | 0.42 | 0.63 | 0.71 | 0.82 | 0.87 | 1.00 | 1.00 |

   Keep onset is between 27 and 30 s, the half point about 38 s, keep
   complete between 54 and 57 s. The split is steepest, about 0.04 per
   second, from 30 to 42 s. Repeated positions agree to 0.02 or better
   (30 s: 0.18 and 0.15; 42 s: 0.62 and 0.64; 51 s: 0.82 and 0.82), so
   a timed move from the send stop repeats to about half a second of
   motor.

2. **Approached from keep, the same curve sits 4 s further toward
   keep than its nominal position.** At rest by nominal position:

   | nominal s from send | 24 | 27.5 | 33 | 36 | 39 | 45 | 48 | 54 | 57 | 60 |
   | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
   | r | 0.03 | 0.21 | 0.45 | 0.56 | 0.65 | 0.78 | 0.83 | 0.92 | 1.00 | 0.99 |

   Each of these reads what the from-send curve reads about 4 s
   further along: the half point falls at nominal 34.5 s against 38 s
   from send, 27.5 s reads 0.21 where from send 30 s reads 0.16, 54 s
   reads 0.92 where from send 57 s reads 1.00. So a stop counted down
   from the keep stop lands about 4 s toward keep of where the count
   says: either the keep stop is near 98 s rather than 94, or the
   drive takes about 4 s to reverse before the ball moves. The two
   are the same to the loop, and it means a position reached from the
   keep end is trusted only with this offset applied, or the loop
   re-homes from send. Repeats from keep agree to 0.01 (39 s: 0.65 and
   0.65; 48 s: 0.82 and 0.83).

3. **The store relay does not enter the map.** Same position and
   direction in the two relay states: 30 s from send 0.18 (charge) and
   0.15 (discharge); 39 s from keep 0.65 and 0.65; 48 s from keep 0.82
   and 0.83; 57 s from keep 1.00 and 1.00. Differences are at the
   meters' step size.

4. **The meters' answer lag is about 1 s, not 4.** In motion toward
   keep, sieg-send-flow crossed half of the total 39 s after the
   motor started in all thirteen full travels (twelve at 39, one at
   40). At rest from send the half point is about 38 s, so a reading
   in motion is about 1 s behind the water. In motion toward send, on
   every re-home, the crossing came when the count stood at 33.0 s
   nominal, whatever position the run began from; at rest from keep
   the half point is at nominal 34.5 s, again about 1 to 1.5 s of
   lag. The 4 s inferred from the 2026-09-28 traverses alone was this
   1 s of lag plus the 4 s keep-side offset of finding 2, which those
   traverses could not separate. One second is within a pico's
   posting period; the concern about a 4 s lag in the flow reading is
   answered by this, not by the pico firmware.

5. **The loop's constants against this map** (`valve.py` at
   `b347d2f0`: `t1 = 26`, `t2 = 56`, `FULL_RANGE_S = 94`): keep onset
   is 2 to 3 s later than `t1`, keep complete 0 to 1 s later than
   `t2`, and the keep stop reads 4 s beyond `FULL_RANGE_S` when
   counted from the keep end. The half point for a start is 38 s from
   send. These belong in the layout as the valve's own parameters.

## Timeline

- 18:23:30 box time: window 1 opened on `b347d2f0`, both pis; local
  control opened the heat pump relay at boot. 18:24 driver took the
  tree, homed to send. 18:26 to 19:34: runs 1 to 12, every StopValve
  sent within 20 ms of its target, every `FullySend` / `FullyKeep`
  observed. 19:38:10 run 13 began; 19:39 the bound closed the window
  23 s into its settle.
- 19:40 window 2 opened for 90 min. 19:42 to 21:06: run 13 again, then
  runs 14 to 26; no missed state, no warning. 21:06:32 driver released
  control; 21:07 window closed, plant services restored on both pis.

## Analysis notes

- `r` uses the two measured meters only; the derived `primary-flow`
  adds nothing and is not read.
- The at-rest value of a run is the median of held readings sampled
  every 10 s from 60 to 150 s after the stop, with a 300 s age cap on
  every sample, since a settled flow posts nothing new. A full-run stop
  followed within 5 s by the next move is not a run and `keep_ratio.py`
  skips it.
- A from-keep position is nominal (94 minus seconds run); finding 2 is
  the correction. `half_point.py` reads the traverses; a crossing
  reported 150 s or more after a stub move belongs to the next move
  and is ignored.
- Both flow picos posted on change through every traverse with 0 s
  ages at the crossings, so the maps in motion are not limited by
  capture cadence.

## Folder contents & experimental method

All data is GENERATED by the two windows: the window scada's log on
the box and the `report.event`s it persisted (no LTN peer), copied by
`house_window.sh maple off`, the driver's own log, and the laptop's
broker capture. Nothing comes from the journal DB. The windows stopped
the deployed plant services on both pis and restored them at close;
the heat pump was off throughout.

- `drive_keep_ratio.py` — the driver; `runs.txt` the shuffled list of
  26, `runs-window1.txt` / `runs-window2.txt` as run (run 13 heads the
  second after the bound cut it).
- `drive-window1-20260928-182418.log`, `drive-window2-20260928-194016.log`
  — the driver's dispatches, stop timings and observed states.
- `maple-window-20260928-193926.log`, `maple-window-20260928-210651.log`
  — the window scada's logs; the `Motor toward` / `Motor stopped` lines
  are the positions.
- `maple-events-20260928-193937/`, `maple-events-20260928-210702/` —
  the persisted events, 15 and 18 `report.event`s, the flow readings.
- `broker-capture-20260928-182337.jsonl` — everything the dev broker saw
  through the tunnel across both windows.
- `keep_ratio.py` — at-rest r per stop (findings 1 to 3, 5);
  `half_point.py` — crossings in motion (finding 4).
- `instances/gw.experiment.run-000.json`, `-001.json` — one run record
  per window, from `emit_instances.py`.

Regenerate everything from the logs and events:

    python keep_ratio.py maple-window-20260928-193926.log maple-events-20260928-193937
    python keep_ratio.py maple-window-20260928-210651.log maple-events-20260928-210702
    python half_point.py maple-window-20260928-193926.log maple-events-20260928-193937
    python half_point.py maple-window-20260928-210651.log maple-events-20260928-210702
    ../../gridworks-scada/gw_spaceheat/venv/bin/python emit_instances.py

No `gw.readings` instance is in this folder; the readings are read
from the persisted reports directly.
