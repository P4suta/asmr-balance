"""CLI surface tests via ``typer.testing.CliRunner``."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import numpy as np
import pytest
import soundfile as sf
from typer.testing import CliRunner

from asmr_balance import __version__
from asmr_balance.cli import _python_type_name, _resolve_config, app
from asmr_balance.config import Config, LayoutPolicy

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner(mix_stderr=False)


def test_version_long_flag_prints_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_version_short_flag_prints_version() -> None:
    result = runner.invoke(app, ["-V"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_scan_requires_path_argument() -> None:
    result = runner.invoke(app, ["scan"])
    assert result.exit_code == 2


def test_inspect_renders_panel(tmp_path: Path) -> None:
    path = tmp_path / "stereo.wav"
    sf.write(str(path), np.zeros((48000, 2), dtype=np.float32), 48000)
    result = runner.invoke(app, ["inspect", str(path)])
    assert result.exit_code == 0, result.stderr
    assert "asmr-balance inspect" in result.stdout


def test_schema_prints_json() -> None:
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "delta_lu" in data
    assert data["flags"] == "list[str]"
    assert data["verdict"] == "str"


def test_log_json_flag_short_circuits_to_version_callback() -> None:
    result = runner.invoke(app, ["--log-json", "--log-level", "DEBUG", "-V"])
    assert result.exit_code == 0


def test_no_args_shows_help() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code in {0, 2}
    assert "asmr-balance" in (result.stdout + result.stderr)


def test_scan_runs_on_single_stereo_file(tmp_path: Path) -> None:
    path = tmp_path / "stereo.wav"
    sf.write(str(path), np.zeros((48000, 2), dtype=np.float32), 48000)
    out = tmp_path / "report.parquet"
    result = runner.invoke(app, ["scan", str(path), "--out", str(out)])
    assert result.exit_code == 0, result.stderr
    assert out.exists()


def test_scan_with_toml_config(tmp_path: Path) -> None:
    path = tmp_path / "stereo.wav"
    sf.write(str(path), np.zeros((48000, 2), dtype=np.float32), 48000)
    cfg = tmp_path / "c.toml"
    cfg.write_text('gate_lufs = -90.0\nlayout_policy = "fl-fr"\n', encoding="utf-8")
    out = tmp_path / "report.parquet"
    result = runner.invoke(app, ["scan", str(path), "--out", str(out), "--config", str(cfg)])
    assert result.exit_code == 0, result.stderr


def test_scan_writes_html_when_requested(tmp_path: Path) -> None:
    path = tmp_path / "stereo.wav"
    sf.write(str(path), np.zeros((48000, 2), dtype=np.float32), 48000)
    parquet_out = tmp_path / "report.parquet"
    html_out = tmp_path / "report.html"
    result = runner.invoke(
        app,
        [
            "scan",
            str(path),
            "--out",
            str(parquet_out),
            "--html",
            str(html_out),
            "--no-summary",
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert html_out.exists()
    body = html_out.read_text(encoding="utf-8")
    assert "asmr-balance" in body


def test_scan_no_summary_suppresses_table(tmp_path: Path) -> None:
    path = tmp_path / "stereo.wav"
    sf.write(str(path), np.zeros((48000, 2), dtype=np.float32), 48000)
    parquet_out = tmp_path / "report.parquet"
    result = runner.invoke(app, ["scan", str(path), "--out", str(parquet_out), "--no-summary"])
    assert result.exit_code == 0, result.stderr
    assert "asmr-balance scan summary" not in result.stdout


def test_resolve_config_no_overrides_returns_defaults() -> None:
    cfg = _resolve_config(None, gate=None, layout_policy=None)
    assert isinstance(cfg, Config)
    assert cfg.gate_lufs == -70.0


def test_resolve_config_applies_overrides() -> None:
    cfg = _resolve_config(None, gate=-90.0, layout_policy=LayoutPolicy.FL_FR)
    assert cfg.gate_lufs == -90.0
    assert cfg.layout_policy is LayoutPolicy.FL_FR


@pytest.mark.parametrize(
    ("annotation_obj", "expected_fragment"),
    [
        (object(), "unknown"),
    ],
)
def test_python_type_name_falls_back_for_missing_annotation(
    annotation_obj: object, expected_fragment: str
) -> None:
    # Pass an object without ``annotation`` attribute → fallback path
    assert _python_type_name(annotation_obj) == expected_fragment
