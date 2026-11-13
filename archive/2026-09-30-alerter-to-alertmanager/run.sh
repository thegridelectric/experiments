#!/usr/bin/env bash
# The alerter-to-alertmanager witness: Alertmanager + webhook receiver +
# alerter + tap (fresh store, sped-up timing, one tracked house) + the
# mock scada from 2026-09-15-alerter-no-data, with the alerter and tap
# restarted while the alert is open. Logs land in a run dir under $TMPDIR
# (printed).
#
# Needs: gw-dev-rabbit, the dev registry (gnr api + gnr rabbit), the
# alerter's .env, and the Alertmanager binaries (ALERTMANAGER_BIN /
# AMTOOL_BIN, default: on PATH). Optional Telegram receiver:
# TELEGRAM_CHAT_ID + TELEGRAM_TOKEN_FILE.
set -euo pipefail
cd "$(dirname "$0")"
ALERTER=../../gridworks-alerter
NO_DATA=../2026-09-15-alerter-no-data
AM=${ALERTMANAGER_BIN:-alertmanager}
AMTOOL=${AMTOOL_BIN:-amtool}
AM_URL=http://127.0.0.1:9093
RUN=$(mktemp -d "${TMPDIR:-/tmp}/alerter-to-alertmanager.XXXXXX")
echo "run dir: $RUN"
[ -f "$ALERTER/.env" ] || { echo "missing $ALERTER/.env"; exit 1; }
set -a; source "$ALERTER/.env"; set +a
export PYTHONPATH=../src
export XDG_DATA_HOME="$RUN/data" XDG_STATE_HOME="$RUN/state"
export GWALERTER_NO_DATA_SILENCE_S=30 GWALERTER_DETECTOR_TICK_S=2
export GWALERTER_FLEET_ROOTS=d1.isone.me.versant.keene.spruce
export GWALERTER_ALERTMANAGER_URL=$AM_URL GWALERTER_TAP_RESEND_S=20

cp alertmanager.yml "$RUN/alertmanager.yml"
if [ -n "${TELEGRAM_CHAT_ID:-}" ] && [ -f "${TELEGRAM_TOKEN_FILE:-/nonexistent}" ]; then
  cat >> "$RUN/alertmanager.yml" <<YAML
    telegram_configs:
      - bot_token_file: $TELEGRAM_TOKEN_FILE
        chat_id: $TELEGRAM_CHAT_ID
        send_resolved: true
        message: '{{ range .Alerts }}{{ .Status | toUpper }} {{ .Labels.alertname }} at {{ .Annotations.house }}: {{ .Annotations.summary }} ({{ .Annotations.about }})
{{ end }}'
YAML
  echo "telegram receiver on, chat $TELEGRAM_CHAT_ID"
fi
"$AMTOOL" check-config "$RUN/alertmanager.yml"

stop() { pkill -TERM -P "$1" 2>/dev/null || true; kill -TERM "$1" 2>/dev/null || true; wait "$1" 2>/dev/null || true; }
alerter() { (cd "$ALERTER" && exec uv run gwalerter rabbit > "$RUN/$1.log" 2>&1) & echo $!; }
tap()     { (cd "$ALERTER" && exec uv run gwalerter tap    > "$RUN/$1.log" 2>&1) & echo $!; }

"$AM" --config.file="$RUN/alertmanager.yml" --storage.path="$RUN/am-data" \
  --web.listen-address=127.0.0.1:9093 --cluster.listen-address="" > "$RUN/alertmanager.log" 2>&1 &
AMPID=$!
python3 webhook_receiver.py 9094 > "$RUN/receiver.log" 2>&1 &
RECV=$!
sleep 3
echo "$(date +%H:%M:%S) step 1: hand alert via amtool"
"$AMTOOL" --alertmanager.url=$AM_URL alert add alertname=HandCheck category=Test subject=run.sh --annotation=summary="amtool hand alert"
sleep 7
A1=$(alerter alerter-1); sleep 3
T1=$(tap tap-1); sleep 4
echo "$(date +%H:%M:%S) step 2: alerter + tap up; mock scada starts"
uv run --project "$ALERTER" python "$NO_DATA/mock_scada.py" --cadence 5 --talk 20 --quiet 60 --resume 20 > "$RUN/mock.log" 2>&1 &
MOCK=$!
# talk 0-20, quiet 20-80 (raise ~50), resume 80-100.
sleep 60
echo "$(date +%H:%M:%S) step 3 check: alertmanager alerts while firing"
"$AMTOOL" --alertmanager.url=$AM_URL alert query -o extended | tee "$RUN/amtool-firing.txt"
echo "$(date +%H:%M:%S) step 5: restart alerter and tap with the alert open"
stop "$A1"; stop "$T1"
A2=$(alerter alerter-2); sleep 2; T2=$(tap tap-2)
wait "$MOCK"
sleep 15
echo "$(date +%H:%M:%S) step 4 check: alertmanager alerts after resume"
"$AMTOOL" --alertmanager.url=$AM_URL alert query -o extended | tee "$RUN/amtool-resolved.txt"
stop "$A2"; stop "$T2"; stop "$RECV"; stop "$AMPID"
echo "--- receiver"; cat "$RUN/receiver.log"
echo "--- tap logs"; grep -h "Firing\|Resolved\|Open at boot\|Bound\|Dropped\|ERROR\|WARNING" "$RUN"/tap-*.log
echo "--- alerter logs"; grep -h "gw.alert\|not sent\|ERROR" "$RUN"/state/gridworks/alerter/log/*.log
echo "store: $RUN/data/gridworks/alerter/alerter.sqlite (archive beside the logs; emit_instances.py reads it)"
