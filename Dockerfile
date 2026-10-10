FROM python:3.12.15-slim-bookworm

# libgomp1: OpenMP runtime needed by LightGBM (Stage 4 model training)
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev
COPY src ./src
COPY migrations ./migrations
RUN uv sync --frozen --no-dev

# The deployed commit, recorded in ledger genesis/model cards/issuances (pass --build-arg GIT_SHA=$(git rev-parse HEAD)).
ARG GIT_SHA=unknown
ENV FLOODLEAD_GIT_SHA=$GIT_SHA

# Same uid/gid as the VM user that owns ARCHIVE_DIR, so archive files keep one owner.
USER 1001:1002
CMD ["floodlead", "ingest"]
