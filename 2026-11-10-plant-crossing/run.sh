#!/usr/bin/env bash
# One crossing: ta-plant on the dev broker's AMQP face, the scada's plant
# link and a witness on its MQTT face. Needs gw-dev-rabbit up.
#
#     ./run.sh            (from anywhere; logs land in ./logs)
set -euo pipefail
# Job control gives the plant its own process group and a SIGINT it can
# hear: a background job of a script otherwise starts with SIGINT ignored.
set -m

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$(dirname "$HERE")")"
LOGS="$HERE/logs"
LAYOUT="$ROOT/gridworks-terminalasset/tests/config/gw.house0.no.sieg.hazel.layout.json"
PLANT_ALIAS="d1.isone.ct.newhaven.hazel1.ta"

mkdir -p "$LOGS"
stamp() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $1" >> "$LOGS/clock.txt"; }
: > "$LOGS/clock.txt"

{
    echo "gridworks-scada $(git -C "$ROOT/gridworks-scada" rev-parse --short HEAD) $(git -C "$ROOT/gridworks-scada" status --porcelain | wc -l) dirty"
    echo "gridworks-terminalasset $(git -C "$ROOT/gridworks-terminalasset" rev-parse --short HEAD) $(git -C "$ROOT/gridworks-terminalasset" status --porcelain | wc -l) dirty"
} > "$LOGS/code-under-test.txt"

stamp "plant starting"
(
    cd "$ROOT/gridworks-terminalasset"
    GWTA_SERVICE_ALIAS="$PLANT_ALIAS" GWTA_G_NODE_PATH="$HERE/g.node.gt.json" \
        exec uv run --locked ta-plant --layout "$LAYOUT" --flux-seconds 2 --seed 20261110
) > "$LOGS/plant.log" 2>&1 &
PLANT_PID=$!
trap 'kill -INT -- "-$PLANT_PID" 2>/dev/null || true; wait "$PLANT_PID" 2>/dev/null || true' EXIT

for _ in $(seq 60); do
    grep -q "consuming; " "$LOGS/plant.log" && break
    kill -0 "$PLANT_PID" 2>/dev/null || { echo "ABORT: plant exited, see $LOGS/plant.log"; exit 2; }
    sleep 0.5
done
grep -q "consuming; " "$LOGS/plant.log" || { echo "ABORT: plant never consumed, see $LOGS/plant.log"; exit 2; }
stamp "plant consuming"

stamp "crossing starting"
set +e
(
    cd "$ROOT/gridworks-scada"
    uv run --locked python "$HERE/crossing.py"
) > "$LOGS/crossing.json" 2> "$LOGS/crossing.stderr"
CROSSING_EXIT=$?
set -e
stamp "crossing ended exit=$CROSSING_EXIT"

sleep 1
kill -INT -- "-$PLANT_PID"
wait "$PLANT_PID" 2>/dev/null || true
trap - EXIT
stamp "plant stopped"

if [ "$CROSSING_EXIT" -eq 0 ]; then
    echo "PASS $LOGS/crossing.json"
else
    echo "FAIL $LOGS/crossing.json"
fi
exit "$CROSSING_EXIT"
