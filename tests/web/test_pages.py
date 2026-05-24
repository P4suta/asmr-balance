from __future__ import annotations

from fastapi.testclient import TestClient


def test_index_renders(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "asmr-balance" in response.text.lower()
    assert "inspect" in response.text.lower()
    assert "/api/inspect/partial" in response.text


def test_static_css_served(client: TestClient) -> None:
    response = client.get("/static/app.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


def test_static_js_served(client: TestClient) -> None:
    response = client.get("/static/app.js")
    assert response.status_code == 200
