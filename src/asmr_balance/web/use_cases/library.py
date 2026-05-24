"""Library browsing & audio-file walking — pure path operations.

Both endpoints (``/api/library``) and the scan-start use case consume the
helpers here. The functions only know about :func:`library_root` from the
runtime layer; they raise :class:`LibraryPathError` for every "outside the
mount / not found / wrong kind" path, never returning silently bogus data.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from asmr_balance.source.audio_extensions import AUDIO_EXTENSIONS
from asmr_balance.web.runtime.paths import library_root
from asmr_balance.web.use_cases.errors import LibraryPathError


@dataclass(frozen=True, slots=True)
class LibraryEntry:
    """One entry under the library mount."""

    name: str
    type: str  # "dir" | "file"
    rel_path: str
    is_audio: bool
    size: int | None


def resolve_library_target(rel_path: str) -> Path:
    """Resolve ``rel_path`` to an absolute :class:`Path` under the library root.

    Raises :class:`LibraryPathError` for path traversal escapes or for paths
    that do not exist on disk.
    """
    root = library_root().resolve()
    target = (root / rel_path).resolve()
    if not target.is_relative_to(root):
        raise LibraryPathError(rel_path, reason="escapes library root")
    if not target.exists():
        raise LibraryPathError(rel_path, reason="not found")
    return target


def list_library(rel_path: str = "") -> list[LibraryEntry]:
    """List entries under ``rel_path`` (empty string ⇒ list the library root)."""
    root = library_root().resolve()
    target = resolve_library_target(rel_path) if rel_path else root
    if not target.is_dir():
        raise LibraryPathError(rel_path, reason="not a directory")

    def sort_key(child: Path) -> tuple[int, str]:
        return (0 if child.is_dir() else 1, child.name.lower())

    entries: list[LibraryEntry] = []
    for child in sorted(target.iterdir(), key=sort_key):
        rel = child.relative_to(root).as_posix()
        if child.is_dir():
            entries.append(
                LibraryEntry(
                    name=child.name,
                    type="dir",
                    rel_path=rel,
                    is_audio=False,
                    size=None,
                )
            )
        else:
            is_audio = child.suffix.lower() in AUDIO_EXTENSIONS
            entries.append(
                LibraryEntry(
                    name=child.name,
                    type="file",
                    rel_path=rel,
                    is_audio=is_audio,
                    size=child.stat().st_size,
                )
            )
    return entries


def walk_audio_files(rel_path: str) -> Iterator[Path]:
    """Yield absolute audio-file paths under ``rel_path`` (file or directory).

    Raises :class:`LibraryPathError` if the target is a file with an
    unsupported extension.
    """
    target = resolve_library_target(rel_path)
    if target.is_file():
        if target.suffix.lower() not in AUDIO_EXTENSIONS:
            raise LibraryPathError(rel_path, reason="not an audio file")
        yield target
        return
    for p in sorted(target.rglob("*")):
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS:
            yield p
