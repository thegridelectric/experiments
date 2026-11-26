#!/usr/bin/env bash
# Build the sim images and start the pod.
#
#     ./run.sh
#
# Podman keeps the image layers. A later run reuses them and rebuilds an
# image only when that image's files have changed, so the builds stay in
# build.sh. Stop with ./stop.sh. A zip from ./package.sh is a different
# tree: its run.sh loads the packed images and does not build.
set -euxo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

if podman pod exists beech-sim; then
    echo "beech-sim is already up. Stop it with ./stop.sh" >&2
    exit 1
fi

# The registry's image is pulled, and its tag is the commit sources.txt
# names for the export the houses are copied from.
gnr_commit="$(awk '$1 == "grid-node-registry" {print $2}' sources.txt)"
if ! grep -q "grid-node-registry:${gnr_commit}\$" pod.yaml; then
    echo "pod.yaml's registry image is not at sources.txt's commit $gnr_commit" >&2
    exit 1
fi
"$HERE/houses.sh" --check
"$HERE/build.sh"
# The podman service resolves a relative hostPath from its own working
# directory, which under `podman machine` is inside the VM, so the pod is
# played with this folder's absolute path in place of each "./".
sed "s|path: \./|path: $HERE/|" pod.yaml | podman kube play -
