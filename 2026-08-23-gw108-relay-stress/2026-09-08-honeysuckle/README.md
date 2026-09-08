# honeysuckle, 2026-09-08 (gw108-relay-stress run 3)

> What this is: does the 0x21 expander reset on iso-valve relay
> switching (`../2026-08-23-spruce/` B: 35/100;
> `../2026-09-08-spruce-board2/` B2: 17/100) need the house
> side at all? Same harness, same runs, on the bench gw108 (honeysuckle)
> with nothing on the relay contacts. Verdict in "Found" once run.

## Why

Two boards have now reset at spruce on the same condition (the iso
relay switched with fewer than two other 0x21 coils energized), while
Joe could not reproduce on his bench boards. Spruce's two boards differ
from a bench board in what hangs on the relay contacts: the iso valve
actuator and the house wiring. Honeysuckle is a gw108 with nothing on
the contacts, so its run B twin separates the two readings of the
board2 result. Zero resets in 100 toggles on the bench and the reset
needs the house side (the actuator's inrush on the relay supply, or the
wiring at that position). Resets at the spruce rate and the mechanism
is in the board family's own relay switching, with no load at all, and
Joe's bench result needs revisiting.

## Setup

- **Host:** honeysuckle, the bench gw108 (`d1.bench.honeysuckle.ta`).
  No scada service, nothing else writes 0x21 (checked 2026-09-08 17:59
  ET: only the printer applet runs). Expanders answer at 0x20 and 0x21.
- **Assumption to confirm on site:** nothing is wired to the relay
  contacts on the bench board, so energizing any coil moves nothing;
  the relay coil supply is the board's own.
- **Harness:** `../relay_stress.py`,
  unchanged, run from the box's `~/experiments` clone with the scada
  venv's python (smbus2 is there). Its prompts and exit-posture message
  name the spruce summer hack; on honeysuckle there is none, `--yes`
  skips the prompt, and the exit posture (iso OPEN, secondary pump ON,
  everything else off) energizes two coils on an unloaded board.
- **Runs:** the board2 triplet with new labels. B3 is the measurement,
  F3 and A3 the guards.

    # once: the box has no experiments clone yet; record it in ~/README.md
    git clone https://github.com/thegridelectric/experiments.git ~/experiments

    cd ~/experiments/2026-08-23-gw108-relay-stress
    PY=~/gridworks-scada/gw_spaceheat/venv/bin/python
    CHARGE_POSTURE=0 PUMP_POSTURE=0 HP_POSTURE=0 LOADS=0 TARGET=iso PERIODS=1 TOGGLES=100 MAX_RESETS=1000 $PY relay_stress.py --run B3 --yes
    CHARGE_POSTURE=0 PUMP_POSTURE=1 HP_POSTURE=1 LOADS=0 TARGET=iso PERIODS=1 TOGGLES=30 MAX_RESETS=1000 $PY relay_stress.py --run F3 --yes
    CHARGE_POSTURE=0 PUMP_POSTURE=1 HP_POSTURE=1 LOADS=5 TARGET=iso PERIODS=1 TOGGLES=30 MAX_RESETS=1000 $PY relay_stress.py --run A3 --yes

    # dev machine: collect, then restore on the box
    scp 'honeysuckle:~/relay-stress-runs/relay-stress-*' .
    ssh honeysuckle 'rm -r ~/relay-stress-runs'

Bar: B3 resets / 100 against 35 (08-23) and 17 (board2). Zero and the
reset needs the house; the spruce rate and it is the board family
unloaded. F3 and A3 must stay at zero, as on both spruce boards.

About five minutes end to end: B3 runs 100 toggles at 1 s, F3 and A3
30 each, 10 s settle between.

## Found

**The bench board does not reset. B3: 0 resets in 100 iso-relay toggles
with no other 0x21 coil energized, the condition that reset spruce's
original board 35 times and its replacement 17 times. F3 and A3: 0/30
each. Not one CRITICAL line in any log. The reset needs what spruce
hangs on the relay contacts: the iso valve actuator's inrush on the
relay supply, or that position's wiring. It is not the board family
switching an unloaded relay, which is also what Joe saw on his bench.**

| run | other coils | toggles | resets | spruce board1 / board2 |
| --- | --- | --- | --- | --- |
| B3 | none | 100 | **0** | 35 / 17 |
| F3 | secondary pump + hp-call | 30 | **0** | 0 / 0 |
| A3 | pump, hp-call, 5 unwired | 30 | **0** | 0 / 0 |

- Same harness, same launch lines, same register map as the two spruce
  runs; the only difference is nothing on the contacts and no house
  wiring. Nothing was wired to any relay contact on the bench (confirmed
  on the day).
- Next on the house side: measure the iso actuator's inrush, and try the
  iso valve on a different relay position or with its supply decoupled
  from the board's relay supply.

## Timeline

- 18:24 ET: `~/experiments` cloned on honeysuckle at `af55644` and
  recorded in the box README (its first clone).
- 18:25:06 to 18:26:59 B3; 18:27:00 to 18:27:43 F3; 18:27:43 to
  18:28:27 A3. Exit posture: iso OPEN, secondary pump ON, everything
  else off (unloaded coils).
- 18:3x: outputs copied here; `/home/pi/relay-stress-runs/` and the
  driver output removed from the box.

## Analysis notes

- The harness's reset count is the PHASE RESULT figure in the log; the
  log carries more CRITICAL lines than resets because a reset caught
  mid-act logs the i2c error and the confirming read separately.
- Register/bit map is the harness's own constants (hp-call 2/0, iso
  3/2, charge 3/3, store pump 3/4, secondary pump 3/5, loads 2/3..2/7),
  the same on every gw108.

## Folder contents & experimental method

Data GENERATED by this experiment: the harness's own register reads on
the box, no store holds them; a re-run is a new dataset. The harness is
the only 0x21 writer on honeysuckle, so no service is stopped.

- `README.md` — this file.
- `relay-stress-<label>.log`, `relay-stress-<label>-results.json` — the
  harness outputs, copied from `/home/pi/relay-stress-runs/` on the box
  and that directory removed. Regenerate with the run lines under Setup.
