#!/usr/bin/env bash
# Fill the beech-sim-bruce volume with the transition matrices the FLO
# needs for the house in ./house, one per seasonal storage mode.
#
#     ./fill-bruce.sh
#
# Once per house shape or bruce tuning, before the pod starts. The FLO
# answers only plant shapes whose matrix is in the volume, and the volume
# stays across ./stop.sh. Needs the FLO image (./build.sh). Takes tens of
# minutes on one core; the output is each matrix as it is built.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=images.sh
source "$HERE/images.sh"
cd "$HERE"

if ! podman image exists localhost/beech-sim_flo:latest; then
    echo "no FLO image. Build it with ./build.sh" >&2
    exit 1
fi

podman volume create --ignore "$BRUCE_VOLUME" >/dev/null
podman run --rm --memory 8g --cpus 1 \
    -e CAN_COMPUTE_TRANSITION_MATRICES=true -e BRUCE_BASE_PATH=/bruce \
    -v "$BRUCE_VOLUME":/bruce:U -v ./house:/house:ro,z \
    -v ./flo_matrix.py:/flo_matrix.py:ro,z \
    --entrypoint python localhost/beech-sim_flo:latest \
    /flo_matrix.py /house
