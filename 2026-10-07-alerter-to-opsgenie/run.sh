#!/usr/bin/env bash
# The alerter-to-opsgenie witness: alerter + tap (fresh store, sped-up
# timing, one tracked house) + the mock scada from
# 2026-09-15-alerter-no-data, with the alerter and tap restarted while
# the alert is open, against Opsgenie itself. Logs land in a run dir
# under $TMPDIR (printed).
#
# Needs: gw-dev-rabbit, the dev registry (gnr api + gnr rabbit), the
# alerter's .env, and the Opsgenie credentials to page with:
# OPSGENIE_API_KEY (an Alert API integration key) and OPSGENIE_TEAM_ID
# (the one team, GridWorks Dev; the run pages whoever is on call).
# Optional OPSGENIE_URL for an EU account.
set -euo pipefail
cd "$(dirname "$0")"
ALERTER=../../gridworks-alerter
NO_DATA=../2026-09-15-alerter-no-data
# The Opsgenie credentials come from the experiments .env (gitignored,
# `OPSGENIE_API_KEY`, `OPSGENIE_TEAM_ID`) or the environment.
[ -f ../.env ] && { set -a; source ../.env; set +a; }
: "${OPSGENIE_API_KEY:?set OPSGENIE_API_KEY}" "${OPSGENIE_TEAM_ID:?set OPSGENIE_TEAM_ID}"
OG_URL=${OPSGENIE_URL:-https://api.opsgenie.com}
RUN=$(mktemp -d "${TMPDIR:-/tmp}/alerter-to-opsgenie.XXXXXX")
echo "run dir: $RUN"
[ -f "$ALERTER/.env" ] || { echo "missing $ALERTER/.env"; exit 1; }
set -a; source "$ALERTER/.env"; set +a
export PYTHONPATH=../src
export XDG_DATA_HOME="$RUN/data" XDG_STATE_HOME="$RUN/state"
export GWALERTER_NO_DATA_SILENCE_S=30 GWALERTER_DETECTOR_TICK_S=2
export GWALERTER_FLEET_ROOTS=d1.isone.me.versant.keene.spruce
export GWALERTER_OPSGENIE_API_KEY=$OPSGENIE_API_KEY GWALERTER_OPSGENIE_TEAM_ID=$OPSGENIE_TEAM_ID
export GWALERTER_OPSGENIE_URL=$OG_URL GWALERTER_TAP_RECONCILE_S=20

stop() { pkill -TERM -P "$1" 2>/dev/null || true; kill -TERM "$1" 2>/dev/null || true; wait "$1" 2>/dev/null || true; }
alerter() { (cd "$ALERTER" && exec uv run gwalerter rabbit > "$RUN/$1.log" 2>&1) & echo $!; }
tap()     { (cd "$ALERTER" && exec uv run gwalerter tap    > "$RUN/$1.log" 2>&1) & echo $!; }
# Opsgenie's view of the run's alerts: every alert the alerter's source
# raised, open or closed, newest first. The raw listing is the evidence
# ($1.json); the typed view printed beside it is derived (../opsgenie_listing.py).
og_query() {
  curl -s -H "Authorization: GenieKey $OPSGENIE_API_KEY" \
    "$OG_URL/v2/alerts?query=source%3A${GWALERTER_SERVICE_ALIAS}&limit=10&sort=createdAt&order=desc" \
    > "$RUN/$1.json"
  uv run --project "$ALERTER" python ../opsgenie_listing.py "$RUN/$1.json" | tee "$RUN/$1.txt"
}

A1=$(alerter alerter-1); sleep 3
T1=$(tap tap-1); sleep 4
echo "$(date +%H:%M:%S) step 1: alerter + tap up; mock scada starts"
uv run --project "$ALERTER" python "$NO_DATA/mock_scada.py" --cadence 5 --talk 20 --quiet 60 --resume 20 > "$RUN/mock.log" 2>&1 &
MOCK=$!
# talk 0-20, quiet 20-80 (raise ~50), resume 80-100.
sleep 60
echo "$(date +%H:%M:%S) step 2 check: opsgenie while firing"
og_query opsgenie-firing
echo "$(date +%H:%M:%S) step 4: restart alerter and tap with the alert open"
stop "$A1"; stop "$T1"
A2=$(alerter alerter-2); sleep 2; T2=$(tap tap-2)
wait "$MOCK"
sleep 15
echo "$(date +%H:%M:%S) step 3 check: opsgenie after resume"
og_query opsgenie-resolved
stop "$A2"; stop "$T2"
echo "--- tap logs"; grep -h "Firing\|Resolved\|Reconcile\|Bound\|Dropped\|ERROR\|WARNING" "$RUN"/tap-*.log
echo "--- alerter logs"; grep -h "gw.alert\|not sent\|ERROR" "$RUN"/state/gridworks/alerter/log/*.log
echo "store: $RUN/data/gridworks/alerter/alerter.sqlite (archive beside the logs)"
