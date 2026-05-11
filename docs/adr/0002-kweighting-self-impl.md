# 0002 — K-weighting self-implementation

- Status: Accepted
- Date: 2026-05-12
- Deciders: @P4suta

## Context

`pyloudnorm.Meter.integrated_loudness()` は ITU-R BS.1770 の channel-weighted SUM (`-0.691 + 10·log10(Σ G_i z_i)`) を最終 scalar として返す。途中で計算する **per-channel `z_avg_gated`** は private、外から取れない。

我々が欲しい主指標 `delta_lu = single_channel_lufs_l − single_channel_lufs_r` は per-channel `z_gated` を要求するので、3 通りの選択肢がある:

- **案 A**: 片側 0 にした 2 ch 配列を 2 回測る (`Meter.integrated_loudness([L, 0])` と `[0, R]`) → spec の channel weighting (`G_l = G_r = 1.0`) に依存して片側だけが寄与する形にする。
- **案 B**: ITU-R BS.1770-5 の K-weighting biquad (pre-filter + RLB) と gated 400 ms block integration を **自前実装**。
- **案 C**: ffmpeg `ebur128` filter を subprocess で per-channel に当てる → integrated loudness は依然 channel-weighted SUM しか出ないので結局単独 ch では取れない。**却下**。

## Decision

**案 B (自前実装) を採用。**

理由:

1. **per-channel `z_gated` への直接アクセス** — pyloudnorm を fork したり monkey patch する必要がなくなる。
2. **DSP 語彙の自前化** — `K-weighting`、`gated integration` を本コードベースの一級語彙として持ち、testability と命名統制を保つ。
3. **decoupling** — pyloudnorm の公開 API (`integrated_loudness`) ではなく内部実装 (`IIRfilter`) に依存することを避ける。`pyloudnorm` は production 依存から外し、**test-only dev-dep として `LUFS_I_stereo` の回帰 test (`±0.1 LU`) にだけ使う**。

実装は `src/asmr_balance/dsp/kweight.py` に biquad、`gating.py` に block + 二段 gate state machine、`lufs.py` に `single_channel_lufs_{l,r}` + `LUFS_I_stereo` を置く。

## Consequences

- ✓ DSP layer が外部 lib の private API に依存しない。
- ✓ Sample-rate ごとの biquad 再計算 (ADR-0003) を一貫して扱える。
- ✓ `pyloudnorm` との `±0.1 LU` 回帰 test を CI で常時保証することで実装誤りを早期検出。
- ✗ ITU-R BS.1770-5 の解釈 (特に gating の per-channel/stereo combined の選択) を我々が責任を持つ → ADR-0004 と合わせて明文化する。
