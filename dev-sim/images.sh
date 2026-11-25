# The images the pod runs. Sourced by build.sh, package.sh and the
# packaged run.sh. Localhost tags are built here; the rest are pulled.
SIM_IMAGES=(
    localhost/beech-sim_plant:latest
    localhost/beech-sim_scada:latest
    localhost/beech-sim_flo:latest
    localhost/beech-sim_price:latest
    localhost/beech-sim_mm:latest
    localhost/beech-sim_journal:latest
    localhost/beech-sim_ear:latest
    localhost/beech-sim_weather:latest
    localhost/beech-sim_web:latest
    localhost/beech-sim_frontend:latest
)
PULL_IMAGES=(
    ghcr.io/thegridelectric/dev-rabbit:latest
    docker.io/library/eclipse-mosquitto:2
    docker.io/library/postgres:16
    docker.io/timescale/timescaledb-ha:pg18-ts2.25
)
ALL_IMAGES=("${SIM_IMAGES[@]}" "${PULL_IMAGES[@]}")
BRUCE_VOLUME=beech-sim-bruce
