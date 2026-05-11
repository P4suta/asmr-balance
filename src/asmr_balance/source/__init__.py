"""File source layer: probe + open + layout-fold + decode backends.

The :func:`open_source` function is the single boundary at which skip decisions
are made (layout policy, mono detection). Its result is an algebraic data type
:data:`SourceResult` of :class:`Source` (the file is analysable) or
:class:`SkipMono` / :class:`SkipLayout` (the file is rejected with reason).
Downstream code matches on the ADT exhaustively; ``basedpyright`` enforces
totality via ``assert_never``.

Decode backend dispatch is based on file extension (soundfile for pure audio,
PyAV for video containers). The backends are isolated in :mod:`asmr_balance.source.backend`.
"""

from __future__ import annotations

from asmr_balance.source.adt import (
    LayoutPolicy,
    SkipLayout,
    SkipMono,
    SkipReason,
    Source,
    SourceResult,
)
from asmr_balance.source.layout import fold_to_stereo
from asmr_balance.source.open import iter_blocks, open_source

__all__ = [
    "LayoutPolicy",
    "SkipLayout",
    "SkipMono",
    "SkipReason",
    "Source",
    "SourceResult",
    "fold_to_stereo",
    "iter_blocks",
    "open_source",
]
