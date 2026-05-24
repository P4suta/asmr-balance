"""Diagnosis view — turn rule firings into user-facing narrative.

The Web UI's value proposition is *interpretation*, not just data display.
Raw metrics (``|ΔLU|=12.00 ≥ 6.0``) are a domain fact; this module is the
sole place that translates each rule firing into:

* a **title** — what the issue *is*, in one sentence
* an **explanation** — why it matters for ASMR production / listening
* a **recommendation** — what to do about it

Aggregated into a :class:`Diagnosis` for the inspect partial, the result
puts the human-readable headline at the top and demotes raw numbers to a
disclosure section. The interpretation is keyed off the canonical
``Flag.code`` so adding a rule means adding one row here.

Strings are in 日本語 (the project's primary user language). i18n is a
Phase 4 concern.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from asmr_balance.algebra.semilattice import Verdict
from asmr_balance.metrics.record import MetricRecord, ScanStatus
from asmr_balance.rules.algebra import Flag
from asmr_balance.scan.pipeline import FileResult


# ----------------------------------------------------------------------
# Data shapes
# ----------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Finding:
    """One user-facing issue derived from a single :class:`Flag`."""

    title: str
    severity: Verdict
    explanation: str
    recommendation: str
    technical_ref: str


@dataclass(frozen=True, slots=True)
class Diagnosis:
    """The narrative summary the inspect UI renders before the raw data."""

    verdict: Verdict
    headline: str
    summary: str
    findings: tuple[Finding, ...]
    actions: tuple[str, ...]
    is_analyzable: bool


# ----------------------------------------------------------------------
# Per-flag interpretation
# ----------------------------------------------------------------------
def _fmt_lu(value: float) -> str:
    if not math.isfinite(value):
        return "—"
    return f"{value:+.2f} LU"


def _build_lr_balance(flag: Flag, record: MetricRecord) -> Finding:
    loud = record.loudness
    delta = loud.delta_lu if loud is not None else float("nan")
    abs_delta = abs(delta) if math.isfinite(delta) else float("nan")
    direction = "左 (L) が大きい" if delta > 0 else "右 (R) が大きい"
    return Finding(
        title=f"左右の平均音量が偏っています ({direction})",
        severity=flag.severity,
        explanation=(
            f"ファイル全体の平均で L − R が {_fmt_lu(delta)} 偏っています。"
            "通常のステレオミックスは ±3 LU 程度に収まるのが目安で、"
            f"今回はその {abs_delta:.1f} LU と大きく外れています。"
            "片耳だけが大きい/小さい違和感がリスナーにそのまま伝わります。"
        ),
        recommendation=(
            "DAW のパン/ゲインを見直すか、収録時のマイク位置 (片側にだけ近い等) と"
            "ケーブル/インターフェイスの両チャンネルレベルを確認してください。"
        ),
        technical_ref=f"{flag.code} · {flag.message}",
    )


def _build_local_bias(flag: Flag, record: MetricRecord) -> Finding:
    sliding = record.sliding
    p95 = sliding.p95_lu if sliding is not None else float("nan")
    t_max = sliding.t_max_sec if sliding is not None else float("nan")
    return Finding(
        title="一部の区間で L/R が偏り続けています",
        severity=flag.severity,
        explanation=(
            "全体平均では均衡でも、1 秒ウィンドウで見たときに局所的に持続的な"
            f"偏りが出ています (p95 ΔLU = {_fmt_lu(p95)})。"
            "ASMR では「囁きが片耳に寄ったまま長い」「タッピング音源で耳元位置が偏る」"
            "といった現象として聞こえます。"
        ),
        recommendation=(
            f"最大偏差は {t_max:.1f}s 付近です。その周辺の素材を中心にパン/位置"
            "オートメーション、もしくは ASMR モチーフ間の左右配置を確認してください。"
        ),
        technical_ref=f"{flag.code} · {flag.message}",
    )


def _build_pseudo_mono(flag: Flag, record: MetricRecord) -> Finding:
    corr = record.correlation
    pearson = corr.pearson_r if corr is not None else float("nan")
    return Finding(
        title="ステレオなのに L=R に近い (擬似モノラル)",
        severity=flag.severity,
        explanation=(
            f"左右波形の相関係数が {pearson:.3f} と非常に高く、"
            "ファイルはステレオ chunk ですが聴感上はほぼモノラルです。"
            "意図的な dual-mono であれば問題ありませんが、"
            "binaural / 立体 ASMR を意図していた場合は録音/書き出し設定のミスが疑われます。"
        ),
        recommendation=(
            "Dual-mono が意図通りなら無視可。"
            "ステレオを期待していた場合は、収録時のマイクペア接続、"
            "ステレオバスルーティング、書き出し時の channel layout を確認してください。"
        ),
        technical_ref=f"{flag.code} · {flag.message}",
    )


def _build_phase_inv(flag: Flag, _record: MetricRecord) -> Finding:
    return Finding(
        title="低域 (<300 Hz) で位相反転が疑われます",
        severity=flag.severity,
        explanation=(
            "低域帯の L/R 位相相関が負の値です。"
            "スピーカー再生では低域がキャンセルされ「スカスカに」聞こえ、"
            "ヘッドホン再生では音像が頭の外側にゆらぐ違和感が生じます。"
        ),
        recommendation=(
            "ケーブルの極性 (+/−) 逆挿し、"
            "DAW の Phase Invert スイッチ、"
            "L/R 入力の取り違えを順に確認してください。"
        ),
        technical_ref=f"{flag.code} · {flag.message}",
    )


def _build_mid_side_narrow(flag: Flag, _record: MetricRecord) -> Finding:
    return Finding(
        title="ステレオ感が乏しい (Side 成分が痩せています)",
        severity=flag.severity,
        explanation=(
            "Mid (中央) に対して Side (差分) のエネルギーが小さく、"
            "技術的にはステレオでも立体感の薄い音になっています。"
            "binaural / dummy head ASMR では特に問題になりやすい指標です。"
        ),
        recommendation=(
            "マイク間距離・配置、ステレオエフェクト/M-S プロセッサの設定、"
            "もしくは収録環境の反射特性を見直してください。"
        ),
        technical_ref=f"{flag.code} · {flag.message}",
    )


_BAND_LABEL: dict[str, str] = {
    "BAND_BIAS_LOW": "低域 (20–125 Hz)",
    "BAND_BIAS_LOW_MID": "中低域 (160–1.25 kHz)",
    "BAND_BIAS_HIGH_MID": "中高域 (1.6–6.3 kHz)",
    "BAND_BIAS_HIGH": "高域 (8 kHz–20 kHz)",
}


def _build_band_bias(flag: Flag, _record: MetricRecord) -> Finding:
    band_name = _BAND_LABEL.get(flag.code, "未知の帯域")
    return Finding(
        title=f"{band_name} で L/R 偏りが出ています",
        severity=flag.severity,
        explanation=(
            f"{band_name} で左右のエネルギーが大きく異なります。"
            "EQ の片チャンネルだけかけ忘れ、片側のマイク特性の偏り、"
            "あるいは部屋の音響特性が片側だけに乗っている可能性があります。"
        ),
        recommendation=(
            f"{band_name} を中心に EQ や個別チャンネル処理を見直すか、"
            "1/3-octave チャートで他の帯域との比較を確認してください (詳細データ内)。"
        ),
        technical_ref=f"{flag.code} · {flag.message}",
    )


def _build_true_peak(flag: Flag, record: MetricRecord) -> Finding:
    dyn = record.dynamics
    peak = dyn.true_peak_dbtp_max if dyn is not None else float("nan")
    clipping = "の発生が確実" if flag.severity is Verdict.FAIL else "の可能性"
    return Finding(
        title="True Peak が上限を超えています (clip 危険)",
        severity=flag.severity,
        explanation=(
            f"BS.1770-5 Annex 2 で計測した true peak が {peak:+.2f} dBTP に達しています。"
            f"民生 DAC でのインターサンプルクリップ{clipping}があり、"
            "再生環境次第で歪み/プチノイズとして聞こえます。"
        ),
        recommendation=(
            "マスター段で True Peak Limiter (target ≤ −1 dBTP) を入れるか、"
            "全体ゲインを下げてヘッドルームを確保してください。"
        ),
        technical_ref=f"{flag.code} · {flag.message}",
    )


def _build_gate_reject(flag: Flag, _record: MetricRecord) -> Finding:
    return Finding(
        title="片側または両方のチャンネルが無音レベルです",
        severity=flag.severity,
        explanation=(
            "BS.1770 の絶対ゲート (−70 LUFS) で除外されるほどに、"
            "L または R チャンネルが小さいまたは無音です。"
            "録音漏れ、ミュート、ケーブル断、入力レベルの設定ミスが疑われます。"
        ),
        recommendation=(
            "該当チャンネルの収録レベル、ミュート/ソロ状態、"
            "ケーブル接続、オーディオインターフェイスのゲイン設定を確認してください。"
        ),
        technical_ref=f"{flag.code} · {flag.message}",
    )


# Map flag-code prefix → builder (covers both _WARN and _FAIL suffixes).
_BUILDERS = {
    "LR_BALANCE_WARN": _build_lr_balance,
    "LR_BALANCE_FAIL": _build_lr_balance,
    "LOCAL_BIAS_WARN": _build_local_bias,
    "LOCAL_BIAS_FAIL": _build_local_bias,
    "PSEUDO_MONO": _build_pseudo_mono,
    "PHASE_INV_WARN": _build_phase_inv,
    "MID_SIDE_NARROW": _build_mid_side_narrow,
    "BAND_BIAS_LOW": _build_band_bias,
    "BAND_BIAS_LOW_MID": _build_band_bias,
    "BAND_BIAS_HIGH_MID": _build_band_bias,
    "BAND_BIAS_HIGH": _build_band_bias,
    "TRUE_PEAK_WARN": _build_true_peak,
    "TRUE_PEAK_FAIL": _build_true_peak,
    "GATE_REJECT_ALL": _build_gate_reject,
}


def _build_finding(flag: Flag, record: MetricRecord) -> Finding:
    builder = _BUILDERS.get(flag.code, _build_generic)
    return builder(flag, record)


def _build_generic(flag: Flag, _record: MetricRecord) -> Finding:
    """Fallback for flags without an explicit interpreter — keeps the UI honest."""
    return Finding(
        title=f"検査ルール {flag.code} が fired しました",
        severity=flag.severity,
        explanation=(
            f"このルールへの平語の解説はまだ用意されていません。技術的な詳細: {flag.message}"
        ),
        recommendation="詳細データのフラグ一覧と raw metric を参照してください。",
        technical_ref=f"{flag.code} · {flag.message}",
    )


# ----------------------------------------------------------------------
# Headline / summary builders
# ----------------------------------------------------------------------
_HEADLINE_PREFIX = {
    Verdict.OK: "✅ 問題なし",
    Verdict.WARN: "⚠ 注意あり",
    Verdict.FAIL: "✗ 要修正",
}


def _build_headline(verdict: Verdict, findings: tuple[Finding, ...]) -> str:
    prefix = _HEADLINE_PREFIX[verdict]
    if not findings:
        return f"{prefix} — 主要な検査項目を通過しました"
    # Surface the title of the most severe finding (first in iteration order is fine
    # because Verdict comparisons sort by severity already).
    top = max(findings, key=lambda f: f.severity.value)
    return f"{prefix} — {top.title}"


def _build_summary(verdict: Verdict, findings: tuple[Finding, ...]) -> str:
    fail_count = sum(1 for f in findings if f.severity is Verdict.FAIL)
    warn_count = sum(1 for f in findings if f.severity is Verdict.WARN)
    if verdict is Verdict.OK:
        return (
            "ステレオ音場 / ラウドネス / 帯域バランス / true peak のいずれも"
            "規定の閾値内に収まりました。配信向けに大きな修正点はありません。"
        )
    if verdict is Verdict.WARN:
        return (
            f"検査で {warn_count} 件の注意点が見つかりました。"
            "致命的な問題ではありませんが、配信前に下記を一度確認することを推奨します。"
        )
    return (
        f"検査で重大な問題が {fail_count} 件 + 注意点が {warn_count} 件見つかりました。"
        "配信前に下記の項目を修正してください。リスナー体験に直接影響するレベルです。"
    )


def _dedup_actions(findings: Iterable[Finding]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for finding in findings:
        if finding.recommendation in seen:
            continue
        seen.add(finding.recommendation)
        out.append(finding.recommendation)
    return tuple(out)


# ----------------------------------------------------------------------
# Unanalyzable (SKIPPED / ERRORED) — the use case still wants to render
# something coherent rather than blowing up the template
# ----------------------------------------------------------------------
def _build_unanalyzable_diagnosis(record: MetricRecord) -> Diagnosis:
    reason = record.skip_reason or "詳細不明"
    if record.status is ScanStatus.SKIPPED:
        headline = "ℹ 解析対象外"
        summary = (
            f"このファイルは BS.1770-5 ベースの L/R 検査の対象になりません ({reason})。"
            "モノラル素材や 5.1ch などのマルチチャンネル素材は仕様上スキップされます。"
        )
    else:  # ERRORED — should be rare here because the use case usually raises
        headline = "✗ 解析失敗"
        summary = f"ファイルのデコードに失敗しました ({reason})。"
    return Diagnosis(
        verdict=Verdict.OK,
        headline=headline,
        summary=summary,
        findings=(),
        actions=(),
        is_analyzable=False,
    )


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------
def diagnose(result: FileResult) -> Diagnosis:
    """Project a :class:`FileResult` into the narrative :class:`Diagnosis`."""
    record = result.record
    if record.status is not ScanStatus.ANALYZED:
        return _build_unanalyzable_diagnosis(record)
    findings = tuple(_build_finding(flag, record) for flag in result.flags)
    return Diagnosis(
        verdict=result.verdict,
        headline=_build_headline(result.verdict, findings),
        summary=_build_summary(result.verdict, findings),
        findings=findings,
        actions=_dedup_actions(findings),
        is_analyzable=True,
    )
