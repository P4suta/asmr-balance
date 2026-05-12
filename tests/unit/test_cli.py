"""Tests for the typer CLI surface."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl
import soundfile as sf
from typer.testing import CliRunner

from asmr_balance import __version__
from asmr_balance.cli import app


def _stereo_wav(path: Path) -> Path:
    rng = np.random.default_rng(seed=0)
    samples = (rng.standard_normal((4800, 2)) * 0.1).astype(np.float32)
    sf.write(str(path), samples, 48000, subtype="FLOAT")
    return path


_runner = CliRunner()


def test_version_command() -> None:
    result = _runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_version_flag_short() -> None:
    result = _runner.invoke(app, ["-V"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_schema_json_format() -> None:
    result = _runner.invoke(app, ["schema", "--format", "json"])
    assert result.exit_code == 0
    columns = json.loads(result.stdout)
    assert isinstance(columns, list)
    assert "meta.file_path" in columns
    assert "loudness.lufs_i_stereo" in columns
    assert "band.third_octave.b_1000hz" in columns


def test_schema_plain_format() -> None:
    result = _runner.invoke(app, ["schema"])
    assert result.exit_code == 0
    assert "loudness.lufs_i_stereo" in result.stdout


def test_scan_command_writes_parquet(tmp_path: Path) -> None:
    src = _stereo_wav(tmp_path / "x.wav")
    out = tmp_path / "report.parquet"
    result = _runner.invoke(
        app, ["scan", str(src), "--out", str(out), "--no-summary", "--workers", "1"]
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    df = pl.read_parquet(out)
    assert df.height == 1


def test_scan_command_no_files_exits_1(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = _runner.invoke(app, ["scan", str(empty), "--out", str(tmp_path / "r.parquet")])
    assert result.exit_code == 1


def test_inspect_command_outputs_metrics(tmp_path: Path) -> None:
    src = _stereo_wav(tmp_path / "y.wav")
    result = _runner.invoke(app, ["inspect", str(src)])
    assert result.exit_code == 0
    assert "loudness.lufs_i_stereo" in result.stdout
