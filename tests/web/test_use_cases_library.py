from __future__ import annotations

from pathlib import Path

import pytest

from asmr_balance.web.use_cases.errors import LibraryPathError
from asmr_balance.web.use_cases.library import (
    LibraryEntry,
    list_library,
    resolve_library_target,
    walk_audio_files,
)
from tests.fixtures.gen_fixtures import write_balanced_tone, write_panned_tone


def test_list_empty_library(library_root: Path) -> None:
    assert list_library() == []


def test_list_with_files_and_dirs(library_root: Path) -> None:
    (library_root / "music").mkdir()
    write_balanced_tone(library_root / "single.wav", duration_sec=0.5)
    (library_root / "notes.txt").write_text("hi")

    entries = list_library()
    names = [e.name for e in entries]
    # dirs first, then files (alphabetical within group)
    assert names == ["music", "notes.txt", "single.wav"]

    music = next(e for e in entries if e.name == "music")
    assert music.type == "dir"
    assert music.is_audio is False
    assert music.size is None

    audio = next(e for e in entries if e.name == "single.wav")
    assert audio.type == "file"
    assert audio.is_audio is True
    assert audio.size is not None

    txt = next(e for e in entries if e.name == "notes.txt")
    assert txt.is_audio is False


def test_list_subdirectory(library_root: Path) -> None:
    sub = library_root / "album"
    sub.mkdir()
    write_balanced_tone(sub / "track.wav", duration_sec=0.5)
    entries = list_library("album")
    assert [e.name for e in entries] == ["track.wav"]
    assert entries[0].rel_path == "album/track.wav"


def test_list_rejects_traversal(library_root: Path) -> None:
    with pytest.raises(LibraryPathError) as exc_info:
        list_library("..")
    assert exc_info.value.reason == "escapes library root"
    assert exc_info.value.status_code == 404


def test_list_rejects_nested_traversal(library_root: Path) -> None:
    with pytest.raises(LibraryPathError) as exc_info:
        list_library("album/../..")
    assert exc_info.value.reason == "escapes library root"


def test_list_rejects_absolute_path(library_root: Path) -> None:
    with pytest.raises(LibraryPathError) as exc_info:
        list_library("/etc")
    assert exc_info.value.reason == "escapes library root"


def test_list_rejects_missing(library_root: Path) -> None:
    with pytest.raises(LibraryPathError) as exc_info:
        list_library("does/not/exist")
    assert exc_info.value.reason == "not found"


def test_list_rejects_file_target(library_root: Path) -> None:
    write_balanced_tone(library_root / "x.wav", duration_sec=0.5)
    with pytest.raises(LibraryPathError) as exc_info:
        list_library("x.wav")
    assert exc_info.value.reason == "not a directory"


def test_walk_yields_single_audio_file(library_root: Path) -> None:
    write_balanced_tone(library_root / "x.wav", duration_sec=0.5)
    files = list(walk_audio_files("x.wav"))
    assert len(files) == 1
    assert files[0].name == "x.wav"


def test_walk_recursively_yields_audio_files(library_root: Path) -> None:
    write_balanced_tone(library_root / "top.wav", duration_sec=0.5)
    sub = library_root / "album"
    sub.mkdir()
    write_panned_tone(sub / "nested.wav", duration_sec=0.5)
    (sub / "notes.txt").write_text("not audio")

    files = sorted(p.name for p in walk_audio_files(""))
    assert files == ["nested.wav", "top.wav"]


def test_walk_rejects_non_audio_file(library_root: Path) -> None:
    (library_root / "doc.txt").write_text("hi")
    with pytest.raises(LibraryPathError) as exc_info:
        list(walk_audio_files("doc.txt"))
    assert exc_info.value.reason == "not an audio file"


def test_resolve_returns_absolute(library_root: Path) -> None:
    sub = library_root / "album"
    sub.mkdir()
    target = resolve_library_target("album")
    assert target == sub.resolve()


def test_library_entry_is_frozen_dataclass() -> None:
    import dataclasses

    entry = LibraryEntry(name="x", type="file", rel_path="x", is_audio=True, size=10)
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.name = "y"  # pyright: ignore[reportAttributeAccessIssue]
