"""Domain types for asmr-balance.

- ``StereoBlock``: PCM tile streamed through analyzers (NDArray, shape ``(N, 2)``,
  dtype ``float32``).  Boundary asserts only; pydantic is reserved for semantic
  records (ADR-0001).
- ``MetricRecord``, ``FileResult``, ``Flag``, ``Verdict``: pydantic frozen
  records that travel from analyzers → flags → report writer.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path  # runtime import: pydantic needs Path for MetricRecord.file_path
from typing import Final

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

type StereoBlock = NDArray[np.float32]
"""Shape ``(N, 2)``, contiguous, dtype ``float32`` (validated at decode boundary)."""

STEREO_CHANNELS: Final[int] = 2


class Verdict(StrEnum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"


class Flag(BaseModel):
    """A single triggered policy outcome."""

    model_config = ConfigDict(frozen=True)

    code: str = Field(..., description="Symbolic flag id, e.g. LR_BALANCE_FAIL")
    severity: Verdict
    message: str = Field("", description="Human-readable explanation")


class MetricRecord(BaseModel):
    """All numeric metrics for one audio file."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    # --- file metadata ---
    file_path: Path
    sample_rate: int
    duration_sec: float
    channel_layout: str
    skipped: bool = False
    skip_reason: str | None = None

    # --- loudness (BS.1770) ---
    lufs_i_stereo: float = float("nan")
    single_channel_lufs_l: float = float("nan")
    single_channel_lufs_r: float = float("nan")
    single_channel_lufs_ungated_l: float = float("nan")
    single_channel_lufs_ungated_r: float = float("nan")
    delta_lu: float = float("nan")
    delta_lu_ungated: float = float("nan")

    # --- correlation / M-S ---
    pearson_r: float = float("nan")
    ms_ratio_db: float = float("nan")

    # --- band imbalance (dB, L/R per band) ---
    band_imbalance_low: float = float("nan")
    band_imbalance_low_mid: float = float("nan")
    band_imbalance_high_mid: float = float("nan")
    band_imbalance_high: float = float("nan")

    # --- sliding window (1 s) ---
    sliding_max_lu: float = float("nan")
    sliding_p95_lu: float = float("nan")
    sliding_std_lu: float = float("nan")
    sliding_t_max_sec: float = float("nan")

    # --- low-band phase ---
    low_phase_coherence: float = float("nan")


class FileResult(BaseModel):
    """A row of the final report: metrics + flags + verdict."""

    model_config = ConfigDict(frozen=True)

    metrics: MetricRecord
    flags: tuple[Flag, ...] = ()
    verdict: Verdict = Verdict.OK
