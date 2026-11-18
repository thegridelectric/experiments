#!/usr/bin/env bash
# The simulated Beech layout pairs, under the names a scada reads:
# hardware-layout.json and operational-params.json.
#
#     ./gen_layout.sh
#
# Writes ./house (AllTanks, d1.isone.me.versant.keene.beech.at) and
# ./house-buffer (BufferOnly, d1.isone.me.versant.keene.beech.buf). Needs the
# sibling tlayouts checkout to hold TLAYOUTS_SHA (fetched; it need not be
# checked out) and the sibling gridworks-scada checkout, whose
# environment the generator runs in.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")/.."
TLAYOUTS_SHA=3516263
SCADA_REPO="${SCADA_REPO:-$ROOT/gridworks-scada}"

TREE="$(mktemp -d)"
trap 'rm -rf "$TREE"' EXIT
git -C "$ROOT/tlayouts" archive "$TLAYOUTS_SHA" | tar -x -C "$TREE"

mkdir -p "$HERE/house" "$HERE/house-buffer"
(cd "$SCADA_REPO" && uv run --locked python "$HERE/beech_sim_gen.py" "$TREE" \
    "$HERE/house" d1.isone.me.versant.keene.beech.at AllTanks)
(cd "$SCADA_REPO" && uv run --locked python "$HERE/beech_sim_gen.py" "$TREE" \
    "$HERE/house-buffer" d1.isone.me.versant.keene.beech.buf BufferOnly)
cp "$HERE/house/plant-overrides.json" "$HERE/house-buffer/plant-overrides.json"
