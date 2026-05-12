"""Tests for :mod:`asmr_balance.graph.scheduler`."""

from __future__ import annotations

import numpy as np
import pytest

from asmr_balance.graph.builder import GraphBuilder
from asmr_balance.graph.scheduler import run_from_iter
from asmr_balance.graph.types import RawBlock
from asmr_balance.metrics.correlation import StereoCorrelationReducer
from asmr_balance.metrics.loudness import IntegratedLoudnessReducer


def _stereo_blocks(samples: np.ndarray, block_samples: int) -> list[RawBlock]:
    return [
        RawBlock(np.ascontiguousarray(samples[i : i + block_samples], dtype=np.float32))
        for i in range(0, len(samples), block_samples)
    ]


def test_run_empty_input_finalizes_all_reducers() -> None:
    g = GraphBuilder()
    raw = g.source()
    g.reduce("correlation", StereoCorrelationReducer(), raw)
    frozen = g.freeze()
    results = run_from_iter(frozen, raw_blocks=[])
    assert "correlation" in results
    assert results["correlation"].pearson_r != results["correlation"].pearson_r  # NaN


def test_run_drives_correlation_to_pearson_one_for_identical_channels() -> None:
    sr = 48000
    rng = np.random.default_rng(seed=0)
    sig = rng.standard_normal(sr // 2).astype(np.float32)
    stereo = np.column_stack([sig, sig])
    blocks = _stereo_blocks(stereo, 4800)

    g = GraphBuilder()
    raw = g.source()
    g.reduce("correlation", StereoCorrelationReducer(), raw)
    frozen = g.freeze()
    results = run_from_iter(frozen, blocks)
    assert results["correlation"].pearson_r == pytest.approx(1.0, abs=1e-9)


def test_run_with_zblock_chain_produces_loudness() -> None:
    sr = 48000
    # 1 s of constant amplitude — non-zero but stable; LUFS should be finite.
    stereo = np.full((sr, 2), 0.1, dtype=np.float32)
    blocks = _stereo_blocks(stereo, 4800)

    g = GraphBuilder()
    raw = g.source()
    kw = g.kweight(raw, sample_rate=sr)
    z = g.zblocks(kw, sample_rate=sr)
    g.reduce("loudness", IntegratedLoudnessReducer(), z)
    frozen = g.freeze()
    results = run_from_iter(frozen, blocks)
    # K-weighting strongly attenuates DC, so the integrated LUFS is very low.
    assert results["loudness"].lufs_i_stereo < -50.0


def test_broadcast_delivers_same_payload_to_both_consumers() -> None:
    """Two reducers on the same Stream must see identical sequences."""
    sr = 48000
    rng = np.random.default_rng(seed=1)
    stereo = rng.standard_normal((sr // 2, 2)).astype(np.float32)
    blocks = _stereo_blocks(stereo, 4800)

    g = GraphBuilder()
    raw = g.source()
    g.reduce("a", StereoCorrelationReducer(), raw)
    g.reduce("b", StereoCorrelationReducer(), raw)
    frozen = g.freeze()
    results = run_from_iter(frozen, blocks)
    assert results["a"].pearson_r == pytest.approx(results["b"].pearson_r, abs=1e-12)
    assert results["a"].ms_ratio_db == pytest.approx(results["b"].ms_ratio_db, abs=1e-12)


def test_chunked_input_matches_bulk_input() -> None:
    """The scheduler's payload ordering must respect filter associativity."""
    sr = 48000
    rng = np.random.default_rng(seed=2)
    stereo = rng.standard_normal((sr // 4, 2)).astype(np.float32)

    def _run(block_size: int) -> float:
        g = GraphBuilder()
        raw = g.source()
        kw = g.kweight(raw, sample_rate=sr)
        z = g.zblocks(kw, sample_rate=sr)
        g.reduce("loudness", IntegratedLoudnessReducer(), z)
        frozen = g.freeze()
        results = run_from_iter(frozen, _stereo_blocks(stereo, block_size))
        return results["loudness"].lufs_i_stereo

    coarse = _run(4800)  # one 100 ms block at a time
    fine = _run(480)  # ten 10 ms blocks per 100 ms slot
    assert coarse == pytest.approx(fine, abs=1e-9)
