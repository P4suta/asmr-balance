from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _post_inspect(client: TestClient, *, path: Path, filename: str, endpoint: str = "/api/inspect"):
    with path.open("rb") as handle:
        return client.post(
            endpoint,
            files={"file": (filename, handle, "audio/wav")},
        )


def test_inspect_json_panned_fires_lr_balance(client: TestClient, panned_wav: Path) -> None:
    response = _post_inspect(client, path=panned_wav, filename="panned.wav")
    assert response.status_code == 200
    body = response.json()
    assert body["source_name"] == "panned.wav"
    assert body["verdict"] in {"WARN", "FAIL"}
    flag_codes = {f["code"] for f in body["flags"]}
    assert any(code.startswith("LR_BALANCE") for code in flag_codes)
    assert body["record"]["status"] == "analyzed"
    assert isinstance(body["record"]["meta"]["file_path"], str)


def test_inspect_json_balanced_does_not_fire_lr_balance(
    client: TestClient, balanced_wav: Path
) -> None:
    # A perfectly balanced sine has delta_lu == 0, so LR_BALANCE must not fire.
    # PSEUDO_MONO is allowed to fire (Pearson r == 1 on identical channels).
    response = _post_inspect(client, path=balanced_wav, filename="balanced.wav")
    assert response.status_code == 200
    body = response.json()
    assert body["record"]["status"] == "analyzed"
    flag_codes = {f["code"] for f in body["flags"]}
    assert not any(code.startswith("LR_BALANCE") for code in flag_codes)


def test_inspect_partial_returns_html(client: TestClient, panned_wav: Path) -> None:
    response = _post_inspect(
        client, path=panned_wav, filename="panned.wav", endpoint="/api/inspect/partial"
    )
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    text = response.text
    # Phase 2.5: diagnosis hero leads.
    assert "diagnosis" in text
    # Insights dashboards present — 4 sections (balance / loudness / headroom / tone).
    assert "dash--balance" in text
    assert "dash--loudness" in text
    assert "dash--headroom" in text
    assert "dash--tone" in text
    # Pan meter / LUFS meter / headroom gauge / tone grid markup rendered.
    assert "pan-meter" in text
    assert "lufs-meter" in text
    assert "headroom-meter" in text
    assert "tone-grid" in text
    # Findings + recommendations (listener-framed copy).
    assert "視聴時に注意したい点" in text
    assert "視聴のコツ" in text
    # Raw data still available under disclosure.
    assert "raw-details" in text
    assert "chart-band" in text
    # technical_ref still includes the original rule code.
    assert "LR_BALANCE" in text


def test_inspect_partial_for_skipped_record_shows_unanalyzable_diagnosis(
    client: TestClient, mono_wav: Path
) -> None:
    response = _post_inspect(
        client, path=mono_wav, filename="mono.wav", endpoint="/api/inspect/partial"
    )
    assert response.status_code == 200
    text = response.text
    assert "diagnosis" in text
    assert "対象外" in text
    # No dashboards / charts / KPI for skipped records (every insight is None).
    assert "dash--balance" not in text
    assert "chart-band" not in text
    assert "kpi-grid" not in text


def test_inspect_rejects_unsupported_suffix(client: TestClient) -> None:
    response = client.post(
        "/api/inspect",
        files={"file": ("notes.txt", b"not audio", "text/plain")},
    )
    assert response.status_code == 415
    body = response.json()
    assert body["error"] == "UnsupportedAudioFormatError"
    assert body["context"]["suffix"] == ".txt"
    assert ".wav" in body["context"]["supported"]
    assert body["trace_id"]


def test_inspect_returns_skipped_for_mono(client: TestClient, mono_wav: Path) -> None:
    response = _post_inspect(client, path=mono_wav, filename="mono.wav")
    assert response.status_code == 200
    body = response.json()
    assert body["record"]["status"] == "skipped"
    assert body["record"]["skip_reason"]


