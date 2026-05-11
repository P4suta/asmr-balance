"""4x polyphase oversampling for BS.1770-5 Annex 2 true-peak estimation.

The polyphase decomposition expresses an L-fold upsampler as ``L`` parallel
FIR filters operating at the input rate. For each new input sample ``x[n]``,
phase ``k ∈ {0,1,2,3}`` produces one output sample ``y[4n+k]``:

.. code:: text

   y[4n + k] = Σᵢ h[4i + k] · x[n - i]   for i ∈ [0, T)

where ``T = ceil(L_h / L)`` is the per-phase tap count.

We design the prototype 49-tap FIR via the Kaiser window with ``β = 8.0``
(>= 70 dB stopband attenuation) and a cutoff of ``0.95 / 4`` normalised
frequency. The 49 taps cleanly decompose into four polyphase branches; padding
to 52 taps gives a clean ``T = 13`` per phase.

True peak (dBTP) is computed downstream by
:class:`~asmr_balance.metrics.dynamics.TruePeakReducer` from the produced
:data:`OversampledBlock` payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import ClassVar, Final

import numpy as np
import scipy.signal as _sps
from numpy.typing import NDArray

from asmr_balance.graph.types import OversampledBlock, RawBlock

_OVERSAMPLE_FACTOR: Final[int] = 4
_PROTOTYPE_LENGTH: Final[int] = 49
_KAISER_BETA: Final[float] = 8.0
_CUTOFF_NORMALIZED: Final[float] = 0.95 / _OVERSAMPLE_FACTOR


@lru_cache(maxsize=1)
def _polyphase_taps() -> tuple[NDArray[np.float64], ...]:
    """Design the prototype FIR once and return its 4 polyphase branches.

    The branches are length ``T = ceil(L_h / 4)`` each. We scale the prototype
    by ``L = 4`` so that the polyphase output reconstructs a unity-gain
    upsample (the standard convention for polyphase interpolators).
    """
    proto = _sps.firwin(
        _PROTOTYPE_LENGTH,
        cutoff=_CUTOFF_NORMALIZED,
        window=("kaiser", _KAISER_BETA),
    ).astype(np.float64) * _OVERSAMPLE_FACTOR
    pad = (-len(proto)) % _OVERSAMPLE_FACTOR
    if pad:
        proto = np.concatenate([proto, np.zeros(pad, dtype=np.float64)])
    return tuple(np.ascontiguousarray(proto[k :: _OVERSAMPLE_FACTOR]) for k in range(_OVERSAMPLE_FACTOR))


def _per_phase_tap_count() -> int:
    return _polyphase_taps()[0].size


def _oversample_channel(
    state: NDArray[np.float64],
    x: NDArray[np.float64],
    phases: tuple[NDArray[np.float64], ...],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Run one channel through the polyphase upsampler.

    Args:
        state: Previous input samples retained as filter context, length ``T-1``.
        x: New input samples, length ``N``.
        phases: 4 polyphase branches, each length ``T``.

    Returns:
        ``(y, new_state)`` where ``y`` has length ``4 * N`` and ``new_state``
        has length ``T - 1``.
    """
    tap_count = phases[0].size
    if x.size == 0:
        return np.empty(0, dtype=np.float64), state
    full = np.concatenate([state, x])
    y = np.empty(_OVERSAMPLE_FACTOR * x.size, dtype=np.float64)
    for k, phase in enumerate(phases):
        # 'valid' convolution: output length = len(full) - T + 1 = (T-1 + N) - T + 1 = N
        y[k :: _OVERSAMPLE_FACTOR] = np.convolve(full, phase, mode="valid")
    new_state = full[-(tap_count - 1) :] if tap_count > 1 else np.empty(0, dtype=np.float64)
    return y, new_state


@dataclass(slots=True)
class Oversample4xPolyphase:
    """``Stream[RawBlock] → Stream[OversampledBlock]`` (4x polyphase upsample)."""

    name: ClassVar[str] = "oversample4x"

    _phases: tuple[NDArray[np.float64], ...] = field(default_factory=_polyphase_taps)
    _state_l: NDArray[np.float64] = field(init=False)
    _state_r: NDArray[np.float64] = field(init=False)

    def __post_init__(self) -> None:
        T = _per_phase_tap_count()
        self._state_l = np.zeros(T - 1, dtype=np.float64)
        self._state_r = np.zeros(T - 1, dtype=np.float64)

    def process(self, payload: RawBlock) -> list[OversampledBlock]:
        if payload.shape[0] == 0:
            return []
        left = np.asarray(payload[:, 0], dtype=np.float64)
        right = np.asarray(payload[:, 1], dtype=np.float64)
        l_out, self._state_l = _oversample_channel(self._state_l, left, self._phases)
        r_out, self._state_r = _oversample_channel(self._state_r, right, self._phases)
        return [OversampledBlock(np.column_stack([l_out, r_out]))]

    def flush(self) -> list[OversampledBlock]:
        return []
