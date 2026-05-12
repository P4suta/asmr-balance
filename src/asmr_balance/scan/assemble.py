"""Default graph builder + result assembly.

Two responsibilities:

* :func:`build_default_graph` — wires up the canonical eight-reducer graph
  for a single sample-rate. The wiring is the single source of truth for
  "what asmr-balance computes"; adding a metric means adding one filter call
  (optional) and one ``.reduce()`` here.
* :func:`assemble_record` — folds the scheduler's keyed result dict into a
  :class:`MetricRecord`. No string-key gymnastics: the keys ``"loudness"``,
  ``"lra"``, … match :data:`_REDUCER_NAMES`, which are also the names
  registered on the graph.
"""

from __future__ import annotations

from typing import Any

from asmr_balance.config.model import Config
from asmr_balance.graph.builder import GraphBuilder
from asmr_balance.graph.frozen import FrozenGraph
from asmr_balance.metrics.band import BandImbalanceReducer
from asmr_balance.metrics.correlation import StereoCorrelationReducer
from asmr_balance.metrics.dynamics import TruePeakReducer, derive_psr_db
from asmr_balance.metrics.loudness import GateConfig, IntegratedLoudnessReducer
from asmr_balance.metrics.lra import LRAReducer
from asmr_balance.metrics.phase import LowPhaseCoherenceReducer
from asmr_balance.metrics.record import FileMeta, MetricRecord, ScanStatus
from asmr_balance.metrics.sliding import SlidingImbalanceReducer

_LOUDNESS = "loudness"
_LRA = "lra"
_SLIDING = "sliding"
_CORRELATION = "correlation"
_BAND = "band"
_PHASE = "phase"
_TRUEPEAK = "truepeak"


def build_default_graph(config: Config, sample_rate: int) -> FrozenGraph:
    """Construct the canonical analysis graph for one file's sample rate."""
    g = GraphBuilder()
    raw = g.source()
    kw = g.kweight(raw, sample_rate=sample_rate)
    z = g.zblocks(kw, sample_rate=sample_rate)
    short_z = g.shortterm_zblocks(kw, sample_rate=sample_rate)
    lpf = g.lowpass(raw, sample_rate=sample_rate, cutoff_hz=300.0, order=4)
    bands = g.bandsplit(raw, sample_rate=sample_rate)
    oversampled = g.oversample4x(raw)

    gate = GateConfig(abs_gate_lufs=config.gate_lufs)
    g.reduce(_LOUDNESS, IntegratedLoudnessReducer(gate=gate), z)
    g.reduce(_LRA, LRAReducer(), short_z)
    g.reduce(_SLIDING, SlidingImbalanceReducer(), z)
    g.reduce(_CORRELATION, StereoCorrelationReducer(), raw)
    g.reduce(_BAND, BandImbalanceReducer(), bands)
    g.reduce(_PHASE, LowPhaseCoherenceReducer(), lpf)
    g.reduce(_TRUEPEAK, TruePeakReducer(), oversampled)
    return g.freeze()


def assemble_record(meta: FileMeta, scheduler_output: dict[str, Any]) -> MetricRecord:
    """Compose a :class:`MetricRecord` from named scheduler outputs."""
    lra = scheduler_output[_LRA]
    peak = scheduler_output[_TRUEPEAK]
    dynamics = derive_psr_db(peak, lra)
    return MetricRecord(
        meta=meta,
        status=ScanStatus.ANALYZED,
        loudness=scheduler_output[_LOUDNESS],
        lra=lra,
        correlation=scheduler_output[_CORRELATION],
        band=scheduler_output[_BAND],
        sliding=scheduler_output[_SLIDING],
        phase=scheduler_output[_PHASE],
        dynamics=dynamics,
    )
