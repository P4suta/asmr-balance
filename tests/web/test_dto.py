from __future__ import annotations

from pathlib import Path

from asmr_balance.algebra.semilattice import Verdict
from asmr_balance.config.model import Config
from asmr_balance.rules.algebra import Flag
from asmr_balance.scan.pipeline import scan_one
from asmr_balance.web.dto import (
    ErrorEnvelope,
    FlagDto,
    HealthResponse,
    InspectResponse,
    SchemaResponse,
)


def test_health_response_round_trip() -> None:
    response = HealthResponse(status="ok", version="9.9.9")
    assert response.model_dump() == {"status": "ok", "version": "9.9.9"}


def test_schema_response_tuple_preserved() -> None:
    response = SchemaResponse(columns=("a", "b", "c"))
    assert response.columns == ("a", "b", "c")


def test_flag_dto_from_flag_emits_severity_name() -> None:
    flag = Flag(code="TEST", severity=Verdict.WARN, message="hello")
    dto = FlagDto.from_flag(flag)
    assert dto.code == "TEST"
    assert dto.severity == "WARN"
    assert dto.message == "hello"


def test_inspect_response_from_file_result(balanced_wav: Path) -> None:
    result = scan_one(balanced_wav, Config().with_overrides(workers=1))
    response = InspectResponse.from_file_result(result, source_name="balanced.wav")
    assert response.source_name == "balanced.wav"
    assert response.verdict == result.verdict.name
    assert response.elapsed_sec == result.elapsed_sec
    assert len(response.flags) == len(result.flags)
    assert response.record == result.record


def test_error_envelope_defaults_context_to_empty_dict() -> None:
    envelope = ErrorEnvelope(
        error="X",
        detail="d",
        status=400,
        trace_id="t",
    )
    assert envelope.context == {}


def test_error_envelope_round_trip() -> None:
    envelope = ErrorEnvelope(
        error="UnsupportedAudioFormatError",
        detail="unsupported audio format: .xyz",
        status=415,
        context={"suffix": ".xyz", "supported": [".wav"]},
        trace_id="deadbeef",
    )
    assert envelope.model_dump() == {
        "error": "UnsupportedAudioFormatError",
        "detail": "unsupported audio format: .xyz",
        "status": 415,
        "context": {"suffix": ".xyz", "supported": [".wav"]},
        "trace_id": "deadbeef",
    }
