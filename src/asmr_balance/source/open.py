"""``open_source`` — probe a file and decide analyze vs skip.

The function is the *only* boundary at which the layout policy collapses into
an ADT. The pipeline matches on the result exhaustively; new layout policies
are introduced by extending the match cascade and the union type, not by
adding side branches deep in the call stack.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from asmr_balance.graph.types import RawBlock
from asmr_balance.metrics.record import FileMeta
from asmr_balance.source.adt import (
    LayoutPolicy,
    SkipLayout,
    SkipMono,
    Source,
    SourceResult,
)
from asmr_balance.source.backend.dispatch import iter_pcm_frames, probe
from asmr_balance.source.layout import fold_to_stereo

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def open_source(path: Path, policy: LayoutPolicy, block_samples: int) -> SourceResult:
    """Probe ``path`` and return :class:`Source` or a typed skip reason.

    Decode failures (invalid file, unsupported codec) propagate as exceptions
    — they are I/O concerns, not domain decisions. The ADT is reserved for
    *policy* outcomes.

    Args:
        path: Audio or video file path.
        policy: Active :class:`LayoutPolicy` for non-stereo files.
        block_samples: PCM block size in samples (typically ``sample_rate * 0.1``).

    Returns:
        Either a :class:`Source` ready for graph execution, or a
        :class:`SkipMono` / :class:`SkipLayout` describing why the file was
        rejected for balance analysis.
    """
    if block_samples <= 0:
        msg = f"block_samples must be positive, got {block_samples}"
        raise ValueError(msg)

    probed = probe(path)
    meta = FileMeta(
        file_path=path,
        sample_rate=probed.sample_rate,
        duration_sec=probed.duration_sec,
        channel_layout=probed.layout_name,
    )
    if probed.n_channels == 1:
        return SkipMono(meta=meta)
    if probed.n_channels > 2 and policy is LayoutPolicy.SKIP:
        return SkipLayout(
            meta=meta,
            n_channels=probed.n_channels,
            reason=f"layout has {probed.n_channels} channels and policy=skip",
        )
    return Source(
        meta=meta,
        n_channels=probed.n_channels,
        block_samples=block_samples,
        layout_policy=policy,
    )


def iter_blocks(source: Source) -> Iterator[RawBlock]:
    """Stream :class:`RawBlock` payloads from a successfully-opened source.

    Layout folding happens in-line; the caller receives only well-formed
    ``(N, 2) float32`` stereo blocks. Mono-only frames (impossible for a
    valid :class:`Source`) and policy-rejected layouts are excluded at the
    :func:`open_source` boundary, so this iterator's contract is total.
    """
    for frame in iter_pcm_frames(source.meta.file_path, source.block_samples):
        stereo = fold_to_stereo(frame, source.n_channels, source.layout_policy)
        if stereo is None:
            # Unreachable in practice: open_source rejects layouts whose
            # folding would return None. Defensive against future policy
            # variants that may produce optional skips per-frame.
            continue
        yield RawBlock(stereo)
