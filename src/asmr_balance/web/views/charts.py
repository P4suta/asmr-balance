"""Plotly figure builders.

Each function takes the relevant domain subtree (and any threshold context)
and returns a :class:`ChartFigure` — a frozen dataclass with ``data`` and
``layout`` ready to feed ``Plotly.newPlot(div, data, layout)`` in the browser.

The builders never touch I/O, templates, or HTTP. Routes serialise the
figure via :meth:`ChartFigure.to_plotly_json` and embed it in HTML for
client-side hydration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from asmr_balance.metrics.subtrees import (
    BandImbalanceMetrics,
    DynamicsMetrics,
    SlidingMetrics,
)
from asmr_balance.nodes.bandsplit import BANDS
from asmr_balance.rules.thresholds import BandBiasThresholds, TruePeakClipThresholds

# ----------------------------------------------------------------------
# theme — matches the app.css dark palette so charts feel native
# ----------------------------------------------------------------------
_COLOR_OK = "#4ade80"
_COLOR_WARN = "#fbbf24"
_COLOR_FAIL = "#f87171"
_COLOR_NEUTRAL = "#5aa9ff"
_COLOR_FG = "#e8e8ea"
_COLOR_MUTED = "#8a8d96"
_COLOR_BORDER = "rgba(255,255,255,0.08)"

_BASE_LAYOUT: dict[str, Any] = {
    "paper_bgcolor": "transparent",
    "plot_bgcolor": "rgba(255,255,255,0.02)",
    "font": {"color": _COLOR_FG, "family": "system-ui, sans-serif"},
    "margin": {"l": 60, "r": 24, "t": 48, "b": 64},
}


# ----------------------------------------------------------------------
# ChartFigure — typed Plotly spec wrapper
# ----------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ChartFigure:
    """A complete Plotly figure spec, ready for ``Plotly.newPlot``."""

    data: list[dict[str, Any]]
    layout: dict[str, Any]

    def to_plotly_json(self) -> dict[str, Any]:
        """Return the ``{"data", "layout"}`` envelope for template embedding."""
        return {"data": self.data, "layout": self.layout}


# ----------------------------------------------------------------------
# horizontal-line helper for threshold markers
# ----------------------------------------------------------------------
def _threshold_line(y: float, color: str, label: str) -> dict[str, Any]:
    return {
        "type": "line",
        "xref": "paper",
        "x0": 0,
        "x1": 1,
        "yref": "y",
        "y0": y,
        "y1": y,
        "line": {"color": color, "dash": "dash", "width": 1},
        "name": label,
    }


# ----------------------------------------------------------------------
# inspect — band imbalance bars (1/3-octave)
# ----------------------------------------------------------------------
def _band_color(value: float, threshold_db: float) -> str:
    if abs(value) >= threshold_db:
        return _COLOR_WARN
    return _COLOR_NEUTRAL


def band_imbalance_figure(
    band: BandImbalanceMetrics, thresholds: BandBiasThresholds
) -> ChartFigure:
    """Per-band L/R imbalance (1/3-octave) with warn-threshold lines."""
    names = [b.name for b in BANDS]
    values = [float(band.third_octave.get(name, 0.0)) for name in names]
    colors = [_band_color(v, thresholds.db) for v in values]
    return ChartFigure(
        data=[
            {
                "type": "bar",
                "x": names,
                "y": values,
                "marker": {"color": colors, "line": {"width": 0}},
                "hovertemplate": "%{x}: %{y:+.2f} dB<extra></extra>",
                "name": "L − R",
            }
        ],
        layout={
            **_BASE_LAYOUT,
            "title": {"text": "1/3-octave imbalance (L − R, dB)", "x": 0.02},
            "xaxis": {
                "title": "Center frequency",
                "tickangle": -45,
                "gridcolor": _COLOR_BORDER,
                "tickfont": {"size": 10},
            },
            "yaxis": {
                "title": "Imbalance (dB)",
                "zeroline": True,
                "zerolinecolor": _COLOR_BORDER,
                "gridcolor": _COLOR_BORDER,
            },
            "shapes": [
                _threshold_line(thresholds.db, _COLOR_WARN, "warn"),
                _threshold_line(-thresholds.db, _COLOR_WARN, "warn"),
            ],
            "showlegend": False,
            "height": 320,
        },
    )


# ----------------------------------------------------------------------
# inspect — true peak per channel with warn / fail lines
# ----------------------------------------------------------------------
def true_peak_figure(dynamics: DynamicsMetrics, thresholds: TruePeakClipThresholds) -> ChartFigure:
    """Per-channel true peak bars with warn / fail dBTP horizontal lines."""
    return ChartFigure(
        data=[
            {
                "type": "bar",
                "x": ["L", "R"],
                "y": [
                    float(dynamics.true_peak_dbtp_l),
                    float(dynamics.true_peak_dbtp_r),
                ],
                "marker": {"color": [_COLOR_NEUTRAL, _COLOR_NEUTRAL]},
                "hovertemplate": "%{x}: %{y:.2f} dBTP<extra></extra>",
                "name": "dBTP",
            }
        ],
        layout={
            **_BASE_LAYOUT,
            "title": {"text": "True peak (dBTP)", "x": 0.02},
            "xaxis": {"title": "Channel"},
            "yaxis": {
                "title": "dBTP",
                "zeroline": True,
                "zerolinecolor": _COLOR_BORDER,
                "gridcolor": _COLOR_BORDER,
            },
            "shapes": [
                _threshold_line(thresholds.warn_dbtp, _COLOR_WARN, "warn"),
                _threshold_line(thresholds.fail_dbtp, _COLOR_FAIL, "fail"),
            ],
            "showlegend": False,
            "height": 280,
        },
    )


# ----------------------------------------------------------------------
# inspect — sliding ΔLU summary (max / p95 / std)
# ----------------------------------------------------------------------
def sliding_delta_figure(sliding: SlidingMetrics) -> ChartFigure:
    """Per-block ΔLU summary statistics as a 3-bar chart."""
    return ChartFigure(
        data=[
            {
                "type": "bar",
                "x": ["max", "p95", "std"],
                "y": [
                    float(sliding.max_lu),
                    float(sliding.p95_lu),
                    float(sliding.std_lu),
                ],
                "marker": {"color": [_COLOR_FAIL, _COLOR_WARN, _COLOR_NEUTRAL]},
                "hovertemplate": "%{x}: %{y:.2f} LU<extra></extra>",
                "name": "ΔLU",
            }
        ],
        layout={
            **_BASE_LAYOUT,
            "title": {
                "text": f"Sliding ΔLU stats (max at {sliding.t_max_sec:.1f}s)",
                "x": 0.02,
            },
            "xaxis": {"title": "Statistic"},
            "yaxis": {
                "title": "LU",
                "zeroline": True,
                "zerolinecolor": _COLOR_BORDER,
                "gridcolor": _COLOR_BORDER,
            },
            "showlegend": False,
            "height": 280,
        },
    )


# ----------------------------------------------------------------------
# scan — verdict donut (live-updated client-side via Plotly.restyle)
# ----------------------------------------------------------------------
def verdict_donut_figure(counts: dict[str, int] | None = None) -> ChartFigure:
    """Empty / seeded verdict-distribution donut.

    The scan UI hydrates this on render and calls ``Plotly.restyle`` per SSE
    event to update the slice values. A ``None`` counts dict produces the
    empty skeleton (all zeros).
    """
    populated = counts or {}
    values = [
        populated.get("OK", 0),
        populated.get("WARN", 0),
        populated.get("FAIL", 0),
    ]
    return ChartFigure(
        data=[
            {
                "type": "pie",
                "hole": 0.55,
                "labels": ["OK", "WARN", "FAIL"],
                "values": values,
                "marker": {"colors": [_COLOR_OK, _COLOR_WARN, _COLOR_FAIL]},
                "textposition": "inside",
                "hovertemplate": "%{label}: %{value} (%{percent})<extra></extra>",
            }
        ],
        layout={
            **_BASE_LAYOUT,
            "title": {"text": "Verdict distribution", "x": 0.02},
            "showlegend": True,
            "legend": {"orientation": "h", "y": -0.1},
            "height": 280,
        },
    )


# ----------------------------------------------------------------------
# scan — per-file ΔLU scatter (live-extended client-side via Plotly.extendTraces)
# ----------------------------------------------------------------------
def delta_scatter_figure() -> ChartFigure:
    """Empty per-file ΔLU scatter; client extends as SSE events arrive."""
    return ChartFigure(
        data=[
            {
                "type": "scatter",
                "mode": "markers",
                "x": [],
                "y": [],
                "text": [],
                "marker": {"color": _COLOR_NEUTRAL, "size": 8},
                "hovertemplate": "#%{x} %{text}: %{y:+.2f} LU<extra></extra>",
                "name": "ΔLU",
            }
        ],
        layout={
            **_BASE_LAYOUT,
            "title": {"text": "Per-file ΔLU (signed)", "x": 0.02},
            "xaxis": {"title": "File index", "gridcolor": _COLOR_BORDER},
            "yaxis": {
                "title": "ΔLU",
                "zeroline": True,
                "zerolinecolor": _COLOR_BORDER,
                "gridcolor": _COLOR_BORDER,
            },
            "showlegend": False,
            "height": 280,
        },
    )
