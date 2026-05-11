# 0001 — Streaming Analyzer Protocol

- Status: Accepted
- Date: 2026-05-12
- Deciders: @P4suta

## Context

1 h × 48 kHz × stereo × f32 = **1.3 GB / file**。`ProcessPoolExecutor` で 8 並列を組むと PCM だけで 10 GB 級 RAM、worker 中間バッファを足すと swap 突入。wall time が読めなくなる。

幸い、我々が回す全 metric は **block-streaming friendly**:

| Metric | Streaming で OK |
| --- | --- |
| K-weighted LUFS | `400 ms` block 和の累積 |
| Pearson | Welford 風 online covariance (`Σx, Σy, Σxy, Σx², Σy², n`) |
| Mid/Side | per-block の `M = (L+R)/√2`, `S = (L−R)/√2` RMS 累積 |
| 4-band RMS | `sosfilt` の `zi` 保持で block 連結 |
| Sliding window | 自然に block 単位 |
| 低域 phase coherence | BPF + windowed xcorr (block 友好) |

## Decision

**Analyzer Protocol は `push(block) / finalize()` を唯一の interface とする。** RAM full PCM の materialize は禁止。

```python
class Analyzer(Protocol):
    name: ClassVar[str]
    def push(self, block: StereoBlock) -> None: ...
    def finalize(self) -> MetricRecord: ...
```

- 並列度は **ファイル並列のみ** (`ProcessPoolExecutor`)。Worker 内は逐次 (block 取得 → 全 Analyzer に fan-out)。
- block size は `K-weighting + 400 ms gating` の境界に揃える (`block_size = round(sample_rate * 0.4)`)。
- StereoBlock の型は `NDArray[np.float32]` (shape `(N, 2)`)、decode boundary でのみ runtime assert。pydantic は意味の重い型 (`Flag`, `Config`, `FileResult`) のみに使う。

## Consequences

- ✓ メモリ予算が `block_size × n_analyzers × n_workers` で線形に閉じる。
- ✓ 1 ファイルが TB 級でも理論的に動く (実用は I/O 律速)。
- ✗ Analyzer 並列は捨てる (Amdahl で旨味薄、メモリ swap risk と引き換えに合わない)。
- ✗ `numpy.corrcoef` のような全配列前提 API は使えない → Welford online 実装が必要 (ADR で別個には立てないが、`dsp/correlation.py` でこの判断を comment 化)。
