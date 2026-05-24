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


def test_library_entry_dto_from_entry() -> None:
    from asmr_balance.web.dto import LibraryEntryDto
    from asmr_balance.web.use_cases.library import LibraryEntry

    entry = LibraryEntry(name="x.wav", type="file", rel_path="album/x.wav", is_audio=True, size=42)
    dto = LibraryEntryDto.from_entry(entry)
    assert dto.name == "x.wav"
    assert dto.type == "file"
    assert dto.rel_path == "album/x.wav"
    assert dto.is_audio is True
    assert dto.size == 42


def test_scan_job_response_from_job(tmp_path: Path) -> None:
    import asyncio
    from datetime import UTC, datetime
    from uuid import uuid4

    from asmr_balance.web.dto import ScanJobResponse
    from asmr_balance.web.runtime.jobs import Job

    job = Job(
        id=uuid4(),
        requested_paths=("a", "b"),
        resolved_files=(tmp_path / "x.wav",),
        out_dir=tmp_path,
        queue=asyncio.Queue(),
        started_at=datetime.now(UTC),
    )
    dto = ScanJobResponse.from_job(job)
    assert dto.job_id == str(job.id)
    assert dto.total_files == 1
    assert dto.requested_paths == ("a", "b")


def test_scan_job_status_from_job_terminal(tmp_path: Path) -> None:
    import asyncio
    from datetime import UTC, datetime
    from uuid import uuid4

    from asmr_balance.web.dto import ScanJobStatus
    from asmr_balance.web.runtime.jobs import Job, JobState

    started = datetime.now(UTC)
    job = Job(
        id=uuid4(),
        requested_paths=("a",),
        resolved_files=(),
        out_dir=tmp_path,
        queue=asyncio.Queue(),
        started_at=started,
        state=JobState.FAILED,
        completed_at=started,
        failed_reason="boom",
    )
    dto = ScanJobStatus.from_job(job)
    assert dto.state == "failed"
    assert dto.failed_reason == "boom"
    assert dto.completed_at == started


def test_scan_file_event_from_file_result(balanced_wav: Path) -> None:
    from asmr_balance.config.model import Config
    from asmr_balance.scan.pipeline import scan_one
    from asmr_balance.web.dto import ScanFileEvent

    result = scan_one(balanced_wav, Config().with_overrides(workers=1))
    event = ScanFileEvent.from_file_result(result, sequence=2, total=5)
    assert event.type == "file_done"
    assert event.sequence == 2
    assert event.total == 5
    assert event.source_name == "balanced.wav"
    assert event.verdict == result.verdict.name
    assert event.delta_lu_db is not None  # balanced wav: ANALYZED → ΔLU present


def test_scan_file_event_from_skipped_record(mono_wav: Path) -> None:
    # Mono files are SKIPPED; loudness subtree is None, so delta_lu_db
    # must serialize as None instead of crashing.
    from asmr_balance.config.model import Config
    from asmr_balance.scan.pipeline import scan_one
    from asmr_balance.web.dto import ScanFileEvent

    result = scan_one(mono_wav, Config().with_overrides(workers=1))
    event = ScanFileEvent.from_file_result(result, sequence=1, total=1)
    assert event.record_status == "skipped"
    assert event.delta_lu_db is None
