"""Pure typeclasses backing the asmr-balance redesign.

This package contains no I/O and no DSP. It defines the algebraic shapes the
rest of the codebase consumes:

* :class:`~asmr_balance.algebra.reducer.Reducer` — streaming reducer protocol
* :class:`~asmr_balance.algebra.semilattice.Verdict` — bounded join-semilattice
* :class:`~asmr_balance.algebra.iir.UninitializedIIR` / :class:`~asmr_balance.algebra.iir.SteadyIIR`
  — type-state IIR filter pair (steady-state initialisation encoded in types)

All values defined here are frozen / hashable so that they remain safe to share
across :mod:`concurrent.futures.ProcessPoolExecutor` boundaries (Phase D).
"""

from __future__ import annotations

from asmr_balance.algebra.iir import IIRFactory, SteadyIIR, UninitializedIIR
from asmr_balance.algebra.reducer import Reducer
from asmr_balance.algebra.semilattice import Verdict

__all__ = [
    "IIRFactory",
    "Reducer",
    "SteadyIIR",
    "UninitializedIIR",
    "Verdict",
]
