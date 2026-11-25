# syntax=docker/dockerfile:1
#
# The ear, built from the gridworks-ear repository. There is no local
# checkout; the context is the git URL:
#
#     podman build -t localhost/beech-sim_ear:latest -f ear.Dockerfile \
#         --ignorefile ear.Dockerfile.dockerignore \
#         https://github.com/thegridelectric/gridworks-ear.git
#
# `ear listen --no-s3` writes each message under XDG_DATA_HOME. The pod
# sets that to the host mount.

FROM python:3.12-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
RUN uv sync --locked --no-dev && rm -rf /root/.cache/uv

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=build /app /app
RUN groupadd --gid 1000 ear \
    && useradd --uid 1000 --gid 1000 --create-home ear \
    && touch /app/.env
USER ear
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["ear"]
CMD ["listen", "--no-s3"]
