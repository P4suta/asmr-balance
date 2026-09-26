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

# system deps: ffmpeg (PyAV needs libav at runtime), libsndfile (soundfile), ripgrep (defensive grep), git (semantic-release).
# BuildKit cache mounts persist /var/cache/apt + /var/lib/apt/lists across
# image rebuilds so cold ``docker compose build --no-cache`` skips the apt
# download stage (~50s → ~5s on Dockerfile / base-image churn).
# The ``rm /etc/apt/apt.conf.d/docker-clean`` is required because Debian's
# slim image auto-purges /var/cache/apt after install, defeating the mount.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        ripgrep \
        ca-certificates \
        curl \
        git

# uv (latest mainline from ghcr — Renovate bumps the tag)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# /app is bind-mounted from the host (uid != 0) so git refuses by default.
# pre-commit / lefthook / cyclonedx-py / git-cliff all need git to work.
RUN git config --global --add safe.directory /app

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
