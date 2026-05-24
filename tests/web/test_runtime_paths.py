from __future__ import annotations

from pathlib import Path

import pytest

from asmr_balance.web.runtime.paths import library_root, reports_root


def test_library_root_defaults_to_library(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASMR_LIBRARY_ROOT", raising=False)
    assert library_root() == Path("/library")


def test_reports_root_defaults_to_app_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASMR_REPORTS_ROOT", raising=False)
    assert reports_root() == Path("/app/reports")


def test_env_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ASMR_LIBRARY_ROOT", str(tmp_path / "lib"))
    monkeypatch.setenv("ASMR_REPORTS_ROOT", str(tmp_path / "rep"))
    assert library_root() == tmp_path / "lib"
    assert reports_root() == tmp_path / "rep"
