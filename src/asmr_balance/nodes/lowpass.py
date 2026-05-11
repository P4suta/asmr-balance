"""4th-order Butterworth low-pass filter — shared by phase and band low slot.

The legacy implementation had two independent low-pass paths: one in
``dsp/phase.py`` (300 Hz, used to compute low-band phase coherence) and one
inside the 4-band band split at 250 Hz (used as the low slot of band
imbalance). The redesign collapses both into a single filter node so that the
SOS, ``zi`` state, and CPU work are shared. The downstream consumers attach
to the same :class:`~asmr_balance.graph.types.Stream[LowPassBlock]` handle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import ClassVar

import numpy as np
import scipy.signal as _sps
from numpy.typing import NDArray

from asmr_balance.algebra.iir import IIRFactory, SteadyIIR, UninitializedIIR
from asmr_balance.graph.types import LowPassBlock, RawBlock


@lru_cache(maxsize=64)
def _lowpass_sos(order: int, cutoff_hz: float, sample_rate: int) -> tuple[tuple[float, ...], ...]:
    if sample_rate <= 0:
        msg = f"sample_rate must be positive, got {sample_rate}"
        raise ValueError(msg)
    nyquist = sample_rate / 2.0
    if not (0.0 < cutoff_hz < nyquist):
        msg = f"cutoff_hz must satisfy 0 < {cutoff_hz} < {nyquist} (Nyquist)"
        raise ValueError(msg)
    sos = _sps.butter(order, cutoff_hz, btype="low", fs=sample_rate, output="sos")
    return tuple(tuple(row) for row in sos)


def make_lowpass_sos(order: int, cutoff_hz: float, sample_rate: int) -> NDArray[np.float64]:
    """Design a Butterworth low-pass SOS matrix (cached by ``order``/fc/sr)."""
    return np.asarray(_lowpass_sos(order, cutoff_hz, sample_rate), dtype=np.float64)


def _step_with_init(
    state: UninitializedIIR | SteadyIIR,
    samples: NDArray[np.float64],
) -> tuple[NDArray[np.float64], SteadyIIR]:
    primed = state.prime(float(samples[0])) if isinstance(state, UninitializedIIR) else state
    return primed.step(samples)


@dataclass(slots=True)
class LowPassFilter:
    """``Stream[RawBlock] → Stream[LowPassBlock]`` (Butterworth low-pass)."""

    name: ClassVar[str] = "lowpass"

    sample_rate: int
    cutoff_hz: float = 300.0
    order: int = 4
    _state_l: UninitializedIIR | SteadyIIR = field(init=False)
    _state_r: UninitializedIIR | SteadyIIR = field(init=False)

    def __post_init__(self) -> None:
        factory = IIRFactory(sos=make_lowpass_sos(self.order, self.cutoff_hz, self.sample_rate))
        self._state_l = factory.build()
        self._state_r = factory.build()

    def process(self, payload: RawBlock) -> list[LowPassBlock]:
        if payload.shape[0] == 0:
            return []
        left = np.asarray(payload[:, 0], dtype=np.float64)
        right = np.asarray(payload[:, 1], dtype=np.float64)
        l_out, self._state_l = _step_with_init(self._state_l, left)
        r_out, self._state_r = _step_with_init(self._state_r, right)
        return [LowPassBlock(np.column_stack([l_out, r_out]))]

    def flush(self) -> list[LowPassBlock]:
        return []
