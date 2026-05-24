from __future__ import annotations

from pathlib import Path

import pytest

from asmr_balance.web.use_cases.errors import (
    AudioDecodeError,
    UnsupportedAudioFormatError,
)
from asmr_balance.web.use_cases.inspect import (
    _normalized_suffix,
    perform_inspect,
)


def test_normalized_suffix_handles_none() -> None:
    assert _normalized_suffix(None) == ""


def test_normalized_suffix_handles_empty() -> None:
    assert _normalized_suffix("") == ""


def test_normalized_suffix_lowercases() -> None:
    assert _normalized_suffix("Track.WAV") == ".wav"


def test_normalized_suffix_handles_windows_basename() -> None:
    # PurePosixPath sees backslashes as part of the filename, so the suffix
    # is correctly parsed off the trailing dot regardless of OS separator.
    assert _normalized_suffix("C:/audio/track.flac") == ".flac"


def test_perform_inspect_rejects_unknown_suffix() -> None:
    with pytest.raises(UnsupportedAudioFormatError) as exc_info:
        perform_inspect(b"junk", "doc.xyz")
    assert exc_info.value.suffix == ".xyz"
    assert ".wav" in exc_info.value.context["supported"]


def test_perform_inspect_rejects_no_filename() -> None:
    with pytest.raises(UnsupportedAudioFormatError):
        perform_inspect(b"junk", None)


def test_perform_inspect_happy_path(balanced_wav: Path) -> None:
    result = perform_inspect(balanced_wav.read_bytes(), "balanced.wav")
    assert result.record.status.value == "analyzed"


def test_perform_inspect_corrupt_raises_decode_error() -> None:
    junk = b"\x00" * 1024
    with pytest.raises(AudioDecodeError) as exc_info:
        perform_inspect(junk, "broken.wav")
    assert exc_info.value.original_filename == "broken.wav"
    assert exc_info.value.reason
