"""ITU-R BS.1770-5 K-weighting biquads.

Two-stage cascade (high-shelf pre-filter + RLB high-pass), implemented for any
sample rate using the RBJ Audio EQ Cookbook biquad formulas — the same standard
form used by ``pyloudnorm``.  The high-shelf coefficients match the BS.1770-5
spec reference values at 48 kHz to printed precision (verified by
``tests/regression/test_pyloudnorm_parity.py``).

References:
- ITU-R BS.1770-5 (2023-11): K-weighting and gating.
- Robert Bristow-Johnson, "Audio EQ Cookbook" (RBJ):
  https://www.w3.org/TR/audio-eq-cookbook/
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

import numpy as np
import scipy.signal

if TYPE_CHECKING:
    from numpy.typing import NDArray

_PRE_FILTER_FC: Final[float] = 1500.0  # Hz, K-weighting pre-filter centre
_PRE_FILTER_Q: Final[float] = 1.0 / math.sqrt(2.0)
_PRE_FILTER_GAIN_DB: Final[float] = 4.0

_RLB_FC: Final[float] = 38.0  # Hz, RLB cut-off
_RLB_Q: Final[float] = 0.5


def _high_shelf_biquad(gain_db: float, q: float, fc: float, sample_rate: int) -> list[float]:
    """Return SOS row ``[b0, b1, b2, 1, a1, a2]`` (RBJ cookbook high-shelf)."""
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
    """Return SOS row ``[b0, b1, b2, 1, a1, a2]`` (RBJ cookbook 2nd-order HP)."""
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


def make_kweighting_sos(sample_rate: int) -> NDArray[np.float64]:
    """Compose K-weighting biquads (pre-filter + RLB) as SOS.

    Args:
        sample_rate: Hz. Must be positive.

    Returns:
        2x6 array of SOS sections, suitable for ``scipy.signal.sosfilt``.

    Raises:
        ValueError: If ``sample_rate`` is non-positive or below ``2·fc`` of any
            stage (Nyquist would be violated).
    """
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
    return np.asarray([shelf, rlb], dtype=np.float64)


def apply_kweighting(
    samples: NDArray[np.floating],
    sos: NDArray[np.float64],
    zi: NDArray[np.float64] | None = None,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Apply K-weighting SOS to a 1-D channel; return ``(filtered, zi_next)``.

    Args:
        samples: 1-D float array.
        sos: 2x6 SOS coefficients from ``make_kweighting_sos``.
        zi: Filter state. If ``None``, initialise to steady-state at
            ``samples[0]`` (or zeros if the input is empty).

    Returns:
        Tuple of filtered samples (``float64``) and the next state vector.
    """
    if samples.ndim != 1:
        msg = f"samples must be 1-D, got shape {samples.shape}"
        raise ValueError(msg)
    if zi is None:
        zi_init = scipy.signal.sosfilt_zi(sos)
        zi = zi_init * (float(samples[0]) if samples.size > 0 else 0.0)
    if samples.size == 0:
        return np.asarray([], dtype=np.float64), np.asarray(zi, dtype=np.float64)
    out, zi_next = scipy.signal.sosfilt(sos, samples.astype(np.float64, copy=False), zi=zi)
    return np.asarray(out, dtype=np.float64), np.asarray(zi_next, dtype=np.float64)
