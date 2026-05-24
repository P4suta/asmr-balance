from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from asmr_balance.web import create_app
from tests.fixtures.gen_fixtures import (
    write_balanced_tone,
    write_mono,
    write_panned_tone,
)


@pytest.fixture
def library_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Empty library mounted at a tmp dir; ASMR_LIBRARY_ROOT points at it."""
    root = tmp_path / "library"
    root.mkdir()
    monkeypatch.setenv("ASMR_LIBRARY_ROOT", str(root))
    return root


@pytest.fixture
def reports_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "reports"
    root.mkdir()
    monkeypatch.setenv("ASMR_REPORTS_ROOT", str(root))
    return root


@pytest.fixture
def library_with_audio(library_root: Path) -> Path:
    """A library containing one balanced wav and one nested panned wav."""
    write_balanced_tone(library_root / "balanced.wav", duration_sec=1.0)
    sub = library_root / "album"
    sub.mkdir()
    write_panned_tone(sub / "panned.wav", duration_sec=1.0)
    return library_root


@pytest.fixture
def app(library_root: Path, reports_root: Path) -> FastAPI:
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def panned_wav(tmp_path: Path) -> Path:
    p = tmp_path / "panned.wav"
    write_panned_tone(p, duration_sec=2.5)
    return p


@pytest.fixture
def balanced_wav(tmp_path: Path) -> Path:
    p = tmp_path / "balanced.wav"
    write_balanced_tone(p, duration_sec=2.5)
    return p


@pytest.fixture
def mono_wav(tmp_path: Path) -> Path:
    p = tmp_path / "mono.wav"
    write_mono(p, duration_sec=1.0)
    return p
