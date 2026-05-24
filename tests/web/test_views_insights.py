from __future__ import annotations

import math
from pathlib import Path

import pytest

from asmr_balance.algebra.semilattice import Verdict
from asmr_balance.config.model import Config
from asmr_balance.metrics.record import FileMeta, MetricRecord, ScanStatus
from asmr_balance.metrics.subtrees import (
    BandImbalanceMetrics,
    DynamicsMetrics,
    LoudnessMetrics,
    LRAMetrics,
    SlidingMetrics,
    StereoCorrelationMetrics,
)
from asmr_balance.nodes.bandsplit import BANDS
from asmr_balance.scan.pipeline import scan_one
from asmr_balance.web.views.insights import (
    _build_region,
    _channel_status_label,
    _dynamics_label,
    _headroom_label,
    _image_label,
    _loudness_target_label,
    _pan_label,
    _psr_label,
    _region_of,
    _stability_label,
    _tone_severity,
    derive_headroom,
    derive_inspect_insights,
    derive_loudness,
    derive_stereo_balance,
    derive_tone,
)


def _loudness(**kw) -> LoudnessMetrics:
    defaults = {
        "lufs_i_stereo": -23.0,
        "single_channel_lufs_l": -23.0,
        "single_channel_lufs_r": -23.0,
        "single_channel_lufs_ungated_l": -23.0,
        "single_channel_lufs_ungated_r": -23.0,
        "delta_lu": 0.0,
        "delta_lu_ungated": 0.0,
    }
    defaults.update(kw)
    return LoudnessMetrics(**defaults)


def _record(
    *,
    loudness: LoudnessMetrics | None = None,
    lra: LRAMetrics | None = None,
    correlation: StereoCorrelationMetrics | None = None,
    band: BandImbalanceMetrics | None = None,
    sliding: SlidingMetrics | None = None,
    dynamics: DynamicsMetrics | None = None,
) -> MetricRecord:
    meta = FileMeta(
        file_path=Path("/tmp/x.wav"),
        sample_rate=48000,
        duration_sec=1.0,
        channel_layout="stereo",
    )
    return MetricRecord(
        meta=meta,
        status=ScanStatus.ANALYZED,
        loudness=loudness,
        lra=lra,
        correlation=correlation,
        band=band,
        sliding=sliding,
        dynamics=dynamics,
    )


# ---------------------------------------------------------------------------
# Stereo balance — pan classification + reference
# ---------------------------------------------------------------------------
def test_balanced_wav_is_centered(balanced_wav: Path) -> None:
    record = scan_one(balanced_wav, Config().with_overrides(workers=1)).record
    insight = derive_stereo_balance(record)
    assert insight is not None
    assert insight.pan_severity is Verdict.OK
    assert "中央" in insight.pan_label or "わずか" in insight.pan_label
    assert abs(insight.pan_offset_pct) < 30


def test_panned_wav_shows_pan_warning(panned_wav: Path) -> None:
    record = scan_one(panned_wav, Config().with_overrides(workers=1)).record
    insight = derive_stereo_balance(record)
    assert insight is not None
    assert insight.pan_severity in {Verdict.WARN, Verdict.FAIL}
    # 12 dB pan → offset clamps near ±100.
    assert abs(insight.pan_offset_pct) > 40
    assert "左" in insight.pan_label or "右" in insight.pan_label


def test_stereo_balance_returns_none_when_subtree_missing(mono_wav: Path) -> None:
    record = scan_one(mono_wav, Config().with_overrides(workers=1)).record
    # mono → SKIPPED → loudness/sliding/correlation all None
    assert derive_stereo_balance(record) is None


# ---------------------------------------------------------------------------
# Loudness — target / dynamics / PSR categorical labels
# ---------------------------------------------------------------------------
def test_loudness_categorizes_into_asmr_or_loud(balanced_wav: Path) -> None:
    record = scan_one(balanced_wav, Config().with_overrides(workers=1)).record
    insight = derive_loudness(record)
    assert insight is not None
    # Synthetic sine at 0.5 amplitude is loud → outside ASMR target range,
    # so we expect a non-OK target severity OR an "OK" if the integrated
    # LUFS happens to fall into the ASMR band. Either way, the label is
    # populated and the reference text mentions known platforms.
    assert insight.target_label
    assert "ASMR" in insight.target_reference
    assert "Podcast" in insight.target_reference or "Podcasts" in insight.target_reference
    assert insight.dynamics_label
    assert insight.psr_label


