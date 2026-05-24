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
def app() -> FastAPI:
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
