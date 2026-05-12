"""Filter implementations for the signal DAG.

Each module in this package exports one or more :class:`~asmr_balance.graph.types.Filter`
implementations: stateful, sequential Mealy machines that transform one stage
of payload into another. They contain *no* I/O, *no* config knowledge, and
*no* knowledge of downstream reducers — they only consume their declared input
stage and emit their declared output stage.

The cardinality of inputs to outputs varies per filter:

* :class:`~asmr_balance.nodes.kweighting.KWeightingFilter` — 1 in / 1 out
* :class:`~asmr_balance.nodes.zblocks.ZBlocksFilter` — N in / M out (windowed)
* :class:`~asmr_balance.nodes.bandsplit.ThirdOctaveBandSplit` — 1 in / 1 out (single BandedFrame)
* :class:`~asmr_balance.nodes.oversample.Oversample4xPolyphase` — 1 in / 1 out (4x length)
"""

from __future__ import annotations

from asmr_balance.nodes.bandsplit import (
    BANDS,
    BandedFrame,
    BandSpec,
    FourBandPartition,
    ThirdOctaveBandSplit,
)
from asmr_balance.nodes.kweighting import KWeightingFilter, make_kweighting_sos
from asmr_balance.nodes.lowpass import LowPassFilter
from asmr_balance.nodes.oversample import Oversample4xPolyphase
from asmr_balance.nodes.zblocks import ShortTermZBlocksFilter, ZBlocksFilter

__all__ = [
    "BANDS",
    "BandSpec",
    "BandedFrame",
    "FourBandPartition",
    "KWeightingFilter",
    "LowPassFilter",
    "Oversample4xPolyphase",
    "ShortTermZBlocksFilter",
    "ThirdOctaveBandSplit",
    "ZBlocksFilter",
    "make_kweighting_sos",
]
