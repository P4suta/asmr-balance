"""Normalise decoded frames into stereo ``StereoBlock`` per the layout policy.

This is the single place where multichannel → stereo conversion lives (ADR-0005).
``to_stereo`` returns ``None`` when the policy dictates that the file be
skipped from balance analysis (``mono`` always, and other layouts when policy
== ``skip``).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final, cast

import numpy as np

from asmr_balance.config import LayoutPolicy
from asmr_balance.decode import AudioMetadata, iter_pcm_blocks

if TYPE_CHECKING:
    from collections.abc import Iterator

    from numpy.typing import NDArray

    from asmr_balance.types import StereoBlock

_INV_SQRT2: Final[float] = 1.0 / math.sqrt(2.0)


def to_stereo(
    frame: NDArray[np.float32],
    n_channels: int,
    policy: LayoutPolicy,
) -> StereoBlock | None:
    """Convert ``(N, n_channels)`` frame to ``(N, 2)`` stereo per ``policy``.

    Returns ``None`` if the layout cannot be analysed for balance under the
    chosen policy. The caller records the skip reason.
    """
    if n_channels == 1:
        return None
    if n_channels == 2:
        return np.ascontiguousarray(frame, dtype=np.float32)
    if policy is LayoutPolicy.SKIP:
        return None
    if policy is LayoutPolicy.FL_FR or n_channels < 5:
        return np.ascontiguousarray(frame[:, :2], dtype=np.float32)
    # ITU-R BS.775 downmix for 5.1+ (FL, FR, FC, LFE, BL, BR, ...)
    fl = frame[:, 0]
    fr = frame[:, 1]
    fc = frame[:, 2]
    bl = frame[:, 4] if frame.shape[1] >= 5 else 0.0
    br = frame[:, 5] if frame.shape[1] >= 6 else 0.0
    left = fl + _INV_SQRT2 * fc + 0.5 * bl
    right = fr + _INV_SQRT2 * fc + 0.5 * br
    return np.ascontiguousarray(np.column_stack([left, right]), dtype=np.float32)


def iter_stereo_blocks(
    metadata: AudioMetadata,
    policy: LayoutPolicy,
    block_samples: int,
) -> Iterator[StereoBlock]:
    """Stream stereo blocks for ``metadata`` honouring the layout policy.

    Iteration is empty when the layout is rejected — callers should detect
    that via ``should_skip`` before consuming.  Once we get past that gate,
    ``to_stereo`` is guaranteed to return ndarray (precondition enforced by
    ``should_skip`` symmetry, see tests/unit/test_stream.py).
    """
    if should_skip(metadata.n_channels, policy):
        return
    n = metadata.n_channels
    for frame in iter_pcm_blocks(metadata, block_samples):
        # ``should_skip`` precondition guarantees ``to_stereo`` returns ndarray
        stereo = cast("StereoBlock", to_stereo(frame, n, policy))
        yield stereo


def should_skip(n_channels: int, policy: LayoutPolicy) -> bool:
    """Return True when the layout policy will reject the file."""
    if n_channels == 1:
        return True
    if n_channels == 2:
        return False
    return policy is LayoutPolicy.SKIP


def skip_reason(n_channels: int, policy: LayoutPolicy) -> str:
    """Human-readable reason; only meaningful when ``should_skip`` is True."""
    if n_channels == 1:
        return "mono input — no L/R balance to measure"
    if n_channels > 2 and policy is LayoutPolicy.SKIP:
        return f"layout has {n_channels} channels and policy=skip"
    return ""
