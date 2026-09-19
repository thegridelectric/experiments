#!/usr/bin/env bash
# Run a bounded window of the unlimbo scada, from the laptop, in one word each:
# on a house (swapping it off its deployed plant control for the window) or in
# dev (the laptop's scada checkout on its sim layout). Every window is recorded
# by capture_broker.py on the laptop's gw-dev-rabbit. spruce_window.sh and
# beech_window.sh call this with their house.
#
#   ./house_window.sh <target> on [minutes] [--debug] [--ltn]
#                                            start the broker capture if none is
#                                            running (refuses if it cannot prove
#                                            itself), then open the window. On a
#                                            house: check the box is ready (below),
#                                            open the ssh -R 1885 tunnel to the
#                                            laptop's gw-dev-rabbit, stop the house's
#                                            running plant services, boot the window
#                                            scada. No minutes = a standing window
#                                            until `off`.
#                                              --debug  scada (and LTN) loggers at DEBUG
#                                              --ltn    run the LTN on the laptop against
#                                                       the target's layout, as the
#                                                       scada's upstream peer
#   ./house_window.sh <target> off           kill the window scada (and the LTN), copy
#                                            the logs to ../scratch/, confirm the
#                                            stopped services are back
#   ./house_window.sh <target> status        services, window scada, tunnel, relay bits
#   ./house_window.sh capture off|status     stop / show the broker capture; it is
#                                            shared by every open window, so it is
#                                            stopped by hand, after the last `off`
#
# <target> is dev, spruce or beech (a house is the ssh host of the same name).
#
# `on` for a house refuses unless:
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
# own mosquitto). A dev window runs the same boot from the laptop's scada
# checkout and its .env. Then `gwa watch <house>` from the laptop.
#
# The LTN takes its identity and its peer from the layout it loads, so --ltn
# loads the target's own pair: the scada .env's pair in dev, the tlayouts gen
# output for a house. One LTN runs at a time (its paths root is shared).
set -euo pipefail

HOUSE="${1:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SCRATCH="$HERE/../scratch"
SCADA="$HERE/../gridworks-scada"
TLAYOUTS="$HERE/../tlayouts"
WINDOW_BOOT="$HERE/2026-08-10-ads-declared-rate/window_boot.py"
CAPTURE_PID="$HERE/.capture_broker.pid"
CAPTURE_OUT="$SCRATCH/capture.out"
usage() { sed -n 2,29p "$0"; exit 1; }

capture_up() { [ -f "$CAPTURE_PID" ] && kill -0 "$(cat "$CAPTURE_PID")" 2>/dev/null; }
ensure_capture() {
  mkdir -p "$SCRATCH"
  if capture_up; then echo "capture: already running ($(grep -m1 '^capturing' "$CAPTURE_OUT" | sed 's/.*-> //'))"; return; fi
  (cd "$HERE" && exec nohup uv run python capture_broker.py "$SCRATCH" > "$CAPTURE_OUT" 2>&1 < /dev/null) &
  for _ in $(seq 20); do grep -q '^capturing' "$CAPTURE_OUT" 2>/dev/null && break; sleep 1; done
  grep '^capturing' "$CAPTURE_OUT" || { cat "$CAPTURE_OUT"; echo "refusing: no proven broker capture, so the window would leave no record"; exit 1; }
}
ltn_up() { pgrep -f "gws ltn run" >/dev/null; }
stop_ltn() { if ltn_up; then pkill -f "gws ltn run" || true; echo "ltn stopped; log: $(ls -t "$SCRATCH"/*-ltn-*.log 2>/dev/null | head -1)"; fi; }

case "$HOUSE" in
  capture)
    case "${2:-}" in
      off) if capture_up; then kill "$(cat "$CAPTURE_PID")"; sleep 3; tail -1 "$CAPTURE_OUT"; else echo "capture: not running"; fi ;;
      status) capture_up && grep -m1 '^capturing' "$CAPTURE_OUT" || echo "capture: not running" ;;
      *) usage ;;
    esac
    exit 0 ;;
  dev)
    # the pair the scada checkout's .env names, paths relative to the checkout
    LTN_LAYOUT="$(sed -n 's/^LTN_PATHS__HARDWARE_LAYOUT *= *//p' "$SCADA/.env" | tr -d '"')"
    LTN_OPS="$(sed -n 's/^SCADA_PATHS__OPERATIONAL_PARAMS *= *//p' "$SCADA/.env" | tr -d '"')"
    ;;
  spruce)
    SERVICES="spruce-winter-hack gwspaceheat gwspaceheat-restart.timer"
    BOOT_ENV="SCADA_PICO_CYCLER_STATE_LOGGING=true"
    LTN_LAYOUT="$TLAYOUTS/output/spruce/gw.nolan.layout.json"
    LTN_OPS="$TLAYOUTS/output/spruce/gw.nolan.operational.params.json"
    # gw108 relay board 0x21, output register 3
    RELAYS="~/gridworks-scada/gw_spaceheat/venv/bin/python -c \"import smbus2; r=smbus2.SMBus(1).read_byte_data(0x21,3); print('0x21 reg3 iso=%d store=%d secondary=%d' % ((r>>2)&1,(r>>4)&1,(r>>5)&1))\""
    ;;
  beech)
    SERVICES="gwspaceheat gwspaceheat-restart.timer"
    BOOT_ENV=""
    LTN_LAYOUT="$TLAYOUTS/output/beech/hardware-layout.generated.json"
    LTN_OPS="$TLAYOUTS/output/beech/operational-params.generated.json"
    # PCF8575: one 16-bit port word per Krida, read as two bytes; a low bit is an energized relay
    RELAYS="for a in 0x20 0x21; do echo -n \"\$a: \"; sudo i2ctransfer -y 1 r2@\$a; done"
    ;;
  *) usage ;;
