"""Audio decoding: soundfile for pure audio, PyAV for video containers.

We split metadata probing (``probe``) from streaming decode (``iter_pcm_blocks``)
so the pipeline can record file-level info even when a file is skipped by the
layout policy.

Dispatch:
- ``.wav`` / ``.flac`` / ``.ogg`` / ``.opus`` → soundfile (Phase B)
- ``.mp4`` / ``.mkv`` / ``.webm`` / ``.m4a`` / ``.mov`` / ``.mp3`` / ``.aac`` → PyAV (Phase D)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

import av
import numpy as np
import soundfile as sf

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from numpy.typing import NDArray

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

_SOUNDFILE_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {
        ".wav",
        ".flac",
        ".ogg",
        ".opus",
        ".aiff",
        ".aif",
        ".au",
    }
)

_PYAV_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {
        ".mp4",
        ".mkv",
        ".webm",
        ".m4a",
        ".mov",
        ".mp3",
        ".aac",
    }
)


@dataclass(frozen=True, slots=True)
class AudioMetadata:
    """Header-level info: no audio samples decoded."""

    path: Path
    sample_rate: int
    n_channels: int
    n_frames: int
    layout_name: str

    @property
    def duration_sec(self) -> float:
        return self.n_frames / self.sample_rate


def probe(path: Path) -> AudioMetadata:
    """Read header info from ``path``; raises on bad files."""
    if _use_pyav(path):
        return _probe_pyav(path)
    return _probe_soundfile(path)


def iter_pcm_blocks(
    metadata: AudioMetadata,
    block_samples: int,
) -> Iterator[NDArray[np.float32]]:
    """Yield ``(N, n_channels)`` float32 blocks from the file."""
    if block_samples <= 0:
        msg = f"block_samples must be positive, got {block_samples}"
        raise ValueError(msg)
    if _use_pyav(metadata.path):
        yield from _iter_pyav(metadata)
        return
    yield from _iter_soundfile(metadata, block_samples)


# --- private dispatchers ----------------------------------------------------


def _use_pyav(path: Path) -> bool:
    return path.suffix.lower() in _PYAV_EXTENSIONS


def _layout_name(n_channels: int) -> str:
    return _LAYOUT_BY_CHANNELS.get(n_channels, f"{n_channels}ch")


def _probe_soundfile(path: Path) -> AudioMetadata:
    info = sf.info(str(path))
    return AudioMetadata(
        path=path,
        sample_rate=int(info.samplerate),
        n_channels=int(info.channels),
        n_frames=int(info.frames),
        layout_name=_layout_name(int(info.channels)),
    )


def _iter_soundfile(metadata: AudioMetadata, block_samples: int) -> Iterator[NDArray[np.float32]]:
    with sf.SoundFile(str(metadata.path), mode="r") as snd:
        while True:
            buf = snd.read(frames=block_samples, dtype="float32", always_2d=True)
            if buf.size == 0:
                return
            yield np.ascontiguousarray(buf, dtype=np.float32)


def _probe_pyav(path: Path) -> AudioMetadata:
    with av.open(str(path)) as container:
        stream = _first_audio_stream(container, path)
        sample_rate = int(stream.rate)
        n_channels = int(stream.layout.nb_channels)
        layout = stream.layout.name
        # Decode-free duration estimate: ``container.duration`` is in
        # ``AV_TIME_BASE`` microseconds for any normally-muxed file; 0 means
        # the muxer didn't write one.
        duration_us = container.duration or 0
        n_frames = int((duration_us / av.time_base) * sample_rate)
        return AudioMetadata(
            path=path,
            sample_rate=sample_rate,
            n_channels=n_channels,
            n_frames=n_frames,
            layout_name=layout,
        )


def _first_audio_stream(container: Any, path: Path) -> Any:  # noqa: ANN401
    streams = list(container.streams.audio)
    if not streams:
        msg = f"No audio stream in {path}"
        raise ValueError(msg)
    return streams[0]


def _iter_pyav(metadata: AudioMetadata) -> Iterator[NDArray[np.float32]]:
    with av.open(str(metadata.path)) as container:
        stream = _first_audio_stream(container, metadata.path)
        resampler = av.AudioResampler(
            format="fltp",
            layout=stream.layout.name,
            rate=metadata.sample_rate,
        )
        for frame in container.decode(stream):
            yield from _convert_frames(resampler.resample(frame))
        yield from _convert_frames(resampler.resample(None))


def _convert_frames(frames: list[Any]) -> Iterator[NDArray[np.float32]]:
    """Convert PyAV ``fltp`` (planar float) frames to ``(samples, channels)`` float32."""
    for frame in frames:
        arr = frame.to_ndarray()  # shape (n_channels, n_samples)
        yield np.ascontiguousarray(arr.T, dtype=np.float32)
