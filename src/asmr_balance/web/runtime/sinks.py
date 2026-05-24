"""Sinks bridging the sync ``scan_many`` worker loop to the async SSE handler.

The :class:`JsonStreamingSink` implements the existing
:class:`asmr_balance.sink.base.Sink` protocol — the scan worker calls
``open / write / close`` from a worker thread; the sink schedules each event
into the parent event loop's ``asyncio.Queue`` via
``loop.call_soon_threadsafe``. The SSE handler awaits items off the same
queue and serializes them as ``data:`` lines.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from asmr_balance.web.dto import ScanFileEvent

if TYPE_CHECKING:
    from asmr_balance.scan.pipeline import FileResult


@dataclass(slots=True)
class JsonStreamingSink:
    """Sink that pushes one :class:`ScanFileEvent` per file into ``queue``.

    Belongs to one job; ``total`` is the number of files the orchestrator
    resolved up-front so each event carries a ``(sequence, total)`` ratio
    the UI can render as a progress bar.
    """

    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[ScanFileEvent | None]
    total: int
    _sequence: int = field(default=0, init=False)

    def open(self) -> None:
        return

    def write(self, result: FileResult) -> None:
        self._sequence += 1
        event = ScanFileEvent.from_file_result(result, sequence=self._sequence, total=self.total)
        self.loop.call_soon_threadsafe(self.queue.put_nowait, event)

    def close(self) -> None:
        return
