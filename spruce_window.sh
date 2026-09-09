#!/usr/bin/env bash
# Swap spruce between the deployed scada and a window scada on the
# unlimbo checkout, from the laptop, in one word each.
#
#   ./spruce_window.sh on [minutes]   stop the deployed scada + summer hack, open the
#                                     ssh -R 1885 tunnel to the laptop's gw-dev-rabbit,
#                                     boot the unlimbo window scada (default 30 min)
#   ./spruce_window.sh off            kill the window scada, copy its log to
#                                     ../scratch/, restart the deployed services
#   ./spruce_window.sh status         services, window scada, tunnel, 0x21 relay bits
#
# The window scada runs the box's ~/gridworks-scada-unlimbo checkout through
# ~/experiments/2026-08-10-ads-declared-rate/window_boot.py from ~/envs/dev.env
# (dev-broker creds only; upstream through the tunnel, admin link on the box's
# own mosquitto). Then `gwa watch spruce` from the laptop. Pull both box
# checkouts before `on` if the code moved: the box runs pushed SHAs only.
set -euo pipefail

HOST=spruce
SERVICES="spruce-summer-hack gwspaceheat gwspaceheat-restart.timer"
BOX_LOG_DIR=/tmp/spruce-window
BOOT="cd ~/gridworks-scada-unlimbo/gw_spaceheat && SCADA_PICO_CYCLER_STATE_LOGGING=true setsid nohup timeout \$((SECS + 60)) venv/bin/python ~/experiments/2026-08-10-ads-declared-rate/window_boot.py \$SECS ~/envs/dev.env > $BOX_LOG_DIR/boot.log 2>&1 < /dev/null &"
SCRATCH="$(cd "$(dirname "$0")/.." && pwd)/scratch"

tunnel_up() { pgrep -f "ssh -f -N.*-R 1885:localhost:1885 $HOST" >/dev/null; }

case "${1:-}" in
  on)
    MIN="${2:-30}"
    tunnel_up || ssh -f -N -o ExitOnForwardFailure=yes -R 1885:localhost:1885 "$HOST"
    echo "tunnel up"
    ssh "$HOST" "sudo systemctl stop $SERVICES; mkdir -p $BOX_LOG_DIR; SECS=$((MIN * 60)); $BOOT; sleep 20; git -C ~/gridworks-scada-unlimbo log --oneline -1; tail -3 $BOX_LOG_DIR/boot.log | cut -c1-140"
    echo "window scada up for $MIN min; now: gridworks-scada/gw_spaceheat/venv/bin/gwa watch spruce"
    ;;
  off)
    mkdir -p "$SCRATCH"
    ssh "$HOST" 'pkill -f "[w]indow_boot.py" || true; sleep 3'
    scp -q "$HOST:$BOX_LOG_DIR/boot.log" "$SCRATCH/spruce-window-$(date +%Y%m%d-%H%M%S).log" 2>/dev/null || echo "no boot.log to copy"
    ssh "$HOST" "rm -rf $BOX_LOG_DIR; sudo systemctl start $SERVICES; sleep 3; systemctl is-active $SERVICES | paste -sd' '"
    echo "deployed scada + summer hack back; window log in $SCRATCH"
    ;;
  status)
    tunnel_up && echo "tunnel: up" || echo "tunnel: down"
    ssh "$HOST" "echo -n 'services: '; systemctl is-active $SERVICES | paste -sd' '; pgrep -f '[w]indow_boot.py' >/dev/null && echo 'window scada: RUNNING' || echo 'window scada: down'; ~/gridworks-scada/gw_spaceheat/venv/bin/python -c \"import smbus2; r=smbus2.SMBus(1).read_byte_data(0x21,3); print('0x21 reg3 iso=%d store=%d secondary=%d' % ((r>>2)&1,(r>>4)&1,(r>>5)&1))\""
    ;;
  *)
    sed -n 2,15p "$0"; exit 1
    ;;
esac
