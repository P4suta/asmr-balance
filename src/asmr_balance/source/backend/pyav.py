"""PyAV-backed decoding (MP4 / MKV / WebM / M4A / MP3 / AAC / MOV)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import av
import numpy as np

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from numpy.typing import NDArray


def _first_audio_stream(container: Any, path: Path) -> Any:  # noqa: ANN401
    streams = list(container.streams.audio)
    if not streams:
        msg = f"no audio stream in {path}"
        raise ValueError(msg)
    return streams[0]


_LOCAL_LAYOUTS: dict[int, str] = {
    1: "mono",
    2: "stereo",
    3: "2.1",
    4: "quad",
    5: "5.0",
    6: "5.1",
    7: "6.1",
    8: "7.1",
}


def _layout_name_for(n_channels: int, raw: str) -> str:
    return raw if raw else _LOCAL_LAYOUTS.get(n_channels, f"{n_channels}ch")


def probe(path: Path) -> "ProbedAudio":
    from asmr_balance.source.backend.dispatch import ProbedAudio  # local to avoid cycle

    with av.open(str(path)) as container:
        stream = _first_audio_stream(container, path)
        sample_rate = int(stream.rate)
        n_channels = int(stream.layout.nb_channels)
        layout = _layout_name_for(n_channels, stream.layout.name)
        duration_us = container.duration or 0
        n_frames = int((duration_us / av.time_base) * sample_rate)
        return ProbedAudio(
            sample_rate=sample_rate,
            n_channels=n_channels,
            n_frames=n_frames,
            layout_name=layout,
        )


def iter_frames(path: Path) -> Iterator[NDArray[np.float32]]:
    with av.open(str(path)) as container:
        stream = _first_audio_stream(container, path)
        resampler = av.AudioResampler(
            format="fltp",
            layout=stream.layout.name,
            rate=int(stream.rate),
        )
        for frame in container.decode(stream):
            yield from _convert(resampler.resample(frame))
        yield from _convert(resampler.resample(None))


def _convert(frames: list[Any]) -> Iterator[NDArray[np.float32]]:
    for frame in frames:
        arr = frame.to_ndarray()  # shape: (n_channels, n_samples)
        yield np.ascontiguousarray(arr.T, dtype=np.float32)


if TYPE_CHECKING:
    from asmr_balance.source.backend.dispatch import ProbedAudio
