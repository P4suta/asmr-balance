"""DSP primitives: K-weighting biquads, gated integration, filterbanks, online stats.

All routines here are pure functions or small stateful accumulators that conform
to the streaming Analyzer Protocol (ADR-0001): they consume blocks via ``push``
and produce final scalars via ``finalize``.
"""
