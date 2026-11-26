#!/usr/bin/env bash
# The pod's two houses and the FLO's GNode, from the commits sources.txt
# names: ./beech1 (AllTanks), ./beech2 (BufferOnly) and ./flo.
#
#     ./houses.sh           # write them
#     ./houses.sh --check   # fail if the committed ones differ
#
# The layouts are tlayouts' sim output, the FLO's GNode is the registry's
# export, and twin_houses.py runs in the environment of the scada at its
# commit. The folders are committed, so a box that only plays the pod
# needs none of this. ./run.sh runs the check before it builds.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$HERE/fetch-sources.sh"

write() {
    (cd "$HERE/.sources/gridworks-scada" && uv run --locked python \
        "$HERE/twin_houses.py" "$HERE/.sources/tlayouts" \
        "$HERE/.sources/grid-node-registry" "$1")
}

case "${1:-}" in
    "")
        write "$HERE"
        ;;
    --check)
        fresh="$(mktemp -d)"
        trap 'rm -rf "$fresh"' EXIT
        write "$fresh"
        differ=0
        for folder in beech1 beech2 flo; do
            if ! diff -r "$fresh/$folder" "$HERE/$folder"; then
                differ=1
            fi
        done
        if [[ "$differ" -eq 1 ]]; then
            echo "the committed houses differ from sources.txt's commits;" \
                "run ./houses.sh and read the diff" >&2
            exit 1
        fi
        ;;
    *)
        echo "unknown argument: $1" >&2
        exit 1
        ;;
esac
