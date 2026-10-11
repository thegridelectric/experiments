#!/usr/bin/env bash
# The prod-broker outage drill, as run on 2026-10-11, one step per call
# so a person drives it and watches between steps:
#
#   ./runbook.sh census    # clients on the broker before the stop
#   ./runbook.sh stop      # STOPS THE PROD BROKER (asks first)
#   ./runbook.sh start     # brings it back
#   ./runbook.sh collect   # evidence into evidence/ (after the fleet is back)
#
# Pre-flight: no open alert that would swallow BrokerUnreachable; no
# house that needs LTN dispatch for the outage; the window starts after
# the prober has been quiet for a few minutes. The houses keep their
# reports and send them when the broker returns. FIS keeps running.
#
# `rmqbot` is hw1-1 (the prod broker, container rmq1 under
# ~/rmq-docker); `alerts` is the alerts box. Both are ssh config names.
# The broker log and the alerter store are read for the window
# START..END (UTC, edit before collect). Places nothing on either box.
# census, stop and start are the commands run on 2026-10-11; that day's
# evidence was read by hand over ssh, and collect is those reads written
# down as one step.
set -euo pipefail
cd "$(dirname "$0")"
START="2026-10-11T18:17:30Z"
END="2026-10-11T18:29:30Z"

case "${1:-}" in
census)
	ssh rmqbot "sudo docker exec rmq1 rabbitmqctl list_connections -q user protocol connected_at; \
		sudo docker exec rmq1 rabbitmqctl list_mqtt_connections -q client_id user"
	;;
stop)
	read -r -p "Stop the PROD broker on hw1-1? type 'stop prod': " ok
	[ "$ok" = "stop prod" ] || exit 1
	ssh rmqbot "date -u; cd ~/rmq-docker && sudo docker compose stop"
	;;
start)
	ssh rmqbot "date -u; cd ~/rmq-docker && sudo docker compose start"
	;;
collect)
	mkdir -p evidence
	ssh rmqbot "sudo docker exec rmq1 rabbitmqctl list_connections -q user protocol connected_at" \
		| { printf 'user\tprotocol\tconnected_at\n'; cat; } >evidence/amqp-connections-after.tsv
	ssh rmqbot "sudo docker exec rmq1 rabbitmqctl list_mqtt_connections -q client_id user" \
		| { printf 'client_id\tuser\n'; cat; } >evidence/mqtt-connections-after.tsv
	# Raw log to a scratch file: it holds public IPs and this repo is
	# public. Reduce it by hand to listener, startup and accept lines,
	# replace each IP with a stable token (ip-A, ip-B, ...), add the
	# provenance header, and save as evidence/broker-log-reduced.txt.
	raw=$(mktemp "${TMPDIR:-/tmp}/rmq1-log.XXXXXX")
	ssh rmqbot "sudo docker logs --since $START --until $END rmq1 2>&1" \
		| sed 's/\x1b\[[0-9;]*m//g' >"$raw"
	echo "raw broker log: $raw (reduce it, then delete it)"
	# The alerter store's alerts rows for the window, read-only.
	ssh alerts "sqlite3 -readonly -json ~/.local/share/gridworks/alerter/alerter.sqlite \
		\"select payload, resolved_payload from alerts where raised_ms between \
		$(($(date -j -u -f %Y-%m-%dT%H:%M:%SZ "$START" +%s) * 1000)) and \
		$(($(date -j -u -f %Y-%m-%dT%H:%M:%SZ "$END" +%s) * 1000))\"" \
		>evidence/alerter-store-alerts.raw.json
	echo "decode the payload columns to JSON objects into evidence/alerter-store-alerts.json"
	;;
*)
	sed -n '2,8p' "$0"
	exit 1
	;;
esac
