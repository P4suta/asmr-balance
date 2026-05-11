# asmr-balance

ASMR 音声・動画ファイルの **L/R チャンネル偏り** を ITU-R BS.1770 ベースで多軸計測する batch CLI。

> 全体平均は均衡でも局所的に片側集中する案件・dual mono として配信されてしまった案件・低域 phase 逆相・帯域別の偏り — これらを `delta_lu` / `pearson_r` / `mid_side_ratio` / `band_imbalance_*` / `sliding_max_lu` / `low_phase_coherence` の 6 軸で機械的に検査する。

## 主要 metric

| Metric | 内容 |
| --- | --- |
| `lufs_i_stereo` | ITU-R BS.1770-5 spec compliant integrated loudness |
| `single_channel_lufs_{l,r}` | K-weighted gated mean per channel (spec 外、scalar `delta_lu` の元) |
| `delta_lu` | 主 imbalance scalar (`L − R` in LU) |
| `pearson_r` | Welford online L/R correlation |
| `ms_ratio_db` | Mid/Side RMS 比 |
| `band_imbalance_{low,low_mid,high_mid,high}` | 4 帯域 (`<250 / 250-2k / 2k-8k / >8k Hz`) per-band L/R ratio |
| `sliding_{max,p95,std}_lu` | 1 s window 上の delta_lu 統計 |
| `low_phase_coherence` | <300 Hz 帯の windowed xcorr |

`OK` / `WARN` / `FAIL` flag は TOML config で閾値を override 可能。

## Quickstart

```bash
just bootstrap                       # docker build + uv sync + pre-commit install
just scan /path/to/library           # → report.parquet + report.html
just inspect /path/to/single_file.mp4
```

## 開発

```bash
just lint        # ruff + basedpyright + bandit + vulture + defensive grep
just cov         # pytest --cov-branch --cov-fail-under=100
just prop        # hypothesis property tests
just regression  # pyloudnorm ±0.1 LU parity
just mutate      # mutmut, kill rate ≥ 80% gate
just ci          # 全 gate 一括
```

詳細は `docs/adr/` の各 ADR と `docs/guide/` を参照。

## License

MIT
