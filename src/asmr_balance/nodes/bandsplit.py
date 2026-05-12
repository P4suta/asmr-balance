"""1/3-octave band split — ANSI S1.11 Class 1 / IEC 61260-1 preferred centers.

Replaces the legacy 4-band Butterworth split (ADR-0006). The 1/3-octave 31
bands form the always-on primary partition of the audio spectrum; the
legacy 4-band scheme (``low / low_mid / high_mid / high``) is recovered as a
**roll-up aggregate** by summing per-band energies in
:mod:`asmr_balance.metrics.band`.

Center frequencies follow ISO 266 preferred numbers from 20 Hz to 20 kHz
inclusive (31 values). Each band is realized as a 4th-order Butterworth
band-pass with edges ``f_c / 2^(1/6)`` and ``f_c * 2^(1/6)`` (the standard
1/3-octave half-width). Edge bands are clipped to the open Nyquist interval.

The filter is a Mealy stream transformer with 31 independent IIR states per
channel. Its output is a single :data:`BandedFrame` per input block: a frozen
mapping ``band_name -> (N, 2) float64``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import ClassVar, Final, NewType

import numpy as np
import scipy.signal as _sps
from numpy.typing import NDArray

from asmr_balance.algebra.iir import IIRFactory, SteadyIIR, UninitializedIIR
from asmr_balance.graph.types import RawBlock


@dataclass(frozen=True, slots=True)
class BandSpec:
    """One 1/3-octave band: nominal center, low/high edges (Hz), partition tag."""

    name: str
    center_hz: float
    low_edge_hz: float
    high_edge_hz: float
    partition: str  # "low" | "low_mid" | "high_mid" | "high"


_THIRD_OCTAVE_RATIO: Final[float] = 2.0 ** (1.0 / 6.0)
_NOMINAL_CENTERS: Final[tuple[float, ...]] = (
    20.0, 25.0, 31.5, 40.0, 50.0, 63.0, 80.0, 100.0, 125.0, 160.0,
    200.0, 250.0, 315.0, 400.0, 500.0, 630.0, 800.0, 1000.0, 1250.0, 1600.0,
    2000.0, 2500.0, 3150.0, 4000.0, 5000.0, 6300.0, 8000.0, 10000.0, 12500.0,
    16000.0, 20000.0,
)


def _partition_for(center_hz: float) -> str:
    if center_hz < 250.0:
        return "low"
    if center_hz < 2000.0:
        return "low_mid"
    if center_hz < 8000.0:
        return "high_mid"
    return "high"


def _band_name(center_hz: float) -> str:
    if center_hz >= 1000.0:
        return f"b_{int(round(center_hz))}hz"
    if center_hz == int(center_hz):
        return f"b_{int(center_hz)}hz"
    # 31.5 → b_31_5hz
    return f"b_{str(center_hz).replace('.', '_')}hz"


BANDS: Final[tuple[BandSpec, ...]] = tuple(
    BandSpec(
        name=_band_name(fc),
        center_hz=fc,
        low_edge_hz=fc / _THIRD_OCTAVE_RATIO,
        high_edge_hz=fc * _THIRD_OCTAVE_RATIO,
        partition=_partition_for(fc),
    )
    for fc in _NOMINAL_CENTERS
)
"""The full canonical 1/3-octave band table (31 entries, 20 Hz – 20 kHz)."""


@dataclass(frozen=True, slots=True)
class FourBandPartition:
    """Names of the 1/3-octave bands belonging to each legacy 4-band slot."""

    low: tuple[str, ...]
    low_mid: tuple[str, ...]
    high_mid: tuple[str, ...]
    high: tuple[str, ...]

    @classmethod
    def from_bands(cls, bands: tuple[BandSpec, ...]) -> FourBandPartition:
        groups: dict[str, list[str]] = {"low": [], "low_mid": [], "high_mid": [], "high": []}
        for b in bands:
            groups[b.partition].append(b.name)
        return cls(
            low=tuple(groups["low"]),
            low_mid=tuple(groups["low_mid"]),
            high_mid=tuple(groups["high_mid"]),
            high=tuple(groups["high"]),
        )


BandedFrame = NewType("BandedFrame", dict[str, NDArray[np.float64]])
"""One frame's worth of per-band stereo samples: ``band_name → (N, 2) float64``.

Treated as a single payload through the graph; downstream
:class:`~asmr_balance.metrics.band.BandImbalanceReducer` consumes the entire
frame in one ``update`` call. Each value is a contiguous ``float64`` array of
shape ``(N, 2)``.
"""


@lru_cache(maxsize=64)
def _bandpass_sos(
    order: int,
    low_edge_hz: float,
    high_edge_hz: float,
    sample_rate: int,
) -> tuple[tuple[float, ...], ...]:
    nyquist = sample_rate / 2.0
    # Clip edges into the open Nyquist interval; if the band lies entirely above
    # Nyquist (or entirely at DC), raise — we don't silently drop bands.
    low = max(0.5, low_edge_hz)
    high = min(nyquist - 0.5, high_edge_hz)
    if not (0.0 < low < high < nyquist):
        msg = (
            f"band edges ({low_edge_hz}, {high_edge_hz}) Hz cannot fit inside "
            f"(0, {nyquist}) for sample_rate={sample_rate}"
        )
        raise ValueError(msg)
    sos = _sps.butter(order, [low, high], btype="band", fs=sample_rate, output="sos")
    return tuple(tuple(row) for row in sos)


def _step_with_init(
    state: UninitializedIIR | SteadyIIR,
    samples: NDArray[np.float64],
) -> tuple[NDArray[np.float64], SteadyIIR]:
    primed = state.prime(float(samples[0])) if isinstance(state, UninitializedIIR) else state
    return primed.step(samples)


@dataclass(slots=True)
class _PerBandState:
    """Per-band, per-channel filter state."""

    spec: BandSpec
    left: UninitializedIIR | SteadyIIR
    right: UninitializedIIR | SteadyIIR


@dataclass(slots=True)
class ThirdOctaveBandSplit:
    """``Stream[RawBlock] → Stream[BandedFrame]`` (31 1/3-octave bands)."""

    name: ClassVar[str] = "third_octave_bandsplit"

    sample_rate: int
    order: int = 4
    bands: tuple[BandSpec, ...] = BANDS
    _states: list[_PerBandState] = field(init=False)

    def __post_init__(self) -> None:
        states: list[_PerBandState] = []
        for spec in self.bands:
            sos = np.asarray(
                _bandpass_sos(self.order, spec.low_edge_hz, spec.high_edge_hz, self.sample_rate),
                dtype=np.float64,
            )
            factory = IIRFactory(sos=sos)
            states.append(_PerBandState(spec=spec, left=factory.build(), right=factory.build()))
        self._states = states

    def process(self, payload: RawBlock) -> list[BandedFrame]:
        if payload.shape[0] == 0:
            return []
        left = np.asarray(payload[:, 0], dtype=np.float64)
        right = np.asarray(payload[:, 1], dtype=np.float64)
        frame: dict[str, NDArray[np.float64]] = {}
        for st in self._states:
            l_out, st.left = _step_with_init(st.left, left)
            r_out, st.right = _step_with_init(st.right, right)
            frame[st.spec.name] = np.column_stack([l_out, r_out])
        return [BandedFrame(frame)]

    def flush(self) -> list[BandedFrame]:
        return []
