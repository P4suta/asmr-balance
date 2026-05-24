from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.fixtures.gen_fixtures import write_balanced_tone


def _parse_ndjson(lines: Iterator[str]) -> list[dict[str, object]]:
    """One JSON object per non-empty line — same shape as ``InspectStream``."""
    return [json.loads(raw) for raw in lines if raw.strip()]


def _drain_stream(client: TestClient, job_id: str) -> list[dict[str, object]]:
    """Block until the scan stream closes; return every frame in order."""
    with client.stream("GET", f"/api/scan/{job_id}/stream") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/x-ndjson")
        return _parse_ndjson(resp.iter_lines())


def _wait_until(predicate, timeout: float = 10.0) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.05)
    msg = f"predicate not satisfied in {timeout}s"
    raise AssertionError(msg)


def test_post_scan_returns_job_handle(client: TestClient, library_with_audio: Path) -> None:
    response = client.post("/api/scan", json={"paths": [""]})
    assert response.status_code == 200
    body = response.json()
    assert body["total_files"] == 2
    assert body["requested_paths"] == [""]
    assert body["job_id"]


def test_post_scan_400_on_empty_paths_list(client: TestClient) -> None:
    response = client.post("/api/scan", json={"paths": []})
    assert response.status_code == 422  # Pydantic validation min_length=1
    body = response.json()
    assert body["error"] == "RequestValidationError"


def test_post_scan_400_on_empty_resolved(client: TestClient, library_root: Path) -> None:
    (library_root / "empty").mkdir()
    response = client.post("/api/scan", json={"paths": ["empty"]})
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "EmptyScanRequestError"
    assert body["context"]["requested"] == ["empty"]


def test_post_scan_404_on_missing(client: TestClient, library_root: Path) -> None:
    response = client.post("/api/scan", json={"paths": ["nope"]})
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "LibraryPathError"


def test_stream_emits_file_frames_then_done(client: TestClient, library_root: Path) -> None:
    write_balanced_tone(library_root / "x.wav", duration_sec=0.5)
    start = client.post("/api/scan", json={"paths": ["x.wav"]})
    assert start.status_code == 200
    job_id = start.json()["job_id"]

    events = _drain_stream(client, job_id)
    types = [e["type"] for e in events]
    assert "file_done" in types
    assert types[-1] == "done"

    file_event = next(e for e in events if e["type"] == "file_done")
    assert file_event["sequence"] == 1
    assert file_event["total"] == 1
    assert file_event["source_name"] == "x.wav"
    assert file_event["verdict"] in {"OK", "WARN", "FAIL"}


def test_stream_emits_failed_frame_when_job_crashes(
    client: TestClient, library_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mid-flight exception in ``scan_many`` surfaces as a terminal ``failed`` frame.

    Mirrors the inspect-stream failure contract: HTTP stays 200, the in-band
    frame carries the detail.
    """
    from asmr_balance.web.use_cases import scan as scan_module

    def explode(*_args, **_kwargs):
        message = "simulated scan crash"
        raise RuntimeError(message)

    monkeypatch.setattr(scan_module, "scan_many", explode)
    write_balanced_tone(library_root / "x.wav", duration_sec=0.3)
    start = client.post("/api/scan", json={"paths": ["x.wav"]})
    job_id = start.json()["job_id"]

    events = _drain_stream(client, job_id)
    assert events[-1]["type"] == "failed"
    detail = events[-1]["detail"]
    assert isinstance(detail, str)
    assert "simulated scan crash" in detail
    assert "RuntimeError" in detail


def test_get_scan_status_eventually_done(client: TestClient, library_root: Path) -> None:
    write_balanced_tone(library_root / "x.wav", duration_sec=0.5)
    start = client.post("/api/scan", json={"paths": ["x.wav"]})
    job_id = start.json()["job_id"]

    # Drain the stream first so we don't race the background task to completion.
    _drain_stream(client, job_id)

    _wait_until(lambda: client.get(f"/api/scan/{job_id}").json()["state"] == "done")
    body = client.get(f"/api/scan/{job_id}").json()
    assert body["state"] == "done"
    assert body["total_files"] == 1
    assert body["completed_at"]


def test_get_scan_status_404_on_missing(client: TestClient) -> None:
    response = client.get("/api/scan/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["error"] == "JobNotFoundError"


def test_get_scan_status_validation_error_on_bad_uuid(client: TestClient) -> None:
    response = client.get("/api/scan/not-a-uuid")
    assert response.status_code == 422
    assert response.json()["error"] == "RequestValidationError"


def test_download_parquet_report(client: TestClient, library_root: Path) -> None:
    write_balanced_tone(library_root / "x.wav", duration_sec=0.5)
    start = client.post("/api/scan", json={"paths": ["x.wav"]})
    job_id = start.json()["job_id"]
    _drain_stream(client, job_id)
    _wait_until(lambda: client.get(f"/api/scan/{job_id}").json()["state"] == "done")

    response = client.get(f"/api/scan/{job_id}/report.parquet")
    assert response.status_code == 200
    assert response.content
    assert response.headers["content-type"] in {
        "application/vnd.apache.parquet",
        "application/octet-stream",
    }


def test_download_html_report(client: TestClient, library_root: Path) -> None:
    write_balanced_tone(library_root / "x.wav", duration_sec=0.5)
    start = client.post("/api/scan", json={"paths": ["x.wav"]})
    job_id = start.json()["job_id"]
    _drain_stream(client, job_id)
    _wait_until(lambda: client.get(f"/api/scan/{job_id}").json()["state"] == "done")

    response = client.get(f"/api/scan/{job_id}/report.html")
    assert response.status_code == 200
    assert b"<html" in response.content.lower() or b"<table" in response.content.lower()


def test_download_report_404_when_job_unknown(client: TestClient) -> None:
    response = client.get("/api/scan/00000000-0000-0000-0000-000000000000/report.parquet")
    assert response.status_code == 404


def test_download_report_404_when_job_still_running(
    client: TestClient, library_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Make scan_many block so the job stays RUNNING.
    import threading

    from asmr_balance.web.use_cases import scan as scan_module

    stop = threading.Event()

    def slow_scan(*_args, **_kwargs):
        # Yield zero results but block until released.
        stop.wait(timeout=5.0)
        return iter([])

    monkeypatch.setattr(scan_module, "scan_many", slow_scan)
    write_balanced_tone(library_root / "x.wav", duration_sec=0.5)
    start = client.post("/api/scan", json={"paths": ["x.wav"]})
    job_id = start.json()["job_id"]
    try:
        response = client.get(f"/api/scan/{job_id}/report.parquet")
        assert response.status_code == 404
    finally:
        stop.set()


def test_download_report_404_when_file_missing(
    client: TestClient, library_root: Path, reports_root: Path
) -> None:
    # Job runs to completion; delete the report file to simulate a
    # post-completion race (cleanup task, manual ``web-reset``, …).
    write_balanced_tone(library_root / "x.wav", duration_sec=0.5)
    start = client.post("/api/scan", json={"paths": ["x.wav"]})
    job_id = start.json()["job_id"]
    _drain_stream(client, job_id)
    _wait_until(lambda: client.get(f"/api/scan/{job_id}").json()["state"] == "done")

    (reports_root / job_id / "report.parquet").unlink()

    response = client.get(f"/api/scan/{job_id}/report.parquet")
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "ScanReportNotReadyError"
    assert body["context"]["reason"] == "report.parquet missing"
