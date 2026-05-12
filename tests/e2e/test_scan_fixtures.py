"""End-to-end: scan a library of deterministic WAV fixtures and assert flags.

Updated for the v1 redesign:

* The parquet ``flags`` column is now :data:`flag_codes`
  (:mod:`asmr_balance.sink.base`).
* :data:`PSEUDO_MONO` and :data:`PHASE_INV_WARN` are unchanged.
* The CLI accepts ``--workers 1`` to disable :class:`ProcessPoolExecutor` for
  deterministic test runs.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from asmr_balance.cli import app
from tests.fixtures.gen_fixtures import (
    write_balanced_tone,
    write_dual_mono,
    write_panned_tone,
    write_phase_inverted,
    write_silent,
)

pytestmark = pytest.mark.e2e


@pytest.fixture
def library(tmp_path: Path) -> Path:
    write_balanced_tone(tmp_path / "B_balanced.wav")
    write_panned_tone(tmp_path / "C_panned_l.wav")
    write_dual_mono(tmp_path / "E_dual_mono.wav")
    write_phase_inverted(tmp_path / "F_phase_inv.wav")
    write_silent(tmp_path / "A_silent.wav")
    return tmp_path


def test_scan_produces_parquet_with_expected_flags(library: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    out = tmp_path / "report.parquet"
    result = runner.invoke(
        app,
        ["scan", str(library), "--out", str(out), "--workers", "1", "--no-summary"],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()

    df = pl.read_parquet(out)
    by_name = {Path(r["meta.file_path"]).name: r for r in df.to_dicts()}
    # B: identical L/R pure tone → no LR_BALANCE_FAIL. Pearson r ≈ 1 fires
    # PSEUDO_MONO so verdict is WARN.
    b_flags = by_name["B_balanced.wav"]["flag_codes"]
    assert "LR_BALANCE_FAIL" not in b_flags
    assert by_name["B_balanced.wav"]["verdict"] in {"OK", "WARN"}
    # C: ~12 dB panned → LR_BALANCE_FAIL
    assert "LR_BALANCE_FAIL" in by_name["C_panned_l.wav"]["flag_codes"]
    assert by_name["C_panned_l.wav"]["verdict"] == "FAIL"
    # E: L == R noise → PSEUDO_MONO
    assert "PSEUDO_MONO" in by_name["E_dual_mono.wav"]["flag_codes"]
    # F: phase-inverted at all frequencies → low-band coherence ≈ -1
    assert "PHASE_INV_WARN" in by_name["F_phase_inv.wav"]["flag_codes"]
    # A: silent → GATE_REJECT_ALL
    assert "GATE_REJECT_ALL" in by_name["A_silent.wav"]["flag_codes"]
