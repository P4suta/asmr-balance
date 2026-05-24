"""Single-file inspection use case.

Bridges in-memory upload bytes to the path-coupled :func:`scan_one` pipeline
by materializing the upload to a temporary file (the audio backends — soundfile
and PyAV — both probe via path). The temp file is always cleaned up.

Two error classes can be raised: :class:`UnsupportedAudioFormatError` for an
upload whose filename suffix is not in :data:`AUDIO_EXTENSIONS`, and
:class:`AudioDecodeError` when ``scan_one`` returns a record with status
:attr:`ScanStatus.ERRORED` (the decoder gave up). ``SKIPPED`` records (mono
input, unsupported channel layout) are *not* errors and are returned as-is so
the UI can surface ``skip_reason``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path, PurePosixPath

from asmr_balance.config.model import Config
from asmr_balance.metrics.record import ScanStatus
from asmr_balance.scan.pipeline import FileResult, scan_one
from asmr_balance.source.audio_extensions import AUDIO_EXTENSIONS
from asmr_balance.web.use_cases.errors import (
    AudioDecodeError,
    UnsupportedAudioFormatError,
)


def _normalized_suffix(filename: str | None) -> str:
    if not filename:
        return ""
    # PurePosixPath sidesteps platform-dependent suffix parsing for client-
    # provided names (Windows clients may send a Win-style basename).
    return PurePosixPath(filename).suffix.lower()


def _session_config() -> Config:
    """Config used for one inspect call — sequential, default thresholds."""
    return Config().with_overrides(workers=1)


def perform_inspect(audio_bytes: bytes, original_filename: str | None) -> FileResult:
    """Run the analysis pipeline on a single upload.

    Raises:
        UnsupportedAudioFormatError: when the filename suffix is unknown.
        AudioDecodeError: when the audio backend cannot decode the bytes.
    """
    suffix = _normalized_suffix(original_filename)
    if suffix not in AUDIO_EXTENSIONS:
        raise UnsupportedAudioFormatError(suffix, supported=AUDIO_EXTENSIONS)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(audio_bytes)
    try:
        result = scan_one(tmp_path, _session_config())
    finally:
        tmp_path.unlink(missing_ok=True)
    if result.record.status is ScanStatus.ERRORED:
        raise AudioDecodeError(
            original_filename=original_filename or "<unnamed>",
            reason=result.record.skip_reason or "unknown decode failure",
        )
    return result
