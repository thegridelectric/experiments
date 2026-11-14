# sieg-valve-calibration

> What this is: the procedure that measures a house's Siegenthaler valve,
> the three positions in motor seconds that the sieg loop's strategies
> stand on (keep onset, keep complete, keep stop), run on every house
> with a sieg loop and repeated when a valve or its actuator changes.
> Undated: one recipe, one driver, one reader, and a dated run folder
> per house under `runs/`. The method was found at maple on 2026-09-28
> (`../../archive/2026-09-28-maple-ecodan-start-in-full-keep/`, `../../archive/2026-09-28-sieg-keep-ratio-map/`).

## Why

The loop knows the valve only as a timer counted from the send stop. The
flow split changes over a middle span of the travel and the motor runs on
to a mechanical stop beyond it; a strategy that parks on the cusp of keep
(`t2`) or opens from it needs those seconds for the valve in front of it.
Until the hardware layout names them the scada code holds maple's values
(94 s keep stop, 26 s keep onset, 56 s keep complete), and a valve parked
short of its own keep-complete point leaks send flow through a start.

## Setup

- The house runs its deployed scada; the driver goes through the admin
  path from the laptop (`gwadmin`, the house's entry in
  `~/.config/gridworks/admin/admin-config.json`), with the scada venv.
- Flow only: the driver turns the heat pump off, sets the store relay
  (ChargeStore by default, so send flow enters the store), switches the
  primary pump's failsafe relay to Scada and closes its scada-ops relay.
  With the failsafe on the heat pump side the ops relay does nothing and
  the pump stays off, which the 2026-11-13 beech run found the hard way. At a house with a manual
  isolation valve on the store, close it beforehand if the store is where
  the water should go.
- About 35 minutes for the first-pass plan (`plans/traverses.txt`).
  The house has no heat for that long; local control resumes its posture
  at release.

## Protocol

```
../../../gridworks-scada/gw_spaceheat/venv/bin/python drive.py <house> \
    plans/traverses.txt --log runs/<date>-<house>/drive.log
```

The driver homes the valve to full send, then runs the plan: three full
traverses (send to keep, settle 150 s, keep to send, settle 150 s) and two
stops from the send stop at 70 and 80 s, each settled and re-homed to send.
Every dispatch and every sieg-loop state it observes is logged with the
laptop clock. The motor's timing is read afterwards from the journal.

## Reading the positions

```
uv run python positions.py --house <house> --start '<ET>' --end '<ET>'
```

The two valve relays post on change into report.event, so each motor
start and stop is in the journal whatever scada version the house runs.
For each run the reader holds the flow readings per second, forms the
kept fraction (`sieg-flow / primary-flow` where primary flow is measured,
`sieg-flow / (sieg-flow + sieg-send-flow)` where the send line is), and
prints the seconds after the motor start at which the fraction leaves its
starting plateau (onset), crosses one half (half) and reaches its ending
plateau (complete).

The meters answer some seconds after the motor (4 s at maple). With H the
true half point, K the keep stop and L the lag:

- toward keep from the send stop, half is seen at `H + L`;
- toward send from the keep stop, at `K - H + L`;
- toward send from a stop at S seconds, at `S - H + L`.

So the two stop runs give `K = S + (half from keep) - (half from S)` with
no lag in it, and L follows from the traverses once K is known. Keep
onset and keep complete come off the toward-keep traverses with L taken
out (`--lag-s`). The three positions go into the house's gen in tlayouts
when the layout word exists, and into the scada's valve constants until
then.

## Runs

| Run | House | Keep onset | Keep complete | Keep stop | Lag | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| `../../archive/2026-09-28-*` | maple | 26 s | 56 s | 94 s | 4 s | the method's source |
| `runs/2026-11-13-beech/` | beech | 13 s | 54 s | 75 s | 3.5 s | first run; K from one stop pair |

## Folder contents & experimental method

`drive.py` sends the admin dispatches and logs them; the measurement
itself is the journal's report.event readings of the house's relay and
flow channels, pulled by `positions.py` through the repo's `spot_check.py`, which
is the whole of the evidence. A run folder `runs/<date>-<house>/` holds
the driver log and the reader's output as run.
