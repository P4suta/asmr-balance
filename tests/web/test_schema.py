from __future__ import annotations

from fastapi.testclient import TestClient

from asmr_balance.sink.base import COLUMN_NAMES


def test_schema_returns_canonical_columns(client: TestClient) -> None:
    response = client.get("/api/schema")
    assert response.status_code == 200
    body = response.json()
    assert body["columns"] == list(COLUMN_NAMES)
