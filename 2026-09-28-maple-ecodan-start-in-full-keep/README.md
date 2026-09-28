# maple-ecodan-start-in-full-keep, 2026-09-28

> What this is: a 21-minute beta field window on maple (scada `b9679d4e`,
> the `jm/spruce-unlimbo` branch on both pis) driven by hand from the
> admin panel to watch the Mitsubishi Ecodan start with the Siegenthaler
> loop at full keep and cold water at its inlet: how long the call takes
> to become power, how the kept loop heats, and how the Ecodan behaves
> when the call is removed. Every reading below is from the window scada's
> own log; the window's reports and the broker capture are in the folder.

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
- `instances/gw.experiment.run-000.json` — the run record, emitted by
  `emit_instances.py` from the window log's first and last stamps.
