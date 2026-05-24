from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.fixtures.gen_fixtures import write_balanced_tone


def _parse_sse(lines: Iterator[str]) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw in lines:
        line = raw.rstrip("\r")
        if not line:
            if current:
                events.append(current)
                current = {}
            continue
        if line.startswith("event:"):
            current["event"] = line[len("event:") :].strip()
        elif line.startswith("data:"):
            current["data"] = line[len("data:") :].strip()
    if current:
        events.append(current)
    return events


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


def test_sse_streams_file_and_done_events(client: TestClient, library_root: Path) -> None:
    write_balanced_tone(library_root / "x.wav", duration_sec=0.5)
    start = client.post("/api/scan", json={"paths": ["x.wav"]})
    assert start.status_code == 200
    job_id = start.json()["job_id"]

    with client.stream("GET", f"/api/scan/{job_id}/events") as resp:
        assert resp.status_code == 200
        events = _parse_sse(resp.iter_lines())

    types = [e.get("event") for e in events]
    assert "file_done" in types
    assert types[-1] == "done"

    file_event = next(e for e in events if e.get("event") == "file_done")
    payload = json.loads(file_event["data"])
    assert payload["sequence"] == 1
    assert payload["total"] == 1
    assert payload["source_name"] == "x.wav"


def test_get_scan_status_eventually_done(client: TestClient, library_root: Path) -> None:
    write_balanced_tone(library_root / "x.wav", duration_sec=0.5)
    start = client.post("/api/scan", json={"paths": ["x.wav"]})
    job_id = start.json()["job_id"]

    # Drain the SSE first so we don't race the background task to completion.
    with client.stream("GET", f"/api/scan/{job_id}/events") as resp:
        for _ in resp.iter_lines():
            pass

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
    with client.stream("GET", f"/api/scan/{job_id}/events") as resp:
        for _ in resp.iter_lines():
            pass
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
    with client.stream("GET", f"/api/scan/{job_id}/events") as resp:
        for _ in resp.iter_lines():
            pass
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
