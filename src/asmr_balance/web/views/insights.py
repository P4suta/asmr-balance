"""Domain → semantic insight projection.

The user-visible value of this tool is *understanding*, not *numbers*. Raw
metrics like ``delta_lu = +12.0`` are domain facts with no meaning to a
producer / listener; this module is the single place that translates them
into:

* a **categorical label** ("極端に左寄り", "ASMR 推奨レンジ内", "クリップ確実")
* a **positional offset** for visual gauges ("46% to the L on a [-100, +100]
  axis", "headroom 65% safe / 35% warn zone")
* a **reference frame** ("目安: ±3 LU 以内 / あなた: +12 LU")
* a **severity** so the UI can color-code

The four bundles (:class:`StereoBalanceInsight`, :class:`LoudnessInsight`,
:class:`HeadroomInsight`, :class:`ToneBalanceInsight`) are composed into
:class:`InspectInsights`. Each builder is pure: it takes the
:class:`MetricRecord` (and nothing else) and returns a frozen dataclass.

Strings are in 日本語. i18n is Phase 4.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

from asmr_balance.algebra.semilattice import Verdict
from asmr_balance.metrics.record import MetricRecord
from asmr_balance.nodes.bandsplit import BANDS


# ----------------------------------------------------------------------
# Data shapes
# ----------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class StereoBalanceInsight:
    """How the stereo image sits — pan / stability / image width."""

    pan_label: str
    pan_severity: Verdict
    pan_offset_pct: float
    """Position on a [-100, +100] scale; negative = R, positive = L."""

    pan_reference: str

    stability_label: str
    stability_severity: Verdict

    image_label: str
    image_severity: Verdict
    image_reference: str


@dataclass(frozen=True, slots=True)
class LoudnessInsight:
    """Loudness profile in user-meaningful categories."""

    target_label: str
    target_severity: Verdict
    integrated_lufs: float
    target_reference: str

    dynamics_label: str
    dynamics_severity: Verdict
    dynamics_reference: str

    psr_label: str
    psr_severity: Verdict
    psr_reference: str


@dataclass(frozen=True, slots=True)
class HeadroomInsight:
    """Clipping-risk dashboard."""

    headroom_db: float
    severity: Verdict
    risk_label: str
    headroom_fill_pct: float
    """0 = touching 0 dBTP (clip), 100 = full headroom (≤ −6 dBTP)."""

    channel_status_label: str
    channel_status_severity: Verdict


@dataclass(frozen=True, slots=True)
class ToneRegion:
    """One of {bass, mid, treble} — collapsed from the 31 third-octave bins."""

    name: str
    imbalance_db: float
    label: str
    severity: Verdict


@dataclass(frozen=True, slots=True)
class ToneBalanceInsight:
    """Bass / mid / treble bias grouped from the 31 1/3-oct measurements."""

    regions: tuple[ToneRegion, ToneRegion, ToneRegion]
    most_imbalanced_label: str | None
    most_imbalanced_severity: Verdict


@dataclass(frozen=True, slots=True)
class InspectInsights:
    """All four dashboards bundled for the inspect template."""

    balance: StereoBalanceInsight | None
    loudness: LoudnessInsight | None
    headroom: HeadroomInsight | None
    tone: ToneBalanceInsight | None


# ----------------------------------------------------------------------
# Stereo balance
# ----------------------------------------------------------------------
def _pan_label(delta_lu: float) -> tuple[str, Verdict]:
    abs_d = abs(delta_lu)
    side = "右" if delta_lu < 0 else "左"
    if abs_d < 1.5:
        return ("中央バランス", Verdict.OK)
    if abs_d < 3:
        return (f"わずかに{side}寄り", Verdict.OK)
    if abs_d < 6:
        return (f"{side}に偏っています", Verdict.WARN)
    return (f"極端に{side}寄り", Verdict.FAIL)


def _stability_label(p95_lu: float, t_max_sec: float) -> tuple[str, Verdict]:
    if not math.isfinite(p95_lu):
        return ("計測不能", Verdict.WARN)
    if p95_lu < 3:
        return ("全体的に安定", Verdict.OK)
    if p95_lu < 6:
        return (f"局所的にゆらぎあり (最大 {t_max_sec:.1f}s 付近)", Verdict.WARN)
    return (f"持続的に大きくゆらぐ (p95 {p95_lu:.1f} LU)", Verdict.FAIL)


def _image_label(pearson: float, ms_ratio_db: float) -> tuple[str, Verdict]:
    if math.isfinite(pearson) and pearson > 0.95:
        return ("ほぼモノラル (Side 成分なし)", Verdict.WARN)
    if math.isfinite(ms_ratio_db) and ms_ratio_db > 12:
        return ("立体感が薄い (Side が痩せている)", Verdict.WARN)
    if math.isfinite(ms_ratio_db) and ms_ratio_db > 6:
        return ("ステレオ感あり", Verdict.OK)
    return ("広いステレオ感", Verdict.OK)


def derive_stereo_balance(record: MetricRecord) -> StereoBalanceInsight | None:
    loud = record.loudness
    sliding = record.sliding
    corr = record.correlation
    if loud is None or sliding is None or corr is None:
        return None

    delta = loud.delta_lu if math.isfinite(loud.delta_lu) else 0.0
    # Linear map: ±20 LU → ±100% (saturated). 0 LU → 0%.
    pan_offset = max(-100.0, min(100.0, delta * 5.0))
    pan_label, pan_severity = _pan_label(delta)

    stability_label, stability_severity = _stability_label(sliding.p95_lu, sliding.t_max_sec)
    image_label, image_severity = _image_label(corr.pearson_r, corr.ms_ratio_db)

    return StereoBalanceInsight(
        pan_label=pan_label,
        pan_severity=pan_severity,
        pan_offset_pct=pan_offset,
        pan_reference=f"目安: ±3 LU 以内 / あなた: {delta:+.1f} LU",
        stability_label=stability_label,
        stability_severity=stability_severity,
        image_label=image_label,
        image_severity=image_severity,
        image_reference=f"Mid/Side 比: {corr.ms_ratio_db:+.1f} dB (目安: 0–6 dB)",
    )


# ----------------------------------------------------------------------
# Loudness
# ----------------------------------------------------------------------
def _loudness_target_label(lufs: float) -> tuple[str, Verdict, str]:
    """Where this file sits vs streaming + ASMR-typical loudness targets."""
    reference = "ASMR 推奨 −23 LUFS / Apple Podcasts −16 / Spotify −14 / ラウドネス戦争 ≥ −10"
    if not math.isfinite(lufs):
        return ("計測不能", Verdict.WARN, reference)
    if lufs < -30:
        return ("非常に静か (静寂レベル)", Verdict.WARN, reference)
    if -30 <= lufs <= -18:
        return ("ASMR 推奨レンジ内", Verdict.OK, reference)
    if -18 < lufs <= -12:
        return ("ポッドキャスト/配信向け (ASMR としては大きめ)", Verdict.WARN, reference)
    return ("大きすぎ (ラウドネス戦争域、聴き疲れの原因)", Verdict.FAIL, reference)


def _dynamics_label(lra_lu: float) -> tuple[str, Verdict, str]:
    reference = "目安: ASMR は 12–18 LU が典型 / 配信音楽は 6–10 LU が多い"
    if not math.isfinite(lra_lu):
        return ("計測不能", Verdict.WARN, reference)
    if lra_lu < 6:
        return ("圧縮されている (抑揚が乏しい)", Verdict.WARN, reference)
    if lra_lu < 12:
        return ("普通の抑揚", Verdict.OK, reference)
    if lra_lu < 20:
        return ("豊かな抑揚 (ASMR らしい)", Verdict.OK, reference)
    return ("極端なダイナミクス (再生環境次第で聴きづらい)", Verdict.WARN, reference)


def _psr_label(psr_db: float) -> tuple[str, Verdict, str]:
    reference = "PSR = peak − loudness。高いほど「静かなのに時々大きい」音"
    if not math.isfinite(psr_db):
        return ("計測不能", Verdict.WARN, reference)
    if psr_db < 12:
        return ("圧縮された音 (音楽/放送的)", Verdict.OK, reference)
    if psr_db < 20:
        return ("会話程度の自然さ", Verdict.OK, reference)
    return ("囁き型 (典型的 ASMR / 静寂と耳元の対比強)", Verdict.OK, reference)


def derive_loudness(record: MetricRecord) -> LoudnessInsight | None:
    loud = record.loudness
    lra = record.lra
    dyn = record.dynamics
    if loud is None or lra is None or dyn is None:
        return None

    target_label, target_severity, target_ref = _loudness_target_label(loud.lufs_i_stereo)
    dyn_label, dyn_severity, dyn_ref = _dynamics_label(lra.lra_lu)
    psr_label, psr_severity, psr_ref = _psr_label(dyn.psr_db)

    return LoudnessInsight(
        target_label=target_label,
        target_severity=target_severity,
        integrated_lufs=loud.lufs_i_stereo,
        target_reference=target_ref,
        dynamics_label=dyn_label,
        dynamics_severity=dyn_severity,
        dynamics_reference=dyn_ref,
        psr_label=psr_label,
        psr_severity=psr_severity,
        psr_reference=psr_ref,
    )


# ----------------------------------------------------------------------
# Headroom / channel status
# ----------------------------------------------------------------------
def _headroom_label(dbtp: float) -> tuple[str, Verdict]:
    if not math.isfinite(dbtp):
        return ("計測不能", Verdict.WARN)
    if dbtp >= 0:
        return ("クリップ確実 (再生機材で歪み)", Verdict.FAIL)
    if dbtp >= -1:
        return ("クリップ警告ゾーン", Verdict.WARN)
    if dbtp >= -3:
        return ("ヘッドルームやや少なめ", Verdict.WARN)
    return ("安全圏", Verdict.OK)


def _channel_status_label(record: MetricRecord) -> tuple[str, Verdict]:
    loud = record.loudness
    if loud is None:
        return ("計測不能", Verdict.WARN)
    bad_l = not math.isfinite(loud.single_channel_lufs_l)
    bad_r = not math.isfinite(loud.single_channel_lufs_r)
    if bad_l and bad_r:
        return ("両チャンネル無音 (致命的)", Verdict.FAIL)
    if bad_l:
        return ("L チャンネル無音", Verdict.FAIL)
    if bad_r:
        return ("R チャンネル無音", Verdict.FAIL)
    return ("両チャンネル稼働", Verdict.OK)


def derive_headroom(record: MetricRecord) -> HeadroomInsight | None:
    dyn = record.dynamics
    if dyn is None:
        return None
    peak = dyn.true_peak_dbtp_max if math.isfinite(dyn.true_peak_dbtp_max) else 0.0
    risk_label, severity = _headroom_label(peak)
    headroom_db = -peak  # how far below 0 dBTP we are
    # Fill gauge: 0 dBTP = 0%, <= -6 dBTP = 100%.
    fill = max(0.0, min(100.0, (headroom_db / 6.0) * 100.0))
    channel_label, channel_severity = _channel_status_label(record)
    return HeadroomInsight(
        headroom_db=headroom_db,
        severity=severity,
        risk_label=risk_label,
        headroom_fill_pct=fill,
        channel_status_label=channel_label,
        channel_status_severity=channel_severity,
    )


# ----------------------------------------------------------------------
# Tone balance — group 31 third-oct bins into bass / mid / treble
# ----------------------------------------------------------------------
_REGION_EDGES = (250.0, 4000.0)  # bass < 250 ≤ mid < 4000 ≤ treble


def _region_of(center_hz: float) -> str:
    if center_hz < _REGION_EDGES[0]:
        return "bass"
    if center_hz < _REGION_EDGES[1]:
        return "mid"
    return "treble"


_REGION_LABELS = {"bass": "低音", "mid": "中音", "treble": "高音"}


def _tone_severity(abs_db: float) -> Verdict:
    if abs_db < 3:
        return Verdict.OK
    if abs_db < 6:
        return Verdict.WARN
    return Verdict.FAIL


def _tone_label(name: str, value_db: float, severity: Verdict) -> str:
    if severity is Verdict.OK:
        return f"{name}バランス OK"
    side = "L" if value_db > 0 else "R"
    return f"{name} {side} 偏り ({abs(value_db):.1f} dB)"


def derive_tone(record: MetricRecord) -> ToneBalanceInsight | None:
    band = record.band
    if band is None:
        return None
    # Bucket every band into bass / mid / treble using the band specs' centers.
    buckets: dict[str, list[float]] = {"bass": [], "mid": [], "treble": []}
    for spec in BANDS:
        value = band.third_octave.get(spec.name)
        if value is None or not math.isfinite(value):
            continue
        buckets[_region_of(spec.center_hz)].append(value)

    # Explicit 3-tuple (rather than ``tuple(..for..)`` generator) so the type
    # is ``tuple[ToneRegion, ToneRegion, ToneRegion]`` and matches the DTO.
    regions = (
        _build_region("bass", buckets["bass"]),
        _build_region("mid", buckets["mid"]),
        _build_region("treble", buckets["treble"]),
    )

    # Find the single most imbalanced 1/3-oct band for the marquee callout.
    worst: tuple[str, float, float] | None = None  # name, value, abs_value
    for spec in BANDS:
        value = band.third_octave.get(spec.name)
        if value is None or not math.isfinite(value):
            continue
        abs_v = abs(value)
        if worst is None or abs_v > worst[2]:
            worst = (spec.name, value, abs_v)
    most_label: str | None
    most_severity: Verdict
    if worst is None or worst[2] < 3:
        most_label = None
        most_severity = Verdict.OK
    else:
        side = "L" if worst[1] > 0 else "R"
        most_label = f"{worst[0]} で {side} が {worst[2]:.1f} dB 強い"
        most_severity = _tone_severity(worst[2])

    return ToneBalanceInsight(
        regions=regions,
        most_imbalanced_label=most_label,
        most_imbalanced_severity=most_severity,
    )


def _build_region(name: str, values: list[float]) -> ToneRegion:
    if not values:
        return ToneRegion(
            name=_REGION_LABELS[name],
            imbalance_db=0.0,
            label=f"{_REGION_LABELS[name]} 計測不能",
            severity=Verdict.WARN,
        )
    # Energy-weighted mean is more representative than arithmetic mean for
    # this band — but for the user-facing label, the worst-band magnitude
    # within the region is the most diagnostic. ``cast`` because ``max(...,
    # key=abs)`` infers a wider union than ``float`` when ``key`` is set.
    worst = cast("float", max(values, key=abs))
    severity = _tone_severity(abs(worst))
    label = _tone_label(_REGION_LABELS[name], worst, severity)
    return ToneRegion(
        name=_REGION_LABELS[name],
        imbalance_db=worst,
        label=label,
        severity=severity,
    )


# ----------------------------------------------------------------------
# Public aggregator
# ----------------------------------------------------------------------
def derive_inspect_insights(record: MetricRecord) -> InspectInsights:
    """All four insight bundles for the inspect template (None when SKIPPED)."""
    return InspectInsights(
        balance=derive_stereo_balance(record),
        loudness=derive_loudness(record),
        headroom=derive_headroom(record),
        tone=derive_tone(record),
    )