def test_loudness_returns_none_for_skipped(mono_wav: Path) -> None:
    record = scan_one(mono_wav, Config().with_overrides(workers=1)).record
    assert derive_loudness(record) is None


# ---------------------------------------------------------------------------
# Headroom — clip risk + channel status
# ---------------------------------------------------------------------------
def test_headroom_for_balanced_is_safe(balanced_wav: Path) -> None:
    record = scan_one(balanced_wav, Config().with_overrides(workers=1)).record
    insight = derive_headroom(record)
    assert insight is not None
    # Synthetic sines have predictable, well below 0 dBTP peaks → safe.
    assert insight.severity is Verdict.OK
    assert "安全" in insight.risk_label
    assert 0 <= insight.headroom_fill_pct <= 100
    assert insight.channel_status_severity is Verdict.OK
    assert "両チャンネル" in insight.channel_status_label


def test_headroom_returns_none_for_skipped(mono_wav: Path) -> None:
    record = scan_one(mono_wav, Config().with_overrides(workers=1)).record
    assert derive_headroom(record) is None


# ---------------------------------------------------------------------------
# Tone — bass/mid/treble buckets
# ---------------------------------------------------------------------------
def test_tone_groups_into_three_regions(balanced_wav: Path) -> None:
    record = scan_one(balanced_wav, Config().with_overrides(workers=1)).record
    insight = derive_tone(record)
    assert insight is not None
    names = [r.name for r in insight.regions]
    assert names == ["低音", "中音", "高音"]
    for region in insight.regions:
        assert region.label
        assert region.severity in {Verdict.OK, Verdict.WARN, Verdict.FAIL}


def test_tone_callout_for_extreme_imbalance(panned_wav: Path) -> None:
    record = scan_one(panned_wav, Config().with_overrides(workers=1)).record
    insight = derive_tone(record)
    assert insight is not None
    # 12 dB pan = all bands imbalanced → most_imbalanced_label populated.
    assert insight.most_imbalanced_label is not None
    assert insight.most_imbalanced_severity in {Verdict.WARN, Verdict.FAIL}


def test_tone_returns_none_for_skipped(mono_wav: Path) -> None:
    record = scan_one(mono_wav, Config().with_overrides(workers=1)).record
    assert derive_tone(record) is None


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------
def test_derive_inspect_insights_packs_all_four(balanced_wav: Path) -> None:
    record = scan_one(balanced_wav, Config().with_overrides(workers=1)).record
    bundle = derive_inspect_insights(record)
    assert bundle.balance is not None
    assert bundle.loudness is not None
    assert bundle.headroom is not None
    assert bundle.tone is not None


def test_derive_inspect_insights_all_none_when_skipped(mono_wav: Path) -> None:
    record = scan_one(mono_wav, Config().with_overrides(workers=1)).record
    bundle = derive_inspect_insights(record)
    assert bundle.balance is None
    assert bundle.loudness is None
    assert bundle.headroom is None
    assert bundle.tone is None


# ---------------------------------------------------------------------------
# Private categorical helpers — every branch covered (branch-coverage gate)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("delta", "expected_severity"),
    [
        (0.5, Verdict.OK),  # 中央バランス
        (2.0, Verdict.OK),  # わずか寄り
        (-2.0, Verdict.OK),  # わずか右寄り (negative branch of `side`)
        (4.0, Verdict.WARN),  # 偏っています
        (10.0, Verdict.FAIL),  # 極端
    ],
)
def test_pan_label_covers_every_bucket(delta: float, expected_severity: Verdict) -> None:
    _, severity = _pan_label(delta)
    assert severity is expected_severity


@pytest.mark.parametrize(
    ("p95", "t_max", "expected_severity"),
    [
        (float("nan"), 0.0, Verdict.WARN),  # 計測不能
        (1.0, 0.0, Verdict.OK),
        (4.0, 12.3, Verdict.WARN),
        (8.0, 5.0, Verdict.FAIL),
    ],
)
def test_stability_label_covers_every_bucket(
    p95: float, t_max: float, expected_severity: Verdict
) -> None:
    _, severity = _stability_label(p95, t_max)
    assert severity is expected_severity


@pytest.mark.parametrize(
    ("pearson", "ms_db", "expected_severity"),
    [
        (0.99, 5.0, Verdict.WARN),  # pseudo-mono branch
        (0.5, 15.0, Verdict.WARN),  # narrow side branch
        (0.5, 8.0, Verdict.OK),  # stereo branch
        (0.5, 3.0, Verdict.OK),  # wide branch
    ],
)
def test_image_label_covers_every_bucket(
    pearson: float, ms_db: float, expected_severity: Verdict
) -> None:
    _, severity = _image_label(pearson, ms_db)
    assert severity is expected_severity


