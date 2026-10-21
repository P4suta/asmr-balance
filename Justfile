# asmr-balance — all recipes route through a long-running ``docker compose
# exec`` so that the per-command container-start tax (~0.5s × n) is paid
# exactly once at ``just dev-up`` (or implicitly via any aggregator
# recipe). The persistent service is defined in docker-compose.yml.
#
# Categories:
#   bootstrap   …  one-shot env setup, docker build, hook install
#   dev-up/down …  persistent app container lifecycle
#   fmt / lint  …  static checks (ruff / ty / bandit / vulture / typos)
#   test       …  pytest matrix
#   run        …  CLI shortcuts (scan, inspect, schema)
#   docs/release …  documentation + release tooling
#   hooks      …  Lefthook + pre-commit management
#   ci          …  aggregate everything
#
# Naming convention: kebab-case (matches just's default).

set shell := ["bash", "-cu"]
set dotenv-load := true

DC := "docker compose exec -T app"

[private]
default:
    @just --list --unsorted

# --- dev container lifecycle -----------------------------------------

# Start the persistent ``app`` container. Subsequent ``docker compose exec``
# calls skip the container-start tax. Idempotent — running while up is no-op.
dev-up:
    @docker compose up -d app >/dev/null

# Stop the persistent ``app`` container (named volumes preserved).
dev-down:
    docker compose stop app

# Drop into an interactive shell on the persistent app container.
shell: dev-up
    docker compose exec -it app bash

# --- bootstrap --------------------------------------------------------

# Build the image, install Python deps, and wire up git hooks.
bootstrap: docker-build dev-up hooks-install
    {{DC}} uv sync --frozen --all-groups

docker-build:
    docker compose build app

# --- fmt / lint -------------------------------------------------------

# `just fmt` applies auto-fixes (ruff --fix) AND format. ユーザー要望: 機械
# 修正は default で適用、手動レビューが必要なものだけ残す。
fmt: dev-up
    {{DC}} bash -ceu 'uv run --frozen ruff check . --fix && uv run --frozen ruff format .'

lint: lint-static lint-defensive lint-text

lint-text: typos
    mise x -- actionlint
    mise x -- gitleaks dir --redact --no-banner .

# Batched into one ``bash -ceu`` so we pay the docker-exec round-trip
# (~0.1-0.2s) once instead of five times. Fail-fast preserved via ``set -e``.
# Type checker is ``ty`` (astral) — see ``[tool.ty]`` in pyproject.toml.
lint-static: dev-up
    {{DC}} bash -ceu '\
        uv run --frozen ruff check . && \
        uv run --frozen ruff format --check . && \
        uv run --frozen ty check && \
        uv run --frozen bandit -c pyproject.toml -r src && \
        uv run --frozen vulture src --min-confidence 70'

lint-defensive:
    @echo "→ defensive grep gates (host rg)"
    @! rg -nP '^\s*print\(' src/ tests/ || (echo "print() forbidden — use structlog" && exit 1)
    @! rg -nP '#\s*TODO(?!\(#\d+\))' src/ || (echo "TODO must include (#issue)" && exit 1)
    @! rg -nP '#\s*type:\s*ignore' src/asmr_balance/ || (echo "type: ignore forbidden in src/" && exit 1)
    @! rg -nP '#\s*noqa(?!:\s*\w+)' src/asmr_balance/ || (echo "noqa without code forbidden" && exit 1)
    @! rg -nP '^\s*except\s*:' src/ || (echo "bare except forbidden" && exit 1)
    @! rg -nP '\beval\(|\bexec\(' src/ || (echo "eval/exec forbidden" && exit 1)
    @! rg -nP 'continue-on-error:\s*true' .github/ || (echo "continue-on-error forbidden" && exit 1)
    @! rg -nP '\b__import__\(' src/ || (echo "dynamic __import__ forbidden" && exit 1)
    @! rg -nP '\.(z_blocks|_acc_l|_acc_r|_zi_l|_zi_r)\b' src/ || (echo "no private DSP state access" && exit 1)
    @echo "✓ defensive gates passed"

# Text checks use native tools and do not start the app container.
typos:
    mise x -- typos

# --- test -------------------------------------------------------------

# Inner-loop test suite. ``property`` tests are excluded because Hypothesis
# shrink+example phases add ~7s and they're better suited to ``just prop``
# (or the full ``just cov``) — they catch algebraic-law regressions, not
# the kind of bugs you fix in inner dev iteration.
test: dev-up
    {{DC}} uv run --frozen pytest -m "not bench and not slow and not property"

cov: dev-up
    {{DC}} uv run --frozen pytest -n 2 --hypothesis-seed=1 --randomly-seed=1

