"""Windowed mean-square reducers — emit ``z`` pairs for downstream LUFS / LRA / sliding.

Two filters live here:

* :class:`ZBlocksFilter` — BS.1770 400 ms / 100 ms-hop integrated-loudness blocks.
  The downstream reducer (:class:`~asmr_balance.metrics.loudness.IntegratedLoudnessReducer`)
  computes ``L = -0.691 + 10·log10(z)`` per block and applies two-stage gating.
* :class:`ShortTermZBlocksFilter` — EBU R128 3 s / 100 ms-hop short-term loudness
  blocks for the LRA reducer (:class:`~asmr_balance.metrics.lra.LRAReducer`).

Both share an internal helper that maintains a per-channel ring buffer of
already-K-weighted samples and emits one ``z`` per ``hop_size`` once the first
``window_size`` samples have been buffered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Final

import numpy as np
from numpy.typing import NDArray

from asmr_balance.graph.types import KWeightedBlock, ShortTermZBlock, ZBlock

_INTEGRATED_WINDOW_SEC: Final[float] = 0.4
_INTEGRATED_HOP_SEC: Final[float] = 0.1
_SHORTTERM_WINDOW_SEC: Final[float] = 3.0
_SHORTTERM_HOP_SEC: Final[float] = 0.1


@dataclass(slots=True)
class _ChannelMeanSquareBuffer:
    """Streaming ring buffer that emits mean-square per ``hop_size`` once primed.

    Internally stores samples as a single concatenated ndarray and advances a
    sliding origin index. Periodically trims the buffer when the origin is
    far enough that residual prefix can be released.
    """

    block_size: int
    hop_size: int
    _buf: NDArray[np.float64] = field(default_factory=lambda: np.empty(0, dtype=np.float64))
    _origin: int = 0

    def push(self, samples: NDArray[np.float64]) -> list[float]:
        if samples.size == 0:
            return []
        self._buf = np.concatenate([self._buf, samples])
        emitted: list[float] = []
        end = self._origin + self.block_size
        while end <= self._buf.size:
            window = self._buf[self._origin : end]
            emitted.append(float(np.mean(window * window)))
            self._origin += self.hop_size
            end = self._origin + self.block_size
        if self._origin >= 4 * self.block_size:
            self._buf = self._buf[self._origin :]
            self._origin = 0
        return emitted


@dataclass(slots=True)
class _ZBlocksCore:
    """Shared core: two per-channel buffers, paired emission."""

    sample_rate: int
    window_sec: float
    hop_sec: float
    _left: _ChannelMeanSquareBuffer = field(init=False)
    _right: _ChannelMeanSquareBuffer = field(init=False)

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            msg = f"sample_rate must be positive, got {self.sample_rate}"
            raise ValueError(msg)
        block_size = round(self.sample_rate * self.window_sec)
        hop_size = round(self.sample_rate * self.hop_sec)
        self._left = _ChannelMeanSquareBuffer(block_size=block_size, hop_size=hop_size)
        self._right = _ChannelMeanSquareBuffer(block_size=block_size, hop_size=hop_size)

    def push_block(self, payload: KWeightedBlock) -> list[tuple[float, float]]:
        if payload.shape[0] == 0:
            return []
        z_l = self._left.push(np.asarray(payload[:, 0], dtype=np.float64))
        z_r = self._right.push(np.asarray(payload[:, 1], dtype=np.float64))
        # The two channels see identical sample counts → equal emissions.
        return list(zip(z_l, z_r, strict=True))


@dataclass(slots=True)
class ZBlocksFilter:
    """``Stream[KWeightedBlock] → Stream[ZBlock]`` (BS.1770 400 ms / 100 ms hop)."""

    name: ClassVar[str] = "zblocks"

    sample_rate: int
    _core: _ZBlocksCore = field(init=False)

    def __post_init__(self) -> None:
        self._core = _ZBlocksCore(
            sample_rate=self.sample_rate,
            window_sec=_INTEGRATED_WINDOW_SEC,
            hop_sec=_INTEGRATED_HOP_SEC,
        )

    def process(self, payload: KWeightedBlock) -> list[ZBlock]:
        return [ZBlock(pair) for pair in self._core.push_block(payload)]

    def flush(self) -> list[ZBlock]:
        return []


@dataclass(slots=True)
class ShortTermZBlocksFilter:
    """``Stream[KWeightedBlock] → Stream[ShortTermZBlock]`` (EBU R128 3 s / 100 ms hop)."""

    name: ClassVar[str] = "shortterm_zblocks"

    sample_rate: int
    _core: _ZBlocksCore = field(init=False)

    def __post_init__(self) -> None:
        self._core = _ZBlocksCore(
            sample_rate=self.sample_rate,
            window_sec=_SHORTTERM_WINDOW_SEC,
            hop_sec=_SHORTTERM_HOP_SEC,
        )

    def process(self, payload: KWeightedBlock) -> list[ShortTermZBlock]:
        return [ShortTermZBlock(pair) for pair in self._core.push_block(payload)]

    def flush(self) -> list[ShortTermZBlock]:
        return []
