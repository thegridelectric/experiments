# syntax=docker/dockerfile:1
#
# The weather service from a gridworks-weather-forecast checkout, which
# is the build context:
#
#     podman build -t localhost/beech-sim_weather:latest \
#         -f weather.Dockerfile \
#         --ignorefile weather.Dockerfile.dockerignore \
#         .sources/gridworks-weather-forecast
#
# One image, three commands. `gwwf rabbit` fetches and publishes and is
# the only writer of the service's database. `gwwf api` serves the read
# façade. `gwwf create` mints one record from dev-records/.

FROM python:3.12-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src/ src/
RUN uv sync --locked --no-dev && rm -rf /root/.cache/uv

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=build /app /app
COPY alembic.ini ./
COPY alembic/ alembic/
COPY dev-records/ dev-records/
COPY scripts/dev-g.node.gt.json /weather/g.node.gt.json
RUN groupadd --gid 1000 weather \
    && useradd --uid 1000 --gid 1000 --create-home weather
USER weather
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["gwwf"]
CMD ["api"]