prop: dev-up
    docker compose exec -T -e HYPOTHESIS_PROFILE=ci app uv run --frozen pytest tests/property -m property --no-cov -n 2 --hypothesis-seed=1 --randomly-seed=1

regression: dev-up
    {{DC}} uv run --frozen pytest tests/regression -m regression --no-cov

e2e: dev-up
    {{DC}} uv run --frozen pytest tests/e2e -m e2e --no-cov

mutate: dev-up
    {{DC}} uv run --frozen mutmut run
    {{DC}} uv run --frozen mutmut results

audit: dev-up
    {{DC}} uv run --frozen pip-audit

bench: dev-up
    {{DC}} uv run --frozen pytest tests/bench --benchmark-only -m bench

# --- run --------------------------------------------------------------

# `scan` / `inspect` take an arbitrary host path. We resolve it, then bind-
# mount the enclosing directory read-only at the SAME absolute path inside
# the container, so the CLI can receive the host path verbatim — no env var,
# no path translation, no copy. Reports still land in /app (= repo root).
# Scan a directory or file anywhere on the host. Reports → ./report.parquet.
scan PATH *FLAGS:
    @set -eu; \
      ABS="$(realpath -- {{quote(PATH)}})"; \
      if [ -d "$ABS" ]; then MNT="$ABS"; else MNT="$(dirname -- "$ABS")"; fi; \
      docker compose run --rm -v "$MNT:$MNT:ro" app \
        uv run --frozen asmr-balance scan "$ABS" {{FLAGS}}

# Inspect a single file anywhere on the host (Rich panel to stdout).
inspect FILE *FLAGS:
    @set -eu; \
      ABS="$(realpath -- {{quote(FILE)}})"; \
      MNT="$(dirname -- "$ABS")"; \
      docker compose run --rm -v "$MNT:$MNT:ro" app \
        uv run --frozen asmr-balance inspect "$ABS" {{FLAGS}}

schema *FLAGS: dev-up
    {{DC}} uv run --frozen asmr-balance schema {{FLAGS}}

# --- web -------------------------------------------------------------

# Start the Web UI in the background. Exposed at http://127.0.0.1:8000 by
# default (override with ASMR_WEB_HOST_PORT). The container binds 0.0.0.0;
# compose maps it onto host loopback only — see ADR-0014.
web:
    docker compose up -d --build web
    @echo "→ http://127.0.0.1:${ASMR_WEB_HOST_PORT:-8000}"

# Stop the web container (keeps the named report volume).
web-down:
    docker compose stop web

# Tail web container logs.
web-logs:
    docker compose logs -f web

# Reset the web container + report volume (factory wipe).
web-reset:
    docker compose rm -fsv web
    docker volume rm -f asmr-balance_web-reports 2>/dev/null || true

# --- hooks (Lefthook + pre-commit) -----------------------------------

# Install both Lefthook (fast, parallel) and pre-commit (CI-canonical) hooks.
hooks-install: dev-up
    @echo "→ installing pre-commit hooks"
    {{DC}} uv run --frozen pre-commit install --install-hooks
    {{DC}} uv run --frozen pre-commit install --hook-type commit-msg
    @echo "→ installing lefthook hooks (host)"
    @command -v lefthook >/dev/null 2>&1 && lefthook install || echo "  (lefthook not installed — run 'mise use -g lefthook@latest' to enable)"

# Alias for the umbrella hooks command.
hooks: hooks-install

upgrade-hooks: dev-up
    {{DC}} uv run --frozen pre-commit autoupdate

# --- docs / release ---------------------------------------------------

docs: dev-up
    {{DC}} uv run --frozen pdoc src/asmr_balance -o docs/api
    {{DC}} uv run --frozen mkdocs build --strict

package: dev-up
    {{DC}} uv build --no-sources
    {{DC}} uv run --frozen cyclonedx-py environment -o bom.json

changelog: dev-up
    {{DC}} uv run --frozen git-cliff -o CHANGELOG.md

sbom: dev-up
    {{DC}} uv run --frozen cyclonedx-py environment -o bom.json

# --- CI aggregate -----------------------------------------------------

verify-app: lint-static lint-defensive cov audit

ci: lint-text verify-app
    @echo "✓ all gates green"

# Quick developer-loop check: format + lint + fast tests + typos.
# Brings up the persistent app container once, then exec'd recipes follow.
dev: dev-up fmt lint-static lint-defensive typos test
    @echo "✓ dev gate green"

# --- maintenance ------------------------------------------------------

clean:
    rm -rf .pytest_cache .ruff_cache .mutmut-cache .hypothesis \
           .coverage coverage.xml htmlcov dist build *.egg-info \
           docs/api site report report.parquet report.html bom.json
