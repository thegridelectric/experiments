#!/usr/bin/env bash
# The loop: a scada on the no-sieg House0 fixture with ta-plant feeding it
# over the dev broker. Needs gw-dev-rabbit and the local mosquitto up.
#
#     ./run.sh                 ten minutes
#     LOOP_SECONDS=90 ./run.sh a short trial
#     SCADA_REPO=<checkout> ./run.sh   the scada from another checkout
#
# The scada runs from a scratch XDG home under ./scratch, so it shares no
# config, data or log folder with any other scada on the laptop, and on the
# mosquitto's second listener, so it shares no local topic with one either.
set -euo pipefail
# Job control gives each service its own process group and a SIGINT it can
# hear: a background job of a script otherwise starts with SIGINT ignored.
set -m

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$(dirname "$HERE")")"
LOGS="$HERE/logs"
SCRATCH="$HERE/scratch"
SCADA_REPO="${SCADA_REPO:-$ROOT/gridworks-scada}"
FIXTURES="$SCADA_REPO/tests/config"
PAIR="gw.house0.no.sieg.hazel"
PLANT_ALIAS="d1.isone.ct.newhaven.hazel1.ta"
LOOP_SECONDS="${LOOP_SECONDS:-600}"
SECONDS_PER_REPORT=60

rm -rf "$SCRATCH"
mkdir -p "$LOGS" "$SCRATCH/config/gridworks/scada" "$SCRATCH/data" "$SCRATCH/state"
LAYOUT="$SCRATCH/config/gridworks/scada/hardware-layout.json"
stamp() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $1" >> "$LOGS/clock.txt"; }
: > "$LOGS/clock.txt"

{
    echo "gridworks-scada $(git -C "$SCADA_REPO" rev-parse --short HEAD) $(git -C "$SCADA_REPO" status --porcelain | wc -l) dirty"
    echo "gridworks-terminalasset $(git -C "$ROOT/gridworks-terminalasset" rev-parse --short HEAD) $(git -C "$ROOT/gridworks-terminalasset" status --porcelain | wc -l) dirty"
} > "$LOGS/code-under-test.txt"

# The fixture pair as deployed names. The one edit: the web server takes a
# port nothing holds, since another scada on the laptop may hold the
# fixture's.
cp "$FIXTURES/$PAIR.operational.params.json" "$SCRATCH/config/gridworks/scada/operational-params.json"
python3 - "$FIXTURES/$PAIR.layout.json" "$LAYOUT" <<'EOF'
import json, socket, sys
layout = json.load(open(sys.argv[1]))
with socket.socket() as s:
    s.bind(("", 0))
    port = s.getsockname()[1]
servers = [c["WebServer"] for c in layout["Components"] if "WebServer" in c]
assert len(servers) == 1, servers
servers[0]["Port"] = port
json.dump(layout, open(sys.argv[2], "w"), indent=2)
print(f"web server port {port}")
EOF

PLANT_PID=""
SCADA_PID=""
stop_all() {
    [ -n "$SCADA_PID" ] && kill -INT -- "-$SCADA_PID" 2>/dev/null || true
    [ -n "$PLANT_PID" ] && kill -INT -- "-$PLANT_PID" 2>/dev/null || true
    wait 2>/dev/null || true
}
trap stop_all EXIT

stamp "plant starting"
(
    cd "$ROOT/gridworks-terminalasset"
    GWTA_SERVICE_ALIAS="$PLANT_ALIAS" GWTA_G_NODE_PATH="$HERE/g.node.gt.json" \
        exec uv run --locked ta-plant --layout "$LAYOUT" --seed 20261110
) > "$LOGS/plant.log" 2>&1 &
PLANT_PID=$!
for _ in $(seq 60); do
    grep -q "consuming; " "$LOGS/plant.log" && break
    kill -0 "$PLANT_PID" 2>/dev/null || { echo "ABORT: plant exited, see $LOGS/plant.log"; exit 2; }
    sleep 0.5
done
grep -q "consuming; " "$LOGS/plant.log" || { echo "ABORT: plant never consumed, see $LOGS/plant.log"; exit 2; }
stamp "plant consuming"

stamp "scada starting"
(
    cd "$SCADA_REPO"
    XDG_CONFIG_HOME="$SCRATCH/config" XDG_DATA_HOME="$SCRATCH/data" XDG_STATE_HOME="$SCRATCH/state" \
    SCADA_LOCAL_MQTT__PORT=18831 SCADA_WEATHER_SOURCE=Sim \
        exec uv run --locked gws run --message-summary --seconds-per-report "$SECONDS_PER_REPORT"
) > "$LOGS/scada.log" 2>&1 &
SCADA_PID=$!

END=$(( $(date +%s) + LOOP_SECONDS ))
while [ "$(date +%s)" -lt "$END" ]; do
    if ! kill -0 "$SCADA_PID" 2>/dev/null; then
        stamp "scada died"
        echo "FAIL: scada died, see $LOGS/scada.log"
        exit 1
    fi
    if ! kill -0 "$PLANT_PID" 2>/dev/null; then
        stamp "plant died"
        echo "ABORT: plant died, see $LOGS/plant.log"
        exit 2
    fi
    sleep 5
done
stamp "scada alive at the end of the window"

kill -INT -- "-$SCADA_PID"
wait "$SCADA_PID" 2>/dev/null || true
SCADA_PID=""
stamp "scada stopped"
kill -INT -- "-$PLANT_PID"
wait "$PLANT_PID" 2>/dev/null || true
PLANT_PID=""
trap - EXIT
stamp "plant stopped"

set +e
(
    cd "$SCADA_REPO"
    uv run --locked python "$HERE/loop_check.py" "$SCRATCH" "$LOGS"
) > "$LOGS/loop.json" 2> "$LOGS/loop_check.stderr"
CHECK_EXIT=$?
set -e
stamp "check ended exit=$CHECK_EXIT"

if [ "$CHECK_EXIT" -eq 0 ]; then
    echo "PASS $LOGS/loop.json"
else
    echo "FAIL $LOGS/loop.json"
fi
exit "$CHECK_EXIT"
