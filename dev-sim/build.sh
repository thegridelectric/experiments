#!/usr/bin/env bash
# Build the sim's localhost images. ./run.sh calls this, then plays the
# pod. ./package.sh calls it under --build.
#
# Every image is built from ./.sources/<repo>, which fetch-sources.sh
# puts at the commit sources.txt names. Each image is labelled with that
# commit: podman image inspect --format '{{index .Labels "gw.source"}}'.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=images.sh
source "$HERE/images.sh"
cd "$HERE"
./fetch-sources.sh

source_label() {
    echo "gw.source=$1@$(git -C ".sources/$1" rev-parse HEAD)"
}
set -x

podman build -t localhost/beech-sim_plant:latest \
    --label "$(source_label gridworks-terminalasset)" \
    .sources/gridworks-terminalasset
podman build -t localhost/beech-sim_scada:latest \
    --label "$(source_label gridworks-scada)" \
    -f scada.Dockerfile .sources/gridworks-scada
podman build -t localhost/beech-sim_flo:latest -f flo.Dockerfile \
    --ignorefile flo.Dockerfile.dockerignore \
    --label "$(source_label gridworks-flo)" \
    --label "gw.source.bruce=$(git -C .sources/optimal-flexibility rev-parse HEAD)" \
    --build-context bruce=.sources/optimal-flexibility .sources/gridworks-flo
podman build -t localhost/beech-sim_price:latest -f price.Dockerfile \
    --ignorefile price.Dockerfile.dockerignore \
    --label "$(source_label gridworks-price-forecast)" \
    .sources/gridworks-price-forecast
podman build -t localhost/beech-sim_mm:latest -f mm.Dockerfile \
    --ignorefile mm.Dockerfile.dockerignore \
    --label "$(source_label gridworks-marketmaker)" \
    .sources/gridworks-marketmaker
podman build -t localhost/beech-sim_journal:latest -f journal.Dockerfile \
    --ignorefile journal.Dockerfile.dockerignore \
    --label "$(source_label gridworks-journalkeeper)" \
    .sources/gridworks-journalkeeper
podman build -t localhost/beech-sim_ear:latest -f ear.Dockerfile \
    --ignorefile ear.Dockerfile.dockerignore \
    --label "$(source_label gridworks-ear)" \
    .sources/gridworks-ear
podman build -t localhost/beech-sim_weather:latest -f weather.Dockerfile \
    --ignorefile weather.Dockerfile.dockerignore \
    --label "$(source_label gridworks-weather-forecast)" \
    .sources/gridworks-weather-forecast
podman build -t localhost/beech-sim_web:latest -f web.Dockerfile \
    --ignorefile web.Dockerfile.dockerignore \
    --label "$(source_label gridworks-web-backend)" \
    .sources/gridworks-web-backend
podman build -t localhost/beech-sim_frontend:latest \
    -f frontend.Dockerfile \
    --ignorefile frontend.Dockerfile.dockerignore \
    --label "$(source_label gridworks-web-frontend)" \
    .sources/gridworks-web-frontend
