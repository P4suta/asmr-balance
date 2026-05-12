# 0013 — DSP science upgrade (True Peak, LRA, PSR, 1/3-octave bands)

- Status: Accepted (extends ADR-0002 / ADR-0006)
- Date: 2026-05-12
- Deciders: @P4suta

## Context

ASMR masters routinely ship at 96 / 192 kHz with 24-bit or 32-bit float
sample depth and aggressive dynamic range. The Phase B metric set
(integrated LUFS + ΔLU + 4-band Butterworth imbalance + low-band phase
coherence + Pearson r + M/S ratio) was tuned for typical streaming
content and missed two clinically useful axes:

1. **Inter-sample peaks** — perceived clipping on consumer DACs is
   driven by *true peak*, not sample peak. BS.1770-5 Annex 2 defines a
   4× oversampling polyphase FIR specifically for this measurement.
2. **Loudness range** — EBU R128 §3.5 defines LRA as ``P95 − P10`` of
   gated short-term loudness over the file. ASMR's "whisper-to-tap"
   dynamic profile produces distinctive LRA signatures (typically 12-18
   LU vs. 5-10 LU for streaming masters).

Additionally, the legacy 4-band Butterworth split (ADR-0006) gave only
four coarse imbalance buckets. For high-resolution analysis, ANSI S1.11
Class 1 / IEC 61260-1 1/3-octave (31 nominal centers from 20 Hz to
20 kHz) is the industry standard.

## Decision

Three always-on additions and one structural refactor.

### Always-on metrics

| Metric | Module | Rationale |
| --- | --- | --- |
| **True Peak (dBTP)** | `metrics.dynamics.TruePeakReducer` | BS.1770-5 Annex 2, 4× oversampling via `nodes.oversample.Oversample4xPolyphase` (Kaiser-windowed 49-tap FIR, polyphase-decomposed). Per-channel + max. |
| **LRA (LU)** | `metrics.lra.LRAReducer` | EBU R128 §3.5. Short-term LUFS via `nodes.zblocks.ShortTermZBlocksFilter` (3 s / 100 ms hop), gated at `-70 LUFS` absolute and `-20 LU` relative; `P95 − P10` of survivors. Also exposes `max_short_term_lufs`. |
| **PSR (dB)** | `metrics.dynamics.derive_psr_db` | Peak-to-short-term-loudness ratio; derived from TruePeak + LRA in the `assemble` step (no separate reducer). High PSR (>20 dB) signals "quiet content with peaks" — typical of ASMR. |

### Band-split refactor

The 4-band Butterworth filterbank from ADR-0006 is **replaced** by a
single 1/3-octave 31-band split (`nodes.bandsplit.ThirdOctaveBandSplit`,
4th-order Butterworth band-passes at ISO 266 preferred centers).
The four legacy aggregates (`low / low_mid / high_mid / high`) are
recovered as a **mathematical roll-up** of the 31-band ``Σ L²`` and
``Σ R²`` accumulators (`metrics.band.BandImbalanceReducer`) — no
additional IIR pass, no double-counting. The partition is exposed via
`FourBandPartition.from_bands(BANDS)`.

The CI band aggregation invariant is property-tested
(`tests/unit/metrics/test_band.py::test_rollup_equals_partition_sum`).

### High-sample-rate ergonomics

`Config.block_samples: int = 4800` is replaced by
`Config.block_duration_sec: float = 0.1`. The pipeline probes each file
once and chooses `round(sample_rate × block_duration_sec)`, so 192 kHz
masters get 19 200-sample blocks (still 100 ms) instead of being chopped
into 25 ms slivers that multiply the Python overhead 4×.

Pyloudnorm parity is asserted at 44.1, 48, 88.2, 96 and 192 kHz
(`tests/regression/test_pyloudnorm_parity.py::test_lufs_parity_at_high_rates`).

## Deferred

- **Spectral centroid / rolloff** — separate from imbalance, would
  warrant its own subtree (`SpectralMetrics`). Not in scope for v1.0.0.
- **Channel-wise LUFS for >stereo files** — would couple to
  `LayoutPolicy.NATIVE_WEIGHTED`; the policy is wired up but the
  graph builder still uses the stereo balance path. Phase E.
- **Custom 1/3-octave rule thresholds** — the `BAND_BIAS_*` rule fires
  on the four roll-ups by default. A future PR can layer per-band-name
  rules; the registry is parametric, so this is a registration change.

## Consequences

- ✓ ASMR-relevant metrics (PSR, LRA) are first-class.
- ✓ Frequency-domain analysis goes from 4 → 31 buckets while preserving
  the legacy 4-band exposure for backward compatibility of rule
  thresholds.
- ✓ High-rate (96 / 192 kHz) sources are first-class through both the
  block-duration ergonomics and the per-rate `@functools.cache`'d SOS
  factories.
- ✗ Parquet schema grows by ~30 columns (the 31 1/3-octave entries),
  acknowledged as v1.0.0 breaking change.
- ✗ Per-file CPU rises by the cost of 31 band-pass IIRs vs. 4 — measured
  at ~15 % vs. legacy at 48 kHz, easily amortized by file-level
  parallelism.