@pytest.mark.parametrize(
    ("lufs", "expected_severity"),
    [
        (float("nan"), Verdict.WARN),
        (-40.0, Verdict.WARN),  # very quiet
        (-23.0, Verdict.OK),  # ASMR range
        (-15.0, Verdict.WARN),  # podcast / louder
        (-8.0, Verdict.FAIL),  # loudness war
    ],
)
def test_loudness_target_label_buckets(lufs: float, expected_severity: Verdict) -> None:
    _, severity, _ = _loudness_target_label(lufs)
    assert severity is expected_severity


@pytest.mark.parametrize(
    ("lra", "expected_severity"),
    [
        (float("nan"), Verdict.WARN),
        (3.0, Verdict.WARN),  # compressed
        (8.0, Verdict.OK),  # normal
        (15.0, Verdict.OK),  # ASMR rich
        (25.0, Verdict.WARN),  # extreme
    ],
)
def test_dynamics_label_buckets(lra: float, expected_severity: Verdict) -> None:
    _, severity, _ = _dynamics_label(lra)
    assert severity is expected_severity


@pytest.mark.parametrize(
    ("psr", "expected_label_token"),
    [
        (float("nan"), "計測不能"),
        (8.0, "圧縮"),
        (16.0, "会話"),
        (24.0, "囁き"),
    ],
)
def test_psr_label_buckets(psr: float, expected_label_token: str) -> None:
    label, _, _ = _psr_label(psr)
    assert expected_label_token in label


@pytest.mark.parametrize(
    ("dbtp", "expected_severity"),
    [
        (float("nan"), Verdict.WARN),
        (0.5, Verdict.FAIL),  # clip
        (-0.5, Verdict.WARN),  # warn zone
        (-2.0, Verdict.WARN),  # marginal
        (-6.0, Verdict.OK),  # safe
    ],
)
def test_headroom_label_buckets(dbtp: float, expected_severity: Verdict) -> None:
    _, severity = _headroom_label(dbtp)
    assert severity is expected_severity


# ---------------------------------------------------------------------------
# _channel_status_label — full Cartesian over (L finite, R finite)
# ---------------------------------------------------------------------------
def test_channel_status_missing_loudness_returns_warn() -> None:
    record = _record()
    _, severity = _channel_status_label(record)
    assert severity is Verdict.WARN


def test_channel_status_both_active() -> None:
    record = _record(loudness=_loudness())
    label, severity = _channel_status_label(record)
    assert severity is Verdict.OK
    assert "両" in label


def test_channel_status_l_silent() -> None:
    record = _record(loudness=_loudness(single_channel_lufs_l=float("-inf")))
    label, severity = _channel_status_label(record)
    assert severity is Verdict.FAIL
    assert "L" in label


def test_channel_status_r_silent() -> None:
    record = _record(loudness=_loudness(single_channel_lufs_r=float("-inf")))
    label, severity = _channel_status_label(record)
    assert severity is Verdict.FAIL
    assert "R" in label


def test_channel_status_both_silent() -> None:
    record = _record(
        loudness=_loudness(
            single_channel_lufs_l=float("-inf"),
            single_channel_lufs_r=float("-inf"),
        )
    )
    label, severity = _channel_status_label(record)
    assert severity is Verdict.FAIL
    assert "両" in label


# ---------------------------------------------------------------------------
# Region helpers — empty bucket, NaN entries, edges
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("center_hz", "expected"),
    [
        (50.0, "bass"),  # below low edge
        (200.0, "bass"),  # still bass (< 250)
        (250.0, "mid"),  # at edge → mid
        (1000.0, "mid"),
        (3999.0, "mid"),
        (4000.0, "treble"),
        (10000.0, "treble"),
    ],
)
def test_region_of(center_hz: float, expected: str) -> None:
    assert _region_of(center_hz) == expected


@pytest.mark.parametrize(
    ("abs_db", "expected"),
    [(0.0, Verdict.OK), (3.0, Verdict.WARN), (6.0, Verdict.FAIL)],
)
def test_tone_severity(abs_db: float, expected: Verdict) -> None:
    assert _tone_severity(abs_db) is expected


def test_build_region_handles_empty_bucket() -> None:
    region = _build_region("bass", [])
    assert region.severity is Verdict.WARN
    assert "計測不能" in region.label


