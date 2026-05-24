"""Presentation views — pure projections from domain into wire-friendly shapes.

The views layer sits between the use cases (which return domain values like
:class:`FileResult` / :class:`MetricRecord`) and the templates / client JS
(which want pre-shaped data to render). Every view is a pure function: no
I/O, no globals, no template knowledge.
"""

from asmr_balance.web.views.charts import (
    ChartFigure,
    band_imbalance_figure,
    delta_scatter_figure,
    sliding_delta_figure,
    true_peak_figure,
    verdict_donut_figure,
)
from asmr_balance.web.views.diagnosis import Diagnosis, Finding, diagnose
from asmr_balance.web.views.insights import (
    HeadroomInsight,
    InspectInsights,
    LoudnessInsight,
    StereoBalanceInsight,
    ToneBalanceInsight,
    ToneRegion,
    derive_headroom,
    derive_inspect_insights,
    derive_loudness,
    derive_stereo_balance,
    derive_tone,
)

__all__ = [
    "ChartFigure",
    "Diagnosis",
    "Finding",
    "HeadroomInsight",
    "InspectInsights",
    "LoudnessInsight",
    "StereoBalanceInsight",
    "ToneBalanceInsight",
    "ToneRegion",
    "band_imbalance_figure",
    "delta_scatter_figure",
    "derive_headroom",
    "derive_inspect_insights",
    "derive_loudness",
    "derive_stereo_balance",
    "derive_tone",
    "diagnose",
    "sliding_delta_figure",
    "true_peak_figure",
    "verdict_donut_figure",
]
