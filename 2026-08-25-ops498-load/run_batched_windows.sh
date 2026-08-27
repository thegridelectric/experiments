#!/usr/bin/env bash
# Continue run 20260825T2008: windows 2-4 of pass 2 with batched commits, then check.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"; JK="$HERE/../../gridworks-journalkeeper"
RUN="$HERE/runs/20260825T2008"
export DEV_DB_URL="postgresql+psycopg2://gw_journalkeeper:changeme@localhost:5433/tsdb"
export GJK_DB_URL="$DEV_DB_URL"
cd "$JK"
for w in "2024-12-10 2024-12-12" "2025-02-15 2025-02-17" "2025-12-20 2025-12-22"; do set -- $w
  t0=$(date +%s)
  uv run --project "$JK" python -m gjk.s3_message_importer --workers 8 --batch-size 500 --start "$1" --end "$2" --message-types '~layout.lite' --summary-json "$RUN/pass2_$1_$2.json" > "$RUN/pass2_$1_$2.batched.log" 2>&1
  n=$(grep -o 'messages processed: [0-9]*' "$RUN/pass2_$1_$2.batched.log" | grep -o '[0-9]*$')
  echo "window $1..$2: $n messages in $(( $(date +%s) - t0 ))s"
done
uv run --project "$JK" python "$HERE/assert_dev_run.py" check "$RUN" | tee "$RUN/check.txt"
