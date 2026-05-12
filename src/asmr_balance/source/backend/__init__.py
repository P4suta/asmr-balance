"""Decode backends — extension-based dispatch between soundfile and PyAV."""

from __future__ import annotations

from asmr_balance.source.backend.dispatch import (
    ProbedAudio,
    iter_pcm_frames,
    probe,
)

__all__ = ["ProbedAudio", "iter_pcm_frames", "probe"]
