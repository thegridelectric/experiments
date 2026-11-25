#!/usr/bin/env bash
# Stop the sim pod. The journal database goes with it. ./eventstore,
# ./events and the bruce volume stay.
#
#     ./stop.sh
set -euxo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

if ! podman pod exists beech-sim; then
    echo "beech-sim is not running"
    exit 0
fi

podman kube down pod.yaml
