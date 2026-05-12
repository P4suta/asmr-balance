# 0012 — Rule algebra + Verdict semilattice

- Status: Accepted (supersedes the flat `FlagThresholds` + monolithic
  `flags.judge`)
- Date: 2026-05-12
- Deciders: @P4suta

## Context

The Phase B `flags.judge` was eight hand-rolled `_lr_balance`,
`_local_bias`, ... functions called in sequence, each appending to a
shared `list[Flag]`. Threshold values lived in a flat
`FlagThresholds(BaseModel)` with eight unrelated floats; rule code strings
(`"LR_BALANCE_FAIL"`, ...) were textual constants scattered across the
module.

Two specific defects motivated a rewrite:

1. **Verdict aggregation went through an int round-trip**
   (`max(_RANK[v] for v in flags)` → `_INVERSE_RANK[rank]`). This is the
   pattern that betrays a missing semilattice abstraction.
2. **`StrEnum.__or__` would have been mathematically incorrect.** If we
   had used `StrEnum(int, ...)` for Verdict, then `Verdict.OK | Verdict.WARN`
   would inherit `IntFlag`'s bitwise OR through integer promotion. We need
   a closed binary operation on `{OK, WARN, FAIL}`, not a bit-or.

## Decision

Three components, decoupled:

1. **`Verdict` is a bounded join-semilattice over `OK ⊑ WARN ⊑ FAIL`.**
   Implemented as a plain `enum.Enum` (NOT `StrEnum`) with an explicit
   `__or__` returning the maximum element. The identity is `Verdict.OK`
   (also `Verdict.bottom()`); the annihilator is `Verdict.FAIL`
   (`Verdict.top()`). `Verdict.join(iterable)` folds with `bottom()` as
   initial.

   The semilattice axioms (associativity / commutativity / idempotence,
   plus bottom identity and top annihilation) are property-tested under
   `tests/property/test_semilattice_laws.py`.

2. **A `Rule[M, T]` is a typed predicate-with-severity** that consumes a
   metric subtree `M` and a threshold subtree `T` and returns
   `Flag | None`. `None` means "rule did not fire", distinct from
   `Verdict.OK` which would mean "rule actively certified OK". Rule
   metadata (`code`, `severity_ceiling`, `metric_path`, `threshold_path`)
   is exposed as class attributes so the registry can be discovered at
   runtime.

3. **Thresholds are owned by the rule that uses them.** Each rule has its
   own pydantic subtree in `asmr_balance.rules.thresholds`; the top-level
   `ThresholdSet` composes them in a tree mirrored by the TOML schema:

   ```toml
   [thresholds.lr_balance]
   warn_lu = 3.0
   fail_lu = 6.0
   ```

The evaluator `evaluate(rules, record, thresholds)` is now a one-line
fold: for each rule, look up its subtree by name, call `judge`, and
join the resulting severity into the running verdict.

## Consequences

- ✓ Adding a rule is: one threshold dataclass + one rule class + one
  entry on `DEFAULT_RULES`. No more `flags.judge` editing.
- ✓ Threshold TOML mirrors the rule tree structure.
- ✓ Verdict join is now a documented total operation; semilattice law
  property tests catch any future refactor regression.
- ✓ Maybe semantics (`Flag | None`) explicitly distinguish "rule didn't
  fire" from "rule judged OK". Aggregation does not have to filter `OK`
  flags out of the list.
- ✗ The textual rule code (`"LR_BALANCE_FAIL"`) is still a string; we
  could lift it to an Enum but the union would have to span the full
  rule registry (open-world) and the ergonomics aren't worth the rigor.

## Migration

The legacy `flags.judge(metrics, FlagThresholds(...))` becomes:

```python
from asmr_balance.rules import DEFAULT_RULES, ThresholdSet, evaluate

result = evaluate(DEFAULT_RULES, metric_record, ThresholdSet())
# result.flags, result.verdict
```

Threshold TOML keys are restructured:

```diff
-[flag_thresholds]
-lr_balance_warn_lu = 3.0
-lr_balance_fail_lu = 6.0
-pseudo_mono_pearson = 0.95
+[thresholds.lr_balance]
+warn_lu = 3.0
+fail_lu = 6.0
+[thresholds.pseudo_mono]
+pearson_r = 0.95
```

This is a deliberate v1.0.0 breaking change (acknowledged in the redesign
scope).
