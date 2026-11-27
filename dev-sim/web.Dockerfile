# syntax=docker/dockerfile:1
#
# The web backend from a gridworks-web-backend checkout, which is the
# build context. Two commands of one image: `python -m api` on port
# 8000, `python -m gateway` on port 8100.
#
#     podman build -t localhost/beech-sim_web:latest -f web.Dockerfile \
#         --ignorefile web.Dockerfile.dockerignore \
#         .sources/gridworks-web-backend

FROM python:3.12-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
# --frozen installs the lock as it is. --locked would first check the lock
# against pyproject.toml, which needs the optional rerun group's bruce
# package at ../optimal-flexibility, and the image does not install it.
RUN uv sync --frozen --no-dev && rm -rf /root/.cache/uv

FROM python:3.12-slim-bookworm
WORKDIR /app
COPY --from=build /app /app
COPY api/ api/
COPY gateway/ gateway/
RUN touch /app/.env
ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "-m", "api"]