def test_inspect_rejects_corrupt_audio(client: TestClient) -> None:
    # Valid suffix but garbage bytes → soundfile fails → scan_one returns
    # ERRORED → perform_inspect raises AudioDecodeError → 422.
    junk = b"\x00\x01\x02\x03" * 200
    response = client.post(
        "/api/inspect",
        files={"file": ("corrupt.wav", junk, "audio/wav")},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "AudioDecodeError"
    assert body["context"]["original_filename"] == "corrupt.wav"
    assert body["context"]["reason"]


def test_inspect_missing_file_returns_validation_error(client: TestClient) -> None:
    response = client.post("/api/inspect")  # no multipart body at all
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "RequestValidationError"
    assert body["context"]["errors"]


# ---------------------------------------------------------------------------
# /api/inspect/stream — NDJSON streaming inspect
# ---------------------------------------------------------------------------
def _consume_ndjson(client: TestClient, *, path: Path, filename: str) -> list[dict]:
    """POST to /api/inspect/stream and parse the NDJSON body into events."""
    with path.open("rb") as handle:
        response = client.post(
            "/api/inspect/stream",
            files={"file": (filename, handle, "audio/wav")},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_inspect_stream_emits_progress_then_done(client: TestClient, panned_wav: Path) -> None:
    """Happy path: many ``progress`` frames, then one terminal ``done`` with HTML."""
    events = _consume_ndjson(client, path=panned_wav, filename="panned.wav")
    types = [e["type"] for e in events]
    assert types[-1] == "done", f"last frame must be 'done', got {types[-1]}"
    assert "progress" in types, "no progress frames emitted"
    # Stages observed cover the pipeline boundaries.
    stages = {e["stage"] for e in events if e["type"] == "progress"}
    assert {"probe", "decode", "analyze", "assemble", "evaluate", "complete"} <= stages
    # Terminal done frame contains the rendered HTML partial.
    done = events[-1]
    assert "diagnosis" in done["html"]
    assert "dash--balance" in done["html"]


def test_inspect_stream_unsupported_suffix_yields_failed_frame(
    client: TestClient,
) -> None:
    """Pre-stream rejection surfaces as an in-band ``failed`` frame, not a 4xx."""
    response = client.post(
        "/api/inspect/stream",
        files={"file": ("notes.txt", b"not audio", "text/plain")},
    )
    # The HTTP layer is already 200 (stream started). Failure is in-band.
    assert response.status_code == 200
    lines = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert len(lines) == 1
    assert lines[0]["type"] == "failed"
    assert lines[0]["error"] == "UnsupportedAudioFormatError"
    assert lines[0]["status"] == 415
    assert lines[0]["context"]["suffix"] == ".txt"


def test_inspect_stream_decode_error_yields_failed_frame(client: TestClient) -> None:
    """Decoder failure mid-pipeline surfaces as a terminal ``failed`` frame."""
    junk = b"\x00\x01\x02\x03" * 200
    response = client.post(
        "/api/inspect/stream",
        files={"file": ("corrupt.wav", junk, "audio/wav")},
    )
    assert response.status_code == 200
    lines = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    # The pipeline catches the decode error and ScanStatus.ERRORED triggers
    # AudioDecodeError after the worker thread finishes; some progress frames
    # may have flushed first, but the terminal frame must be ``failed``.
    assert lines[-1]["type"] == "failed"
    assert lines[-1]["error"] == "AudioDecodeError"
    assert lines[-1]["status"] == 422
    assert lines[-1]["context"]["original_filename"] == "corrupt.wav"


def test_inspect_stream_progress_payload_shape(client: TestClient, balanced_wav: Path) -> None:
    """Every progress frame carries (stage, current, total) with sane values."""
    events = _consume_ndjson(client, path=balanced_wav, filename="balanced.wav")
    progress = [e for e in events if e["type"] == "progress"]
    assert progress, "expected at least one progress frame"
    for frame in progress:
        assert isinstance(frame["stage"], str)
        assert frame["stage"]
        assert isinstance(frame["current"], int)
        assert frame["current"] >= 0
        assert isinstance(frame["total"], int)
        assert frame["total"] >= 0
        # current is bounded by total except for the "0/0 unknown" case.
        assert frame["total"] == 0 or frame["current"] <= frame["total"]


def test_inspect_stream_programmer_bug_is_framed_as_failed(
    client: TestClient,
    balanced_wav: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unexpected exceptions still produce a 500-shaped ``failed`` frame.

    The detail must NOT leak the original exception message (matches the
    unhandled-exception handler in :mod:`asmr_balance.web.errors`).
    """

    async def boom(_bytes: bytes, _filename: str | None) -> AsyncIterator[object]:
        message = "simulated programmer bug"
        raise RuntimeError(message)
        yield  # pragma: no cover -- unreachable, satisfies async-generator signature

    monkeypatch.setattr(
        "asmr_balance.web.routes.inspect.perform_inspect_streaming",
        boom,
    )
    with balanced_wav.open("rb") as handle:
        response = client.post(
            "/api/inspect/stream",
            files={"file": ("x.wav", handle, "audio/wav")},
        )
    assert response.status_code == 200
    lines = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert lines == [
        {
            "type": "failed",
            "error": "RuntimeError",
            "detail": "internal server error",
            "status": 500,
            "context": {},
        }
    ]


def test_inspect_stream_skipped_for_mono(client: TestClient, mono_wav: Path) -> None:
    """Mono input → 'skipped' progress event + terminal 'done' frame.

    Skipped is *not* a failure — listener UI still gets the diagnosis card
    (with the 対象外 banner) so it can advise picking a stereo source.
    """
    events = _consume_ndjson(client, path=mono_wav, filename="mono.wav")
    stages = [e["stage"] for e in events if e["type"] == "progress"]
    assert "skipped" in stages
    assert events[-1]["type"] == "done"
    assert "対象外" in events[-1]["html"]
