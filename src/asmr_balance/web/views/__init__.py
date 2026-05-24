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

__all__ = [
    "ChartFigure",
    "band_imbalance_figure",
    "delta_scatter_figure",
    "sliding_delta_figure",
    "true_peak_figure",
    "verdict_donut_figure",
]
