# Architecture Decision Records

[MADR](https://adr.github.io/madr/) フォーマット。各 ADR は 1 つの load-bearing な判断を記録する。

| # | Title | Status |
| --- | --- | --- |
| 0001 | [Streaming Analyzer Protocol](0001-streaming-analyzer-protocol.md) | Superseded by 0011 |
| 0002 | [K-weighting self-impl](0002-kweighting-self-impl.md) | Accepted (extended by 0013) |
| 0003 | [Sample-rate policy](0003-sample-rate-policy.md) | Accepted |
| 0004 | [Per-channel metric semantics](0004-per-channel-metric-semantics.md) | Accepted |
| 0005 | [Channel layout policy](0005-channel-layout-policy.md) | Accepted (NATIVE_WEIGHTED added) |
| 0006 | [Band split](0006-band-split.md) | Reinterpreted by 0013 (4-band → 31-band roll-up) |
| 0007 | [Gate threshold expose](0007-gate-threshold-expose.md) | Accepted |
| 0008 | [Strict tooling + defensive gates](0008-strict-tooling-defensive-gates.md) | Accepted |
| 0009 | [Structured logging](0009-structured-logging.md) | Accepted |
| 0010 | [Release automation](0010-release-automation.md) | Accepted |
| 0011 | [Signal DAG redesign (Filter / Reducer)](0011-signal-dag-redesign.md) | Accepted |
| 0012 | [Rule algebra + Verdict semilattice](0012-rule-algebra-verdict-semilattice.md) | Accepted |
| 0013 | [DSP science upgrade (TruePeak / LRA / PSR / 1/3-octave)](0013-dsp-science-upgrade.md) | Accepted |
