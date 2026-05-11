"""``libsndfile``-backed decoding (WAV / FLAC / OGG / OPUS / AIFF / AU)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import soundfile as sf

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from numpy.typing import NDArray

# Re-export through ``dispatch.layout_name`` to avoid a circular import:
# ``dispatch`` imports this module, this module imports ``layout_name``.
# We instead inline a tiny local mapping; dispatch keeps its own canonical copy.
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


def _layout_name(n_channels: int) -> str:
    return _LOCAL_LAYOUTS.get(n_channels, f"{n_channels}ch")


def probe(path: Path) -> "ProbedAudio":
    from asmr_balance.source.backend.dispatch import ProbedAudio  # local to avoid cycle

    info = sf.info(str(path))
    return ProbedAudio(
        sample_rate=int(info.samplerate),
        n_channels=int(info.channels),
        n_frames=int(info.frames),
        layout_name=_layout_name(int(info.channels)),
    )


def iter_frames(path: Path, block_samples: int) -> Iterator[NDArray[np.float32]]:
    with sf.SoundFile(str(path), mode="r") as snd:
        while True:
            buf = snd.read(frames=block_samples, dtype="float32", always_2d=True)
            if buf.size == 0:
                return
            yield np.ascontiguousarray(buf, dtype=np.float32)


if TYPE_CHECKING:
    from asmr_balance.source.backend.dispatch import ProbedAudio
