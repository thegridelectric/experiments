#!/usr/bin/env bash
# Build the sim's localhost images. ./run.sh calls this, then plays the
# pod. ./package.sh calls it under --build.
set -euxo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=images.sh
source "$HERE/images.sh"
cd "$HERE"

podman build -t localhost/beech-sim_plant:latest \
    ../../gridworks-terminalasset
podman build -t localhost/beech-sim_scada:latest \
    -f scada.Dockerfile ../../gridworks-scada
podman build -t localhost/beech-sim_flo:latest -f flo.Dockerfile \
    --ignorefile flo.Dockerfile.dockerignore \
    --build-context bruce=../../optimal-flexibility ../../gridworks-flo
podman build -t localhost/beech-sim_price:latest -f price.Dockerfile \
    --ignorefile price.Dockerfile.dockerignore \
    ../../gridworks-price-forecast
podman build -t localhost/beech-sim_mm:latest -f mm.Dockerfile \
    --ignorefile mm.Dockerfile.dockerignore \
    ../../gridworks-marketmaker
podman build -t localhost/beech-sim_journal:latest -f journal.Dockerfile \
    --ignorefile journal.Dockerfile.dockerignore \
    ../../gridworks-journalkeeper
podman build -t localhost/beech-sim_ear:latest -f ear.Dockerfile \
    --ignorefile ear.Dockerfile.dockerignore \
    https://github.com/thegridelectric/gridworks-ear.git
podman build -t localhost/beech-sim_weather:latest -f weather.Dockerfile \
    --ignorefile weather.Dockerfile.dockerignore \
    https://github.com/thegridelectric/gridworks-weather-forecast.git
podman build -t localhost/beech-sim_web:latest -f web.Dockerfile \
    --ignorefile web.Dockerfile.dockerignore \
    ../../gridworks-web-backend
podman build -t localhost/beech-sim_frontend:latest \
    -f frontend.Dockerfile \
    --ignorefile frontend.Dockerfile.dockerignore \
    ../../gridworks-web-frontend
