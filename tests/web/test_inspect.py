from __future__ import annotations

from pathlib import Path

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
    # Findings + recommendations.
    assert "見つかった問題" in text
    assert "どう直す" in text
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
