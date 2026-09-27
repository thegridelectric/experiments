#!/usr/bin/env bash
# Run a bounded window of the unlimbo scada, from the laptop, in one word each:
# on a house (swapping it off its deployed plant control for the window) or in
# dev (the laptop's scada checkout on its sim layout). Every window is recorded
# by capture_broker.py on the laptop's gw-dev-rabbit. spruce_window.sh,
# beech_window.sh and maple_window.sh call this with their house.
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
#                                            until `off`. A bounded window is at
#                                            least MIN_WINDOW_MIN minutes, so it
#                                            crosses two report boundaries and
#                                            saves the first full-slot report.
#                                              --debug  scada (and LTN) loggers at DEBUG
#                                              --ltn    run the LTN on the laptop against
#                                                       the target's layout, as the
#                                                       scada's upstream peer
#   ./house_window.sh <target> off           kill the window scada (and the LTN), copy
#                                            the log and this window's persisted
#                                            events to ../scratch/, count the
#                                            report.events, confirm the stopped
#                                            services are back
#   ./house_window.sh <target> status        services, window scada, tunnel, relay bits
#   ./house_window.sh capture off|status     stop / show the broker capture; it is
#                                            shared by every open window, so it is
#                                            stopped by hand, after the last `off`
#
# <target> is dev, spruce, beech or maple (a house is the ssh host of the same name).
# Every house but spruce has a second pi (<house>2), and a window runs on both:
# the second pi's deployed scada2 is stopped and the branch scada2 boots there
# from its own ~/gridworks-scada-unlimbo on the same layout pair, posting to
# the first pi's broker; `off` and `status` cover it. A reading carries no
# unit on the wire, so a window never mixes one pi on the branch pair with the
# other on production: both pis boot at once, `on` ends the window on both
# unless both come up, and a watcher on the laptop ends it on both when it
# ends on either (a bound, a crash). A laptop asleep or off the network
# leaves each pi to its own bound.
#
# `on` for a house refuses unless:
#   - the box's window pair (~/.config/gridworks/scada-experiment/) is
#     byte-identical to ../tlayouts/output/<house>/ (put_layout.sh <house> check).
#     This script never writes a layout; put_layout.sh does.
#   - the laptop's scada head is pushed and the box's ~/gridworks-scada-unlimbo
#     checkout is at it (the box runs pushed SHAs only; pull on the box); the
#     second pi's too.
#   - no window scada is already running.
#
# The services running at `on` are recorded on the box and stopped. The box
# starts exactly those again when the window scada exits for any reason: the
# minutes bound, a crash, or `off`. A service that was not running stays off.
#
# The window scada runs through
# ~/experiments/window_boot.py from ~/envs/dev.env
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
WINDOW_BOOT="$HERE/window_boot.py"
CAPTURE_PID="$HERE/.capture_broker.pid"
CAPTURE_OUT="$SCRATCH/capture.out"
usage() { sed -n 2,34p "$0"; exit 1; }
# Reports go out on 300 s wall-clock boundaries; the first covers the partial
# slot after boot, the second is the first full slot. 11 min crosses both with
# a minute left for boot.
MIN_WINDOW_MIN=11

capture_up() { [ -f "$CAPTURE_PID" ] && kill -0 "$(cat "$CAPTURE_PID")" 2>/dev/null; }
ensure_capture() {
  mkdir -p "$SCRATCH"
  if capture_up; then echo "capture: already running ($(grep -m1 '^capturing' "$CAPTURE_OUT" | sed 's/.*-> //'))"; return; fi
  (cd "$HERE" && exec nohup uv run python capture_broker.py "$SCRATCH" > "$CAPTURE_OUT" 2>&1 < /dev/null) &
  for _ in $(seq 20); do grep -q '^capturing' "$CAPTURE_OUT" 2>/dev/null && break; sleep 1; done
  grep '^capturing' "$CAPTURE_OUT" || { cat "$CAPTURE_OUT"; echo "refusing: no proven broker capture, so the window would leave no record"; exit 1; }
}
# One line per window in the running capture's .windows.txt; capture_broker.py
# folds them into the capture's provenance sidecar when it stops.
note_window() {
  local cap; cap="$(grep -m1 '^capturing' "$CAPTURE_OUT" | sed 's/.*-> //')"
  echo "$(date '+%Y-%m-%d %H:%M:%S') $HOUSE window, ${MIN} min, debug=$DEBUG ltn=$LTN, scada $1" >> "${cap%.jsonl}.windows.txt"
}
ltn_up() { pgrep -f "gws ltn run" >/dev/null; }
stop_ltn() { if ltn_up; then pkill -f "gws ltn run" || true; echo "ltn stopped; log: $(ls -t "$SCRATCH"/*-ltn-*.log 2>/dev/null | head -1)"; fi; }

