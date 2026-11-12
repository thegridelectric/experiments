#!/usr/bin/env bash
# The simulated Beech's layout pair, into ./house under the names a scada
# reads: hardware-layout.json and operational-params.json.
#
#     ./gen_layout.sh
#
# Needs the sibling tlayouts checkout to hold TLAYOUTS_SHA (fetched; it
# need not be checked out) and the sibling gridworks-scada checkout, whose
# environment the generator runs in.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")/.."
TLAYOUTS_SHA=10110cc
SCADA_REPO="${SCADA_REPO:-$ROOT/gridworks-scada}"

TREE="$(mktemp -d)"
trap 'rm -rf "$TREE"' EXIT
git -C "$ROOT/tlayouts" archive "$TLAYOUTS_SHA" | tar -x -C "$TREE"

mkdir -p "$HERE/house"
(cd "$SCADA_REPO" && uv run --locked python "$HERE/beech_sim_gen.py" "$TREE" "$HERE/house")
