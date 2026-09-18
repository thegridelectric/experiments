#!/usr/bin/env bash
# gwalert no-data page runbook: stop the deployed spruce scada, wait for
# gwalert to page Opsgenie, restart the scada, capture the evidence.
# STOPS A LIVE HOUSE'S SCADA for ~15 minutes; the restart timer is
# stopped with it so the watchdog does not undo the window.
# The 2026-09-16 run was driven by hand with these same commands.
set -euo pipefail
cd "$(dirname "$0")"
HOUSE=spruce
SERVICES="gwspaceheat gwspaceheat-restart.timer"
ALIAS="$(date +%Y-%m-%d)-$HOUSE-no_data"
OG='cd ~/gridworks-alerts && set -a && . ./.env && set +a && curl -s -G https://api.opsgenie.com/v2/alerts -H "Authorization: GenieKey $GWALERT_OPSGENIE_API_KEY"'
mkdir -p evidence

echo "== open Opsgenie alerts with alias $ALIAS (must be none)"
ssh alerts "$OG --data-urlencode 'query=alias:$ALIAS AND status:open'" | python3 -c 'import sys,json; d=json.load(sys.stdin)["data"]; print(len(d), "open"); sys.exit(1 if d else 0)'

SINCE=$(date -u +"%Y-%m-%d %H:%M")
echo "== stop $SERVICES on $HOUSE at $(date -u +%H:%M:%SZ)"
ssh $HOUSE "sudo systemctl stop $SERVICES; systemctl is-active $SERVICES | paste -sd' '" || true

echo "== poll gwalert journal for the page (up to 25 min)"
for _ in $(seq 1 50); do
    if ssh alerts "journalctl -u gridworks-alerts --since '$SINCE' --no-pager -q | grep -q '\[ALERT\] $HOUSE'"; then break; fi
    sleep 30
done
ssh alerts "journalctl -u gridworks-alerts --since '$SINCE' --no-pager -q | grep -E '\[ALERT\]|Opsgenie'"

echo "== restart $SERVICES at $(date -u +%H:%M:%SZ)"
ssh $HOUSE "sudo systemctl start $SERVICES; systemctl is-active $SERVICES | paste -sd' '"

echo "== wait for fresh $HOUSE data (up to 10 min)"
for _ in $(seq 1 20); do
    if ssh alerts "journalctl -u gridworks-alerts --since '$SINCE' --no-pager -q | grep -q '$HOUSE: Found data up to 0'"; then break; fi
    sleep 30
done

echo "== capture evidence"
UNTIL=$(date -u -v+5M +"%Y-%m-%d %H:%M" 2>/dev/null || date -u -d '+5 min' +"%Y-%m-%d %H:%M")
{ echo "# EXTERNAL EVIDENCE (journald). Captured $(date -u +%F) over ssh from the alerts box (clock UTC)."
  ssh alerts "journalctl -u gridworks-alerts --since '$SINCE' --until '$UNTIL' --no-pager -q -o short-iso"; } > evidence/alerts-journal.log
{ echo "# EXTERNAL EVIDENCE (journald). Captured $(date -u +%F) over ssh from the $HOUSE pi (clock America/New_York)."
  echo "# Scada checkout: $(ssh $HOUSE 'git -C ~/gridworks-scada log --oneline -1; git -C ~/gridworks-scada branch --show-current' | paste -sd' ')"
  ssh $HOUSE "sudo journalctl -u gwspaceheat --since '-1h' --no-pager -q -o short-iso | grep -E 'systemd\[1\]'"; } > evidence/spruce-journal.log
{ echo "# EXTERNAL EVIDENCE (Opsgenie REST API, point-in-time). Captured $(date -u +%F) from the alerts box with gwalert's key."
  ssh alerts "$OG --data-urlencode 'query=alias:$ALIAS'" | python3 -m json.tool; } > evidence/opsgenie-alert.txt
echo "done; now: uv run python emit_instances.py"
