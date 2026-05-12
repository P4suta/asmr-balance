"""File-level parallelism via :class:`ProcessPoolExecutor`.

Each worker process opens its own :class:`Source` (re-probing the file),
runs the graph, and returns a :class:`FileResult`. Only fully picklable values
(frozen pydantic / frozen dataclass / Enum) cross the process boundary.

We deliberately do *not* attempt intra-file chunk parallelism: IIR filters
are Mealy machines whose state cannot be merged across a stream split without
breaking BS.1770 parity. File-level concurrency saturates typical workloads
because asmr-balance CPU is dominated by per-file K-weighting + bandsplit.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from typing import TYPE_CHECKING

from asmr_balance.scan.pipeline import FileResult, scan_one

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from pathlib import Path

    from asmr_balance.config.model import Config


def _resolved_workers(requested: int) -> int:
    if requested > 1:
        return requested
    if requested == 1:
        return 1
    return max(1, os.cpu_count() or 1)


def _scan_one_picklable(args: tuple[Path, Config]) -> FileResult:
    """Top-level wrapper required for :func:`ProcessPoolExecutor.map`."""
    path, config = args
    return scan_one(path, config)


def scan_many(paths: Iterable[Path], config: Config) -> Iterator[FileResult]:
    """Stream :class:`FileResult` for each path, sequentially or in parallel."""
    paths_list = list(paths)
    if not paths_list:
        return
    workers = _resolved_workers(config.workers)
    if workers == 1:
        for p in paths_list:
            yield scan_one(p, config)
        return
    with ProcessPoolExecutor(max_workers=workers) as ex:
        yield from ex.map(_scan_one_picklable, [(p, config) for p in paths_list])
