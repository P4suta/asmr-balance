# asmr-balance — all recipes route through `docker compose run` so they
# reproduce CI exactly on any developer machine.
#
# Categories:
#   bootstrap   …  one-shot env setup, docker build, hook install
#   fmt / lint  …  static checks (ruff / basedpyright / bandit / vulture / typos)
#   test       …  pytest matrix
#   run        …  CLI shortcuts (scan, inspect, schema)
#   docs/release …  documentation + release tooling
#   hooks      …  Lefthook + pre-commit management
#   ci          …  aggregate everything
#
# Naming convention: kebab-case (matches just's default).

set shell := ["bash", "-cu"]
set dotenv-load := true

DC := "docker compose run --rm app"

[private]
default:
    @just --list --unsorted

# --- bootstrap --------------------------------------------------------

# Build the image, install Python deps, and wire up git hooks.
bootstrap: docker-build hooks-install
    {{DC}} uv sync --all-groups

docker-build:
    docker compose build

# --- fmt / lint -------------------------------------------------------

# `just fmt` applies auto-fixes (ruff --fix) AND format. ユーザー要望: 機械
# 修正は default で適用、手動レビューが必要なものだけ残す。
fmt:
    {{DC}} uv run ruff check . --fix
    {{DC}} uv run ruff format .

lint: lint-static lint-defensive typos

lint-static:
    {{DC}} uv run ruff check .
    {{DC}} uv run ruff format --check .
    {{DC}} uv run basedpyright --level error .
    {{DC}} uv run bandit -c pyproject.toml -r src
    {{DC}} uv run vulture src --min-confidence 70

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

# Run typos against the whole repo via the pre-commit hook (so the binary is
# managed by pre-commit's cache — no need to install crate-ci/typos on the
# host or in the project image).
typos:
    {{DC}} uv run pre-commit run typos --all-files

# --- test -------------------------------------------------------------

test:
    {{DC}} uv run pytest -m "not bench and not slow"

cov:
    {{DC}} uv run pytest

prop:
    HYPOTHESIS_PROFILE=ci {{DC}} uv run pytest tests/property -m property

regression:
    {{DC}} uv run pytest tests/regression -m regression

e2e:
    {{DC}} uv run pytest tests/e2e -m e2e

mutate:
    {{DC}} uv run mutmut run
    {{DC}} uv run mutmut results

audit:
    {{DC}} uv run pip-audit

bench:
    {{DC}} uv run pytest tests/bench --benchmark-only -m bench

# --- run --------------------------------------------------------------

scan PATH *FLAGS:
    {{DC}} uv run asmr-balance scan {{PATH}} {{FLAGS}}

inspect FILE *FLAGS:
    {{DC}} uv run asmr-balance inspect {{FILE}} {{FLAGS}}

schema *FLAGS:
    {{DC}} uv run asmr-balance schema {{FLAGS}}

# --- hooks (Lefthook + pre-commit) -----------------------------------

# Install both Lefthook (fast, parallel) and pre-commit (CI-canonical) hooks.
hooks-install:
    @echo "→ installing pre-commit hooks"
    {{DC}} uv run pre-commit install --install-hooks
    {{DC}} uv run pre-commit install --hook-type commit-msg
    @echo "→ installing lefthook hooks (host)"
    @command -v lefthook >/dev/null 2>&1 && lefthook install || echo "  (lefthook not installed — run 'mise use -g lefthook@latest' to enable)"

# Alias for the umbrella hooks command.
hooks: hooks-install

upgrade-hooks:
    {{DC}} uv run pre-commit autoupdate

# --- docs / release ---------------------------------------------------

docs:
    {{DC}} uv run mkdocs build
    {{DC}} uv run pdoc src/asmr_balance -o docs/api

changelog:
    {{DC}} uv run git-cliff -o CHANGELOG.md

sbom:
    {{DC}} uv run cyclonedx-py environment -o bom.json

# --- CI aggregate -----------------------------------------------------

ci: lint cov prop regression e2e audit
    @echo "✓ all gates green"

# Quick developer-loop check: format + lint + fast tests + typos.
dev: fmt lint-static lint-defensive typos test
    @echo "✓ dev gate green"

# --- maintenance ------------------------------------------------------

clean:
    rm -rf .pytest_cache .ruff_cache .basedpyright .mutmut-cache .hypothesis \
           .coverage coverage.xml htmlcov dist build *.egg-info \
           docs/api site report report.parquet report.html bom.json
