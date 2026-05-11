# 0007 — Gate threshold expose

- Status: Accepted
- Date: 2026-05-12
- Deciders: @P4suta

## Context

ITU-R BS.1770 の絶対 gate は `-70 LUFS`。これは broadcast コンテンツ前提の閾値で、囁き ASMR (`integrated -40 〜 -50 LUFS`, momentary 頻繁に `< -70`) には厳しすぎる。素直に適用すると `single_channel_lufs_{l,r} = -inf` になる block が頻発し、結果 file の whole-file aggregate が `-inf` になる pathology が起きる。

## Decision

3 層の対策:

1. **default は spec compliant** (`abs_gate = -70 LUFS`)。spec 準拠を default に置くことで、broadcast-grade なコンテンツとの相互運用性は維持。
2. **CLI flag で override 可能**: `--gate -70 | -90 | none`。ASMR-friendly な `-90` を選んで `single_channel_lufs` が `-inf` にならないようにするのは end user の判断。
3. **`ungated` を常に Parquet に併記**: `single_channel_lufs_ungated_{l,r}` と `delta_lu_ungated` を column として持ち、`-inf` 時の fallback として読める。HTML 凡例で gate kick 状況を表示。
4. **`GATE_REJECT_ALL` flag**: `single_channel_lufs_{l|r}` が `-inf` の場合に発火、HTML で赤マークで表示。

## Consequences

- ✓ spec 互換性と ASMR 実用性を両立。
- ✓ `-inf` で auto-flag 全失敗のような silent breakdown を防ぐ。
- ✗ Parquet schema が冗長 (`*_ungated` が 4 column 増える)。schema を読む downstream tool は基本指標 + ungated を選択的に使う。
