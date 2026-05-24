from __future__ import annotations

import asyncio
from pathlib import Path

from asmr_balance.config.model import Config
from asmr_balance.scan.pipeline import scan_one
from asmr_balance.web.dto import ScanFileEvent
from asmr_balance.web.runtime.sinks import JsonStreamingSink


def test_write_enqueues_scan_file_event(balanced_wav: Path) -> None:
    async def runner() -> ScanFileEvent | None:
        queue: asyncio.Queue[ScanFileEvent | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        sink = JsonStreamingSink(loop=loop, queue=queue, total=1)
        result = scan_one(balanced_wav, Config().with_overrides(workers=1))
        sink.open()
        sink.write(result)
        sink.close()
        # Drain via call_soon_threadsafe -- give the loop a tick.
        await asyncio.sleep(0)
        return await queue.get()

    event = asyncio.run(runner())
    assert isinstance(event, ScanFileEvent)
    assert event.sequence == 1
    assert event.total == 1
    assert event.source_name == "balanced.wav"


def test_sequence_increments_per_write(balanced_wav: Path) -> None:
    async def runner() -> list[ScanFileEvent | None]:
        queue: asyncio.Queue[ScanFileEvent | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        sink = JsonStreamingSink(loop=loop, queue=queue, total=3)
        result = scan_one(balanced_wav, Config().with_overrides(workers=1))
        sink.open()
        sink.write(result)
        sink.write(result)
        sink.write(result)
        sink.close()
        await asyncio.sleep(0)
        return [await queue.get() for _ in range(3)]

    events = asyncio.run(runner())
    assert [e.sequence for e in events if e is not None] == [1, 2, 3]
