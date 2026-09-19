#!/usr/bin/env bash
# Swap a house between its deployed plant control and a window scada on the
# unlimbo checkout, from the laptop, in one word each. spruce_window.sh and
# beech_window.sh call this with their house.
#
#   ./house_window.sh <house> on [minutes]   check the box is ready (below), open the
#                                            ssh -R 1885 tunnel to the laptop's
#                                            gw-dev-rabbit (observation only; the window
#                                            opens without it), stop the house's running
#                                            plant services, boot the window scada.
#                                            No minutes = a standing window until `off`.
#   ./house_window.sh <house> off            kill the window scada, copy its log to
#                                            ../scratch/, confirm the stopped services
#                                            are back
#   ./house_window.sh <house> status         services, window scada, tunnel, relay bits
#
# <house> is spruce or beech (the ssh host of the same name).
#
# `on` refuses unless:
#   - the box's window pair (~/.config/gridworks/scada-experiment/) is
#     byte-identical to ../tlayouts/output/<house>/ (put_layout.sh <house> check).
#     This script never writes a layout; put_layout.sh does.
#   - the laptop's scada head is pushed and the box's ~/gridworks-scada-unlimbo
#     checkout is at it (the box runs pushed SHAs only; pull on the box).
#   - no window scada is already running.
#
# The services running at `on` are recorded on the box and stopped. The box
# starts exactly those again when the window scada exits for any reason: the
# minutes bound, a crash, or `off`. A service that was not running stays off.
#
# The window scada runs through
# ~/experiments/2026-08-10-ads-declared-rate/window_boot.py from ~/envs/dev.env
# (dev-broker creds only; upstream through the tunnel, admin link on the box's
# own mosquitto). Then `gwa watch <house>` from the laptop.
set -euo pipefail

HOUSE="${1:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
case "$HOUSE" in
  spruce)
    SERVICES="spruce-winter-hack gwspaceheat gwspaceheat-restart.timer"
    BOOT_ENV="SCADA_PICO_CYCLER_STATE_LOGGING=true"
    # gw108 relay board 0x21, output register 3
    RELAYS="~/gridworks-scada/gw_spaceheat/venv/bin/python -c \"import smbus2; r=smbus2.SMBus(1).read_byte_data(0x21,3); print('0x21 reg3 iso=%d store=%d secondary=%d' % ((r>>2)&1,(r>>4)&1,(r>>5)&1))\""
    ;;
  beech)
    SERVICES="gwspaceheat gwspaceheat-restart.timer"
    BOOT_ENV=""
    # PCF8575: one 16-bit port word per Krida, read as two bytes; a low bit is an energized relay
    RELAYS="for a in 0x20 0x21; do echo -n \"\$a: \"; sudo i2ctransfer -y 1 r2@\$a; done"
    ;;
  *) sed -n 2,17p "$0"; exit 1 ;;
esac

BOX_LOG_DIR="/tmp/$HOUSE-window"
STOPPED="$BOX_LOG_DIR/stopped-services"
SCRATCH="$HERE/../scratch"
SCADA="$HERE/../gridworks-scada"

tunnel_up() { pgrep -f "ssh -f -N.*-R 1885:localhost:1885 $HOUSE" >/dev/null; }
window_up() { ssh "$HOUSE" 'pgrep -f "[w]indow_boot.py" >/dev/null'; }

