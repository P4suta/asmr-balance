from __future__ import annotations

from pathlib import Path

from asmr_balance.algebra.semilattice import Verdict
from asmr_balance.config.model import Config
from asmr_balance.scan.pipeline import scan_one
from asmr_balance.web.views.insights import (
    derive_headroom,
    derive_inspect_insights,
    derive_loudness,
    derive_stereo_balance,
    derive_tone,
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
def test_loudness_categorises_into_asmr_or_loud(balanced_wav: Path) -> None:
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
