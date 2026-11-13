#!/usr/bin/env bash
# The whole battery: rig check → broker up → battery (which runs FIS) → storm.
# Evidence lands under runs/<UTC stamp>/.
set -euo pipefail
cd "$(dirname "$0")"
FIS=../../gridworks-fleet-index-service
[ -f certs/out/ids.env ] || ./setup.sh
[ -f ../../gridworks-infra/rmqbot/auth-mechanism/rabbitmq_auth_mechanism_gridworks-0.1.0.ez ] \
  || { echo "build the mechanism first: (cd ../../gridworks-infra/rmqbot/auth-mechanism && ./build.sh)"; exit 1; }

# Every exec runs as the rabbitmq user: an exec as root before the server has
# written its Erlang cookie creates a root-owned cookie the server then cannot
# read, and the broker crash-loops on `.erlang.cookie: eacces`.
docker compose up -d
for _ in $(seq 1 30); do
  docker exec -u rabbitmq fis-gate-broker rabbitmq-diagnostics -q check_running >/dev/null 2>&1 && break; sleep 2
done
docker exec -u rabbitmq fis-gate-broker rabbitmq-plugins list -e -m 2>/dev/null | grep -E 'auth_backend_http|gridworks' | sed 's/^/plugin: /'

RUN=runs/$(date -u +%Y%m%dT%H%M)
mkdir -p "$RUN"
uv run --project "$FIS" --with pika --with paho-mqtt --with ../../gridworks-base battery.py --run-dir "$RUN" "$@"
uv run --project "$FIS" --with pika --with ../../gridworks-base storm.py --run-dir "$RUN"
echo "evidence: $RUN/"
