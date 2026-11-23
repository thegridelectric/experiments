#!/usr/bin/env bash
# Zip the images and files another box needs to run the sim, without the
# sibling checkouts. The zip's run.sh loads the images and plays the pod.
#
#     ./package.sh
#     ./package.sh --build     # build the localhost images first
#     ./package.sh --dry-run   # list what would go in, write nothing
#
# Writes beech-sim-<utc>-<arch>.zip in this directory. It holds the ISO-NE
# accounts from ./price.env and ./mm.env, and the images this tree builds.
# The other box pulls Rabbit, Mosquitto, Postgres and Timescale.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=images.sh
source "$HERE/images.sh"
cd "$HERE"

BUILD=0
DRY=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --build) BUILD=1 ;;
        --dry-run) DRY=1 ;;
        -h|--help)
            sed -n '2,12p' "$0"
            exit 0
            ;;
        *)
            echo "unknown argument: $1" >&2
            exit 1
            ;;
    esac
    shift
done

ARCH="$(uname -m)"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
NAME="beech-sim-${STAMP}-${ARCH}"
OUT="$HERE/${NAME}.zip"

missing=()
if [[ "$BUILD" -eq 1 ]]; then
    "$HERE/build.sh"
fi
for img in "${SIM_IMAGES[@]}"; do
    if ! podman image exists "$img"; then
        missing+=("$img")
    fi
done
if [[ ${#missing[@]} -gt 0 ]]; then
    echo "images not on this box:" >&2
    printf '  %s\n' "${missing[@]}" >&2
    echo "build them with ./package.sh --build, or ./run.sh" >&2
    exit 1
fi

for need in price.env mm.env house/hardware-layout.json \
    house/operational-params.json house/plant-overrides.json \
    house/ta-deed.json flo/g.node.gt.json journal_boot.py pod.yaml \
    stop.sh flo_matrix.py; do
    if [[ ! -e "$need" ]]; then
        echo "missing $need" >&2
        exit 1
    fi
done

have_bruce=0
if podman volume exists "$BRUCE_VOLUME"; then
    have_bruce=1
fi

echo "packed images:"
printf '  %s\n' "${SIM_IMAGES[@]}"
echo "pulled on the other box:"
printf '  %s\n' "${PULL_IMAGES[@]}"
echo "files: house/ flo/ journal_boot.py pod.yaml stop.sh flo_matrix.py price.env mm.env"
if [[ "$have_bruce" -eq 1 ]]; then
    echo "bruce volume: $BRUCE_VOLUME"
else
    echo "bruce volume: none (the other box fills it with flo_matrix.py)"
fi
echo "arch: $ARCH"
if [[ "$DRY" -eq 1 ]]; then
    echo "dry-run: would write $OUT"
    exit 0
fi

STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT
ROOT="$STAGING/$NAME"
mkdir -p "$ROOT/house" "$ROOT/house-buffer" "$ROOT/flo"

echo "saving built images"
# Without --multi-image-archive every name after the first is stored as
# a tag of the first image, so the archive contains only that image.
podman save --multi-image-archive -o "$ROOT/images.tar" "${SIM_IMAGES[@]}"
gzip -1 "$ROOT/images.tar"

if [[ "$have_bruce" -eq 1 ]]; then
    echo "exporting $BRUCE_VOLUME"
    podman volume export "$BRUCE_VOLUME" -o "$ROOT/bruce.tar"
fi

cp -a house/. "$ROOT/house/"
cp -a house-buffer/. "$ROOT/house-buffer/"
cp -a flo/. "$ROOT/flo/"
cp -a journal_boot.py pod.yaml stop.sh flo_matrix.py images.sh \
    mosquitto-1884.conf price.env mm.env "$ROOT/"
cp -a run-packaged.sh "$ROOT/run.sh"
chmod +x "$ROOT/run.sh" "$ROOT/stop.sh"

{
    echo "name=$NAME"
    echo "arch=$ARCH"
    echo "packed_utc=$STAMP"
    echo "bruce=$have_bruce"
    echo "packed<<"
    printf '%s\n' "${SIM_IMAGES[@]}"
    echo ">>"
    echo "pull<<"
    printf '%s\n' "${PULL_IMAGES[@]}"
    echo ">>"
} > "$ROOT/MANIFEST"

cat > "$ROOT/README.md" <<'EOF'
A packaged Beech simulation. Needs Podman, a network to pull Rabbit,
Mosquitto, Postgres and Timescale, the same CPU architecture as the box
that wrote the zip (see `arch=` in MANIFEST), and the host ports 5173,
5433 and 8100 free.

    unzip beech-sim-*.zip
    cd beech-sim-*
    ./run.sh

Stop with `./stop.sh`. The web app is
http://localhost:5173/gridworks-web-frontend/ (login `beech` / `beech`).

`price.env` and `mm.env` are the ISO-NE accounts. They travel with the
zip. Do not put the zip somewhere public.
EOF

echo "writing $OUT"
(
    cd "$STAGING"
    zip -q -r -n .gz:.tar "$OUT" "$NAME"
)
echo "wrote $OUT ($(du -h "$OUT" | awk '{print $1}'))"
