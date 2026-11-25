# syntax=docker/dockerfile:1
#
# The price-forecast service from a gridworks-price-forecast checkout,
# which is the build context. The dev GNode record is the identity the
# pod runs:
#
#     podman build -t localhost/beech-sim_price:latest -f price.Dockerfile \
#         --ignorefile price.Dockerfile.dockerignore \
#         .sources/gridworks-price-forecast
#
# Two commands of one image: `gwpf rabbit` watches ISO-NE and writes the
# kept forecast, `gwpf api` serves it.

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
COPY scripts/dev-g.node.gt.json /price/g.node.gt.json
RUN groupadd --gid 1000 price \
    && useradd --uid 1000 --gid 1000 --create-home price
USER price
ENV PATH="/app/.venv/bin:$PATH"
ENTRYPOINT ["gwpf"]
CMD ["api"]