case "${2:-}" in
  on)
    MIN="${3:-0}"
    [[ "$MIN" =~ ^[0-9]+$ ]] || { echo "minutes must be a whole number"; exit 1; }
    "$HERE/put_layout.sh" "$HOUSE" check || { echo "refusing: put the gen output first (./put_layout.sh $HOUSE <change>)"; exit 1; }
    HEAD="$(git -C "$SCADA" rev-parse HEAD)"
    [ -z "$(git -C "$SCADA" log --oneline '@{u}..')" ] || { echo "refusing: the laptop's scada head ${HEAD:0:8} is not pushed"; exit 1; }
    BOX_HEAD="$(ssh "$HOUSE" 'git -C ~/gridworks-scada-unlimbo rev-parse HEAD')"
    [ "$BOX_HEAD" = "$HEAD" ] || { echo "refusing: $HOUSE unlimbo checkout is at ${BOX_HEAD:0:8}, the laptop's scada head is ${HEAD:0:8}; on the box: git -C ~/gridworks-scada-unlimbo pull --ff-only"; exit 1; }
    if window_up; then echo "refusing: a window scada is already running on $HOUSE"; exit 1; fi
    # The tunnel carries the upstream (LTN) link to the laptop's dev broker for
    # observation only; commands ride the box's own mosquitto. Without it the
    # upstream link waits for its peer and the window's events stay on the box.
    if tunnel_up || ssh -f -N -o ExitOnForwardFailure=yes -R 1885:localhost:1885 "$HOUSE"; then
      echo "tunnel up"
    else
      echo "no tunnel: the window runs without the upstream link to the dev broker"
    fi
    # One box-side job: run the window scada, then start what was stopped.
    # SECS=0 is the standing window (window_boot.py runs until killed), so the
    # `timeout` wrapper is dropped in that case.
    ssh "$HOUSE" "mkdir -p $BOX_LOG_DIR
      for s in $SERVICES; do systemctl is-active -q \$s && echo \$s; done > $STOPPED
      echo \"stopping: \$(paste -sd' ' $STOPPED)\"
      [ ! -s $STOPPED ] || sudo systemctl stop \$(cat $STOPPED)
      SECS=$((MIN * 60))
      setsid nohup bash -c \"cd ~/gridworks-scada-unlimbo/gw_spaceheat && $BOOT_ENV \$([ \$SECS -gt 0 ] && echo timeout \$((SECS + 60))) venv/bin/python ~/experiments/2026-08-10-ads-declared-rate/window_boot.py \$SECS ~/envs/dev.env > $BOX_LOG_DIR/boot.log 2>&1; [ ! -s $STOPPED ] || sudo systemctl start \\\$(cat $STOPPED)\" > /dev/null 2>&1 < /dev/null &
      sleep 20
      git -C ~/gridworks-scada-unlimbo log --oneline -1
      tail -3 $BOX_LOG_DIR/boot.log | cut -c1-140"
    if window_up; then
      [ "$MIN" -gt 0 ] && echo "window scada up for $MIN min" || echo "window scada up, standing (until ./house_window.sh $HOUSE off)"
      echo "now: gridworks-scada/gw_spaceheat/venv/bin/gwa watch $HOUSE"
    else
      echo "window scada is NOT running after boot; the stopped services restart on the box. See: ./house_window.sh $HOUSE off (copies the log)"
      exit 1
    fi
    ;;
  off)
    mkdir -p "$SCRATCH"
    ssh "$HOUSE" 'pkill -f "[w]indow_boot.py" || true; sleep 5'
    LOG="$SCRATCH/$HOUSE-window-$(date +%Y%m%d-%H%M%S).log"
    scp -q "$HOUSE:$BOX_LOG_DIR/boot.log" "$LOG" 2>/dev/null && echo "window log: $LOG" || echo "no boot.log to copy"
    # The box-side job starts the recorded services when the window scada
    # exits; start them here as well so `off` is the restore even when that job
    # is gone (a reboot mid-window clears /tmp; enabled services start at boot).
    ssh "$HOUSE" "[ ! -s $STOPPED ] || sudo systemctl start \$(cat $STOPPED); sleep 3
      for s in $SERVICES; do echo \"\$s: \$(systemctl is-active \$s)\"; done
      [ ! -f $STOPPED ] || echo \"running before the window: \$(paste -sd' ' $STOPPED)\"
      rm -rf $BOX_LOG_DIR"
    ;;
  status)
    tunnel_up && echo "tunnel: up" || echo "tunnel: down"
    ssh "$HOUSE" "for s in $SERVICES; do echo \"\$s: \$(systemctl is-active \$s)\"; done
      pgrep -f '[w]indow_boot.py' >/dev/null && echo 'window scada: RUNNING' || echo 'window scada: down'
      [ ! -f $STOPPED ] || echo \"stopped for the window: \$(paste -sd' ' $STOPPED)\"
      $RELAYS"
    ;;
  *) sed -n 2,17p "$0"; exit 1 ;;
esac
