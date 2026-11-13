# Spruce living-room fan-coil → distribution-pump test

Genre: incident investigation (field actuation). Run 2026-08-15 ~15:10 ET.
Code under test: none — this probes the *deployed* plant (actual-spruce
scada + the gw108 zone relays). Harness:
[`spruce_fancoil_dist_test.py`](spruce_fancoil_dist_test.py), a re-runnable
reproducer.

## Why

George reported the living-room (zone 5) fan-coil **thermostat "wasn't
working"** — no cooling. Earlier the same day the zone-5 whitewire opto read
`idle` (no call reaching the board). This test asks the discriminating
question: **force the zone-5 call at the scada relay, bypassing the wall
thermostat — does the distribution side respond?** If yes, the fault is
upstream (thermostat / whitewire); if no, it is downstream (relay → Caleffi
→ zone valve → dist pump → fan-coil).

Zones 3 (upstairs fan-coil) and 5 (living-room fan-coil) share the
distribution pump, so we take control of both, hold 3 off, and toggle only 5.

## Setup

Summer hack STOPPED for the window (nothing else drives the 0x20 zone
relays); deployed actual-spruce scada left RUNNING (we read its snapshots).
The harness touches only the 0x20 zone-3/zone-5 relays (read-modify-write,
so the 1/2/4 floor holds are preserved), never 0x21 or the DAC. It restores
zones 3 & 5 to thermostat control on exit; the hack was restarted afterward.
Zone-5 fan-coil is cooling-safe (no condensation hazard), so a forced summer
call is reversible and benign. Dist-pump-pwr is async (5 W delta, 1 s poll),
dist-flow async on-change — both respond within seconds of a real change.

## Found

| channel | baseline (both off) | zone-5 call ON |
|---|---|---|
| dist-flow | 0.06 GPM | **1.56 GPM** (rose within ~26 s, held) |
| dist-pump-pwr | 0–1 W | 0–1 W (**no measurable change**) |
| secondary-flow | 0 GPM | 0 GPM (HX side; hack stopped) |
| primary-flow | 7.51 GPM | 7.51 GPM (unchanged) |

**The downstream path works.** Forcing the zone-5 call opened the
living-room fan-coil circuit and produced an immediate, sustained
distribution-flow response (0.06 → 1.56 GPM). The relay → Caleffi → zone
valve → fan-coil chain is functional. Combined with the zone-5 whitewire
opto reading `idle`, this points at the **wall thermostat / whitewire as the
fault** — not the relay, valve, or plumbing.

**Open — the distribution pump's own power did not rise.** The 1.56 GPM
appears with `dist-pump-pwr` still at ~0 W while the primary loop runs a
steady 7.51 GPM. Most likely the flow is primary-loop-driven through the
newly-opened zone branch (the dist pump did not need to run), or the dist
pump draws below the 5 W async threshold. Not resolved here; it does not
change the upstream-fault conclusion, but it is worth a look before trusting
`dist-pump-pwr` as the sole "is the dist pump running" signal.

## Reproduce

    # on spruce, summer hack stopped, starter venv:
    sudo systemctl stop spruce-summer-hack.service
    ssh pi@<spruce> 'cd ~/starter-scripts && venv/bin/python -' < spruce_fancoil_dist_test.py
    sudo systemctl start spruce-summer-hack.service

Reads the prod-broker snapshot via the starter-scripts `.env` creds; writes
only the two zone relays on i2c 0x20.
