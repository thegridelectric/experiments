#!/usr/bin/env bash
# The battery and the storm against the box named in remote.env. The box's
# broker and FIS are used as found (FIS is restarted under systemd and its
# database's leases, auth events and mirror truncated on every FIS boot).
# Evidence lands under runs/<UTC stamp>-<box>/.
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./remote.env; set +a
FIS=../../gridworks-fleet-index-service
[ -f "$BATTERY_CERTS_DIR/ids.env" ] || ./setup-remote.sh

RUN=runs/$(date -u +%Y%m%dT%H%M)-${BATTERY_BROKER_HOST%%.*}
mkdir -p "$RUN"
uv run --project "$FIS" --with pika --with paho-mqtt --with ../../gridworks-base battery.py --run-dir "$RUN" "$@"
uv run --project "$FIS" --with pika --with ../../gridworks-base storm.py --run-dir "$RUN"
echo "evidence: $RUN/"
