# syntax=docker/dockerfile:1
#
# A scada from a gridworks-scada checkout, which is the build context:
#
#     podman build -f scada.Dockerfile \
#       --ignorefile scada.Dockerfile.dockerignore \
#       .sources/gridworks-scada
#     ./build-scada-arm64.sh
#
# The build stage installs the locked environment. The runtime stage keeps
# that environment, the protocol package it points at, and gw_spaceheat.
# Git, uv, and the uv cache stay in the build stage. What reaches the
# build from the checkout is what scada.Dockerfile.dockerignore lets
# through: no .env, no .venv.

FROM python:3.12-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
RUN uv sync --locked --no-dev && rm -rf /root/.cache/uv

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=build /app /app
COPY gw_spaceheat/ gw_spaceheat/
RUN useradd --create-home scada
USER scada
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["python", "gw_spaceheat/gws"]
CMD ["run", "--message-summary"]
