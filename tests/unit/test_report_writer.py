"""Tests for ``asmr_balance.report.writer``."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import polars as pl

from asmr_balance.report.writer import to_rows, write_parquet
from asmr_balance.types import FileResult, Flag, MetricRecord, Verdict

if TYPE_CHECKING:
    from pathlib import Path


def _make_result(
    *,
    file_path: Path,
    delta_lu: float = 0.0,
    verdict: Verdict = Verdict.OK,
    flags: tuple[Flag, ...] = (),
) -> FileResult:
    metrics = MetricRecord(
        file_path=file_path,
        sample_rate=48000,
        duration_sec=1.0,
        channel_layout="stereo",
        delta_lu=delta_lu,
    )
    return FileResult(metrics=metrics, flags=flags, verdict=verdict)


def test_to_rows_basic(tmp_path: Path) -> None:
    r = _make_result(file_path=tmp_path / "a.wav", delta_lu=1.5)
    rows = to_rows([r])
    assert len(rows) == 1
    assert rows[0]["delta_lu"] == 1.5
    assert rows[0]["verdict"] == "OK"
    assert rows[0]["flags"] == []


def test_to_rows_includes_flag_codes(tmp_path: Path) -> None:
    r = _make_result(
        file_path=tmp_path / "a.wav",
        delta_lu=7.0,
        verdict=Verdict.FAIL,
        flags=(Flag(code="LR_BALANCE_FAIL", severity=Verdict.FAIL, message="x"),),
    )
    rows = to_rows([r])
    assert rows[0]["flags"] == ["LR_BALANCE_FAIL"]
    assert rows[0]["verdict"] == "FAIL"


def test_to_rows_serialises_nan_and_inf(tmp_path: Path) -> None:
    metrics = MetricRecord(
        file_path=tmp_path / "x.wav",
        sample_rate=48000,
        duration_sec=1.0,
        channel_layout="stereo",
        single_channel_lufs_l=float("-inf"),
        single_channel_lufs_r=float("inf"),
        delta_lu=float("nan"),
    )
    r = FileResult(metrics=metrics, flags=(), verdict=Verdict.OK)
    row = to_rows([r])[0]
    assert math.isnan(row["delta_lu"])
    assert row["single_channel_lufs_l"] == float("-inf")
    assert row["single_channel_lufs_r"] == float("inf")


def test_write_parquet_writes_rows(tmp_path: Path) -> None:
    out = tmp_path / "report.parquet"
    r = _make_result(file_path=tmp_path / "a.wav", delta_lu=2.0)
    rows_written = write_parquet([r], out)
    assert rows_written == 1
    assert out.exists()
    df = pl.read_parquet(out)
    assert df.height == 1
    assert df["delta_lu"][0] == 2.0


def test_write_parquet_empty_creates_file_with_schema(tmp_path: Path) -> None:
    out = tmp_path / "empty.parquet"
    written = write_parquet([], out)
    assert written == 0
    assert out.exists()
    df = pl.read_parquet(out)
    assert df.height == 0
    assert "delta_lu" in df.columns
