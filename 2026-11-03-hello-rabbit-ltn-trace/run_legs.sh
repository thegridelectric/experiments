#!/usr/bin/env bash
# The away-and-back legs as one timeline, laptop held awake. Run from this
# folder with the capture already recording:
#   caffeinate -i ./run_legs.sh
# Starts the LTN then the scada, lets the link go Active and one 60 s ping
# round pass, stops the LTN (SIGTERM), leaves the scada alone with no peer
# for 100 s, starts the LTN again, lets it re-activate and pass a ping round,
# then stops both. Every step's wall clock goes to logs/clock.txt.
set -u
RUN="${RUN:-run3}"
HERE="$(cd "$(dirname "$0")" && pwd)"
LTN=/Users/jessica/GridWorks/gridworks-ltn
SCADA=/Users/jessica/GridWorks/gridworks-scada
clock() { echo "$1 $(date -u +%H:%M:%S)Z" >> "$HERE/logs/clock.txt"; }

(cd "$LTN" && exec uv run gwltn rabbit) > "$HERE/logs/ltn-${RUN}.log" 2>&1 &
LTN_PID=$!; clock "${RUN} ltn start"
sleep 3
(cd "$SCADA" && SCADA_GRIDWORKS_MQTT__PORT=1885 exec gw_spaceheat/venv/bin/gws run --message-summary) > "$HERE/logs/scada-${RUN}.log" 2>&1 &
SCADA_PID=$!; clock "${RUN} scada start"
sleep 95
kill -TERM "$LTN_PID"; clock "${RUN} ltn SIGTERM"
wait "$LTN_PID"; clock "${RUN} ltn exited $?"
sleep 100
(cd "$LTN" && exec uv run gwltn rabbit) > "$HERE/logs/ltn-${RUN}b.log" 2>&1 &
LTN_PID=$!; clock "${RUN} ltn start again"
sleep 95
kill -TERM "$LTN_PID"; clock "${RUN} ltn SIGTERM (final)"
wait "$LTN_PID"
kill -INT "$SCADA_PID"; clock "${RUN} scada SIGINT"
wait "$SCADA_PID"; clock "${RUN} scada exited $?"
