from __future__ import annotations

from fastapi.testclient import TestClient

from asmr_balance import __version__


def test_healthz_returns_status_and_version(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ok", "version": __version__}


def test_healthz_includes_request_id_header(client: TestClient) -> None:
    response = client.get("/healthz")
    assert "X-Request-ID" in response.headers
    assert response.headers["X-Request-ID"]


def test_healthz_respects_inbound_request_id(client: TestClient) -> None:
    response = client.get("/healthz", headers={"X-Request-ID": "deadbeef"})
    assert response.headers["X-Request-ID"] == "deadbeef"
