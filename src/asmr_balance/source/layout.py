"""Multichannel → stereo folding per layout policy (ADR-0005).

This module is the *only* place where layout reasoning lives. The pipeline
never inspects channel counts directly; it pulls a stereo
:data:`~asmr_balance.graph.types.RawBlock` stream from
:func:`asmr_balance.source.open.iter_blocks` and trusts the layout invariant.
"""

from __future__ import annotations

import math
from typing import Final

import numpy as np
from numpy.typing import NDArray

from asmr_balance.source.adt import LayoutPolicy

_INV_SQRT2: Final[float] = 1.0 / math.sqrt(2.0)


def fold_to_stereo(
    frame: NDArray[np.float32],
    n_channels: int,
    policy: LayoutPolicy,
) -> NDArray[np.float32] | None:
    """Fold an ``(N, n_channels)`` frame to ``(N, 2)`` per policy.

    Returns ``None`` when the layout cannot be analyzed for balance under the
    selected policy. The skip decision is settled at
    :func:`asmr_balance.source.open.open_source` boundary; this function
    cannot be reached at all when the source has already been rejected.

    Args:
        frame: ``(N, n_channels)`` ``float32`` PCM block.
        n_channels: Layout cardinality (must match ``frame.shape[1]``).
        policy: Active layout policy.

    Returns:
        A ``(N, 2)`` contiguous ``float32`` view, or ``None`` if the layout
        cannot be folded under the policy.
    """
    if n_channels == 1:
        return None
    if n_channels == 2:
        return np.ascontiguousarray(frame, dtype=np.float32)
    if policy is LayoutPolicy.SKIP:
        return None
    if policy is LayoutPolicy.NATIVE_WEIGHTED:
        # Balance reducers are excluded at the graph-build boundary; the
        # source produces synthetic stereo via FL_FR for the loudness path.
        return np.ascontiguousarray(frame[:, :2], dtype=np.float32)
    if policy is LayoutPolicy.FL_FR or n_channels < 5:
        return np.ascontiguousarray(frame[:, :2], dtype=np.float32)
    # ITU-R BS.775 5.1+ downmix: FL FR FC LFE BL BR ...
    fl = frame[:, 0]
    fr = frame[:, 1]
    fc = frame[:, 2]
    bl = frame[:, 4] if frame.shape[1] >= 5 else 0.0
    br = frame[:, 5] if frame.shape[1] >= 6 else 0.0
    left = fl + _INV_SQRT2 * fc + 0.5 * bl
    right = fr + _INV_SQRT2 * fc + 0.5 * br
    return np.ascontiguousarray(np.column_stack([left, right]), dtype=np.float32)
