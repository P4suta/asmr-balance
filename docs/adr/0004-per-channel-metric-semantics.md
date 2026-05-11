# 0004 — Per-channel metric semantics

- Status: Accepted
- Date: 2026-05-12
- Deciders: @P4suta

## Context

`ITU-R BS.1770-5` の loudness 式

$$
L_{\text{LUFS}} = -0.691 + 10\log_{10}\!\left(\sum_i G_i \cdot z_i\right)
$$

は channel-weighted **SUM** の上にしか定義されていない (`G_l = G_r = 1.0`, `G_c = 1.0`, `G_{ls} = G_{rs} = 1.41`)。単独チャンネルで同じ式を回した値は spec の外で、`LUFS_L` と呼ぶと EBU R128 リテラシーのある読者が必ず混乱する。

しかし ASMR の左右偏り検査では、**per-channel の loudness 相当量** こそが欲しい。

## Decision

per-channel 量に固有の命名と二重出力を行う:

- per-channel 量は **`"single-channel LUFS (non-spec compliant)"`** と呼ぶ。Parquet column 名は `single_channel_lufs_l`, `single_channel_lufs_r`。HTML 脚注・Parquet column comment・TUI 凡例で spec 脱規であることを必ず明示。
- 主 imbalance scalar は **`delta_lu = single_channel_lufs_l − single_channel_lufs_r`**。同じ pipeline で計算した 2 量の差なので絶対値の spec 脱規が相対量として打ち消され、auto-flag に使える clean な scalar。
- 併記する **`LUFS_I_stereo`** は BS.1770-5 spec compliant な channel-weighted SUM。`pyloudnorm.Meter.integrated_loudness()` と `±0.1 LU` で一致することを CI 回帰 test で常時保証 ([ADR-0002](0002-kweighting-self-impl.md))。

### Gating の per-channel/stereo combined 区別

- **絶対 gate (`-70 LUFS`)** は **per-channel 独立** に適用。片側だけ silent な場合に、もう片側が gate 通過してしまう不変条件を維持。
- **相対 gate (`mean − 10 LU`)** は **stereo combined** で計算。spec 準拠の `LUFS_I_stereo` 用と single-channel 用で別の reference mean を使うと値が両者で乖離して読みづらい。

## Consequences

- ✓ ASMR の左右偏り検査に必要な per-channel scalar が手に入り、命名で spec 脱規を読者に通告できる。
- ✓ `delta_lu` という scalar 1 つで `LR_BALANCE_WARN/FAIL` flag を回せる。
- ✗ 命名が冗長 (`single_channel_lufs_l` は 22 文字)。column header の読みやすさは HTML 側で alias を当てる。