def test_build_region_picks_worst_band() -> None:
    region = _build_region("treble", [1.0, -5.0, 2.0])
    # max(by abs) is -5.0 → R bias
    assert "R" in region.label
    assert region.severity is Verdict.WARN


# ---------------------------------------------------------------------------
# Tone derive — band dict missing entries (None / NaN) still safe
# ---------------------------------------------------------------------------
def test_derive_tone_handles_missing_band_entries() -> None:
    third = {b.name: 0.0 for b in BANDS}
    third[BANDS[0].name] = float("nan")  # NaN should be skipped
    band = BandImbalanceMetrics(low=0.0, low_mid=0.0, high_mid=0.0, high=0.0, third_octave=third)
    insight = derive_tone(_record(band=band))
    assert insight is not None
    assert insight.most_imbalanced_label is None


def test_derive_tone_all_nan_yields_no_callout() -> None:
    third = {b.name: float("nan") for b in BANDS}
    band = BandImbalanceMetrics(low=0.0, low_mid=0.0, high_mid=0.0, high=0.0, third_octave=third)
    insight = derive_tone(_record(band=band))
    assert insight is not None
    assert insight.most_imbalanced_label is None
    # Each region falls back to "計測不能" because every value was filtered out.
    assert all("計測不能" in r.label for r in insight.regions)


# ---------------------------------------------------------------------------
# Stereo balance — non-finite delta_lu defaults to 0
# ---------------------------------------------------------------------------
def test_stereo_balance_non_finite_delta_normalizes_to_zero() -> None:
    loud = _loudness(delta_lu=float("nan"))
    sliding = SlidingMetrics(max_lu=0.0, p95_lu=0.0, std_lu=0.0, t_max_sec=0.0)
    corr = StereoCorrelationMetrics(pearson_r=0.5, ms_ratio_db=4.0)
    insight = derive_stereo_balance(_record(loudness=loud, sliding=sliding, correlation=corr))
    assert insight is not None
    assert insight.pan_offset_pct == 0.0


# ---------------------------------------------------------------------------
# Headroom — non-finite peak falls back to 0 (clip)
# ---------------------------------------------------------------------------
def test_headroom_non_finite_peak_falls_back_to_zero() -> None:
    dyn = DynamicsMetrics(
        true_peak_dbtp_l=0.0,
        true_peak_dbtp_r=0.0,
        true_peak_dbtp_max=float("nan"),
        psr_db=20.0,
    )
    insight = derive_headroom(_record(dynamics=dyn))
    assert insight is not None
    # NaN → 0 → fill 0 (full danger).
    assert insight.headroom_fill_pct == 0.0
    assert insight.severity is Verdict.FAIL


# ---------------------------------------------------------------------------
# Partial records — one None subtree should short-circuit derive_*
# ---------------------------------------------------------------------------
def test_stereo_balance_missing_sliding_returns_none() -> None:
    loud = _loudness()
    corr = StereoCorrelationMetrics(pearson_r=0.5, ms_ratio_db=4.0)
    assert derive_stereo_balance(_record(loudness=loud, correlation=corr)) is None


def test_loudness_missing_lra_returns_none() -> None:
    loud = _loudness()
    dyn = DynamicsMetrics(
        true_peak_dbtp_l=-3.0,
        true_peak_dbtp_r=-3.0,
        true_peak_dbtp_max=-3.0,
        psr_db=20.0,
    )
    assert derive_loudness(_record(loudness=loud, dynamics=dyn)) is None


def test_loudness_with_full_subtrees_returns_insight() -> None:
    loud = _loudness()
    lra = LRAMetrics(lra_lu=15.0, max_short_term_lufs=-20.0)
    dyn = DynamicsMetrics(
        true_peak_dbtp_l=-3.0, true_peak_dbtp_r=-3.0, true_peak_dbtp_max=-3.0, psr_db=20.0
    )
    insight = derive_loudness(_record(loudness=loud, lra=lra, dynamics=dyn))
    assert insight is not None
    assert math.isfinite(insight.integrated_lufs)
    assert insight.target_label  # non-empty


def test_headroom_with_real_dynamics() -> None:
    dyn = DynamicsMetrics(
        true_peak_dbtp_l=-3.0, true_peak_dbtp_r=-3.0, true_peak_dbtp_max=-3.0, psr_db=20.0
    )
    insight = derive_headroom(_record(dynamics=dyn))
    assert insight is not None
    assert insight.severity is Verdict.WARN  # -3 dBTP falls into "marginal" bucket
