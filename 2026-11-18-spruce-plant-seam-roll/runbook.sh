#!/usr/bin/env bash
# spruce-plant-seam-roll, 2026-11-18. Commands as run, laptop, ET times.
# Pre-roll: spruce on main 7e8e52f4, gwspaceheat active, log clean (evidence/pre-roll-tail.log).

S=hw1-isone-me-versant-keene-spruce
# 19:10 ET  box service log, followed for the window
ssh -n spruce 'timeout 3300 journalctl -u gwspaceheat -f --no-pager -o short-iso --since "30 seconds ago"' > evidence/spruce-journal.log 2>&1 &
# 19:12 ET  tap broker, spruce scada + LTN, both directions (a first attempt bound '#.spruce.#', which never matches a hyphenated alias segment, and was discarded)
(cd .. && uv run python tap_listen.py -k "gw.$S-scada.#" -k "gw.$S.#" -k "gw.*.to.$S-scada.#" -k "gw.*.to.$S.#" --out 2026-11-18-spruce-plant-seam-roll/evidence --seconds 3300) > evidence/tap-stdout.log 2>&1 &
# <time>  the roll, run by Jessica from gridworks-scada
# scripts/roll.sh spruce to jm/plant-seam
