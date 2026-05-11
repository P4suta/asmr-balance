# 0006 — Band split

- Status: Accepted
- Date: 2026-05-12
- Deciders: @P4suta

## Context

「全体は均衡だが低域だけ左偏り」のような帯域別偏りを捉えたい。選択肢:

- **1/3-octave 31 bands** — psychoacoustic に厳密、過去の audio analyzer の伝統。だが auto-flag という用途では noise が多く、解釈に手間がかかる。
- **4 bands (低 / 低中 / 高中 / 高)** — ASMR の心理音響的に十分。

## Decision

**4 帯域、Butterworth order-4 SOS filterbank** を採用。

| Band | 範囲 | 解釈 |
| --- | --- | --- |
| `low` | `< 250 Hz` | サブベース / 低音ハム / proximity の温かみ |
| `low_mid` | `250 – 2000 Hz` | ボディ・人声基底音 |
| `high_mid` | `2000 – 8000 Hz` | プレゼンス / 子音 / brushing 中心 |
| `high` | `> 8000 Hz` | air / 高域 brushing / hiss |

- フィルタは `scipy.signal.butter(N=4, output='sos')` の low-pass / band-pass / band-pass / high-pass。
- 状態は `sosfilt_zi` で steady-state 初期化、block 連結時は `zi` を持ち越し ([ADR-0001](0001-streaming-analyzer-protocol.md))。
- 出力は per-band の **L/R RMS 比 (dB)** のみ。`band_imbalance_low` 等。

### 重要な不変条件

Butterworth band-pass filter は **complementary ではない** (`Σ band_energy ≠ total_energy`)。これは imbalance 比較 (L vs R) には影響しないが、HTML レポートで「帯域別エネルギー分布」と称して総和して見せると説明事故になる。

**→ 各帯域は per-channel L/R 比のみ表示。総和は禁止。**

## Consequences

- ✓ ASMR の心理音響に沿った 4 帯域で auto-flag が回せる。
- ✓ `BAND_BIAS_{band}` flag (default `≥ 4 dB`) で帯域別偏り検出が成立。
- ✗ 1/3-octave 31 bands ほどの解像度は無い (psychoacoustic 研究目的では物足りない、将来 ADR で追加検討)。
