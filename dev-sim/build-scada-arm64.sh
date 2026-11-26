#!/usr/bin/env bash
# The scada image for a 64-bit Pi: linux/arm64, without the checkout
# virtualenv, git, uv, or the uv wheel cache.
#
#     ./build-scada-arm64.sh
#
# Prints the image size when the build finishes. Extra arguments are
# passed to podman build, before the context.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$HERE/fetch-sources.sh"
CONTEXT="$HERE/.sources/gridworks-scada"
TAG="${TAG:-scada:arm64}"

if [[ ! -e /proc/sys/fs/binfmt_misc/qemu-aarch64 ]]; then
  echo "qemu-aarch64 binfmt is not registered. Install qemu-user-static-binfmt." >&2
  exit 1
fi

podman build \
  --platform linux/arm64 \
  --ignorefile "$HERE/scada.Dockerfile.dockerignore" \
  -f "$HERE/scada.Dockerfile" \
  -t "$TAG" \
  "$@" \
  "$CONTEXT"

podman images --format '{{.Repository}}:{{.Tag}}  {{.Size}}' "$TAG"
