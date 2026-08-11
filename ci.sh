#!/usr/bin/env bash
#
# ci.sh — the experiments repo gate. Three layers, per the sema-aligned
# coding maxim: types (pyright, zero errors), regeneration (emitters run
# clean and reproduce the committed instances byte-for-byte), semantics
# (every instance validates against the sema registry).
#
# The pyright gate covers EVERY .py in the repo by default (a new
# experiment's scripts are gated without editing this file); the only
# exclusions are the PYRIGHT_EXCLUDE scripts below, each importing an
# environment this repo does not have, and the vendored snapshot
# (src/, generated — gated at source in the sema repo).
#
# Requires a sibling sema checkout for `sema validate` (SEMA_REPO to
# override).
set -euo pipefail
cd "$(dirname "$0")"
SEMA_REPO="${SEMA_REPO:-$(cd ../sema && pwd)}"

echo "==> uv sync"
uv sync -q

echo "==> pyright (zero errors, all repo scripts)"
PYRIGHT_EXCLUDE='2026-08-06-ads-noise/ads_noise_experiment.py
2026-08-05-registry-projection-rig/rig_reparent.py
2026-08-10-ads-declared-rate/window_boot.py
2026-08-10-ads-declared-rate/capture_window.py
future/pico-rejoin/rejoin_trace.py
2026-06-11-sim-sensor/sim_sensor_experiment.py
2026-06-11-sim-time-bridge/harness.py
2026-06-11-stale-layout-migration/layout_roundtrip_check.py
2026-06-11-stale-layout-migration/make_imaginary_layout.py
2026-06-12-sim-plant-flux/simulated_plant.py'
# Top five: environments this repo lacks (smbus2 pi-only · gnr env ·
# the pi scada checkout's venv · the laptop scada venv ·
# MicroPython on-pico). June five: archived records of runs that no
# longer reproduce (June-era APIs), kept verbatim as evidence.
FILES=$(find . -name '*.py' -not -path './.venv/*' -not -path './src/*' \
    -not -path '*/__pycache__/*' | sed 's|^\./||' | sort \
    | grep -Fxv "$PYRIGHT_EXCLUDE")
uvx pyright@latest --pythonpath .venv/bin/python $FILES

echo "==> emitters reproduce committed instances"
# Every folder's emitter is named emit_instances.py — the glob means a
# new folder's emitter is exercised without editing this file.
for e in */emit_instances.py; do
    (cd "$(dirname "$e")" && uv run python emit_instances.py >/dev/null)
done
git diff --exit-code -- '*/instances' \
    || { echo "ERROR: emitters no longer reproduce the committed instances"; exit 1; }

echo "==> sema validate every instance"
fail=0
for f in */instances/*-000.json */instances/*/*-000.json */*-gw.readings-000.json; do
    out=$(cd "$SEMA_REPO" && uv run sema validate "$(pwd)/../experiments/$f" 2>&1 | tail -1)
    case "$out" in
        OK:*) ;;
        *) echo "INVALID: $f — $out"; fail=1 ;;
    esac
done
# The reader-component instance is valid at its OWN version; its 001->002
# upgrade is context-dependent by design, which the validate CLI cannot
# yet express — check own-version decode instead.
uv run python - <<'EOF'
import json, sys
sys.path.insert(0, "src")
from gwexp.sema.codec import SemaCodec
from gwexp.sema.types.old_versions.i2c_thermistor_reader_component_gt_000 import (
    I2cThermistorReaderComponentGt000,
)
SemaCodec().from_dict(
    json.load(open("2026-08-06-ads-noise/i2c.thermistor.reader.component.gt-000.json")),
    auto_upgrade=False, expect=I2cThermistorReaderComponentGt000)
print("reader instance: own-version decode OK")
EOF
[ "$fail" -eq 0 ] || exit 1

echo "==> ci green"
