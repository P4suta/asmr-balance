# 0008 — Strict tooling + defensive gates

- Status: Accepted
- Date: 2026-05-12
- Deciders: @P4suta

## Context

「警告を `ignore` / `suppress` / `continue-on-error` で隠さず根本 fix」「defensive gates を上流に置く」が User の常時遵守原則。Greenfield では Day 0 から CI gate を strict にしておかないと、後から戻すコストが 10× になる。

## Decision

Day 0 から以下を **全部 CI gate に**:

### Static analysis

| Tool | 設定 |
| --- | --- |
| `ruff` | `select = ["ALL"]` + 明示 ignore のみ (`D100-104, D107, COM812, ISC001, CPY001, TD002, TD003, PLR0913`) → 残 880+ rule active |
| `basedpyright` | `typeCheckingMode = "strict"` + `reportImplicitOverride`, `reportShadowedImports`, `reportUnnecessaryTypeIgnoreComment` 等 error |
| `bandit` | `bandit -c pyproject.toml -r src`、CI gate |
| `vulture` | `--min-confidence 70` で dead code 検出、CI gate |

### Test

| Tool | 設定 |
| --- | --- |
| `pytest` | `--strict-markers --strict-config` |
| `pytest-cov` | `--cov-branch --cov-fail-under=100` (`C1 100%` 不可逆) |
| `pytest-randomly` | test 順序 random で flaky 検出 |
| `hypothesis` | property test、CI profile `max_examples=10000` |
| `mutmut` | kill rate `≥ 80%` を CI gate |
| `filterwarnings = ["error"]` | warning は test failure に昇格 |

### Defensive grep gates (`just lint-defensive` / CI `defensive` job)

| パターン | 理由 |
| --- | --- |
| `print(` | `print()` 全面禁止。`structlog` 経由のみ ([ADR-0009](0009-structured-logging.md)) |
| `# TODO` without `(#nnn)` | 全 TODO は GitHub issue link 必須 |
| `# type: ignore` without `[code]` | rule code 明記必須 |
| `# noqa` without `: code` | 同上 |
| `except:` (bare) | 例外型必須 |
| `eval(`, `exec(` | 動的評価禁止 |
| `continue-on-error: true` | 警告抑制禁止 |
| `__import__(` | 動的 import 禁止 |

### Supply chain / Secrets

- `pip-audit` で CVE scan、CI gate
- `trufflehog` (CI) + `gitleaks` (pre-commit) の二重 secrets scan
- `actionlint` で GHA workflow lint
- Dependabot weekly (uv + github-actions + docker)

## Consequences

- ✓ Day 0 から strict なので「あとで厳しくする」の戻り工数が発生しない。
- ✓ 警告抑制を grep で機械的に拒否 (User `feedback_defensive_gates_upfront`)。
- ✗ `select = ["ALL"]` 由来で初回コミット時に false positive が増える可能性 → そのときは ADR 修正 + `ignore` 列に追加 + 理由明記、ad-hoc な silencing は禁止。
- ✗ `mutmut` の kill rate `80%` 越えは小規模 codebase では大変 → ADR-0008 で `80%` を CI gate に固定、Phase 0 では Phase A 完了まで lenient とし `mutate` job を `needs: test` に置くことで Phase A 完了後に enforced。
