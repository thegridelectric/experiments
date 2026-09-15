#!/usr/bin/env bash
# The NoData witness runbook: watcher + alerter (fresh store, sped-up
# timing, one tracked house) + mock scada, with the alerter restarted
# while the alert is open. Logs land in a run dir under $TMPDIR
# (printed); instances/ gets the witnessed alert words.
#
# Background jobs of a non-interactive shell ignore SIGINT, so the stop
# step uses SIGTERM (what systemd sends), children first.
set -euo pipefail
cd "$(dirname "$0")"
ALERTER=../../gridworks-alerter
RUN=$(mktemp -d "${TMPDIR:-/tmp}/alerter-no-data.XXXXXX")
echo "run dir: $RUN"
rm -f instances/*.json
[ -f "$ALERTER/.env" ] || { echo "missing $ALERTER/.env (copy template.env, set the broker URL)"; exit 1; }
set -a; source "$ALERTER/.env"; set +a
export PYTHONPATH=../src   # this repo's sema snapshot, for the harness scripts
export XDG_DATA_HOME="$RUN/data" XDG_STATE_HOME="$RUN/state"
export GWALERTER_NO_DATA_SILENCE_S=30 GWALERTER_DETECTOR_TICK_S=2
export GWALERTER_FLEET_ROOTS=d1.isone.me.versant.keene.spruce

stop() {  # $1 = pid of a `uv run` wrapper
  pkill -TERM -P "$1" 2>/dev/null || true
  kill -TERM "$1" 2>/dev/null || true
  wait "$1" 2>/dev/null || true
}
alerter() {  # $1 = log name
  (cd "$ALERTER" && exec uv run gwalerter rabbit > "$RUN/$1.log" 2>&1) &
  echo $!
}

uv run --project "$ALERTER" python watcher.py instances > "$RUN/watcher.log" 2>&1 &
WATCHER=$!
sleep 2
A1=$(alerter alerter-1)
sleep 5
T0=$(date +%s)
uv run --project "$ALERTER" python mock_scada.py --cadence 5 --talk 20 --quiet 60 --resume 20 \
  > "$RUN/mock.log" 2>&1 &
MOCK=$!
# talk 0-20, quiet 20-80 (raise expected ~50), resume 80-100.
sleep 65
echo "$(date +%H:%M:%S) stopping alerter 1 with the alert open"; stop "$A1"
A2=$(alerter alerter-2)
echo "$(date +%H:%M:%S) alerter 2 started"
wait "$MOCK"
sleep 4
stop "$A2"; stop "$WATCHER"
echo "--- mock"; grep -v "report.event from" "$RUN/mock.log"
echo "--- watcher"; cat "$RUN/watcher.log"
echo "--- alerter logs"; grep -h "gw.house\|not sent\|ERROR" "$RUN"/state/gridworks/alerter/log/*.log
echo "--- instances"; ls -1 instances
