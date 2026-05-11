# asmr-balance

ASMR 音声・動画ファイルの **L/R チャンネル偏り** を `ITU-R BS.1770` ベースで多軸計測する batch CLI。

- [Guide / Getting started](guide/getting-started.md)
- [CLI reference](guide/cli.md)
- [Config reference](guide/config.md)
- [Metric reference](guide/metrics.md)
- [Flag reference](guide/flags.md)
- [Architecture Decision Records](adr/index.md)
- [API reference](api/)

## なぜ多軸 ?

ASMR は意図的な panning が一級コンテンツで、単一指標 (全体平均 LUFS の差) だけでは

- 全体平均は均衡でも特定タイムに片側集中 (`sliding_max_lu`)
- 配信時に dual mono 化されている (`pearson_r ≈ 1`)
- 低域 phase 逆相で片側のサブベースが消える (`low_phase_coherence < 0`)
- 帯域別に偏り (低域は左偏り、高域は右偏り など、`band_imbalance_*`)

を捉えられない。これらを ITU-R BS.1770 K-weighting + Mid/Side decomposition + band-wise filtering + sliding window + low-band coherence の合計 6 軸 + 20+ scalar で機械検査する。

## 設計の核 (3 つの load-bearing 判断)

1. **Streaming-first pipeline** — 1 h × 48 kHz × stereo × f32 = 1.3 GB / file の RAM 展開を回避するため、Analyzer Protocol は `push(block) / finalize()` 単一 interface。詳細は [ADR-0001](adr/0001-streaming-analyzer-protocol.md)。
2. **per-channel LUFS の命名** — BS.1770 spec は channel-weighted sum の上にしか LUFS を定義していない。単独チャンネルでの計算結果は `"single-channel LUFS (non-spec)"` と呼び、spec 準拠の `LUFS_I_stereo` を必ず併記。詳細は [ADR-0004](adr/0004-per-channel-metric-semantics.md)。
3. **DSP 先、pipeline 後** — `dsp/kweight.py + gating.py + lufs.py` を `pyloudnorm` 回帰 test で固めてから pipeline を組む。詳細は [ADR-0002](adr/0002-kweighting-self-impl.md)。
