#!/usr/bin/env bash
# The alerter-broker-down witness: alerter + tap + prober (fresh store,
# sped-up timing, one tracked house) + the mock scada from
# 2026-09-15-alerter-no-data, with the dev broker STOPPED for four
# minutes in the middle, against Opsgenie itself. Logs land in a run dir
# under $TMPDIR (printed).
#
# Each long-lived process runs under a restart loop, which is what
# systemd's Restart=always does on the box: the alerter's gwbase actor
# reconnects by itself, but the tap's consumer and the mock's pika
# channel die with the broker and come back when it does.
#
# Needs: gw-dev-rabbit (docker), the dev registry (gnr api + gnr rabbit),
# the alerter's .env, and the Opsgenie credentials to page with:
# OPSGENIE_API_KEY and OPSGENIE_TEAM_ID (the one team, GridWorks Dev;
# the run pages whoever is on call). Optional OPSGENIE_URL for an EU
# account.
set -euo pipefail
cd "$(dirname "$0")"
ALERTER=../../gridworks-alerter
NO_DATA=../2026-09-15-alerter-no-data
# The Opsgenie credentials come from the experiments .env (gitignored,
# `OPSGENIE_API_KEY`, `OPSGENIE_TEAM_ID`) or the environment.
[ -f ../.env ] && { set -a; source ../.env; set +a; }
: "${OPSGENIE_API_KEY:?set OPSGENIE_API_KEY}" "${OPSGENIE_TEAM_ID:?set OPSGENIE_TEAM_ID}"
OG_URL=${OPSGENIE_URL:-https://api.opsgenie.com}
RUN=$(mktemp -d "${TMPDIR:-/tmp}/alerter-broker-down.XXXXXX")
echo "run dir: $RUN"
[ -f "$ALERTER/.env" ] || { echo "missing $ALERTER/.env"; exit 1; }
set -a; source "$ALERTER/.env"; set +a
export PYTHONPATH=../src
export XDG_DATA_HOME="$RUN/data" XDG_STATE_HOME="$RUN/state"
# NoData at 120 s so a 240 s outage would page without the hold; the
# prober raises after 3 probes 10 s apart; the tap reconciles every 20 s.
export GWALERTER_NO_DATA_SILENCE_S=120 GWALERTER_DETECTOR_TICK_S=2
export GWALERTER_FLEET_ROOTS=d1.isone.me.versant.keene.spruce
export GWALERTER_OPSGENIE_API_KEY=$OPSGENIE_API_KEY GWALERTER_OPSGENIE_TEAM_ID=$OPSGENIE_TEAM_ID
export GWALERTER_OPSGENIE_URL=$OG_URL GWALERTER_TAP_RECONCILE_S=20
export GWALERTER_PROBE_AMQP_URL=$GWALERTER_RABBIT__URL
export GWALERTER_PROBE_MQTT_HOST=localhost GWALERTER_PROBE_MQTT_PORT=1885 GWALERTER_PROBE_MQTT_TLS=false
export GWALERTER_PROBE_INTERVAL_S=10 GWALERTER_PROBE_FAILURES_TO_RAISE=3

stamp() { date +%H:%M:%S; }
stop() { pkill -TERM -P "$1" 2>/dev/null || true; kill -TERM "$1" 2>/dev/null || true; wait "$1" 2>/dev/null || true; }
# A restart loop around one gwalerter subcommand, logging each restart.
loop() { # name subcommand
  ( cd "$ALERTER" && while true; do
      uv run gwalerter "$2" || echo "$(stamp) $1 exited $?; restarting in 3 s"
      sleep 3
    done ) >> "$RUN/$1.log" 2>&1 &
  echo $!
}
mock_loop() {
  ( while true; do
      uv run --project "$ALERTER" python "$NO_DATA/mock_scada.py" --cadence 5 --talk 900 --quiet 0 --resume 0 \
        || echo "$(stamp) mock exited $?; restarting in 3 s"
      sleep 3
    done ) >> "$RUN/mock.log" 2>&1 &
  echo $!
}
# Opsgenie's view of the run's alerts, newest first: raw listing saved,
# typed view printed (../opsgenie_listing.py).
og_query() {
  curl -s -H "Authorization: GenieKey $OPSGENIE_API_KEY" \
    "$OG_URL/v2/alerts?query=source%3A${GWALERTER_SERVICE_ALIAS}&limit=10&sort=createdAt&order=desc" \
    > "$RUN/$1.json"
  uv run --project "$ALERTER" python ../opsgenie_listing.py "$RUN/$1.json" | tee "$RUN/$1.txt"
}

docker inspect -f '{{.State.Running}}' gw-dev-rabbit | grep -q true || { echo "gw-dev-rabbit is not running"; exit 1; }
A=$(loop alerter rabbit); sleep 3
T=$(loop tap tap); sleep 2
P=$(loop prober probe); sleep 2
M=$(mock_loop)
echo "$(stamp) step 1: alerter, tap, prober and mock up; 60 s of normal traffic"
sleep 60
echo "$(stamp) step 2: STOPPING gw-dev-rabbit for 240 s"
docker stop gw-dev-rabbit > /dev/null
sleep 90
echo "$(stamp) step 2 check: opsgenie while the broker is down (two BrokerUnreachable open, no NoData)"
og_query opsgenie-down
sleep 150
echo "$(stamp) step 3: STARTING gw-dev-rabbit"
docker start gw-dev-rabbit > /dev/null
sleep 75
echo "$(stamp) step 3 check: opsgenie after the broker is back (both resolved)"
og_query opsgenie-back
echo "$(stamp) step 4: 150 s past the broker's return, past the NoData threshold; no NoData expected"
sleep 150
og_query opsgenie-final
stop "$M"; stop "$P"; stop "$T"; stop "$A"
pkill -f "gwalerter (rabbit|tap|probe)" 2>/dev/null || true
pkill -f mock_scada.py 2>/dev/null || true
echo "--- prober log"; grep -h "Firing\|Resolved\|failed\|Probing" "$RUN"/prober.log
echo "--- tap log"; grep -h "Firing\|Resolved\|Reconcile\|Bound\|exited\|ERROR" "$RUN"/tap.log
echo "--- alerter file log (NoData lines, expected none)"; grep -h "NoData" "$RUN"/state/gridworks/alerter/log/*.log || echo "(no NoData)"
echo "store: $RUN/data/gridworks/alerter/alerter.sqlite (archive beside the logs)"
