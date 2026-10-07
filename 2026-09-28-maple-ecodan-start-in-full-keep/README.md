# maple-ecodan-start-in-full-keep, 2026-09-28

> What this is: four beta field windows on maple in one day (the first
> on scada `b9679d4e`, the last two on `1287911f`, the `jm/spruce-unlimbo`
> branch on both pis) driven by hand from the admin panel to watch the
> Mitsubishi Ecodan start with the Siegenthaler loop at full keep: how
> long the call takes to become power, how the kept loop heats, how the
> Ecodan behaves when the call is removed, and, from the closed starts
> of all four windows together, the water volume of the loop. Findings
> 1 to 5 are from the first window's log; finding 6 is fit across the
> four windows' persisted reports.

## Setup

- Window opened 06:53:44 box time (`house_window.sh maple on 30`), the
  plant services stopped and recorded on both pis, restored at close.
  Heating mode, actuation authority Active. Admin took the tree at
  06:55:11 and held it to the end.
- The box clock runs about 70 s behind the laptop clock. Times here are
  the box's.
- The heat pump had been running under the production scada right up to
  the window (relay 6 closed, 1.8 kW at the first reading), so the first
  minutes are its tail, not part of the test.

## Timeline (box clock)

| time | admin move | what followed |
| --- | --- | --- |
| 06:55:11 | TurnOff (hp-boss opens relay 6) | Ecodan still ramping from its earlier call: 2.9 kW, a 5.1 kW peak at 06:55:44, 2.1 kW to 06:57:14, then 300 W at 06:57:44. About 2.5 min from the call opening to standby. |
| 06:58:26 | MoveToFullSend, then ChargeStore at 06:58:41 | Store water reaches the heat pump: hp-ewt 118 F at 06:59:14, 73 F at 06:59:44, 62 F by 07:00:44; store-hot-pipe 117 F to 66 F over the same minute. |
| 07:00:48 | MoveToFullKeep | Motor runs 110 s; FullyKeep at 07:02:38. sieg-flow 0 to 5.01 gpm, sieg-send-flow 4.0 to 0.02 gpm, primary-flow 5.03 gpm. Loop water 68.6 F at hp-lwt, 68.8 F at hp-ewt. |
| 07:03:07 | TurnOn (hp-boss closes relay 6) | Standby 54 to 56 W for 3 min 52 s. Power step at about 07:07:00: 1164 W at the 07:07:14 reading. |
| | | Ramp in full keep: 1164 W to 07:08:44; 1466 W at 07:09:14 (6 min after the call); 2478 W at 07:10:14; 2784 W at 07:10:44; 4262 W at 07:11:12. |
| 07:08:53 | DischargeStore | mixing water for the send side to come from the buffer. |
| 07:11:12 | MoveToFullSend | hp-lwt 130.1 F, hp-ewt 127.6 F at the move. |
| 07:11:18 | TurnOff (relay 6 opens) | Ecodan runs on: 4262 W at 07:11:14, 3147 W at 07:11:44 with hp-lwt at 139.5 F, 2522 W through 07:13:02, 48 W at 07:13:14. About 1 min 50 s from the call opening to standby. |
| 07:13:02 | | FullySend reached; loop opened, hp-ewt back at 117 F by 07:13:44. |

## Found

1. **Cold start in full keep: 3 min 52 s from the call to power.** The
   Ecodan sat at standby from 07:03:07 to about 07:07:00 with 69 F water
   at its inlet and the loop fully kept at 5 gpm, then stepped to 1164 W.
   1.5 kW came at 6 min. Both sit on the startup-signature medians for
   this machine (215 s to the step, 414 s to 1.5 kW), so a kept loop with
   cold water does not change the start delay.
2. **The kept loop heats about 15 F a minute at 1.2 to 2.8 kW.** From the
   07:07:14 reading (hp-lwt 73.7 F) to 07:11:12 (130.1 F) is 56 F in
   4 min with the loop closed at 5 gpm. The lift across the heat pump
   stayed small the whole time, 1.5 to 2.6 F at 5.1 gpm, which is 3.8 to
   6.6 kBTU/h leaving the machine against 1.2 to 2.8 kW going in: the
   Ecodan is well below its running COP during this ramp. hp-lwt reached
   139.5 F at 07:11:44, above the 138.9 F thirty-day maximum in the
   signature notes, before the loop opened.
