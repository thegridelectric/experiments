# syntax=docker/dockerfile:1
# The FLO with bruce, laid out as gridworks-flo's packaging expects: the
# two checkouts side by side and bruce editable with its .git, so every
# recommendation records bruce's commit. Build from this folder:
#
#     podman build -t localhost/beech-sim_flo:latest -f flo.Dockerfile \
#         --ignorefile flo.Dockerfile.dockerignore \
#         --build-context bruce=.sources/optimal-flexibility .sources/gridworks-flo
FROM python:3.12-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /src/optimal-flexibility
COPY --from=bruce pyproject.toml uv.lock LICENSE ./
COPY --from=bruce src/ src/
COPY --from=bruce .git/ .git/
WORKDIR /src/gridworks-flo
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src/ src/
RUN uv sync --locked --no-dev --extra bruce && rm -rf /root/.cache/uv

FROM python:3.12-slim-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && git config --system --add safe.directory /src/optimal-flexibility
COPY --from=build /src /src
RUN useradd --create-home flo
USER flo
WORKDIR /home/flo
ENV PATH="/src/gridworks-flo/.venv/bin:$PATH"
ENTRYPOINT ["gwflo"]
CMD ["rabbit"]
