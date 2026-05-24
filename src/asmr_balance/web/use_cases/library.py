"""Library browsing & audio-file walking — pure path operations.

Both endpoints (``/api/library``) and the scan-start use case consume the
helpers here. The functions only know about :func:`library_root` from the
runtime layer; they raise :class:`LibraryPathError` for every "outside the
mount / not found / wrong kind" path, never returning silently bogus data.

Path-safety strategy (two-stage barrier — defense in depth):

1. :func:`_ensure_safe_relative` rejects the user-supplied string up front if
   it is absolute or contains any ``..`` segment. This is the static guard
   CodeQL recognizes as a path-injection sanitizer.
2. After joining + ``resolve()``, :func:`resolve_library_target` re-checks
   that the resolved path is still under the mount root (catches anything
   that slipped through via symlinks the first guard cannot see).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

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


def _ensure_safe_relative(rel_path: str) -> None:
    """Reject obviously unsafe inputs before they reach the filesystem.

    This is the *string-level* sanitizer: any absolute path or any segment
    equal to ``..`` raises :class:`LibraryPathError`. Callers may safely
    join the input with the mount root afterwards.
    """
    if rel_path == "":
        return
    pure = PurePosixPath(rel_path)
    if pure.is_absolute() or any(part == ".." for part in pure.parts):
        raise LibraryPathError(rel_path, reason="escapes library root")


def resolve_library_target(rel_path: str) -> Path:
    """Resolve ``rel_path`` to an absolute :class:`Path` under the library root.

    Raises :class:`LibraryPathError` for path traversal escapes or for paths
    that do not exist on disk. See module docstring for the two-stage
    sanitization strategy.
    """
    _ensure_safe_relative(rel_path)
    root = library_root().resolve()
    target = (root / rel_path).resolve()
    # Defense in depth: re-check after resolve in case symlinks routed us out.
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
