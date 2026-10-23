#!/usr/bin/env bash
# spruce-i2c-feedback-window, 2026-10-22 — the commands as run, from experiments/ on the laptop.
# Box pulled to aa3b0709 and the window pair checked identical before run 1.
# Run 1 (07:57 ET): the driver crashed on an import before sending anything; nothing tested.
# Run 2 (08:11 ET): the steps below. The driver was a one-off, iso_toggle_drive.py 6 5;
# admin_drive.py now sends the same sequence and is what a re-run uses.
set -euo pipefail
R=2026-10-22-spruce-i2c-feedback-window
V=../gridworks-scada/gw_spaceheat/venv/bin/python
./spruce_window.sh status
./spruce_window.sh on 11                                  # bounded; the hook prints the Process section
sleep 45                                                  # boot posture, boot adopt, first verify
# 08:13:07 ET: admin takes the tree, TurnOff to hp-boss, six CloseValve/OpenValve pairs on the iso 5 s apart, release
$V admin_drive.py --scada spruce --log $R/evidence/admin-drive.log \
    hp:off sleep:5 \
    valve:iso:close sleep:5 valve:iso:open sleep:5 \
    valve:iso:close sleep:5 valve:iso:open sleep:5 \
    valve:iso:close sleep:5 valve:iso:open sleep:5 \
    valve:iso:close sleep:5 valve:iso:open sleep:5 \
    valve:iso:close sleep:5 valve:iso:open sleep:5 \
    valve:iso:close sleep:5 valve:iso:open sleep:15 \
    release
# the bound closes the window at 11 min (08:23:21 ET)
./spruce_window.sh off                                    # no-op once the bound closed it; copies boot.log to ../scratch
./spruce_window.sh status
./house_window.sh capture off
# then: cp ../scratch/spruce-window-20261022-082343.log $R/evidence/
