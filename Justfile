# asmr-balance — all recipes route through `docker compose run`
# Host-side ripgrep is used for defensive grep (rg is User-environment global).

set shell := ["bash", "-cu"]
set dotenv-load := true

DC := "docker compose run --rm app"

[private]
default:
    @just --list --unsorted

# --- bootstrap --------------------------------------------------------

bootstrap:
    docker compose build
    {{DC}} uv sync --all-groups
    {{DC}} uv run pre-commit install --install-hooks
    {{DC}} uv run pre-commit install --hook-type commit-msg

# --- format / lint ----------------------------------------------------

fmt:
    {{DC}} uv run ruff format .

lint: lint-static lint-defensive

lint-static:
    {{DC}} uv run ruff check .
    {{DC}} uv run ruff format --check .
    {{DC}} uv run basedpyright .
    {{DC}} uv run bandit -c pyproject.toml -r src
    {{DC}} uv run vulture src --min-confidence 70

lint-defensive:
    @echo "→ defensive grep gates (host rg)"
    @! rg -nP '^\s*print\(' src/ tests/ || (echo "print() forbidden — use structlog" && exit 1)
    @! rg -nP '#\s*TODO(?!\(#\d+\))' src/ || (echo "TODO must include (#issue)" && exit 1)
    @! rg -nP '#\s*type:\s*ignore(?!\[[\w,-]+\])' src/ || (echo "# type: ignore must specify rule code" && exit 1)
    @! rg -nP '#\s*noqa(?!:\s*\w+)' src/ || (echo "# noqa must specify rule code" && exit 1)
    @! rg -nP '^\s*except\s*:' src/ || (echo "bare except forbidden" && exit 1)
    @! rg -nP '\beval\(|\bexec\(' src/ || (echo "eval/exec forbidden" && exit 1)
    @! rg -nP 'continue-on-error:\s*true' .github/ || (echo "continue-on-error forbidden" && exit 1)
    @! rg -nP '\b__import__\(' src/ || (echo "dynamic __import__ forbidden" && exit 1)
    @echo "✓ defensive gates passed"

upgrade-hooks:
    {{DC}} uv run pre-commit autoupdate

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

scan PATH:
    {{DC}} uv run asmr-balance scan {{PATH}}

inspect FILE:
    {{DC}} uv run asmr-balance inspect {{FILE}}

schema:
    {{DC}} uv run asmr-balance schema

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

# --- maintenance ------------------------------------------------------

clean:
    rm -rf .pytest_cache .ruff_cache .basedpyright .mutmut-cache .hypothesis \
           .coverage coverage.xml htmlcov dist build *.egg-info \
           docs/api site report report.parquet report.html bom.json
