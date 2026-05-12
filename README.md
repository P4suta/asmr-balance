# asmr-balance

ASMR 音声・動画ファイルの **L/R チャンネル偏り** を ITU-R BS.1770-5 ベースで多軸計測する batch CLI。

> 全体平均は均衡でも局所的に片側集中する案件、dual mono として配信されてしまった案件、低域 phase 逆相、帯域別の偏り、inter-sample peak で clip する案件 — これらを 30+ の独立 metric と 11 のルールで機械的に検査する。
>
> ASMR でよく使われる **96 / 192 kHz** ・ **24-bit / 32-bit float** ソースを first-class でサポート (sample rate に関わらず BS.1770 parity を CI で保証)。

## v1.0.0 のアーキテクチャ

`Source ─push─▶ SignalGraph(Filter…) ─push─▶ Reducer… ─assemble─▶ MetricRecord ─rules─▶ Flags + Verdict ─▶ Sink…`

- **Filter** = Mealy stream transformer (K-weighting, 1/3-octave bandsplit, 4x oversample 等)
- **Reducer** = stream → 1 つの typed metric subtree
- **Rule** = 1 つの typed predicate × severity × threshold subtree
- **Verdict** = bounded join-semilattice (`OK ⊑ WARN ⊑ FAIL`)

詳細は `docs/adr/` (特に [0011](docs/adr/0011-signal-dag-redesign.md) /
[0012](docs/adr/0012-rule-algebra-verdict-semilattice.md) /
[0013](docs/adr/0013-dsp-science-upgrade.md)) を参照。

## 主要 metric

| Subtree | Metric | 内容 |
| --- | --- | --- |
| `loudness` | `lufs_i_stereo` | ITU-R BS.1770-5 spec-compliant integrated loudness |
| `loudness` | `single_channel_lufs_{l,r}` | K-weighted gated mean per channel (ADR-0004) |
| `loudness` | `delta_lu` | 主 imbalance scalar (`L − R` in LU) |
| `lra` | `lra_lu` | EBU R128 §3.5 loudness range (P95 − P10) |
| `lra` | `max_short_term_lufs` | 最大短期ラウドネス (3 s window) |
| `correlation` | `pearson_r` | Welford online L/R correlation |
| `correlation` | `ms_ratio_db` | Mid/Side RMS 比 |
| `band` | `{low, low_mid, high_mid, high}` | 4-band aggregate (1/3-octave roll-up) |
| `band` | `third_octave.b_*hz` | 31 個の 1/3-octave band imbalance (ANSI S1.11) |
| `sliding` | `{max, p95, std, t_max_sec}_lu` | 1 s window 上の ΔLU 統計 |
| `phase` | `low_phase_coherence` | <300 Hz 帯の Welford xcorr |
| `dynamics` | `true_peak_dbtp_{l, r, max}` | BS.1770-5 Annex 2 4x polyphase oversampling |
| `dynamics` | `psr_db` | Peak-to-short-term-loudness ratio (ASMR の囁き判定) |

`OK` / `WARN` / `FAIL` flag は階層 TOML config で閾値 override 可能:

```toml
[thresholds.lr_balance]
warn_lu = 3.0
fail_lu = 6.0

[thresholds.true_peak_clip]
warn_dbtp = -1.0
fail_dbtp = 0.0
```

## Quickstart

```bash
just bootstrap                       # docker build + uv sync + pre-commit/lefthook install
just scan /path/to/library           # → report.parquet (+ HTML / Rich summary)
just inspect /path/to/single_file.mp4
just schema --format=json            # 出力 column 一覧
```

`scan` は ProcessPoolExecutor で複数ファイル並列処理。`--workers N` で worker 数指定 (default = `os.cpu_count()`)。

## 開発

```bash
just dev         # quick loop: fmt + lint + typos + fast tests
just lint        # ruff + basedpyright + bandit + vulture + defensive grep
just cov         # pytest --cov-branch --cov-fail-under=100
just prop        # hypothesis property tests (semilattice law / IIR type-state / parity)
just regression  # pyloudnorm ±0.1 LU parity at 44.1 / 48 / 88.2 / 96 / 192 kHz
just mutate      # mutmut, kill rate ≥ 80% gate
just typos       # crate-ci/typos (audio glossary allowlist in .typos.toml)
just ci          # 全 gate 一括
```

Modern git hooks via [Lefthook](https://github.com/evilmartians/lefthook) — `just hooks-install` で
pre-commit + commit-msg + pre-push を全段 wire-up (パッケージは host 側に `mise use -g lefthook@latest` で入れる)。

## License

MIT
