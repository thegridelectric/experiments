#!/usr/bin/env bash
# Seed the laptop's config folders with the scada repo's Nolan sim fixtures,
# under the deployed names a scada and an LTN read:
#
#   ./put_layout.sh dev check     compare each folder's files to the source
#                                 (sha256); exit 1 when any differs
#   ./put_layout.sh dev <change>  for each file that differs: leave a dated
#                                 <file>.<date>-pre-<change>.json copy beside
#                                 it, copy the source over it, verify the
#                                 sha256. <change> is a short dashed slug naming
#                                 what the new layout brings (pi-ids).
#
# The source is ../gridworks-scada/tests/config/ (gw.nolan.*); the laptop gets
# the files in ~/.config/gridworks/: scada/ (what `gws run` reads) takes the
# layout, the operational params and the ta-deed; ltn/ takes the layout and
# the params. A house's box takes its files from the committed tlayouts JSON
# through ../gridworks-scada/scripts/roll.sh.
#
# A scada writes its own operational-params.json (the cold latch that
# refuses dispatch), so the folder's params can hold something the source
# lacks. Where they differ, the script shows the difference and copies only
# on an answer of y; any other answer leaves the file as it is and exits 1.
set -euo pipefail
TARGET="${1:-}"
CHANGE="${2:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
[ "$TARGET" = dev ] || { sed -n 2,22p "$0"; exit 1; }
[[ "$CHANGE" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || { sed -n 2,22p "$0"; exit 1; }
GEN_DIR="$HERE/../gridworks-scada/tests/config"
# folder:stems, stems as deployed
PLACES=".config/gridworks/scada:hardware-layout operational-params ta-deed
.config/gridworks/ltn:hardware-layout operational-params"
STAMP="$(date +%Y-%m-%d)"
source_of() {
  case "$1" in
    hardware-layout) echo "$GEN_DIR/gw.nolan.layout.json" ;;
    operational-params) echo "$GEN_DIR/gw.nolan.operational.params.json" ;;
    ta-deed) echo "$GEN_DIR/gw.nolan.ta.deed.json" ;;
  esac
}
# the hash of a file, empty when it does not exist
sha_of() { if [ -f "$1" ]; then shasum -a 256 "$1" | cut -d' ' -f1; fi; }

DIFFERS=0
while IFS= read -r PLACE; do
  DIR="$HOME/${PLACE%%:*}"
  for STEM in ${PLACE#*:}; do
    GEN="$(source_of "$STEM")"
    FILE="$DIR/$STEM.json"
    AT="laptop ${PLACE%%:*}/$STEM.json"
    [ -f "$GEN" ] || { echo "no source file $GEN"; exit 1; }
    WANT="$(sha_of "$GEN")"
    if [ "$(sha_of "$FILE")" = "$WANT" ]; then
      echo "$AT: identical to the source (${WANT:0:12})"
      continue
    fi
    DIFFERS=1
    if [ "$CHANGE" = check ]; then
      echo "$AT: DIFFERS from the source (${WANT:0:12})"
      continue
    fi
    if [ "$STEM" = operational-params ] && [ -f "$FILE" ]; then
      echo "$AT: differs from the source; the file (-) against the source (+):"
      diff -u "$FILE" "$GEN" | tail -n +3 || true
      read -r -p "copy the source over the laptop's params? [y/N] " ANSWER || ANSWER=""
      [ "$ANSWER" = y ] || { echo "$AT: left as it is"; exit 1; }
    fi
    mkdir -p "$DIR"
    KEPT=none
    if [ -f "$FILE" ]; then
      cp -p "$FILE" "$DIR/$STEM.$STAMP-pre-$CHANGE.json"
      KEPT="$STEM.$STAMP-pre-$CHANGE.json"
    fi
    cp "$GEN" "$FILE"
    [ "$(sha_of "$FILE")" = "$WANT" ] || { echo "$AT: sha256 MISMATCH after the copy"; exit 1; }
    echo "$AT: put (${WANT:0:12}); previous file: $KEPT"
  done
done <<< "$PLACES"
[ "$CHANGE" = check ] && exit $DIFFERS || exit 0
