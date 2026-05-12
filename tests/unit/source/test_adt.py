"""Tests for the source ADT (Source / SkipReason)."""

from __future__ import annotations

from pathlib import Path

import pytest

from asmr_balance.metrics.record import FileMeta
from asmr_balance.source.adt import LayoutPolicy, SkipLayout, SkipMono, Source


def _meta() -> FileMeta:
    return FileMeta(
        file_path=Path("/tmp/x.wav"),
        sample_rate=48000,
        duration_sec=10.0,
        channel_layout="stereo",
    )


def test_layout_policy_values() -> None:
    assert {p.value for p in LayoutPolicy} == {"fl-fr", "downmix", "native-weighted", "skip"}


def test_source_is_frozen() -> None:
    s = Source(meta=_meta(), n_channels=2, block_samples=4800, layout_policy=LayoutPolicy.DOWNMIX)
    with pytest.raises(AttributeError):
        s.n_channels = 3  # type: ignore[misc]


def test_skip_mono_default_reason() -> None:
    skip = SkipMono(meta=_meta())
    assert "mono" in skip.reason.lower()


def test_skip_layout_carries_channels_and_reason() -> None:
    skip = SkipLayout(meta=_meta(), n_channels=6, reason="policy=skip")
    assert skip.n_channels == 6
    assert skip.reason == "policy=skip"
