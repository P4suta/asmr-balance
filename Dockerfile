# syntax=docker/dockerfile:1.7
FROM python:3.14-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=3.14 \
    UV_COMPILE_BYTECODE=1 \
    PATH="/opt/venv/bin:${PATH}"

# system deps: ffmpeg (PyAV needs libav at runtime), libsndfile (soundfile), ripgrep (defensive grep), git (semantic-release)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        ripgrep \
        ca-certificates \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# uv (latest mainline from ghcr — Dependabot bumps the tag)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Layer cache: lockfile/manifest first, then full source
COPY pyproject.toml uv.lock* README.md ./
COPY src/asmr_balance/__init__.py src/asmr_balance/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --all-groups --no-install-project || \
    uv sync --all-groups --no-install-project

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --all-groups || uv sync --all-groups

ENTRYPOINT []
CMD ["bash"]
