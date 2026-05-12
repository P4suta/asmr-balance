"""Source / SkipReason algebraic data type.

A file is either analyzable (:class:`Source`) or skipped with a typed reason
(:class:`SkipMono`, :class:`SkipLayout`). The two skip variants are distinct
types so that :class:`basedpyright`'s exhaustive-match analysis flags an
unhandled case at the :func:`assert_never` boundary in the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from asmr_balance.metrics.record import FileMeta


class LayoutPolicy(StrEnum):
    """How to fold non-stereo audio for analysis (ADR-0005).

    Values:
        FL_FR: Take the front-left and front-right channels verbatim.
        DOWNMIX: ITU-R BS.775 5.1+ downmix to stereo.
        NATIVE_WEIGHTED: BS.1770 multichannel-weighted mode; balance metrics
            are *not* emitted (they require a stereo signal).  LUFS is the
            only meaningful axis. Pipeline excludes balance reducers when
            this policy is active.
        SKIP: Reject any non-stereo layout with :class:`SkipLayout`.
    """

    FL_FR = "fl-fr"
    DOWNMIX = "downmix"
    NATIVE_WEIGHTED = "native-weighted"
    SKIP = "skip"


@dataclass(frozen=True, slots=True)
class Source:
    """An analyzable file: header metadata + analysis parameters.

    Note: this dataclass does *not* hold a decoded sample buffer or an open
    file handle. To stream blocks, pass the source to
    :func:`asmr_balance.source.open.iter_blocks`. This keeps the dataclass
    pickle-safe across :class:`concurrent.futures.ProcessPoolExecutor`.
    """

    meta: FileMeta
    n_channels: int
    block_samples: int
    layout_policy: LayoutPolicy


@dataclass(frozen=True, slots=True)
class SkipMono:
    """The file is mono — no L/R balance is meaningful."""

    meta: FileMeta
    reason: str = "mono input — no L/R balance to measure"


@dataclass(frozen=True, slots=True)
class SkipLayout:
    """The file has an unsupported channel layout under the active policy."""

    meta: FileMeta
    n_channels: int
    reason: str


type SkipReason = SkipMono | SkipLayout
"""Sum of typed skip reasons."""

type SourceResult = Source | SkipReason
"""The output of :func:`open_source` — analyze or skip."""
