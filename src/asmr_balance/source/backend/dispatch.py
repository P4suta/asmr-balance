"""Decode backend dispatch: extension → soundfile or PyAV.

The dispatch table is the single registration point. Adding a backend means
appending one extension set and one ``(probe_fn, iter_fn)`` pair; downstream
code is unchanged. The dispatch decision is computed twice per file (once at
:func:`probe`, once at :func:`iter_pcm_frames`); this is cheap and avoids
threading the backend choice through the source ADT.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from asmr_balance.source.backend import pyav as _pyav, soundfile as _soundfile

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    import numpy as np
    from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class ProbedAudio:
    """Backend-agnostic header information (analog of legacy ``AudioMetadata``)."""

    sample_rate: int
    n_channels: int
    n_frames: int
    layout_name: str

    @property
    def duration_sec(self) -> float:
        if self.sample_rate <= 0:
            return 0.0
        return self.n_frames / self.sample_rate


_PYAV_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {".mp4", ".mkv", ".webm", ".m4a", ".mov", ".mp3", ".aac"},
)
_SOUNDFILE_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {".wav", ".flac", ".ogg", ".opus", ".aiff", ".aif", ".au"},
)


def _use_pyav(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in _PYAV_EXTENSIONS:
        return True
    if suffix in _SOUNDFILE_EXTENSIONS:
        return False
    msg = f"unsupported file extension: {path.suffix!r} ({path})"
    raise ValueError(msg)


_LAYOUT_BY_CHANNELS: Final[dict[int, str]] = {
    1: "mono",
    2: "stereo",
    3: "2.1",
    4: "quad",
    5: "5.0",
    6: "5.1",
    7: "6.1",
    8: "7.1",
}


def layout_name(n_channels: int) -> str:
    return _LAYOUT_BY_CHANNELS.get(n_channels, f"{n_channels}ch")


def probe(path: Path) -> ProbedAudio:
    """Read header info; raises on I/O or unsupported extension."""
    if _use_pyav(path):
        return _pyav.probe(path)
    return _soundfile.probe(path)


def iter_pcm_frames(path: Path, block_samples: int) -> Iterator[NDArray[np.float32]]:
    """Stream ``(N, n_channels)`` float32 frames; dispatches to the right backend."""
    if block_samples <= 0:
        msg = f"block_samples must be positive, got {block_samples}"
        raise ValueError(msg)
    if _use_pyav(path):
        yield from _pyav.iter_frames(path)
        return
    yield from _soundfile.iter_frames(path, block_samples)
