"""Low-band phase coherence: ``corr(LPF(L), LPF(R))`` for the sub-300 Hz region.

ASMR mixes that are panned consistently still keep the bass image mono-like;
phase-inverted low frequencies indicate a mix mistake (the listener loses the
sub on a mono playback system).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

import numpy as np
import scipy.signal

from asmr_balance.dsp.correlation import WelfordCorrelation

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from asmr_balance.types import StereoBlock

_LOW_CUTOFF_HZ: Final[float] = 300.0
_LPF_ORDER: Final[int] = 4


def make_lowpass_sos(sample_rate: int) -> NDArray[np.float64]:
    if sample_rate <= 2 * _LOW_CUTOFF_HZ:
        msg = f"sample_rate {sample_rate} too low for low-band coherence"
        raise ValueError(msg)
    sos = scipy.signal.butter(
        _LPF_ORDER,
        _LOW_CUTOFF_HZ,
        btype="low",
        fs=sample_rate,
        output="sos",
    )
    return np.asarray(sos, dtype=np.float64)


@dataclass(slots=True)
class LowPhaseCoherence:
    """Streaming Pearson correlation of low-passed L and R."""

    sample_rate: int
    _sos: NDArray[np.float64] = field(init=False)
    _zi_l: NDArray[np.float64] = field(init=False)
    _zi_r: NDArray[np.float64] = field(init=False)
    _initialised: bool = field(default=False, init=False)
    _stats: WelfordCorrelation = field(default_factory=WelfordCorrelation, init=False)

    def __post_init__(self) -> None:
        self._sos = make_lowpass_sos(self.sample_rate)
        self._zi_l = scipy.signal.sosfilt_zi(self._sos)
        self._zi_r = scipy.signal.sosfilt_zi(self._sos)

    def push(self, block: StereoBlock) -> None:
        if block.size == 0:
            return
        left = block[:, 0].astype(np.float64, copy=False)
        right = block[:, 1].astype(np.float64, copy=False)
        if not self._initialised:
            self._zi_l = self._zi_l * float(left[0])
            self._zi_r = self._zi_r * float(right[0])
            self._initialised = True
        l_lp, self._zi_l = scipy.signal.sosfilt(self._sos, left, zi=self._zi_l)
        r_lp, self._zi_r = scipy.signal.sosfilt(self._sos, right, zi=self._zi_r)
        self._stats.update(l_lp, r_lp)

    def finalize(self) -> float:
        return self._stats.correlation
