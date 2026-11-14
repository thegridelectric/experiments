# sieg-valve-calibration run: beech, 2026-11-13

> What this is: the first calibration of beech's Siegenthaler valve, three
> full traverses and two timed stops driven through admin from the laptop
> between 10:09 and 10:54 ET, read from the journal's report.event
> readings of `hp-loop-on-off-relay`, `hp-loop-keep-send-relay`,
> `sieg-flow` and `primary-flow`.

## Setup as run

Heat pump off, store relay ChargeStore, primary pump failsafe relay to
Scada and scada-ops relay closed; primary flow 4.1 to 4.7 gpm through
the run. The scada was `td/new-house-params` (`865fd9c8`), the deployed
code; the valve relays and flow meters post on change every two to four
seconds while the water moves. A first attempt at 09:58 ran three
traverses with the pump off, because the failsafe relay was on the heat
pump side and the ops relay alone does nothing; `drive.py` gained the
failsafe switch and the plan was rerun at 10:09. The pump-off traverses
are in the journal and `drive.log` and measure nothing.

## Found

`positions-raw.txt` is the reader's output. Seconds are after the motor
start, as the meters report them (lag not removed); r is
`sieg-flow / primary-flow`.

| Move | Onset | Half | Complete | Runs |
| --- | --- | --- | --- | --- |
| toward keep from the send stop | 16–17 s | 29 s | 58–62 s | 3 traverses, 2 stop runs |
| toward send from the keep stop | 24 s | 52–53 s | 65 s | 3 traverses |
| toward send from the 70 s stop | 20 s | 48 s | 61 s | 1 |

With H the true half point, K the keep stop and L the meter lag, half
toward keep is `H + L = 29`, half toward send from the keep stop is
`K - H + L = 52.5`, and from the 70 s stop `70 - H + L = 48`. The last
two give `K = 70 + 52.5 - 48 = 74.5 s`; the first two then give
`L = (29 + 52.5 - 74.5) / 2 = 3.5 s`, the same lag maple showed (4 s), and
`H = 25.5 s`. Keep onset: toward keep `t1 + L = 16.5` gives `t1 = 13 s`;
toward send `K - t1 + L = 65` gives 13 s. Keep complete: toward send
`K - t2 + L = 24` gives `t2 = 54 s`; toward keep r reaches 0.87 at about
58 s and goes on to its 0.95 plateau at about 70 s, so the last of the
split closes slowly right up to the stop.

**Beech's valve: keep onset 13 s, keep complete 54 s, keep stop 75 s,
meter lag 3.5 s.** Against maple's 26 / 56 / 94 s the range is 20 s
shorter and the split starts changing 13 s earlier, so maple's constants
in the scada park beech's valve, at `t2 = 56`, two seconds past its keep
complete point, which is harmless, and command full runs 30 s longer than
its range, which the motor stall absorbs.

Two more things the data shows:

- At full keep r settles at 0.94–0.97: `primary-flow` reads 0.2–0.3 gpm
  more than `sieg-flow` with the send path shut, from the two meters'
  calibration or a real leak past the valve; the derived
  `sieg-send-flow` reads that difference as send flow. At full send
  `sieg-flow` reads zero.
- The split is close to linear in motor seconds over 13 to 54 s, where
  maple's is steep in the middle (`../../../../archive/2026-09-28-sieg-keep-ratio-map/`).

## Folder contents & experimental method

`drive.log` is the driver's log of every dispatch and every state it
observed, both attempts, laptop clock. `started.txt` stamps the two
starts. `positions-raw.txt` is `positions.py --house beech --start
'2026-11-13 10:09' --end '2026-11-13 11:05'`, the evidence being the
journal's report.event readings, which the reader pulls through the
repo's `spot_check.py`.
