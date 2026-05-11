# 0009 — Structured logging

- Status: Accepted
- Date: 2026-05-12
- Deciders: @P4suta

## Context

User `feedback_dev_observability`: rich error context + tracing spans + diagnostic test harness が無いと opaque failure × Docker iteration で session が stall する。`print()` は構造化できず CI ログでも追跡できない。

## Decision

**`structlog` を logging の唯一の path** とする。`print()` は defensive grep で禁止 ([ADR-0008](0008-strict-tooling-defensive-gates.md))。

### 設定 (`src/asmr_balance/logging.py`)

- TTY: `ConsoleRenderer(colors=True)` で人間可読 (rich とは別系統)
- 非 TTY (CI / pipe): `JSONRenderer()` で 1 行 1 イベントの JSON
- 全イベントに `timestamp`, `level`, `event`, `module` 付与
- per-stage span: `decode`, `stream`, `analyzer.<name>`, `pipeline`, `report` の context bind

### 必須 fields

- `file_path` (解析対象)
- `analyzer` (Analyzer name)
- `stage` (decode | stream | analyze | flag | report)
- error 時: `error.type`, `error.message`, `error.traceback`

### CLI 制御

- `--log-level debug|info|warning|error` (default `info`)
- `--log-json` で TTY でも強制 JSON

## Consequences

- ✓ Docker iteration の opaque failure を JSON で grep / jq できる。
- ✓ `print()` 禁止が CI gate で機械的に enforced。
- ✗ `structlog` の dependency が production に追加 (rich とは別)。許容範囲。
