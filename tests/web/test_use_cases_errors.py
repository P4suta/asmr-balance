from __future__ import annotations

from asmr_balance.web.use_cases.errors import (
    AudioDecodeError,
    DomainError,
    LibraryPathError,
    UnsupportedAudioFormatError,
)


def test_domain_error_default_status_code() -> None:
    err = DomainError("oops")
    assert err.status_code == 400
    assert err.context == {}


def test_domain_error_carries_explicit_context() -> None:
    err = DomainError("oops", context={"foo": 1})
    assert err.context == {"foo": 1}


def test_unsupported_audio_format_error_carries_supported() -> None:
    err = UnsupportedAudioFormatError(".xyz", supported=frozenset({".wav", ".mp3"}))
    assert err.status_code == 415
    assert err.suffix == ".xyz"
    assert err.context["suffix"] == ".xyz"
    assert err.context["supported"] == [".mp3", ".wav"]


def test_audio_decode_error_captures_reason() -> None:
    err = AudioDecodeError(original_filename="x.wav", reason="header missing")
    assert err.status_code == 422
    assert err.original_filename == "x.wav"
    assert err.reason == "header missing"
    assert "header missing" in str(err)


def test_library_path_error_captures_reason() -> None:
    err = LibraryPathError("/library/../etc", reason="traversal")
    assert err.status_code == 404
    assert err.context == {"requested": "/library/../etc", "reason": "traversal"}
