"""Tests for :func:`asmr_balance.scan.parallel.scan_many`."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from asmr_balance.config.model import Config
from asmr_balance.scan.parallel import scan_many


def _stereo_wav(path: Path) -> Path:
    rng = np.random.default_rng(seed=0)
    samples = (rng.standard_normal((4800, 2)) * 0.1).astype(np.float32)
    sf.write(str(path), samples, 48000, subtype="FLOAT")
    return path


def test_scan_many_sequential_yields_one_result_per_file(tmp_path: Path) -> None:
    paths = [_stereo_wav(tmp_path / f"f{i}.wav") for i in range(3)]
    cfg = Config(workers=1)
    results = list(scan_many(paths, cfg))
    assert len(results) == 3
    seen = {r.record.meta.file_path for r in results}
    assert seen == set(paths)


def test_scan_many_empty_input_yields_nothing(tmp_path: Path) -> None:
    cfg = Config(workers=1)
    assert list(scan_many([], cfg)) == []


def test_scan_many_processpool_smoke(tmp_path: Path) -> None:
    paths = [_stereo_wav(tmp_path / f"f{i}.wav") for i in range(2)]
    cfg = Config(workers=2)
    results = list(scan_many(paths, cfg))
    assert len(results) == 2
    # All results are pickle-safe (they returned through ProcessPoolExecutor).
    for r in results:
        assert r.record is not None
