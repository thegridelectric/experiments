#!/usr/bin/env bash
# spruce-roll-rehearsal, 2026-10-22 — the commands as run, from the laptop.
# Attempt 1 (10:52:33 ET) stopped before the restart: the inner ssh calls in
# roll.sh swallowed the piped answers. ssh -n was added and the roll re-run.
# The quarantine step at the end is what roll.sh now does itself on every roll.
set -euo pipefail
S=../gridworks-scada/scripts
$S/roll.sh spruce check
printf 'y\ny\n' | $S/roll.sh spruce to jm/spruce-unlimbo        # 10:53:08 ET; y: install the jm/spruce layout, y: install its ops file
ssh -n spruce 'timeout 120 journalctl -u gwspaceheat -f --no-pager -o short-iso --since "90 seconds ago"'   # 10:53:48 ET
printf 'y\n' | $S/roll.sh spruce back                           # 10:56:15 ET; y: restore the actual-spruce layout
ssh -n spruce 'timeout 75 journalctl -u gwspaceheat -u spruce-winter-hack -f --no-pager -o short-iso --since "60 seconds ago"'
$S/roll.sh spruce check
# 11:00 ET, by hand: the branch's un-acked report.event kept the actual-spruce link flapping
ssh -n spruce 'E=~/.local/share/gridworks/scada/event; Q=~/.local/share/gridworks/scada/event-quarantine-2026-10-22-branch-rehearsal; sudo systemctl stop gwspaceheat; mkdir -p $Q; find $E -type f -exec mv {} $Q/ \; ; sudo systemctl start gwspaceheat'
# Restore: nothing was placed on the box beyond what roll.sh keeps by design
# (hardware-layout.2026-10-22-pre-roll.json, operational-params.json, the
# quarantine folder), all under ~/.config/gridworks/scada and ~/.local/share/gridworks/scada.
