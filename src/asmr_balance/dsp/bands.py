"""4-band Butterworth filterbank for per-band L/R imbalance (ADR-0006).

Bands (Hz):

- ``low``      : ``< 250``
- ``low_mid``  : ``250 – 2000``
- ``high_mid`` : ``2000 – 8000``
- ``high``     : ``> 8000``

Order-4 SOS, with ``sosfilt_zi`` steady-state initial conditions per channel.
The bandpass filters are **not** complementary (Σ band_energy ≠ total) — we
expose only per-band L/R ratios, never band sums (ADR-0006).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Final

import numpy as np
import scipy.signal

if TYPE_CHECKING:
    from numpy.typing import NDArray


class Band(StrEnum):
    LOW = "low"
    LOW_MID = "low_mid"
    HIGH_MID = "high_mid"
    HIGH = "high"


_LOW_HZ: Final[float] = 250.0
_LOW_MID_HZ: Final[tuple[float, float]] = (250.0, 2000.0)
_HIGH_MID_HZ: Final[tuple[float, float]] = (2000.0, 8000.0)
_HIGH_HZ: Final[float] = 8000.0
_ORDER: Final[int] = 4


def make_band_sos(band: Band, sample_rate: int) -> NDArray[np.float64]:
    """Return SOS coefficients for the given band at ``sample_rate``."""
    if sample_rate <= 2 * _HIGH_HZ:
        msg = (
            f"sample_rate {sample_rate} Hz is too low for the high-band edge "
            f"({_HIGH_HZ} Hz); need > {2 * _HIGH_HZ} Hz"
        )
        raise ValueError(msg)
    kwargs = {"N": _ORDER, "fs": sample_rate, "output": "sos"}
    if band is Band.LOW:
        sos = scipy.signal.butter(Wn=_LOW_HZ, btype="low", **kwargs)
    elif band is Band.LOW_MID:
        sos = scipy.signal.butter(Wn=_LOW_MID_HZ, btype="bandpass", **kwargs)
    elif band is Band.HIGH_MID:
        sos = scipy.signal.butter(Wn=_HIGH_MID_HZ, btype="bandpass", **kwargs)
    else:  # Band.HIGH
        sos = scipy.signal.butter(Wn=_HIGH_HZ, btype="high", **kwargs)
    return np.asarray(sos, dtype=np.float64)


@dataclass(slots=True)
class BandImbalanceAccumulator:
    """Stream stereo samples through 4 bands; accumulate per-band sum-of-squares."""

    sample_rate: int
    _sos_per_band: dict[Band, NDArray[np.float64]] = field(default_factory=dict, init=False)
    _zi_l: dict[Band, NDArray[np.float64]] = field(default_factory=dict, init=False)
    _zi_r: dict[Band, NDArray[np.float64]] = field(default_factory=dict, init=False)
    _sum_sq_l: dict[Band, float] = field(default_factory=dict, init=False)
    _sum_sq_r: dict[Band, float] = field(default_factory=dict, init=False)
    _initialised: bool = field(default=False, init=False)
    _n_samples: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        for band in Band:
            sos = make_band_sos(band, self.sample_rate)
            self._sos_per_band[band] = sos
            self._zi_l[band] = scipy.signal.sosfilt_zi(sos)
            self._zi_r[band] = scipy.signal.sosfilt_zi(sos)
            self._sum_sq_l[band] = 0.0
            self._sum_sq_r[band] = 0.0

    def push(self, left: NDArray[np.floating], right: NDArray[np.floating]) -> None:
        if left.size == 0:
            return
        l64 = left.astype(np.float64, copy=False)
        r64 = right.astype(np.float64, copy=False)
        if not self._initialised:
            for band in Band:
                self._zi_l[band] = self._zi_l[band] * float(l64[0])
                self._zi_r[band] = self._zi_r[band] * float(r64[0])
            self._initialised = True
        for band, sos in self._sos_per_band.items():
            l_filt, self._zi_l[band] = scipy.signal.sosfilt(sos, l64, zi=self._zi_l[band])
            r_filt, self._zi_r[band] = scipy.signal.sosfilt(sos, r64, zi=self._zi_r[band])
            self._sum_sq_l[band] += float(np.dot(l_filt, l_filt))
            self._sum_sq_r[band] += float(np.dot(r_filt, r_filt))
        self._n_samples += l64.size

    def imbalance_db(self, band: Band) -> float:
        """``10·log10(RMS_L² / RMS_R²)`` for ``band``; ``nan`` when undefined."""
        if self._n_samples == 0:
            return float("nan")
        left_e = self._sum_sq_l[band]
        right_e = self._sum_sq_r[band]
        if left_e <= 0.0 or right_e <= 0.0:
            return float("nan")
        return 10.0 * math.log10(left_e / right_e)