SECOND_PI=""
SECOND_SERVICES=""
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
    BOOT_ENV="SCADA_PICO_CYCLER_STATE_LOGGING=true SCADA_UNKNOWN_CHANNEL_LOGGING=true"
    LTN_LAYOUT="$TLAYOUTS/output/spruce/gw.nolan.layout.json"
    LTN_OPS="$TLAYOUTS/output/spruce/gw.nolan.operational.params.json"
    # gw108 relay board 0x21, output register 3
    RELAYS="~/gridworks-scada/gw_spaceheat/venv/bin/python -c \"import smbus2; r=smbus2.SMBus(1).read_byte_data(0x21,3); print('0x21 reg3 iso=%d store=%d secondary=%d' % ((r>>2)&1,(r>>4)&1,(r>>5)&1))\""
    ;;
  beech)
    SERVICES="gwspaceheat gwspaceheat-restart.timer"
    BOOT_ENV="SCADA_UNKNOWN_CHANNEL_LOGGING=true"
    SECOND_PI=beech2
    SECOND_SERVICES="gwspaceheat2 gwspaceheat2-restart.timer"
    LTN_LAYOUT="$TLAYOUTS/output/beech/hardware-layout.generated.json"
    LTN_OPS="$TLAYOUTS/output/beech/operational-params.generated.json"
    # PCF8575: one 16-bit port word per Krida, read as two bytes; a low bit is an energized relay
    RELAYS="for a in 0x20 0x21; do echo -n \"\$a: \"; sudo i2ctransfer -y 1 r2@\$a; done"
    ;;
  maple)
    SERVICES="gwspaceheat gwspaceheat-restart.timer"
    BOOT_ENV="SCADA_UNKNOWN_CHANNEL_LOGGING=true"
    SECOND_PI=maple2
    SECOND_SERVICES="gwspaceheat2 gwspaceheat2-restart.timer"
    LTN_LAYOUT="$TLAYOUTS/output/maple/hardware-layout.generated.json"
    LTN_OPS="$TLAYOUTS/output/maple/operational-params.generated.json"
    # the same two-Krida panel as beech
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
if [ "$MIN" -gt 0 ] && [ "$MIN" -lt "$MIN_WINDOW_MIN" ]; then
  echo "refusing: a bounded window is at least $MIN_WINDOW_MIN min so it saves a full-slot report; no minutes = a standing window"; exit 1
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
      note_window "$(git -C "$SCADA" rev-parse HEAD)$([ -z "$(git -C "$SCADA" status --porcelain)" ] || echo ' (working tree dirty)')"
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
# UTC start of the window; persisted event files are named by a UTC ISO stamp
STARTED="$BOX_LOG_DIR/started-utc"
BOX_EVENT_DIR="/home/pi/.local/share/gridworks/scada-experiment/event"

