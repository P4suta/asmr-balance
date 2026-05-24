from __future__ import annotations

from pathlib import Path

from asmr_balance.config.model import Config
from asmr_balance.metrics.subtrees import (
    BandImbalanceMetrics,
    DynamicsMetrics,
    SlidingMetrics,
)
from asmr_balance.nodes.bandsplit import BANDS
from asmr_balance.rules.thresholds import BandBiasThresholds, TruePeakClipThresholds
from asmr_balance.scan.pipeline import scan_one
from asmr_balance.web.views import (
    ChartFigure,
    band_imbalance_figure,
    delta_scatter_figure,
    sliding_delta_figure,
    true_peak_figure,
    verdict_donut_figure,
)


def _make_band(values: dict[str, float] | None = None) -> BandImbalanceMetrics:
    third = {b.name: 0.0 for b in BANDS}
    if values:
        third.update(values)
    return BandImbalanceMetrics(low=0.0, low_mid=0.0, high_mid=0.0, high=0.0, third_octave=third)


def test_chart_figure_to_plotly_json_round_trip() -> None:
    fig = ChartFigure(data=[{"type": "bar"}], layout={"title": "t"})
    assert fig.to_plotly_json() == {"data": [{"type": "bar"}], "layout": {"title": "t"}}


def test_band_imbalance_has_one_bar_per_band_and_threshold_lines() -> None:
    band = _make_band()
    fig = band_imbalance_figure(band, BandBiasThresholds())
    trace = fig.data[0]
    assert trace["type"] == "bar"
    assert len(trace["x"]) == len(BANDS)
    assert len(trace["y"]) == len(BANDS)
    # Two threshold lines (positive + negative).
    assert len(fig.layout["shapes"]) == 2


def test_band_imbalance_colors_breach_bands_warn() -> None:
    # Pick two real band slugs straight from BANDS so the test never drifts
    # from the production naming convention (b_<freq>hz).
    breach = BANDS[5].name  # arbitrary mid-low band
    calm = BANDS[12].name
    band = _make_band({breach: 10.0, calm: 1.0})
    thresholds = BandBiasThresholds(db=4.0)
    fig = band_imbalance_figure(band, thresholds)
    colors = fig.data[0]["marker"]["color"]
    name_to_color = dict(zip(fig.data[0]["x"], colors, strict=True))
    assert name_to_color[breach] != name_to_color[calm]


def test_true_peak_has_two_channel_bars_and_warn_fail_lines() -> None:
    dynamics = DynamicsMetrics(
        true_peak_dbtp_l=-3.0,
        true_peak_dbtp_r=-2.5,
        true_peak_dbtp_max=-2.5,
        psr_db=18.0,
    )
    fig = true_peak_figure(dynamics, TruePeakClipThresholds())
    assert fig.data[0]["x"] == ["L", "R"]
    assert fig.data[0]["y"] == [-3.0, -2.5]
    assert len(fig.layout["shapes"]) == 2


def test_sliding_delta_has_three_stat_bars() -> None:
    sliding = SlidingMetrics(max_lu=6.0, p95_lu=4.0, std_lu=1.0, t_max_sec=12.3)
    fig = sliding_delta_figure(sliding)
    assert fig.data[0]["x"] == ["max", "p95", "std"]
    assert fig.data[0]["y"] == [6.0, 4.0, 1.0]
    assert "12.3s" in fig.layout["title"]["text"]


def test_verdict_donut_seeded_counts() -> None:
    fig = verdict_donut_figure({"OK": 3, "WARN": 1, "FAIL": 2})
    assert fig.data[0]["labels"] == ["OK", "WARN", "FAIL"]
    assert fig.data[0]["values"] == [3, 1, 2]
    assert fig.data[0]["hole"] == 0.55


def test_verdict_donut_empty_defaults_to_zero() -> None:
    fig = verdict_donut_figure()
    assert fig.data[0]["values"] == [0, 0, 0]


def test_delta_scatter_starts_empty() -> None:
    fig = delta_scatter_figure()
    assert fig.data[0]["x"] == []
    assert fig.data[0]["y"] == []
    assert fig.data[0]["mode"] == "markers"


def test_band_imbalance_from_real_scan(balanced_wav: Path) -> None:
    # End-to-end: ensure the figure shape is JSON-serialisable for a
    # real MetricRecord. (Pydantic models hold the band dict.)
    result = scan_one(balanced_wav, Config().with_overrides(workers=1))
    assert result.record.band is not None
    fig = band_imbalance_figure(result.record.band, Config().thresholds.band_bias)
    payload = fig.to_plotly_json()
    assert payload["data"][0]["type"] == "bar"
    assert "shapes" in payload["layout"]
