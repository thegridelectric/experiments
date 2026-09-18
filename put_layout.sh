#!/usr/bin/env bash
# Put the tlayouts gen output where a house's experiment-window scada
# reads it, from the laptop.
#
#   ./put_layout.sh <house> check      compare the box's window files to
#                                      ../tlayouts/output/<house>/ (sha256); exit 1
#                                      when either differs
#   ./put_layout.sh <house> <change>   for each file that differs: leave a dated
#                                      <file>.<date>-pre-<change>.json copy on the
#                                      box, copy the gen output over it, verify the
#                                      sha256. <change> is a short dashed slug naming
#                                      what the new layout brings (pi-ids).
#
# <house> is spruce, beech or maple (the ssh host of the same name). The
# window scada reads ~/.config/gridworks/scada-experiment/hardware-layout.json
# and the operational-params.json beside it. Run the house's gen first
# (../tlayouts/<house>_gen.py, from the scada venv); this script copies
# bytes and does not regenerate. It refuses while a window scada is running.
set -euo pipefail

HOUSE="${1:-}"
CHANGE="${2:-}"
case "$HOUSE" in
  spruce)      GEN_LAYOUT=gw.nolan.layout.json; GEN_OPS=gw.nolan.operational.params.json ;;
  beech|maple) GEN_LAYOUT=hardware-layout.generated.json; GEN_OPS=operational-params.generated.json ;;
  *)           sed -n 2,19p "$0"; exit 1 ;;
esac
[[ "$CHANGE" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || { sed -n 2,19p "$0"; exit 1; }

GEN_DIR="$(cd "$(dirname "$0")/.." && pwd)/tlayouts/output/$HOUSE"
BOX_DIR=.config/gridworks/scada-experiment
STAMP="$(date +%Y-%m-%d)"

# the box hash of a window file, empty when the file does not exist
box_sha() { ssh "$HOUSE" "sha256sum $BOX_DIR/$1 2>/dev/null | cut -d' ' -f1"; }

DIFFERS=0
for PAIR in "$GEN_LAYOUT:hardware-layout" "$GEN_OPS:operational-params"; do
  GEN="$GEN_DIR/${PAIR%%:*}"
  STEM="${PAIR##*:}"
  [ -f "$GEN" ] || { echo "no gen output $GEN"; exit 1; }
  WANT="$(shasum -a 256 "$GEN" | cut -d' ' -f1)"
  if [ "$(box_sha "$STEM.json")" = "$WANT" ]; then
    echo "$STEM.json: identical to the gen output (${WANT:0:12})"
    continue
  fi
  DIFFERS=1
  if [ "$CHANGE" = check ]; then
    echo "$STEM.json: DIFFERS from the gen output (${WANT:0:12})"
    continue
  fi
  if ssh "$HOUSE" 'pgrep -f "[w]indow_boot.py" >/dev/null'; then
    echo "a window scada is running on $HOUSE; stop it first"; exit 1
  fi
  KEPT="$(ssh "$HOUSE" "mkdir -p $BOX_DIR; [ ! -f $BOX_DIR/$STEM.json ] || { cp -p $BOX_DIR/$STEM.json $BOX_DIR/$STEM.$STAMP-pre-$CHANGE.json && echo $STEM.$STAMP-pre-$CHANGE.json; }")"
  scp -q "$GEN" "$HOUSE:$BOX_DIR/$STEM.json"
  [ "$(box_sha "$STEM.json")" = "$WANT" ] || { echo "$STEM.json: sha256 MISMATCH after the copy"; exit 1; }
  echo "$STEM.json: put (${WANT:0:12}); previous file: ${KEPT:-none, the box had no $STEM.json}"
done
[ "$CHANGE" = check ] && exit $DIFFERS || exit 0