tunnel_up() { pgrep -f "ssh -f -N.*-R 1885:localhost:1885 $HOUSE" >/dev/null; }
window_up() { ssh "${1:-$HOUSE}" 'pgrep -f "[w]indow_boot.py" >/dev/null'; }
# up, down, or unknown when the box cannot be reached
window_state() { ssh -o ConnectTimeout=5 -o BatchMode=yes "$1" 'pgrep -f "[w]indow_boot.py" >/dev/null && echo up || echo down' 2>/dev/null || echo unknown; }
PAIR_PID="$HERE/.pair_watch.$HOUSE.pid"
pair_up() { [ -f "$PAIR_PID" ] && kill -0 "$(cat "$PAIR_PID")" 2>/dev/null; }
head_check() {  # $1 box: refuse unless its unlimbo checkout is at the laptop's head
  local box_head; box_head="$(ssh "$1" 'git -C ~/gridworks-scada-unlimbo rev-parse HEAD')"
  [ "$box_head" = "$HEAD" ] || { echo "refusing: $1 unlimbo checkout is at ${box_head:0:8}, the laptop's scada head is ${HEAD:0:8}; on the box: git -C ~/gridworks-scada-unlimbo pull --ff-only"; exit 1; }
}
# One box-side job on $1: stop the services in $2, run the window scada with
# the env in $3, then start what was stopped. SECS=0 is the standing window
# (window_boot.py runs until killed), so the `timeout` wrapper is dropped.
box_start() {
  ssh "$1" "mkdir -p $BOX_LOG_DIR
    date -u +%Y-%m-%dT%H:%M:%S > $STARTED
    for s in $2; do systemctl is-active -q \$s && echo \$s; done > $STOPPED
    echo \"$1 stopping: \$(paste -sd' ' $STOPPED)\"
    [ ! -s $STOPPED ] || sudo systemctl stop \$(cat $STOPPED)
    SECS=$SECS
    setsid nohup bash -c \"cd ~/gridworks-scada-unlimbo/gw_spaceheat && $3 \$([ \$SECS -gt 0 ] && echo timeout \$((SECS + 60))) venv/bin/python ~/experiments/window_boot.py \$SECS ~/envs/dev.env > $BOX_LOG_DIR/boot.log 2>&1; [ ! -s $STOPPED ] || sudo systemctl start \\\$(cat $STOPPED)\" > /dev/null 2>&1 < /dev/null &
    sleep 20
    git -C ~/gridworks-scada-unlimbo log --oneline -1
    tail -3 $BOX_LOG_DIR/boot.log | cut -c1-140"
}
# Restore $1: kill its window scada, start the services in $2 (the box-side
# job does this too; here as well so `off` restores even when that job is
# gone: a reboot mid-window clears /tmp, and enabled services start at boot).
box_restore() {
  ssh "$1" "[ ! -s $STOPPED ] || sudo systemctl start \$(cat $STOPPED); sleep 3
    for s in $2; do echo \"$1 \$s: \$(systemctl is-active \$s)\"; done
    [ ! -f $STOPPED ] || echo \"$1 running before the window: \$(paste -sd' ' $STOPPED)\"
    rm -rf $BOX_LOG_DIR"
}
# End the window on $1 now: kill its window scada and start the services it
# stopped. pkill takes the box-side job's wrapper with it, so the job's own
# restart does not run; this does it. The log stays for `off` to copy.
box_end() {
  ssh "$1" "pkill -f '[w]indow_boot.py' || true; sleep 5
    [ ! -s $STOPPED ] || sudo systemctl start \$(cat $STOPPED)"
}
# Every 10 s while the window runs on both pis: when it has ended on either,
# end it on both (on the pi already down this restarts its services in case
# its job did not), then exit.
pair_watch() {
  local a b
  while sleep 10; do
    a="$(window_state "$HOUSE")"; b="$(window_state "$SECOND_PI")"
    if [ "$a" = up ] && [ "$b" = up ]; then continue; fi
    if [ "$a" = unknown ] || [ "$b" = unknown ]; then continue; fi
    echo "$(date '+%Y-%m-%d %H:%M:%S') $HOUSE window $a, $SECOND_PI window $b: ending both"
    box_end "$HOUSE"; box_end "$SECOND_PI"
    return
  done
}
box_status() {
  ssh "$1" "for s in $2; do echo \"$1 \$s: \$(systemctl is-active \$s)\"; done
    pgrep -f '[w]indow_boot.py' >/dev/null && echo '$1 window scada: RUNNING' || echo '$1 window scada: down'
    [ ! -f $STOPPED ] || echo \"$1 stopped for the window: \$(paste -sd' ' $STOPPED)\""
}