esac

# on [minutes] [--debug] [--ltn]
MIN=0; DEBUG=0; LTN=0
if [ "${2:-}" = on ]; then
  for a in "${@:3}"; do
    case "$a" in
      --debug) DEBUG=1 ;;
      --ltn) LTN=1 ;;
      *) [[ "$a" =~ ^[0-9]+$ ]] || { echo "minutes must be a whole number; flags are --debug and --ltn"; exit 1; }; MIN="$a" ;;
    esac
  done
fi
SECS=$((MIN * 60))
DEBUG_ENV=""
[ "$DEBUG" = 0 ] || DEBUG_ENV="SCADA_LOGGING__BASE_LOG_LEVEL=10 SCADA_LOGGING__LEVELS__MESSAGE_SUMMARY=10"

start_ltn() {
  [ "$LTN" = 1 ] || return 0
  if ltn_up; then echo "refusing: an LTN is already running on the laptop"; exit 1; fi
  local log="$SCRATCH/$HOUSE-ltn-$(date +%Y%m%d-%H%M%S).log"
  (cd "$SCADA" && exec nohup env LTN_PATHS__HARDWARE_LAYOUT="$LTN_LAYOUT" LTN_PATHS__OPERATIONAL_PARAMS="$LTN_OPS" \
    $([ "$DEBUG" = 0 ] || echo LTN_LOGGING__BASE_LOG_LEVEL=10) gw_spaceheat/gws ltn run --env-file .env > "$log" 2>&1 < /dev/null) &
  sleep 5
  ltn_up && echo "ltn up on $LTN_LAYOUT; log: $log" || { echo "the LTN did not stay up; see $log"; exit 1; }
}

if [ "$HOUSE" = dev ]; then
  DEV_LOG="$SCRATCH/dev-window-boot.log"
  dev_up() { pgrep -f "window_boot.py .* $SCADA/gw_spaceheat" >/dev/null; }
  case "${2:-}" in
    on)
      if dev_up; then echo "refusing: a dev window scada is already running"; exit 1; fi
      ensure_capture
      start_ltn
      (cd "$SCADA" && exec nohup env $DEBUG_ENV gw_spaceheat/venv/bin/python "$WINDOW_BOOT" "$SECS" .env "$SCADA/gw_spaceheat" > "$DEV_LOG" 2>&1 < /dev/null) &
      sleep 15
      if dev_up; then
        [ "$MIN" -gt 0 ] && echo "dev window scada up for $MIN min" || echo "dev window scada up, standing (until ./house_window.sh dev off)"
        grep -m1 '== window boot' "$DEV_LOG" || true
      else
        echo "dev window scada is NOT running after boot; see $DEV_LOG"; stop_ltn; exit 1
      fi
      ;;
    off)
      pkill -f "window_boot.py .* $SCADA/gw_spaceheat" || true; sleep 3
      stop_ltn
      LOG="$SCRATCH/dev-window-$(date +%Y%m%d-%H%M%S).log"
      [ -f "$DEV_LOG" ] && mv "$DEV_LOG" "$LOG" && echo "window log: $LOG" || echo "no boot log to keep"
      capture_up && echo "capture still running; after the last window: ./house_window.sh capture off"
      ;;
    status)
      dev_up && echo "dev window scada: RUNNING" || echo "dev window scada: down"
      ltn_up && echo "ltn: RUNNING" || echo "ltn: down"
      capture_up && grep -m1 '^capturing' "$CAPTURE_OUT" || echo "capture: not running"
      ;;
    *) usage ;;
  esac
  exit 0
fi