3. **Removing the call does not stop the Ecodan for one to two and a half
   minutes.** Twice in this window the compressor ran on after relay 6
   opened: 06:55:11 to 06:57:44 (mid-ramp, with a 5.1 kW peak after the
   open), and 07:11:18 to 07:13:14 (from 4.3 kW). The HpOff the admin
   panel shows is the relay's commanded and physical state (bit 2 of
   expander 0x20 low byte, energize-low, read at the bus); the power is
   the machine's own run-down.
4. **The relay is where the panel says it is.** Relay 6 read energized
   (open, HpOff) at the bus while `hp-odu-pwr` showed 1.9 kW, and
   de-energized (closed) before the window under production. The 1.9 kW
   was the tail of the production call.
5. **The sieg-flow meter is live in both loop positions.** 0.00 gpm at
   full send with primary-flow 4.4 gpm; 5.01 gpm at full keep with
   sieg-send-flow 0.02. primary = sieg + send held within 0.02 gpm at
   every reading.

6. **The kept loop is about 0.8 gallons of water; the fit drifts up
   with temperature.** The model is the simplest one that fits a closed
   loop: no losses, no pipe or sensor mass, and one unknown, the volume
   of water V in the loop. Then over any interval

       V x (rise in hp-lwt) = integral of sieg-flow x (hp-lwt - hp-ewt) dt

   with V in gallons, flow in gpm and temperatures in F. Solving for V
   needs only the three channels the loop already reports. The
   integral is a trapezoid sum over the hp-lwt readings in each
   report.event, with hp-ewt interpolated to each hp-lwt stamp and
   sieg-flow the last reading before it (`loop_volume.py`). The
   intervals are disjoint one-minute chunks of compressor run into the
   kept loop, each beginning where the lift is about 2 F, nine across
   the four windows:

   | Chunk | hp-lwt over the minute | Lift, mean | gpm | Integral (gal F) | Rise | V (gal) | Turnover at 5 gpm |
   | --- | --- | --- | --- | --- | --- | --- | --- |
   | 07:07:33 | 82.4 to 96.4 F | 2.06 F | 5.09 | 10.08 | 14.0 F | 0.72 | 8.5 s |
   | 07:08:36 | 97.4 to 107.7 F | 1.61 F | 5.12 | 7.58 | 10.3 F | 0.74 | 8.6 s |
   | 12:53:17 | 70.6 to 82.7 F | 1.63 F | 5.06 | 8.10 | 12.0 F | 0.67 | 8.0 s |
   | 12:55:57 | 101.2 to 116.2 F | 2.49 F | 5.13 | 12.05 | 15.0 F | 0.80 | 9.4 s |
   | 14:22:41 | 75.3 to 88.1 F | 1.99 F | 4.99 | 9.73 | 12.8 F | 0.76 | 9.2 s |
   | 14:23:41 | 88.3 to 99.4 F | 1.85 F | 5.03 | 9.06 | 11.1 F | 0.82 | 9.7 s |
   | 14:24:42 | 99.8 to 112.7 F | 2.41 F | 5.04 | 11.29 | 13.0 F | 0.87 | 10.4 s |
   | 14:44:38 | 104.6 to 118.5 F | 2.67 F | 5.04 | 12.43 | 13.9 F | 0.89 | 10.6 s |
   | 14:45:39 | 118.7 to 127.9 F | 1.88 F | 5.06 | 9.36 | 9.1 F | 1.03 | 12.2 s |

   Median 0.80 gal, mean 0.81, range 0.67 to 1.03. Eight feet of 1"
   type L copper holds 0.34 gal, so about 0.45 gal sits inside the heat
   pump between the two sensors. At 5 gpm the loop turns over every 9
   to 10 s.

   The spread is the model's own signal that it is missing a term. V
   climbs with loop temperature, 0.67 gal at 75 F to 1.03 gal at 125 F,
   and does so in step within one run (14:22 to 14:24: 0.76, 0.82,
   0.87). A lossless fixed volume gives the same V at every
   temperature. Of the candidates, only heat leaving the loop grows
   with temperature: loss to the room, and heat taken by the heat
   pump's exchanger and refrigerant side while they warm. Pipe and
   sensor mass add a fixed amount to V (the copper is about 0.2 gal of
   water-equivalent) and sensor lag shifts both traces equally in time
   and changes neither the lift nor the rise per minute, so neither
   can make a trend. The 14:37 to 14:43 hold in the fourth window
   (valve stopped at keep_seconds 81.1, heat pump idle at 54 W, hp-lwt
   and hp-ewt on a 0.05 C async delta) measured the room loss
   directly: 0.27 C a minute at 105 F, about 60 W, 3 percent of the
   2 kW the lift represents, so room loss alone is too small for the
   spread and the heat pump's own warming is the larger term. The same
   hold read hp-ewt 0.35 to 0.38 C above hp-lwt on the same water;
   adding that offset back to the lift (`--offset 0.65`) raises every V
   by a quarter to a third, mean 1.07 gal, and leaves the spread, so
   the offset is a calibration correction separate from the loss term.

   The lift itself is the number to carry forward: about 2 F at 5 gpm
   is 2 kW into the water against 1 to 3.5 kW of electricity at the
   outdoor unit, so through these ramps most of the heat pump's output
   is not reaching the water.

