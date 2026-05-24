"""Diagnosis view — turn rule firings into listener-facing narrative.

The Web UI's audience is the **listener** (the person about to watch /
listen to an ASMR file), not the producer who made it. Every finding is
phrased in terms the listener can act on:

* a **title** — what they will experience while listening
* an **explanation** — why this matters for the viewing experience
* a **recommendation** — equipment / volume / posture advice (NOT mix
  advice — the listener can't re-record the file)

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
    """One listener-facing issue derived from a single :class:`Flag`."""

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
# Per-flag interpretation (listener perspective)
# ----------------------------------------------------------------------
def _fmt_lu(value: float) -> str:
    if not math.isfinite(value):
        return "—"
    return f"{value:+.2f} LU"


def _build_lr_balance(flag: Flag, record: MetricRecord) -> Finding:
    loud = record.loudness
    delta = loud.delta_lu if loud is not None else float("nan")
    abs_delta = abs(delta) if math.isfinite(delta) else float("nan")
    louder, quieter = ("左", "右") if delta > 0 else ("右", "左")
    return Finding(
        title=f"{louder}耳の音が{quieter}耳より大きく聞こえます",
        severity=flag.severity,
        explanation=(
            f"録音そのものに左右の音量差 {_fmt_lu(delta)} があります "
            f"(目安: ±3 LU 以内)。実測 {abs_delta:.1f} LU はリスナー側で"
            "「片耳だけうるさい / 小さい」とはっきり違和感を感じるレベルです。"
            "再生機材の問題ではなく音源側の特性なので、"
            "イヤホンの左右を入れ替えても改善しません。"
        ),
        recommendation=(
            "違和感が強ければ、片イヤホンに切り替えるか別の音源を試してみてください。"
            "意図的な定位演出の可能性もあります (例: 右側からの囁き)。"
        ),
        technical_ref=f"{flag.code} · {flag.message}",
    )


def _build_local_bias(flag: Flag, record: MetricRecord) -> Finding:
    sliding = record.sliding
    p95 = sliding.p95_lu if sliding is not None else float("nan")
    t_max = sliding.t_max_sec if sliding is not None else float("nan")
    return Finding(
        title="特定の場面で音が片耳に強く偏る瞬間があります",
        severity=flag.severity,
        explanation=(
            f"全体平均は均衡でも、{t_max:.1f}s 付近で音像が大きく片側へ寄ります "
            f"(局所最大 ΔLU = {_fmt_lu(p95)})。"
            "ASMR では「囁きが急に片耳に寄った」「タッピング音の位置が突然移った」"
            "と感じる瞬間に相当します。"
        ),
        recommendation=(
            "意図的な定位演出 (例: 耳元への移動) の可能性が高いです。"
            "違和感が強ければその秒数前後だけスキップして視聴することもできます。"
        ),
        technical_ref=f"{flag.code} · {flag.message}",
    )


def _build_pseudo_mono(flag: Flag, record: MetricRecord) -> Finding:
    corr = record.correlation
    pearson = corr.pearson_r if corr is not None else float("nan")
    return Finding(
        title="ステレオ表記ですが実質モノラルです",
        severity=flag.severity,
        explanation=(
            f"左右の波形相関が {pearson:.3f} と極端に高く、"
            "技術的にはステレオファイルですが聴感上はモノラルと変わりません。"
            "binaural / 立体 ASMR とうたわれていた場合、"
            "期待した立体感や耳元感は得られない可能性が高いです。"
        ),
        recommendation=(
            "dual-mono として意図された作品なら問題ありません。"
            "binaural 視聴を期待していたなら、別の音源を探した方が満足度が高いです。"
        ),
        technical_ref=f"{flag.code} · {flag.message}",
    )


def _build_phase_inv(flag: Flag, _record: MetricRecord) -> Finding:
    return Finding(
        title="スピーカー再生で低音がスカスカに聞こえる可能性",
        severity=flag.severity,
        explanation=(
            "低音域 (< 300 Hz) の L/R が逆位相気味になっています。"
            "スピーカー再生では左右の低音が空中で打ち消し合い、"
            "「ベース感が抜けて軽く聞こえる」状態になります。"
            "ヘッドホン / イヤホンでは耳元で物理的に分離されるので問題は起きません。"
        ),
        recommendation=(
            "**イヤホン / ヘッドホン視聴を推奨**。"
            "スピーカーで聴くなら、低音が薄い印象になることを了承しておいてください。"
        ),
        technical_ref=f"{flag.code} · {flag.message}",
    )


def _build_mid_side_narrow(flag: Flag, _record: MetricRecord) -> Finding:
    return Finding(
        title="ステレオ感が薄め (中央に音が固まる)",
        severity=flag.severity,
        explanation=(
            "左右で同じ音 (Mid 成分) が多く、"
            "左右で違う音 (Side 成分) が少ない構成です。"
            "binaural / dummy head による「耳元の立体感」を期待すると、"
            "やや物足りなく感じる可能性があります。"
        ),
        recommendation=(
            "立体感重視で視聴したい場合は、より広がり感のある音源の方が向いています。"
            "リラックス用 BGM 的に流すなら問題ありません。"
        ),
        technical_ref=f"{flag.code} · {flag.message}",
    )


_BAND_LABEL: dict[str, str] = {
    "BAND_BIAS_LOW": "低音域 (20–125 Hz, ベース / タッピング)",
    "BAND_BIAS_LOW_MID": "中低音域 (160–1.25 kHz, 声 / 体)",
    "BAND_BIAS_HIGH_MID": "中高音域 (1.6–6.3 kHz, 子音 / こすれ音)",
    "BAND_BIAS_HIGH": "高音域 (8–20 kHz, 息 / シュッ音)",
}


def _build_band_bias(flag: Flag, _record: MetricRecord) -> Finding:
    band_name = _BAND_LABEL.get(flag.code, "未知の帯域")
    return Finding(
        title=f"{band_name} が片耳寄りに聞こえます",
        severity=flag.severity,
        explanation=(
            f"{band_name} だけ左右でバランスが大きく崩れています。"
            "全体としてはステレオでも、この帯域に該当する音 "
            "(例えば低音域なら低いタッピング、高音域なら息遣いの細い音) "
            "が片耳に偏って届くことになります。"
        ),
        recommendation=(
            "気になる場合は片イヤホンで聴き比べると判別しやすいです。"
            "ASMR の素材特性 (片側で出てる音) であって意図的な可能性もあります。"
        ),
        technical_ref=f"{flag.code} · {flag.message}",
    )


def _build_true_peak(flag: Flag, record: MetricRecord) -> Finding:
    dyn = record.dynamics
    peak = dyn.true_peak_dbtp_max if dyn is not None else float("nan")
    if flag.severity is Verdict.FAIL:
        title = "音割れする箇所があります"
        explanation = (
            f"true peak が {peak:+.2f} dBTP に達しており、"
            "再生機材によっては「バリッ」「ジリッ」と歪んで聞こえる場面があります。"
            "安いイヤホンやスマホ内蔵スピーカーで特に顕著で、"
            "大音量再生では確実に歪みます。"
        )
        recommendation = (
            "**マスターボリュームを控えめにして視聴してください**。"
            "それでも気になる場合は再生機材 (DAC / ヘッドホンアンプ) の"
            "クオリティを上げると改善します。"
        )
    else:
        title = "音量大きめ、機材次第で音割れの可能性"
        explanation = (
            f"true peak が {peak:+.2f} dBTP まで上がっており、"
            "ヘッドルームに余裕が少なめです。"
            "高音質な再生環境では問題ないことが多いですが、"
            "安い機材や大音量設定では歪みが出るかもしれません。"
        )
        recommendation = "マスターボリュームを少し下げて視聴するのが無難です。"
    return Finding(
        title=title,
        severity=flag.severity,
        explanation=explanation,
        recommendation=recommendation,
        technical_ref=f"{flag.code} · {flag.message}",
    )


def _build_gate_reject(flag: Flag, _record: MetricRecord) -> Finding:
    return Finding(
        title="片側または両方のチャンネルがほぼ無音です",
        severity=flag.severity,
        explanation=(
            "L または R チャンネルがほぼ無音レベル "
            "(BS.1770 の絶対ゲート −70 LUFS 以下) になっています。"
            "音源側がモノラル素材を片チャンネルだけに収録した可能性、"
            "あるいは販売物として明らかに不良 (録音漏れ) の可能性があります。"
        ),
        recommendation=(
            "ステレオ音源として購入したものであれば、不良品の可能性があります。"
            "販売元 / プラットフォームに確認することをおすすめします。"
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
        title=f"検査ルール {flag.code} が反応しました",
        severity=flag.severity,
        explanation=(
            f"このルールへの平語の解説はまだ用意されていません。技術的な詳細: {flag.message}"
        ),
        recommendation="詳細データのフラグ一覧と raw metric を参照してください。",
        technical_ref=f"{flag.code} · {flag.message}",
    )


# ----------------------------------------------------------------------
# Headline / summary builders (listener framing)
# ----------------------------------------------------------------------
_HEADLINE_PREFIX = {
    Verdict.OK: "✅ 視聴 OK",
    Verdict.WARN: "⚠ 視聴上の注意",
    Verdict.FAIL: "✗ 視聴環境を選びます",
}


def _build_headline(verdict: Verdict, findings: tuple[Finding, ...]) -> str:
    prefix = _HEADLINE_PREFIX[verdict]
    if not findings:
        return f"{prefix} — 通常の視聴環境で安心して聞けます"
    top = max(findings, key=lambda f: f.severity.value)
    return f"{prefix} — {top.title}"


def _build_summary(verdict: Verdict, findings: tuple[Finding, ...]) -> str:
    fail_count = sum(1 for f in findings if f.severity is Verdict.FAIL)
    warn_count = sum(1 for f in findings if f.severity is Verdict.WARN)
    if verdict is Verdict.OK:
        return (
            "L/R バランス・音量レベル・帯域バランス・true peak のいずれも"
            "規定の閾値内に収まっています。通常の再生環境で問題なく視聴できます。"
        )
    if verdict is Verdict.WARN:
        return (
            f"視聴前に知っておくべき点が {warn_count} 件あります。"
            "致命的な問題ではないので、下記を踏まえて再生環境 / 音量を"
            "調整すれば快適に視聴できます。"
        )
    return (
        f"再生環境への適性に大きく影響する問題が {fail_count} 件 + 注意点 {warn_count} 件あります。"
        "視聴前に下記を確認し、必要なら再生機材 / 音量を調整してください。"
        "音源そのものに問題がある場合は別の音源を検討する価値があります。"
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
        headline = "ℹ 視聴チェック対象外"
        summary = (
            f"このファイルは L/R バランスの検査対象になりません ({reason})。"
            "モノラル素材や 5.1ch などのマルチチャンネル素材は仕様上スキップされます。"
            "ファイルが視聴できないという意味ではありません。"
        )
    else:  # ERRORED
        headline = "✗ ファイルが読めません"
        summary = (
            f"ファイルのデコードに失敗しました ({reason})。"
            "ファイル形式が壊れている、または対応していない可能性があります。"
        )
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
