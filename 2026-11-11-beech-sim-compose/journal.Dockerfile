# syntax=docker/dockerfile:1
#
# The journal keeper from a gridworks-journalkeeper checkout, which is
# the build context:
#
#     podman build -t localhost/beech-sim_journal:latest -f journal.Dockerfile \
#         --ignorefile journal.Dockerfile.dockerignore \
#         ../../gridworks-journalkeeper

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
COPY run_journal_keeper.py /app/run_journal_keeper.py
RUN groupadd --gid 1000 journal \
    && useradd --uid 1000 --gid 1000 --create-home journal
USER journal
ENV PATH="/app/.venv/bin:$PATH"
CMD ["python", "run_journal_keeper.py"]
