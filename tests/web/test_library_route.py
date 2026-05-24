from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.fixtures.gen_fixtures import write_balanced_tone


def test_get_library_root(client: TestClient, library_root: Path) -> None:
    response = client.get("/api/library")
    assert response.status_code == 200
    body = response.json()
    assert body == {"rel_path": "", "parent_rel_path": None, "entries": []}


def test_get_library_with_entries(client: TestClient, library_root: Path) -> None:
    write_balanced_tone(library_root / "x.wav", duration_sec=0.5)
    (library_root / "sub").mkdir()
    response = client.get("/api/library")
    assert response.status_code == 200
    body = response.json()
    names = [e["name"] for e in body["entries"]]
    assert names == ["sub", "x.wav"]


def test_get_library_subdir(client: TestClient, library_root: Path) -> None:
    sub = library_root / "album"
    sub.mkdir()
    write_balanced_tone(sub / "track.wav", duration_sec=0.5)
    response = client.get("/api/library", params={"path": "album"})
    assert response.status_code == 200
    body = response.json()
    assert body["rel_path"] == "album"
    assert body["parent_rel_path"] == ""
    assert len(body["entries"]) == 1
    assert body["entries"][0]["rel_path"] == "album/track.wav"


def test_get_library_nested_parent(client: TestClient, library_root: Path) -> None:
    nested = library_root / "a" / "b"
    nested.mkdir(parents=True)
    response = client.get("/api/library", params={"path": "a/b"})
    assert response.status_code == 200
    assert response.json()["parent_rel_path"] == "a"


def test_get_library_404_on_missing(client: TestClient, library_root: Path) -> None:
    response = client.get("/api/library", params={"path": "missing"})
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "LibraryPathError"
    assert body["context"]["reason"] == "not found"


def test_get_library_404_on_traversal(client: TestClient, library_root: Path) -> None:
    response = client.get("/api/library", params={"path": "../etc"})
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "LibraryPathError"
    assert body["context"]["reason"] == "escapes library root"
