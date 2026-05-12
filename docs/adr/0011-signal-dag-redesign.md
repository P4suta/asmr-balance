# 0011 — Signal DAG redesign (Analyzer → Filter | Reducer)

- Status: Accepted (supersedes ADR-0001's `Analyzer` protocol)
- Date: 2026-05-12
- Deciders: @P4suta

## Context

The Phase B `Analyzer.push(block) / finalize() -> dict[str, float]` protocol
from ADR-0001 succeeded as a streaming guarantee but produced four structural
defects that grew worse with every added metric:

1. **dict-string assembly** — `pipeline._build_record` mapped analyzer
   `dict[str, float]` outputs into `MetricRecord` via 16 hand-written
   `merged.get("key", nan)` lines. Adding a metric required editing two
   unrelated files in lock-step.
2. **Hidden recomputation** — `LufsImbalanceAnalyzer` and
   `SlidingImbalanceAnalyzer` both built independent `LufsAccumulator`s,
   each running its own K-weighting + 400 ms block accumulation. The
   sliding analyzer also reached into the LUFS one's private `_acc_l.z_blocks`
   via `# noqa: SLF001`.
3. **Mixed concerns** — `Analyzer` was simultaneously a stream transformer
   (Mealy machine carrying IIR `zi`) and a reduction terminal (final
   `dict`). The two have different algebraic shapes (Mealy is not a monoid;
   reductions are) and should not share an interface.
4. **No stage typing** — every analyzer received the same `StereoBlock`.
   A typo at the call site (passing raw PCM where K-weighted samples are
   expected, or vice versa) could not be caught statically.

## Decision

Replace `Analyzer` with a typed *signal DAG* of two-kind nodes:

* **Filter** (`asmr_balance.graph.types.Filter[InP, OutP]`) — Mealy stream
  transformer with `process(payload) -> list[OutP]` and `flush()`.
  Examples: `KWeightingFilter`, `ZBlocksFilter`, `ThirdOctaveBandSplit`,
  `Oversample4xPolyphase`, `LowPassFilter`.
* **Reducer** (`asmr_balance.algebra.reducer.Reducer[In, M]`) — terminal
  that ingests stream payloads and produces *exactly one* typed
  metric subtree `M` (e.g. `LoudnessMetrics`, `BandImbalanceMetrics`).
  Reducer state is intentionally *not* required to be a monoid: file-level
  parallelism via `ProcessPoolExecutor` makes `merge` unnecessary, and the
  per-file scheduler is sequential.

Stages are typed via `typing.NewType` aliases (`RawBlock`,
`KWeightedBlock`, `ZBlock`, `ShortTermZBlock`, `LowPassBlock`,
`BandedFrame`, `OversampledBlock`); `basedpyright` strict rejects a
`Stream[RawBlock]` being plugged where a `Stream[ZBlock]` is expected.

Broadcast (one producer → many consumers) is expressed by **variable
binding**: pass the same `Stream` handle to multiple `.reduce()` calls.
There is no implicit memoization — calling `g.kweight(raw, sr)` twice
produces two independent filter nodes.

The scheduler (`asmr_balance.graph.scheduler.run`) is a Kahn-ordered push
interpreter over the algebraic sum `SourceNode | FilterNode | ReducerNode`,
dispatched via exhaustive `match` with `assert_never`.

## Consequences

- ✓ K-weighting now runs **once per file** (LUFS + Sliding share the
  same `Stream[ZBlock]`). DSP CPU dropped ~40 %.
- ✓ Low-pass <300 Hz is shared between phase coherence and the band-low
  legacy slot (now derived from 1/3-octave roll-up; see ADR-0006 revision).
- ✓ The `# noqa: SLF001` private access in `dsp/sliding.py` is gone.
- ✓ Adding a metric is now: one `Reducer` class + one subtree dataclass
  + one `.reduce(...)` call in `scan/assemble.build_default_graph`.
  No more dict-string drift.
- ✓ Stage-typed payloads catch wiring errors at type-check time.
- ✗ Intra-file chunk parallelism is rejected (IIR `zi` continuity is not
  associative — chunk-split would break BS.1770 parity). File-level
  parallelism via `ProcessPoolExecutor` saturates typical workloads
  anyway.
- ✗ If a future workload needs intra-file parallelism (TB-class single
  files), a separate `MergeableReducer(Reducer)` subprotocol can be
  added — YAGNI for now.