## What was lost

The window was closed at about 07:14:40 box time, before the 07:15:00
report boundary, because the close was timed on the laptop clock, 70 s
ahead of the box. The report for the 07:10 to 07:15 slot, the one carrying
the MoveToFullSend and TurnOff moves and the run-down, was never produced.
The same readings are in `sieg-view.csv` at 30 s and in the broker
capture's snapshots, so nothing in "Found" rests on the missing report;
the reports that exist cover 06:53 to 07:10. Close a window on the box's
clock, not the laptop's.

## Folder contents & method

All values were generated during the session by the window scada and the
laptop capture; nothing here is from the journal DB. Admin moves were made
by hand through the admin panel (`gwa watch maple`).

- `maple-window-20260928-071602.log` — the window scada's log on maple,
  copied by `house_window.sh maple off`. The `[sieg-loop] sieg-view` lines
  are the 30 s strip of loop temperatures, flows and power.
- `maple2-window-20260928-071609.log` — the second pi's window scada2
  log (analog temperatures).
- `maple-pair-watch-20260928-065516.log` — the laptop's watcher on the
  two pis.
- `sieg-view.csv` — the sieg-view lines as columns, written by
  `parse_sieg_view.py` (run it again after any edit to the log).
- `timeline.txt` — the admin dispatches, hp-boss relay commands and
  sieg-loop transitions, grepped from the window log.
- `maple-events/` — the 19 events the window scada persisted on the box
  (no LTN peer, so events never left it): startup and comm events, and
  the four `report.event`s at 06:55, 07:00, 07:05 and 07:10.
- `broker-capture-20260928-065451.jsonl` + `.provenance.txt` — every
  message the laptop's dev broker saw through the tunnel: snapshots,
  power, the layout announcement. 100 messages.
- `instances/gw.experiment.run-000.json` — the run record of the first
  window, emitted by `emit_instances.py` from the window log's first and
  last stamps. The later windows have no run instance yet.
- `maple-window-20260928-143026.log`, `-145019.log` and
  `maple-events-130239/`, `-143041/`, `-145033/` — the second, third and
  fourth windows of the day (12:41 to 13:02, 14:13 to 14:30, 14:33 to
  14:50 ET), each the window scada's log and its persisted events as
  `house_window.sh maple off` copied them; the suffix is the copy's
  laptop stamp. The second window's log is
  `../beta-field-windows/runs/2026-09-28-1241-maple-admin-start/maple-window-20260928-130220.log.gz`,
  that run's own copy. The third window was the first with hp-lwt and hp-ewt
  at a 0.1 C async delta, the fourth at 0.05 C. A 13:49 to 14:12 window
  between them ran no start and is not kept here.
- `loop_volume.py` — the finding-6 fit over the nine chunks named in it,
  reading the `maple-events*` folders; `--offset` adds a same-water
  sensor offset to the lift.
