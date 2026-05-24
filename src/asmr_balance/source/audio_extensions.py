"""Single source of truth for audio file extensions we accept.

Both the CLI ``scan`` walker and the Web ``inspect`` upload validator dispatch
on the same set; defining it twice would create silent drift the moment we add
or remove a backend. Lowercase, dot-prefixed.
"""

from __future__ import annotations

from typing import Final

AUDIO_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {
        # soundfile-backed
        ".wav",
        ".flac",
        ".ogg",
        ".opus",
        ".aiff",
        ".aif",
        ".au",
        # PyAV-backed
        ".mp4",
        ".mkv",
        ".webm",
        ".m4a",
        ".mov",
        ".mp3",
        ".aac",
    }
)
"""All file extensions the analysis pipeline can decode (lowercase, with dot)."""