case "${2:-}" in
  on)
    "$HERE/put_layout.sh" "$HOUSE" check || { echo "refusing: put the gen output first (./put_layout.sh $HOUSE <change>)"; exit 1; }
    HEAD="$(git -C "$SCADA" rev-parse HEAD)"
    [ -z "$(git -C "$SCADA" log --oneline '@{u}..')" ] || { echo "refusing: the laptop's scada head ${HEAD:0:8} is not pushed"; exit 1; }
    head_check "$HOUSE"
    [ -z "$SECOND_PI" ] || head_check "$SECOND_PI"
    if window_up; then echo "refusing: a window scada is already running on $HOUSE"; exit 1; fi
    if [ -n "$SECOND_PI" ] && window_up "$SECOND_PI"; then echo "refusing: a window scada2 is already running on $SECOND_PI"; exit 1; fi
    ensure_capture
    note_window "$HEAD"
    # The tunnel carries the upstream (LTN) link to the laptop's dev broker for
    # observation only; commands ride the box's own mosquitto. Without it the
    # upstream link waits for its peer and the window's events stay on the box.
    if tunnel_up || ssh -f -N -o ExitOnForwardFailure=yes -R 1885:localhost:1885 "$HOUSE"; then
      echo "tunnel up"
    else
      echo "no tunnel: the window runs without the upstream link to the dev broker, and the capture will hold nothing from $HOUSE"
    fi
    start_ltn
    if [ -z "$SECOND_PI" ]; then
      box_start "$HOUSE" "$SERVICES" "$BOOT_ENV $DEBUG_ENV"
    else
      box_start "$HOUSE" "$SERVICES" "$BOOT_ENV $DEBUG_ENV" > "$SCRATCH/.$HOUSE-start.out" 2>&1 < /dev/null &
      P1=$!
      box_start "$SECOND_PI" "$SECOND_SERVICES" "WINDOW_SCADA2=1 $DEBUG_ENV" > "$SCRATCH/.$SECOND_PI-start.out" 2>&1 < /dev/null &
      P2=$!
      # the two boots only: the broker capture is a background job of this shell too
      wait "$P1" "$P2"
      cat "$SCRATCH/.$HOUSE-start.out" "$SCRATCH/.$SECOND_PI-start.out"
      rm -f "$SCRATCH/.$HOUSE-start.out" "$SCRATCH/.$SECOND_PI-start.out"
      if window_up && window_up "$SECOND_PI"; then
        echo "$SECOND_PI window scada2 up"
        ( trap '' HUP; pair_watch ) > "$SCRATCH/$HOUSE-pair-watch-$(date +%Y%m%d-%H%M%S).log" 2>&1 < /dev/null &
        echo $! > "$PAIR_PID"
      else
        echo "the window did not come up on both $HOUSE and $SECOND_PI; ending it on both. See: ./house_window.sh $HOUSE off (copies the logs)"
        box_end "$HOUSE"; box_end "$SECOND_PI"
        exit 1
      fi
    fi
    if window_up; then
      [ "$MIN" -gt 0 ] && echo "window scada up for $MIN min" || echo "window scada up, standing (until ./house_window.sh $HOUSE off)"
      echo "now: gridworks-scada/gw_spaceheat/venv/bin/gwa watch $HOUSE"
    else
      echo "window scada is NOT running after boot; the stopped services restart on the box. See: ./house_window.sh $HOUSE off (copies the log)"
      exit 1
    fi
    ;;
  off)
    # the first pi is restored on the way out whatever fails below
    trap 'box_restore "$HOUSE" "$SERVICES"' EXIT
    mkdir -p "$SCRATCH"
    if pair_up; then kill "$(cat "$PAIR_PID")"; fi
    rm -f "$PAIR_PID"
    ssh "$HOUSE" 'pkill -f "[w]indow_boot.py" || true; sleep 5'
    stop_ltn
    LOG="$SCRATCH/$HOUSE-window-$(date +%Y%m%d-%H%M%S).log"
    scp -q "$HOUSE:$BOX_LOG_DIR/boot.log" "$LOG" 2>/dev/null && echo "window log: $LOG" || echo "no boot.log to copy"
    if [ -n "$SECOND_PI" ]; then
      ssh "$SECOND_PI" 'pkill -f "[w]indow_boot.py" || true; sleep 5'
      LOG2="$SCRATCH/$SECOND_PI-window-$(date +%Y%m%d-%H%M%S).log"
      scp -q "$SECOND_PI:$BOX_LOG_DIR/boot.log" "$LOG2" 2>/dev/null && echo "$SECOND_PI window log: $LOG2" || echo "no $SECOND_PI boot.log to copy"
      box_restore "$SECOND_PI" "$SECOND_SERVICES"
    fi
    # Events the upstream link did not deliver (no LTN, or before it acked)
    # persist on the box; pull the ones stamped at or after this window's start.
    EVENTS="$SCRATCH/$HOUSE-events-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$EVENTS"
    ssh "$HOUSE" "[ -f $STARTED ] || exit 0; cd $BOX_EVENT_DIR 2>/dev/null || exit 0
      start=\$(cat $STARTED); find . -type f -name '*.json' | while read f; do [[ \$(basename \"\$f\") > \$start ]] && echo \"\$f\"; done | tar -cf - -T - 2>/dev/null" | tar -xf - -C "$EVENTS" 2>/dev/null || true
    N_EVENTS="$(find "$EVENTS" -type f -name '*.json' | wc -l | tr -d ' ')"
    N_REPORTS="$({ grep -l '"TypeName": *"report.event"' -r "$EVENTS" 2>/dev/null || true; } | wc -l | tr -d ' ')"
    echo "events: $N_EVENTS persisted on the box, $N_REPORTS report.event -> $EVENTS"
    [ "$N_REPORTS" -gt 0 ] || echo "WARNING: no report.event on the box; a window run with --ltn delivers them to the capture instead"
    capture_up && echo "capture still running; after the last window: ./house_window.sh capture off"
    ;;
  status)
    tunnel_up && echo "tunnel: up" || echo "tunnel: down"
    ltn_up && echo "ltn: RUNNING" || echo "ltn: down"
    capture_up && grep -m1 '^capturing' "$CAPTURE_OUT" || echo "capture: not running"
    box_status "$HOUSE" "$SERVICES"
    ssh "$HOUSE" "$RELAYS"
    if [ -n "$SECOND_PI" ]; then
      box_status "$SECOND_PI" "$SECOND_SERVICES"
      pair_up && echo "pair watch: RUNNING" || echo "pair watch: down"
    fi
    ;;
  *) usage ;;
esac
