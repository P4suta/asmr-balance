# 0003 — Sample-rate policy

- Status: Accepted
- Date: 2026-05-12
- Deciders: @P4suta

## Context

ITU-R BS.1770-5 の K-weighting biquad 係数 (`b0, b1, b2, a1, a2`) は **48 kHz でのみ spec に固定値が書かれている**。他のサンプリングレートでは「周波数応答を保ったまま再計算」とだけ書かれており、具体的な方法は処理系任せ。

入力は 44.1 / 48 / 96 / 192 kHz が現実的。リサンプリングして強制 48 kHz にする選択もあるが、リサンプリング自体が周波数応答とエイリアシングを混入させるので、**生レートで動く biquad を再計算する** ほうが clean。

## Decision

**`scipy.signal.iirfilter` の bilinear transform に prewarp を加えて、各サンプルレートで biquad を再計算する。**

- Pre-filter: high-shelf, `+4 dB @ 1500 Hz, Q = 1/√2`
- RLB filter: high-pass, `38 Hz, Q = 0.5`
- 両方とも biquad 1 段、SOS 形式 (`scipy.signal.iirfilter(output='sos')`)
- 初期化は `scipy.signal.sosfilt_zi(sos) * x[0]` で steady-state、立ち上がりの transient を avoid

実装は `src/asmr_balance/dsp/kweight.py` の `make_kweighting_sos(sample_rate: int) -> SOSCoefficients` 一発で済ます。

## Consequences

- ✓ リサンプリング不要、生レートで K-weighting を当てられる。
- ✓ 48 kHz 入力では spec 固定値と numerical に一致 (`pyloudnorm` parity test で確認)。
- ✗ 非常識なサンプルレート (8 kHz など) では prewarp が 1500 Hz / 38 Hz の Nyquist に近づくが、これは ADR 範囲外 (Warning で elevate)。
