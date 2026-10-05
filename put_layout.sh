#!/usr/bin/env bash
# Put a house's authored files where its scada reads them, from the laptop:
# the tlayouts gen output onto a house's box, or the scada repo's sim
# fixtures into the laptop's own config folders.
#
#   ./put_layout.sh <target> check     compare the target's files to the source
#                                      (sha256); exit 1 when any differs
#   ./put_layout.sh <target> <change>  for each file that differs: leave a dated
#                                      <file>.<date>-pre-<change>.json copy beside
#                                      it, copy the source over it, verify the
#                                      sha256. <change> is a short dashed slug naming
#                                      what the new layout brings (pi-ids).
#
# <target> is spruce, beech or maple (the ssh host of the same name), or dev.
#
# A house: the source is ../tlayouts/output/<house>/, and the window scada
# reads ~/.config/gridworks/scada-experiment/hardware-layout.json and the
# operational-params.json beside it. Every house but spruce has a second pi
# (<house>2), which gets the same pair in the same place: a reading carries
# no unit on the wire, so both pis must hold one layout. Run the house's gen
# first (../tlayouts/<house>_gen.py, from the scada venv); this script copies
# bytes and does not regenerate.
#
# dev: the source is the Nolan sim fixtures in ../gridworks-scada/tests/config/,
# and the laptop gets them under the deployed names in ~/.config/gridworks/:
# scada/ (what `gws run` reads) and scada-experiment/ (what a dev window
# reads) take the pair and the ta-deed.json; ltn/ takes the pair.
#
# It refuses while a window scada is running on the target.
set -euo pipefail

HOUSE="${1:-}"
CHANGE="${2:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
PAIR="hardware-layout operational-params"
case "$HOUSE" in
  spruce)      GEN_LAYOUT=gw.nolan.layout.json; GEN_OPS=gw.nolan.operational.params.json; BOXES=spruce ;;
  beech)       GEN_LAYOUT=hardware-layout.generated.json; GEN_OPS=operational-params.generated.json; BOXES="beech beech2" ;;
  maple)       GEN_LAYOUT=hardware-layout.generated.json; GEN_OPS=operational-params.generated.json; BOXES="maple maple2" ;;
  dev)         GEN_LAYOUT=gw.nolan.layout.json; GEN_OPS=gw.nolan.operational.params.json; GEN_DEED=gw.nolan.ta.deed.json; BOXES=laptop ;;
  *)           sed -n 2,30p "$0"; exit 1 ;;
esac
[[ "$CHANGE" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || { sed -n 2,30p "$0"; exit 1; }

if [ "$HOUSE" = dev ]; then
  GEN_DIR="$HERE/../gridworks-scada/tests/config"
  # folder:files, files as deployed stems
  PLACES=".config/gridworks/scada:$PAIR ta-deed .config/gridworks/scada-experiment:$PAIR ta-deed .config/gridworks/ltn:$PAIR"
else
  GEN_DIR="$HERE/../tlayouts/output/$HOUSE"
  PLACES=".config/gridworks/scada-experiment:$PAIR"
fi
STAMP="$(date +%Y-%m-%d)"

# run a command in the home directory of a box, or of the laptop
on_box() { if [ "$1" = laptop ]; then (cd "$HOME" && bash -c "$2"); else ssh "$1" "$2"; fi; }
to_box() { if [ "$1" = laptop ]; then cp "$2" "$HOME/$3"; else scp -q "$2" "$1:$3"; fi; }
# the source file a deployed stem is copied from
source_of() {
  case "$1" in
    hardware-layout) echo "$GEN_DIR/$GEN_LAYOUT" ;;
    operational-params) echo "$GEN_DIR/$GEN_OPS" ;;
    ta-deed) echo "$GEN_DIR/$GEN_DEED" ;;
  esac
}
# the hash of a file on a box, empty when the file does not exist
box_sha() { on_box "$1" "{ sha256sum $2 2>/dev/null || shasum -a 256 $2 2>/dev/null; } | cut -d' ' -f1"; }

DIFFERS=0
IFS=$'\n'
for BOX in ${BOXES// /$'\n'}; do
for PLACE in $(echo "$PLACES" | sed 's# \.config#\n.config#g'); do
  BOX_DIR="${PLACE%%:*}"
  for STEM in $(echo "${PLACE#*:}" | tr ' ' '\n'); do
    GEN="$(source_of "$STEM")"
    AT="$BOX $BOX_DIR/$STEM.json"
    [ -f "$GEN" ] || { echo "no source file $GEN"; exit 1; }
    WANT="$(shasum -a 256 "$GEN" | cut -d' ' -f1)"
    if [ "$(box_sha "$BOX" "$BOX_DIR/$STEM.json")" = "$WANT" ]; then
      echo "$AT: identical to the source (${WANT:0:12})"
      continue
    fi
    DIFFERS=1
    if [ "$CHANGE" = check ]; then
      echo "$AT: DIFFERS from the source (${WANT:0:12})"
      continue
    fi
    if on_box "$BOX" 'pgrep -f "[w]indow_boot.py" >/dev/null'; then
      echo "a window scada is running on $BOX; stop it first"; exit 1
    fi
    KEPT="$(on_box "$BOX" "mkdir -p $BOX_DIR; [ ! -f $BOX_DIR/$STEM.json ] || { cp -p $BOX_DIR/$STEM.json $BOX_DIR/$STEM.$STAMP-pre-$CHANGE.json && echo $STEM.$STAMP-pre-$CHANGE.json; }")"
    to_box "$BOX" "$GEN" "$BOX_DIR/$STEM.json"
    [ "$(box_sha "$BOX" "$BOX_DIR/$STEM.json")" = "$WANT" ] || { echo "$AT: sha256 MISMATCH after the copy"; exit 1; }
    echo "$AT: put (${WANT:0:12}); previous file: ${KEPT:-none}"
  done
done
done
[ "$CHANGE" = check ] && exit $DIFFERS || exit 0
