"""K-weighting filter — ITU-R BS.1770-5 spec-strict prefilter (ADR-0002 invariant).

Two-stage cascade (high-shelf pre-filter + RLB high-pass), implemented for any
sample rate via the RBJ Audio EQ Cookbook biquad formulas — the same standard
form used by ``pyloudnorm``. The high-shelf coefficients match the BS.1770-5
spec reference values at 48 kHz to printed precision; the
``tests/regression/test_pyloudnorm_parity.py`` regression test enforces
``±0.1 LU`` agreement with pyloudnorm across the full sample-rate range.

This module **does not change** the numeric behavior of the legacy
``dsp/kweight.py`` — the SOS coefficients are bit-identical. What changes is
the API surface: state is managed via
:class:`~asmr_balance.algebra.iir.UninitializedIIR` /
:class:`~asmr_balance.algebra.iir.SteadyIIR` (type-state) and the filter is a
:class:`~asmr_balance.graph.types.Filter` over
``RawBlock → KWeightedBlock``.

References:
* ITU-R BS.1770-5 (2023-11) — K-weighting and gating
* RBJ Audio EQ Cookbook — https://www.w3.org/TR/audio-eq-cookbook/
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from typing import ClassVar, Final

import numpy as np
from numpy.typing import NDArray

from asmr_balance.algebra.iir import IIRFactory, SteadyIIR, UninitializedIIR
from asmr_balance.graph.types import KWeightedBlock, RawBlock

_PRE_FILTER_FC: Final[float] = 1500.0
_PRE_FILTER_Q: Final[float] = 1.0 / math.sqrt(2.0)
_PRE_FILTER_GAIN_DB: Final[float] = 4.0

_RLB_FC: Final[float] = 38.0
_RLB_Q: Final[float] = 0.5


def _high_shelf_biquad(gain_db: float, q: float, fc: float, sample_rate: int) -> list[float]:
    a = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * math.pi * fc / sample_rate
    cw = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * q)
    sqa = math.sqrt(a)
    b0 = a * ((a + 1.0) + (a - 1.0) * cw + 2.0 * sqa * alpha)
    b1 = -2.0 * a * ((a - 1.0) + (a + 1.0) * cw)
    b2 = a * ((a + 1.0) + (a - 1.0) * cw - 2.0 * sqa * alpha)
    a0 = (a + 1.0) - (a - 1.0) * cw + 2.0 * sqa * alpha
    a1 = 2.0 * ((a - 1.0) - (a + 1.0) * cw)
    a2 = (a + 1.0) - (a - 1.0) * cw - 2.0 * sqa * alpha
    return [b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]


def _high_pass_biquad(q: float, fc: float, sample_rate: int) -> list[float]:
    w0 = 2.0 * math.pi * fc / sample_rate
    cw = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * q)
    b0 = (1.0 + cw) / 2.0
    b1 = -(1.0 + cw)
    b2 = (1.0 + cw) / 2.0
    a0 = 1.0 + alpha
    a1 = -2.0 * cw
    a2 = 1.0 - alpha
    return [b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]


@lru_cache(maxsize=32)
def _kweighting_sos_cached(sample_rate: int) -> tuple[tuple[float, ...], ...]:
    """Internal: tuple form for hashability so :func:`lru_cache` can memoise."""
    if sample_rate <= 0:
        msg = f"sample_rate must be positive, got {sample_rate}"
        raise ValueError(msg)
    nyquist = sample_rate / 2.0
    if nyquist <= _PRE_FILTER_FC or nyquist <= _RLB_FC:
        msg = (
            f"sample_rate {sample_rate} Hz is below Nyquist for K-weighting "
            f"(need > {2 * _PRE_FILTER_FC:.0f} Hz)"
        )
        raise ValueError(msg)
    shelf = _high_shelf_biquad(_PRE_FILTER_GAIN_DB, _PRE_FILTER_Q, _PRE_FILTER_FC, sample_rate)
    rlb = _high_pass_biquad(_RLB_Q, _RLB_FC, sample_rate)
    return (tuple(shelf), tuple(rlb))


def make_kweighting_sos(sample_rate: int) -> NDArray[np.float64]:
    """Compose K-weighting biquads (pre-filter + RLB) as a 2x6 SOS matrix.

    Args:
        sample_rate: Hz; must be positive and above ``2 * 1500 Hz`` Nyquist.

    Returns:
        ``(2, 6)`` ``float64`` SOS matrix suitable for :func:`scipy.signal.sosfilt`.

    Raises:
        ValueError: If ``sample_rate`` is non-positive or below Nyquist.
    """
    return np.asarray(_kweighting_sos_cached(sample_rate), dtype=np.float64)


def _step_with_init(
    state: UninitializedIIR | SteadyIIR,
    samples: NDArray[np.float64],
) -> tuple[NDArray[np.float64], SteadyIIR]:
    """Drive a per-channel filter: prime on first sample then step.

    The caller is responsible for guarding ``samples.size > 0``.
    """
    primed = state.prime(float(samples[0])) if isinstance(state, UninitializedIIR) else state
    return primed.step(samples)


@dataclass(slots=True)
class KWeightingFilter:
    """``Stream[RawBlock] → Stream[KWeightedBlock]`` (BS.1770-5 K-weighted)."""

    name: ClassVar[str] = "kweighting"

    sample_rate: int
    _state_l: UninitializedIIR | SteadyIIR = field(init=False)
    _state_r: UninitializedIIR | SteadyIIR = field(init=False)

    def __post_init__(self) -> None:
        factory = IIRFactory(sos=make_kweighting_sos(self.sample_rate))
        self._state_l = factory.build()
        self._state_r = factory.build()

    def process(self, payload: RawBlock) -> list[KWeightedBlock]:
        if payload.shape[0] == 0:
            return []
        left = np.asarray(payload[:, 0], dtype=np.float64)
        right = np.asarray(payload[:, 1], dtype=np.float64)
        l_out, self._state_l = _step_with_init(self._state_l, left)
        r_out, self._state_r = _step_with_init(self._state_r, right)
        return [KWeightedBlock(np.column_stack([l_out, r_out]))]

    def flush(self) -> list[KWeightedBlock]:
        return []
