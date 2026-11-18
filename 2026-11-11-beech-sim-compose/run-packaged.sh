#!/usr/bin/env bash
# Start the sim from a zip ./package.sh wrote. Load the packed images,
# import the bruce volume if it is packed, then play the pod. Stop with
# ./stop.sh.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=images.sh
source "$HERE/images.sh"
cd "$HERE"

if [[ -f MANIFEST ]]; then
    packed_arch="$(awk -F= '/^arch=/{print $2}' MANIFEST)"
    here_arch="$(uname -m)"
    if [[ -n "$packed_arch" && "$packed_arch" != "$here_arch" ]]; then
        echo "this package is $packed_arch; this box is $here_arch" >&2
        exit 1
    fi
fi

if podman pod exists beech-sim; then
    echo "beech-sim is already up. Stop it with ./stop.sh" >&2
    exit 1
fi

for need in pod.yaml house/hardware-layout.json house/operational-params.json \
    house/plant-overrides.json house/ta-deed.json flo/g.node.gt.json \
    journal_boot.py price.env mm.env; do
    if [[ ! -e "$need" ]]; then
        echo "missing $need" >&2
        exit 1
    fi
done

if [[ -f images.tar.gz ]]; then
    echo "loading images.tar.gz"
    gzip -dc images.tar.gz | podman load
elif [[ -f images.tar ]]; then
    echo "loading images.tar"
    podman load -i images.tar
else
    echo "no images.tar.gz or images.tar in $HERE" >&2
    exit 1
fi

if [[ -f bruce.tar ]]; then
    if podman volume exists "$BRUCE_VOLUME"; then
        echo "volume $BRUCE_VOLUME already exists; leaving it"
    else
        podman volume create "$BRUCE_VOLUME" >/dev/null
        echo "importing $BRUCE_VOLUME from bruce.tar"
        podman volume import "$BRUCE_VOLUME" bruce.tar
    fi
elif ! podman volume exists "$BRUCE_VOLUME"; then
    echo "no bruce.tar and no $BRUCE_VOLUME volume." >&2
    echo "Fill it before the pod starts:" >&2
    echo "  podman volume create --ignore $BRUCE_VOLUME" >&2
    echo "  podman run --rm --memory 8g --cpus 1 \\" >&2
    echo "    -e CAN_COMPUTE_TRANSITION_MATRICES=true -e BRUCE_BASE_PATH=/bruce \\" >&2
    echo "    -v $BRUCE_VOLUME:/bruce:U -v ./house:/house:ro,z \\" >&2
    echo "    -v ./flo_matrix.py:/flo_matrix.py:ro,z \\" >&2
    echo "    --entrypoint python localhost/beech-sim_flo:latest \\" >&2
    echo "    /flo_matrix.py /house" >&2
    exit 1
fi

mkdir -p events eventstore
podman kube play pod.yaml
echo "web app: http://localhost:5173/gridworks-web-frontend/  (beech / beech)"
