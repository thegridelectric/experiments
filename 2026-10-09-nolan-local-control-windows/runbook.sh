#!/usr/bin/env bash
# nolan-local-control-windows, 2026-10-09 — the commands as run, from experiments/ on the laptop.
set -euo pipefail
ssh spruce 'git -C ~/experiments pull --ff-only'                       # 10:48 ET, box at 1e5bd72
yes | ./put_layout.sh spruce nolan-window                               # ops params put, layout identical
./spruce_window.sh status                                               # winter hack + gwspaceheat active, window down
./spruce_window.sh on 15                                                # 10:49:22 ET
ssh spruce 'grep -a -E "\[lc\]|hp-watch|forecast|Provisioning|Traceback" /tmp/spruce-window/boot.log'
# wait for the bound (~11:05:45 ET), then:
./spruce_window.sh off                                                  # copies boot.log + events to ../scratch
./spruce_window.sh status                                               # services back
./house_window.sh capture off

# Run 2, afternoon — spruce and beech
ssh beech 'cd ~/starter-scripts && git pull --ff-only && ./pico_cycle_census.sh 240'   # 15:20 ET, census
./put_layout.sh beech check                                              # differs: post-10-02 gen commits
yes | ./put_layout.sh beech standby-cold-watch                           # both pis, pre-copies left
ssh beech 'git -C ~/gridworks-scada-unlimbo pull --ff-only'; ssh beech2 'git -C ~/gridworks-scada-unlimbo pull --ff-only'
./spruce_window.sh on 25                                                 # 15:29:22 ET
ssh beech 'git -C ~/experiments pull --ff-only'; ssh beech2 'git -C ~/experiments pull --ff-only'   # first beech on refused
./beech_window.sh on 20                                                  # 15:31:04 ET
./beech_window.sh off                                                    # 15:37:14 ET, run 2a closed early by mistake
./beech_window.sh on 20                                                  # 15:37:54 ET, run 2b
# bounds: spruce 15:54:22, beech ~15:58; then:
./spruce_window.sh off                                                   # 15:59:21 ET, 12 events, 5 report.event
./beech_window.sh off                                                    # 15:59:40 ET, 18 events, 4 report.event
./house_window.sh capture off                                            # 166 messages
