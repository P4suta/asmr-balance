"""Type-state IIR filters — initialization encoded in types, not in flags.

Stateful IIR filters in this codebase obey a strict two-phase lifecycle:

1. **Uninitialised** — the filter has the SOS coefficients and a template
   ``zi`` (from :func:`scipy.signal.sosfilt_zi`) but the first input sample
   has not yet been observed. Calling ``step`` in this state would produce a
   transient artifact that BS.1770 parity tests reject.
2. **Steady** — the first sample has been used to scale the template ``zi``
   into a steady-state initial condition. ``step`` is now total.

Previous incarnations encoded this with a runtime ``self._initialized: bool``
flag and a guard inside ``push``. That pattern surfaces three times in the
legacy DSP layer (kweight / bands / phase) with subtle divergences. Here we
make the invariant *type-level*: two disjoint classes
(:class:`UninitializedIIR` and :class:`SteadyIIR`) implement disjoint
interfaces (``prime`` vs ``step``), and the only legal transition is
``UninitializedIIR.prime(x0) -> SteadyIIR``. ``basedpyright`` strict rejects
``uninit.step(...)`` statically.

The two-class formulation is preferred over a phantom-type ``IIRFilter[State]``
because Python's variance for ``Protocol`` generics is weak enough that the
former is the most idiomatic way to make the invariant non-bypassable.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.signal as _sps
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class SteadyIIR:
    """IIR filter in steady state — ``step`` is total.

    ``sos`` is the second-order-sections coefficient matrix (immutable). ``zi``
    is the running filter delay-line state, advanced on every ``step``.
    """

    sos: NDArray[np.float64]
    zi: NDArray[np.float64]

    def step(self, samples: NDArray[np.float64]) -> tuple[NDArray[np.float64], SteadyIIR]:
        """Filter one chunk of samples and return ``(output, next_state)``.

        Args:
            samples: 1-D input chunk (any length, including empty).

        Returns:
            A tuple of the filtered output and the next steady-state filter.
        """
        out, next_zi = _sps.sosfilt(self.sos, samples, zi=self.zi)
        return out, SteadyIIR(sos=self.sos, zi=next_zi)


@dataclass(frozen=True, slots=True)
class UninitializedIIR:
    """IIR filter pre-prime — only ``prime`` is defined.

    Construct via :class:`IIRFactory.build` or directly with the SOS matrix.
    Calling :meth:`prime` with the first observed sample yields a
    :class:`SteadyIIR` whose ``zi`` is scaled to the constant-input
    steady-state response of the filter.
    """

    sos: NDArray[np.float64]
    zi_template: NDArray[np.float64]

    def prime(self, first_sample: float) -> SteadyIIR:
        """Scale the template ``zi`` by the first sample and transition to steady.

        Args:
            first_sample: The first sample of the stream the filter will
                process. The template ``zi`` from :func:`scipy.signal.sosfilt_zi`
                corresponds to unit DC input; scaling by ``first_sample``
                yields the steady-state response for that constant input.

        Returns:
            A :class:`SteadyIIR` ready to consume the rest of the stream.
        """
        return SteadyIIR(sos=self.sos, zi=self.zi_template * float(first_sample))


@dataclass(frozen=True, slots=True)
class IIRFactory:
    """Convenience factory that holds a frozen SOS matrix.

    Designers compute the SOS once (often via cached design functions like
    :func:`asmr_balance.nodes.kweighting.make_kweighting_sos`) and reuse a
    single factory across many filter instances. ``build()`` always returns a
    fresh :class:`UninitializedIIR` so per-channel state is independent.
    """

    sos: NDArray[np.float64]

    def build(self) -> UninitializedIIR:
        """Construct an unprimed filter using ``scipy.signal.sosfilt_zi``."""
        zi = _sps.sosfilt_zi(self.sos)
        return UninitializedIIR(sos=self.sos, zi_template=zi)
