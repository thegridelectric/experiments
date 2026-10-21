#!/usr/bin/env bash
# spruce-pump-on-power-window, 2026-10-21 — the commands as run, from experiments/ on the laptop.
set -euo pipefail
./put_layout.sh spruce hp-boss-pump                     # layout put, ops identical
ssh spruce 'git -C ~/gridworks-scada-unlimbo pull --ff-only'   # box at a9acd401
./spruce_window.sh status                               # hack + gwspaceheat active, window down
./spruce_window.sh on 11                                # 16:24:00 ET
ssh spruce 'tail -f /tmp/spruce-window/boot.log' | grep -E -i "secondary-pump|hp-watch|hp-boss|admin"
# operator: gwa watch spruce; take admin, turn the heat pump on, later off
./spruce_window.sh off                                  # after the bound; copies boot.log to ../scratch
./spruce_window.sh status
./house_window.sh capture off
