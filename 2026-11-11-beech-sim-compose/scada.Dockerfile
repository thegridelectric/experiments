# syntax=docker/dockerfile:1
#
# A scada from a gridworks-scada checkout, which is the build context:
#
#     docker build -f scada.Dockerfile ../../gridworks-scada
#
# The image holds the checkout's gw_spaceheat and its locked environment,
# and runs gws. What reaches the build from the checkout is what
# scada.Dockerfile.dockerignore lets through: no .env, no .venv.

FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
RUN uv sync --locked --no-dev
COPY gw_spaceheat/ gw_spaceheat/

RUN useradd --create-home scada
USER scada
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["python", "gw_spaceheat/gws"]
CMD ["run", "--message-summary"]
