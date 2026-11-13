#!/usr/bin/env bash
# Swap beech between the deployed scada and a window scada on the
# unlimbo checkout, from the laptop, in one word each. The beech copy of
# ../spruce_window.sh: no summer hack on beech, a 5-minute default, and
# the status line reads the second Krida's port word (relays 17-32).
#
#   ./beech_window.sh on             stop the deployed scada + its restart timer, open the
#                                    ssh -R 1885 tunnel to the laptop's gw-dev-rabbit,
#                                    place the window layout pair, boot the window scada.
#                                    NOT self-terminating in practice: the bound is 4 h as a
#                                    safety net; the experiment (heat_call.py, then `off`)
#                                    ends the window.
#   ./beech_window.sh off            kill the window scada, copy its boot log + its pending
#                                    report events (unacked: no LTN on the dev broker) into
#                                    instances/, restart the deployed service + timer
#   ./beech_window.sh status         services, window scada, tunnel, both Krida port words
#
# The window scada runs the box's ~/gridworks-scada-unlimbo checkout through
# ~/experiments/2026-08-10-ads-declared-rate/window_boot.py from ~/envs/dev.env
# (dev-broker creds only; upstream through the tunnel, admin link on the box's
# own mosquitto). The layout pair comes from this folder's instances/ via the
# box's ~/experiments clone (pull before `on` if it moved: pushed SHAs only).
# Then `gwa watch beech` from the laptop (admin-config registers beech's
# mosquitto over tailscale).
set -euo pipefail

HOST=beech
SERVICES="gwspaceheat gwspaceheat-restart.timer"
BOX_LOG_DIR=/tmp/beech-window
EXP=experiments/2026-09-10-beech-krida-witness
BOX_INSTANCES="~/$EXP/instances"
BOX_CONFIG="~/.config/gridworks/scada-experiment"
BOX_EVENTS="~/.local/share/gridworks/scada-experiment/event"
BOOT="cd ~/gridworks-scada-unlimbo/gw_spaceheat && setsid nohup timeout \$((SECS + 60)) venv/bin/python ~/experiments/2026-08-10-ads-declared-rate/window_boot.py \$SECS ~/envs/dev.env > $BOX_LOG_DIR/boot.log 2>&1 < /dev/null &"
HERE="$(cd "$(dirname "$0")" && pwd)"
# PCF8575: one 16-bit port word, read as two bytes (P0-7, P10-17); a low bit is an energized relay.
PORTS="for a in 0x20 0x21; do echo -n \"\$a: \"; sudo i2ctransfer -y 1 r2@\$a; done"

tunnel_up() { pgrep -f "ssh -f -N.*-R 1885:localhost:1885 $HOST" >/dev/null; }

case "${1:-}" in
  on)
    MIN="${2:-240}"
    tunnel_up || ssh -f -N -o ExitOnForwardFailure=yes -R 1885:localhost:1885 "$HOST"
    echo "tunnel up"
    ssh "$HOST" "mkdir -p $BOX_CONFIG && cp $BOX_INSTANCES/beech-window-gw.house0.layout-000.json $BOX_CONFIG/hardware-layout.json && cp $BOX_INSTANCES/beech-window-gw.house0.operational.params-000.json $BOX_CONFIG/operational-params.json && sha256sum $BOX_CONFIG/*.json | cut -c1-16,66-"
    ssh "$HOST" "sudo systemctl stop $SERVICES; sleep 2; echo 'port words before boot:'; $PORTS; mkdir -p $BOX_LOG_DIR; SECS=$((MIN * 60)); $BOOT sleep 25; git -C ~/gridworks-scada-unlimbo log --oneline -1; tail -3 $BOX_LOG_DIR/boot.log | cut -c1-140"
    echo "window scada up (bound $MIN min); now: ../../gridworks-scada/gw_spaceheat/venv/bin/python heat_call.py drive-<stamp>.log broker-<stamp>.jsonl"
    ;;
  off)
    ssh "$HOST" 'pkill -f "[w]indow_boot.py" || true; sleep 3'
    STAMP=$(date +%Y%m%d-%H%M%S)
    scp -q "$HOST:$BOX_LOG_DIR/boot.log" "$HERE/boot-$STAMP.log" 2>/dev/null || echo "no boot.log to copy"
    mkdir -p "$HERE/instances"
    scp -q "$HOST:$BOX_EVENTS/*/*.json" "$HERE/instances/" 2>/dev/null && ssh "$HOST" "rm -rf $BOX_EVENTS/*" || echo "no pending events in $BOX_EVENTS"
    ssh "$HOST" "echo 'port words after window:'; $PORTS; rm -rf $BOX_LOG_DIR; sudo systemctl start $SERVICES; sleep 3; systemctl is-active $SERVICES | paste -sd' '"
    echo "deployed scada + timer back; window log at $HERE/boot-$STAMP.log; events in instances/"
    ;;
  status)
    tunnel_up && echo "tunnel: up" || echo "tunnel: down"
    ssh "$HOST" "echo -n 'services: '; systemctl is-active $SERVICES | paste -sd' '; pgrep -f '[w]indow_boot.py' >/dev/null && echo 'window scada: RUNNING' || echo 'window scada: down'; $PORTS"
    ;;
  *)
    sed -n 2,14p "$0"; exit 1
    ;;
esac
