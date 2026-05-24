"""Domain error hierarchy.

Every use case raises one of these classes (never a bare :class:`Exception`).
Each error carries:

* a stable HTTP status code (``status_code`` class attribute)
* a human-readable detail (``str(exc)``)
* a structured ``context`` mapping that is preserved through the wire format
  and the log line — invaluable when triaging from production logs.

The HTTP layer (:mod:`asmr_balance.web.errors`) renders every
:class:`DomainError` uniformly through :class:`ErrorEnvelope`; no route ever
needs to know which concrete subclass was raised.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar


class DomainError(Exception):
    """Base class for all use-case errors with HTTP-mappable semantics."""

    status_code: ClassVar[int] = 400

    def __init__(self, message: str, *, context: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.context: dict[str, Any] = dict(context) if context else {}


class UnsupportedAudioFormatError(DomainError):
    """Upload filename suffix is not in :data:`AUDIO_EXTENSIONS`."""

    status_code: ClassVar[int] = 415

    def __init__(self, suffix: str, *, supported: frozenset[str]) -> None:
        super().__init__(
            f"unsupported audio format: {suffix or '<none>'}",
            context={"suffix": suffix, "supported": sorted(supported)},
        )
        self.suffix = suffix


class AudioDecodeError(DomainError):
    """The audio backend (soundfile / PyAV) refused to decode the upload."""

    status_code: ClassVar[int] = 422

    def __init__(self, *, original_filename: str, reason: str) -> None:
        super().__init__(
            f"failed to decode {original_filename!r}: {reason}",
            context={"original_filename": original_filename, "reason": reason},
        )
        self.original_filename = original_filename
        self.reason = reason


class LibraryPathError(DomainError):
    """Library browse / scan target was missing or outside the mount."""

    status_code: ClassVar[int] = 404

    def __init__(self, requested: str, *, reason: str) -> None:
        super().__init__(
            f"library path error: {reason} ({requested!r})",
            context={"requested": requested, "reason": reason},
        )
        self.requested = requested
        self.reason = reason


class JobNotFoundError(DomainError):
    """A scan job ID does not exist in the registry (or has been evicted)."""

    status_code: ClassVar[int] = 404

    def __init__(self, job_id: str) -> None:
        super().__init__(
            f"scan job not found: {job_id}",
            context={"job_id": job_id},
        )
        self.job_id = job_id


class EmptyScanRequestError(DomainError):
    """The scan request resolved to zero audio files."""

    status_code: ClassVar[int] = 400

    def __init__(self, requested: tuple[str, ...]) -> None:
        super().__init__(
            f"scan request resolved to zero audio files: {list(requested)!r}",
            context={"requested": list(requested)},
        )


class ScanReportNotReadyError(DomainError):
    """The report file is not yet (or no longer) available for download."""

    status_code: ClassVar[int] = 404

    def __init__(self, job_id: str, *, state: str, reason: str) -> None:
        super().__init__(
            f"report not ready: job {job_id} is {state} ({reason})",
            context={"job_id": job_id, "state": state, "reason": reason},
        )
