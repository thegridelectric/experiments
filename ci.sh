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
2026-08-15-spruce-fancoil-dist-test/spruce_fancoil_dist_test.py
2026-08-23-spruce-store-charge-valve/charge_valve_polarity.py
2026-08-23-gw108-relay-stress/relay_stress.py
2026-09-06-spruce-pump-speed-sweep/sweep.py
2026-06-11-sim-sensor/sim_sensor_experiment.py
2026-06-11-sim-time-bridge/harness.py
2026-06-11-stale-layout-migration/layout_roundtrip_check.py
2026-06-11-stale-layout-migration/make_imaginary_layout.py
2026-06-12-sim-plant-flux/simulated_plant.py
2026-08-11-gwwf-obs-roundtrip/roundtrip.py
2026-08-11-gwwf-scheduler-witness/witness.py
2026-08-11-nws-updatetime-probe/probe.py
2026-08-12-gwwf-record-broadcast/witness.py
2026-08-12-dac-bus-bench/append_dac_writer.py
2026-08-14-sasl-mechanism-spike/actor_test.py
2026-08-14-sasl-mechanism-spike/client_test.py
2026-08-25-ops498-load/assert_dev_run.py
2026-08-25-ops498-load/seed_current_era.py
2026-08-27-ops-457-regenesis/regenesis.py
2026-09-05-dac-output-bench/bench_dispatch.py
2026-09-05-fis-gate-battery/battery.py
2026-09-05-fis-gate-battery/mint.py
2026-09-05-fis-gate-battery/rig.py
2026-09-05-fis-gate-battery/storm.py
2026-09-07-admin-reboots-picos/admin_reboots_picos.py
2026-09-07-gw108-ct-testing/capture.py
2026-09-07-gw108-ct-testing/speed-ladder/ladder.py
2026-09-07-hp-boss-admin-drive/hp_boss_admin_drive.py
2026-09-08-five-v-boss-hold/five_v_boss_hold.py
2026-09-08-spruce-admin-panel/extract_window.py
2026-09-08-spruce-admin-panel/flow_watch.py
2026-09-08-spruce-admin-panel/rig-log/afternoon/egauge_live.py
2026-09-08-spruce-admin-panel/rig_record.py'
# Top five: environments this repo lacks (smbus2 pi-only · gnr env ·
# the pi scada checkout's venv · the laptop scada venv ·
# MicroPython on-pico); next four: spruce on-box harnesses (smbus2 /
# blinka / starter_settings — the pi's starter-scripts venv). June five:
# archived records of runs that no longer reproduce (June-era APIs),
# kept verbatim as evidence. August–September additions, each importing
# an environment this repo lacks: the gwwf checkout (obs-roundtrip,
# scheduler-witness, record-broadcast, nws probe), gwsproto (dac-bus
# bench), gwbase (sasl spike, fis-gate battery), gw_data + sqlalchemy
# (ops498 load), gnr (ops-457 regenesis), gwadmin + gwproactor (dac-output
# bench, admin-reboots-picos, hp-boss-admin-drive, five-v-boss-hold),
# smbus2 and the starter-scripts venv on the pi (gw108-ct-testing capture and ladder), paho
# and the box venv (spruce-admin-panel).
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
# 2026-08-06-ads-noise/i2c.thermistor.reader.component.gt-000.json is a
# record of the pre-regenesis word (AdcAddress, Bus, SeriesResistanceKOhms);
# the registry's 000 is a different schema now and no snapshot carries the
# old one, so the file is kept verbatim as evidence and not validated.
[ "$fail" -eq 0 ] || exit 1

echo "==> ci green"
