"""Deterministic WAV signal generation for e2e tests.

Used by ``tests/e2e/test_scan_fixtures.py`` to produce small canonical files
without depending on external binaries.
"""

from __future__ import annotations

import math
import subprocess
from typing import TYPE_CHECKING

import numpy as np
import soundfile as sf

if TYPE_CHECKING:
    from pathlib import Path

SAMPLE_RATE: int = 48000


def _sine(duration_sec: float, freq_hz: float, amp: float, sr: int = SAMPLE_RATE) -> np.ndarray:
    n = int(duration_sec * sr)
    t = np.arange(n, dtype=np.float64) / sr
    return (amp * np.sin(2.0 * math.pi * freq_hz * t)).astype(np.float32)


def _pink(duration_sec: float, seed: int, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Approximate pink noise via 1/√f shaping in the frequency domain."""
    n = int(duration_sec * sr)
    rng = np.random.default_rng(seed)
    spec = rng.standard_normal(n // 2 + 1) + 1j * rng.standard_normal(n // 2 + 1)
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    freqs[0] = 1.0
    spec = spec / np.sqrt(freqs)
    out = np.fft.irfft(spec, n=n).real.astype(np.float32)
    peak = float(np.max(np.abs(out)))
    if peak > 0.0:
        out = (out * (0.25 / peak)).astype(np.float32)
    return out


def write_balanced_tone(path: Path, *, duration_sec: float = 2.5) -> None:
    sine = _sine(duration_sec, 1000.0, 0.5)
    sf.write(str(path), np.column_stack([sine, sine]).astype(np.float32), SAMPLE_RATE)


def write_panned_tone(path: Path, *, duration_sec: float = 2.5, db_drop: float = 12.0) -> None:
    left = _sine(duration_sec, 1000.0, 0.5)
    right = _sine(duration_sec, 1000.0, 0.5 * 10.0 ** (-db_drop / 20.0))
    sf.write(str(path), np.column_stack([left, right]).astype(np.float32), SAMPLE_RATE)


def write_dual_mono(path: Path, *, duration_sec: float = 2.5) -> None:
    pink = _pink(duration_sec, seed=1234)
    sf.write(str(path), np.column_stack([pink, pink]).astype(np.float32), SAMPLE_RATE)


def write_phase_inverted(path: Path, *, duration_sec: float = 2.5) -> None:
    pink = _pink(duration_sec, seed=4321)
    sf.write(str(path), np.column_stack([pink, -pink]).astype(np.float32), SAMPLE_RATE)


def write_silent(path: Path, *, duration_sec: float = 1.0) -> None:
    n = int(duration_sec * SAMPLE_RATE)
    sf.write(str(path), np.zeros((n, 2), dtype=np.float32), SAMPLE_RATE)


def write_mono(path: Path, *, duration_sec: float = 1.0) -> None:
    sine = _sine(duration_sec, 1000.0, 0.5)
    sf.write(str(path), sine, SAMPLE_RATE)


def write_5_1(path: Path, *, duration_sec: float = 1.0) -> None:
    """Six-channel WAV (FL, FR, FC, LFE, BL, BR), FL == FR balanced."""
    fl = _sine(duration_sec, 1000.0, 0.4)
    fr = _sine(duration_sec, 1000.0, 0.4)
    silence = np.zeros_like(fl)
    block = np.column_stack([fl, fr, silence, silence, silence, silence]).astype(np.float32)
    sf.write(str(path), block, SAMPLE_RATE)


def reencode_wav_to(wav: Path, target: Path) -> None:
    """Use system ``ffmpeg`` to re-encode ``wav`` into the container at ``target``.

    The target codec is inferred from ``target.suffix``: ``.mp4`` / ``.m4a`` use
    AAC, ``.mkv`` and ``.webm`` use Opus.
    """
    suffix = target.suffix.lower()
    if suffix in {".mp4", ".m4a", ".mov", ".aac"}:
        codec = ["-c:a", "aac", "-b:a", "192k"]
    elif suffix in {".webm", ".mkv"}:
        codec = ["-c:a", "libopus", "-b:a", "128k"]
    elif suffix == ".mp3":
        codec = ["-c:a", "libmp3lame", "-b:a", "192k"]
    else:
        codec = ["-c:a", "pcm_s16le"]
    cmd = ["ffmpeg", "-y", "-i", str(wav), *codec, str(target)]
    subprocess.run(cmd, check=True, capture_output=True)
