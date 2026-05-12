"""Tests for :class:`asmr_balance.sink.parquet.ParquetSink`."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest
import soundfile as sf

from asmr_balance.config.model import Config
from asmr_balance.scan.pipeline import scan_one
from asmr_balance.sink.base import COLUMN_NAMES
from asmr_balance.sink.parquet import ParquetSink


def _stereo_wav(path: Path, sample_rate: int = 48000) -> Path:
    rng = np.random.default_rng(seed=0)
    samples = (rng.standard_normal((sample_rate // 4, 2)) * 0.1).astype(np.float32)
    sf.write(str(path), samples, sample_rate, subtype="FLOAT")
    return path


def test_parquet_sink_writes_one_row_per_result(tmp_path: Path) -> None:
    src = _stereo_wav(tmp_path / "a.wav")
    out = tmp_path / "report.parquet"
    sink = ParquetSink(path=out)
    sink.open()
    sink.write(scan_one(src, Config()))
    sink.close()
    df = pl.read_parquet(out)
    assert df.height == 1


def test_parquet_sink_schema_matches_column_names(tmp_path: Path) -> None:
    src = _stereo_wav(tmp_path / "a.wav")
    out = tmp_path / "report.parquet"
    sink = ParquetSink(path=out)
    sink.open()
    sink.write(scan_one(src, Config()))
    sink.close()
    df = pl.read_parquet(out)
    assert tuple(df.columns) == COLUMN_NAMES


def test_parquet_sink_rejects_write_before_open(tmp_path: Path) -> None:
    src = _stereo_wav(tmp_path / "a.wav")
    sink = ParquetSink(path=tmp_path / "out.parquet")
    with pytest.raises(RuntimeError, match="before open"):
        sink.write(scan_one(src, Config()))


def test_parquet_sink_close_without_open_is_noop(tmp_path: Path) -> None:
    sink = ParquetSink(path=tmp_path / "out.parquet")
    # Should not raise.
    sink.close()


def test_parquet_sink_preserves_flag_codes_as_list(tmp_path: Path) -> None:
    # Use intentionally panned audio so at least one flag fires.
    rng = np.random.default_rng(seed=0)
    samples = (rng.standard_normal((48000, 2)) * 0.1).astype(np.float32)
    samples[:, 1] *= 0.01  # 40 dB pan → big delta_lu
    p = tmp_path / "panned.wav"
    sf.write(str(p), samples, 48000, subtype="FLOAT")
    out = tmp_path / "report.parquet"
    sink = ParquetSink(path=out)
    sink.open()
    sink.write(scan_one(p, Config()))
    sink.close()
    df = pl.read_parquet(out)
    codes = df.select("flag_codes").to_series().to_list()[0]
    assert "LR_BALANCE_FAIL" in codes
