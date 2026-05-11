# 0010 — Release automation

- Status: Accepted
- Date: 2026-05-12
- Deciders: @P4suta

## Context

User `feedback_no_cron_in_repos`: GHA `on.schedule` 禁止、Dependabot weekly のみ例外。`feedback_prefer_latest_not_pinning`: deps は lockfile + Dependabot で最新、Actions は SHA pin + Dependabot bump。

Release は手動 tag 打ちでなく、Conventional Commits に基づいて semantic bump → tag → GitHub Release → SBOM → (Optional) PyPI publish を自動化したい。

## Decision

### Conventional Commits

- `conventional-pre-commit` で commit-msg を local 検証 ([.pre-commit-config.yaml](../../.pre-commit-config.yaml))
- 許容 type: `feat`, `fix`, `perf`, `refactor`, `style`, `test`, `build`, `ci`, `docs`, `chore`, `revert`

### Changelog

- `git-cliff` で `CHANGELOG.md` を Conventional Commits から自動生成 ([cliff.toml](../../cliff.toml))

### Release pipeline (`release.yml`)

`push` to `main` で起動。`chore(release):` で始まる commit はループ防止で skip。

1. `python-semantic-release version --commit --push --vcs-release` で
   - version bump (`feat` → minor, `fix` → patch, `BREAKING CHANGE` → major)
   - git tag `vX.Y.Z`
   - GitHub Release 作成
2. `git-cliff` で `CHANGELOG.md` 更新
3. `uv build` で wheel + sdist
4. `cyclonedx-py environment -o bom.json` で SBOM 生成
5. Artifact upload (`dist/`, `CHANGELOG.md`, `bom.json`)
6. `vars.PYPI_PUBLISH == 'true'` なら `uv publish` で PyPI (trusted publishing)

### Dependabot

| Ecosystem | 対象 | Interval |
| --- | --- | --- |
| `uv` | `uv.lock` 経由の Python deps | weekly |
| `github-actions` | `.github/workflows/*.yml` の action SHA | weekly |
| `docker` | `Dockerfile` の base image | weekly |

GHA action は初期 `@v4` 等の tag で書き始めるが、初回 Dependabot PR で SHA pin に bump される運用。手動 SHA は書かない (`feedback_consult_official_docs`: memory は仮説、docs は事実)。

### `on.schedule` は使わない

- Repo 内 workflow は `push` / `pull_request` / `workflow_dispatch` のみで trigger
- 定期実行が必要なら Dependabot を使うか、外部 (GitHub-hosted) で trigger

## Consequences

- ✓ Conventional Commits を pre-commit で強制、release pipeline が semantic bump で自動化。
- ✓ SBOM 同梱、Dependabot で deps 最新追従、Actions は SHA pin。
- ✗ `chore(release):` commit が main に積まれる (loop 防止で `release.yml` 内で if-skip)。