BOX_LOG_DIR="/tmp/$HOUSE-window"
STOPPED="$BOX_LOG_DIR/stopped-services"

tunnel_up() { pgrep -f "ssh -f -N.*-R 1885:localhost:1885 $HOUSE" >/dev/null; }
window_up() { ssh "$HOUSE" 'pgrep -f "[w]indow_boot.py" >/dev/null'; }

case "${2:-}" in
  on)
    "$HERE/put_layout.sh" "$HOUSE" check || { echo "refusing: put the gen output first (./put_layout.sh $HOUSE <change>)"; exit 1; }
    HEAD="$(git -C "$SCADA" rev-parse HEAD)"
    [ -z "$(git -C "$SCADA" log --oneline '@{u}..')" ] || { echo "refusing: the laptop's scada head ${HEAD:0:8} is not pushed"; exit 1; }
    BOX_HEAD="$(ssh "$HOUSE" 'git -C ~/gridworks-scada-unlimbo rev-parse HEAD')"
    [ "$BOX_HEAD" = "$HEAD" ] || { echo "refusing: $HOUSE unlimbo checkout is at ${BOX_HEAD:0:8}, the laptop's scada head is ${HEAD:0:8}; on the box: git -C ~/gridworks-scada-unlimbo pull --ff-only"; exit 1; }
    if window_up; then echo "refusing: a window scada is already running on $HOUSE"; exit 1; fi
    ensure_capture
    # The tunnel carries the upstream (LTN) link to the laptop's dev broker for
    # observation only; commands ride the box's own mosquitto. Without it the
    # upstream link waits for its peer and the window's events stay on the box.
    if tunnel_up || ssh -f -N -o ExitOnForwardFailure=yes -R 1885:localhost:1885 "$HOUSE"; then
      echo "tunnel up"
    else
      echo "no tunnel: the window runs without the upstream link to the dev broker, and the capture will hold nothing from $HOUSE"
    fi
    start_ltn
    # One box-side job: run the window scada, then start what was stopped.
    # SECS=0 is the standing window (window_boot.py runs until killed), so the
    # `timeout` wrapper is dropped in that case.
    ssh "$HOUSE" "mkdir -p $BOX_LOG_DIR
      for s in $SERVICES; do systemctl is-active -q \$s && echo \$s; done > $STOPPED
      echo \"stopping: \$(paste -sd' ' $STOPPED)\"
      [ ! -s $STOPPED ] || sudo systemctl stop \$(cat $STOPPED)
      SECS=$SECS
      setsid nohup bash -c \"cd ~/gridworks-scada-unlimbo/gw_spaceheat && $BOOT_ENV $DEBUG_ENV \$([ \$SECS -gt 0 ] && echo timeout \$((SECS + 60))) venv/bin/python ~/experiments/2026-08-10-ads-declared-rate/window_boot.py \$SECS ~/envs/dev.env > $BOX_LOG_DIR/boot.log 2>&1; [ ! -s $STOPPED ] || sudo systemctl start \\\$(cat $STOPPED)\" > /dev/null 2>&1 < /dev/null &
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
    stop_ltn
    LOG="$SCRATCH/$HOUSE-window-$(date +%Y%m%d-%H%M%S).log"
    scp -q "$HOUSE:$BOX_LOG_DIR/boot.log" "$LOG" 2>/dev/null && echo "window log: $LOG" || echo "no boot.log to copy"
    # The box-side job starts the recorded services when the window scada
    # exits; start them here as well so `off` is the restore even when that job
    # is gone (a reboot mid-window clears /tmp; enabled services start at boot).
    ssh "$HOUSE" "[ ! -s $STOPPED ] || sudo systemctl start \$(cat $STOPPED); sleep 3
      for s in $SERVICES; do echo \"\$s: \$(systemctl is-active \$s)\"; done
      [ ! -f $STOPPED ] || echo \"running before the window: \$(paste -sd' ' $STOPPED)\"
      rm -rf $BOX_LOG_DIR"
    capture_up && echo "capture still running; after the last window: ./house_window.sh capture off"
    ;;
  status)
    tunnel_up && echo "tunnel: up" || echo "tunnel: down"
    ltn_up && echo "ltn: RUNNING" || echo "ltn: down"
    capture_up && grep -m1 '^capturing' "$CAPTURE_OUT" || echo "capture: not running"
    ssh "$HOUSE" "for s in $SERVICES; do echo \"\$s: \$(systemctl is-active \$s)\"; done
      pgrep -f '[w]indow_boot.py' >/dev/null && echo 'window scada: RUNNING' || echo 'window scada: down'
      [ ! -f $STOPPED ] || echo \"stopped for the window: \$(paste -sd' ' $STOPPED)\"
      $RELAYS"
    ;;
  *) usage ;;
esac
