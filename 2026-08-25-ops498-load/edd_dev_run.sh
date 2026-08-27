#!/usr/bin/env bash
# EDD dev run: reset → seed current era → snapshot → pass 1 (layouts) → pass 2 (rest) → check.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
JK="$HERE/../../gridworks-journalkeeper"
RUN="$HERE/runs/$(date -u +%Y%m%dT%H%M)"
mkdir -p "$RUN"
export DEV_DB_URL="${DEV_DB_URL:-postgresql+psycopg2://gw_journalkeeper:changeme@localhost:5433/tsdb}"
# Reset needs the table owner; the dev container's superuser (dev only).
DEV_ADMIN_URL="${DEV_ADMIN_URL:-postgresql://postgres:changeme@localhost:5433/tsdb}"
# shellcheck disable=SC1091
set -a; . "$HERE/../.env"; set +a
export GJK_DB_URL_PROD="$GJK_DB_URL"
PY="uv run --project $JK python"
IMPORT="$PY -m gjk.s3_message_importer --workers ${WORKERS:-8} --batch-size ${BATCH:-500}"

# Windows: start end. Pass 1 (layouts) covers all; pass 2 skips the layout-only one.
WINDOWS=("2024-10-13 2024-10-15" "2024-12-01 2024-12-03" "2024-12-10 2024-12-12" "2025-02-15 2025-02-17" "2025-12-20 2025-12-22")
LAYOUT_ONLY="2024-12-01 2024-12-03"

echo "== reset dev DB"
psql "$DEV_ADMIN_URL" -q -v ON_ERROR_STOP=1 -f "$HERE/reset_dev.sql"
echo "== seed current era from prod"
GJK_DB_URL="$GJK_DB_URL_PROD" $PY "$HERE/seed_current_era.py"
echo "== snapshot"
$PY "$HERE/assert_dev_run.py" snapshot "$RUN"

cd "$JK"
export GJK_DB_URL="$DEV_DB_URL"
echo "== pass 1: layout.lite forward"
for w in "${WINDOWS[@]}"; do set -- $w
  $IMPORT --start "$1" --end "$2" --message-types layout.lite --summary-json "$RUN/pass1_$1_$2.json" > "$RUN/pass1_$1_$2.log" 2>&1
  tail -n +1 "$RUN/pass1_$1_$2.log" | grep -A40 "RUN SUMMARY" | head -60
done
echo "== pass 2: everything else forward"
for w in "${WINDOWS[@]}"; do [ "$w" = "$LAYOUT_ONLY" ] && continue; set -- $w
  $IMPORT --start "$1" --end "$2" --message-types '~layout.lite' --summary-json "$RUN/pass2_$1_$2.json" > "$RUN/pass2_$1_$2.log" 2>&1
  grep -A60 "RUN SUMMARY" "$RUN/pass2_$1_$2.log" | head -80
done
echo "== check"
$PY "$HERE/assert_dev_run.py" check "$RUN" | tee "$RUN/check.txt"
