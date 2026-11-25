#!/usr/bin/env bash
# The simulated Beech layout pairs, under the names a scada reads:
# hardware-layout.json and operational-params.json.
#
#     ./gen_layout.sh
#
# Writes ./house (AllTanks, d1.isone.me.versant.keene.beech.at) and
# ./house-buffer (BufferOnly, d1.isone.me.versant.keene.beech.buf) from
# tlayouts at the commit sources.txt names, with the generator run in the
# environment of the scada at its commit there.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$HERE/fetch-sources.sh"
TREE="$HERE/.sources/tlayouts"
SCADA_REPO="$HERE/.sources/gridworks-scada"

mkdir -p "$HERE/house" "$HERE/house-buffer"
(cd "$SCADA_REPO" && uv run --locked python "$HERE/beech_sim_gen.py" "$TREE" \
    "$HERE/house" d1.isone.me.versant.keene.beech.at AllTanks)
(cd "$SCADA_REPO" && uv run --locked python "$HERE/beech_sim_gen.py" "$TREE" \
    "$HERE/house-buffer" d1.isone.me.versant.keene.beech.buf BufferOnly)
cp "$HERE/house/plant-overrides.json" "$HERE/house-buffer/plant-overrides.json"
